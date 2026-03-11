from __future__ import annotations

from django.contrib.auth import login, logout
from django.shortcuts import redirect, render
from django.views import View

from .forms_auth import EmailLoginForm
from .forms_register import RegisterForm


class LoginView(View):
    template_name = "auth/login.html"

    def get(self, request):
        # nếu đã login → vào OS
        if request.user.is_authenticated:
            return redirect("/os/")

        form = EmailLoginForm(request=request)
        return render(request, self.template_name, {"form": form})

    def post(self, request):
        # nếu đã login → vào OS
        if request.user.is_authenticated:
            return redirect("/os/")

        form = EmailLoginForm(request=request, data=request.POST)

        if form.is_valid():
            user = form.get_user()

            # login bằng backend email
            login(request, user, backend="apps.accounts.backends.EmailAuthBackend")

            next_url = request.GET.get("next") or "/os/"
            return redirect(next_url)

        return render(request, self.template_name, {"form": form})


class RegisterView(View):
    template_name = "auth/register.html"

    def get(self, request):
        # đã login thì không cần register
        if request.user.is_authenticated:
            return redirect("/os/")

        form = RegisterForm()
        return render(request, self.template_name, {"form": form})

    def post(self, request):
        if request.user.is_authenticated:
            return redirect("/os/")

        form = RegisterForm(request.POST)

        if form.is_valid():
            result = form.save()

            # lấy user từ result
            user = result["user"]

            # login luôn sau khi tạo workspace
            login(request, user, backend="apps.accounts.backends.EmailAuthBackend")

            return redirect("/os/")

        return render(request, self.template_name, {"form": form})


class LogoutView(View):

    def get(self, request):
        logout(request)
        return redirect("/login/")

    def post(self, request):
        logout(request)
        return redirect("/login/")