from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from apps.os.ai_decision_engine import build_ai_decisions
from apps.os.contract_health_score import build_contract_health_score


@dataclass(frozen=True)
class MissionControlResult:
    status: str
    headline: Dict
    risks: List[Dict]
    actions: List[Dict]


def _agency_status(critical: int, warning: int) -> str:
    if critical > 0:
        return "critical"
    if warning > 0:
        return "warning"
    return "good"


def build_mission_control(
    *,
    tenant_id: int,
    company_id=None,
    shop_id=None,
    project_id=None,
):
    ai = build_ai_decisions(
        tenant_id=tenant_id,
        company_id=company_id,
        shop_id=shop_id,
        project_id=project_id,
        limit=5,
    )

    contract = build_contract_health_score(
        tenant_id=tenant_id,
        company_id=company_id,
        shop_id=shop_id,
        project_id=project_id,
        limit=10,
    )

    critical = ai.headline.get("ai_decision_critical", 0) + contract.headline.get(
        "contract_health_critical", 0
    )

    warning = ai.headline.get("ai_decision_warning", 0) + contract.headline.get(
        "contract_health_warning", 0
    )

    status = _agency_status(critical, warning)

    risks = []

    for x in ai.items[:3]:
        risks.append(
            {
                "title": x.get("title"),
                "summary": x.get("summary"),
                "priority": x.get("priority"),
            }
        )

    actions = []

    for x in ai.items[:3]:
        actions.append(
            {
                "title": x.get("title"),
                "action": x.get("action"),
                "priority": x.get("priority"),
            }
        )

    headline = {
        "status": status,
        "critical": critical,
        "warning": warning,
        "contracts_total": contract.headline.get("contract_health_total", 0),
    }

    return MissionControlResult(
        status=status,
        headline=headline,
        risks=risks,
        actions=actions,
    )