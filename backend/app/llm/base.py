"""与具体模型厂商无关的消息格式。

Agent 层只认这里的类型，各厂商的适配器负责双向转换，
这样切换模型或做模型路由时，Agent 代码不用改。
"""

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
    cost: float = 0.0


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
