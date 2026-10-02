"""路由层共用的错误映射。

模型调用失败统一以厂商中立异常（``app.llm.errors``）冒泡，这里集中翻译成
HTTP 状态码。接第三家模型时，provider 层把异常翻译好就行，路由不用改。
"""

from fastapi import HTTPException

from app.llm.errors import (
    LLMAuthenticationError,
    LLMError,
    LLMNotConfiguredError,
    LLMRateLimitError,
    LLMUpstreamError,
)

# 顺序有意义：子类要排在父类前面
_STATUS_BY_ERROR: tuple[tuple[type[Exception], int], ...] = (
    (LLMNotConfiguredError, 503),
    (LLMAuthenticationError, 503),
    (LLMRateLimitError, 429),
    (LLMUpstreamError, 502),
)


def http_error_for_llm(exc: LLMError) -> HTTPException:
    status = next((code for err, code in _STATUS_BY_ERROR if isinstance(exc, err)), 502)
    return HTTPException(status_code=status, detail=str(exc))
