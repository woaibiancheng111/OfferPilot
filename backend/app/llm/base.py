"""与具体模型厂商无关的消息格式。

Agent 层只认这里的类型，各厂商的适配器负责双向转换，
这样切换模型或做模型路由时，Agent 代码不用改。
"""

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

StopReason = Literal["end_turn", "tool_use", "max_tokens", "refusal", "other"]
ToolChoice = Literal["auto", "none"]


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ToolResult:
    tool_call_id: str
    content: str
    is_error: bool = False


@dataclass
class UserMessage:
    content: str


@dataclass
class AssistantMessage:
    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    # 厂商原始内容块。回传给同一厂商时原样使用，保证 thinking 等块不丢失
    provider_content: Any = None


@dataclass
class ToolResultsMessage:
    results: list[ToolResult]
    # 附在工具结果后的额外说明，比如“已达到步数上限，请直接作答”
    note: str | None = None


Message = UserMessage | AssistantMessage | ToolResultsMessage


@dataclass
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass
class Usage:
    """本次调用的 token 用量。

    只统计 token，不折算金额：项目可能接第三方中转，模型名和单价都不在我们控制内，
    维护一张价目表只会持续给出错误的数字。token 数是厂商无关且始终可靠的，
    成本优化靠的是"少用 token"，而不是"算准了多少钱"。
    """

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0


@dataclass
class LLMResponse:
    message: AssistantMessage
    stop_reason: StopReason
    usage: Usage
    model: str


class LLMClient(Protocol):
    async def chat(
        self,
        messages: list[Message],
        *,
        system: str | None = None,
        tools: list[ToolSpec] | None = None,
        tool_choice: ToolChoice = "auto",
        prompt_version: str | None = None,
    ) -> LLMResponse: ...

    def stream_chat(
        self,
        messages: list[Message],
        *,
        system: str | None = None,
        prompt_version: str | None = None,
    ) -> "TextStream":
        """流式出字。

        目前只支持「不带工具、纯文本」这一种情况——面试官的提问就是这种。
        需要工具调用的路径继续走 ``chat``，不硬塞进流式。
        """
        ...


class TextStream:
    """文本流：迭代拿到增量，同时在迭代结束后读到完整文本和用量。

    不用「async generator + return value」是因为拿不到返回值；也不让调用方
    自己拼字符串——那样每个调用点都要重复累加逻辑，容易漏。
    """

    def __init__(self) -> None:
        self._chunks: list[str] = []
        self._text = ""
        self._usage = Usage()
        self._stop_reason: StopReason = "other"
        self._model = ""

    async def push(self, delta: str) -> None:
        """由 provider 在收到增量时调用。"""
        if not delta:
            return
        self._chunks.append(delta)
        self._text += delta

    def finish(self, *, model: str, stop_reason: StopReason, usage: Usage) -> None:
        """流结束时由 provider 调用，补上只在末尾才拿得到的元信息。"""
        self._model = model
        self._stop_reason = stop_reason
        self._usage = usage

    async def __aiter__(self) -> AsyncIterator[str]:
        for chunk in self._chunks:
            yield chunk
            # 让出事件循环，避免一次性吐完把请求饿死
            await asyncio.sleep(0)

    @property
    def text(self) -> str:
        return self._text

    @property
    def usage(self) -> Usage:
        return self._usage

    @property
    def stop_reason(self) -> StopReason:
        return self._stop_reason

    @property
    def model(self) -> str:
        return self._model
