# apps/api/v1/os/os_control_center.py
from __future__ import annotations

from typing import Any, Dict, Optional

from django.core.cache import cache
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.v1.insight import _get_tenant_id
from apps.core.permissions import resolve_user_role

# Reuse existing OS APIs (no internal HTTP, no duplication)
from apps.api.v1.os.os_layout import OSLayoutApi
from apps.api.v1.os.dashboard import OSDashboardApi
from apps.api.v1.os.os_timeline import OSTimelineApi
from apps.api.v1.os.os_notifications import OSNotificationsApi
from apps.api.v1.os.os_home import OSHomeApi

from .os_layout import build_os_layout_schema  # em sẽ tạo ở phần B


def _parse_int(v, default: Optional[int] = None) -> Optional[int]:
    try:
        if v is None or v == "":
            return default
        return int(v)
    except Exception:
        return default


def _parse_bool(v, default: bool = False) -> bool:
    s = (str(v) if v is not None else "").strip().lower()
    if not s:
        return default
    return s in {"1", "true", "yes", "y", "on"}


def _safe_call(view: APIView, request: Request, *, method: str = "get", **kwargs) -> Dict[str, Any]:
    """
    Call DRF view method safely and return dict payload.
    Never raise to the caller (control-center must be resilient).
    """
    try:
        fn = getattr(view, method, None)
        if not fn:
            return {"ok": False, "message": f"view has no method '{method}'"}
        resp = fn(request, **kwargs)
        # resp is DRF Response
        data = getattr(resp, "data", None)
        if isinstance(data, dict):
            return data
        return {"ok": True, "data": data}
    except Exception as e:
        return {"ok": False, "message": str(e)}


class OSControlCenterApi(APIView):
    """
    GET /api/v1/os/control-center/

    Purpose: single-shot payload for FE Beta:
      - layout schema
      - dashboard KPIs
      - timeline events
      - notifications (targeting + scope)
      - home decisions (decisions/recommendations/actions snapshot)

    Query params (optional):
      - include=layout,dashboard,timeline,notifications,home   (default: all)
      - limit=50 (notifications/timeline)
      - hours=24 (timeline)
      - scope=tenant|company|shop|project (timeline)
      - company_id, shop_id, project_id (scope filters)
      - status=new|read|archived (notifications)
      - no_cache=1 to bypass cache
    """
    permission_classes = [IsAuthenticated]

    def get(self, request: Request):
        tenant_id = _get_tenant_id(request)
        if not tenant_id:
            return Response({"ok": False, "message": "Thiếu tenant_id"}, status=400)

        role = (resolve_user_role(request.user) or "operator").strip().lower()
        uid = getattr(request.user, "id", None)

        include_raw = (request.query_params.get("include") or "").strip()
        include = {x.strip().lower() for x in include_raw.split(",") if x.strip()} if include_raw else {
            "layout", "dashboard", "timeline", "notifications", "home"
        }

        # shared filters
        limit = _parse_int(request.query_params.get("limit"), 50) or 50
        limit = max(1, min(200, limit))

        hours = _parse_int(request.query_params.get("hours"), 24) or 24
        hours = max(1, min(24 * 30, hours))  # <= 30 days

        timeline_scope = (request.query_params.get("scope") or "tenant").strip().lower()
        if timeline_scope not in {"tenant", "company", "shop", "project"}:
            timeline_scope = "tenant"

        company_id = _parse_int(request.query_params.get("company_id"), None)
        shop_id = _parse_int(request.query_params.get("shop_id"), None)
        project_id = _parse_int(request.query_params.get("project_id"), None)

        notif_status = (request.query_params.get("status") or "new").strip().lower()
        if notif_status not in {"new", "read", "archived"}:
            notif_status = "new"

        no_cache = _parse_bool(request.query_params.get("no_cache"), False)

        # cache key (very short TTL for FE smoothness)
        cache_key = (
            f"os:control_center:v1:"
            f"t{int(tenant_id)}:u{int(uid or 0)}:r{role}:"
            f"inc[{','.join(sorted(include))}]:"
            f"lim{limit}:hrs{hours}:sc{timeline_scope}:"
            f"co{company_id or 0}:sh{shop_id or 0}:pj{project_id or 0}:ns{notif_status}"
        )
        if not no_cache:
            cached = cache.get(cache_key)
            if isinstance(cached, dict) and cached.get("ok") is True:
                return Response(cached)

        # --- Build payload by calling sub-views safely ---
        payload: Dict[str, Any] = {
            "ok": True,
            "tenant_id": int(tenant_id),
            "role": role,
            "generated_at": timezone.now().isoformat(),
            "meta": {
                "include": sorted(include),
                "filters": {
                    "limit": limit,
                    "hours": hours,
                    "scope": timeline_scope,
                    "company_id": company_id,
                    "shop_id": shop_id,
                    "project_id": project_id,
                    "status": notif_status,
                },
            },
        }

        # layout
        if "layout" in include:
            payload["layout"] = _safe_call(OSLayoutApi(), request)

        # dashboard
        if "dashboard" in include:
            payload["dashboard"] = _safe_call(OSDashboardApi(), request)

        # timeline
        if "timeline" in include:
            # Pass query params through request (OSTimelineApi uses request.query_params)
            payload["timeline"] = _safe_call(OSTimelineApi(), request)

        # notifications
        if "notifications" in include:
            payload["notifications"] = _safe_call(OSNotificationsApi(), request)

        # home (decisions snapshot)
        if "home" in include:
            payload["home"] = _safe_call(OSHomeApi(), request)

        # headline shortcut (FE render KPI instantly)
        # Prefer dashboard.headline if exists
        headline = {}
        try:
            if isinstance(payload.get("dashboard"), dict):
                headline = payload["dashboard"].get("headline") or {}
        except Exception:
            headline = {}

        payload["headline"] = headline or {
            "shops_total": None,
            "shops_risk": None,
            "work_open": None,
            "work_overdue": None,
            "actions_open": None,
            "actions_critical": None,
        }

        # cache short TTL
        if not no_cache:
            cache.set(cache_key, payload, timeout=8)

        return Response(payload)
    
        # --- Build layout schema separately (heavy lifting) ---

        schema = build_os_layout_schema(tenant_id=int(tenant_id))
        return Response(
            {
                "ok": True,
                "tenant_id": int(tenant_id),
                "schema": schema,
            }
        )