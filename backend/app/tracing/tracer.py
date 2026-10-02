import functools
import inspect
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import Any, ParamSpec, TypeVar

from app.tracing.exporter import BatchExporter
from app.tracing.serialize import safe_serialize
from app.tracing.span import Span, SpanKind, Trace

P = ParamSpec("P")
R = TypeVar("R")

# contextvars 保证 asyncio 并发时每个协程看到的都是自己的 trace/span，
# 用全局变量的话，两个并发请求的 span 会互相串到对方的树上。
_current_trace: ContextVar[Trace | None] = ContextVar("current_trace", default=None)
_current_span: ContextVar[Span | None] = ContextVar("current_span", default=None)


def current_trace() -> Trace | None:
    return _current_trace.get()


def current_span() -> Span | None:
    return _current_span.get()


class Tracer:
    def __init__(self, exporter: BatchExporter | None = None, max_payload_chars: int = 20000):
        self.exporter = exporter
        self.max_payload_chars = max_payload_chars

    def serialize(self, value: Any) -> Any:
        return safe_serialize(value, self.max_payload_chars)

    @asynccontextmanager
    async def trace(self, name: str, *, user_id: str | None = None) -> AsyncIterator[Trace]:
        """开启一个 trace。已经处在 trace 中时直接复用外层的，不嵌套新 trace。"""
        existing = _current_trace.get()
        if existing is not None:
            yield existing
            return

        trace = Trace(name=name, user_id=user_id)
        token = _current_trace.set(trace)
        try:
            yield trace
        except BaseException:
            trace.status = "error"
            raise
        finally:
            _current_trace.reset(token)
            trace.end()
            if self.exporter is not None:
                self.exporter.enqueue(trace)

    @asynccontextmanager
    async def span(self, kind: SpanKind, name: str, *, input: Any = None) -> AsyncIterator[Span]:
        """开启一个 span，自动挂到当前 span 下；没有外层 trace 时自动创建一个。"""
        async with self.trace(name) as trace:
            parent = _current_span.get()
            span = Span(
                trace_id=trace.id,
                kind=kind,
                name=name,
                parent_span_id=parent.id if parent else None,
                input=self.serialize(input) if input is not None else None,
            )
            trace.spans.append(span)
            token = _current_span.set(span)
            try:
                yield span
            except BaseException as e:
                span.error = f"{type(e).__name__}: {e}"
                raise
            finally:
                _current_span.reset(token)
                span.end()

    def observe(
        self,
        kind: SpanKind,
        name: str | None = None,
        *,
        capture_input: bool = True,
        capture_output: bool = True,
    ) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
        """装饰 async 函数，把每次调用记录为一个 span。

        涉及隐私的函数（比如处理原始简历）可以关掉 capture_input/capture_output。
        """

        def decorator(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
            span_name = name or func.__qualname__
            signature = inspect.signature(func)

            @functools.wraps(func)
            async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
                call_input = _bind_arguments(signature, args, kwargs) if capture_input else None
                async with self.span(kind, span_name, input=call_input) as span:
                    result = await func(*args, **kwargs)
                    if capture_output:
                        span.output = self.serialize(result)
                    return result

            return wrapper

        return decorator


def _bind_arguments(signature: inspect.Signature, args: tuple, kwargs: dict) -> dict[str, Any]:
    try:
        bound = signature.bind_partial(*args, **kwargs)
    except TypeError:
        return {"args": args, "kwargs": kwargs}
    return {k: v for k, v in bound.arguments.items() if k not in ("self", "cls")}


def record_llm_usage(
    *,
    model: str,
    input_tokens: int,
    output_tokens: int,
    prompt_version: str | None = None,
) -> None:
    """在当前 span 上记录模型用量，由 LLM 适配层调用。"""
    span = _current_span.get()
    if span is None:
        return
    span.model = model
    span.input_tokens += input_tokens
    span.output_tokens += output_tokens
    if prompt_version is not None:
        span.prompt_version = prompt_version


tracer = Tracer()
trace_span = tracer.observe
