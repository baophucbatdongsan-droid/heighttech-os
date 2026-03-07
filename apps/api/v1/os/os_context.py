from __future__ import annotations

from typing import Any, Dict, List

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.v1.insight import _get_tenant_id


def _safe_model(path: str, name: str):
    try:
        m = __import__(path, fromlist=[name])
        return getattr(m, name)
    except Exception:
        return None


Company = _safe_model("apps.companies.models", "Company")
Shop = _safe_model("apps.shops.models", "Shop")
Project = _safe_model("apps.projects.models", "Project")


class OSContextApi(APIView):
    """
    /api/v1/os/context/
    Returns lightweight lists for filter bar:
      - companies
      - shops
      - projects
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        tenant_id = _get_tenant_id(request)
        if not tenant_id:
            return Response({"ok": False, "message": "Thiếu tenant_id"}, status=400)

        tenant_id = int(tenant_id)

        data: Dict[str, Any] = {"ok": True, "tenant_id": tenant_id}

        # companies
        companies: List[Dict[str, Any]] = []
        if Company is not None:
            try:
                qs = Company.objects.filter(tenant_id=tenant_id).order_by("-id")[:200]
                for c in qs:
                    companies.append(
                        {"id": c.id, "name": getattr(c, "name", None) or f"Company {c.id}"}
                    )
            except Exception:
                companies = []
        data["companies"] = companies

        # shops
        shops: List[Dict[str, Any]] = []
        if Shop is not None:
            try:
                qs = Shop.objects.filter(tenant_id=tenant_id).order_by("-id")[:300]
                for s in qs:
                    shops.append(
                        {
                            "id": s.id,
                            "name": getattr(s, "name", None) or getattr(s, "shop_name", None) or f"Shop {s.id}",
                            "company_id": getattr(s, "company_id", None),
                        }
                    )
            except Exception:
                shops = []
        data["shops"] = shops

        # projects
        projects: List[Dict[str, Any]] = []
        if Project is not None:
            try:
                qs = Project.objects.filter(tenant_id=tenant_id).order_by("-id")[:300]
                for p in qs:
                    projects.append(
                        {
                            "id": p.id,
                            "name": getattr(p, "name", None) or f"Project {p.id}",
                            "company_id": getattr(p, "company_id", None),
                            "shop_id": getattr(p, "shop_id", None),
                        }
                    )
            except Exception:
                projects = []
        data["projects"] = projects

        return Response(data)