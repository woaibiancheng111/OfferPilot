"""演示用 Agent：用两个简单工具验证 agent loop 和 trace 全链路。

正式的求职 Agent（JD 解析、模拟面试）从第 2 周开始写。
"""

import ast
import operator
from datetime import datetime
from typing import Annotated
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field

from app.tools.registry import ToolError, ToolRegistry

DEMO_SYSTEM_PROMPT = "你是一个简洁的助手。需要计算或查询时间时，请使用提供的工具，不要自己心算。"
# 版本号不在这里手写，由 run_agent 从 DEMO_SYSTEM_PROMPT 的内容自动算出

demo_tools = ToolRegistry()


@demo_tools.tool()
async def get_current_time(
    timezone: Annotated[
        str, Field(description="IANA 时区名，例如 Asia/Shanghai")
    ] = "Asia/Shanghai",
) -> str:
    """查询指定时区的当前日期和时间。"""
    try:
        tz = ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError) as e:
        raise ToolError(f"未知时区：{timezone}") from e
    return datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S %Z")


_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


@demo_tools.tool()
async def calculator(
    expression: Annotated[str, Field(description="四则运算表达式，例如 (3 + 5) * 2 ** 3")],
) -> float:
    """计算数学表达式，支持 + - * / // % ** 和括号。"""
    try:
        return _eval(ast.parse(expression, mode="eval").body)
    except (SyntaxError, ZeroDivisionError, OverflowError) as e:
        raise ToolError(f"无法计算 {expression!r}：{e}") from e


def _eval(node: ast.expr) -> float:
    # 只解释白名单内的语法节点，绝不用 eval()，防止模型或用户注入任意代码
    match node:
        case ast.Constant(value=int() | float() as value):
            return value
        case ast.BinOp(left=left, op=op, right=right) if type(op) in _OPERATORS:
            if isinstance(op, ast.Pow) and abs(_eval(right)) > 100:
                raise ToolError("指数过大")
            return _OPERATORS[type(op)](_eval(left), _eval(right))
        case ast.UnaryOp(op=op, operand=operand) if type(op) in _OPERATORS:
            return _OPERATORS[type(op)](_eval(operand))
    raise ToolError(f"不支持的表达式：{ast.dump(node)}")
