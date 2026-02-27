# apps/core/rate_limit.py
from __future__ import annotations

from dataclasses import dataclass
from django.core.cache import cache


@dataclass
class RateLimitConfig:
    window_seconds: int = 60


DEFAULT_CFG = RateLimitConfig()


def is_rate_limited(tenant_id: int | None, max_requests: int, cfg: RateLimitConfig = DEFAULT_CFG) -> bool:
    if not tenant_id:
        return False

    key = f"rl:tenant:{tenant_id}"
    cache.add(key, 0, timeout=cfg.window_seconds)

    try:
        val = cache.incr(key)
    except ValueError:
        cache.set(key, 1, timeout=cfg.window_seconds)
        val = 1
    except Exception:
        return False

    return int(val) > int(max_requests)