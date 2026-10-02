"""演示 Agent 接口。

用完即弃的脚手架：等正式的求职 Agent 接上来之后整个文件删掉。
留着它是因为它是"接口层有多薄"的样板。
"""

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.api.errors import http_error_for_llm
from app.deps import LLMDep, SettingsDep
from app.llm.errors import LLMError
from app.services.demo_service import run_demo

router = APIRouter(prefix="/api/agent", tags=["agent"])


class DemoRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    user_id: str | None = None


class DemoResponse(BaseModel):
    text: str
    stop_reason: str
    steps: int
    trace_id: str
    input_tokens: int
    output_tokens: int


@router.post("/demo", response_model=DemoResponse)
async def run_demo_endpoint(body: DemoRequest, llm: LLMDep, settings: SettingsDep) -> DemoResponse:
    try:
        outcome = await run_demo(llm, body.message, settings=settings, user_id=body.user_id)
    except LLMError as e:
        # provider 层已经把厂商异常翻译成中立异常，这里只管映射状态码
        raise http_error_for_llm(e) from e

    return DemoResponse(
        text=outcome.text,
        stop_reason=outcome.stop_reason,
        steps=outcome.steps,
        trace_id=outcome.trace_id,
        input_tokens=outcome.usage.input_tokens,
        output_tokens=outcome.usage.output_tokens,
    )
