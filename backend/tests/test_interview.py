"""模拟面试。

最重要的一组测试在 :class:`TestEvaluationDrivesNextQuestion`：
**评估结果必须真的改变下一题**。如果它只是打个分然后被扔掉，三个 agent
就只是三次 LLM 调用，拆开没有意义。
"""

import uuid

import pytest

from app.agents.evaluator import SUBMIT_TOOL as EVAL_SUBMIT
from app.agents.evaluator import EvaluationError, evaluate_turn
from app.agents.interviewer import InterviewError, ask_question
from app.agents.planner import SUBMIT_TOOL as PLAN_SUBMIT
from app.agents.planner import PlanError, plan_interview
from app.db.models import InterviewTurnRecord
from app.llm.base import ToolCall
from app.schemas.interview import InterviewPlan, PlanTopic, TurnEvaluation
from app.schemas.jd import JDAnalysis
from app.services.interview_service import MAX_TURNS, _next_turn
from tests.fakes import ScriptedLLM, reply

JD = JDAnalysis(
    seniority="中级",
    seniority_reason="要求 3 年以上经验",
    skills_required=["Python", "PostgreSQL"],
    keywords=["Python", "PostgreSQL", "Redis"],
)

PLAN = InterviewPlan(
    topics=[
        PlanTopic(topic="Redis 持久化", difficulty="进阶", source="jd", why="JD 要求 Redis"),
        PlanTopic(topic="Python 异步", difficulty="基础", source="jd", why="主要技术栈是 Python"),
        PlanTopic(
            topic="PostgreSQL 索引", difficulty="进阶", source="jd", why="JD 要求 PostgreSQL"
        ),
    ],
    focus_points=["后端基础"],
    opening="你好，我们开始吧。",
)

EVAL_FOLLOW_UP = TurnEvaluation(
    technical_depth=3,
    clarity=4,
    evidence=2,
    relevance=5,
    summary="答到了 RDB 但没提 AOF",
    next_action="follow_up",
    follow_up_reason="只讲了 RDB 没提 AOF，要追问两种方式的取舍",
)
EVAL_SWITCH = TurnEvaluation(
    technical_depth=4,
    clarity=4,
    evidence=4,
    relevance=5,
    summary="Redis 这块答得不错",
    next_action="switch_topic",
    follow_up_reason="这个点已经问够了，换到 Python 异步",
)

TOPIC_A = PLAN.topics[0]
TOPIC_B = PLAN.topics[1]


def _turn(index: int, topic: str, question: str = "上一个问题", answer: str = "上一个回答"):
    return InterviewTurnRecord(
        session_id=uuid.uuid4(),
        turn_index=index,
        question=question,
        answer=answer,
        topic=topic,
    )


def _plan_reply():
    return reply(
        tool_calls=[
            ToolCall(
                "p1",
                PLAN_SUBMIT,
                {
                    "topics": [
                        {
                            "topic": "Redis 持久化",
                            "difficulty": "进阶",
                            "source": "jd",
                            "why": "JD 要求熟悉 Redis",
                        },
                        {
                            "topic": "Python 异步",
                            "difficulty": "基础",
                            "source": "jd",
                            "why": "主要技术栈是 Python",
                        },
                        {
                            "topic": "PostgreSQL 索引",
                            "difficulty": "进阶",
                            "source": "jd",
                            "why": "JD 要求 PostgreSQL",
                        },
                    ],
                    "focus_points": ["后端基础"],
                    "opening": "你好，我们开始吧。",
                },
            )
        ]
    )


def _eval_reply(action: str, reason: str):
    return reply(
        tool_calls=[
            ToolCall(
                "e1",
                EVAL_SUBMIT,
                {
                    "technical_depth": 3,
                    "clarity": 4,
                    "evidence": 2,
                    "relevance": 5,
                    "summary": "还行",
                    "next_action": action,
                    "follow_up_reason": reason,
                },
            )
        ]
    )


# ---------- 规划 Agent ----------


async def test_planner_submits_structured_plan(flush):
    llm = ScriptedLLM([_plan_reply(), reply(text="大纲已生成")])

    result = await plan_interview(llm, JD)

    assert result.attempts == 1
    assert [t.topic for t in result.plan.topics] == [
        "Redis 持久化",
        "Python 异步",
        "PostgreSQL 索引",
    ]
    assert result.plan.focus_points == ["后端基础"]


