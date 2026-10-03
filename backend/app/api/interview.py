"""模拟面试接口。

只做三件事：校验入参 → 调用例 → 返回。状态机和三个 agent 的编排在 service 层。
"""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.agents.evaluator import EvaluationError
from app.agents.interviewer import InterviewError
from app.agents.planner import PlanError
from app.api.errors import http_error_for_llm
from app.api.sse import Event, ReplayStore, with_replay
from app.deps import LLMDep, SessionFactoryDep
from app.llm.errors import LLMError
from app.schemas.interview import InterviewPlan, TurnEvaluation
from app.schemas.jd import JDInput
from app.services.interview_service import (
    InterviewNotFound,
    SessionView,
    start_session,
    submit_answer,
    submit_answer_stream,
)

router = APIRouter(prefix="/api/interview", tags=["interview"])


class StartRequest(BaseModel):
    jd: JDInput = Field(
        description="已经解析好的 JD。可以直接把 /api/jd/parse 的响应原样传回来"
    )
    user_id: str = Field(min_length=1, max_length=64)
    resume_text: str | None = Field(
        default=None, max_length=20000, description="简历原文，可选；只进 prompt，不落库"
    )


class AnswerRequest(BaseModel):
    answer: str = Field(min_length=1, max_length=10000)


class TurnOut(BaseModel):
    turn_index: int
    topic: str
    difficulty: str
    question: str
    answer: str | None
    evaluation: TurnEvaluation | None


class SessionOut(BaseModel):
    session_id: str
    plan: InterviewPlan
    turns: list[TurnOut]
    finished: bool
    total_tokens: int
    trace_id: str


def _out(view: SessionView) -> SessionOut:
    return SessionOut(
        session_id=view.session_id,
        plan=view.plan,
        turns=[
            TurnOut(
                turn_index=t.turn_index,
                topic=t.topic,
                difficulty=t.difficulty,
                question=t.question,
                answer=t.answer,
                evaluation=t.evaluation,
            )
            for t in view.turns
        ],
        finished=view.finished,
        total_tokens=view.total_tokens,
        trace_id=view.trace_id,
    )


@router.post("/start", response_model=SessionOut)
async def start(body: StartRequest, llm: LLMDep, sessions: SessionFactoryDep) -> SessionOut:
    try:
        view = await start_session(
            llm,
            body.jd,
            session_factory=sessions,
            user_id=body.user_id,
            resume_text=body.resume_text,
        )
    except (PlanError, EvaluationError, InterviewError) as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    except LLMError as e:
        raise http_error_for_llm(e) from e
    return _out(view)


@router.post("/{session_id}/answer", response_model=SessionOut)
async def answer(
    session_id: str, body: AnswerRequest, llm: LLMDep, sessions: SessionFactoryDep
) -> SessionOut:
    try:
        view = await submit_answer(llm, session_id, body.answer, session_factory=sessions)
    except InterviewNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except (PlanError, EvaluationError, InterviewError) as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    except LLMError as e:
        raise http_error_for_llm(e) from e
    return _out(view)


@router.post("/{session_id}/answer/stream")
async def answer_stream(
    session_id: str,
    body: AnswerRequest,
    llm: LLMDep,
    sessions: SessionFactoryDep,
    last_event_id: Annotated[int, Header(alias="Last-Event-ID")] = 0,
) -> StreamingResponse:
    """流式提交回答。

    断线重连时带 ``Last-Event-ID``，服务端把漏掉的片段补回来再接着推。
    续传缓冲在进程内存里（见 sse.py），接 Redis 只需替换 ReplayStore。
    """
    store = _replay_store_for(session_id)

    async def produce() -> AsyncIterator[Event]:
        try:
            async for raw in submit_answer_stream(
                llm, session_id, body.answer, session_factory=sessions
            ):
                yield store.emit(raw["event"], raw["data"])
        except Exception as exc:  # noqa: BLE001
            # 错误也要以事件形式发出去，否则前端只能干等到超时
            yield store.emit("error", {"message": str(exc)})

    return StreamingResponse(
        with_replay(produce(), store, last_event_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # Nginx 必须放开缓冲，否则流式会被攒成一次性返回
            "X-Accel-Buffering": "no",
        },
    )


# 同一场面试的多次重连共用一个缓冲，按 session 分桶。接 Redis 时换成
# "session_id -> redis key" 的实现即可，上面的 SSE 逻辑一行不用改。
_REPLAY_STORES: dict[str, ReplayStore] = {}


def _replay_store_for(session_id: str) -> ReplayStore:
    return _REPLAY_STORES.setdefault(session_id, ReplayStore())
