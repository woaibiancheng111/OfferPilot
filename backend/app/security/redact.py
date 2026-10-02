"""隐私脱敏。

简历、手机号、身份证这类信息会随 prompt 一起进入 trace。
观测系统不能因为"方便排查"就把真实个人信息落到库里——所以脱敏挂在
``BatchExporter.enqueue`` 上，也就是所有 trace 唯一的落库入口，绕不过去。

已知局限：正则只能覆盖格式化明确的标识符。家庭住址、公司内部代号这类
自由文本里的个人信息匹配不到，需要靠别的方式处理（不把原文送进 trace、
或者改用结构化字段），这一点在 README 里也写明了。
"""

import hashlib
import json
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.tracing.span import Trace

# 顺序有意义：先把手机号替掉，否则 11 位数字会先被学号规则误伤
_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"), "[手机号]"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "[邮箱]"),
    (re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)"), "[身份证]"),
    (re.compile(r"(?<!\d)\d{15}(?!\d)"), "[身份证]"),
    (re.compile(r"(?<!\d)\d{16,19}(?!\d)"), "[银行卡]"),
    (re.compile(r"(?<!\d)\d{10,12}(?!\d)"), "[学号]"),
)

PLACEHOLDER_PREFIX = "["
_MAX_DEPTH = 12


def redact_text(text: str) -> str:
    """替换掉格式化明确的个人标识符。"""
    for pattern, placeholder in _PATTERNS:
        text = pattern.sub(placeholder, text)
    return text


def redact(value: Any, _depth: int = 0) -> Any:
    """递归处理 span 里任意形状的 payload（字符串 / 字典 / 列表）。"""
    if _depth > _MAX_DEPTH:
        return value
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {k: redact(v, _depth + 1) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v, _depth + 1) for v in value]
    return value


def content_hash(value: Any) -> str:
    """内容指纹。

    脱敏后内容就不可逆了，但保留指纹仍然能回答"这条脱敏掉的输入是不是
    上一条那条"，用来做去重分析和确认敏感数据反复出现。
    """
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True, default=repr)
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:8]


def redact_trace(trace: "Trace") -> int:
    """就地脱敏一条 trace，返回被改动的 span 数。"""
    touched = 0
    for span in trace.spans:
        changed: list[str] = []

        for field in ("input", "output"):
            original = getattr(span, field)
            if original is None:
                continue
            cleaned = redact(original)
            if cleaned != original:
                setattr(span, field, cleaned)
                span.attributes[f"{field}_hash"] = content_hash(original)
                changed.append(field)

        if span.error:
            cleaned_error = redact_text(span.error)
            if cleaned_error != span.error:
                span.error = cleaned_error
                changed.append("error")

        if span.attributes:
            span.attributes = redact(span.attributes)

        if changed:
            span.attributes["redacted"] = changed
            touched += 1
    return touched
