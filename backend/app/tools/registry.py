import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, get_type_hints

from pydantic import BaseModel, ConfigDict, ValidationError, create_model

from app.llm.base import ToolSpec
from app.tracing import tracer

ToolFunc = Callable[..., Awaitable[Any]]


class ToolError(Exception):
    """工具执行失败。错误信息会原样返回给模型，让它自行修正。"""


@dataclass
class RegisteredTool:
    spec: ToolSpec
    func: ToolFunc
    args_model: type[BaseModel]


class ToolRegistry:
    """工具注册中心：从函数签名自动生成 JSON Schema，并在执行前校验参数。"""

    def __init__(self) -> None:
        self._tools: dict[str, RegisteredTool] = {}

    def tool(
        self, name: str | None = None, description: str | None = None
    ) -> Callable[[ToolFunc], ToolFunc]:
        def decorator(func: ToolFunc) -> ToolFunc:
            if not inspect.iscoroutinefunction(func):
                raise TypeError(f"工具 {func.__name__} 必须是 async 函数")
            tool_name = name or func.__name__
            if tool_name in self._tools:
                raise ValueError(f"工具 {tool_name} 重复注册")

            args_model = _build_args_model(func)
            schema = args_model.model_json_schema()
            schema.pop("title", None)
            self._tools[tool_name] = RegisteredTool(
                spec=ToolSpec(
                    name=tool_name,
                    description=description or inspect.getdoc(func) or "",
                    input_schema=schema,
                ),
                func=func,
                args_model=args_model,
            )
            return func

        return decorator

    @property
    def specs(self) -> list[ToolSpec]:
        return [t.spec for t in self._tools.values()]

    def __len__(self) -> int:
        return len(self._tools)

    async def execute(self, name: str, arguments: dict[str, Any]) -> Any:
        tool = self._tools.get(name)
        if tool is None:
            raise ToolError(f"不存在名为 {name} 的工具，可用工具：{', '.join(self._tools)}")

        async with tracer.span("tool", name, input=arguments) as span:
            try:
                args = tool.args_model.model_validate(arguments)
            except ValidationError as e:
                raise ToolError(f"参数校验失败：{_format_validation_error(e)}") from e
            result = await tool.func(**args.model_dump())
            span.output = tracer.serialize(result)
            return result


def _build_args_model(func: ToolFunc) -> type[BaseModel]:
    hints = get_type_hints(func, include_extras=True)
    fields: dict[str, Any] = {}
    for param in inspect.signature(func).parameters.values():
        if param.name not in hints:
            raise TypeError(f"工具 {func.__name__} 的参数 {param.name} 缺少类型注解")
        default = ... if param.default is inspect.Parameter.empty else param.default
        fields[param.name] = (hints[param.name], default)
    # 禁止多余参数，模型传错字段名时能明确报错，而不是被静默忽略
    return create_model(f"{func.__name__}_args", __config__=ConfigDict(extra="forbid"), **fields)


def _format_validation_error(error: ValidationError) -> str:
    return "；".join(
        f"{'.'.join(str(p) for p in err['loc']) or '参数'}：{err['msg']}" for err in error.errors()
    )
