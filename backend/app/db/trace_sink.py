import uuid

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import SpanRecord, TraceRecord
from app.tracing import Trace


class SqlAlchemyTraceSink:
    """把一批 trace 连同它们的 span 写进数据库，一批一个事务。"""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def write(self, traces: list[Trace]) -> None:
        async with self.session_factory() as session, session.begin():
            session.add_all(_to_record(t) for t in traces)


def _to_record(trace: Trace) -> TraceRecord:
    return TraceRecord(
        id=uuid.UUID(trace.id),
        name=trace.name,
        user_id=trace.user_id,
        status=trace.status,
        total_tokens=trace.total_tokens,
        latency_ms=trace.latency_ms,
        started_at=trace.started_at,
        ended_at=trace.ended_at,
        spans=[
            SpanRecord(
                id=uuid.UUID(s.id),
                parent_span_id=uuid.UUID(s.parent_span_id) if s.parent_span_id else None,
                kind=s.kind,
                name=s.name,
                input=s.input,
                output=s.output,
                attributes=s.attributes,
                model=s.model,
                prompt_version=s.prompt_version,
                input_tokens=s.input_tokens,
                output_tokens=s.output_tokens,
                latency_ms=s.latency_ms,
                error=s.error,
                started_at=s.started_at,
                ended_at=s.ended_at,
            )
            for s in trace.spans
        ],
    )
