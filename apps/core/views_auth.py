# apps/core/views_auth.py
from __future__ import annotations

from django.contrib.auth import authenticate, login, logout
from django.http import HttpRequest
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from apps.accounts.models import InviteCode


def _is_privileged_user(user) -> bool:
    return bool(user and (getattr(user, "is_staff", False) or getattr(user, "is_superuser", False)))


def _validate_invite(code_raw: str) -> InviteCode | None:
    code = (code_raw or "").strip()
    if not code:
        return None
    ic = InviteCode.objects.filter(code=code, is_active=True).first()
    if not ic or not ic.can_use():
        return None
    return ic


@require_http_methods(["GET", "POST"])
def login_view(request: HttpRequest):
    if getattr(request, "user", None) and request.user.is_authenticated:
        return redirect("/")

    error: str | None = None
    username = ""

    if request.method == "POST":
        username = (request.POST.get("username") or "").strip()
        password = (request.POST.get("password") or "").strip()
        invite_code = (request.POST.get("invite_code") or "").strip()

        user = authenticate(request, username=username, password=password)
        if user is None:
            error = "BAD_CREDENTIALS"
        else:
            # ✅ Invite Gate: user thường phải có invite
            if not _is_privileged_user(user):
                ic = _validate_invite(invite_code)
                if ic is None:
                    error = "INVITE_REQUIRED"
                else:
                    login(request, user)
                    try:
                        ic.mark_used()
                    except Exception:
                        pass
                    nxt = (request.GET.get("next") or "").strip()
                    return redirect(nxt or "/")
            else:
                login(request, user)
                nxt = (request.GET.get("next") or "").strip()
                return redirect(nxt or "/")

    return render(request, "core/login.html", {"error": error, "username": username})


def logout_view(request: HttpRequest):
    logout(request)
    return redirect("/login/")