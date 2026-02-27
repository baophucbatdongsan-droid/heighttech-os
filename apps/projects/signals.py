# apps/projects/signals.py
from __future__ import annotations

from django.core.cache import cache
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from apps.projects.models import Project, ProjectShop


def _bump_key(tid: int) -> str:
    return f"dash_projects_bump:{tid}"


def bump_dashboard_cache(tid: int):
    try:
        cache.incr(_bump_key(int(tid)), ignore_key_check=True)
    except Exception:
        # fallback: set tăng thủ công
        k = _bump_key(int(tid))
        try:
            v = int(cache.get(k) or 0) + 1
        except Exception:
            v = 1
        cache.set(k, v, 24 * 3600)


@receiver(post_save, sender=Project)
def _project_saved(sender, instance: Project, **kwargs):
    if getattr(instance, "tenant_id", None):
        bump_dashboard_cache(instance.tenant_id)


@receiver(post_delete, sender=Project)
def _project_deleted(sender, instance: Project, **kwargs):
    if getattr(instance, "tenant_id", None):
        bump_dashboard_cache(instance.tenant_id)


@receiver(post_save, sender=ProjectShop)
def _projectshop_saved(sender, instance: ProjectShop, **kwargs):
    if getattr(instance, "tenant_id", None):
        bump_dashboard_cache(instance.tenant_id)


@receiver(post_delete, sender=ProjectShop)
def _projectshop_deleted(sender, instance: ProjectShop, **kwargs):
    if getattr(instance, "tenant_id", None):
        bump_dashboard_cache(instance.tenant_id)