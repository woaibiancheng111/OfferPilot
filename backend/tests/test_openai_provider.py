from types import SimpleNamespace

import pytest

from app.llm.base import (
    AssistantMessage,
    ToolCall,
    ToolResult,
    ToolResultsMessage,
    ToolSpec,
    UserMessage,
)
from app.llm.openai_provider import OpenAILLM


def fake_completion(
    content="hi",
    tool_calls=None,
    finish_reason="stop",
    model="gpt-5",
    prompt_tokens=100,
    completion_tokens=50,
    cached_tokens=0,
):
    return SimpleNamespace(
        model=model,
        choices=[
            SimpleNamespace(
                finish_reason=finish_reason,
                message=SimpleNamespace(content=content, tool_calls=tool_calls),
            )
        ],
        usage=SimpleNamespace(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            prompt_tokens_details=SimpleNamespace(cached_tokens=cached_tokens),
        ),
    )


def fake_client(response):
    completions = SimpleNamespace()
    completions.params = None

    async def create(**params):
        completions.params = params
        return response

    completions.create = create
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    return client, completions


def fake_tool_call(id, name, arguments):
    return SimpleNamespace(
        id=id, type="function", function=SimpleNamespace(name=name, arguments=arguments)
    )


async def test_builds_request_with_system_and_tools(trace_sink):
    client, completions = fake_client(fake_completion())
    llm = OpenAILLM(model="gpt-5", client=client, enable_prompt_cache=False)

    await llm.chat(
        [UserMessage("你好")],
        system="sys",
        tools=[ToolSpec("add", "相加", {"type": "object", "properties": {}})],
        tool_choice="none",
    )

    params = completions.params
    assert params["model"] == "gpt-5"
    # system 不是独立参数，而是 messages 的第一条
    assert params["messages"] == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "你好"},
    ]
    assert params["tools"] == [
        {
            "type": "function",
            "function": {
                "name": "add",
                "description": "相加",
                "parameters": {"type": "object", "properties": {}},
            },
        }
    ]
    assert params["tool_choice"] == "none"
    assert "prompt_cache_key" not in params
    # 官方端点用 max_completion_tokens
    assert params["max_completion_tokens"] == 16000
    assert "max_tokens" not in params


async def test_prompt_cache_key_derived_from_system(trace_sink):
    client, completions = fake_client(fake_completion())
    llm = OpenAILLM(model="gpt-5", client=client, enable_prompt_cache=True)

    await llm.chat([UserMessage("q")], system="稳定的系统提示")
    key = completions.params["prompt_cache_key"]
    assert len(key) == 32

    # 同样的 system 应该得到同样的 key，否则缓存永远不命中
    await llm.chat([UserMessage("另一个问题")], system="稳定的系统提示")
    assert completions.params["prompt_cache_key"] == key


async def test_legacy_max_tokens_for_third_party_gateways(trace_sink):
    client, completions = fake_client(fake_completion())
    llm = OpenAILLM(model="gpt-5", client=client, enable_prompt_cache=False, legacy_max_tokens=True)

    await llm.chat([UserMessage("q")], system="s")
    assert completions.params["max_tokens"] == 16000
    assert "max_completion_tokens" not in completions.params


async def test_converts_history_and_ignores_provider_content(trace_sink):
    client, completions = fake_client(fake_completion())
    llm = OpenAILLM(model="gpt-5", client=client, enable_prompt_cache=False)
    # provider_content 是 Anthropic 的原始块，OpenAI 侧必须忽略并重建消息
    raw_blocks = [SimpleNamespace(type="thinking")]

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

    messages = completions.params["messages"]
    # 空文本 + 无工具调用，content 必须是 None 而不是 ""
    assert messages[1] == {"role": "assistant", "content": None}
    # 每个工具结果一条 role=tool，附言单独起一条 user 消息
    assert messages[2] == {"role": "tool", "tool_call_id": "t1", "content": "2"}
    assert messages[3] == {"role": "tool", "tool_call_id": "t2", "content": "坏了"}
    assert messages[4] == {"role": "user", "content": "请收尾"}
    # 工具参数序列化成 JSON 字符串
    assert messages[5] == {
        "role": "assistant",
        "content": "看看",
        "tool_calls": [
            {"id": "t3", "type": "function", "function": {"name": "add", "arguments": '{"a": 2}'}}
        ],
    }


async def test_parses_tool_calls_and_does_not_double_count_cache(flush):
    client, _ = fake_client(
        fake_completion(
            content="先算一下",
            tool_calls=[fake_tool_call("t1", "add", '{"a": 1, "b": 2}')],
            finish_reason="tool_calls",
            prompt_tokens=1000,
            completion_tokens=200,
            cached_tokens=400,
        )
    )
    llm = OpenAILLM(model="gpt-5", client=client, enable_prompt_cache=False)

    result = await llm.chat([UserMessage("1+2")], prompt_version="v1")

    assert result.stop_reason == "tool_use"
    assert result.message.text == "先算一下"
    assert result.message.tool_calls == [ToolCall("t1", "add", {"a": 1, "b": 2})]
    assert result.usage.cache_read_tokens == 400

    [trace] = await flush()
    [span] = trace.spans
    assert (span.kind, span.model, span.prompt_version) == ("llm", "gpt-5", "v1")
    # prompt_tokens 已经含缓存命中的 400，不能再加一次
    assert span.input_tokens == 1000
    assert span.output_tokens == 200


async def test_broken_tool_arguments_json_does_not_crash(trace_sink):
    client, _ = fake_client(fake_completion(tool_calls=[fake_tool_call("t1", "add", "{不是 JSON")]))
    llm = OpenAILLM(model="gpt-5", client=client, enable_prompt_cache=False)

    result = await llm.chat([UserMessage("1+2")])

    # 交给工具注册中心报「参数校验失败」，让模型下一轮自己修正
    assert result.message.tool_calls == [ToolCall("t1", "add", {})]


@pytest.mark.parametrize(
    ("finish_reason", "expected"),
    [
        ("stop", "end_turn"),
        ("tool_calls", "tool_use"),
        ("length", "max_tokens"),
        ("content_filter", "refusal"),
        ("something_new", "other"),
    ],
)
async def test_finish_reason_mapping(trace_sink, finish_reason, expected):
    client, _ = fake_client(fake_completion(finish_reason=finish_reason))
    result = await OpenAILLM(model="gpt-5", client=client).chat([UserMessage("q")])
    assert result.stop_reason == expected


async def test_empty_choices_raises_upstream_error(trace_sink):
    empty = SimpleNamespace(model="gpt-5", choices=[], usage=None)
    client, _ = fake_client(empty)
    with pytest.raises(Exception) as excinfo:
        await OpenAILLM(model="gpt-5", client=client).chat([UserMessage("q")])
    assert type(excinfo.value).__name__ == "LLMUpstreamError"
