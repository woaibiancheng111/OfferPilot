import asyncio

import pytest

from app.tracing import BatchExporter, InMemorySink, current_span, record_llm_usage, tracer
from app.tracing.serialize import safe_serialize


async def test_nested_spans_form_a_tree(flush):
    @tracer.observe("tool", name="inner")
    async def inner(x: int) -> int:
        record_llm_usage(model="m", input_tokens=3, output_tokens=2, cost=0.5)
        return x * 2

    @tracer.observe("agent", name="outer")
    async def outer(x: int) -> int:
        return await inner(x) + await inner(x)

    async with tracer.trace("request", user_id="u1"):
        assert await outer(1) == 4

    [trace] = await flush()
    assert trace.name == "request"
    assert trace.user_id == "u1"
    assert trace.status == "ok"
    assert [s.name for s in trace.spans] == ["outer", "inner", "inner"]

    outer_span, inner1, inner2 = trace.spans
    assert outer_span.parent_span_id is None
    assert inner1.parent_span_id == outer_span.id
    assert inner2.parent_span_id == outer_span.id
    assert inner1.input == {"x": 1}
    assert inner1.output == 2
    assert trace.total_tokens == 10
    assert trace.total_cost == pytest.approx(1.0)
    assert all(s.latency_ms is not None for s in trace.spans)


async def test_exception_marks_span_and_trace_as_error(flush):
    @tracer.observe("tool", name="boom")
    async def boom() -> None:
        raise ValueError("坏了")

    with pytest.raises(ValueError):
        async with tracer.trace("request"):
            await boom()

    [trace] = await flush()
    assert trace.status == "error"
    assert trace.spans[0].error == "ValueError: 坏了"
    assert trace.spans[0].ended_at is not None


async def test_span_without_trace_creates_implicit_trace(flush):
    @tracer.observe("custom", name="standalone")
    async def standalone() -> str:
        return "ok"

    await standalone()
    [trace] = await flush()
    assert trace.name == "standalone"
    assert len(trace.spans) == 1


async def test_concurrent_requests_do_not_mix_spans(flush):
    @tracer.observe("tool", name="work")
    async def work(tag: str) -> str:
        await asyncio.sleep(0.01)
        return tag

    async def handle(tag: str) -> None:
        async with tracer.trace(f"req-{tag}"):
            for _ in range(3):
                await work(tag)

    await asyncio.gather(*(handle(t) for t in "abcde"))

    traces = await flush()
    assert len(traces) == 5
    for trace in traces:
        tag = trace.name.removeprefix("req-")
        assert len(trace.spans) == 3
        assert all(s.input == {"tag": tag} for s in trace.spans)
        assert all(s.trace_id == trace.id for s in trace.spans)


async def test_capture_flags_hide_sensitive_payloads(flush):
    @tracer.observe("tool", name="parse_resume", capture_input=False, capture_output=False)
    async def parse_resume(raw_text: str) -> str:
        return raw_text.upper()

    await parse_resume("手机号 13800000000")
    [trace] = await flush()
    assert trace.spans[0].input is None
    assert trace.spans[0].output is None


async def test_current_span_is_restored_after_exit(trace_sink):
    assert current_span() is None
    async with tracer.span("agent", "outer") as outer:
        async with tracer.span("tool", "inner"):
            pass
        assert current_span() is outer
    assert current_span() is None


def test_safe_serialize_truncates_large_payloads():
    result = safe_serialize({"text": "x" * 1000}, max_chars=100)
    assert result["_truncated"] is True
    assert len(result["preview"]) == 100


def test_safe_serialize_falls_back_to_repr():
    class Opaque:
        def __repr__(self) -> str:
            return "<Opaque>"

    assert safe_serialize({"obj": Opaque()}, max_chars=1000) == {"obj": "<Opaque>"}


async def test_exporter_drops_when_queue_full():
    from app.tracing import Trace

    sink = InMemorySink()
    exporter = BatchExporter(sink, max_queue_size=2)
    for i in range(5):
        exporter.enqueue(Trace(name=str(i)))
    await exporter.flush()
    assert [t.name for t in sink.traces] == ["0", "1"]
    assert exporter.dropped == 3


async def test_exporter_survives_sink_failure():
    from app.tracing import Trace

    class BrokenSink:
        async def write(self, traces):
            raise RuntimeError("数据库挂了")

    exporter = BatchExporter(BrokenSink())
    exporter.enqueue(Trace(name="t"))
    await exporter.flush()  # 不应抛异常
    assert exporter.dropped == 1


async def test_exporter_background_task_flushes_periodically():
    from app.tracing import Trace

    sink = InMemorySink()
    exporter = BatchExporter(sink, flush_interval_s=0.01)
    exporter.start()
    exporter.enqueue(Trace(name="t"))
    for _ in range(100):
        if sink.traces:
            break
        await asyncio.sleep(0.01)
    await exporter.shutdown()
    assert len(sink.traces) == 1
