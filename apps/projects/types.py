# apps/projects/types.py
from __future__ import annotations

from typing import Optional, Any


# -------------------------
# Type normalize (IMPORTANT)
# -------------------------
TYPE_MAP = {
    # legacy/display -> canonical (db)
    "SHOP_OPERATION": "shop_operation",
    "shop_operation": "shop_operation",
    "BUILD_CHANNEL": "build_channel",
    "build_channel": "build_channel",
    "BOOKING": "booking",
    "booking": "booking",
}


def normalize_project_type(v: Optional[str]) -> str:
    raw = (v or "").strip()
    if not raw:
        return "shop_operation"
    if raw in TYPE_MAP:
        return TYPE_MAP[raw]
    up = raw.upper()
    if up in TYPE_MAP:
        return TYPE_MAP[up]
    return raw.lower()


def get_type_display_safe(p: Any) -> str:
    """
    Trả display cho field type nếu model có get_type_display().
    Nếu value lạ/legacy hoặc model không có method -> trả raw type để không crash.
    """
    try:
        fn = getattr(p, "get_type_display", None)
        if callable(fn):
            return fn()
    except Exception:
        pass
    return str(getattr(p, "type", "") or "")