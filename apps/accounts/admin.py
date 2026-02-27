from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, Membership


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ("username", "email", "is_staff", "is_superuser")
    ordering = ("username",)


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "company", "role", "is_active")
    list_filter = ("company", "role", "is_active")