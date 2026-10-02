import asyncio
import contextlib
import logging
from collections import deque
from typing import Protocol

from app.security.redact import redact_trace
from app.tracing.span import Trace

logger = logging.getLogger(__name__)


class TraceSink(Protocol):
    """trace 的最终落点（数据库、内存、文件……）。"""

    async def write(self, traces: list[Trace]) -> None: ...


class InMemorySink:
    """测试和本地调试用。"""

    def __init__(self) -> None:
        self.traces: list[Trace] = []

    async def write(self, traces: list[Trace]) -> None:
        self.traces.extend(traces)


class BatchExporter:
    """异步批量导出 trace。

    业务协程只做一次 O(1) 的入队，写库交给后台任务，按时间间隔或攒够一批时触发。
    队列满时丢弃新 trace 并计数：观测系统宁可丢数据，也不能拖垮主流程。
    """

    def __init__(
        self,
        sink: TraceSink,
        *,
        flush_interval_s: float = 1.0,
        batch_size: int = 50,
        max_queue_size: int = 10_000,
        redact_payloads: bool = True,
    ) -> None:
        self.sink = sink
        self.flush_interval_s = flush_interval_s
        self.batch_size = batch_size
        self.max_queue_size = max_queue_size
        self.redact_payloads = redact_payloads
        self.dropped = 0
        # 累计被脱敏的 span 数：这个数突然上涨说明线上出现了新的敏感字段
        self.redacted_spans = 0
        self._queue: deque[Trace] = deque()
        self._wakeup = asyncio.Event()
        self._lock = asyncio.Lock()
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name="trace-exporter")

    def enqueue(self, trace: Trace) -> None:
        if len(self._queue) >= self.max_queue_size:
            self.dropped += 1
            return
        # 脱敏放在入队这一步：这是 trace 唯一的落库入口，业务代码绕不过去。
        # 队列满时直接丢弃，所以脱敏放在容量检查之后，不为被丢掉的 trace 白费 CPU。
        if self.redact_payloads:
            self.redacted_spans += redact_trace(trace)
        self._queue.append(trace)
        if len(self._queue) >= self.batch_size:
            self._wakeup.set()

    async def flush(self) -> None:
        async with self._lock:
            while self._queue:
                batch = [
                    self._queue.popleft() for _ in range(min(self.batch_size, len(self._queue)))
                ]
                try:
                    await self.sink.write(batch)
                except Exception:
                    # 写失败只记日志，不重试，避免失败的批次无限堆积
                    logger.exception("写入 %d 条 trace 失败，已丢弃", len(batch))
                    self.dropped += len(batch)

    async def shutdown(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        await self.flush()

    async def _run(self) -> None:
        while True:
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._wakeup.wait(), timeout=self.flush_interval_s)
            self._wakeup.clear()
            await self.flush()
