# apps/core/tenant_quota.py
from __future__ import annotations

from dataclasses import dataclass

@dataclass(frozen=True)
class Quota:
    req_per_min: int


PLAN_QUOTAS = {
    "basic": Quota(req_per_min=300),
    "pro": Quota(req_per_min=1200),
    "enterprise": Quota(req_per_min=5000),
}


def get_tenant_quota(tenant) -> Quota:
    """
    tenant: object có .plan và optional .req_per_min_override
    """
    plan = (getattr(tenant, "plan", "") or "basic").lower().strip()
    q = PLAN_QUOTAS.get(plan, PLAN_QUOTAS["basic"])

    override = getattr(tenant, "req_per_min_override", None)
    if override:
        return Quota(req_per_min=int(override))
    return q


def has_feature(tenant, key: str, default: bool = True) -> bool:
    flags = getattr(tenant, "feature_flags", None) or {}
    # nếu key không tồn tại => default
    val = flags.get(key, default)
    return bool(val)