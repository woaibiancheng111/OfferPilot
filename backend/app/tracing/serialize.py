import dataclasses
import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel


def _default(obj: Any) -> Any:
    if isinstance(obj, BaseModel):
        return obj.model_dump(mode="json")
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {
            f.name: getattr(obj, f.name)
            for f in dataclasses.fields(obj)
            if not f.name.startswith("_")
        }
    if isinstance(obj, set | frozenset | tuple):
        return list(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    return repr(obj)


def safe_serialize(value: Any, max_chars: int) -> Any:
    """把任意对象转成可存进 JSON 列的值。

    trace 永远不能因为序列化失败而影响业务，所以这里兜底用 repr；
    过大的内容会被截断，避免单条 span 撑爆数据库。
    """
    try:
        text = json.dumps(value, default=_default, ensure_ascii=False)
    except (TypeError, ValueError):
        text = json.dumps(repr(value), ensure_ascii=False)

    if len(text) > max_chars:
        return {"_truncated": True, "_original_chars": len(text), "preview": text[:max_chars]}
    return json.loads(text)
