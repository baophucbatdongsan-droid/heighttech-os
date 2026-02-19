# apps/api/v1/insight.py
from __future__ import annotations

from typing import Any, Dict, List, Optional

from rest_framework.permissions import IsAuthenticated

from apps.api.v1.base import BaseApi, api_ok
from apps.api.v1.permissions import AbilityPermission
from apps.core.policy import VIEW_API_FOUNDER
from apps.intelligence.services import FounderIntelligenceService


def _as_float(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


def _norm_risk(r: str) -> str:
    r = (r or "").upper()
    if r in ("HIGH", "MEDIUM", "LOW"):
        return r
    if r in ("MED",):
        return "MEDIUM"
    return "LOW"


def _bucket_risk(risk: str) -> int:
    # sort priority
    m = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    return m.get(_norm_risk(risk), 9)


def _pick_top(rows: List[Dict[str, Any]], *, n: int = 10) -> List[Dict[str, Any]]:
    return rows[: max(0, n)]


class FounderInsightApi(BaseApi):
    """
    GET /api/v1/founder/insight/?month=YYYY-MM-01
    Output:
      - summary (counts)
      - highlights (top risks, best growth, margin low, loss streak...)
      - alerts (already computed)
      - actions (already computed)
      - forecast (already computed)
    """
    permission_classes = [IsAuthenticated, AbilityPermission]
    required_ability = VIEW_API_FOUNDER

    def get(self, request):
        month: Optional[str] = request.GET.get("month") or None
        ctx = FounderIntelligenceService.build_founder_context(month=month)

        shop_health: List[Dict[str, Any]] = ctx.get("shop_health") or []
        alerts: List[Dict[str, Any]] = ctx.get("alerts") or []
        actions: List[Dict[str, Any]] = ctx.get("actions") or []
        forecast: Dict[str, Any] = ctx.get("forecast") or {}

        # ---- Normalize row fields (defensive) ----
        for r in shop_health:
            r["risk_level"] = _norm_risk(r.get("risk_level"))
            r["health_score"] = _as_float(r.get("health_score"))
            r["growth_mom"] = _as_float(r.get("growth_mom"))
            r["margin_last"] = _as_float(r.get("margin_last"))
            r["revenue_last"] = _as_float(r.get("revenue_last"))
            r["profit_last"] = _as_float(r.get("profit_last"))
            r["rank_percentile"] = _as_float(r.get("rank_percentile"))

        # ---- Build insight lists ----
        # 1) Top risk: HIGH/CRITICAL first, score thấp trước
        risk_sorted = sorted(
            shop_health,
            key=lambda r: (_bucket_risk(r.get("risk_level")), r.get("health_score", 999), -r.get("revenue_last", 0)),
        )
        top_risks = _pick_top(risk_sorted, n=10)

        # 2) Best growth (MoM)
        best_growth = sorted(shop_health, key=lambda r: r.get("growth_mom", -10**9), reverse=True)
        best_growth = [r for r in best_growth if r.get("growth_mom", 0) > 0]
        best_growth = _pick_top(best_growth, n=10)

        # 3) Worst growth (MoM)
        worst_growth = sorted(shop_health, key=lambda r: r.get("growth_mom", 10**9))
        worst_growth = [r for r in worst_growth if r.get("growth_mom", 0) < 0]
        worst_growth = _pick_top(worst_growth, n=10)

        # 4) Low margin
        low_margin = sorted(shop_health, key=lambda r: (r.get("margin_last", 999), r.get("health_score", 999)))
        low_margin = [r for r in low_margin if r.get("margin_last", 0) < 5]
        low_margin = _pick_top(low_margin, n=10)

        # 5) Loss streak flag (notes contains "Loss streak")
        loss_streak = [r for r in shop_health if "Loss streak" in (r.get("notes") or "")]
        loss_streak.sort(key=lambda r: (r.get("health_score", 999), -r.get("revenue_last", 0)))
        loss_streak = _pick_top(loss_streak, n=10)

        # ---- Summary counts ----
        total = len(shop_health)
        count_high = sum(1 for r in shop_health if r.get("risk_level") == "HIGH")
        count_med = sum(1 for r in shop_health if r.get("risk_level") == "MEDIUM")
        count_low = sum(1 for r in shop_health if r.get("risk_level") == "LOW")

        p0 = sum(1 for a in alerts if (a.get("severity") or "").upper() == "P0")
        p1 = sum(1 for a in alerts if (a.get("severity") or "").upper() == "P1")

        data = {
            "filters": {"month": month or ""},
            "summary": {
                "shops_total": total,
                "risk_high": count_high,
                "risk_medium": count_med,
                "risk_low": count_low,
                "alerts_p0": p0,
                "alerts_p1": p1,
            },
            "highlights": {
                "top_risks": top_risks,
                "best_growth": best_growth,
                "worst_growth": worst_growth,
                "low_margin": low_margin,
                "loss_streak": loss_streak,
            },
            "alerts": alerts[:50],
            "actions": actions[:30],
            "forecast": forecast,
        }
        return api_ok(data)