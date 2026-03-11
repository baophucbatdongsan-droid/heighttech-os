from __future__ import annotations

from typing import List, Set, Tuple, Optional

from django.core.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission

from apps.core.tenant_context import get_current_tenant
from apps.accounts.models import Membership
from apps.shops.models import ShopMember


# =====================================================
# ROLE CONSTANTS
# =====================================================
ROLE_FOUNDER = "founder"
ROLE_HEAD = "head"
ROLE_ACCOUNT = "account"
ROLE_SALE = "sale"
ROLE_OPERATOR = "operator"
ROLE_CLIENT = "client"
ROLE_NONE = "none"

# ✅ thêm role đang dùng thật trong Membership
ROLE_LEADER_OPERATION = "leader_operation"
ROLE_LEADER_CHANNEL = "leader_channel"
ROLE_LEADER_BOOKING = "leader_booking"
ROLE_EDITOR = "editor"


# =====================================================
# ABILITY CONSTANTS
# =====================================================
VIEW_DASHBOARD = "view_dashboard"
VIEW_FOUNDER = "view_founder"

VIEW_API_DASHBOARD = "api:view_dashboard"
VIEW_API_FOUNDER = "api:view_founder"


# =====================================================
# ROLE → ABILITY POLICY
# =====================================================
ROLE_TO_ABILITIES = {
    ROLE_FOUNDER: {
        VIEW_DASHBOARD,
        VIEW_FOUNDER,
        VIEW_API_DASHBOARD,
        VIEW_API_FOUNDER,
    },

    ROLE_HEAD: {
        VIEW_DASHBOARD,
        VIEW_API_DASHBOARD,
    },

    ROLE_ACCOUNT: {
        VIEW_DASHBOARD,
        VIEW_API_DASHBOARD,
    },

    ROLE_SALE: {
        VIEW_DASHBOARD,
        VIEW_API_DASHBOARD,
    },

    ROLE_OPERATOR: {
        VIEW_DASHBOARD,
        VIEW_API_DASHBOARD,
    },

    ROLE_CLIENT: {
        VIEW_DASHBOARD,
        VIEW_API_DASHBOARD,
    },

    # ✅ leader/editor cũng vào được dashboard/work
    ROLE_LEADER_OPERATION: {
        VIEW_DASHBOARD,
        VIEW_API_DASHBOARD,
    },

    ROLE_LEADER_CHANNEL: {
        VIEW_DASHBOARD,
        VIEW_API_DASHBOARD,
    },

    ROLE_LEADER_BOOKING: {
        VIEW_DASHBOARD,
        VIEW_API_DASHBOARD,
    },

    ROLE_EDITOR: {
        VIEW_DASHBOARD,
        VIEW_API_DASHBOARD,
    },
}


# =====================================================
# SAFE CHECKS
# =====================================================
def _is_authenticated(user) -> bool:
    return bool(getattr(user, "is_authenticated", False))


def _current_tenant_id() -> Optional[int]:
    t = get_current_tenant()
    return getattr(t, "id", None)


def _mgr(model_cls):
    """
    Ưu tiên objects_all (soft-delete friendly), fallback objects.
    """
    return getattr(model_cls, "objects_all", model_cls.objects)


# =====================================================
# MEMBERSHIP HELPERS (accounts.Membership)
# =====================================================
def get_user_memberships(user):
    """
    Membership company-level.
    """
    if not _is_authenticated(user):
        return Membership.objects.none()

    tenant_id = _current_tenant_id()
    qs = Membership.objects.filter(user=user, is_active=True)

    if tenant_id and hasattr(qs.model, "tenant_id"):
        qs = qs.filter(tenant_id=tenant_id)

    return qs


def get_user_roles(user) -> Set[str]:
    if not _is_authenticated(user):
        return set()

    roles = set(get_user_memberships(user).values_list("role", flat=True))
    return {str(r).strip().lower() for r in roles if r}


