from __future__ import annotations

from typing import Optional

from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.v1.insight import FounderInsightApi, _get_tenant_id
from apps.core.permissions import resolve_user_role
from apps.intelligence.action_runner import run_actions
from apps.intelligence.decision_engine import run_decisions
from apps.intelligence.risk_engine import detect_risks
from apps.intelligence.strategy_actions import plans_to_actions
from apps.intelligence.strategy_engine import build_strategies, plans_to_dict
from apps.os.ui_schema import build_os_ui_schema


def _int_or_none(v: Optional[str]) -> Optional[int]:
    try:
        if v is None:
            return None
        s = str(v).strip()
        if not s:
            return None
        return int(s)
    except Exception:
        return None


class OSHomeApi(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        tenant_id = _get_tenant_id(request)
        if not tenant_id:
            return Response({"ok": False, "message": "Thiếu tenant_id"}, status=400)

        tenant_id = int(tenant_id)

        try:
            role = (resolve_user_role(request.user) or "operator").strip().lower()
        except Exception:
            role = "operator"

        scope = (request.query_params.get("scope") or "tenant").strip().lower()
        company_id = _int_or_none(request.query_params.get("company_id"))
        shop_id = _int_or_none(request.query_params.get("shop_id"))
        project_id = _int_or_none(request.query_params.get("project_id"))

        try:
            ui_schema = build_os_ui_schema(tenant_id=tenant_id, role=role)
        except TypeError:
            ui_schema = build_os_ui_schema(tenant_id=tenant_id)

        insight_resp = FounderInsightApi().get(request)
        insight = getattr(insight_resp, "data", {}) or {}

        overview = insight.get("overview") or {}
        tasks_block = overview.get("tasks") or {}
        shops = insight.get("shops") or []

        context = {
            "tenant_id": tenant_id,
            "role": role,
            "scope": scope,
            "company_id": company_id,
            "shop_id": shop_id,
            "project_id": project_id,
            "overdue_tasks": int(tasks_block.get("overdue") or 0),
            "shops_health": shops,
            "overview": overview,
        }

        decisions = run_decisions(tenant_id=tenant_id, context=context)
        action_results = run_actions(
            tenant_id=tenant_id,
            actions=getattr(decisions, "actions", []) or [],
        )

        risks = detect_risks(context)

        plans = build_strategies(
            tenant_id=tenant_id,
            context=context,
            risks=risks,
        )
        plans_dict = plans_to_dict(plans)

        actions_from_strategy = plans_to_actions(plans_dict)
        action_results_strategy = run_actions(
            tenant_id=tenant_id,
            actions=actions_from_strategy,
        )

        def _is_risk(x):
            lv = str((x or {}).get("level") or (x or {}).get("status") or "").lower()
            return lv in ("high", "critical", "risk")

        work_open = int(
            tasks_block.get("open")
            or tasks_block.get("total_open")
            or tasks_block.get("open_count")
            or 0
        )

        actions_open = len(getattr(decisions, "actions", []) or [])
        headline = {
            "shops_total": len(shops),
            "shops_risk": len([x for x in shops if _is_risk(x)]),
            "work_open": work_open,
            "actions_open": actions_open,
        }

        return Response(
            {
                "ok": True,
                "generated_at": timezone.now().isoformat(),
                "tenant_id": tenant_id,
                "role": role,
                "scope": scope,
                "filters": {
                    "company_id": company_id,
                    "shop_id": shop_id,
                    "project_id": project_id,
                },
                "ui_schema": ui_schema or {},
                "headline": headline,
                "quyet_dinh": {
                    "canh_bao": getattr(decisions, "alerts", []) or [],
                    "goi_y": getattr(decisions, "recommendations", []) or [],
                    "hanh_dong": getattr(decisions, "actions", []) or [],
                },
                "ket_qua_hanh_dong": action_results,
                "rui_ro": risks,
                "chien_luoc": plans_dict,
                "ket_qua_hanh_dong_chien_luoc": action_results_strategy,
                "layout": [
                    "overview",
                    "alerts",
                    "recommendations",
                    "shops_health",
                    "tasks",
                    "events",
                ],
                "blocks": {
                    "overview": overview,
                    "alerts": insight.get("alerts") or [],
                    "recommendations": insight.get("recommendations") or [],
                    "shops_health": shops,
                    "tasks": tasks_block,
                    "events": overview.get("events") or [],
                },
            }
        )