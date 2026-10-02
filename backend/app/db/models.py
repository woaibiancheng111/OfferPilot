import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# 生产用 PostgreSQL 的 JSONB，测试用 SQLite 时自动退化为 JSON
JsonType = JSON().with_variant(JSONB(), "postgresql")


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class TraceRecord(Base):
    __tablename__ = "traces"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    user_id: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16))
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    spans: Mapped[list["SpanRecord"]] = relationship(
        back_populates="trace", cascade="all, delete-orphan", order_by="SpanRecord.started_at"
    )

    __table_args__ = (
        Index("ix_traces_started_at", "started_at"),
        Index("ix_traces_user_id_started_at", "user_id", "started_at"),
    )


class SpanRecord(Base):
    __tablename__ = "spans"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    trace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("traces.id", ondelete="CASCADE"))
    parent_span_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    kind: Mapped[str] = mapped_column(String(16))
    name: Mapped[str] = mapped_column(String(200))
    input: Mapped[Any] = mapped_column(JsonType, nullable=True)
    output: Mapped[Any] = mapped_column(JsonType, nullable=True)
    attributes: Mapped[dict[str, Any]] = mapped_column(JsonType, default=dict)
    model: Mapped[str | None] = mapped_column(String(100))
    prompt_version: Mapped[str | None] = mapped_column(String(100))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    trace: Mapped[TraceRecord] = relationship(back_populates="spans")

    __table_args__ = (
        Index("ix_spans_trace_id", "trace_id"),
        Index("ix_spans_kind_name", "kind", "name"),
    )


class InterviewSessionRecord(Base):
    """一场模拟面试。"""

    __tablename__ = "interview_sessions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64))
    # 只存 JD 解析结果，不存简历原文——原文不进 trace 也不进这里
    jd_analysis: Mapped[Any] = mapped_column(JsonType)
    plan: Mapped[Any | None] = mapped_column(JsonType, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="created")
    # planning / interviewing / finished
    trace_id: Mapped[str | None] = mapped_column(String(36))
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    turns: Mapped[list["InterviewTurnRecord"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="InterviewTurnRecord.turn_index",
    )

    __table_args__ = (Index("ix_interview_sessions_user_created", "user_id", "created_at"),)


class InterviewTurnRecord(Base):
    """一问一答。评估结果是评测闭环的原始素材，所以原样存下来。"""

    __tablename__ = "interview_turns"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("interview_sessions.id", ondelete="CASCADE")
    )
    turn_index: Mapped[int] = mapped_column(Integer)
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    topic: Mapped[str | None] = mapped_column(String(200))
    evaluation: Mapped[Any | None] = mapped_column(JsonType, nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    session: Mapped[InterviewSessionRecord] = relationship(back_populates="turns")

    __table_args__ = (
        Index("ix_interview_turns_session", "session_id", "turn_index"),
        # 后面要按知识点捞历史表现建评测集，这个索引是前提
        Index("ix_interview_turns_topic", "topic"),
    )