async def test_planner_retries_when_model_does_not_call_tool():
    llm = ScriptedLLM([reply(text="我用文字写吧"), _plan_reply(), reply(text="好了")])

    result = await plan_interview(llm, JD)

    assert result.attempts == 2
    assert result.plan.opening


async def test_planner_raises_after_exhausting_attempts():
    llm = ScriptedLLM([reply(text="不用工具"), reply(text="还是不用")])

    with pytest.raises(PlanError):
        await plan_interview(llm, JD)


async def test_planner_rejects_a_plan_that_is_too_short():
    """schema 层就拦住太短的大纲，错误回给模型让它自己补。"""
    bad = {
        "topics": [{"topic": "只有一个", "difficulty": "基础", "source": "jd", "why": "凑数"}],
        "focus_points": [],
        "opening": "开始",
    }
    llm = ScriptedLLM(
        [reply(tool_calls=[ToolCall("p1", PLAN_SUBMIT, bad)]), _plan_reply(), reply(text="好了")]
    )

    result = await plan_interview(llm, JD)

    assert len(result.plan.topics) == 3
    # 第一次被 schema 拒绝，模型重试后才通过
    assert "at least 3" in str(llm.calls[1]["messages"])


# ---------- 评估 Agent ----------


async def test_evaluator_scores_each_dimension(flush):
    llm = ScriptedLLM([_eval_reply("follow_up", "只讲了 RDB"), reply(text="已提交")])

    result = await evaluate_turn(llm, TOPIC_A, "问 Redis 持久化怎么做？", "用 RDB 就行")

    assert result.attempts == 1
    ev = result.evaluation
    assert (ev.technical_depth, ev.clarity, ev.evidence, ev.relevance) == (3, 4, 2, 5)
    assert ev.next_action == "follow_up"
    assert ev.follow_up_reason == "只讲了 RDB"


async def test_evaluator_rejects_out_of_range_scores():
    bad = {
        "technical_depth": 9,  # 超过 5
        "clarity": 3,
        "evidence": 3,
        "relevance": 3,
        "summary": "还行",
        "next_action": "follow_up",
        "follow_up_reason": "再问",
    }
    llm = ScriptedLLM(
        [
            reply(tool_calls=[ToolCall("e1", EVAL_SUBMIT, bad)]),
            _eval_reply("follow_up", "修正"),
            reply(text="好"),
        ]
    )

    result = await evaluate_turn(llm, TOPIC_A, "q", "a")

    assert result.evaluation.technical_depth == 3
    # 错误信息回传给了模型，它第二轮才改对
    second_call = llm.calls[1]["messages"]
    assert any(getattr(m, "results", None) for m in second_call)


async def test_evaluator_raises_after_exhausting_attempts():
    llm = ScriptedLLM([reply(text="不给结构化结果"), reply(text="还是不给")])

    with pytest.raises(EvaluationError):
        await evaluate_turn(llm, TOPIC_A, "q", "a")


# ---------- 面试官 Agent ----------


async def test_interviewer_asks_one_question():
    llm = ScriptedLLM([reply(text="Redis 有哪两种持久化方式？分别适合什么场景？")])

    question = await ask_question(llm, PLAN, TOPIC_A, turn_index=0, history=[])

    assert "持久化" in question.text
    assert not question.text.startswith("【")


async def test_interviewer_raises_on_empty_output():
    llm = ScriptedLLM([reply(text="   ")])

    with pytest.raises(InterviewError):
        await ask_question(llm, PLAN, TOPIC_A, turn_index=0, history=[])


# ---------- 验收标准：评估结果真的改变下一题 ----------


