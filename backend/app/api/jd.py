"""JD 解析接口。"""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.agents.jd_parser import JDParseError, parse_jd
from app.api.errors import http_error_for_llm
from app.llm.errors import LLMError
from app.tracing import tracer

router = APIRouter(prefix="/api/jd", tags=["jd"])


class ParseJDRequest(BaseModel):
    jd_text: str = Field(min_length=10, max_length=20000, description="职位描述原文")
    user_id: str | None = None


class ParseJDResponse(BaseModel):
    company: str | None
    role_title: str | None
    seniority: str
    seniority_reason: str
    business_domain: str | None
    skills_required: list[str]
    skills_nice_to_have: list[str]
    responsibilities: list[str]
    keywords: list[str]
    attempts: int = Field(description="为了拿到结构化结果用了几次尝试")
    cost_usd: float
    trace_id: str


@router.post("/parse", response_model=ParseJDResponse)
async def parse_jd_endpoint(body: ParseJDRequest, request: Request) -> ParseJDResponse:
    async with tracer.trace("jd.parse", user_id=body.user_id) as trace:
        try:
            result = await parse_jd(request.app.state.llm, body.jd_text)
        except LLMError as e:
            raise http_error_for_llm(e) from e
        except JDParseError as e:
            raise HTTPException(status_code=502, detail=str(e)) from e

    a = result.analysis
    return ParseJDResponse(
        company=a.company,
        role_title=a.role_title,
        seniority=a.seniority,
        seniority_reason=a.seniority_reason,
        business_domain=a.business_domain,
        skills_required=a.skills_required,
        skills_nice_to_have=a.skills_nice_to_have,
        responsibilities=a.responsibilities,
        keywords=a.keywords,
        attempts=result.attempts,
        cost_usd=result.cost,
        trace_id=trace.id,
    )
