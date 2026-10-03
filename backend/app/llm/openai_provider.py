"""OpenAI 协议适配器。

和 Anthropic 有三处不兼容的地方，都在这里做转换，Agent 层无感知：

1. ``system`` 不是独立参数，而是 messages 里的第一条 system 消息
2. 工具调用参数是 **JSON 字符串**，需要反序列化；工具结果是每条结果一条
   ``role=tool`` 消息（Anthropic 是把所有结果打包进一条 user 消息的 content 块）
3. ``provider_content`` 原样回传是 Anthropic 的私有能力，OpenAI 侧一律忽略并重建消息

另外 ``prompt_tokens`` 已经包含缓存命中的部分，所以这里上报用量时不能再把
cached_tokens 加一遍，否则 trace 里的 token 数会翻倍。
"""

import hashlib
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import openai

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
    LLMRateLimitError,
    LLMUpstreamError,
)
from app.tracing import record_llm_usage, trace_span

logger = logging.getLogger(__name__)

_FINISH_REASONS: dict[str, StopReason] = {
    "stop": "end_turn",
    "tool_calls": "tool_use",
    "length": "max_tokens",
    "content_filter": "refusal",
}


class OpenAILLM:
    """OpenAI 兼容端点的适配器。

    官方端点直接用 ``openai_api_key``；接第三方中转站时再配 ``openai_base_url``。
    """

    def __init__(
        self,
        *,
        model: str,
        max_tokens: int = 16000,
        enable_prompt_cache: bool = True,
        # 官方端点用 max_completion_tokens；部分第三方中转站只认已废弃的 max_tokens
        legacy_max_tokens: bool = False,
        client: openai.AsyncOpenAI | None = None,
    ) -> None:
        self.model = model
        self.max_tokens = max_tokens
        self.enable_prompt_cache = enable_prompt_cache
        self.legacy_max_tokens = legacy_max_tokens
        self.client = client or openai.AsyncOpenAI()

    @trace_span(kind="llm", name="openai.stream")
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
            "messages": _to_openai_messages(messages, system),
            "stream": True,
            # 不显式要 usage 的话，流式响应里根本没有 token 数
            "stream_options": {"include_usage": True},
        }
        if self.legacy_max_tokens:
            params["max_tokens"] = self.max_tokens
        else:
            params["max_completion_tokens"] = self.max_tokens

        stream = TextStream()
        finish_reason = ""
        usage = Usage()

        active = None
        try:
            active = await self.client.chat.completions.create(**params)
        except openai.BadRequestError:
            # 不是所有第三方端点都认 stream_options，去掉重试一次。
            # 代价是这条流拿不到 token 数，trace 里会是 0。
            params.pop("stream_options", None)
            active = await self.client.chat.completions.create(**params)
            logger.warning("%s 的端点不支持 stream_options，本次流式没有 token 统计", self.model)

        async with active as chunks:
            async for chunk in chunks:
                if not chunk.choices:
                    # 最后一个只带 usage 的分片
                    if chunk.usage:
                        usage = _usage_from_openai(chunk.usage)
                    continue
                choice = chunk.choices[0]
                if choice.finish_reason:
                    finish_reason = choice.finish_reason
                delta = choice.delta.content
                if delta:
                    await stream.push(delta)
                    yield delta
                if chunk.usage:
                    usage = _usage_from_openai(chunk.usage)

        stream.finish(
            model=self.model,
            stop_reason=_FINISH_REASONS.get(finish_reason, "other"),
            usage=usage,
        )
        record_llm_usage(
            model=stream.model,
            # prompt_tokens 已含缓存命中的部分，这里不能重复加
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            prompt_version=prompt_version,
        )

    @trace_span(kind="llm", name="openai.chat")
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
            "messages": _to_openai_messages(messages, system),
            (
                "max_tokens" if self.legacy_max_tokens else "max_completion_tokens"
            ): self.max_tokens,
        }
        if tools:
            params["tools"] = [_to_openai_tool(t) for t in tools]
            params["tool_choice"] = tool_choice
        if self.enable_prompt_cache and system:
            # OpenAI 的缓存是自动的，这个字段只用来提高缓存命中的路由稳定性
            params["prompt_cache_key"] = hashlib.sha256(system.encode()).hexdigest()[:32]

        try:
            response = await self.client.chat.completions.create(**params)
        except openai.AuthenticationError as e:
            raise LLMAuthenticationError("OpenAI 凭证无效") from e
        except openai.RateLimitError as e:
            raise LLMRateLimitError("OpenAI 限流") from e
        except openai.APIConnectionError as e:
            raise LLMUpstreamError("无法连接 OpenAI API") from e
        except openai.APIStatusError as e:
            raise LLMUpstreamError(f"OpenAI API 错误：{e}") from e

        result = _from_openai_response(response)
        record_llm_usage(
            model=result.model,
            # prompt_tokens 已经包含缓存命中的 token，不能再叠加 cache_read
            input_tokens=result.usage.input_tokens,
            output_tokens=result.usage.output_tokens,
            prompt_version=prompt_version,
        )
        return result


