from collections.abc import AsyncIterator
from typing import Any

import anthropic

from app.llm.base import (
    AssistantMessage,
    LLMResponse,
    Message,
    StopReason,
    TextStream,
    ToolCall,
    ToolChoice,
    ToolResultsMessage,
    ToolSpec,
    Usage,
    UserMessage,
)
from app.llm.errors import (
    LLMAuthenticationError,
    LLMNotConfiguredError,
    LLMRateLimitError,
    LLMUpstreamError,
)
from app.tracing import record_llm_usage, trace_span

_STOP_REASONS: dict[str, StopReason] = {
    "end_turn": "end_turn",
    "tool_use": "tool_use",
    "max_tokens": "max_tokens",
    "refusal": "refusal",
}

_FALLBACK_BETA = "server-side-fallback-2026-07-01"


class AnthropicLLM:
    """Claude 适配器：把通用消息格式转换成 Messages API 请求。

    凭证由 SDK 从环境变量读取（ANTHROPIC_API_KEY，可选 ANTHROPIC_BASE_URL）。
    """

    def __init__(
        self,
        *,
        model: str,
        max_tokens: int = 16000,
        enable_fallbacks: bool = True,
        enable_prompt_cache: bool = True,
        client: anthropic.AsyncAnthropic | None = None,
    ) -> None:
        self.model = model
        self.max_tokens = max_tokens
        self.enable_fallbacks = enable_fallbacks
        self.enable_prompt_cache = enable_prompt_cache
        self.client = client or anthropic.AsyncAnthropic()

    @trace_span(kind="llm", name="anthropic.stream")
    async def stream_chat(
        self,
        messages: list[Message],
        *,
        system: str | None = None,
        prompt_version: str | None = None,
    ) -> AsyncIterator[str]:
        """流式出字，只支持不带工具的纯文本场景。"""
        params: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": [_to_anthropic_message(m) for m in messages],
        }
        if system:
            params["system"] = system

        stream = TextStream()
        async with self.client.messages.stream(**params) as active:
            async for delta in active.text_stream:
                await stream.push(delta)
                yield delta
            # usage 和 stop_reason 只在流结束时才拿得到
            final = await active.get_final_message()

        raw = final.usage
        usage = Usage(
            input_tokens=raw.input_tokens,
            output_tokens=raw.output_tokens,
            cache_read_tokens=getattr(raw, "cache_read_input_tokens", None) or 0,
            cache_write_tokens=getattr(raw, "cache_creation_input_tokens", None) or 0,
        )
        stream.finish(
            model=final.model,
            stop_reason=_STOP_REASONS.get(final.stop_reason or "", "other"),
            usage=usage,
        )
        record_llm_usage(
            model=stream.model,
            input_tokens=usage.input_tokens + usage.cache_read_tokens + usage.cache_write_tokens,
            output_tokens=usage.output_tokens,
            prompt_version=prompt_version,
        )

    @trace_span(kind="llm", name="anthropic.chat")
    async def chat(
        self,
        messages: list[Message],
        *,
        system: str | None = None,
        tools: list[ToolSpec] | None = None,
        tool_choice: ToolChoice = "auto",
        prompt_version: str | None = None,
    ) -> LLMResponse:
        params: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": [_to_anthropic_message(m) for m in messages],
        }
        if system:
            params["system"] = system
        if tools:
            params["tools"] = [
                {"name": t.name, "description": t.description, "input_schema": t.input_schema}
                for t in tools
            ]
            params["tool_choice"] = {"type": tool_choice}
        if self.enable_prompt_cache:
            params["cache_control"] = {"type": "ephemeral"}

        try:
            if self.enable_fallbacks:
                # 安全分类器误拒时，由服务端自动换模型重跑，避免误报变成故障
                response = await self.client.beta.messages.create(
                    **params, betas=[_FALLBACK_BETA], fallbacks="default"
                )
            else:
                response = await self.client.messages.create(**params)
        except TypeError as e:
            # SDK 完全找不到凭证时抛的是 TypeError，而不是 API 异常
            if "authentication" in str(e):
                raise LLMNotConfiguredError("未配置 ANTHROPIC_API_KEY") from e
            raise
        except anthropic.AuthenticationError as e:
            raise LLMAuthenticationError("Anthropic 凭证无效") from e
        except anthropic.RateLimitError as e:
            raise LLMRateLimitError("Anthropic 限流") from e
        except anthropic.APIConnectionError as e:
            raise LLMUpstreamError("无法连接 Anthropic API") from e
        except anthropic.APIStatusError as e:
            raise LLMUpstreamError(f"Anthropic API 错误：{e}") from e

        result = _from_anthropic_response(response)
        record_llm_usage(
            model=result.model,
            # Anthropic 的 input_tokens 不含缓存部分，缓存读写要单独加进来
            input_tokens=result.usage.input_tokens
            + result.usage.cache_read_tokens
            + result.usage.cache_write_tokens,
            output_tokens=result.usage.output_tokens,
            prompt_version=prompt_version,
        )
        return result


def _to_anthropic_message(message: Message) -> dict[str, Any]:
    match message:
        case UserMessage(content=content):
            return {"role": "user", "content": content}
        case AssistantMessage(provider_content=blocks) if blocks is not None:
            # 原样回传，thinking 块必须保持不变
            return {"role": "assistant", "content": blocks}
        case AssistantMessage(text=text, tool_calls=calls):
            content: list[dict[str, Any]] = [{"type": "text", "text": text}] if text else []
            content += [
                {"type": "tool_use", "id": c.id, "name": c.name, "input": c.arguments}
                for c in calls
            ]
            return {"role": "assistant", "content": content}
        case ToolResultsMessage(results=results, note=note):
            # 同一轮的所有工具结果必须放在同一条 user 消息里
            blocks = [
                {
                    "type": "tool_result",
                    "tool_use_id": r.tool_call_id,
                    "content": r.content,
                    "is_error": r.is_error,
                }
                for r in results
            ]
            if note:
                blocks.append({"type": "text", "text": note})
            return {"role": "user", "content": blocks}
    raise TypeError(f"未知的消息类型：{type(message).__name__}")


def _from_anthropic_response(response: Any) -> LLMResponse:
    text_parts: list[str] = []
    tool_calls: list[ToolCall] = []
    for block in response.content:
        if block.type == "text":
            text_parts.append(block.text)
        elif block.type == "tool_use":
            tool_calls.append(ToolCall(id=block.id, name=block.name, arguments=block.input))

    raw_usage = response.usage
    usage = Usage(
        input_tokens=raw_usage.input_tokens,
        output_tokens=raw_usage.output_tokens,
        cache_read_tokens=getattr(raw_usage, "cache_read_input_tokens", None) or 0,
        cache_write_tokens=getattr(raw_usage, "cache_creation_input_tokens", None) or 0,
    )
    # 发生回退时 response.model 是实际服务的模型，trace 里按它记录
    model = response.model
    return LLMResponse(
        message=AssistantMessage(
            text="".join(text_parts), tool_calls=tool_calls, provider_content=response.content
        ),
        stop_reason=_STOP_REASONS.get(response.stop_reason or "", "other"),
        usage=usage,
        model=model,
    )
