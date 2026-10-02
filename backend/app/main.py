import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import agent, interview, jd, traces
from app.config import get_settings
from app.db.session import create_engine, create_session_factory
from app.db.trace_sink import SqlAlchemyTraceSink
from app.llm import build_llm_client, describe_config
from app.tracing import BatchExporter, tracer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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
    logger.info("模型配置：%s", describe_config(settings))
    try:
        yield
    finally:
        # 先把内存里的 trace 写完再关连接池
        await exporter.shutdown()
        tracer.exporter = None
        await engine.dispose()


app = FastAPI(title="OfferPilot API", version="0.1.0", lifespan=lifespan)
# 前端开发服务器和后端不同源，不加这个浏览器会直接拦掉所有请求。
# 允许的具体域名来自配置，生产环境别用通配符。
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(agent.router)
app.include_router(jd.router)
app.include_router(interview.router)
app.include_router(traces.router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
