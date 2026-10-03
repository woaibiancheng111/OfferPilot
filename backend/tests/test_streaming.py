"""SSE 基础设施和流式调用链。

重点不是「接口能返回」，而是三件容易做错的事：
- 事件帧的序列化格式（换行会截断事件）
- 断线续传不能漏事件、也不能重发已收到的
- async generator 的 span 必须在提前 break 时收尾，否则 trace 里永远挂着一条
"""

import pytest

from app.api.sse import Event, ReplayStore, sse_format, with_replay
from app.llm.base import TextStream, Usage
from app.tracing import tracer

# ---------- 帧格式 ----------


def test_sse_format_has_id_event_and_data():
    frame = sse_format(Event(id=7, event="question", data={"delta": "你"}))
    assert frame.startswith("id: 7\n")
    assert "event: question\n" in frame
    assert frame.endswith("\n\n")


def test_sse_format_keeps_multiline_payload_on_one_data_line():
    """json.dumps 会把换行转义成 \\n，所以带换行的文本仍然只占一个 data 行。"""
    frame = sse_format(Event(id=1, event="x", data={"text": "第一行\n第二行"}))
    assert frame.count("data: ") == 1
    # 换行在 JSON 里是转义后的两个字符，不会被误当成帧结束
    assert frame.rstrip().endswith("}")
    assert "第一行" in frame


def test_sse_format_keeps_chinese_readable():
    """不转义成 \\u，浏览器和日志里都能直接看。"""
    frame = sse_format(Event(id=1, event="x", data={"t": "追问"}))
    assert "追问" in frame
    assert "\\u" not in frame


# ---------- 续传缓冲 ----------


def test_replay_store_increments_id():
    store = ReplayStore()
    assert store.emit("a", {}).id == 1
    assert store.emit("b", {}).id == 2


def test_replay_store_is_bounded():
    store = ReplayStore(maxlen=3)
    for i in range(6):
        store.emit("q", {"i": i})
    # 最早的被挤掉，只留最近 3 条
    assert len(store) == 3
    assert [e.data["i"] for e in store.snapshot().values()] == [3, 4, 5]


def test_after_returns_only_newer_events():
    store = ReplayStore()
    for i in range(5):
        store.emit("q", {"i": i})
    assert [e.id for e in store.after(3)] == [4, 5]
    assert store.after(99) == []


def test_after_zero_returns_everything():
    """首次连接没有 Last-Event-ID，应该拿到全部。"""
    store = ReplayStore()
    store.emit("a", {})
    assert len(store.after(0)) == 1


# ---------- 续传串接 ----------


async def test_with_replay_replays_missed_then_continues():
    store = ReplayStore()
    store.emit("turn_start", {"turn": 0})
    store.emit("question", {"delta": "你"})
    store.emit("question", {"delta": "好"})

    async def fresh():
        yield store.emit("question", {"delta": "吗"})

    stream = with_replay(fresh(), store, last_event_id=2)
    out = await _parse(stream)

    # 断线期间漏掉的第 3 条被补回来了，接着的是新产生的
    assert [e["data"]["delta"] for e in out] == ["好", "吗"]
    # 补发的事件 id 和实时事件连成一条递增序列
    assert [e["id"] for e in out] == [3, 4]


async def test_with_replay_from_scratch_when_no_last_event_id():
    store = ReplayStore()

    async def fresh():
        yield store.emit("a", {})

    out = await _parse(with_replay(fresh(), store, last_event_id=0))
    assert len(out) == 1


# ---------- TextStream ----------


async def test_text_stream_accumulates_and_iterates():
    stream = TextStream()

    async def drive():
        await stream.push("你")
        await stream.push("好")
        stream.finish(
            model="m", stop_reason="end_turn", usage=Usage(input_tokens=3, output_tokens=2)
        )

    await drive()
    # 迭代给的是增量本身，完整文本要读 .text
    assert [c async for c in stream] == ["你", "好"]
    assert stream.text == "你好"
    assert stream.model == "m"
    assert stream.stop_reason == "end_turn"
    assert stream.usage.input_tokens == 3


async def test_text_stream_ignores_empty_deltas():
    stream = TextStream()
    await stream.push("")
    await stream.push("x")
    await stream.push("")
    assert stream.text == "x"


# ---------- tracer 对 async generator 的支持 ----------


async def test_span_closes_when_generator_is_fully_consumed(flush):
    @tracer.observe("llm", name="gen.full")
    async def gen():
        for i in range(3):
            yield i

    async for _ in gen():
        pass

    [trace] = await flush()
    [span] = trace.spans
    assert span.output["chunks"] == 3
    assert span.ended_at is not None


async def test_span_closes_when_caller_breaks_early(flush):
    """调用方只取前两个就 break，span 也要收尾，否则 trace 里永远挂着一条。

    注意 ``break`` 之后 async generator 处于挂起状态，要等显式 ``aclose()``
    （或被 GC）才会跑到 ``finally``。真实场景里客户端断连时 Starlette 会
    主动关闭响应体的迭代器，所以这条路径是会被触发的。
    """

    @tracer.observe("llm", name="gen.partial")
    async def gen():
        for i in range(100):
            yield i

    agen = gen()
    async for value in agen:
        if value == 1:
            break
    await agen.aclose()

    [trace] = await flush()
    [span] = trace.spans
    assert span.ended_at is not None
    assert span.output["chunks"] == 2


async def test_span_records_error_from_generator(flush):
    @tracer.observe("llm", name="gen.boom")
    async def gen():
        yield 1
        raise ValueError("炸了")

    with pytest.raises(ValueError):
        async for _ in gen():
            pass

    [trace] = await flush()
    assert trace.status == "error"
    assert "炸了" in trace.spans[0].error


# ---------- 辅助 ----------


async def _parse(stream) -> list[dict]:
    """把 SSE 帧字符串解析回事件，方便断言。"""
    import json

    out = []
    buf = ""
    async for raw in stream:
        buf += raw
        while "\n\n" in buf:
            frame, buf = buf.split("\n\n", 1)
            event = {"event": None, "id": None, "data": {}}
            for line in frame.splitlines():
                if line.startswith("id:"):
                    event["id"] = int(line[3:])
                elif line.startswith("event:"):
                    event["event"] = line[6:]
                elif line.startswith("data:"):
                    event["data"] = json.loads(line[5:])
            out.append(event)
    return out
