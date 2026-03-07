# apps/intelligence/decision_engine.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from apps.events.emit import emit_os_event
from apps.os.notifications_service import create_notification


@dataclass
class DecisionResult:
    alerts: List[Dict[str, Any]]
    recommendations: List[Dict[str, Any]]
    actions: List[Dict[str, Any]]


def _safe_int(v, default: int = 0) -> int:
    try:
        return int(v)
    except Exception:
        return default


def run_decisions(*, tenant_id: int, context: Dict[str, Any]) -> DecisionResult:
    """
    Decision Engine V1 (rule-based, deterministic).
    - Input: context (đã aggregate từ insight/dashboard/work/perf...)
    - Output:
        alerts: cảnh báo cho UI
        recommendations: gợi ý cho UI
        actions: hành động để action_runner thực thi (tạo task, escalate, ...)
    Đồng thời:
        - Emit outbox event (os.decision.created) để timeline hiển thị
        - Tạo notification cho founder (optional beta)
    """

    alerts: List[Dict[str, Any]] = []
    recs: List[Dict[str, Any]] = []
    actions: List[Dict[str, Any]] = []

    # 1) Quá hạn nhiều
    overdue = _safe_int(context.get("overdue_tasks", 0), 0)
    if overdue >= 10:
        alerts.append(
            {
                "code": "TASK_OVERDUE_HIGH",
                "severity": "high",
                "title": "Nhiều công việc quá hạn",
                "detail": f"Số công việc quá hạn = {overdue}",
            }
        )
        recs.append(
            {
                "code": "INCREASE_CAPACITY",
                "title": "Tăng năng lực xử lý công việc",
                "reason": "Số công việc quá hạn đang cao",
                "confidence": 0.7,
            }
        )

    # 2) Shop health thấp
    shops = context.get("shops_health") or []
    for s in shops:
        shop_id = s.get("shop_id") or s.get("id")
        score = _safe_int(s.get("health_score", 100), 100)

        if score <= 50 and shop_id:
            alerts.append(
                {
                    "code": "SHOP_HEALTH_LOW",
                    "severity": "medium",
                    "title": "Shop có điểm sức khoẻ thấp",
                    "entity": {"type": "shop", "id": int(shop_id)},
                    "detail": f"health_score = {score}",
                }
            )
            actions.append(
                {
                    "type": "task.create",
                    "payload": {
                        "title": f"(OS) Rà soát sức khoẻ Shop #{int(shop_id)}",
                        "priority": 3,
                        "target_type": "shop",
                        "target_id": int(shop_id),
                        "note": f"Shop health_score={score} (<=50).",
                    },
                }
            )

    result = DecisionResult(alerts=alerts, recommendations=recs, actions=actions)

    # =========================
    # Emit event + notification (1 lần)
    # =========================
    try:
        emit_os_event(
            tenant_id=int(tenant_id),
            name="os.decision.created",
            entity="tenant",
            entity_id=int(tenant_id),
            payload={
                "so_canh_bao": len(result.alerts),
                "so_goi_y": len(result.recommendations),
                "so_hanh_dong": len(result.actions),
                "tom_tat": "OS vừa sinh quyết định mới.",
            },
        )
    except Exception:
        pass

    # Founder notification (beta): chỉ bắn khi có gì đó đáng nói
    try:
        if result.alerts or result.recommendations or result.actions:
            create_notification(
                tenant_id=int(tenant_id),
                target_role="founder",
                severity="info",
                tieu_de="OS vừa cập nhật quyết định",
                noi_dung=f"Cảnh báo: {len(result.alerts)} • Gợi ý: {len(result.recommendations)} • Hành động: {len(result.actions)}",
                entity_kind="tenant",
                entity_id=int(tenant_id),
                meta={
                    "alerts": result.alerts[:5],
                    "recommendations": result.recommendations[:5],
                    "actions": result.actions[:5],
                },
            )
    except Exception:
        pass

    return result