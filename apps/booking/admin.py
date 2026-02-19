from __future__ import annotations

from django.contrib import admin

from .models import Booking, BookingItem


class BookingItemInline(admin.TabularInline):
    model = BookingItem
    extra = 0


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ("id", "tenant", "company", "shop", "code", "status", "amount", "scheduled_at", "created_at")
    list_filter = ("status", "company")
    search_fields = ("code", "title")
    inlines = [BookingItemInline]