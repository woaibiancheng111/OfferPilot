from typing import Annotated

import pytest
from pydantic import Field

from app.tools.registry import ToolError, ToolRegistry


@pytest.fixture
def registry():
    registry = ToolRegistry()

    @registry.tool()
    async def search_questions(
        topic: Annotated[str, Field(description="知识点")],
        limit: int = 5,
    ) -> list[str]:
        """按知识点检索面试题。"""
        return [f"{topic}-{i}" for i in range(limit)]

    return registry


def test_schema_is_generated_from_signature(registry):
    [spec] = registry.specs
    assert spec.name == "search_questions"
    assert spec.description == "按知识点检索面试题。"
    assert spec.input_schema["required"] == ["topic"]
    assert spec.input_schema["properties"]["topic"]["description"] == "知识点"
    assert spec.input_schema["properties"]["limit"]["default"] == 5
    assert spec.input_schema["additionalProperties"] is False


async def test_execute_validates_and_coerces_arguments(registry, trace_sink):
    assert await registry.execute("search_questions", {"topic": "Redis", "limit": "2"}) == [
        "Redis-0",
        "Redis-1",
    ]


async def test_invalid_arguments_raise_tool_error(registry, trace_sink):
    with pytest.raises(ToolError, match="参数校验失败.*topic"):
        await registry.execute("search_questions", {"limit": 1})
    with pytest.raises(ToolError, match="参数校验失败.*unknown"):
        await registry.execute("search_questions", {"topic": "x", "unknown": 1})


async def test_unknown_tool_lists_available_tools(registry, trace_sink):
    with pytest.raises(ToolError, match="search_questions"):
        await registry.execute("nope", {})


def test_rejects_sync_functions_and_duplicates(registry):
    with pytest.raises(TypeError):

        @registry.tool()
        def sync_tool() -> None: ...

    with pytest.raises(ValueError):

        @registry.tool(name="search_questions")
        async def duplicate() -> None: ...
