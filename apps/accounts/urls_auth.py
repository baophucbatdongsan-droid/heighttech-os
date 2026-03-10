from __future__ import annotations

from django.urls import path

from .views_auth import LoginView, LogoutView, RegisterView

urlpatterns = [
    path("login/", LoginView.as_view(), name="login"),
    path("register/", RegisterView.as_view(), name="register"),
    path("logout/", LogoutView.as_view(), name="logout"),
]