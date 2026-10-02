import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import SpanRecord, TraceRecord
from app.db.session import get_session

router = APIRouter(prefix="/api/traces", tags=["traces"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


class TraceSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    user_id: str | None
    status: str
    total_tokens: int
    latency_ms: int | None
    started_at: datetime


class TraceList(BaseModel):
    items: list[TraceSummary]
    total: int


class SpanNode(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    parent_span_id: uuid.UUID | None
    kind: str
    name: str
    input: Any
    output: Any
    attributes: dict[str, Any]
    model: str | None
    prompt_version: str | None
    input_tokens: int
    output_tokens: int
    latency_ms: int | None
    error: str | None
    started_at: datetime
    ended_at: datetime | None
    children: list["SpanNode"] = []


class TraceDetail(TraceSummary):
    ended_at: datetime | None
    spans: list[SpanNode]


@router.get("", response_model=TraceList)
async def list_traces(
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    user_id: str | None = None,
) -> TraceList:
    query = select(TraceRecord)
    count_query = select(func.count()).select_from(TraceRecord)
    if user_id is not None:
        query = query.where(TraceRecord.user_id == user_id)
        count_query = count_query.where(TraceRecord.user_id == user_id)

    rows = await session.scalars(
        query.order_by(TraceRecord.started_at.desc()).limit(limit).offset(offset)
    )
    total = await session.scalar(count_query)
    return TraceList(items=[TraceSummary.model_validate(r) for r in rows], total=total or 0)


@router.get("/{trace_id}", response_model=TraceDetail)
async def get_trace(trace_id: uuid.UUID, session: SessionDep) -> TraceDetail:
    trace = await session.scalar(
        select(TraceRecord)
        .where(TraceRecord.id == trace_id)
        .options(selectinload(TraceRecord.spans))
    )
    if trace is None:
        raise HTTPException(status_code=404, detail="trace 不存在")
    return TraceDetail(
        **TraceSummary.model_validate(trace).model_dump(),
        ended_at=trace.ended_at,
        spans=build_span_tree(trace.spans),
    )


def build_span_tree(spans: list[SpanRecord]) -> list[SpanNode]:
    """把扁平的 span 列表还原成树，同一层按开始时间排序。"""
    nodes = {s.id: SpanNode.model_validate(s) for s in spans}
    roots: list[SpanNode] = []
    for node in sorted(nodes.values(), key=lambda n: n.started_at):
        parent = nodes.get(node.parent_span_id) if node.parent_span_id else None
        # 父 span 缺失（比如被截断）时当作根节点展示，不丢数据
        (parent.children if parent else roots).append(node)
    return roots
