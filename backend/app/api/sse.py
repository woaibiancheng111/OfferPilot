"""SSE 事件与断线续传。

**为什么事件要带 id**：前端断线重连时会带上 ``Last-Event-ID``，服务端靠它把
漏掉的片段补回去。没有 id 的话重连只能从头再来，用户会看到问题被重复打一遍。

**为什么先用内存缓冲**：Redis 还没接进这个应用（ARQ 那一版才引入），而且
replay buffer 本来就只服务于「同一次流的重连」——单进程内存足够，进程重启了
这次流也早就结束了。把存储抽象成 :class:`ReplayStore`，接 Redis 时只需换实现，
上层 SSE 逻辑一行不用动。

缓冲的取舍：只留最近 N 条。丢更早的片段就退化成「从头重放」，
比无限占内存好——真要更长的续传需求再调 N。
"""

import json
from collections import OrderedDict
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

DEFAULT_REPLAY_SIZE = 100

__all__ = ["Event", "ReplayStore", "sse_format", "replay_from"]


@dataclass
class Event:
    """一条 SSE 事件。

    :param id: 递增序号，前端断线后靠它续传
    :param event: 事件类型，前端按类型分发
    :param data: JSON 负载
    """

    id: int
    event: str
    data: dict[str, Any] = field(default_factory=dict)


def sse_format(event: Event) -> str:
    """序列化成 SSE 帧。

    ``json.dumps`` 会把换行转义成 ``\\n``，所以 data 一定占一行。
    真出现裸换行时按 SSE 规范逐行补 ``data:`` 前缀，否则会被当成帧结束。
    """
    payload = json.dumps(event.data, ensure_ascii=False)
    lines = "".join(f"data: {line}\n" for line in payload.split("\n"))
    return f"id: {event.id}\nevent: {event.event}\n{lines}\n"


def replay_from(events: OrderedDict[int, Event], last_event_id: int) -> list[Event]:
    """取出 ``last_event_id`` 之后的事件。

    最后一条要单独处理：它可能还在被写入（流没结束），要拿到实时对象而不是快照。
    """
    if last_event_id <= 0:
        return list(events.values())
    replay = [e for eid, e in events.items() if eid > last_event_id]
    if replay:
        last = replay[-1]
        if last.id in events:
            replay[-1] = events[last.id]
    return replay


class ReplayStore:
    """按 id 保留最近 N 条事件的有界缓冲。"""

    def __init__(self, maxlen: int = DEFAULT_REPLAY_SIZE) -> None:
        self._events: OrderedDict[int, Event] = OrderedDict()
        self._maxlen = maxlen
        self._next_id = 1

    def emit(self, event: str, data: dict[str, Any]) -> Event:
        event_obj = Event(id=self._next_id, event=event, data=data)
        self._next_id += 1
        self._events[event_obj.id] = event_obj
        while len(self._events) > self._maxlen:
            self._events.popitem(last=False)
        return event_obj

    def next_id(self) -> int:
        """下一个事件的 id。

        续传时先算出「补发完应该从几号开始」，靠这个对齐。
        """
        return self._next_id

    def after(self, last_event_id: int) -> list[Event]:
        if last_event_id <= 0:
            return list(self._events.values())
        return replay_from(self._events, last_event_id)

    def __len__(self) -> int:
        return len(self._events)

    def snapshot(self) -> OrderedDict[int, Event]:
        return OrderedDict(self._events)


async def with_replay(
    produce: AsyncIterator[Event],
    store: ReplayStore,
    last_event_id: int = 0,
) -> AsyncIterator[str]:
    """先补发断线期间漏掉的，再接着产出新的。

    产出的是**已经序列化好的 SSE 帧字符串**：``StreamingResponse`` 只接受
    str/bytes，序列化必须发生在这个边界上；往上吐 Event 对象会得到空响应体。
    """
    for missed in store.after(last_event_id):
        yield sse_format(missed)
    async for event in produce:
        yield sse_format(event)
