"""用例层的行为约定。

这几个测试测的是**分层本身**，不只是功能：trace 开在哪一层、span 挂在谁下面、
agent 会不会自己开 trace。分层一旦回退，这些测试会先挂。
"""

import pytest

from app.agents.jd_parser import JDParseError
from app.llm.base import ToolCall
from app.services.jd_service import parse_jd_text
from tests.fakes import ScriptedLLM, reply
from tests.test_jd_parser import JD_TEXT, SUBMIT_TOOL, VALID_ARGS


async def _succeeding_llm() -> ScriptedLLM:
    return ScriptedLLM(
        [
            reply(tool_calls=[ToolCall("t1", SUBMIT_TOOL, VALID_ARGS)]),
            reply(text="已完成。"),
        ]
    )


async def test_service_owns_the_trace(flush):
    """trace 由用例开，不在 agent 里——这样 CLI 调用同样有 trace。"""
    outcome = await parse_jd_text(await _succeeding_llm(), JD_TEXT)

    [trace] = await flush()
    assert trace.id == outcome.trace_id
    assert trace.name == "jd.parse"


async def test_span_tree_shows_use_case_above_agent(flush):
    """用例 span 在上，agent span 挂它下面，层级一眼能看懂。"""
    await parse_jd_text(await _succeeding_llm(), JD_TEXT)

    [trace] = await flush()
    use_case, agent_span, *rest = trace.spans

    assert (use_case.kind, use_case.name) == ("custom", "jd.parse")
    assert (agent_span.kind, agent_span.name) == ("agent", "jd_parser")
    assert agent_span.parent_span_id == use_case.id
    # llm 和 tool 都挂在 agent 下面，没有跑到用例层
    assert all(s.parent_span_id == agent_span.id for s in rest)
    assert {s.kind for s in rest} == {"llm", "tool"}


async def test_use_case_span_carries_the_business_outcome(flush):
    outcome = await parse_jd_text(await _succeeding_llm(), JD_TEXT)

    [trace] = await flush()
    use_case = trace.spans[0]
    assert use_case.output["analysis"]["seniority"] == outcome.analysis.seniority
    assert use_case.attributes["attempts"] == 1


async def test_failure_is_recorded_on_the_use_case_span(flush):
    llm = ScriptedLLM([reply(text="不用工具"), reply(text="还是不用")])

    with pytest.raises(JDParseError):
        await parse_jd_text(llm, JD_TEXT)

    [trace] = await flush()
    assert trace.status == "error"
    assert trace.spans[0].attributes.get("parse_failed") is True


async def test_agent_spans_nest_under_the_service_trace(flush):
    """agent 本身不显式开 trace。tracer 在没有外层 trace 时会自动建一条
    （这是有意为之：脱离用例单独调 agent 也不该丢数据），但只要用例已经开了
    trace，agent 的 span 就必须挂到它下面，而不是另起一条。
    """
    outcome = await parse_jd_text(await _succeeding_llm(), JD_TEXT)

    [trace] = await flush()
    assert len(trace.spans) > 1, "agent 的 span 应该和用例的 span 在同一条 trace 里"
    assert all(s.trace_id == trace.id for s in trace.spans)
    assert outcome.trace_id == trace.id
