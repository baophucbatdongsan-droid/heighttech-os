# apps/api/v1/work/workitems.py
from __future__ import annotations

from typing import Optional

from rest_framework.permissions import AllowAny, IsAdminUser
from rest_framework.exceptions import ValidationError as DRFValidationError

from apps.api.v1.base import BaseApi, api_error, api_ok
from apps.core.tenant_context import get_current_tenant_id
from apps.work.models import WorkItem, WorkComment, WorkItemTransitionLog


def _current_tenant_id(request) -> Optional[int]:
    tid = get_current_tenant_id() or getattr(request, "tenant_id", None)
    try:
        return int(tid) if tid else None
    except Exception:
        return None


def _raw_manager(Model):
    # bypass mọi default filter của objects
    if hasattr(Model, "_base_manager") and Model._base_manager is not None:
        return Model._base_manager
    if hasattr(Model, "objects_all"):
        return Model.objects_all
    return Model.objects


def _resolve_workitem(workitem_id: int, tenant_id: Optional[int]) -> Optional[WorkItem]:
    M = _raw_manager(WorkItem)
    qs = M.select_related("project")

    if tenant_id:
        wi = qs.filter(id=workitem_id, tenant_id=int(tenant_id)).first()
        if wi:
            return wi

    return qs.filter(id=workitem_id).first()


def _is_project_archived(wi: WorkItem) -> bool:
    p = getattr(wi, "project", None)
    st = (getattr(p, "status", "") or "").strip().lower()
    return st == "archived"


def _extract_error_message(e: Exception) -> str:
    detail = getattr(e, "detail", None)
    if detail is None:
        return str(e)

    # DRFValidationError({"detail": "..."}) => dict
    if isinstance(detail, dict):
        d = detail.get("detail")
        return str(d) if d is not None else str(detail)

    return str(detail)


def _safe_actor(request):
    u = getattr(request, "user", None)
    if u is None:
        return None
    if getattr(u, "is_authenticated", False) and getattr(u, "pk", None):
        return u
    return None


def _request_id(request) -> str:
    return str(getattr(request, "request_id", "") or "")


def _trace_id(request) -> str:
    return str(getattr(request, "trace_id", "") or "")


class WorkItemTransitionApi(BaseApi):
    """
    Endpoint transition (đang pass test).
    """
    permission_classes = [AllowAny]

    def post(self, request, workitem_id: int):
        tid = _current_tenant_id(request)

        wi = _resolve_workitem(int(workitem_id), tid)
        if wi is None:
            return api_error("not_found", "WorkItem không tồn tại.", status=404)

        to_status = (request.data.get("to") or "").strip().lower()
        if not to_status:
            return api_error("bad_request", "Thiếu trường `to`.", status=400)

        if _is_project_archived(wi):
            return api_error("bad_request", "Dự án đã lưu trữ, không thể chuyển trạng thái.", status=400)

        actor = _safe_actor(request)

        try:
            wi.transition_to(to_status, actor=actor)
        except DRFValidationError as e:
            return api_error("bad_request", _extract_error_message(e), status=400)
        except Exception as e:
            return api_error("bad_request", str(e), status=400)

        wi.refresh_from_db()
        return api_ok({"id": wi.id, "status": wi.status, "workflow_version": int(getattr(wi, "workflow_version", 1) or 1)})


class WorkItemUpgradeWorkflowApi(BaseApi):
    """
    Upgrade workflow_version (admin-only) — đúng OS rule:
    - WorkItem freeze version khi tạo
    - Upgrade version là action có kiểm soát (release/migration)
    """
    permission_classes = [IsAdminUser]

    def post(self, request, workitem_id: int):
        tid = _current_tenant_id(request)

        wi = _resolve_workitem(int(workitem_id), tid)
        if wi is None:
            return api_error("not_found", "WorkItem không tồn tại.", status=404)

        if _is_project_archived(wi):
            return api_error("bad_request", "Dự án đã lưu trữ, không thể upgrade workflow.", status=400)

        # input
        to_version_raw = request.data.get("to_version", None)
        note = (request.data.get("note") or "").strip()
        force = bool(request.data.get("force", False))

        try:
            to_version = int(to_version_raw)
        except Exception:
            return api_error("bad_request", "Trường `to_version` phải là số nguyên.", status=400)

        if to_version <= 0:
            return api_error("bad_request", "`to_version` phải > 0.", status=400)

        from_version = int(getattr(wi, "workflow_version", 1) or 1)
        if to_version == from_version:
            return api_ok(
                {
                    "id": wi.id,
                    "workflow_version": from_version,
                    "message": "workflow_version không đổi",
                }
            )

        # policy: mặc định không cho upgrade khi DONE/CANCELLED (tránh rewrite lịch sử)
        status_now = (getattr(wi, "status", "") or "").strip().lower()
        if not force and status_now in {WorkItem.Status.DONE, WorkItem.Status.CANCELLED}:
            return api_error(
                "bad_request",
                "WorkItem đã DONE/CANCELLED, mặc định không cho upgrade workflow_version. (Gửi `force=true` nếu vẫn muốn.)",
                status=400,
            )

        actor = _safe_actor(request)
        rid = _request_id(request)
        tid_ = _trace_id(request)

        # apply
        try:
            wi.workflow_version = to_version
            wi.save(update_fields=["workflow_version", "updated_at"])
        except Exception as e:
            return api_error("bad_request", str(e), status=400)

        # audit: comment + transitionlog (reuse) để có trail
        try:
            WorkComment.objects.create(
                tenant_id=wi.tenant_id,
                work_item_id=wi.id,
                actor=actor,
                body=note or f"Workflow upgraded {from_version} → {to_version}",
                meta={
                    "event": "workflow_upgrade",
                    "from_version": from_version,
                    "to_version": to_version,
                    "force": bool(force),
                    "request_id": rid,
                    "trace_id": tid_,
                },
            )
        except Exception:
            pass

        try:
            WorkItemTransitionLog.objects.create(
                tenant_id=wi.tenant_id,
                company_id=wi.company_id,
                project_id=wi.project_id,
                workitem_id=wi.id,
                from_status=status_now,
                to_status=status_now,
                actor=actor,
                reason=note or f"workflow_upgrade {from_version}->{to_version}",
                workflow_version=to_version,
                request_id=rid,
                trace_id=tid_,
            )
        except Exception:
            pass

        wi.refresh_from_db()
        return api_ok(
            {
                "id": wi.id,
                "status": wi.status,
                "workflow_version": int(getattr(wi, "workflow_version", 1) or 1),
                "from_version": from_version,
                "to_version": to_version,
            }
        )