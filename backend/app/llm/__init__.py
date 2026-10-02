"""模型抽象层：Agent 只认 base 里的消息格式和 LLMClient 协议。

- ``base.py``     与厂商无关的数据类型
- ``errors.py``   与厂商无关的异常
- ``factory.py``  按 .env 构造具体客户端
- ``pricing.py``  按厂商分表的成本估算
- ``anthropic_provider.py`` / ``openai_provider.py``  各家协议差异的转换
"""

from app.llm.base import (
    AssistantMessage,
    LLMClient,
    LLMResponse,
    Message,
    StopReason,
    ToolCall,
    ToolChoice,
    ToolResult,
    ToolResultsMessage,
    ToolSpec,
    Usage,
    UserMessage,
)
from app.llm.errors import (
    LLMAuthenticationError,
    LLMError,
    LLMNotConfiguredError,
    LLMRateLimitError,
    LLMUpstreamError,
)
from app.llm.factory import VENDORS, build_llm_client

__all__ = [
    "AssistantMessage",
    "LLMAuthenticationError",
    "LLMClient",
    "LLMError",
    "LLMNotConfiguredError",
    "LLMRateLimitError",
    "LLMResponse",
    "LLMUpstreamError",
    "Message",
    "StopReason",
    "ToolCall",
    "ToolChoice",
    "ToolResult",
    "ToolResultsMessage",
    "ToolSpec",
    "Usage",
    "UserMessage",
    "VENDORS",
    "build_llm_client",
]
