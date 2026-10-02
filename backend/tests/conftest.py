import pytest

from app.tracing import BatchExporter, InMemorySink, tracer


@pytest.fixture
async def trace_sink():
    """把全局 tracer 接到内存 sink 上，测试结束后恢复。"""
    sink = InMemorySink()
    exporter = BatchExporter(sink)
    previous = tracer.exporter
    tracer.exporter = exporter
    yield sink
    tracer.exporter = previous


@pytest.fixture
async def flush(trace_sink):
    async def _flush():
        await tracer.exporter.flush()
        return trace_sink.traces

    return _flush
