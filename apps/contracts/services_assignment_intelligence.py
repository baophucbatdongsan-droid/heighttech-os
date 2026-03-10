from __future__ import annotations

from typing import Optional

from django.contrib.auth import get_user_model

User = get_user_model()


def _norm(s: str) -> str:
    return str(s or "").strip().lower()


def infer_role_key_from_task(*, title: str, description: str, priority_label: str) -> str:
    """
    Suy luận task này nên giao cho role nào.
    """
    t = _norm(title)
    d = _norm(description)
    p = _norm(priority_label)

    blob = f"{t} {d}"

    # booking
    if any(x in blob for x in ["booking", "koc", "kol", "chốt deal", "deal", "creator"]):
        return "leader_booking"

    # editor
    if any(x in blob for x in ["edit", "editor", "dựng", "hau ky", "hậu kỳ", "thumbnail", "caption"]):
        return "editor"

    # operation
    if any(x in blob for x in ["vận hành", "van hanh", "shop", "gmv", "doanh thu", "sku", "ads", "quảng cáo"]):
        return "leader_operation"

    # content/channel
    if p in {"scale_now", "produce_now", "fix_now"}:
        return "leader_channel"

    return "leader_channel"


def pick_assignee_for_role(*, tenant_id: int, role_key: str) -> Optional[User]:
    """
    Chọn user đầu tiên phù hợp trong tenant.
    Hệ của anh đang chưa chốt 100% schema Membership.role/title,
    nên em match mềm theo text để chạy thực chiến trước.
    """
    try:
        from apps.accounts.models import Membership

        memberships = (
            Membership.objects.filter(
                tenant_id=int(tenant_id),
                is_active=True,
            )
            .select_related("user")
            .order_by("id")
        )

        role_key_n = _norm(role_key)

        for m in memberships:
            role_blob = " ".join([
                str(getattr(m, "role", "") or ""),
                str(getattr(m, "title", "") or ""),
                str(getattr(getattr(m, "user", None), "username", "") or ""),
                str(getattr(getattr(m, "user", None), "email", "") or ""),
                str(getattr(getattr(m, "user", None), "first_name", "") or ""),
                str(getattr(getattr(m, "user", None), "last_name", "") or ""),
            ]).lower()

            if role_key_n == "leader_booking" and any(x in role_blob for x in ["leader_booking", "booking", "book"]):
                return m.user

            if role_key_n == "leader_channel" and any(x in role_blob for x in ["leader_channel", "channel", "content"]):
                return m.user

            if role_key_n == "leader_operation" and any(x in role_blob for x in ["leader_operation", "operation", "ops", "vận hành", "van hanh"]):
                return m.user

            if role_key_n == "editor" and any(x in role_blob for x in ["editor", "edit", "video"]):
                return m.user

    except Exception:
        pass

    return None