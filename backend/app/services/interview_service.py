"""模拟面试用例。

分层上，编排逻辑全部留在这里：路由只转发，agent 只管各自的 prompt 和 loop。

**这个用例成立的前提是评估结果真的改变了下一题。** 如果评估打完分，面试官
下一轮还是照大纲问，那三个 agent 就只是三次 LLM 调用而已，拆开没有意义。
所以「下一轮问什么」被显式做成用例层里的状态机，而不是藏在 prompt 里。

一次 HTTP 请求 = 一条 trace：
- ``interview.start``：规划 + 第一个问题
- ``interview.turn`` ：评估上一轮 + 出下一题
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.agents.evaluator import evaluate_turn
from app.agents.interviewer import ask_question
from app.agents.planner import plan_interview
from app.db.models import InterviewSessionRecord, InterviewTurnRecord
from app.llm.base import AssistantMessage, LLMClient, Message, Usage, UserMessage
from app.schemas.interview import InterviewPlan, PlanTopic, TurnEvaluation
from app.schemas.jd import JDAnalysis
from app.tracing import tracer

MAX_TURNS = 8
# 连续同一个建议的次数上限。真实跑下来发现：候选人一直接受差，评估会一直
# 建议 increase_difficulty，于是死磕一个知识点不换题。深挖有上限，到点必须换。
MAX_SAME_ACTION = 2

__all__ = [
    "MAX_TURNS",
    "InterviewNotFound",
    "SessionView",
    "TurnView",
    "start_session",
    "submit_answer",
]


class InterviewNotFound(RuntimeError):
    """会话不存在。"""


@dataclass
class TurnView:
    turn_index: int
    question: str
    topic: str
    difficulty: str
    answer: str | None = None
    evaluation: TurnEvaluation | None = None


@dataclass
class SessionView:
    session_id: str
    plan: InterviewPlan
    turns: list[TurnView]
    finished: bool
    trace_id: str
    total_tokens: int


@dataclass
class _NextTurn:
    """下一轮的结果。finished 为 True 时 view 为 None，面试结束。"""

    view: TurnView | None
    tokens: int
    finished: bool


async def start_session(
    llm: LLMClient,
    jd_analysis: JDAnalysis,
    *,
    session_factory: async_sessionmaker[AsyncSession],
    user_id: str,
    resume_text: str | None = None,
) -> SessionView:
    async with tracer.trace("interview.start", user_id=user_id) as trace:
        async with tracer.span("custom", "interview.start") as span:
            planned = await plan_interview(llm, jd_analysis, resume_text=resume_text)
            plan = planned.plan
            span.output = {"plan": plan.model_dump(), "attempts": planned.attempts}

            first = plan.topics[0]
            question = await ask_question(
                llm, plan, first, turn_index=0, history=[], previous_evaluation=None
            )

    tokens = _tokens(planned.usage) + _tokens(question.usage)
    session_id = uuid.uuid4()
    first_view = TurnView(0, question.text, first.topic, first.difficulty)

    async with session_factory() as db, db.begin():
        db.add(
            InterviewSessionRecord(
                id=session_id,
                user_id=user_id,
                jd_analysis=jd_analysis.model_dump(),
                plan=plan.model_dump(),
                status="interviewing",
                trace_id=trace.id,
                total_tokens=tokens,
            )
        )
        db.add(
            InterviewTurnRecord(
                id=uuid.uuid4(),
                session_id=session_id,
                turn_index=0,
                question=question.text,
                answer="",
                topic=first.topic,
                input_tokens=question.usage.input_tokens,
                output_tokens=question.usage.output_tokens,
            )
        )

    return SessionView(
        session_id=str(session_id),
        plan=plan,
        turns=[first_view],
        finished=False,
        trace_id=trace.id,
        total_tokens=tokens,
    )


async def submit_answer(
    llm: LLMClient,
    session_id: str,
    answer: str,
    *,
    session_factory: async_sessionmaker[AsyncSession],
) -> SessionView:
    record = await _load(session_factory, session_id)
    if record.plan is None:
        raise InterviewNotFound("会话没有面试大纲，无法继续")
    plan = InterviewPlan.model_validate(record.plan)
    turns = sorted(record.turns, key=lambda t: t.turn_index)
    if not turns:
        raise InterviewNotFound("会话没有任何轮次")

    async with tracer.trace("interview.turn", user_id=record.user_id) as trace:
        async with tracer.span("custom", "interview.turn") as span:
            current = turns[-1]
            topic = _find_topic(plan, current.topic)
            evaluated = await evaluate_turn(
                llm, topic, current.question, answer, jd_requirements=plan.focus_points or None
            )
            span.output = {
                "turn_index": current.turn_index,
                "evaluation": evaluated.evaluation.model_dump(),
                "attempts": evaluated.attempts,
            }

            nxt = await _next_turn(llm, plan, turns, evaluated.evaluation)

    current.answer = answer
    current.evaluation = evaluated.evaluation.model_dump()
    current.input_tokens = evaluated.usage.input_tokens
    current.output_tokens = evaluated.usage.output_tokens
    new_tokens = _tokens(evaluated.usage) + nxt.tokens

    async with session_factory() as db, db.begin():
        merged = await db.get(InterviewSessionRecord, uuid.UUID(session_id))
        assert merged is not None, "会话在处理期间被删除了"
        for t in turns:
            await db.merge(_snapshot(t))
        if nxt.view is not None:
            db.add(
                InterviewTurnRecord(
                    id=uuid.uuid4(),
                    session_id=uuid.UUID(session_id),
                    turn_index=nxt.view.turn_index,
                    question=nxt.view.question,
                    answer="",
                    topic=nxt.view.topic,
                )
            )
        if nxt.finished:
            merged.status = "finished"
        merged.total_tokens = (merged.total_tokens or 0) + new_tokens

    views = [_to_view(t, plan) for t in turns]
    if nxt.view is not None:
        views.append(nxt.view)

    return SessionView(
        session_id=session_id,
        plan=plan,
        turns=views,
        finished=nxt.finished,
        trace_id=trace.id,
        total_tokens=(record.total_tokens or 0) + new_tokens,
    )


async def _next_turn(
    llm: LLMClient,
    plan: InterviewPlan,
    turns: list[InterviewTurnRecord],
    evaluation: TurnEvaluation,
) -> _NextTurn:
    """决定下一轮问什么。整个多 Agent 设计成立与否就看这里。"""
    used_up = len(turns) >= MAX_TURNS
    index = _topic_index(plan, turns[-1].topic)
    exhausted = used_up or _stuck_on_one_action(turns)

    if evaluation.next_action == "switch_topic" or exhausted:
        if used_up or index + 1 >= len(plan.topics):
            return _NextTurn(view=None, tokens=0, finished=True)
        topic = plan.topics[index + 1]
    else:
        # 追问或加难度：留在当前考察点。follow_up_reason 会传给面试官，
        # 它决定具体怎么问——这一轮的问题因此和上一轮的评估是绑定的。
        topic = plan.topics[index]

    question = await ask_question(
        llm,
        plan,
        topic,
        turn_index=len(turns),
        history=_rebuild_history(turns),
        previous_question=turns[-1].question,
        previous_answer=turns[-1].answer,
        previous_evaluation=evaluation,
    )
    return _NextTurn(
        view=TurnView(
            turn_index=len(turns),
            question=question.text,
            topic=topic.topic,
            difficulty=topic.difficulty,
        ),
        tokens=_tokens(question.usage),
        finished=False,
    )


def _rebuild_history(turns: list[InterviewTurnRecord]) -> list[Message]:
    """从已存的轮次重建对话历史。

    只存 question/answer 单一事实来源，历史每次现算。避免 session 上再多存
    一份可能和 turns 不一致的消息列表。
    """
    history: list[Message] = []
    for t in sorted(turns, key=lambda t: t.turn_index):
        if not t.answer:
            continue
        history.append(UserMessage(t.question))
        history.append(AssistantMessage(text=t.answer))
    return history


def _stuck_on_one_action(turns: list[InterviewTurnRecord]) -> bool:
    """已经连续 MAX_SAME_ACTION 次建议留在当前知识点了，再不换就成死循环了。

    只看最近几轮的建议，且要求它们都指向"留在当前点"（follow_up /
    increase_difficulty）。已经答完的轮次才有评估可看。
    """
    actions: list[str] = []
    for t in sorted(turns, key=lambda t: t.turn_index):
        if not t.evaluation:
            continue
        actions.append(TurnEvaluation.model_validate(t.evaluation).next_action)
    if len(actions) < MAX_SAME_ACTION:
        return False
    recent = actions[-MAX_SAME_ACTION:]
    return all(a in ("follow_up", "increase_difficulty") for a in recent)


def _topic_index(plan: InterviewPlan, topic_name: str | None) -> int:
    for i, t in enumerate(plan.topics):
        if t.topic == topic_name:
            return i
    return 0


def _find_topic(plan: InterviewPlan, topic_name: str | None) -> PlanTopic:
    return plan.topics[_topic_index(plan, topic_name)]


def _to_view(t: InterviewTurnRecord, plan: InterviewPlan) -> TurnView:
    return TurnView(
        turn_index=t.turn_index,
        question=t.question,
        topic=t.topic or "",
        difficulty=_find_topic(plan, t.topic).difficulty,
        answer=t.answer or None,
        evaluation=TurnEvaluation.model_validate(t.evaluation) if t.evaluation else None,
    )


def _tokens(usage: Usage) -> int:
    return usage.input_tokens + usage.output_tokens


def _snapshot(t: InterviewTurnRecord) -> InterviewTurnRecord:
    """把已脱离 session 的对象还原成可 merge 的新实例。"""
    return InterviewTurnRecord(
        id=t.id,
        session_id=t.session_id,
        turn_index=t.turn_index,
        question=t.question,
        answer=t.answer,
        topic=t.topic,
        evaluation=t.evaluation,
        input_tokens=t.input_tokens,
        output_tokens=t.output_tokens,
        created_at=t.created_at,
    )


async def _load(
    session_factory: async_sessionmaker[AsyncSession], session_id: str
) -> InterviewSessionRecord:
    async with session_factory() as db:
        record = await db.scalar(
            select(InterviewSessionRecord)
            .where(InterviewSessionRecord.id == uuid.UUID(session_id))
            .options(selectinload(InterviewSessionRecord.turns))
        )
        if record is None:
            raise InterviewNotFound(f"面试会话 {session_id} 不存在")
        return record
