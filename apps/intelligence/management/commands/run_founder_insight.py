from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_date

from apps.intelligence.models import FounderInsightSnapshot, ShopActionItem
from apps.intelligence.notifier import send_webhook
from apps.intelligence.services import FounderIntelligenceService


def _has_field(model, name: str) -> bool:
    try:
        return any(f.name == name for f in model._meta.get_fields())
    except Exception:
        return False


# -----------------------------
# JSON SAFE
# -----------------------------
def _jsonify(x: Any) -> Any:
    if x is None:
        return None
    if isinstance(x, Decimal):
        return float(x)
    if isinstance(x, (date, datetime)):
        return x.isoformat()
    if is_dataclass(x):
        return _jsonify(asdict(x))
    if isinstance(x, dict):
        return {str(k): _jsonify(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_jsonify(v) for v in x]
    return x


# -----------------------------
# RULES
# -----------------------------
def _severity_from_action(action: Dict[str, Any], alerts: List[Dict[str, Any]]) -> str:
    shop_id = int(action.get("shop_id") or 0)

    for al in alerts:
        try:
            if int(al.get("shop_id") or 0) == shop_id and (al.get("severity") == "P0"):
                return "P0"
        except Exception:
            continue

    risk = str(action.get("risk_level") or "").upper()
    badge = str(action.get("health_badge") or "").upper()
    if risk == "HIGH" or badge == "CRITICAL":
        return "P1"
    return "P2"


def _due_from_severity(sev: str) -> Optional[datetime]:
    now = timezone.now()
    sev = (sev or "").upper()
    if sev == "P0":
        return now + timedelta(hours=24)
    if sev == "P1":
        return now + timedelta(days=3)
    if sev == "P2":
        return now + timedelta(days=7)
    return None


def _build_action_title(action: Dict[str, Any]) -> str:
    risk = action.get("risk_level", "")
    badge = action.get("health_badge", "")
    return f"[{risk}/{badge}] Action plan"


def _upsert_action_item(
    *,
    month: Optional[date],
    action: Dict[str, Any],
    severity: str,
    created_by=None,
) -> Tuple[ShopActionItem, bool]:
    shop_id = int(action.get("shop_id") or 0)
    title = _build_action_title(action)
    payload = _jsonify(action) or {}
    shop_name = str(action.get("shop_name") or "")
    company_name = str(action.get("company_name") or "")

    source_val = None
    if _has_field(ShopActionItem, "source"):
        source_val = getattr(ShopActionItem, "SOURCE_FOUNDER_INSIGHT", "founder_insight")

    # query theo key ổn định
    qs = ShopActionItem.objects.filter(month=month, shop_id=shop_id, title=title)
    if source_val is not None:
        qs = qs.filter(source=source_val)

    obj = qs.order_by("-id").first()

    # xác định frozen: DONE hoặc verified=True (nếu có field verified)
    def _is_verified(o) -> bool:
        if not _has_field(ShopActionItem, "verified"):
            return False
        try:
            return bool(getattr(o, "verified", False))
        except Exception:
            return False

    if obj:
        frozen = (obj.status == ShopActionItem.STATUS_DONE) or _is_verified(obj)

        obj.payload = payload
        obj.severity = severity
        if shop_name:
            obj.shop_name = shop_name
        if company_name:
            obj.company_name = company_name

        if _has_field(ShopActionItem, "due_at") and getattr(obj, "due_at", None) is None:
            obj.due_at = _due_from_severity(severity)

        # không reset status/owner/verified nếu frozen
        if not frozen:
            pass

        obj.save()
        return obj, False

    # Create mới: chỉ truyền các field thật sự tồn tại
    create_kwargs: Dict[str, Any] = {
        "month": month,
        "shop_id": shop_id,
        "shop_name": shop_name,
        "company_name": company_name,
        "title": title,
        "severity": severity,
        "status": ShopActionItem.STATUS_OPEN,
        "payload": payload,
    }

    if source_val is not None:
        create_kwargs["source"] = source_val

    if _has_field(ShopActionItem, "due_at"):
        create_kwargs["due_at"] = _due_from_severity(severity)

    if _has_field(ShopActionItem, "owner"):
        create_kwargs["owner"] = None

    if _has_field(ShopActionItem, "verified"):
        create_kwargs["verified"] = False

    obj = ShopActionItem.objects.create(**create_kwargs)
    return obj, True


class Command(BaseCommand):
    help = "Generate founder insight snapshot + upsert actions + notify P0"

    def add_arguments(self, parser):
        parser.add_argument("--month", type=str, default="", help="YYYY-MM-01 (vd: 2026-02-01). Bỏ trống = all-time")
        parser.add_argument("--commit", action="store_true", help="Ghi DB. Không có flag này = DRY RUN")
        parser.add_argument("--user-id", type=int, default=0, help="created_by cho snapshot (optional)")

    def handle(self, *args, **opts):
        month_str = (opts.get("month") or "").strip()
        commit = bool(opts.get("commit"))
        user_id = int(opts.get("user_id") or 0)

        month = parse_date(month_str) if month_str else None
        if month_str and not month:
            self.stdout.write(self.style.ERROR("month không hợp lệ. Dùng YYYY-MM-DD, ví dụ 2026-02-01"))
            return

        created_by = None
        if user_id:
            User = get_user_model()
            created_by = User.objects.filter(pk=user_id).first()

        ctx = FounderIntelligenceService.build_founder_context(month=month_str or None)

        alerts = _jsonify(ctx.get("alerts") or [])
        actions = _jsonify(ctx.get("actions") or [])
        forecast = _jsonify(ctx.get("forecast") or {})
        shop_health = _jsonify(ctx.get("shop_health") or [])
        insights = _jsonify(ctx.get("insights") or ctx.get("ceo_summary") or {})

        kpi = _jsonify({
            "total_revenue": ctx.get("total_revenue"),
            "total_profit": ctx.get("total_profit"),
            "total_net": ctx.get("total_net"),
            "margin": ctx.get("margin"),
        })

        p0 = [a for a in alerts if (a.get("severity") == "P0")]
        if p0:
            try:
                send_webhook({
                    "type": "FOUNDER_ALERT_P0",
                    "month": month_str or "all",
                    "count": len(p0),
                    "alerts": p0[:10],
                })
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"Webhook failed: {e}"))

        if not commit:
            self.stdout.write(self.style.WARNING("DRY RUN (no DB write). Use --commit to save."))
            self.stdout.write(self.style.SUCCESS(f"month={month_str or 'all'} alerts={len(alerts)} actions={len(actions)}"))
            return

        with transaction.atomic():
            snap = FounderInsightSnapshot.objects.create(
                month=month,
                kpi=kpi,
                forecast=forecast,
                alerts=alerts,
                actions=actions,
                insights=insights,
                shop_health=shop_health,
                created_by=created_by,
            )

            created = 0
            updated = 0

            for a in actions:
                sev = _severity_from_action(a, alerts)
                _, is_created = _upsert_action_item(
                    month=month,
                    action=a,
                    severity=sev,
                    created_by=created_by,
                )
                if is_created:
                    created += 1
                else:
                    updated += 1

        self.stdout.write(self.style.SUCCESS(
            f"Saved snapshot #{snap.pk} | actions: created={created}, updated={updated}"
        ))