class TestEvaluationDrivesNextQuestion:
    async def test_follow_up_stays_on_same_topic(self):
        llm = ScriptedLLM([reply(text="那 AOF 呢？")])

        nxt = await _next_turn(llm, PLAN, [_turn(0, "Redis 持久化")], EVAL_FOLLOW_UP)

        assert nxt.view is not None
        assert nxt.view.topic == "Redis 持久化"

    async def test_switch_topic_moves_to_next(self):
        llm = ScriptedLLM([reply(text="说说 Python 的事件循环。")])

        nxt = await _next_turn(llm, PLAN, [_turn(0, "Redis 持久化")], EVAL_SWITCH)

        assert nxt.view is not None
        assert nxt.view.topic == "Python 异步"
        assert nxt.view.turn_index == 1

    async def test_different_evaluations_produce_different_prompts(self):
        """同一条历史，只因为评估不同，面试官收到的东西就不同。"""
        turn = [_turn(0, "Redis 持久化", question="Redis 怎么做持久化？", answer="用 RDB")]

        follow_llm = ScriptedLLM([reply(text="那 AOF 呢？")])
        switch_llm = ScriptedLLM([reply(text="说说事件循环。")])

        await _next_turn(follow_llm, PLAN, turn, EVAL_FOLLOW_UP)
        await _next_turn(switch_llm, PLAN, turn, EVAL_SWITCH)

        follow_prompt = str(follow_llm.calls[-1]["messages"][-1].content)
        switch_prompt = str(switch_llm.calls[-1]["messages"][-1].content)

        # 评估里写的理由被原样传给了面试官
        assert "只讲了 RDB 没提 AOF" in follow_prompt
        assert "这个点已经问够了" in switch_prompt
        # 建议动作不同，传下去的行为指令也不同
        assert "继续追问" in follow_prompt
        assert "换个考察点" in switch_prompt
        assert follow_prompt != switch_prompt

    async def test_interviewer_sees_full_history(self):
        turns = [
            _turn(0, "Redis 持久化", question="Redis 怎么做持久化？", answer="用 RDB"),
            _turn(1, "Redis 持久化", question="那 AOF 呢？", answer="记命令日志"),
        ]
        llm = ScriptedLLM([reply(text="两者的取舍是什么？")])

        await _next_turn(llm, PLAN, turns, EVAL_FOLLOW_UP)

        history = llm.calls[-1]["messages"]
        # 历史是从已存轮次重建的，不额外维护一份：Q/A 交替
        assert [type(m).__name__ for m in history[:4]] == [
            "UserMessage",
            "AssistantMessage",
            "UserMessage",
            "AssistantMessage",
        ]
        assert "Redis 怎么做持久化？" in str(history[0].content)
        assert "记命令日志" in str(history[3].text)

    async def test_finishes_when_topics_exhausted(self):
        llm = ScriptedLLM([])
        last = _turn(2, "PostgreSQL 索引")

        nxt = await _next_turn(llm, PLAN, [last], EVAL_SWITCH)

        assert nxt.finished is True
        assert nxt.view is None
        assert llm.calls == []  # 结束时不浪费一次模型调用

    async def test_keeps_asking_while_answers_are_getting_better(self):
        """没有连续同建议到上限时，follow_up 应该留在当前点继续深挖。"""
        llm = ScriptedLLM([reply(text="再深挖一层")])
        turns = [_turn(0, "Redis 持久化", answer="答得不错")]
        turns[0].evaluation = EVAL_FOLLOW_UP.model_dump()

        nxt = await _next_turn(llm, PLAN, turns, EVAL_FOLLOW_UP)

        assert nxt.view is not None
        assert nxt.view.topic == "Redis 持久化"

    async def test_finishes_at_max_turns_even_without_switch(self):
        """还没问完所有考察点，但轮次用完了，必须收尾。"""
        llm = ScriptedLLM([])
        turns = [_turn(i, "Redis 持久化") for i in range(MAX_TURNS)]

        nxt = await _next_turn(llm, PLAN, turns, EVAL_FOLLOW_UP)

        assert nxt.finished is True
        assert nxt.view is None

    async def test_moves_on_after_repeated_same_action(self):
        """真实跑出来的坑：候选人一直接受差，评估会一直建议加难度，
        于是死磕一个知识点。连续同建议到上限就必须换题。
        """
        llm = ScriptedLLM([reply(text="换个话题问吧")])
        turns = [
            _turn(0, "Redis 持久化", answer="答得不好"),
            _turn(1, "Redis 持久化", answer="还是答得不好"),
        ]
        # 把前两轮的建议补上，它们都指向"留在当前点"
        for t in turns:
            t.evaluation = EVAL_FOLLOW_UP.model_dump()

        nxt = await _next_turn(llm, PLAN, turns, EVAL_FOLLOW_UP)

        assert nxt.view is not None
        assert nxt.view.topic == "Python 异步"  # 被强制换到下一个考察点

    async def test_evaluation_failure_stops_before_asking(self):
        """评估失败就不该继续出题——不然会产生一题无评估的孤立问题。"""
        llm = ScriptedLLM([reply(text="我不给结构化结果"), reply(text="还是不给")])

        with pytest.raises(EvaluationError):
            await evaluate_turn(llm, TOPIC_A, "q", "a")

        # 只有评估的两次尝试，没有走到面试官
        assert len(llm.calls) == 2
