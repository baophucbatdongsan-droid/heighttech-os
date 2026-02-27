# apps/api/v1/guards.py
from __future__ import annotations

from typing import List, Optional, Set

from django.core.exceptions import PermissionDenied

from apps.core.tenant_context import get_current_tenant_id
from apps.core.permissions import is_founder  # founder = role trong Membership
from apps.accounts.models import Membership
from apps.companies.models import Company
from apps.shops.models import Shop, ShopMember


# =====================================================
# INTERNAL HELPERS
# =====================================================

def _is_authed(user) -> bool:
    return bool(getattr(user, "is_authenticated", False))


def _is_all_access(user) -> bool:
    # founder/superuser => ALL access (nhưng vẫn bị chặn theo tenant nếu request set tenant context)
    return bool(getattr(user, "is_superuser", False)) or is_founder(user)


def _has_field(model_cls, field_name: str) -> bool:
    try:
        return any(f.name == field_name for f in model_cls._meta.get_fields())
    except Exception:
        return False


def _filter_tenant(qs, tid: Optional[int]):
    """
    Giữ data trong tenant hiện tại nếu model có tenant/tenant_id.
    """
    if not tid:
        return qs
    if _has_field(qs.model, "tenant_id"):
        return qs.filter(tenant_id=tid)
    if _has_field(qs.model, "tenant"):
        return qs.filter(tenant_id=tid)
    return qs


def _mgr(model_cls):
    """
    Ưu tiên objects_all (soft-delete friendly), fallback objects.
    """
    return getattr(model_cls, "objects_all", model_cls.objects)


# =====================================================
# SCOPE RAW RESOLVERS (NO RECURSION)
# =====================================================

def _membership_company_ids(user, tid: Optional[int]) -> Set[int]:
    """
    Company scope lấy từ Membership (company membership).
    """
    qs = Membership.objects.filter(user=user, is_active=True)
    if tid:
        qs = qs.filter(company__tenant_id=tid)
    return set(qs.values_list("company_id", flat=True))


def _shopmember_shop_ids(user, tid: Optional[int]) -> Set[int]:
    """
    Shop scope lấy trực tiếp từ ShopMember.
    Dùng objects_all nếu có để tránh mất record do soft-delete/custom manager.
    """
    sm = _mgr(ShopMember).filter(user=user, is_active=True)
    sm = _filter_tenant(sm, tid)
    return set(sm.values_list("shop_id", flat=True))


def _shopmember_company_ids(user, tid: Optional[int]) -> Set[int]:
    """
    Company scope suy ra từ ShopMember -> shop.brand.company.
    Dùng objects_all nếu có để tránh mất record do soft-delete/custom manager.
    """
    sm = _mgr(ShopMember).filter(user=user, is_active=True)
    sm = _filter_tenant(sm, tid)
    return set(sm.values_list("shop__brand__company_id", flat=True).distinct())


# =====================================================
# SCOPE RESOLVERS
# =====================================================

def get_scope_company_ids(user) -> List[int]:
    """
    Return list company_ids user được phép truy cập trong tenant hiện tại.

    QUY ƯỚC:
    - superuser/founder: return []  (meaning ALL within tenant)
    - user thường: union(Membership.company_id, ShopMember -> shop.brand.company_id)
    """
    if not _is_authed(user):
        return []

    if _is_all_access(user):
        return []  # ALL within tenant

    tid = get_current_tenant_id()

    company_ids = _membership_company_ids(user, tid)
    company_ids |= _shopmember_company_ids(user, tid)

    return list(company_ids)


