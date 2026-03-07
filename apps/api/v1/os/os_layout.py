# apps/api/v1/os/os_layout.py
from __future__ import annotations

from typing import Any, Dict
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.v1.insight import _get_tenant_id


def build_os_layout_schema(*, tenant_id: int) -> Dict[str, Any]:
    """
    FE render theo blocks:
    - type + source + props
    Stripe-level-2: có filter bar + realtime stream + command palette
    """
    now = timezone.now().isoformat()
    return {
        "key": "os_control_center",
        "version": 2,
        "effective_from": now,
        "title": "HeightTech OS Control Center",
        "meta": {
            "lang": "vi",
            "note": "Schema V2: Stripe-level-2 (filters + SSE + command palette).",
        },
        "blocks": [
            {
                "id": "filters",
                "type": "filters",
                "title": "Bộ lọc",
                "source": None,
                "props": {
                    "fields": [
                        {"key": "company_id", "label": "Company", "type": "number"},
                        {"key": "shop_id", "label": "Shop", "type": "number"},
                        {"key": "project_id", "label": "Project", "type": "number"},
                        {"key": "hours", "label": "Hours", "type": "number", "default": 24},
                    ]
                },
            },
            {
                "id": "headline",
                "type": "kpi",
                "title": "Tổng quan",
                "source": "/api/v1/os/dashboard/",
                "props": {
                    "items": [
                        {"key": "shops_total", "label": "Shops"},
                        {"key": "shops_risk", "label": "Risk"},
                        {"key": "work_open", "label": "Open Tasks"},
                        {"key": "actions_open", "label": "Actions"},
                    ]
                },
            },
            {
                "id": "timeline",
                "type": "timeline",
                "title": "Timeline",
                "source": "/api/v1/os/timeline/?scope=tenant&hours={hours}&company_id={company_id}&shop_id={shop_id}&project_id={project_id}&limit=50",
                "props": {"realtime": True, "stream_url": "/api/v1/os/stream/?scope=tenant"},
            },
            {
                "id": "notifications",
                "type": "notifications",
                "title": "Notifications",
                "source": "/api/v1/os/notifications/?status=new&company_id={company_id}&shop_id={shop_id}&project_id={project_id}&limit=50",
                "props": {"show_badge": True},
            },
            {
                "id": "strategy",
                "type": "strategy",
                "title": "AI Strategy (V1 rule-based)",
                "source": "/api/v1/os/home/",
                "props": {"path": ["decisions"]},
            },
            {
                "id": "shop_health",
                "type": "shop_health",
                "title": "Shop health monitor",
                "source": "/api/v1/os/dashboard/",
                "props": {"path": ["shops", "items"], "limit": 10},
            },
            {
                "id": "command_palette",
                "type": "command_palette",
                "title": "Command Center",
                "source": "/api/v1/os/command-center/",
                "props": {"shortcut": "Ctrl+K / Cmd+K"},
            },
        ],
    }


class OSLayoutApi(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request):
        tenant_id = _get_tenant_id(request)
        if not tenant_id:
            return Response({"ok": False, "message": "Thiếu tenant_id"}, status=400)

        schema = build_os_layout_schema(tenant_id=int(tenant_id))
        return Response(
            {
                "ok": True,
                "tenant_id": int(tenant_id),
                "generated_at": timezone.now().isoformat(),
                "schema": schema,
            }
        )