# =====================================================
# SHOPMEMBER HELPERS (shops.ShopMember)
# =====================================================
def get_user_shop_memberships(user):
    if not _is_authenticated(user):
        return _mgr(ShopMember).none()

    tenant_id = _current_tenant_id()
    qs = _mgr(ShopMember).filter(user=user, is_active=True)

    if tenant_id and hasattr(qs.model, "tenant_id"):
        qs = qs.filter(tenant_id=tenant_id)

    return qs


def user_has_any_shop_membership(user) -> bool:
    try:
        return get_user_shop_memberships(user).exists()
    except Exception:
        return False


# =====================================================
# ROLE CHECKERS
# =====================================================
def is_founder(user) -> bool:
    if not _is_authenticated(user):
        return False
    if getattr(user, "is_superuser", False):
        return True
    return ROLE_FOUNDER in get_user_roles(user)


def is_client(user) -> bool:
    if not _is_authenticated(user):
        return False
    return user_has_any_shop_membership(user)


# =====================================================
# ROLE RESOLVER (UI/API)
# =====================================================
def resolve_user_role(user) -> str:
    if not _is_authenticated(user):
        return ROLE_NONE

    if getattr(user, "is_superuser", False) or is_founder(user):
        return ROLE_FOUNDER

    roles = get_user_roles(user)

    if ROLE_HEAD in roles:
        return ROLE_HEAD

    if ROLE_LEADER_OPERATION in roles:
        return ROLE_LEADER_OPERATION
    if ROLE_LEADER_CHANNEL in roles:
        return ROLE_LEADER_CHANNEL
    if ROLE_LEADER_BOOKING in roles:
        return ROLE_LEADER_BOOKING

    if ROLE_ACCOUNT in roles:
        return ROLE_ACCOUNT
    if ROLE_SALE in roles:
        return ROLE_SALE
    if ROLE_EDITOR in roles:
        return ROLE_EDITOR
    if ROLE_OPERATOR in roles:
        return ROLE_OPERATOR

    if is_client(user):
        return ROLE_CLIENT

    return ROLE_NONE


def role_has_ability(role: str, ability: str) -> bool:
    role = (role or ROLE_NONE).lower()
    return ability in ROLE_TO_ABILITIES.get(role, set())


class AbilityPermission(BasePermission):
    """
    View cần set: required_ability = "api:view_dashboard" ...
    """
    message = "Bạn không có quyền truy cập chức năng này"

    def has_permission(self, request, view):
        required = getattr(view, "required_ability", None)
        if not required:
            return True
        role = resolve_user_role(getattr(request, "user", None))
        return role_has_ability(role, required)


class FounderOnlyPermission(BasePermission):
    message = "Chỉ Founder mới được truy cập"

    def has_permission(self, request, view):
        u = getattr(request, "user", None)
        if not getattr(u, "is_authenticated", False):
            return False
        return bool(getattr(u, "is_superuser", False) or is_founder(u))


# =====================================================
# COMPANY SCOPE RESOLVER (X-Company-Id)
# =====================================================
def resolve_company_scope_for_request(request) -> Tuple[Optional[int], List[int]]:
    user = getattr(request, "user", None)
    if not _is_authenticated(user):
        return None, []

    tenant = get_current_tenant()
    if tenant is None:
        return None, []

    raw = (request.headers.get("X-Company-Id") or request.META.get("HTTP_X_COMPANY_ID") or "").strip()
    selected: Optional[int] = None
    if raw:
        try:
            selected = int(raw)
        except Exception:
            raise PermissionDenied("Bad X-Company-Id")

    if getattr(user, "is_superuser", False) or is_founder(user):
        from apps.companies.models import Company
        allowed = list(_mgr(Company).filter(tenant=tenant).values_list("id", flat=True))
    else:
        allowed = list(get_user_memberships(user).values_list("company_id", flat=True))

    if selected is not None and selected not in set(allowed):
        raise PermissionDenied("Forbidden: company out of scope")

    return selected, allowed