# apps/performance/signals.py
from __future__ import annotations

from django.core.exceptions import ValidationError
from django.core.cache import cache
from django.db import transaction
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from apps.finance.models import AgencyMonthlyFinance
from apps.finance.services import AgencyFinanceService
from apps.performance.models import MonthlyPerformance


# =====================================================
# CACHE HELPERS (safe for Redis + LocMemCache)
# =====================================================

def _cache_delete_pattern_safe(pattern: str) -> None:
    """
    - django-redis: cache.delete_pattern exists
    - LocMemCache: no delete_pattern -> fallback clear (dev ok)
    - Redis down: catch and ignore (avoid crash in signals)
    """
    try:
        if hasattr(cache, "delete_pattern"):
            cache.delete_pattern(pattern)  # type: ignore[attr-defined]
            return
    except Exception:
        # redis connection interrupted etc.
        pass

    try:
        cache.clear()
    except Exception:
        pass


def _clear_founder_cache() -> None:
    _cache_delete_pattern_safe("founder_ctx:*")
    _cache_delete_pattern_safe("founder_shop_ctx:*")


# =====================================================
# FINANCE SNAPSHOT HELPERS
# =====================================================

def _get_snapshot(month):
    return AgencyMonthlyFinance.objects.filter(month=month).first()


def _ensure_snapshot_open(month):
    """
    Nếu chưa có snapshot => tạo + tính.
    """
    AgencyFinanceService.calculate_or_update(month)


def _recalc_snapshot_if_open(month):
    """
    Recalc snapshot nếu OPEN.
    Nếu LOCKED/FINALIZED => skip.
    Nếu chưa có snapshot => tạo + tính.
    """
    snap = _get_snapshot(month)

    if snap is None:
        _ensure_snapshot_open(month)
        return

    if not snap.can_edit():
        return

    AgencyFinanceService.calculate_or_update(month)


# =====================================================
# GUARD: block edits on LOCKED/FINALIZED months
# =====================================================

@receiver(pre_save, sender=MonthlyPerformance)
def prevent_edit_when_month_closed(sender, instance: MonthlyPerformance, **kwargs):
    """
    Chặn:
    - Update vào tháng đã LOCKED/FINALIZED
    - Tạo mới vào tháng đã LOCKED/FINALIZED (nếu snapshot đã tồn tại & đóng)
    - Nếu update và đổi month: chặn nếu month cũ hoặc month mới đã đóng
    """
    old_month = None
    if instance.pk:
        old = sender.objects.filter(pk=instance.pk).only("month").first()
        if old:
            old_month = old.month

    new_month = instance.month

    # check old month (when changing month)
    if old_month and old_month != new_month:
        snap_old = _get_snapshot(old_month)
        if snap_old and snap_old.status in (
            AgencyMonthlyFinance.STATUS_LOCKED,
            AgencyMonthlyFinance.STATUS_FINALIZED,
        ):
            raise ValidationError(
                f"Tháng {old_month} đã {snap_old.status.upper()} - Không thể chuyển dữ liệu ra/vào tháng này."
            )

    # check new month
    snap_new = _get_snapshot(new_month)
    if snap_new and snap_new.status in (
        AgencyMonthlyFinance.STATUS_LOCKED,
        AgencyMonthlyFinance.STATUS_FINALIZED,
    ):
        raise ValidationError(
            f"Tháng {new_month} đã {snap_new.status.upper()} - Không thể tạo/sửa MonthlyPerformance."
        )


# =====================================================
# POST SAVE/DELETE: recalc snapshot (if OPEN) + clear caches
# =====================================================

def _after_commit(month):
    """
    Chạy sau commit để:
    - Recalc snapshot (OPEN)
    - Clear founder caches
    """
    try:
        _recalc_snapshot_if_open(month)
    finally:
        _clear_founder_cache()


@receiver(post_save, sender=MonthlyPerformance)
def performance_post_save(sender, instance: MonthlyPerformance, created, **kwargs):
    transaction.on_commit(lambda: _after_commit(instance.month))


@receiver(post_delete, sender=MonthlyPerformance)
def performance_post_delete(sender, instance: MonthlyPerformance, **kwargs):
    transaction.on_commit(lambda: _after_commit(instance.month))