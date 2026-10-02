import asyncio
import json
from dataclasses import dataclass, field
from typing import Any, Literal

from app.agents.prompts import version_of
from app.llm.base import (
    LLMClient,
    Message,
    ToolCall,
    ToolResult,
    ToolResultsMessage,
    Usage,
)
from app.tools.registry import ToolError, ToolRegistry
from app.tracing import tracer

AgentStopReason = Literal["completed", "max_steps", "max_tokens", "refusal"]

FORCE_FINAL_NOTE = "已达到工具调用步数上限。请不要再调用工具，基于目前已有的信息直接给出最终答复。"


@dataclass
class AgentResult:
    text: str
    stop_reason: AgentStopReason
    steps: int
    messages: list[Message]
    usage: Usage = field(default_factory=Usage)
    cost: float = 0.0


@dataclass
class AgentConfig:
    max_steps: int = 8
    tool_timeout_s: float = 15.0
    max_tool_result_chars: int = 8000


async def run_agent(
    llm: LLMClient,
    messages: list[Message],
    *,
    system: str | None = None,
    tools: ToolRegistry | None = None,
    config: AgentConfig | None = None,
    name: str = "agent",
    prompt_version: str | None = None,
) -> AgentResult:
    """手写的 agent loop：调用模型 → 执行工具 → 回填结果，直到模型给出最终答复。

    - 整次运行是一个 agent span，其中的 LLM 调用和工具调用都挂在它下面
    - 同一轮的多个工具调用并发执行，结果放在同一条消息里回传
    - 工具出错不会中断循环，错误信息作为 is_error 结果交给模型自行修正
    - 达到步数上限后，禁止调用工具，强制模型收尾
    """
    config = config or AgentConfig()
    history = list(messages)
    tool_specs = tools.specs if tools else None
    total_usage = Usage()
    total_cost = 0.0
    # 版本号默认由 system 提示的内容算出，不让调用方手写：
    # 手写的版本号改 prompt 时很容易忘改，后面的前后对比就悄悄失效了
    effective_version = prompt_version or (version_of(system) if system else None)

    async with tracer.span("agent", name, input={"system": system, "messages": messages}) as span:
        span.prompt_version = effective_version

        async def call_llm(tool_choice: Literal["auto", "none"] = "auto"):
            nonlocal total_cost
            response = await llm.chat(
                history,
                system=system,
                tools=tool_specs,
                tool_choice=tool_choice,
                prompt_version=effective_version,
            )
            _add_usage(total_usage, response.usage)
            total_cost += response.cost
            history.append(response.message)
            return response

        def finish(text: str, stop_reason: AgentStopReason, steps: int) -> AgentResult:
            span.output = {"text": text, "stop_reason": stop_reason, "steps": steps}
            span.attributes.update(stop_reason=stop_reason, steps=steps)
            return AgentResult(
                text=text,
                stop_reason=stop_reason,
                steps=steps,
                messages=history,
                usage=total_usage,
                cost=total_cost,
            )

        for step in range(1, config.max_steps + 1):
            response = await call_llm()

            if response.stop_reason == "refusal":
                return finish(response.message.text, "refusal", step)
            if not response.message.tool_calls:
                stop = "max_tokens" if response.stop_reason == "max_tokens" else "completed"
                return finish(response.message.text, stop, step)
            if response.stop_reason == "max_tokens":
                # 输出被截断时，工具参数可能不完整，不能执行
                return finish(response.message.text, "max_tokens", step)

            results = await asyncio.gather(
                *(_run_tool(tools, call, config) for call in response.message.tool_calls)
            )
            is_last_step = step == config.max_steps
            history.append(
                ToolResultsMessage(
                    results=list(results), note=FORCE_FINAL_NOTE if is_last_step else None
                )
            )

        response = await call_llm(tool_choice="none")
        return finish(response.message.text, "max_steps", config.max_steps)


async def _run_tool(tools: ToolRegistry | None, call: ToolCall, config: AgentConfig) -> ToolResult:
    if tools is None:
        return ToolResult(call.id, f"当前没有可用工具，无法调用 {call.name}。", is_error=True)
    try:
        output = await asyncio.wait_for(
            tools.execute(call.name, call.arguments), timeout=config.tool_timeout_s
        )
    except TimeoutError:
        return ToolResult(
            call.id, f"工具 {call.name} 执行超时（{config.tool_timeout_s}s）。", is_error=True
        )
    except ToolError as e:
        return ToolResult(call.id, str(e), is_error=True)
    except Exception as e:
        return ToolResult(
            call.id, f"工具 {call.name} 执行出错：{type(e).__name__}: {e}", is_error=True
        )
    return ToolResult(call.id, _truncate(_to_text(output), config.max_tool_result_chars))


def _to_text(output: Any) -> str:
    if isinstance(output, str):
        return output
    return json.dumps(tracer.serialize(output), ensure_ascii=False)


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return f"{text[:max_chars]}\n……（结果过长，已截断，原长度 {len(text)} 字符）"


def _add_usage(total: Usage, usage: Usage) -> None:
    total.input_tokens += usage.input_tokens
    total.output_tokens += usage.output_tokens
    total.cache_read_tokens += usage.cache_read_tokens
    total.cache_write_tokens += usage.cache_write_tokens
