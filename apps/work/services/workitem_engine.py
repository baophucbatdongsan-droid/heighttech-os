# apps/work/services/workitem_engine.py
from __future__ import annotations

from typing import Optional

from django.db import transaction
from rest_framework.exceptions import ValidationError as DRFValidationError

from apps.work.models import WorkItem, WorkItemTransitionLog


def transition_workitem(
    *,
    wi: WorkItem,
    to: str,
    actor=None,
    reason: str = "",
    request_id: str = "",
    trace_id: str = "",
) -> WorkItem:
    """
    Service orchestration:
    - lock row
    - call domain transition (engine + guard)
    - write transition log (bổ sung workflow_version)
    """

    to_status = (to or "").strip().lower()
    if not to_status:
        raise DRFValidationError({"detail": "missing_to"})

    # Reload + lock để tránh race condition
    with transaction.atomic():
        wi = (
            WorkItem.objects_all.select_for_update()
            .select_related("project")
            .get(id=wi.id)
        )

        # Guard nhanh (domain đã guard nhưng giữ message rõ)
        project = getattr(wi, "project", None)
        if project is not None:
            st = (getattr(project, "status", "") or "").strip().lower()
            if st == "archived":
                raise DRFValidationError({"detail": "project_archived"})

        from_status = (wi.status or "").strip().lower()

        # Domain transition (WorkflowEngine + project lock + metrics)
        wi.transition_to(to_status, actor=actor, note=reason or "")

        # Lấy version (đã có field workflow_version + resolver)
        workflow_version = getattr(wi, "workflow_version", None)
        try:
            workflow_version = int(workflow_version) if workflow_version is not None else wi._resolve_workflow_version()
        except Exception:
            workflow_version = 1

        # Audit log (ngoài WorkComment)
        WorkItemTransitionLog.objects.create(
            tenant_id=wi.tenant_id,
            company_id=wi.company_id,
            project_id=wi.project_id,
            workitem_id=wi.id,
            from_status=from_status,
            to_status=wi.status,
            actor=actor if getattr(actor, "is_authenticated", False) else None,
            reason=reason or "",
            request_id=request_id or "",
            trace_id=trace_id or "",
            workflow_version=workflow_version,
        )

        return wi