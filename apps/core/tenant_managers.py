# apps/core/tenant_managers.py
from __future__ import annotations

from typing import Optional, TypeVar

from django.db import models

from apps.core.tenant_context import get_current_tenant

T = TypeVar("T", bound=models.Model)


def _has_field(model_cls: type[models.Model], field_name: str) -> bool:
    try:
        return any(f.name == field_name for f in model_cls._meta.get_fields())
    except Exception:
        return False


class TenantQuerySet(models.QuerySet[T]):
    def for_tenant(self, tenant) -> "TenantQuerySet[T]":
        if tenant is None:
            return self.none()
        if _has_field(self.model, "tenant"):
            return self.filter(tenant=tenant)
        if _has_field(self.model, "tenant_id"):
            return self.filter(tenant_id=getattr(tenant, "id", None))
        return self

    def active(self) -> "TenantQuerySet[T]":
        # optional, nếu model có is_active
        if _has_field(self.model, "is_active"):
            return self.filter(is_active=True)
        return self

    def unscoped(self) -> "TenantQuerySet[T]":
        # marker (thực tế unscoped nằm ở Manager)
        return self


class TenantManager(models.Manager.from_queryset(TenantQuerySet)):  # type: ignore[misc]
    """
    Default manager: auto filter theo current tenant (contextvars).
    Nếu chưa có tenant trong context -> none() (an toàn chống leak).
    """

    def get_queryset(self) -> TenantQuerySet[T]:
        qs: TenantQuerySet[T] = super().get_queryset()

        # model không có tenant => trả nguyên
        if not (_has_field(self.model, "tenant") or _has_field(self.model, "tenant_id")):
            return qs

        tenant = get_current_tenant()
        if tenant is None:
            # an toàn: chưa resolve tenant thì coi như không có data
            return qs.none()

        return qs.for_tenant(tenant)

    def unscoped(self) -> TenantQuerySet[T]:
        """
        Bỏ tenant scope (dùng cho admin task/superuser/cron).
        """
        return super().get_queryset()

    def for_tenant(self, tenant) -> TenantQuerySet[T]:
        return self.unscoped().for_tenant(tenant)