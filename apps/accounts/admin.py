from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Membership, User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ("id", "email", "username", "is_staff", "is_superuser", "is_active")
    ordering = ("email",)
    search_fields = ("email", "username", "first_name", "last_name")

    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("Thông tin cá nhân", {"fields": ("first_name", "last_name", "email")}),
        (
            "Phân quyền",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        ("Mốc thời gian", {"fields": ("last_login", "date_joined", "created_at")}),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("username", "email", "password1", "password2", "is_staff", "is_superuser"),
            },
        ),
    )

    readonly_fields = ("created_at", "last_login", "date_joined")


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "tenant", "company", "role", "is_active")
    list_filter = ("tenant", "company", "role", "is_active")
    search_fields = ("user__email", "user__username", "company__name", "tenant__name")