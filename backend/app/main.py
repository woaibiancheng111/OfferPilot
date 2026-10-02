import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import agent, traces
from app.config import get_settings
from app.db.session import create_engine, create_session_factory
from app.db.trace_sink import SqlAlchemyTraceSink
from app.llm import build_llm_client
from app.tracing import BatchExporter, tracer

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    engine = create_engine(settings.database_url)
    session_factory = create_session_factory(engine)

    exporter = BatchExporter(
        SqlAlchemyTraceSink(session_factory),
        flush_interval_s=settings.trace_flush_interval_s,
        batch_size=settings.trace_batch_size,
    )
    tracer.exporter = exporter
    tracer.max_payload_chars = settings.trace_max_payload_chars
    exporter.start()

    app.state.session_factory = session_factory
    # 厂商由 .env 的 LLM_VENDOR 决定，这里不关心具体是哪家
    app.state.llm = build_llm_client(settings)
    try:
        yield
    finally:
        # 先把内存里的 trace 写完再关连接池
        await exporter.shutdown()
        tracer.exporter = None
        await engine.dispose()


app = FastAPI(title="OfferPilot API", version="0.1.0", lifespan=lifespan)
app.include_router(agent.router)
app.include_router(traces.router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
