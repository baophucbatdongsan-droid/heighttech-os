# apps/core/context_processors.py
from __future__ import annotations

from apps.core.authz import get_actor_ctx

# đồng bộ key với dashboard workspace
SESSION_SHOP_ID = "active_shop_id"


def actor_context(request):
    ctx = get_actor_ctx(request)

    active_shop = None
    active_shop_id = None
    try:
        raw = request.session.get(SESSION_SHOP_ID)
        if raw:
            active_shop_id = int(raw)
    except Exception:
        active_shop_id = None

    if active_shop_id:
        try:
            from apps.shops.models import Shop
            # dùng _base_manager để không bị TenantManager làm rỗng nếu context chưa set
            active_shop = Shop._base_manager.filter(id=active_shop_id).only("id", "name", "tenant_id").first()
        except Exception:
            active_shop = None

    return {
        "actor": ctx,
        "actor_role": ctx.role,
        "actor_tenant_id": ctx.tenant_id,
        "active_shop_id": active_shop_id,
        "active_shop": active_shop,
        "me": getattr(request, "user", None),
    }