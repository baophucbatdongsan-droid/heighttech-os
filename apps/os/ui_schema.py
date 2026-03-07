# apps/os/ui_schema.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from django.utils import timezone


@dataclass(frozen=True)
class BlockSchema:
    key: str
    tieu_de: str
    loai: str  # kpi | list | timeline | table | text | actions
    mo_ta: str = ""
    icon: str = ""
    props: Optional[Dict[str, Any]] = None


def build_os_ui_schema(*, role: str = "operator") -> Dict[str, Any]:
    """
    Schema UI cho OS Home.
    FE chỉ cần render theo 'loai' + 'props', data nằm trong response blocks.
    """
    blocks: List[BlockSchema] = [
        BlockSchema(
            key="overview",
            tieu_de="Tổng quan hôm nay",
            loai="kpi",
            mo_ta="KPI nhanh theo tenant/shop",
            icon="speedometer",
            props={"kpi_keys": ["shops_total", "shops_risk", "work_open", "work_overdue", "actions_open"]},
        ),
        BlockSchema(
            key="alerts",
            tieu_de="Cảnh báo",
            loai="list",
            mo_ta="Những điểm cần xử lý ngay",
            icon="warning",
            props={"item_layout": "compact", "empty_text": "Không có cảnh báo"},
        ),
        BlockSchema(
            key="recommendations",
            tieu_de="Gợi ý",
            loai="list",
            mo_ta="Gợi ý tối ưu hệ thống",
            icon="sparkles",
            props={"item_layout": "normal", "empty_text": "Chưa có gợi ý"},
        ),
        BlockSchema(
            key="shops_health",
            tieu_de="Sức khoẻ shop",
            loai="table",
            mo_ta="Theo dõi sức khoẻ các shop",
            icon="heart",
            props={"columns": ["ten", "trang_thai", "suc_khoe", "cap_nhat"], "page_size": 10},
        ),
        BlockSchema(
            key="tasks",
            tieu_de="Công việc",
            loai="list",
            mo_ta="Công việc cần xử lý",
            icon="checklist",
            props={"item_layout": "rich", "empty_text": "Chưa có công việc"},
        ),
        BlockSchema(
            key="events",
            tieu_de="Dòng sự kiện",
            loai="timeline",
            mo_ta="Lịch sử hoạt động gần đây",
            icon="history",
            props={"endpoint": "/api/v1/os/timeline/", "page_size": 50},
        ),
        BlockSchema(
            key="chien_luoc",
            tieu_de="Chiến lược",
            loai="list",
            mo_ta="Kế hoạch đề xuất",
            icon="compass",
            props={"item_layout": "rich", "empty_text": "Chưa có chiến lược"},
        ),
        BlockSchema(
            key="hanh_dong_tu_dong",
            tieu_de="Hành động tự động",
            loai="actions",
            mo_ta="Những hành động hệ thống đã/đang chạy",
            icon="bolt",
            props={"empty_text": "Chưa có hành động tự động"},
        ),
    ]

    # founder thấy thêm block “điều khiển”
    if (role or "").lower() in ("founder", "admin"):
        blocks.insert(
            1,
            BlockSchema(
                key="command_center",
                tieu_de="Trung tâm điều khiển",
                loai="actions",
                mo_ta="Chạy lệnh nhanh cho OS",
                icon="control",
                props={"endpoint": "/api/v1/os/command-center/"},
            ),
        )

    return {
        "version": 1,
        "layout": [b.key for b in blocks],
        "blocks_schema": [
            {
                "key": b.key,
                "tieu_de": b.tieu_de,
                "loai": b.loai,
                "mo_ta": b.mo_ta,
                "icon": b.icon,
                "props": b.props or {},
            }
            for b in blocks
        ],
    }



SCHEMA_VERSION = 1


def _now_iso() -> str:
    return timezone.now().isoformat()


