import asyncio

import pytest

from app.agents.loop import FORCE_FINAL_NOTE, AgentConfig, run_agent
from app.llm.base import AssistantMessage, ToolCall, ToolResultsMessage, UserMessage
from app.tools.registry import ToolError, ToolRegistry
from tests.fakes import ScriptedLLM, reply


@pytest.fixture
def tools():
    registry = ToolRegistry()

    @registry.tool()
    async def add(a: int, b: int) -> int:
        """两数相加。"""
        return a + b

    @registry.tool()
    async def fail(reason: str) -> str:
        """总是失败。"""
        raise ToolError(f"失败：{reason}")

    @registry.tool()
    async def crash() -> str:
        """抛出未预期的异常。"""
        raise RuntimeError("bug")

    @registry.tool()
    async def slow() -> str:
        """很慢。"""
        await asyncio.sleep(10)
        return "done"

    @registry.tool()
    async def big() -> str:
        """返回超长结果。"""
        return "x" * 100

    return registry


def call(name: str, id: str = "c1", **arguments) -> ToolCall:
    return ToolCall(id=id, name=name, arguments=arguments)


async def test_answers_directly_without_tools(tools, trace_sink):
    llm = ScriptedLLM([reply("你好")])
    result = await run_agent(llm, [UserMessage("hi")], tools=tools)

    assert result.text == "你好"
    assert result.stop_reason == "completed"
    assert result.steps == 1
    assert len(llm.calls) == 1
    assert {t.name for t in llm.calls[0]["tools"]} == {"add", "fail", "crash", "slow", "big"}


async def test_tool_call_result_is_fed_back(tools, trace_sink):
    llm = ScriptedLLM([reply(tool_calls=[call("add", a=1, b=2)]), reply("结果是 3")])
    result = await run_agent(llm, [UserMessage("1+2=?")], tools=tools, system="sys")

    assert result.text == "结果是 3"
    assert result.steps == 2
    assert llm.calls[1]["system"] == "sys"

    _, assistant, tool_results = llm.calls[1]["messages"]
    assert isinstance(assistant, AssistantMessage)
    assert isinstance(tool_results, ToolResultsMessage)
    assert tool_results.results[0].tool_call_id == "c1"
    assert tool_results.results[0].content == "3"
    assert tool_results.results[0].is_error is False
    # 历史是只追加的：最终消息列表 = 输入 + 每次模型回复 + 每轮工具结果
    assert len(result.messages) == 4


async def test_parallel_tool_calls_return_in_one_message(tools, trace_sink):
    llm = ScriptedLLM(
        [
            reply(tool_calls=[call("add", "c1", a=1, b=1), call("add", "c2", a=2, b=2)]),
            reply("完成"),
        ]
    )
    await run_agent(llm, [UserMessage("算两个")], tools=tools)

    tool_results = llm.calls[1]["messages"][-1]
    assert [(r.tool_call_id, r.content) for r in tool_results.results] == [("c1", "2"), ("c2", "4")]


@pytest.mark.parametrize(
    ("tool_call", "expected"),
    [
        (call("fail", reason="没数据"), "失败：没数据"),
        (call("crash"), "RuntimeError: bug"),
        (call("add", a="不是数字", b=1), "参数校验失败"),
        (call("nonexistent"), "不存在名为 nonexistent 的工具"),
    ],
)
async def test_tool_errors_are_returned_to_model(tools, trace_sink, tool_call, expected):
    llm = ScriptedLLM([reply(tool_calls=[tool_call]), reply("我换个方法")])
    result = await run_agent(llm, [UserMessage("试试")], tools=tools)

    assert result.stop_reason == "completed"
    [error] = llm.calls[1]["messages"][-1].results
    assert error.is_error is True
    assert expected in error.content


async def test_tool_timeout(tools, trace_sink):
    llm = ScriptedLLM([reply(tool_calls=[call("slow")]), reply("超时了")])
    await run_agent(llm, [UserMessage("慢")], tools=tools, config=AgentConfig(tool_timeout_s=0.05))

    [error] = llm.calls[1]["messages"][-1].results
    assert error.is_error is True
    assert "超时" in error.content


async def test_long_tool_results_are_truncated(tools, trace_sink):
    llm = ScriptedLLM([reply(tool_calls=[call("big")]), reply("ok")])
    await run_agent(
        llm, [UserMessage("大")], tools=tools, config=AgentConfig(max_tool_result_chars=10)
    )

    [result] = llm.calls[1]["messages"][-1].results
    assert result.content.startswith("x" * 10 + "\n")
    assert "已截断" in result.content


async def test_max_steps_forces_final_answer(tools, trace_sink):
    looping = [reply(tool_calls=[call("add", f"c{i}", a=i, b=i)]) for i in range(3)]
    llm = ScriptedLLM([*looping, reply("被迫收尾")])
    result = await run_agent(
        llm, [UserMessage("一直算")], tools=tools, config=AgentConfig(max_steps=3)
    )

    assert result.stop_reason == "max_steps"
    assert result.text == "被迫收尾"
    assert len(llm.calls) == 4
    final_call = llm.calls[-1]
    assert final_call["tool_choice"] == "none"
    assert final_call["messages"][-1].note == FORCE_FINAL_NOTE
    # 只有最后一轮工具结果带收尾提示
    assert llm.calls[2]["messages"][-1].note is None


async def test_refusal_stops_the_loop(tools, trace_sink):
    llm = ScriptedLLM([reply("", stop_reason="refusal")])
    result = await run_agent(llm, [UserMessage("...")], tools=tools)
    assert result.stop_reason == "refusal"


async def test_truncated_tool_call_is_not_executed(tools, trace_sink):
    llm = ScriptedLLM([reply(tool_calls=[call("crash")], stop_reason="max_tokens")])
    result = await run_agent(llm, [UserMessage("...")], tools=tools)
    assert result.stop_reason == "max_tokens"
    assert len(llm.calls) == 1


async def test_usage_and_cost_are_accumulated(tools, trace_sink):
    llm = ScriptedLLM([reply(tool_calls=[call("add", a=1, b=1)]), reply("2")])
    result = await run_agent(llm, [UserMessage("1+1")], tools=tools)
    assert result.usage.input_tokens == 20
    assert result.usage.output_tokens == 10
    assert result.cost == pytest.approx(0.002)


async def test_trace_tree_shape(tools, flush):
    llm = ScriptedLLM(
        [
            reply(tool_calls=[call("add", "c1", a=1, b=1), call("fail", "c2", reason="x")]),
            reply("ok"),
        ]
    )
    await run_agent(llm, [UserMessage("1+1")], tools=tools, name="test_agent")

    [trace] = await flush()
    agent_span = trace.spans[0]
    assert (agent_span.kind, agent_span.name) == ("agent", "test_agent")
    assert agent_span.attributes == {"stop_reason": "completed", "steps": 2}

    children = [s for s in trace.spans if s.parent_span_id == agent_span.id]
    assert sorted((s.kind, s.name) for s in children) == [
        ("llm", "fake.chat"),
        ("llm", "fake.chat"),
        ("tool", "add"),
        ("tool", "fail"),
    ]
    fail_span = next(s for s in children if s.name == "fail")
    assert fail_span.error == "ToolError: 失败：x"
    assert trace.total_tokens == 30