def _to_openai_messages(messages: list[Message], system: str | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if system:
        out.append({"role": "system", "content": system})

    for message in messages:
        match message:
            case UserMessage(content=content):
                out.append({"role": "user", "content": content})
            # 不解构 provider_content：它是 Anthropic 的原始内容块，在 OpenAI 侧必须忽略
            case AssistantMessage(text=text, tool_calls=calls):
                entry: dict[str, Any] = {"role": "assistant", "content": text or None}
                if calls:
                    entry["tool_calls"] = [
                        {
                            "id": c.id,
                            "type": "function",
                            "function": {
                                "name": c.name,
                                "arguments": json.dumps(c.arguments, ensure_ascii=False),
                            },
                        }
                        for c in calls
                    ]
                out.append(entry)
            case ToolResultsMessage(results=results, note=note):
                # OpenAI 要求每个工具结果一条独立消息，且必须紧跟在对应的 assistant 消息后面
                out.extend(
                    {"role": "tool", "tool_call_id": r.tool_call_id, "content": r.content}
                    for r in results
                )
                if note:
                    # 附言不能塞进 tool 消息（那会被算成该工具的输出），单独起一条 user 消息
                    out.append({"role": "user", "content": note})
    return out


def _usage_from_openai(raw: Any) -> Usage:
    """OpenAI 的 usage 口径：prompt_tokens 已包含缓存命中的部分。"""
    cached = 0
    details = getattr(raw, "prompt_tokens_details", None)
    if details is not None:
        cached = getattr(details, "cached_tokens", None) or 0
    return Usage(
        input_tokens=raw.prompt_tokens,
        output_tokens=raw.completion_tokens,
        cache_read_tokens=cached,
    )


def _to_openai_tool(tool: ToolSpec) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.input_schema,
        },
    }


def _parse_arguments(raw: str | None) -> dict[str, Any]:
    """工具参数是 JSON 字符串。

    模型偶尔会给出非法 JSON，这里返回空 dict，让工具注册中心报出「参数校验失败」，
    模型在下一轮自行修正——比直接抛异常中断循环更符合 agent 的错误自修正设计。
    """
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("工具参数不是合法 JSON，已按空参数处理")
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _from_openai_response(response: Any) -> LLMResponse:
    if not response.choices:
        raise LLMUpstreamError("OpenAI 返回了空的 choices")

    choice = response.choices[0]
    message = choice.message
    tool_calls = [
        ToolCall(
            id=tc.id,
            name=tc.function.name,
            arguments=_parse_arguments(tc.function.arguments),
        )
        for tc in (message.tool_calls or [])
    ]

    raw_usage = response.usage
    usage = _usage_from_openai(raw_usage)

    return LLMResponse(
        message=AssistantMessage(text=message.content or "", tool_calls=tool_calls),
        stop_reason=_FINISH_REASONS.get(choice.finish_reason or "", "other"),
        usage=usage,
        model=response.model,
    )
