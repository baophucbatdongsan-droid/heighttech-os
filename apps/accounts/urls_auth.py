# apps/accounts/urls_auth.py
from django.urls import path
from apps.accounts.views_auth import LoginView, logout_view

urlpatterns = [
    path("login/", LoginView.as_view(), name="login"),
    path("logout/", logout_view, name="logout"),
]