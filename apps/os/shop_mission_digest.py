from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from apps.os.shop_ai_actions import build_shop_ai_actions
from apps.os.shop_command_center import build_shop_command_center


@dataclass(frozen=True)
class ShopMissionDigestResult:
    headline: Dict[str, Any]
    items: List[Dict[str, Any]]


def build_shop_mission_digest(
    *,
    tenant_id: int,
    company_id: Optional[int] = None,
    shop_id: Optional[int] = None,
    limit: int = 3,
) -> ShopMissionDigestResult:
    command_center = build_shop_command_center(
        tenant_id=int(tenant_id),
        company_id=company_id,
        shop_id=shop_id,
    )

    ai_actions = build_shop_ai_actions(
        tenant_id=int(tenant_id),
        company_id=company_id,
        shop_id=shop_id,
        limit=8,
    )

    items: List[Dict[str, Any]] = []

    for x in (getattr(command_center, "missions", []) or [])[:3]:
        items.append(
            {
                "source": "command_center",
                "priority": x.get("priority") or "info",
                "title": x.get("title") or "Mission",
                "summary": x.get("summary") or "",
            }
        )

    for x in (getattr(ai_actions, "items", []) or [])[:5]:
        items.append(
            {
                "source": "ai_actions",
                "priority": x.get("priority") or "info",
                "title": x.get("title") or "Action",
                "summary": x.get("action") or x.get("summary") or "",
            }
        )

    rank = {"critical": 0, "warning": 1, "info": 2}
    dedup: List[Dict[str, Any]] = []
    seen = set()

    for x in sorted(items, key=lambda v: (rank.get(v.get("priority") or "info", 9), v.get("title") or "")):
        key = (x.get("title"), x.get("summary"))
        if key in seen:
            continue
        seen.add(key)
        dedup.append(x)

    final_items = dedup[: max(1, int(limit or 3))]

    headline = {
        "shop_mission_digest_total": len(final_items),
        "shop_mission_digest_critical": len([x for x in final_items if x.get("priority") == "critical"]),
        "shop_mission_digest_warning": len([x for x in final_items if x.get("priority") == "warning"]),
    }

    return ShopMissionDigestResult(
        headline=headline,
        items=final_items,
    )