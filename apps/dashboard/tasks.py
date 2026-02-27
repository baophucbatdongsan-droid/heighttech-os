from celery import shared_task
from django.core.cache import cache

@shared_task
def warmup_tenant_dashboard(tenant_id: int):
    # TODO: thay bằng query tổng hợp thật
    cache.set(f"dash:tenant:{tenant_id}", {"ok": True}, timeout=300)
    return True

from celery import shared_task
from django.core.cache import cache

@shared_task
def warmup_all_tenants_dashboard():
    from apps.tenants.models import Tenant

    tenant_ids = list(Tenant.objects.filter(is_active=True).values_list("id", flat=True))
    for tid in tenant_ids:
        warmup_tenant_dashboard.delay(int(tid))
    return len(tenant_ids)

@shared_task
def warmup_tenant_dashboard(tenant_id: int):
    # TODO: thay bằng số liệu “Founder cần”: doanh thu, lợi nhuận, SLA, lỗi, vv.
    data = {
        "tenant_id": tenant_id,
        "ok": True,
        "ts": __import__("time").time(),
    }
    cache.set(f"dash:tenant:{tenant_id}", data, timeout=300)
    return True