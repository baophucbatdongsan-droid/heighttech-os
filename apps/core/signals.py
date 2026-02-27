# apps/core/signals.py
from __future__ import annotations

from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver
from django.forms.models import model_to_dict

from apps.core.audit import log_create, log_update, log_delete, audit_signals_disabled
from apps.performance.models import MonthlyPerformance
from apps.shops.models import Shop
from apps.brands.models import Brand
from apps.companies.models import Company


def _snap(instance):
    if instance is None:
        return None
    try:
        data = model_to_dict(instance)
    except Exception:
        data = {}
    data["pk"] = str(getattr(instance, "pk", "") or "")
    return data


# -------------------------
# MonthlyPerformance
# -------------------------
@receiver(pre_save, sender=MonthlyPerformance, dispatch_uid="audit.perf.pre_save")
def perf_pre_save(sender, instance, **kwargs):
    if audit_signals_disabled():
        return

    if not instance.pk:
        instance._audit_before = None
        return

    old = sender._base_manager.filter(pk=instance.pk).first()
    instance._audit_before = _snap(old)


@receiver(post_save, sender=MonthlyPerformance, dispatch_uid="audit.perf.post_save")
def perf_post_save(sender, instance, created, **kwargs):
    if audit_signals_disabled():
        return

    if created:
        log_create(instance)
    else:
        log_update(instance, getattr(instance, "_audit_before", None))


@receiver(post_delete, sender=MonthlyPerformance, dispatch_uid="audit.perf.post_delete")
def perf_post_delete(sender, instance, **kwargs):
    if audit_signals_disabled():
        return

    log_delete(instance)


# -------------------------
# Generic audit for Shop/Brand/Company
# -------------------------
def _attach_generic_audit(Model, prefix: str):
    pre_uid = f"audit.{prefix}.pre_save"
    post_uid = f"audit.{prefix}.post_save"
    del_uid = f"audit.{prefix}.post_delete"

    @receiver(pre_save, sender=Model, dispatch_uid=pre_uid)
    def _pre(sender, instance, **kwargs):
        if audit_signals_disabled():
            return

        if not instance.pk:
            instance._audit_before = None
            return

        old = sender._base_manager.filter(pk=instance.pk).first()
        instance._audit_before = _snap(old)

    @receiver(post_save, sender=Model, dispatch_uid=post_uid)
    def _post(sender, instance, created, **kwargs):
        if audit_signals_disabled():
            return

        if created:
            log_create(instance)
        else:
            log_update(instance, getattr(instance, "_audit_before", None))

    @receiver(post_delete, sender=Model, dispatch_uid=del_uid)
    def _del(sender, instance, **kwargs):
        if audit_signals_disabled():
            return

        log_delete(instance)


_attach_generic_audit(Shop, "shop")
_attach_generic_audit(Brand, "brand")
_attach_generic_audit(Company, "company")