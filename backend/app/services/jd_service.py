"""JD 解析用例。

对外只有一个入口 :func:`parse_jd_text`，负责：
1. 开 trace（一次业务操作 = 一条 trace）
2. 在下面开一个 custom span 承载业务结果（结构化输出、重试次数）
3. 调用 agent 能力
4. 异常在这里收敛成业务异常，路由只管映射状态码
"""

from dataclasses import dataclass

from app.agents.jd_parser import JDParseError, parse_jd
from app.llm.base import LLMClient, Usage
from app.schemas.jd import JDAnalysis
from app.tracing import tracer

__all__ = ["JDParseOutcome", "JDParseError", "parse_jd_text"]


@dataclass
class JDParseOutcome:
    """一次 JD 解析的完整结果。"""

    analysis: JDAnalysis
    attempts: int
    usage: Usage
    trace_id: str


async def parse_jd_text(
    llm: LLMClient, jd_text: str, *, user_id: str | None = None
) -> JDParseOutcome:
    async with tracer.trace("jd.parse", user_id=user_id) as trace:
        async with tracer.span("custom", "jd.parse") as span:
            try:
                result = await parse_jd(llm, jd_text)
            except JDParseError:
                span.attributes.update(parse_failed=True)
                raise

            span.output = {"analysis": result.analysis.model_dump(), "attempts": result.attempts}
            span.attributes.update(attempts=result.attempts, stop_reason=result.stop_reason)

    return JDParseOutcome(
        analysis=result.analysis,
        attempts=result.attempts,
        usage=result.usage,
        trace_id=trace.id,
    )
