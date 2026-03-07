# apps/accounts/views_auth.py
from __future__ import annotations

from django.contrib.auth import logout
from django.contrib.auth.views import LoginView as DjangoLoginView
from django.shortcuts import redirect
from django.urls import reverse

from apps.core.authz import get_actor_ctx


class LoginView(DjangoLoginView):
    template_name = "auth/login.html"

    def get_success_url(self):
        ctx = get_actor_ctx(self.request)
        if ctx.role in ("founder", "admin"):
            return reverse("founder:home")
        return reverse("app:home")


def logout_view(request):
    logout(request)
    return redirect("login")