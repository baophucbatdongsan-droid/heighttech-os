# apps/core/scoping.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional, TypeVar

from django.db import models

from apps.core.tenant_context import get_current_tenant


def _has_field(model, field_name: str) -> bool:
    try:
        return any(f.name == field_name for f in model._meta.get_fields())
    except Exception:
        return False


def _user_in_group(user, name: str) -> bool:
    try:
        return user.groups.filter(name=name).exists()
    except Exception:
        return False


def resolve_role(user) -> str:
    """
    Role chuẩn hoá (fallback).
    Nếu bạn có core.permissions.resolve_user_role thì chỗ gọi có thể override.
    """
    if getattr(user, "is_superuser", False):
        return "founder"

    # group alias tuỳ bạn đặt
    if _user_in_group(user, "founder"):
        return "founder"
    if _user_in_group(user, "head"):
        return "head"
    if _user_in_group(user, "account"):
        return "account"
    if _user_in_group(user, "operator"):
        return "operator"
    if _user_in_group(user, "client"):
        return "client"

    return "none"


def get_shop_ids_for_user(user) -> List[int]:
    """
    Chuẩn: lấy shop ids từ ShopMember (fallback an toàn).
    """
    try:
        from apps.shops.models import ShopMember  # local import
        return list(
            ShopMember.objects.filter(user=user, is_active=True).values_list("shop_id", flat=True)
        )
    except Exception:
        return []


def get_company_ids_for_user(user) -> List[int]:
    """
    Chuẩn: suy company_ids từ ShopMember -> shop -> brand -> company.
    """
    try:
        from apps.shops.models import ShopMember  # local import
        return list(
            ShopMember.objects.filter(user=user, is_active=True)
            .values_list("shop__brand__company_id", flat=True)
            .distinct()
        )
    except Exception:
        return []


def filter_monthly_performance_by_company_ids(qs, company_ids: Iterable[int]):
    """
    Support 2 schema:
    - shop-based: shop__brand__company_id
    - company-based: company_id
    """
    Model = qs.model
    company_ids = list(company_ids)

    if not company_ids:
        return qs.none()

    if _has_field(Model, "shop"):
        return qs.filter(shop__brand__company_id__in=company_ids)
    if _has_field(Model, "company"):
        return qs.filter(company_id__in=company_ids)

    return qs.none()


def filter_monthly_performance_by_shop_ids(qs, shop_ids: Iterable[int]):
    Model = qs.model
    shop_ids = list(shop_ids)

    if not shop_ids:
        return qs.none()

    if _has_field(Model, "shop"):
        return qs.filter(shop_id__in=shop_ids)

    # schema không có shop => không filter được theo shop
    return qs.none()


def company_name_key_for_monthly_performance(model) -> Optional[str]:
    """
    Key dùng cho values() group theo company name.
    """
    if _has_field(model, "shop"):
        return "shop__brand__company__name"
    if _has_field(model, "company"):
        return "company__name"
    return None


# ==========================================================
# OPTIONAL: Tenant scoping (dùng dần, không phá code hiện tại)
# ==========================================================

T = TypeVar("T", bound=models.Model)


class TenantScopedQuerySet(models.QuerySet[T]):
    """
    QuerySet auto-scope theo tenant hiện tại nếu model có field 'tenant'.
    Có thể bypass bằng .ignore_tenant()
    """

    _ignore_tenant: bool = False

    def ignore_tenant(self):
        clone = self._clone()
        clone._ignore_tenant = True
        return clone

    def _apply_tenant_scope(self):
        if self._ignore_tenant:
            return self
        if not _has_field(self.model, "tenant"):
            return self

        tenant = get_current_tenant()
        if tenant is None:
            # không có tenant trong context => trả none để tránh leak data
            return self.none()

        return self.filter(tenant_id=getattr(tenant, "id", None))

    def all(self):
        return super().all()._apply_tenant_scope()

    def filter(self, *args, **kwargs):
        return super().filter(*args, **kwargs)._apply_tenant_scope()

    def exclude(self, *args, **kwargs):
        return super().exclude(*args, **kwargs)._apply_tenant_scope()


class TenantScopedManager(models.Manager.from_queryset(TenantScopedQuerySet)):  # type: ignore[misc]
    """
    Manager mặc định dùng TenantScopedQuerySet.
    Nếu model không có tenant => behave như bình thường.
    """

    def ignore_tenant(self):
        return self.get_queryset().ignore_tenant()