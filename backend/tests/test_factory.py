"""验证「改 .env 就能切模型」这条约定真的成立。"""

import pytest

from app.config import Settings
from app.llm.anthropic_provider import AnthropicLLM
from app.llm.errors import LLMNotConfiguredError
from app.llm.factory import VENDORS, build_llm_client
from app.llm.openai_provider import OpenAILLM


def test_default_vendor_is_anthropic():
    llm = build_llm_client(Settings(_env_file=None))
    assert isinstance(llm, AnthropicLLM)
    assert llm.model == "claude-opus-5"


def test_switching_vendor_and_model_only_needs_env():
    settings = Settings(
        _env_file=None,
        llm_vendor="openai",
        llm_model="gpt-4o",
        llm_max_tokens=4000,
        openai_api_key="sk-test",
        openai_base_url="https://example.com/v1",
    )
    llm = build_llm_client(settings)

    assert isinstance(llm, OpenAILLM)
    assert llm.model == "gpt-4o"
    assert llm.max_tokens == 4000
    assert str(llm.client.base_url).startswith("https://example.com/v1")


def test_legacy_max_tokens_flows_from_env():
    llm = build_llm_client(
        Settings(_env_file=None, llm_vendor="openai", llm_model="gpt-4o",
                 openai_api_key="sk-test", openai_legacy_max_tokens=True)
    )
    assert llm.legacy_max_tokens is True


def test_unknown_vendor_fails_fast_with_options():
    with pytest.raises(LLMNotConfiguredError, match="openai"):
        build_llm_client(Settings(_env_file=None, llm_vendor="Openai"))


def test_openai_without_api_key_explains_what_to_set():
    with pytest.raises(LLMNotConfiguredError, match="OPENAI_API_KEY"):
        build_llm_client(Settings(_env_file=None, llm_vendor="openai"))


def test_every_vendor_has_an_entry():
    for vendor in VENDORS:
        settings = Settings(
            _env_file=None,
            llm_vendor=vendor,
            anthropic_api_key="x",
            openai_api_key="sk-test",
        )
        assert build_llm_client(settings) is not None