def build_os_ui_schema(*, role: str, tenant_id: int) -> Dict[str, Any]:
    """
    Trả về schema để FE dựng UI cực nhanh:
      - layout: thứ tự block
      - blocks: định nghĩa block (title, endpoint, refresh, empty_state...)
      - actions: CTA hiển thị theo role
      - versioning: schema_version để FE cache/invalidate
    """

    role = (role or "operator").strip().lower()

    # layout cơ bản (mọi role đều có)
    layout: List[str] = [
        "tong_quan",
        "canh_bao",
        "goi_y",
        "timeline",
        "thong_bao",
        "cong_viec",
    ]

    # founder/admin thấy thêm command center + stream
    if role in {"founder", "admin"}:
        layout.insert(0, "control_center")
        layout.append("stream")
        layout.append("command_center")

    blocks: Dict[str, Any] = {
        "control_center": {
            "tieu_de": "Trung tâm điều hành",
            "mo_ta": "KPI tổng hợp theo tenant",
            "endpoint": "/api/v1/os/dashboard/",
            "refresh_seconds": 60,
            "kich_thuoc": "xl",
            "role_allow": ["founder", "admin"],
        },
        "tong_quan": {
            "tieu_de": "Tổng quan",
            "mo_ta": "Insight tổng hợp (shops, tasks, events)",
            "endpoint": "/api/v1/founder/insight/",
            "refresh_seconds": 60,
            "kich_thuoc": "l",
            "empty_state": {"tieu_de": "Chưa có dữ liệu", "noi_dung": "Hãy kết nối shop hoặc tạo công việc."},
        },
        "canh_bao": {
            "tieu_de": "Cảnh báo",
            "mo_ta": "Cảnh báo hệ thống từ Decision Engine",
            "endpoint": "/api/v1/os/home/",
            "path_in_response": ["decisions", "alerts"],
            "refresh_seconds": 45,
            "kich_thuoc": "m",
        },
        "goi_y": {
            "tieu_de": "Gợi ý hành động",
            "mo_ta": "Recommendations từ OS",
            "endpoint": "/api/v1/os/home/",
            "path_in_response": ["decisions", "recommendations"],
            "refresh_seconds": 45,
            "kich_thuoc": "m",
        },
        "timeline": {
            "tieu_de": "Dòng thời gian",
            "mo_ta": "Sự kiện + công việc + bình luận + chuyển trạng thái",
            "endpoint": "/api/v1/os/timeline/?scope=tenant&hours=24&limit=50",
            "refresh_seconds": 20,
            "kich_thuoc": "xl",
        },
        "thong_bao": {
            "tieu_de": "Thông báo",
            "mo_ta": "Nhắm đúng user/role/public",
            "endpoint": "/api/v1/os/notifications/?status=new&limit=50",
            "refresh_seconds": 20,
            "kich_thuoc": "m",
        },
        "cong_viec": {
            "tieu_de": "Công việc",
            "mo_ta": "Danh sách công việc cần xử lý",
            "endpoint": "/api/v1/work/",
            "refresh_seconds": 30,
            "kich_thuoc": "l",
        },
        "stream": {
            "tieu_de": "Luồng realtime",
            "mo_ta": "SSE/Websocket (tuỳ anh bật sau)",
            "endpoint": "/api/v1/os/stream/",
            "refresh_seconds": 5,
            "kich_thuoc": "xl",
            "role_allow": ["founder", "admin"],
        },
        "command_center": {
            "tieu_de": "Command Center",
            "mo_ta": "Chạy lệnh OS (beta)",
            "endpoint": "/api/v1/os/command-center/",
            "refresh_seconds": 0,
            "kich_thuoc": "l",
            "role_allow": ["founder", "admin"],
        },
    }

    actions: List[Dict[str, Any]] = [
        {"key": "tao_task", "tieu_de": "Tạo công việc", "type": "navigate", "to": "/work/create/"},
        {"key": "xem_timeline", "tieu_de": "Xem timeline", "type": "navigate", "to": "/os/timeline/"},
    ]

    if role in {"founder", "admin"}:
        actions += [
            {"key": "mo_command_center", "tieu_de": "Mở Command Center", "type": "navigate", "to": "/os/command-center/"},
        ]

    return {
        "ok": True,
        "schema_version": SCHEMA_VERSION,
        "tenant_id": int(tenant_id),
        "role": role,
        "generated_at": _now_iso(),
        "layout": layout,
        "blocks": blocks,
        "actions": actions,
    }