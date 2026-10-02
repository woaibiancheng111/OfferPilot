"""演示 Agent 用例。配置组装和 trace 都在这里，路由不碰。"""

from dataclasses import dataclass

from app.agents.demo import DEMO_SYSTEM_PROMPT, demo_tools
from app.agents.loop import AgentConfig, run_agent
from app.config import Settings
from app.llm.base import LLMClient, Usage, UserMessage
from app.tracing import tracer

__all__ = ["DemoOutcome", "run_demo"]


@dataclass
class DemoOutcome:
    text: str
    stop_reason: str
    steps: int
    usage: Usage
    trace_id: str


async def run_demo(
    llm: LLMClient, message: str, *, settings: Settings, user_id: str | None = None
) -> DemoOutcome:
    async with tracer.trace("agent.demo", user_id=user_id) as trace:
        result = await run_agent(
            llm,
            [UserMessage(message)],
            system=DEMO_SYSTEM_PROMPT,
            tools=demo_tools,
            config=AgentConfig(
                max_steps=settings.agent_max_steps,
                tool_timeout_s=settings.agent_tool_timeout_s,
                max_tool_result_chars=settings.agent_max_tool_result_chars,
            ),
            name="demo_agent",
        )

    return DemoOutcome(
        text=result.text,
        stop_reason=result.stop_reason,
        steps=result.steps,
        usage=result.usage,
        trace_id=trace.id,
    )
