"""按配置构造 LLM 客户端。

业务代码只调 ``build_llm_client(settings)``，切换厂商和模型只需要改 .env：

    LLM_VENDOR=openai
    LLM_MODEL=gpt-4o
    OPENAI_API_KEY=sk-...

接第三家模型时，在这里加一个分支 + 一个 provider 模块即可，Agent 层和 API 层不用动。
"""

import anthropic
import openai

from app.config import Settings
from app.llm.anthropic_provider import AnthropicLLM
from app.llm.base import LLMClient
from app.llm.errors import LLMNotConfiguredError
from app.llm.openai_provider import OpenAILLM

VENDORS = ("anthropic", "openai")


def build_llm_client(settings: Settings) -> LLMClient:
    vendor = settings.llm_vendor
    if vendor == "anthropic":
        return _build_anthropic(settings)
    if vendor == "openai":
        return _build_openai(settings)
    raise LLMNotConfiguredError(
        f"未知的 LLM_VENDOR：{vendor!r}，可选值：{', '.join(VENDORS)}"
    )


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
