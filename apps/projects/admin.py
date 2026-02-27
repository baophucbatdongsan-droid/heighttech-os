from django.contrib import admin
from .models import Project, ProjectShop


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "type", "company", "status", "owner")
    list_filter = ("type", "status")
    search_fields = ("name",)


@admin.register(ProjectShop)
class ProjectShopAdmin(admin.ModelAdmin):
    list_display = ("id", "project", "shop", "role", "status", "assigned_pm")
    list_filter = ("role", "status")