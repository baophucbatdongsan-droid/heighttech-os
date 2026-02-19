# apps/core/permissions.py
from __future__ import annotations

from typing import List, Set, Tuple, Optional

from django.core.exceptions import PermissionDenied

from apps.core.tenant_context import get_current_tenant

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


# =====================================================
# SAFE CHECKS
# =====================================================

def _is_authenticated(user) -> bool:
    return bool(getattr(user, "is_authenticated", False))


def _current_tenant_id():
    t = get_current_tenant()
    return getattr(t, "id", None)


# =====================================================
# COMPANY MEMBERSHIP HELPERS (accounts.Membership)
# =====================================================

def get_user_memberships(user):
    if not _is_authenticated(user):
        return []
    if not hasattr(user, "memberships"):
        return []

    tenant_id = _current_tenant_id()

    qs = user.memberships.filter(is_active=True)

    # Nếu model Membership sau này có tenant_id thì tự filter
    if tenant_id and hasattr(qs.model, "tenant_id"):
        qs = qs.filter(tenant_id=tenant_id)

    return qs


def get_user_roles(user) -> Set[str]:
    if not _is_authenticated(user):
        return set()
    return set(get_user_memberships(user).values_list("role", flat=True))


def get_user_company_ids(user) -> List[int]:
    if not _is_authenticated(user):
        return []
    return list(get_user_memberships(user).values_list("company_id", flat=True))


# =====================================================
# SHOP MEMBERSHIP HELPERS (shops.ShopMember)
# =====================================================

def get_user_shop_memberships(user):
    if not _is_authenticated(user):
        return []
    if not hasattr(user, "shop_memberships"):
        return []

    tenant_id = _current_tenant_id()

    qs = user.shop_memberships.filter(is_active=True)

    # Multi-tenant filter nếu model có tenant
    if tenant_id and hasattr(qs.model, "tenant_id"):
        qs = qs.filter(tenant_id=tenant_id)

    return qs


def get_user_shop_ids(user) -> List[int]:
    if not _is_authenticated(user):
        return []
    return list(get_user_shop_memberships(user).values_list("shop_id", flat=True))


def get_user_company_ids_from_shops(user) -> List[int]:
    if not _is_authenticated(user):
        return []

    qs = get_user_shop_memberships(user)
    return list(qs.values_list("shop__brand__company_id", flat=True).distinct())


# =====================================================
# ROLE CHECKERS
# =====================================================

def is_founder(user) -> bool:
    if not _is_authenticated(user):
        return False
    if getattr(user, "is_superuser", False):
        return True
    return ROLE_FOUNDER in get_user_roles(user)


def is_head(user) -> bool:
    return ROLE_HEAD in get_user_roles(user)


def is_account(user) -> bool:
    return ROLE_ACCOUNT in get_user_roles(user)


def is_sale(user) -> bool:
    return ROLE_SALE in get_user_roles(user)


def is_operator(user) -> bool:
    return ROLE_OPERATOR in get_user_roles(user)


def is_client(user) -> bool:
    """
    Client = có shop membership nhưng không có company membership.
    """
    if not _is_authenticated(user):
        return False

    try:
        if get_user_shop_memberships(user).exists() and not get_user_memberships(user).exists():
            return True
    except Exception:
        pass

    return False


# =====================================================
# ROLE RESOLVER (UI/Dashboard)
# =====================================================

def resolve_user_role(user) -> str:
    """
    Priority:
      superuser/founder > head > account > sale > operator > client > none
    """
    if not _is_authenticated(user):
        return ROLE_NONE

    if getattr(user, "is_superuser", False) or is_founder(user):
        return ROLE_FOUNDER

    if is_head(user):
        return ROLE_HEAD

    if is_account(user):
        return ROLE_ACCOUNT

    if is_sale(user):
        return ROLE_SALE

    if is_operator(user):
        return ROLE_OPERATOR

    if is_client(user):
        return ROLE_CLIENT

    return ROLE_NONE


# =====================================================
# COMPANY SCOPE RESOLVER (X-Company-Id)
# =====================================================

def resolve_company_scope_for_request(request) -> Tuple[Optional[int], List[int]]:
    """
    Trả về:
      (selected_company_id, allowed_company_ids)

    Rule:
    - superuser/founder: allowed = all Company trong tenant hiện tại
      selected lấy từ header X-Company-Id (nếu có và hợp lệ), nếu không có => None
    - user thường: allowed = company_ids từ Membership (is_active=True)
      selected bắt buộc phải nằm trong allowed, nếu header có mà ngoài scope => PermissionDenied
    """
    user = getattr(request, "user", None)
    if not _is_authenticated(user):
        return None, []

    tenant = get_current_tenant()
    if tenant is None:
        # an toàn: chưa set tenant thì coi như không scope được
        return None, []

    # đọc header
    raw = (request.headers.get("X-Company-Id") or request.META.get("HTTP_X_COMPANY_ID") or "").strip()
    selected: Optional[int] = None
    if raw:
        try:
            selected = int(raw)
        except Exception:
            raise PermissionDenied("Bad X-Company-Id")

    # allowed list
    if getattr(user, "is_superuser", False) or is_founder(user):
        from apps.companies.models import Company
        allowed = list(Company.objects.filter(tenant=tenant).values_list("id", flat=True))
    else:
        allowed = list(get_user_company_ids(user) or [])

    # validate selected in allowed (nếu có selected)
    if selected is not None:
        if selected not in set(allowed):
            raise PermissionDenied("Forbidden: company out of scope")

    return selected, allowed