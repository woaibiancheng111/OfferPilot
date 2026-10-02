import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

SpanKind = Literal["agent", "llm", "tool", "retrieval", "custom"]


def new_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass
class Span:
    """调用树中的一个节点：一次 Agent 步骤、LLM 调用或工具调用。"""

    trace_id: str
    kind: SpanKind
    name: str
    parent_span_id: str | None = None
    id: str = field(default_factory=new_id)
    input: Any = None
    output: Any = None
    model: str | None = None
    prompt_version: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float = 0.0
    error: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    started_at: datetime = field(default_factory=utcnow)
    ended_at: datetime | None = None
    latency_ms: int | None = None
    # 用单调时钟算耗时，避免系统时间跳变
    _t0: float = field(default_factory=time.perf_counter, repr=False)

    def end(self) -> None:
        self.ended_at = utcnow()
        self.latency_ms = int((time.perf_counter() - self._t0) * 1000)


@dataclass
class Trace:
    """一次完整请求，包含它产生的所有 span。"""

    name: str
    user_id: str | None = None
    id: str = field(default_factory=new_id)
    status: Literal["ok", "error"] = "ok"
    spans: list[Span] = field(default_factory=list)
    started_at: datetime = field(default_factory=utcnow)
    ended_at: datetime | None = None
    latency_ms: int | None = None
    _t0: float = field(default_factory=time.perf_counter, repr=False)

    @property
    def total_tokens(self) -> int:
        return sum(s.input_tokens + s.output_tokens for s in self.spans)

    @property
    def total_cost(self) -> float:
        return sum(s.cost for s in self.spans)

    def end(self) -> None:
        self.ended_at = utcnow()
        self.latency_ms = int((time.perf_counter() - self._t0) * 1000)
