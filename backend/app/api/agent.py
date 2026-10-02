from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.agents.demo import DEMO_SYSTEM_PROMPT, demo_tools
from app.agents.loop import AgentConfig, run_agent
from app.config import get_settings
from app.llm import (
    LLMAuthenticationError,
    LLMError,
    LLMNotConfiguredError,
    LLMRateLimitError,
    LLMUpstreamError,
    UserMessage,
)
from app.tracing import tracer

router = APIRouter(prefix="/api/agent", tags=["agent"])

# 中立异常 → HTTP 状态码。加新厂商时这里不用改，provider 层已经把异常翻译好了
_STATUS_BY_ERROR: tuple[tuple[type[Exception], int], ...] = (
    (LLMNotConfiguredError, 503),
    (LLMAuthenticationError, 503),
    (LLMRateLimitError, 429),
    (LLMUpstreamError, 502),
)


class DemoRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    user_id: str | None = None


class DemoResponse(BaseModel):
    text: str
    stop_reason: str
    steps: int
    trace_id: str
    cost_usd: float


@router.post("/demo", response_model=DemoResponse)
async def run_demo(body: DemoRequest, request: Request) -> DemoResponse:
    settings = get_settings()
    async with tracer.trace("agent.demo", user_id=body.user_id) as trace:
        try:
            result = await run_agent(
                request.app.state.llm,
                [UserMessage(body.message)],
                system=DEMO_SYSTEM_PROMPT,
                tools=demo_tools,
                config=AgentConfig(
                    max_steps=settings.agent_max_steps,
                    tool_timeout_s=settings.agent_tool_timeout_s,
                    max_tool_result_chars=settings.agent_max_tool_result_chars,
                ),
                name="demo_agent",
            )
        except LLMError as e:
            # provider 层已经把厂商异常翻译成中立异常，这里统一映射成 HTTP 状态码
            status = next((code for exc, code in _STATUS_BY_ERROR if isinstance(e, exc)), 502)
            raise HTTPException(status_code=status, detail=str(e)) from e

    return DemoResponse(
        text=result.text,
        stop_reason=result.stop_reason,
        steps=result.steps,
        trace_id=trace.id,
        cost_usd=result.cost,
    )
