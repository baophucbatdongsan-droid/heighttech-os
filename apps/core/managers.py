# apps/core/managers.py
from __future__ import annotations

from typing import Any, Optional, TypeVar

from django.db import models

from apps.core.tenant_context import get_current_tenant

T = TypeVar("T", bound=models.Model)


def _has_field(model: type[models.Model], field_name: str) -> bool:
    try:
        return any(f.name == field_name for f in model._meta.get_fields())
    except Exception:
        return False


class TenantQuerySet(models.QuerySet):
    """
    QuerySet có tenant scope tự động.
    - Nếu model không có field tenant => trả về y nguyên
    - Nếu có tenant => auto filter theo tenant hiện tại (contextvar)
    - Superuser/admin bypass sẽ không nằm ở đây, mà xử lý ở middleware/admin/service layer.
      (Vì ở queryset không có request/user.)
    """

    def for_current_tenant(self):
        Model = self.model
        if not _has_field(Model, "tenant"):
            return self

        tenant = get_current_tenant()
        if tenant is None:
            # Không có tenant trong context -> trả none để tránh lộ data cross-tenant
            return self.none()

        return self.filter(tenant=tenant)

    def active(self):
        Model = self.model
        qs = self
        if _has_field(Model, "is_active"):
            qs = qs.filter(is_active=True)
        return qs

    # tiện: dùng để bypass khi cần
    def unscoped(self):
        return self.all()


class TenantManager(models.Manager):
    """
    Manager mặc định cho model multi-tenant.
    - Model.objects -> luôn scope theo tenant hiện tại
    - Model._base_manager -> bypass scope (Django built-in)
    """

    def get_queryset(self):
        qs = TenantQuerySet(self.model, using=self._db)
        return qs.for_current_tenant()

    # helpers
    def active(self):
        return self.get_queryset().active()

    def unscoped(self):
        # NOTE: vẫn trả queryset scoped theo get_queryset().
        # Nếu bạn muốn *thực sự* unscoped thì dùng Model._base_manager
        return TenantQuerySet(self.model, using=self._db).all()


class TenantAllManager(models.Manager):
    """
    Manager không scope (xài cho admin/superuser hoặc báo cáo tổng).
    Dùng nếu bạn muốn: objects_all = TenantAllManager()
    """

    def get_queryset(self):
        return TenantQuerySet(self.model, using=self._db).all()

    def active(self):
        return self.get_queryset().active()