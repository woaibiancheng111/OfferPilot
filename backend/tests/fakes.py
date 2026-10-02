import copy

from app.llm.base import (
    AssistantMessage,
    LLMResponse,
    Message,
    StopReason,
    ToolCall,
    ToolChoice,
    ToolSpec,
    Usage,
)
from app.tracing import record_llm_usage, trace_span


def reply(
    text: str = "",
    tool_calls: list[ToolCall] | None = None,
    stop_reason: StopReason | None = None,
    input_tokens: int = 10,
    output_tokens: int = 5,
) -> LLMResponse:
    calls = tool_calls or []
    return LLMResponse(
        message=AssistantMessage(text=text, tool_calls=calls),
        stop_reason=stop_reason or ("tool_use" if calls else "end_turn"),
        usage=Usage(input_tokens=input_tokens, output_tokens=output_tokens),
        model="fake-model",
        cost=0.001,
    )


class ScriptedLLM:
    """按预设脚本依次返回响应，并记录每次调用时看到的参数。"""

    def __init__(self, responses: list[LLMResponse]) -> None:
        self.responses = list(responses)
        self.calls: list[dict] = []

    @trace_span(kind="llm", name="fake.chat")
    async def chat(
        self,
        messages: list[Message],
        *,
        system: str | None = None,
        tools: list[ToolSpec] | None = None,
        tool_choice: ToolChoice = "auto",
        prompt_version: str | None = None,
    ) -> LLMResponse:
        self.calls.append(
            {
                "messages": copy.deepcopy(messages),
                "system": system,
                "tools": tools,
                "tool_choice": tool_choice,
            }
        )
        if not self.responses:
            raise AssertionError("ScriptedLLM 的脚本已用完")
        response = self.responses.pop(0)
        record_llm_usage(
            model=response.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            cost=response.cost,
            prompt_version=prompt_version,
        )
        return response
