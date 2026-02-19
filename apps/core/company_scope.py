from __future__ import annotations

from django.core.exceptions import PermissionDenied

from apps.accounts.models import Membership


AGENCY_ROLES = {"founder", "head", "account", "sale", "operator"}
CLIENT_ROLE = "client"


def resolve_company_scope(request):
    """
    Resolve company scope từ:
    - request.user
    - tenant (đã set qua middleware)
    - X-Company-Id header (nếu có)

    Trả về:
        membership instance
    """

    tenant = getattr(request, "tenant", None)
    if tenant is None:
        raise PermissionDenied("Tenant not resolved")

    user = request.user
    if not user.is_authenticated:
        raise PermissionDenied("Authentication required")

    company_id = request.headers.get("X-Company-Id")

    qs = Membership.objects.filter(
        user=user,
        is_active=True,
        company__tenant=tenant,
    ).select_related("company")

    if company_id:
        qs = qs.filter(company_id=int(company_id))

    membership = qs.first()

    if not membership:
        raise PermissionDenied("No membership in this company")

    return membership