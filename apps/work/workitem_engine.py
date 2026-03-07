# apps/work/services/workitem_engine.py (gợi ý)
from dataclasses import dataclass
from typing import Optional, Dict, Any

@dataclass
class TransitionResult:
    ok: bool
    error: str = ""
    payload: Optional[Dict[str, Any]] = None

# apps/work/services/workitem_engine.py
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from apps.work.models import WorkItem, WorkItemTransitionLog

def transition_workitem(*, wi: WorkItem, to: str, actor=None, reason: str = "", request_id: str = "", trace_id: str = "") -> WorkItem:
    # 1) chặn nếu project archived
    if getattr(wi.project, "status", "") == "archived":
        raise ValidationError("Dự án đã lưu trữ, không thể chuyển trạng thái công việc.")

    from_status = wi.status

    # 2) gọi engine hiện tại của bạn (đã test OK)
    # ví dụ: wi.transition_to(to)
    try:
        wi.transition_to(to)
    except Exception as e:
        # bạn có thể map message cho sạch
        raise ValidationError(str(e))

    wi.save(update_fields=["status", "updated_at"])

    # 3) ghi audit log
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
    )
    return wi