from __future__ import annotations

from typing import Any, Optional

from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.v1.insight import _get_tenant_id
from apps.os.timeline_engine import TimelineCursor, build_os_timeline


def _parse_int(v: Any, default: Optional[int] = None) -> Optional[int]:
    try:
        if v is None:
            return default
        s = str(v).strip()
        if s == "":
            return default
        return int(s)
    except Exception:
        return default


class OSTimelineApi(APIView):
    """
    GET /api/v1/os/timeline/

    Query:
      scope=tenant|shop|company|project|user
      shop_id=
      company_id=
      project_id=
      actor_id=
      hours=24
      limit=50
      before_ts=ISO8601
      before_id=int
    """

    permission_classes = [IsAuthenticated]

    def get(self, request: Request):

        tenant_id = _get_tenant_id(request)
        if not tenant_id:
            return Response({"ok": False, "message": "Thiếu tenant_id"}, status=400)

        tenant_id = int(tenant_id)

        qp = request.query_params

        scope = (qp.get("scope") or "tenant").strip().lower()

        shop_id = _parse_int(qp.get("shop_id"))
        company_id = _parse_int(qp.get("company_id"))
        project_id = _parse_int(qp.get("project_id"))
        actor_id = _parse_int(qp.get("actor_id"))

        hours = _parse_int(qp.get("hours"), 24) or 24
        limit = _parse_int(qp.get("limit"), 50) or 50

        # cursor
        before_ts = (qp.get("before_ts") or "").strip() or None
        before_id = _parse_int(qp.get("before_id"), None)
        cursor = TimelineCursor(before_ts=before_ts, before_id=before_id)

        valid_scopes = {"tenant", "shop", "company", "project", "user"}

        if scope not in valid_scopes:
            return Response(
                {"ok": False, "message": "scope không hợp lệ"},
                status=400,
            )

        # ---- relaxed validation ----
        # nếu FE gửi scope nhưng thiếu id -> fallback tenant
        if scope == "shop" and not shop_id:
            scope = "tenant"

        if scope == "company" and not company_id:
            scope = "tenant"

        if scope == "project" and not project_id:
            scope = "tenant"

        if scope == "user" and not actor_id:
            scope = "tenant"

        # build timeline
        data = build_os_timeline(
            tenant_id=tenant_id,
            scope=scope,
            hours=int(hours),
            limit=int(limit),
            cursor=cursor,
            shop_id=shop_id,
            company_id=company_id,
            project_id=project_id,
            actor_id=actor_id,
        )

        return Response(
            {
                "ok": True,
                "generated_at": timezone.now().isoformat(),
                "tenant_id": tenant_id,
                "scope": scope,
                "filters": {
                    "shop_id": shop_id,
                    "company_id": company_id,
                    "project_id": project_id,
                    "actor_id": actor_id,
                },
                "hours": int(hours),
                "limit": int(limit),
                "items": data.get("items", []) or [],
                "next_cursor": data.get("next_cursor"),
            }
        )