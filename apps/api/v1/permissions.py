# apps/api/v1/permissions.py
from __future__ import annotations

from typing import Set
from rest_framework.permissions import BasePermission
from apps.intelligence.action_runner import run_actions
# ===============================
# HẰNG SỐ ROLE
# ===============================
ROLE_FOUNDER = "founder"
ROLE_HEAD = "head"
ROLE_ACCOUNT = "account"
ROLE_SALE = "sale"
ROLE_OPERATOR = "operator"
ROLE_CLIENT = "client"
ROLE_NONE = "none"

# ===============================
# HẰNG SỐ ABILITY
# ===============================
VIEW_API_DASHBOARD = "api:view_dashboard"
VIEW_API_FOUNDER = "api:view_founder"

# ===============================
# POLICY ROLE → ABILITY
# ===============================
ROLE_TO_ABILITIES = {
    ROLE_FOUNDER: {VIEW_API_DASHBOARD, VIEW_API_FOUNDER},
    ROLE_HEAD: {VIEW_API_DASHBOARD},
    ROLE_ACCOUNT: {VIEW_API_DASHBOARD},
    ROLE_SALE: {VIEW_API_DASHBOARD},
    ROLE_OPERATOR: {VIEW_API_DASHBOARD},
    ROLE_CLIENT: {VIEW_API_DASHBOARD},
}


# ===============================
# HÀM TIỆN ÍCH
# ===============================
def _is_authed(user) -> bool:
    return bool(getattr(user, "is_authenticated", False))


def role_has_ability(role: str, ability: str) -> bool:
    role = (role or ROLE_NONE).lower()
    return ability in ROLE_TO_ABILITIES.get(role, set())


def resolve_user_role(user) -> str:
    """
    Resolve role theo thứ tự ưu tiên:
      superuser -> founder
      membership.role -> theo mapping
      nếu không có membership -> none
    """
    if not _is_authed(user):
        return ROLE_NONE

    if bool(getattr(user, "is_superuser", False)):
        return ROLE_FOUNDER

    # membership-based
    try:
        from apps.accounts.models import Membership

        m = Membership.objects.filter(user=user, is_active=True).first()
        if not m:
            return ROLE_NONE

        role = (getattr(m, "role", "") or "").strip().lower()
        if role in ROLE_TO_ABILITIES:
            return role

        # Nếu role lạ/không nằm policy thì mặc định client (an toàn hơn NONE)
        return ROLE_CLIENT
    except Exception:
        # Nếu vì lý do gì đó không query được membership thì chặn
        return ROLE_NONE


# ===============================
# DRF PERMISSIONS
# ===============================
class AbilityPermission(BasePermission):
    """
    Mỗi view chỉ cần khai báo:
      required_ability = VIEW_API_DASHBOARD
    """

    # ✅ message tiếng Việt (DRF sẽ trả {"detail": message})
    message = "Bạn không có quyền truy cập chức năng này"

    def has_permission(self, request, view) -> bool:
        required = getattr(view, "required_ability", None)
        if not required:
            return True

        user = getattr(request, "user", None)
        role = resolve_user_role(user)
        return role_has_ability(role, required)


class FounderOnlyPermission(BasePermission):
    """
    Chỉ founder/superuser mới được vào.
    """
    message = "Chỉ Founder mới có quyền truy cập"

    def has_permission(self, request, view) -> bool:
        u = getattr(request, "user", None)
        if not _is_authed(u):
            return False

        # superuser luôn là founder
        if bool(getattr(u, "is_superuser", False)):
            return True

        # founder theo Membership role
        return resolve_user_role(u) == ROLE_FOUNDER