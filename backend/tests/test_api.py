import httpx
import pytest
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.models import Base
from app.db.session import create_session_factory
from app.db.trace_sink import SqlAlchemyTraceSink
from app.llm.base import ToolCall
from app.main import app
from app.tracing import BatchExporter, tracer
from tests.fakes import ScriptedLLM, reply


@pytest.fixture
async def client():
    """用 SQLite 内存库代替 PostgreSQL，端到端验证：Agent → trace 写库 → 查询接口。"""
    # StaticPool 让所有连接共用同一个内存库
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = create_session_factory(engine)

    previous = tracer.exporter
    tracer.exporter = BatchExporter(SqlAlchemyTraceSink(session_factory))
    app.state.session_factory = session_factory

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

    tracer.exporter = previous
    await engine.dispose()


async def test_health(client):
    response = await client.get("/health")
    assert response.json() == {"status": "ok"}


async def test_demo_agent_trace_is_queryable(client):
    app.state.llm = ScriptedLLM(
        [
            reply(tool_calls=[ToolCall("c1", "calculator", {"expression": "(3 + 5) * 2"})]),
            reply("结果是 16"),
        ]
    )

    response = await client.post("/api/agent/demo", json={"message": "算一下", "user_id": "u1"})
    assert response.status_code == 200
    body = response.json()
    assert body["text"] == "结果是 16"
    assert body["steps"] == 2

    await tracer.exporter.flush()

    listing = (await client.get("/api/traces", params={"user_id": "u1"})).json()
    assert listing["total"] == 1
    assert listing["items"][0]["id"] == body["trace_id"]
    assert listing["items"][0]["total_tokens"] == 30

    detail = (await client.get(f"/api/traces/{body['trace_id']}")).json()
    assert detail["name"] == "agent.demo"
    [root] = detail["spans"]
    assert (root["kind"], root["name"]) == ("agent", "demo_agent")
    assert [(c["kind"], c["name"]) for c in root["children"]] == [
        ("llm", "fake.chat"),
        ("tool", "calculator"),
        ("llm", "fake.chat"),
    ]
    tool_span = root["children"][1]
    assert tool_span["input"] == {"expression": "(3 + 5) * 2"}
    assert tool_span["output"] == 16


async def test_missing_trace_returns_404(client):
    response = await client.get("/api/traces/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


@pytest.mark.parametrize(
    ("expression", "expected"),
    [("2 ** 10", 1024), ("7 // 2", 3), ("-(1 + 2)", -3)],
)
async def test_calculator(expression, expected, trace_sink):
    from app.agents.demo import calculator

    assert await calculator(expression) == expected


@pytest.mark.parametrize("expression", ["__import__('os')", "1 / 0", "2 ** 1000", "abc"])
async def test_calculator_rejects_unsafe_or_invalid(expression, trace_sink):
    from app.agents.demo import calculator
    from app.tools.registry import ToolError

    with pytest.raises(ToolError):
        await calculator(expression)
