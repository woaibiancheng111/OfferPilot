"""按配置构造 LLM 客户端。

业务代码只调 ``build_llm_client(settings)``，切换厂商和模型只需要改 .env：

    LLM_VENDOR=openai
    LLM_MODEL=gpt-5
    OPENAI_API_KEY=sk-...

接第三家模型时，在这里加一个分支 + 一个 provider 模块即可，
Agent 层和 API 层不用动。

这里刻意不校验模型名、不查价目表：项目可能要接第三方中转，模型名和单价都不在
我们控制内，一张写死的表只会持续给出错误的数字。用什么模型由 ``.env`` 说了算。
"""

import logging

import anthropic
import openai

from app.config import Settings
from app.llm.anthropic_provider import AnthropicLLM
from app.llm.base import LLMClient
from app.llm.errors import LLMNotConfiguredError
from app.llm.openai_provider import OpenAILLM

logger = logging.getLogger(__name__)

VENDORS = ("anthropic", "openai")

__all__ = ["VENDORS", "build_llm_client", "describe_config"]


def build_llm_client(settings: Settings) -> LLMClient:
    vendor = settings.llm_vendor
    if vendor == "anthropic":
        client = _build_anthropic(settings)
    elif vendor == "openai":
        client = _build_openai(settings)
    else:
        raise LLMNotConfiguredError(
            f"未知的 LLM_VENDOR：{vendor!r}。可选值：{', '.join(VENDORS)}"
        )

    logger.info("模型：%s / %s", vendor, settings.llm_model)
    return client


def describe_config(settings: Settings) -> str:
    """给启动日志看的一行配置摘要。"""
    return f"{settings.llm_vendor} / {settings.llm_model}"


def _build_anthropic(settings: Settings) -> AnthropicLLM:
    # 凭证留空时交给 SDK 自己找（环境变量、ant 登录的 profile 等），
    # 保持和之前一致：不在启动时报错，等第一次真正调用时再给明确提示。
    client = anthropic.AsyncAnthropic(
        api_key=settings.anthropic_api_key, base_url=settings.anthropic_base_url
    )
    return AnthropicLLM(
        model=settings.llm_model,
        max_tokens=settings.llm_max_tokens,
        enable_fallbacks=settings.llm_enable_fallbacks,
        enable_prompt_cache=settings.llm_enable_prompt_cache,
        client=client,
    )


def _build_openai(settings: Settings) -> OpenAILLM:
    if not settings.openai_api_key:
        # OpenAI SDK 在构造时就会因为缺 key 抛一个很难懂的异常，这里提前给清楚的说法
        raise LLMNotConfiguredError("LLM_VENDOR=openai 时必须配置 OPENAI_API_KEY")
    client = openai.AsyncOpenAI(
        api_key=settings.openai_api_key, base_url=settings.openai_base_url
    )
    return OpenAILLM(
        model=settings.llm_model,
        max_tokens=settings.llm_max_tokens,
        enable_prompt_cache=settings.llm_enable_prompt_cache,
        legacy_max_tokens=settings.openai_legacy_max_tokens,
        client=client,
    )
