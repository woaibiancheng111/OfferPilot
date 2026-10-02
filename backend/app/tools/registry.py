import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, TypeVar, get_type_hints

from pydantic import BaseModel, ConfigDict, ValidationError, create_model

from app.llm.base import ToolSpec
from app.tracing import tracer

ToolFunc = Callable[..., Awaitable[Any]]
SubmitFunc = Callable[[Any], Any]

ModelT = TypeVar("ModelT", bound=BaseModel)


class ToolError(Exception):
    """工具执行失败。错误信息会原样返回给模型，让它自行修正。"""


@dataclass
class RegisteredTool:
    """两种工具二选一：

    - ``func``：普通工具，从函数签名生成 schema
    - ``submit``：结构化输出工具，schema 来自 Pydantic 模型
    """

    spec: ToolSpec
    args_model: type[BaseModel]
    func: ToolFunc | None = None
    submit: SubmitFunc | None = None


class ToolRegistry:
    """工具注册中心：从函数签名或 Pydantic 模型自动生成 JSON Schema，并在执行前校验参数。"""

    def __init__(self) -> None:
        self._tools: dict[str, RegisteredTool] = {}

    def tool(
        self, name: str | None = None, description: str | None = None
    ) -> Callable[[ToolFunc], ToolFunc]:
        def decorator(func: ToolFunc) -> ToolFunc:
            if not inspect.iscoroutinefunction(func):
                raise TypeError(f"工具 {func.__name__} 必须是 async 函数")
            tool_name = name or func.__name__
            args_model = _build_args_model(func)
            self._register(
                RegisteredTool(
                    spec=ToolSpec(
                        name=tool_name,
                        description=description or inspect.getdoc(func) or "",
                        input_schema=_schema_of(args_model),
                    ),
                    args_model=args_model,
                    func=func,
                )
            )
            return func

        return decorator

    def submit(
        self,
        name: str,
        *,
        description: str,
        model: type[ModelT],
        on_submit: SubmitFunc,
    ) -> type[ModelT]:
        """把一个 Pydantic 模型注册成「提交结果」的工具。

        模型的 JSON Schema 直接作为工具的 input_schema，模型调用工具时参数会被
        Pydantic 校验；校验失败会以 ``is_error`` 把具体错误回给模型，模型下一轮
        自行修正——这就是结构化输出的「校验失败自动重试」，不用另写一套重试逻辑。

        :param model: 结构化输出的模型类
        :param on_submit: 校验通过后的回调，入参是已经校验好的模型实例
        """
        self._register(
            RegisteredTool(
                spec=ToolSpec(name=name, description=description, input_schema=_schema_of(model)),
                args_model=model,
                submit=on_submit,
            )
        )
        return model

    def _register(self, tool: RegisteredTool) -> None:
        if tool.spec.name in self._tools:
            raise ValueError(f"工具 {tool.spec.name} 重复注册")
        self._tools[tool.spec.name] = tool

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
                validated = tool.args_model.model_validate(arguments)
            except ValidationError as e:
                raise ToolError(f"参数校验失败：{_format_validation_error(e)}") from e

            if tool.submit is not None:
                # 参数已在上面的 model_validate 校验过，直接交给回调
                result = tool.submit(validated)
            else:
                result = await tool.func(**validated.model_dump())

            span.output = tracer.serialize(result)
            return result


def _schema_of(model: type[BaseModel]) -> dict[str, Any]:
    schema = model.model_json_schema()
    # 顶层 title 只是模型类名，对模型理解工具没有帮助，去掉省 token
    schema.pop("title", None)
    return schema


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
    """把校验错误整理成模型能直接照着改的句子。

    会带上模型实际填的值：对话轮次多了之后，模型未必记得自己刚才填了什么，
    只说"不合法"它可能改到别的字段上去。
    """
    parts: list[str] = []
    for err in error.errors():
        where = ".".join(str(p) for p in err["loc"]) or "参数"
        got = err.get("input")
        if got is not None:
            shown = repr(got)
            if len(shown) > 60:
                shown = f"{shown[:60]}…"
            parts.append(f"{where}：{err['msg']}（你填的是 {shown}）")
        else:
            parts.append(f"{where}：{err['msg']}")
    return "；".join(parts)
