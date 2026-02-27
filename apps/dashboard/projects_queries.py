# apps/dashboard/projects_queries.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from django.http import HttpRequest

from apps.dashboard.projects_common import parse_int, clamp


@dataclass
class ProjectsDashboardQuery:
    # lọc cơ bản
    q: str = ""
    status: str = ""
    type: str = ""

    # phân trang
    page: int = 1
    page_size: int = 50

    # sort
    sort: str = "updated"
    direction: str = "desc"

    # lọc nâng cao (Level 5)
    health_min: Optional[int] = None
    health_max: Optional[int] = None
    shops_min: Optional[int] = None
    shops_max: Optional[int] = None

    # lọc theo ngày cập nhật (YYYY-MM-DD)
    updated_from: str = ""
    updated_to: str = ""

    @staticmethod
    def _clean(s: str, max_len: int = 255) -> str:
        return (s or "").strip()[:max_len]

    @classmethod
    def from_request(cls, request: HttpRequest) -> "ProjectsDashboardQuery":
        q = cls._clean(request.GET.get("q", ""), 255)
        status = cls._clean(request.GET.get("status", ""), 64)
        type_ = cls._clean(request.GET.get("type", ""), 64)

        page = parse_int(request.GET.get("page")) or 1
        page = max(1, page)

        page_size = parse_int(request.GET.get("page_size")) or 50
        page_size = clamp(page_size, 1, 200)

        sort = cls._clean(request.GET.get("sort", ""), 32).lower()
        direction = cls._clean(request.GET.get("dir", ""), 8).lower()
        if direction not in ("asc", "desc"):
            direction = "desc"

        allowed_sort = {"id", "name", "type", "status", "health", "shops", "updated"}
        if sort not in allowed_sort:
            sort = "updated"

        # advanced filters
        health_min = parse_int(request.GET.get("health_min"))
        health_max = parse_int(request.GET.get("health_max"))
        shops_min = parse_int(request.GET.get("shops_min"))
        shops_max = parse_int(request.GET.get("shops_max"))

        # clamp an toàn
        if health_min is not None:
            health_min = clamp(health_min, 0, 100)
        if health_max is not None:
            health_max = clamp(health_max, 0, 100)

        updated_from = cls._clean(request.GET.get("updated_from", ""), 32)
        updated_to = cls._clean(request.GET.get("updated_to", ""), 32)

        return cls(
            q=q,
            status=status,
            type=type_,
            page=page,
            page_size=page_size,
            sort=sort,
            direction=direction,
            health_min=health_min,
            health_max=health_max,
            shops_min=shops_min,
            shops_max=shops_max,
            updated_from=updated_from,
            updated_to=updated_to,
        )