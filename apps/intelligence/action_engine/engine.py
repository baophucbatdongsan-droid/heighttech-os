from django.apps import apps
from django.utils import timezone
from .rules import RULES


class ActionEngine:

    def __init__(self, tenant_id):
        self.tenant_id = tenant_id

    def run(self):
        results = []

        for rule in RULES:
            fn = getattr(self, rule["check"], None)
            if fn:
                res = fn(rule)
                if res:
                    results.extend(res)

        return results


    def shop_no_order(self, rule):
        Shop = apps.get_model("shops", "Shop")

        shops = Shop.objects_all.filter(tenant_id=self.tenant_id)

        alerts = []

        for s in shops:

            last_order = getattr(s, "last_order_at", None)

            if not last_order:
                alerts.append({
                    "type": "shop_alert",
                    "shop_id": s.id,
                    "title": rule["title"],
                    "severity": rule["severity"]
                })

        return alerts


    def task_overdue(self, rule):

        WorkItem = apps.get_model("work", "WorkItem")

        qs = WorkItem.objects_all.filter(
            tenant_id=self.tenant_id,
            due_at__lt=timezone.now()
        ).exclude(status="done")

        alerts = []

        for t in qs[:20]:

            alerts.append({
                "type": "task_alert",
                "task_id": t.id,
                "title": rule["title"],
                "severity": rule["severity"]
            })

        return alerts