from django.urls import path
from django.shortcuts import redirect

app_name = "legacy"

urlpatterns = [
    path("", lambda r: redirect("/app/")),
]