def get_scope_shop_ids(user) -> List[int]:
    """
    Return list shop_ids user được phép truy cập trong tenant hiện tại.

    QUY ƯỚC:
    - superuser/founder: return []  (meaning ALL shops in tenant)
    - user thường:
        - ShopMember -> shop cụ thể
        - Membership company -> toàn bộ shops thuộc companies đó
    """
    if not _is_authed(user):
        return []

    if _is_all_access(user):
        return []  # ALL within tenant

    tid = get_current_tenant_id()

    # 1) Direct shop memberships
    shop_ids: Set[int] = _shopmember_shop_ids(user, tid)

    # 2) Shops from company memberships (không gọi get_scope_company_ids để tránh vòng)
    company_ids = _membership_company_ids(user, tid)

    # Nếu bạn muốn: user được vào 1 shop thì auto mở cả company:
    # company_ids |= _shopmember_company_ids(user, tid)

    if company_ids:
        shops_qs = _mgr(Shop).all()
        shops_qs = _filter_tenant(shops_qs, tid)
        shop_ids |= set(
            shops_qs.filter(brand__company_id__in=list(company_ids)).values_list("id", flat=True)
        )

    return list(shop_ids)


# =====================================================
# QUERYSET FILTERS
# =====================================================

def filter_shops_queryset_for_user(user, qs):
    """
    Apply shop scope onto Shop queryset.
    - Founder/superuser: vẫn bị giữ trong tenant hiện tại (nếu có tenant context)
    """
    if not _is_authed(user):
        return qs.none()

    tid = get_current_tenant_id()

    if _is_all_access(user):
        return _filter_tenant(qs, tid)

    shop_ids = get_scope_shop_ids(user)
    if not shop_ids:
        return qs.none()

    qs = _filter_tenant(qs, tid)
    return qs.filter(id__in=shop_ids)


def filter_perf_queryset_for_user(user, qs):
    """
    Apply scope to MonthlyPerformance queryset (hoặc model có shop/shop_id).
    - Founder/superuser: vẫn bị giữ trong tenant hiện tại (nếu model có tenant)
    """
    if not _is_authed(user):
        return qs.none()

    tid = get_current_tenant_id()

    if _is_all_access(user):
        return _filter_tenant(qs, tid)

    shop_ids = get_scope_shop_ids(user)
    if not shop_ids:
        return qs.none()

    qs = _filter_tenant(qs, tid)

    if _has_field(qs.model, "shop_id"):
        return qs.filter(shop_id__in=shop_ids)
    return qs.filter(shop__id__in=shop_ids)


# =====================================================
# OBJECT-LEVEL GUARDS
# =====================================================

def ensure_can_access_shop(user, shop: Shop) -> None:
    """
    Double-check object-level (chống leak khi ai đó truyền shop_id bậy).
    """
    if not _is_authed(user):
        raise PermissionDenied("Bạn không có quyền truy cập")

    tid = get_current_tenant_id()
    if tid and getattr(shop, "tenant_id", None) and int(shop.tenant_id) != int(tid):
        raise PermissionDenied("Shop không thuộc tenant hiện tại")

    if _is_all_access(user):
        return

    shop_ids = set(get_scope_shop_ids(user))
    if shop.id not in shop_ids:
        raise PermissionDenied("Shop nằm ngoài phạm vi được phép")


# =====================================================
# COMPANY HEADER GUARD (X-Company-Id)
# =====================================================

def resolve_company_id_for_request(user, company_id_raw: Optional[str]) -> Optional[int]:
    """
    - company_id_raw rỗng => None
    - Founder/superuser: cho chọn company trong tenant hiện tại
    - User thường: company_id phải nằm trong allowed_company_ids
    """
    s = (company_id_raw or "").strip()
    if not s:
        return None

    try:
        cid = int(s)
    except Exception:
        return None

    tid = get_current_tenant_id()

    # Validate company thuộc tenant hiện tại
    c_qs = Company.objects.all()
    if tid:
        c_qs = c_qs.filter(tenant_id=tid)
    if not c_qs.filter(id=cid).exists():
        raise PermissionDenied("Công ty không thuộc tenant hiện tại")

    if _is_all_access(user):
        return cid

    allowed = set(get_scope_company_ids(user))
    if cid in allowed:
        return cid

    raise PermissionDenied("Công ty nằm ngoài phạm vi được phép")