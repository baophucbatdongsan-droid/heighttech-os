# apps/core/workspace.py
SESSION_ACTIVE_SHOP_ID = "active_shop_id"
SESSION_ACTIVE_TENANT_ID = "active_tenant_id"

def get_active_shop_id(request):
    try:
        v = request.session.get(SESSION_ACTIVE_SHOP_ID)
        return int(v) if v else None
    except Exception:
        return None

def set_active_shop(request, shop_id: int, tenant_id: int | None = None):
    request.session[SESSION_ACTIVE_SHOP_ID] = int(shop_id)
    if tenant_id is not None:
        request.session[SESSION_ACTIVE_TENANT_ID] = int(tenant_id)
    request.session.modified = True