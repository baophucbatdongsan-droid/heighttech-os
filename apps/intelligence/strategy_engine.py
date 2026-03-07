# apps/intelligence/strategy_engine.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from django.utils import timezone

from apps.events.emit import emit_os_event
from apps.os.notifications_service import create_notification


# =========================================================
# Strategy V1: deterministic / rule-based
# - Không phụ thuộc DB model đặc thù
# - Input: context + risks
# - Output: list[StrategyPlan]
# =========================================================


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except Exception:
        return default


def _now_iso() -> str:
    return timezone.now().isoformat()


def _norm_severity(v: Any, default: str = "info") -> str:
    s = (str(v or "").strip().lower() or default).strip().lower()
    if s not in {"info", "warning", "critical", "high", "medium", "low"}:
        return default
    # map high/medium/low -> warning/info
    if s == "high":
        return "critical"
    if s == "medium":
        return "warning"
    if s == "low":
        return "info"
    return s


@dataclass
class StrategyAction:
    """
    Action chuẩn để chuyển qua Action Runner (run_actions):
      {"type": "...", "payload": {...}}
    """
    type: str
    payload: Dict[str, Any] = field(default_factory=dict)


@dataclass
class StrategyPlan:
    """
    1 plan = 1 chiến lược nhỏ (ngắn gọn, có action cụ thể)
    """
    id: str
    code: str
    title: str
    summary: str
    severity: str = "info"
    confidence: float = 0.7

    tenant_id: int = 0
    company_id: Optional[int] = None
    shop_id: Optional[int] = None
    project_id: Optional[int] = None

    risks: List[Dict[str, Any]] = field(default_factory=list)
    actions: List[StrategyAction] = field(default_factory=list)

    created_at: str = field(default_factory=_now_iso)
    meta: Dict[str, Any] = field(default_factory=dict)


# =========================================================
# Public API used by OSHomeApi
# =========================================================


