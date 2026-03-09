from __future__ import annotations

from django.db import transaction
from rest_framework.exceptions import ValidationError as DRFValidationError

from apps.work.models import WorkItem


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
    - validate nhanh
    - call domain transition
    - return fresh work item

    NOTE:
    - Transition log + comment đã được xử lý trong WorkItem.transition_to()
    - Không ghi log lần 2 ở đây để tránh duplicate
    """
    to_status = (to or "").strip().lower()
    if not to_status:
        raise DRFValidationError({"detail": "missing_to"})

    with transaction.atomic():
        wi = (
            WorkItem.objects_all.select_for_update()
            .select_related("project")
            .get(id=wi.id)
        )

        project = getattr(wi, "project", None)
        if project is not None:
            st = (getattr(project, "status", "") or "").strip().lower()
            if st == "archived":
                raise DRFValidationError({"detail": "project_archived"})

        wi.transition_to(
            to_status,
            actor=actor,
            note=reason or "",
        )

        wi.refresh_from_db()

        return wi