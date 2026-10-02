"""与厂商无关的错误类型。

各家 SDK 的异常（anthropic.AuthenticationError、openai.RateLimitError……）
只在 provider 层出现，并在那里翻译成这里的类型。API 层只 catch 这些中立异常，
这样以后接第三家模型时，不需要改任何业务代码和路由。
"""


class LLMError(RuntimeError):
    """所有模型调用错误的基类。"""


class LLMNotConfiguredError(LLMError):
    """没有可用的模型凭证，或者配置的厂商名不存在。"""


class LLMAuthenticationError(LLMError):
    """凭证无效。"""


class LLMRateLimitError(LLMError):
    """被模型服务商限流。"""


class LLMUpstreamError(LLMError):
    """模型服务端返回错误，或网络连不上。"""
