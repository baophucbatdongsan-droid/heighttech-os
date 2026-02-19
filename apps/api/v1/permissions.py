from rest_framework.permissions import BasePermission

# ===============================
# ROLE CONSTANTS
# ===============================
ROLE_FOUNDER = "founder"
ROLE_HEAD = "head"
ROLE_ACCOUNT = "account"
ROLE_SALE = "sale"
ROLE_OPERATOR = "operator"
ROLE_CLIENT = "client"
ROLE_NONE = "none"

# ===============================
# ABILITY CONSTANTS
# ===============================
VIEW_API_DASHBOARD = "api:view_dashboard"
VIEW_API_FOUNDER = "api:view_founder"

# ===============================
# ROLE → ABILITY POLICY
# ===============================
ROLE_TO_ABILITIES = {
    ROLE_FOUNDER: {
        VIEW_API_DASHBOARD,
        VIEW_API_FOUNDER,
    },
    ROLE_CLIENT: {
        VIEW_API_DASHBOARD,
    },
    ROLE_OPERATOR: {
        VIEW_API_DASHBOARD,
    },
    ROLE_ACCOUNT: {
        VIEW_API_DASHBOARD,
    },
    ROLE_HEAD: {
        VIEW_API_DASHBOARD,
    },
    ROLE_SALE: {
        VIEW_API_DASHBOARD,
    },
}

# ===============================
# ROLE RESOLUTION
# ===============================
def resolve_user_role(user) -> str:
    if not user or not user.is_authenticated:
        return ROLE_NONE

    if user.is_superuser:
        return ROLE_FOUNDER

    # membership based
    from apps.accounts.models import Membership
    m = Membership.objects.filter(user=user, is_active=True).first()
    if not m:
        return ROLE_NONE

    role = (m.role or "").lower()

    if role in ROLE_TO_ABILITIES:
        return role

    return ROLE_CLIENT


# ===============================
# ABILITY CHECK
# ===============================
def role_has_ability(role: str, ability: str) -> bool:
    role = (role or ROLE_NONE).lower()
    return ability in ROLE_TO_ABILITIES.get(role, set())


# ===============================
# DRF Permission Class
# ===============================
class AbilityPermission(BasePermission):
    message = "Forbidden: missing ability"

    def has_permission(self, request, view):
        required = getattr(view, "required_ability", None)
        if not required:
            return True

        user = request.user
        role = resolve_user_role(user)

        return role_has_ability(role, required)
    
from rest_framework.permissions import BasePermission
from apps.core.permissions import is_founder

class FounderOnlyPermission(BasePermission):
    message = "Founder only"

    def has_permission(self, request, view):
        u = getattr(request, "user", None)
        if not getattr(u, "is_authenticated", False):
            return False
        return bool(getattr(u, "is_superuser", False) or is_founder(u))
from rest_framework.permissions import BasePermission
from apps.core.permissions import is_founder

class FounderOnlyPermission(BasePermission):
    message = "Founder only"

    def has_permission(self, request, view):
        u = getattr(request, "user", None)
        if not getattr(u, "is_authenticated", False):
            return False
        return bool(getattr(u, "is_superuser", False) or is_founder(u))
    
from rest_framework.permissions import BasePermission
from apps.core.permissions import is_founder

class FounderOnlyPermission(BasePermission):
    message = "Founder only"

    def has_permission(self, request, view):
        u = getattr(request, "user", None)
        if not getattr(u, "is_authenticated", False):
            return False
        return bool(getattr(u, "is_superuser", False) or is_founder(u))