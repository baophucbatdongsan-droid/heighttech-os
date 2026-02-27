from __future__ import annotations
from typing import Any, Dict, Optional

from django.utils import timezone

from apps.core.models import AuditLog  # nếu model đúng tên
# Nếu model khác tên, bạn tìm trong apps/core/models.py

def log_dashboard_action(
    *,
    request,
    tenant_id: int,
    action: str,
    entity: str,
    entity_id: int,
    company_id: Optional[int] = None,
    meta: Optional[Dict[str, Any]] = None,
):
    user = getattr(request, "user", None)
    AuditLog.objects.create(
        tenant_id=tenant_id,
        actor_id=getattr(user, "id", None),
        method="DASHBOARD",
        path=getattr(request, "path", ""),
        referer=request.META.get("HTTP_REFERER", ""),
        model=entity,
        model_id=entity_id,
        company_id=company_id,
        action=action,
        meta=meta or {},
        created_at=timezone.now(),
    )