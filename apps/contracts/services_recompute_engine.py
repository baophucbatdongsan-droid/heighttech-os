from __future__ import annotations

from decimal import Decimal

from apps.contracts.models import (
    ContractChannelContent,
    ContractChannelInsightSnapshot,
)
from apps.contracts.services_auto_workitem import ensure_auto_task_for_content
from apps.contracts.services_content_ai import score_content
from apps.contracts.services_content_priority import decide_priority


def _to_decimal(v):
    try:
        return Decimal(str(v or 0))
    except Exception:
        return Decimal("0")


def recompute_content_engine(*, tenant_id: int, limit: int = 300) -> dict:
    contents = (
        ContractChannelContent.objects_all
        .filter(tenant_id=int(tenant_id))
        .prefetch_related("daily_metrics")
        .order_by("-id")[:limit]
    )

    processed = 0
    auto_tasks = 0
    snapshots = 0

    for item in contents:
        metrics = []
        total_views = 0
        total_orders = 0
        total_revenue = Decimal("0")

        try:
            for m in item.daily_metrics.all().order_by("-metric_date")[:14]:
                metrics.append({
                    "views": m.views,
                    "likes": m.likes,
                    "comments": m.comments,
                    "shares": m.shares,
                    "orders": m.orders,
                    "revenue": str(m.revenue or 0),
                })
                total_views += int(m.views or 0)
                total_orders += int(m.orders or 0)
                total_revenue += _to_decimal(m.revenue)
        except Exception:
            pass

        ai = score_content(metrics)

        row = {
            "status": item.status,
            "views_14d": total_views,
            "orders_14d": total_orders,
            "revenue_14d": float(total_revenue),
            "ai": ai,
        }
        priority = decide_priority(row)

        ContractChannelInsightSnapshot.objects_all.create(
            tenant_id=int(tenant_id),
            content=item,
            health_score=int(ai.get("health_score", 0) or 0),
            ai_label=str(ai.get("label") or ""),
            ai_recommendation=str(ai.get("recommendation") or ""),
            priority_score=int(priority.get("priority_score", 0) or 0),
            priority_label=str(priority.get("priority_label") or ""),
            priority_reason=str(priority.get("reason") or ""),
            action_hint=str(priority.get("action_hint") or ""),
            views_14d=int(total_views),
            orders_14d=int(total_orders),
            revenue_14d=total_revenue,
        )
        snapshots += 1

        if priority.get("priority_label") in ("scale_now", "produce_now", "fix_now"):
            ensure_auto_task_for_content(
                tenant_id=int(tenant_id),
                content=item,
                priority=priority,
                ai=ai,
                assignee_id=None,
            )
            auto_tasks += 1

        processed += 1

    return {
        "processed": processed,
        "snapshots": snapshots,
        "auto_tasks": auto_tasks,
    }