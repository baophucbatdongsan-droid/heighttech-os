# apps/api/v1/scope.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional, Set

from django.db.models import Q, QuerySet

from apps.core.permissions import resolve_user_role, ROLE_FOUNDER
from apps.api.v1.guards import get_scope_company_ids, get_scope_shop_ids


@dataclass
class Scope:
    role: str
    is_all_access: bool
    tenant_id: Optional[int]
    company_ids: Set[int]
    shop_ids: Set[int]


def get_scope(request) -> Scope:
    user = request.user
    tid = getattr(request, "tenant_id", None)

    role = resolve_user_role(user)
    is_all_access = bool(role == ROLE_FOUNDER or getattr(user, "is_superuser", False))

    company_ids = set(get_scope_company_ids(user) or [])
    shop_ids = set(get_scope_shop_ids(user) or [])

    return Scope(
        role=role,
        is_all_access=is_all_access,
        tenant_id=int(tid) if tid else None,
        company_ids=company_ids,
        shop_ids=shop_ids,
    )


def apply_tenant(qs: QuerySet, tenant_id: Optional[int]) -> QuerySet:
    if tenant_id:
        return qs.filter(tenant_id=int(tenant_id))
    return qs


def apply_company_or_shop_scope(
    qs: QuerySet,
    scope: Scope,
    company_field: str = "company_id",
    shop_target_type: str = "shop",
    target_type_field: str = "target_type",
    target_id_field: str = "target_id",
) -> QuerySet:
    """
    Default for WorkItem:
      - staff: company_id in allowed company_ids
      - client: target_type="shop" and target_id in allowed shop_ids
      - founder: all
    """
    qs = apply_tenant(qs, scope.tenant_id)
    if scope.is_all_access:
        return qs

    q_company = Q()
    if scope.company_ids:
        q_company = Q(**{f"{company_field}__in": list(scope.company_ids)})

    q_shop = Q()
    if scope.shop_ids:
        q_shop = Q(**{
            target_type_field: shop_target_type,
            f"{target_id_field}__in": list(scope.shop_ids),
        })

    combined = (q_company | q_shop)
    if combined.children:
        return qs.filter(combined)

    return qs.none()


def apply_shop_scope(qs: QuerySet, scope: Scope, shop_field: str = "shop_id") -> QuerySet:
    """
    For Booking/Performance… (direct shop FK)
    """
    qs = apply_tenant(qs, scope.tenant_id)
    if scope.is_all_access:
        return qs

    if not scope.shop_ids:
        return qs.none()

    return qs.filter(**{f"{shop_field}__in": list(scope.shop_ids)})


def apply_company_scope(qs: QuerySet, scope: Scope, company_field: str = "company_id") -> QuerySet:
    """
    For Channel/Project… (direct company FK)
    """
    qs = apply_tenant(qs, scope.tenant_id)
    if scope.is_all_access:
        return qs

    if not scope.company_ids:
        return qs.none()

    return qs.filter(**{f"{company_field}__in": list(scope.company_ids)})