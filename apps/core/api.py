from __future__ import annotations

from rest_framework.permissions import BasePermission
from rest_framework.exceptions import NotFound

from apps.core.tenant_context import get_current_tenant


class TenantScopedQuerysetMixin:
    """
    - API tự filter theo tenant nếu model có field tenant.
    - Founder bypass.
    """

    tenant_field = "tenant"

    def _has_tenant_field(self, model) -> bool:
        try:
            return any(f.name == self.tenant_field for f in model._meta.get_fields())
        except Exception:
            return False

    def get_tenant(self):
        req = getattr(self, "request", None)
        t = getattr(req, "tenant", None) if req else None
        return t or get_current_tenant()

    def get_queryset(self):
        qs = super().get_queryset()
        req = self.request

        if getattr(req.user, "is_superuser", False):
            return qs

        Model = qs.model
        if not self._has_tenant_field(Model):
            return qs

        t = self.get_tenant()
        if not t:
            return qs.none()

        return qs.filter(**{self.tenant_field: t})

    def perform_create(self, serializer):
        req = self.request
        if getattr(req.user, "is_superuser", False):
            return serializer.save()

        t = self.get_tenant()
        if not t:
            raise NotFound("Tenant not resolved")

        Model = serializer.Meta.model
        if self._has_tenant_field(Model):
            return serializer.save(**{self.tenant_field: t})

        return serializer.save()


class IsFounderOrTenantUser(BasePermission):
    """
    Basic: founder always allowed.
    MVP: mọi user đã login thì OK.
    Sau bạn sẽ thay bằng role-based.
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True
        return True