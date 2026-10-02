from types import SimpleNamespace

import pytest

from app.llm.anthropic_provider import AnthropicLLM
from app.llm.base import (
    AssistantMessage,
    ToolCall,
    ToolResult,
    ToolResultsMessage,
    ToolSpec,
    Usage,
    UserMessage,
)
from app.llm.pricing import estimate_cost


def fake_response(content, stop_reason="end_turn", model="claude-opus-5", **usage):
    return SimpleNamespace(
        content=content,
        stop_reason=stop_reason,
        model=model,
        usage=SimpleNamespace(
            input_tokens=usage.get("input_tokens", 100),
            output_tokens=usage.get("output_tokens", 50),
            cache_read_input_tokens=usage.get("cache_read", 0),
            cache_creation_input_tokens=usage.get("cache_write", None),
        ),
    )


class FakeMessages:
    def __init__(self, response):
        self.response = response
        self.params = None

    async def create(self, **params):
        self.params = params
        return self.response


def fake_client(response):
    messages = FakeMessages(response)
    beta_messages = FakeMessages(response)
    client = SimpleNamespace(messages=messages, beta=SimpleNamespace(messages=beta_messages))
    return client, messages, beta_messages


def text_block(text):
    return SimpleNamespace(type="text", text=text)


def tool_use_block(id, name, input):
    return SimpleNamespace(type="tool_use", id=id, name=name, input=input)


async def test_builds_request_with_fallbacks_and_cache(trace_sink):
    client, plain, beta = fake_client(fake_response([text_block("hi")]))
    llm = AnthropicLLM(model="claude-opus-5", client=client)

    await llm.chat(
        [UserMessage("你好")],
        system="sys",
        tools=[ToolSpec("add", "相加", {"type": "object", "properties": {}})],
        tool_choice="none",
    )

    assert plain.params is None
    params = beta.params
    assert params["model"] == "claude-opus-5"
    assert params["system"] == "sys"
    assert params["messages"] == [{"role": "user", "content": "你好"}]
    assert params["tools"][0]["name"] == "add"
    assert params["tool_choice"] == {"type": "none"}
    assert params["cache_control"] == {"type": "ephemeral"}
    assert params["betas"] == ["server-side-fallback-2026-07-01"]
    assert params["fallbacks"] == "default"


async def test_plain_endpoint_when_fallbacks_disabled(trace_sink):
    client, plain, beta = fake_client(fake_response([text_block("hi")]))
    llm = AnthropicLLM(
        model="claude-opus-5", client=client, enable_fallbacks=False, enable_prompt_cache=False
    )
    await llm.chat([UserMessage("你好")])

    assert beta.params is None
    assert "fallbacks" not in plain.params
    assert "cache_control" not in plain.params
    assert "tools" not in plain.params


async def test_converts_history(trace_sink):
    client, _, beta = fake_client(fake_response([text_block("ok")]))
    llm = AnthropicLLM(model="claude-opus-5", client=client)
    raw_blocks = [SimpleNamespace(type="thinking"), tool_use_block("t1", "add", {"a": 1})]

    await llm.chat(
        [
            UserMessage("q"),
            AssistantMessage(text="", tool_calls=[], provider_content=raw_blocks),
            ToolResultsMessage(
                results=[ToolResult("t1", "2"), ToolResult("t2", "坏了", is_error=True)],
                note="请收尾",
            ),
            AssistantMessage(text="看看", tool_calls=[ToolCall("t3", "add", {"a": 2})]),
        ]
    )

    _, assistant, tool_results, rebuilt = beta.params["messages"]
    # 原始块（包括 thinking）原样回传
    assert assistant == {"role": "assistant", "content": raw_blocks}
    assert tool_results == {
        "role": "user",
        "content": [
            {"type": "tool_result", "tool_use_id": "t1", "content": "2", "is_error": False},
            {"type": "tool_result", "tool_use_id": "t2", "content": "坏了", "is_error": True},
            {"type": "text", "text": "请收尾"},
        ],
    }
    assert rebuilt["content"] == [
        {"type": "text", "text": "看看"},
        {"type": "tool_use", "id": "t3", "name": "add", "input": {"a": 2}},
    ]


async def test_parses_response_and_records_usage(flush):
    content = [
        SimpleNamespace(type="thinking"),
        text_block("先算一下"),
        tool_use_block("t1", "add", {"a": 1, "b": 2}),
    ]
    client, _, _ = fake_client(
        fake_response(
            content, stop_reason="tool_use", input_tokens=1000, output_tokens=200, cache_read=4000
        )
    )
    llm = AnthropicLLM(model="claude-opus-5", client=client)

    result = await llm.chat([UserMessage("1+2")], prompt_version="v1")

    assert result.stop_reason == "tool_use"
    assert result.message.text == "先算一下"
    assert result.message.tool_calls == [ToolCall("t1", "add", {"a": 1, "b": 2})]
    assert result.message.provider_content is content
    assert result.usage.cache_read_tokens == 4000
    assert result.usage.cache_write_tokens == 0

    [trace] = await flush()
    [span] = trace.spans
    assert (span.kind, span.model, span.prompt_version) == ("llm", "claude-opus-5", "v1")
    assert span.input_tokens == 5000
    assert span.output_tokens == 200
    assert span.cost == pytest.approx(result.cost)


async def test_unknown_stop_reason_maps_to_other(trace_sink):
    client, _, _ = fake_client(fake_response([], stop_reason="pause_turn"))
    result = await AnthropicLLM(model="claude-opus-5", client=client).chat([UserMessage("q")])
    assert result.stop_reason == "other"


def test_estimate_cost():
    usage = Usage(input_tokens=1_000_000, output_tokens=1_000_000, cache_read_tokens=1_000_000)
    # 5 + 25 + 0.5（缓存读 0.1 倍）
    assert estimate_cost("anthropic", "claude-opus-5", usage) == pytest.approx(30.5)
    assert estimate_cost("anthropic", "unknown-model", usage) == 0.0
    # 厂商名写错也应该静默归零，而不是抛异常影响主流程
    assert estimate_cost("openai", "claude-opus-5", usage) == 0.0


async def test_missing_credentials_raise_clear_error(trace_sink, monkeypatch):
    import anthropic

    from app.llm.anthropic_provider import LLMNotConfiguredError

    for var in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_PROFILE"):
        monkeypatch.delenv(var, raising=False)
    llm = AnthropicLLM(model="claude-opus-5", client=anthropic.AsyncAnthropic())
    with pytest.raises(LLMNotConfiguredError):
        await llm.chat([UserMessage("hi")])
