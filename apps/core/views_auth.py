# apps/core/views_auth.py
from __future__ import annotations

from django.contrib.auth import authenticate, login, logout
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods


@require_http_methods(["GET", "POST"])
def login_view(request):
    # đã login rồi thì đá về dashboard
    if request.user.is_authenticated:
        return redirect("/dashboard/")

    if request.method == "POST":
        username = (request.POST.get("username") or "").strip()
        password = (request.POST.get("password") or "").strip()

        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            # ưu tiên next nếu có
            next_url = request.GET.get("next") or "/dashboard/"
            return redirect(next_url)

        return render(
            request,
            "core/login.html",
            {"error": "Sai tài khoản hoặc mật khẩu."},
        )

    return render(request, "core/login.html")


@require_http_methods(["POST", "GET"])
def logout_view(request):
    logout(request)
    return redirect("/login/")