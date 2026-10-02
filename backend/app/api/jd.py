"""JD 解析接口。

只做三件事：校验入参 → 调用例 → 返回。业务逻辑和 trace 都在 service 层。
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.agents.jd_parser import JDParseError
from app.api.errors import http_error_for_llm
from app.deps import LLMDep
from app.llm.errors import LLMError
from app.schemas.jd import JDAnalysis
from app.services.jd_service import parse_jd_text

router = APIRouter(prefix="/api/jd", tags=["jd"])


class ParseJDRequest(BaseModel):
    jd_text: str = Field(min_length=10, max_length=20000, description="职位描述原文")
    user_id: str | None = None


class ParseJDResponse(JDAnalysis):
    """直接继承领域模型，不手写字段映射。

    继承而不是复制，是为了让 JDAnalysis 改了这里自动跟着变。
    注意给 ``tools.submit()`` 的仍然是 JDAnalysis 本体——否则模型会被要求
    填 attempts/trace_id 这些它根本不知道的字段。
    """

    attempts: int = Field(description="为了拿到结构化结果用了几次尝试")
    input_tokens: int
    output_tokens: int
    trace_id: str


@router.post("/parse", response_model=ParseJDResponse)
async def parse_jd_endpoint(body: ParseJDRequest, llm: LLMDep) -> ParseJDResponse:
    try:
        outcome = await parse_jd_text(llm, body.jd_text, user_id=body.user_id)
    except LLMError as e:
        raise http_error_for_llm(e) from e
    except JDParseError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e

    return ParseJDResponse(
        **outcome.analysis.model_dump(),
        attempts=outcome.attempts,
        input_tokens=outcome.usage.input_tokens,
        output_tokens=outcome.usage.output_tokens,
        trace_id=outcome.trace_id,
    )
