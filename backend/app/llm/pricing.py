"""按厂商分表的成本估算。

各家对 usage 的口径不一样，所以计价规则也必须按厂商写，不能合并成一个公式：

- Anthropic：``input_tokens`` **不含**缓存命中的部分，缓存读单独给 0.1 倍、缓存写 1.25 倍
- OpenAI：``prompt_tokens`` **已经包含**缓存命中的部分，``cached_tokens`` 只是其中的子集

把两家混在一起算，成本看板就会算错，而且错得还很安静。
"""

import logging
from dataclasses import dataclass

from app.llm.base import Usage

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ModelPrice:
    """美元 / 百万 token。"""

    input_per_mtok: float
    output_per_mtok: float
    # 缓存命中的 token 按输入价的这个倍率计费
    cache_read_multiplier: float = 1.0
    # 缓存写入的倍率。OpenAI 不单独收缓存写入费，保持 1.0
    cache_write_multiplier: float = 1.0


def _anthropic_price(input_per_mtok: float, output_per_mtok: float) -> ModelPrice:
    """Anthropic 统一按缓存读 0.1 倍、缓存写 1.25 倍计价。"""
    return ModelPrice(
        input_per_mtok,
        output_per_mtok,
        cache_read_multiplier=0.1,
        cache_write_multiplier=1.25,
    )


ANTHROPIC_PRICES: dict[str, ModelPrice] = {
    "claude-opus-5": _anthropic_price(5.00, 25.00),
    "claude-sonnet-5": _anthropic_price(2.00, 10.00),
    "claude-haiku-4-5": _anthropic_price(1.00, 5.00),
}

# OpenAI 不单独收缓存写入费，只对命中部分给 0.1 倍
OPENAI_PRICES: dict[str, ModelPrice] = {
    "gpt-4o": ModelPrice(2.50, 10.00, cache_read_multiplier=0.1),
    "gpt-4o-mini": ModelPrice(0.15, 0.60, cache_read_multiplier=0.1),
}

PRICES: dict[str, dict[str, ModelPrice]] = {
    "anthropic": ANTHROPIC_PRICES,
    "openai": OPENAI_PRICES,
}


def estimate_cost(vendor: str, model: str, usage: Usage) -> float:
    """估算单次调用费用（美元）。未知模型返回 0 并告警，不影响主流程。"""
    price = PRICES.get(vendor, {}).get(model)
    if price is None:
        logger.warning("价格表里没有 %s / %s，成本记为 0；请更新 app/llm/pricing.py", vendor, model)
        return 0.0

    if vendor == "openai":
        # prompt_tokens 已含缓存命中，要先减出来再单独按 0.1 倍计价
        cached = min(usage.cache_read_tokens, usage.input_tokens)
        uncached = usage.input_tokens - cached
        input_cost = (
            uncached + cached * price.cache_read_multiplier
        ) * price.input_per_mtok
    else:
        input_cost = (
            usage.input_tokens
            + usage.cache_read_tokens * price.cache_read_multiplier
            + usage.cache_write_tokens * price.cache_write_multiplier
        ) * price.input_per_mtok

    return (input_cost + usage.output_tokens * price.output_per_mtok) / 1_000_000
