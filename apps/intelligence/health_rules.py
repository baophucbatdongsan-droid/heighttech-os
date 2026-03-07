# apps/intelligence/health_rules.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass(frozen=True)
class MetricRule:
    key: str
    label: str
    weight: int  # total weights sum to 100 ideally
    # score mapping: (value) -> (0..100)
    # we implement as simple thresholds
    thresholds: List[Tuple[float, int]]  # (min_value, score) sorted asc
    # if lower_is_better=True then invert logic
    lower_is_better: bool = False


def _score_by_thresholds(value: Optional[float], thresholds: List[Tuple[float, int]], lower_is_better: bool) -> int:
    if value is None:
        return 0

    try:
        v = float(value)
    except Exception:
        return 0

    # thresholds: list of (min_value, score) ascending by min_value
    if not lower_is_better:
        s = 0
        for min_v, score in thresholds:
            if v >= float(min_v):
                s = int(score)
        return max(0, min(100, s))

    # lower is better: we convert by comparing against max boundaries
    # Here thresholds min_value means "max allowed" when lower_is_better.
    # Example: [(0.0, 100), (0.1, 80), (0.2, 60), (0.4, 30)]
    s = 0
    for max_v, score in thresholds:
        if v <= float(max_v):
            s = int(score)
            break
    if s == 0:
        s = int(thresholds[-1][1]) if thresholds else 0
    return max(0, min(100, s))


def default_rules() -> List[MetricRule]:
    """
    V1 rules: đủ xài cho Beta.
    Anh có thể tinh chỉnh weight/thresholds sau, không cần migrate DB.

    Metrics keys (engine sẽ cố lấy nếu có dữ liệu):
    - roas_7d
    - revenue_7d
    - orders_7d
    - overdue_tasks
    - blocked_tasks
    - backlog_open_tasks
    - low_stock_skus
    """
    return [
        MetricRule(
            key="roas_7d",
            label="ROAS (7d)",
            weight=30,
            thresholds=[(0.5, 10), (1.0, 30), (1.5, 50), (2.0, 70), (3.0, 90), (4.0, 100)],
        ),
        MetricRule(
            key="revenue_7d",
            label="Revenue (7d)",
            weight=20,
            thresholds=[(1_000_000, 10), (5_000_000, 30), (10_000_000, 50), (30_000_000, 70), (80_000_000, 90), (150_000_000, 100)],
        ),
        MetricRule(
            key="orders_7d",
            label="Orders (7d)",
            weight=15,
            thresholds=[(1, 10), (10, 30), (30, 50), (80, 70), (150, 90), (300, 100)],
        ),
        MetricRule(
            key="overdue_tasks",
            label="Overdue tasks",
            weight=15,
            thresholds=[(0.0, 100), (1.0, 85), (3.0, 70), (5.0, 50), (10.0, 30), (20.0, 10)],
            lower_is_better=True,
        ),
        MetricRule(
            key="blocked_tasks",
            label="Blocked tasks",
            weight=10,
            thresholds=[(0.0, 100), (1.0, 80), (3.0, 60), (5.0, 40), (10.0, 20)],
            lower_is_better=True,
        ),
        MetricRule(
            key="low_stock_skus",
            label="Low stock SKUs",
            weight=10,
            thresholds=[(0.0, 100), (1.0, 85), (3.0, 70), (5.0, 55), (10.0, 35), (30.0, 15)],
            lower_is_better=True,
        ),
    ]


def compute_weighted_score(metrics: Dict[str, Optional[float]], rules: Optional[List[MetricRule]] = None) -> Dict[str, object]:
    rules = rules or default_rules()

    parts = []
    total_weight = sum(max(0, int(r.weight)) for r in rules) or 1

    weighted_sum = 0.0
    for r in rules:
        w = max(0, int(r.weight))
        val = metrics.get(r.key)
        score = _score_by_thresholds(val, r.thresholds, r.lower_is_better)
        weighted_sum += (score * w)
        parts.append(
            {
                "key": r.key,
                "label": r.label,
                "weight": w,
                "value": val,
                "score": score,
            }
        )

    overall = int(round(weighted_sum / total_weight))
    overall = max(0, min(100, overall))

    level = "good"
    if overall < 40:
        level = "critical"
    elif overall < 60:
        level = "warning"

    return {
        "score": overall,
        "level": level,
        "parts": parts,
    }