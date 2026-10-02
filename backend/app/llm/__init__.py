"""模型抽象层：Agent 只认 base 里的消息格式和 LLMClient 协议。

- ``base.py``     与厂商无关的数据类型
- ``errors.py``   与厂商无关的异常
- ``factory.py``  按 .env 构造具体客户端
- ``anthropic_provider.py`` / ``openai_provider.py``  各家协议差异的转换

只统计 token，不折算金额——可能接第三方中转，模型名和单价不在我们控制内。
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
from app.llm.factory import VENDORS, build_llm_client, describe_config

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
    "describe_config",
]
