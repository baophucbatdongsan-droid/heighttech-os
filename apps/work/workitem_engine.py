# apps/work/services/workitem_engine.py (gợi ý)
from dataclasses import dataclass
from typing import Optional, Dict, Any
from django.db import transaction
from rest_framework.exceptions import ValidationError as DRFValidationError

from apps.work.models import WorkItem
@dataclass
class TransitionResult:
    ok: bool
    error: str = ""
    payload: Optional[Dict[str, Any]] = None




def transition_workitem(
    *,
    wi: WorkItem,
    to: str,
    actor=None,
    reason: str = "",
    request_id: str = "",
    trace_id: str = "",
) -> WorkItem:

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