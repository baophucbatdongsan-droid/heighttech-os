from __future__ import annotations

from datetime import date
from django.core.cache import cache
from django.utils import timezone


TTL_SECONDS = 2 * 24 * 3600  # giữ key 2 ngày


def _key(tenant_id: int, d: date, metric: str) -> str:
    return f"usage:{tenant_id}:{d.isoformat()}:{metric}"


def incr_usage(tenant_id: int | None, metric: str, amount: int = 1) -> None:
    if not tenant_id:
        return

    d = timezone.localdate()
    key = _key(int(tenant_id), d, metric)

    cache.add(key, 0, timeout=TTL_SECONDS)
    try:
        cache.incr(key, amount)
    except ValueError:
        cache.set(key, amount, timeout=TTL_SECONDS)
    except Exception:
        # fail-open
        return


def get_usage_value(tenant_id: int, d: date, metric: str) -> int:
    try:
        return int(cache.get(_key(tenant_id, d, metric)) or 0)
    except Exception:
        return 0


def delete_usage_key(tenant_id: int, d: date, metric: str) -> None:
    try:
        cache.delete(_key(int(tenant_id), d, metric))
    except Exception:
        return


def reset_usage_for_day(tenant_id: int, d: date, metric: str) -> None:
    """
    Reset usage của 1 metric trong 1 ngày.
    Hiện tại metering đang dùng cache key theo ngày,
    nên reset = xoá key.
    """
    delete_usage_key(tenant_id, d, metric)