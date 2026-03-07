# apps/work/permissions.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Set, Tuple

from django.db.models import Q
from django.http import Http404

from apps.api.v1.guards import get_scope_company_ids, get_scope_shop_ids
from apps.core.permissions import resolve_user_role, ROLE_FOUNDER, ROLE_CLIENT
from apps.projects.models import Project
from apps.work.models import WorkItem


@dataclass(frozen=True)
class ScopeCtx:
    tenant_id: Optional[int]
    role: str
    is_superuser: bool
    allowed_company_ids: Set[int]
    allowed_shop_ids: Set[int]


def _tenant_id_from_request(request) -> Optional[int]:
    tid = getattr(request, "tenant_id", None)
    try:
        return int(tid) if tid is not None else None
    except Exception:
        return None


def build_scope_ctx(request) -> ScopeCtx:
    user = getattr(request, "user", None)
    role = resolve_user_role(user)
    is_superuser = bool(getattr(user, "is_superuser", False))
    tenant_id = _tenant_id_from_request(request)

    allowed_company_ids = set(get_scope_company_ids(user) or [])
    allowed_shop_ids = set(get_scope_shop_ids(user) or [])

    return ScopeCtx(
        tenant_id=tenant_id,
        role=role,
        is_superuser=is_superuser,
        allowed_company_ids=allowed_company_ids,
        allowed_shop_ids=allowed_shop_ids,
    )


def is_founder_like(ctx: ScopeCtx) -> bool:
    return ctx.is_superuser or (ctx.role == ROLE_FOUNDER)


def is_client_role(ctx: ScopeCtx) -> bool:
    return ctx.role == ROLE_CLIENT


def scope_workitem_queryset(request, qs):
    """
    ✅ Source-of-truth scoping.
    - Always filter tenant first (if tenant_id available)
    - Founder/superuser: full access within tenant
    - Client: only non-internal + only within shop/channel/booking scope (and/or company scope if any)
    - Staff: company scope + shop-derived scope (channel/booking)
    """
    ctx = build_scope_ctx(request)

    if ctx.tenant_id:
        qs = qs.filter(tenant_id=int(ctx.tenant_id))

    if is_founder_like(ctx):
        return qs

    # client never sees internal
    if is_client_role(ctx):
        qs = qs.filter(is_internal=False)

    q_company = Q()
    if ctx.allowed_company_ids:
        q_company = Q(company_id__in=list(ctx.allowed_company_ids))

    q_shop_derived = Q()
    if ctx.allowed_shop_ids:
        q_shop_derived |= Q(target_type="shop", target_id__in=list(ctx.allowed_shop_ids))

        # channel -> shop
        try:
            from apps.channels.models import ChannelShopLink

            channel_ids = set(
                ChannelShopLink.objects_all.filter(shop_id__in=list(ctx.allowed_shop_ids))
                .values_list("channel_id", flat=True)
                .distinct()
            )
            if channel_ids:
                q_shop_derived |= Q(target_type="channel", target_id__in=list(channel_ids))
        except Exception:
            pass

        # booking -> shop
        try:
            from apps.booking.models import Booking

            booking_ids = set(
                Booking.objects_all.filter(shop_id__in=list(ctx.allowed_shop_ids))
                .values_list("id", flat=True)
                .distinct()
            )
            if booking_ids:
                q_shop_derived |= Q(target_type="booking", target_id__in=list(booking_ids))
        except Exception:
            pass

    combined = q_company | q_shop_derived
    if combined.children:
        return qs.filter(combined)

    return qs.none()


def require_company_if_no_resolve_fields(payload: Dict[str, Any]) -> Tuple[bool, str]:
    """
    ✅ Anti-rác for CREATE:
    phải có company_id OR project_id OR (target_type & target_id)
    """
    company_id = payload.get("company_id")
    project_id = payload.get("project_id")
    target_type = (payload.get("target_type") or "").strip()
    target_id = payload.get("target_id")

    if company_id:
        return True, ""
    if project_id:
        return True, ""
    if target_type and target_id:
        return True, ""
    return False, "company_id là bắt buộc nếu không có project_id hoặc target (target_type/target_id)"


def validate_write_scope(request, payload: Dict[str, Any]) -> Tuple[bool, str]:
    """
    ✅ Write-scope validation (CREATE/PATCH).
    - Founder/superuser: allow
    - Client: deny
    - Staff: company/project/target phải nằm trong scope
    """
    ctx = build_scope_ctx(request)

    if is_founder_like(ctx):
        return True, ""

    if is_client_role(ctx):
        return False, "Khách hàng không được thao tác ghi công việc"

    company_id = payload.get("company_id")
    project_id = payload.get("project_id")
    target_type = (payload.get("target_type") or "").strip()
    target_id = payload.get("target_id")

    if company_id is not None:
        try:
            cid = int(company_id)
        except Exception:
            return False, "Bad company_id"
        if ctx.allowed_company_ids and cid not in ctx.allowed_company_ids:
            return False, "Forbidden: company out of scope"

    if project_id is not None:
        try:
            pid = int(project_id)
        except Exception:
            return False, "Bad project_id"

        p_qs = Project.objects_all.all()
        if ctx.tenant_id:
            p_qs = p_qs.filter(tenant_id=int(ctx.tenant_id))

        p = p_qs.filter(id=pid).only("id", "company_id").first()
        if not p:
            return False, "Forbidden: project not found in tenant"
        if ctx.allowed_company_ids and p.company_id not in ctx.allowed_company_ids:
            return False, "Forbidden: project out of company scope"

    if target_id is not None:
        try:
            tid = int(target_id)
        except Exception:
            return False, "Bad target_id"

        if target_type == "shop":
            if ctx.allowed_shop_ids and tid not in ctx.allowed_shop_ids:
                return False, "Forbidden: shop target out of scope"

        elif target_type == "channel":
            try:
                from apps.channels.models import ChannelShopLink

                ok = ChannelShopLink.objects_all.filter(
                    shop_id__in=list(ctx.allowed_shop_ids),
                    channel_id=tid,
                ).exists()
                if ctx.allowed_shop_ids and not ok:
                    return False, "Forbidden: channel target out of scope"
            except Exception:
                if ctx.allowed_shop_ids:
                    return False, "Forbidden: channel target out of scope"

        elif target_type == "booking":
            try:
                from apps.booking.models import Booking

                ok = Booking.objects_all.filter(id=tid, shop_id__in=list(ctx.allowed_shop_ids)).exists()
                if ctx.allowed_shop_ids and not ok:
                    return False, "Forbidden: booking target out of scope"
            except Exception:
                if ctx.allowed_shop_ids:
                    return False, "Forbidden: booking target out of scope"

    return True, ""


def get_scoped_workitem_or_404(request, pk: int) -> WorkItem:
    """
    ✅ Scoped fetch. Out-of-scope => 404 (không leak existence).
    """
    qs = scope_workitem_queryset(request, WorkItem.objects_all.all())
    obj = qs.filter(pk=pk).first()
    if not obj:
        raise Http404
    return obj