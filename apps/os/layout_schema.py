from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from django.utils import timezone


@dataclass(frozen=True)
class LayoutSchema:
    key: str
    version: int
    effective_from: str  # ISO8601 date/time string
    title: str
    blocks: List[Dict[str, Any]]  # FE render theo config
    meta: Dict[str, Any]


def _now_iso() -> str:
    return timezone.now().isoformat()


# ====== V1 (beta) ======
# Quy ước blocks:
# - id: string unique
# - type: "kpi"|"list"|"timeline"|"notifications"|"chart"|"actions"
# - title: tiếng Việt
# - source: endpoint gợi ý (FE dùng để fetch)
# - props: config hiển thị
OS_LAYOUT_V1 = LayoutSchema(
    key="os_control_center",
    version=1,
    effective_from=_now_iso(),
    title="HeightTech OS Control Center",
    blocks=[
        {
            "id": "headline",
            "type": "kpi",
            "title": "Tổng quan",
            "source": "/api/v1/os/dashboard/",
            "props": {
                "items": [
                    {"key": "shops_total", "label": "Shop"},
                    {"key": "shops_risk", "label": "Shop rủi ro"},
                    {"key": "work_open", "label": "Task mở"},
                    {"key": "work_overdue", "label": "Task quá hạn"},
                    {"key": "actions_open", "label": "Action mở"},
                    {"key": "actions_critical", "label": "Action critical"},
                ]
            },
        },
        {
            "id": "notifications",
            "type": "notifications",
            "title": "Thông báo OS",
            "source": "/api/v1/os/notifications/?status=new&limit=20",
            "props": {"show_badge": True},
        },
        {
            "id": "timeline",
            "type": "timeline",
            "title": "Dòng thời gian",
            "source": "/api/v1/os/timeline/?scope=tenant&hours=24&limit=50",
            "props": {"group_by_day": True},
        },
        {
            "id": "work_recent",
            "type": "list",
            "title": "Công việc gần đây",
            "source": "/api/v1/os/dashboard/",
            "props": {"path": ["work", "recent"], "limit": 15},
        },
        {
            "id": "shops_risk",
            "type": "list",
            "title": "Shop rủi ro",
            "source": "/api/v1/os/dashboard/",
            "props": {"path": ["shops", "items"], "limit": 10},
        },
        {
            "id": "os_home",
            "type": "actions",
            "title": "OS đề xuất",
            "source": "/api/v1/os/home/",
            "props": {"path": ["decisions"]},
        },
    ],
    meta={
        "lang": "vi",
        "note": "Schema V1 cho beta: FE chỉ cần đọc schema và render blocks theo type/source/props",
    },
)


def get_schema(*, key: str = "os_control_center", version: Optional[int] = None) -> Dict[str, Any]:
    # Sau này anh muốn nhiều version thì mở registry list.
    schema = OS_LAYOUT_V1

    if key and key != schema.key:
        # fallback vẫn trả v1
        pass

    if version and int(version) != schema.version:
        # beta: chỉ có v1
        pass

    return {
        "key": schema.key,
        "version": schema.version,
        "effective_from": schema.effective_from,
        "title": schema.title,
        "blocks": schema.blocks,
        "meta": schema.meta,
    }