def build_strategies(
    *,
    tenant_id: int,
    context: Dict[str, Any],
    risks: Optional[List[Dict[str, Any]]] = None,
    version: int = 1,
) -> List[StrategyPlan]:
    """
    V1 rules:
    - Nếu overdue_tasks cao -> plan tăng capacity + tạo task triage
    - Nếu shop health critical/low -> plan audit shop + tạo task review
    - Nếu risks có items -> tạo plan theo từng risk (nhẹ nhàng, không spam)
    """
    tenant_id = int(tenant_id)
    risks = risks or []
    ctx = context or {}

    plans: List[StrategyPlan] = []

    overdue = _safe_int(ctx.get("overdue_tasks"), 0)
    shops = ctx.get("shops_health") or []

    # -------------------------
    # Rule A: Overdue tasks cao
    # -------------------------
    if overdue >= 10:
        pid = f"pl_{uuid4().hex[:12]}"
        plans.append(
            StrategyPlan(
                id=pid,
                code="CAPACITY_INCREASE_OVERDUE",
                title="Giảm backlog quá hạn",
                summary=f"Đang có {overdue} task quá hạn. Cần tăng capacity & triage ngay hôm nay.",
                severity="warning" if overdue < 25 else "critical",
                confidence=0.8,
                tenant_id=tenant_id,
                actions=[
                    StrategyAction(
                        type="task.create",
                        payload={
                            "title": f"[OS] Triage backlog quá hạn ({overdue})",
                            "priority": 4 if overdue >= 25 else 3,
                            "target_type": "tenant",
                            "target_id": tenant_id,
                            "meta": {"rule": "overdue>=10", "overdue": overdue, "version": version},
                        },
                    ),
                    StrategyAction(
                        type="task.create",
                        payload={
                            "title": "[OS] Đề xuất tăng capacity xử lý task (phân công/thuê ngoài)",
                            "priority": 3,
                            "target_type": "tenant",
                            "target_id": tenant_id,
                            "meta": {"rule": "overdue>=10", "version": version},
                        },
                    ),
                ],
                meta={"version": version, "rule": "overdue>=10"},
            )
        )

    # -------------------------
    # Rule B: Shop health thấp
    # -------------------------
    # shops format (gợi ý): [{"shop_id": 1, "health_score": 55, ...}, ...]
    low_shops: List[Tuple[int, int]] = []
    critical_shops: List[Tuple[int, int]] = []

    for s in shops:
        sid = _safe_int((s or {}).get("shop_id") or (s or {}).get("id"), 0)
        score = _safe_int((s or {}).get("health_score"), 100)
        if not sid:
            continue
        if score <= 50:
            low_shops.append((sid, score))
        if score <= 30:
            critical_shops.append((sid, score))

    # Đừng spam: ưu tiên critical trước, lấy tối đa 5 shop/1 lần
    target_list = critical_shops[:5] if critical_shops else low_shops[:5]

    for sid, score in target_list:
        pid = f"pl_{uuid4().hex[:12]}"
        sev = "critical" if score <= 30 else "warning"
        plans.append(
            StrategyPlan(
                id=pid,
                code="SHOP_HEALTH_RECOVERY",
                title="Phục hồi hiệu suất shop",
                summary=f"Shop #{sid} health_score={score}. Cần audit ads/listing/vận hành để phục hồi.",
                severity=sev,
                confidence=0.75,
                tenant_id=tenant_id,
                shop_id=int(sid),
                actions=[
                    StrategyAction(
                        type="task.create",
                        payload={
                            "title": f"[OS] Audit Shop #{sid} (health {score})",
                            "priority": 4 if sev == "critical" else 3,
                            "target_type": "shop",
                            "target_id": int(sid),
                            "meta": {"rule": "health_score<=50", "health_score": score, "version": version},
                        },
                    ),
                    StrategyAction(
                        type="task.create",
                        payload={
                            "title": f"[OS] Kiểm tra ROAS/Orders/Revenue 7 ngày gần nhất cho Shop #{sid}",
                            "priority": 3,
                            "target_type": "shop",
                            "target_id": int(sid),
                            "meta": {"rule": "health_score<=50", "version": version},
                        },
                    ),
                ],
                meta={"version": version, "rule": "health_score<=50"},
            )
        )

    # -------------------------
    # Rule C: Convert risks -> plans
    # -------------------------
    # risks format tuỳ engine, em “bắt” nhẹ:
    #   [{"code": "...", "severity": "...", "title": "...", "detail": "...", "entity": {"type":"shop","id":..}}, ...]
    # Không spam quá 10
    for r in (risks or [])[:10]:
        code = (r or {}).get("code") or "RISK"
        title = (r or {}).get("title") or "Rủi ro hệ thống"
        detail = (r or {}).get("detail") or (r or {}).get("message") or ""
        sev = _norm_severity((r or {}).get("severity"), "warning")

        ent = (r or {}).get("entity") or {}
        ent_type = (ent or {}).get("type") or (ent or {}).get("kind")
        ent_id = _safe_int((ent or {}).get("id"), 0)

        pid = f"pl_{uuid4().hex[:12]}"
        plan = StrategyPlan(
            id=pid,
            code=f"RISK_{str(code).upper()}",
            title=str(title).strip() or "Rủi ro",
            summary=str(detail).strip() or "Cần kiểm tra rủi ro và xử lý theo checklist.",
            severity=sev,
            confidence=0.65,
            tenant_id=tenant_id,
            shop_id=int(ent_id) if ent_type == "shop" and ent_id else None,
            project_id=int(ent_id) if ent_type == "project" and ent_id else None,
            risks=[r],
            actions=[
                StrategyAction(
                    type="task.create",
                    payload={
                        "title": f"[OS] Xử lý rủi ro: {title}",
                        "priority": 4 if sev == "critical" else 3,
                        "target_type": str(ent_type or "tenant"),
                        "target_id": int(ent_id) if ent_id else tenant_id,
                        "meta": {"risk": r, "version": version},
                    },
                )
            ],
            meta={"version": version, "rule": "risk_to_plan"},
        )
        plans.append(plan)

    # -------------------------
    # Emit + Notification (fail-safe)
    # -------------------------
    _emit_strategy_created(tenant_id=tenant_id, plans=plans, version=version)

    return plans


def plans_to_dict(plans: List[StrategyPlan]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for p in plans or []:
        out.append(
            {
                "id": p.id,
                "code": p.code,
                "title": p.title,
                "summary": p.summary,
                "severity": p.severity,
                "confidence": float(p.confidence or 0),
                "tenant_id": p.tenant_id,
                "company_id": p.company_id,
                "shop_id": p.shop_id,
                "project_id": p.project_id,
                "risks": p.risks or [],
                "actions": [{"type": a.type, "payload": a.payload or {}} for a in (p.actions or [])],
                "created_at": p.created_at,
                "meta": p.meta or {},
            }
        )
    return out


# =========================================================
# Internal
# =========================================================


def _emit_strategy_created(*, tenant_id: int, plans: List[StrategyPlan], version: int) -> None:
    """
    Emit event + notify founder (public-safe, không crash).
    """
    try:
        emit_os_event(
            tenant_id=int(tenant_id),
            name="os.strategy.created",
            entity="tenant",
            entity_id=int(tenant_id),
            payload={
                "tom_tat": "OS vừa sinh chiến lược mới.",
                "so_ke_hoach": len(plans or []),
                "version": int(version),
            },
        )
    except Exception:
        pass

    try:
        if plans:
            create_notification(
                tenant_id=int(tenant_id),
                target_role="founder",
                severity="info",
                tieu_de="OS đã sinh chiến lược",
                noi_dung=f"Hệ thống vừa tạo {len(plans)} kế hoạch xử lý.",
                entity_kind="tenant",
                entity_id=int(tenant_id),
                meta={"version": int(version)},
            )
    except Exception:
        pass