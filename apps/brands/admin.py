# apps/brands/admin.py
from django.contrib import admin
from .models import Brand


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "company", "is_active", "created_at")
    list_filter = ("is_active", "company")
    search_fields = ("name", "company__name")  # ✅ BẮT BUỘC nếu dùng autocomplete ở nơi khác
    ordering = ("-id",)

    # ✅ chỉ giữ dòng này nếu Company đã có admin + search_fields
    autocomplete_fields = ("company",)