# apps/os/notification_targeting.py
from __future__ import annotations

from typing import Optional
from django.db import models


def _has_field(Model, field_name: str) -> bool:
    try:
        Model._meta.get_field(field_name)
        return True
    except Exception:
        return False


def build_target_q(*, Model, user_id: Optional[int], role: str) -> models.Q:
    """
    Target rules:
      1) target_user_id == user_id
      2) target_role == role (và != "")
      3) public: target_user_id IS NULL AND target_role == ""
    """
    role = (role or "").strip().lower()

    q = models.Q()

    if user_id and _has_field(Model, "target_user"):
        q |= models.Q(target_user_id=int(user_id))

    if role and _has_field(Model, "target_role"):
        q |= (models.Q(target_role=role) & ~models.Q(target_role=""))

    # public
    if _has_field(Model, "target_user") and _has_field(Model, "target_role"):
        q |= (models.Q(target_user__isnull=True) & models.Q(target_role=""))

    return q


def apply_scope_filters(*, qs, company_id=None, shop_id=None, project_id=None):
    """
    Scope: chỉ filter nếu model có field tương ứng.
    """
    Model = qs.model

    if company_id and _has_field(Model, "company"):
        qs = qs.filter(company_id=int(company_id))
    if shop_id and _has_field(Model, "shop"):
        qs = qs.filter(shop_id=int(shop_id))
    if project_id and _has_field(Model, "project"):
        qs = qs.filter(project_id=int(project_id))

    return qs