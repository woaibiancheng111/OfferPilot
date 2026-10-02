from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置，从环境变量或 .env 文件读取。"""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "OfferPilot"
    database_url: str = "postgresql+asyncpg://offerpilot:offerpilot@localhost:55432/offerpilot"

    # LLM。切换厂商只改 .env 里的 LLM_VENDOR / LLM_MODEL，代码不用动
    llm_vendor: str = "anthropic"
    llm_model: str = "claude-opus-5"
    llm_max_tokens: int = 16000
    # 服务端拒答回退（Claude 官方端点可用；接第三方兼容端点时关掉）
    llm_enable_fallbacks: bool = True
    # 顶层自动 prompt 缓存
    llm_enable_prompt_cache: bool = True

    # anthropic 凭证。留空时由 SDK 按默认顺序查找（环境变量、ant 登录的 profile 等）
    anthropic_api_key: str | None = None
    anthropic_base_url: str | None = None

    # openai 凭证。切到 openai 时必填；base_url 用于接第三方中转站
    openai_api_key: str | None = None
    openai_base_url: str | None = None
    # 部分第三方中转站只认已废弃的 max_tokens，官方端点保持 false
    openai_legacy_max_tokens: bool = False

    # Agent
    agent_max_steps: int = 8
    agent_tool_timeout_s: float = 15.0
    agent_max_tool_result_chars: int = 8000

    # Tracing
    trace_flush_interval_s: float = 1.0
    trace_batch_size: int = 50
    trace_max_payload_chars: int = 20000


@lru_cache
def get_settings() -> Settings:
    return Settings()
