# apps/core/decorators.py
from __future__ import annotations

from functools import wraps

from django.http import HttpResponseForbidden

from apps.core.permissions import resolve_user_role
from apps.core.policy import role_has_ability


def require_ability(ability: str):
    def deco(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            user = request.user
            if not getattr(user, "is_authenticated", False):
                return HttpResponseForbidden("Forbidden")

            role = resolve_user_role(user)
            if not role_has_ability(role, ability):
                return HttpResponseForbidden("Forbidden: missing ability")

            return view_func(request, *args, **kwargs)

        return _wrapped

    return deco