# apps/work/urls.py
from __future__ import annotations

from django.urls import path

from .views_os import (
    os_home,
    os_my_work,
    os_item_detail,
    os_create_quick,
    os_transition,
    os_assign,
    os_update_meta,
)
from .views_client import client_work_home

app_name = "work"

urlpatterns = [
    # =========================
    # INTERNAL OS (staff/agency)
    # URL base: /work/
    # =========================
    path("", os_home, name="os_home"),
    path("my/", os_my_work, name="os_my_work"),
    path("item/<int:item_id>/", os_item_detail, name="os_item_detail"),

    path("quick-create/", os_create_quick, name="os_create_quick"),
    path("item/<int:item_id>/transition/", os_transition, name="os_transition"),
    path("item/<int:item_id>/assign/", os_assign, name="os_assign"),
    path("item/<int:item_id>/update-meta/", os_update_meta, name="os_update_meta"),

    # =========================
    # CLIENT PORTAL
    # URL base: /work/client/
    # =========================
    path("client/", client_work_home, name="client_work_home"),
]