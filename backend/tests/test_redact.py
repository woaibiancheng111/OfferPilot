"""脱敏和 prompt 版本号。

这两件事的共同点：都是在数据进库/进对比之前把"以后会出事的隐患"堵掉，
一旦线上有了真实数据再改就晚了，所以现在就把行为钉死在测试里。
"""

import pytest

from app.agents.loop import AgentConfig, run_agent
from app.agents.prompts import version_of
from app.llm.base import UserMessage
from app.security.redact import content_hash, redact, redact_text, redact_trace
from app.tracing.span import Span, Trace
from tests.fakes import ScriptedLLM, reply


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("我的手机是13812345678", "[手机号]"),
        ("邮箱 zhang.san+x@example.co.uk 谢谢", "[邮箱]"),
        ("身份证110101199003078515", "[身份证]"),
        ("旧身份证110101900307851", "[身份证]"),
        ("学号2023123456", "[学号]"),
        ("银行卡6222021234567890", "[银行卡]"),
    ],
)
def test_redact_text(raw, expected):
    assert expected in redact_text(raw)


def test_phone_is_not_swallowed_by_student_id_rule():
    """规则按顺序生效，手机号必须先被替掉，否则 11 位数字会先命中学号规则。"""
    assert redact_text("13812345678") == "[手机号]"
    assert redact_text("2023123456") == "[学号]"


def test_non_pii_text_untouched():
    text = "自我介绍：我熟悉 Redis 持久化和 Python 异步编程"
    assert redact_text(text) == text


def test_redact_walks_nested_structures():
    payload = {
        "messages": [{"role": "user", "content": "电话 13812345678"}],
        "meta": {"tags": ["a@b.com", "ok"], "n": 42, "ok": True},
    }
    cleaned = redact(payload)

    assert cleaned["messages"][0]["content"] == "电话 [手机号]"
    assert cleaned["meta"]["tags"] == ["[邮箱]", "ok"]
    # 非字符串字段必须原样保留
    assert cleaned["meta"]["n"] == 42
    assert cleaned["meta"]["ok"] is True


def test_redact_stops_at_max_depth():
    """病态深的嵌套不能把栈打爆，观测系统永远不能因此影响业务。"""
    deep = value = {}
    for _ in range(50):
        value["next"] = {}
        value = value["next"]
    value["leak"] = "13812345678"

    assert redact(deep) is not None


def test_content_hash_is_stable_and_distinguishing():
    assert content_hash("abc") == content_hash("abc")
    assert content_hash("abc") != content_hash("abd")
    assert len(content_hash("abc")) == 8
    # 非字符串也要能算，否则 dict payload 没法留指纹
    assert content_hash({"a": 1, "b": 2}) == content_hash({"b": 2, "a": 1})


def test_redact_trace_marks_span_and_keeps_fingerprint():
    trace = Trace(name="t")
    span = Span(trace_id=trace.id, kind="agent", name="s", input={"content": "邮箱 a@b.com"})
    trace.spans.append(span)

    assert redact_trace(trace) == 1
    assert span.input == {"content": "邮箱 [邮箱]"}
    # 脱敏后内容不可逆，但指纹能证明"这条敏感输入又出现了"
    assert span.attributes["input_hash"] == content_hash({"content": "邮箱 a@b.com"})
    assert span.attributes["redacted"] == ["input"]


def test_redact_trace_returns_zero_when_nothing_to_do():
    trace = Trace(name="t")
    span = Span(trace_id=trace.id, kind="agent", name="s", input={"q": "普通问题"})
    trace.spans.append(span)

    assert redact_trace(trace) == 0
    assert "redacted" not in span.attributes


async def test_trace_reaching_sink_is_redacted(flush):
    """端到端：走完整条链路，落库的 span 里不能有明文。"""
    from app.tracing import tracer

    async with tracer.span("agent", "resume_agent", input={"raw": "手机 13812345678"}) as span:
        span.output = "已解析，联系邮箱 a@b.com"

    [trace] = await flush()
    assert trace.spans[0].input == {"raw": "手机 [手机号]"}
    assert trace.spans[0].output == "已解析，联系邮箱 [邮箱]"


async def test_exporter_counts_redacted_spans(trace_sink):
    from app.tracing import tracer

    async with tracer.span("agent", "a", input={"x": "13812345678"}):
        pass
    async with tracer.span("agent", "b", input={"x": "没有敏感信息"}):
        pass

    await tracer.exporter.flush()

    assert tracer.exporter.redacted_spans == 1


def test_prompt_version_derived_from_content():
    assert version_of("你是助手") == version_of("你是助手")
    assert version_of("你是助手") != version_of("你是助手。")


async def test_run_agent_records_derived_prompt_version(flush):
    from app.tracing import tracer

    llm = ScriptedLLM([reply(text="好的")])
    async with tracer.trace("session"):
        await run_agent(llm, [UserMessage("你好")], system="你是面试官", name="interviewer")

    [trace] = await flush()
    expected = version_of("你是面试官")
    # agent span 和它下面的 llm span 都带版本号
    assert all(span.prompt_version == expected for span in trace.spans)


async def test_prompt_version_changes_when_prompt_changes(flush):
    """改一个字，版本号必须变——否则前后对比会悄悄失效。"""
    from app.tracing import tracer

    versions = []
    for system in ("你是面试官，请提问。", "你是面试官，请追问。"):
        llm = ScriptedLLM([reply(text="ok")])
        async with tracer.trace("session"):
            await run_agent(
                llm, [UserMessage("q")], system=system, name="interviewer",
                config=AgentConfig(),
            )
        versions.append(version_of(system))

    assert versions[0] != versions[1]


async def test_explicit_prompt_version_still_wins(flush):
    from app.tracing import tracer

    llm = ScriptedLLM([reply(text="ok")])
    async with tracer.trace("session"):
        await run_agent(
            llm, [UserMessage("q")], system="你是面试官", name="i", prompt_version="pinned-v3"
        )

    [trace] = await flush()
    assert all(span.prompt_version == "pinned-v3" for span in trace.spans)
