from __future__ import annotations

from datetime import timedelta
from typing import Optional

from django.db.models import Q
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.v1.insight import FounderInsightApi, _get_tenant_id
from apps.contracts.models import ContractBookingItem, ContractMilestone, ContractPayment
from apps.work.models import WorkItem
from apps.core.permissions import resolve_user_role
from apps.intelligence.action_runner import run_actions
from apps.intelligence.decision_engine import run_decisions
from apps.intelligence.risk_engine import detect_risks
from apps.intelligence.strategy_actions import plans_to_actions
from apps.intelligence.strategy_engine import build_strategies, plans_to_dict
from apps.os.ui_schema import build_os_ui_schema
from apps.contracts.timeline_engine import build_contract_timeline
from apps.contracts.radar_engine import build_contract_radar
from apps.os.founder_dashboard import build_founder_dashboard
from apps.os.shop_risk_radar import build_shop_risk_radar
from apps.os.cashflow_radar import build_cashflow_radar
from apps.os.revenue_prediction import build_revenue_prediction
from apps.os.ai_decision_engine import build_ai_decisions
from apps.os.contract_health_score import build_contract_health_score
from apps.os.mission_control import build_mission_control
from apps.os.agency_health_score import build_agency_health_score
from apps.os.shop_brain import build_shop_brain
from apps.os.product_radar import build_product_radar
from apps.os.shop_services_overview import build_shop_services_overview
from apps.os.shop_service_timeline import build_shop_service_timeline
from apps.os.shop_command_center import build_shop_command_center
from apps.os.shop_ai_actions import build_shop_ai_actions
from apps.os.shop_mission_digest import build_shop_mission_digest
from apps.os.shop_kpi_strip import build_shop_kpi_strip


CONTRACT_SOON_DAYS = 3
BOOKING_PAYOUT_SOON_DAYS = 3
BOOKING_AIR_SOON_DAYS = 2


def _int_or_none(v: Optional[str]) -> Optional[int]:
    try:
        if v is None:
            return None
        s = str(v).strip()
        if not s:
            return None
        return int(s)
    except Exception:
        return None


def _contract_alert_summary(
    *,
    tenant_id: int,
    company_id=None,
    shop_id=None,
    project_id=None,
):
    now = timezone.now()
    pay_soon = now + timedelta(days=CONTRACT_SOON_DAYS)
    payout_soon = now + timedelta(days=BOOKING_PAYOUT_SOON_DAYS)
    air_soon = now + timedelta(days=BOOKING_AIR_SOON_DAYS)

    payment_qs = ContractPayment.objects_all.select_related("contract").filter(
        tenant_id=int(tenant_id),
        status__in=[ContractPayment.Status.PENDING, ContractPayment.Status.PARTIAL],
    )

    if company_id:
        payment_qs = payment_qs.filter(contract__company_id=int(company_id))

    if shop_id:
        payment_qs = payment_qs.filter(
            contract__contract_shops__shop_id=int(shop_id)
        ).distinct()

    payment_overdue = payment_qs.filter(due_at__lt=now).count()
    payment_due_soon = payment_qs.filter(due_at__gte=now, due_at__lte=pay_soon).count()

    milestone_qs = ContractMilestone.objects_all.select_related("contract").filter(
        tenant_id=int(tenant_id),
        status__in=[ContractMilestone.Status.TODO, ContractMilestone.Status.DOING],
    )

    if company_id:
        milestone_qs = milestone_qs.filter(contract__company_id=int(company_id))

    if shop_id:
        milestone_qs = milestone_qs.filter(
            Q(shop_id=int(shop_id)) | Q(contract__contract_shops__shop_id=int(shop_id))
        ).distinct()

    milestone_overdue = milestone_qs.filter(due_at__lt=now).count()
    milestone_due_soon = milestone_qs.filter(due_at__gte=now, due_at__lte=pay_soon).count()

    payout_qs = ContractBookingItem.objects_all.select_related("contract", "shop").filter(
        tenant_id=int(tenant_id),
        payout_status=ContractBookingItem.PayoutStatus.PENDING,
    )

    if company_id:
        payout_qs = payout_qs.filter(contract__company_id=int(company_id))

    if shop_id:
        payout_qs = payout_qs.filter(shop_id=int(shop_id))

    booking_payout_overdue = payout_qs.filter(payout_due_at__lt=now).count()
    booking_payout_due_soon = payout_qs.filter(
        payout_due_at__gte=now,
        payout_due_at__lte=payout_soon,
    ).count()

    air_qs = ContractBookingItem.objects_all.select_related("contract", "shop").filter(
        tenant_id=int(tenant_id),
        air_date__isnull=False,
    )

    if company_id:
        air_qs = air_qs.filter(contract__company_id=int(company_id))

    if shop_id:
        air_qs = air_qs.filter(shop_id=int(shop_id))

    booking_air_soon = air_qs.filter(air_date__gte=now, air_date__lte=air_soon).count()
    booking_air_passed_no_link = air_qs.filter(air_date__lt=now).filter(
        Q(video_link__isnull=True) | Q(video_link="")
    ).count()

    cards = []

    if payment_overdue:
        cards.append(
            {
                "title": "Thanh toán hợp đồng quá hạn",
                "summary": f"Có {payment_overdue} khoản thanh toán hợp đồng đã quá hạn.",
                "priority": "critical",
                "kind": "contract_payment_overdue",
            }
        )

    if milestone_overdue:
        cards.append(
            {
                "title": "Mốc hợp đồng quá hạn",
                "summary": f"Có {milestone_overdue} milestone / nghiệm thu đang quá hạn.",
                "priority": "critical",
                "kind": "contract_milestone_overdue",
            }
        )

    if payment_due_soon:
        cards.append(
            {
                "title": "Thanh toán hợp đồng sắp đến hạn",
                "summary": f"Có {payment_due_soon} khoản thanh toán hợp đồng đến hạn trong {CONTRACT_SOON_DAYS} ngày.",
                "priority": "warning",
                "kind": "contract_payment_due_soon",
            }
        )

    if milestone_due_soon:
        cards.append(
            {
                "title": "Mốc hợp đồng sắp đến hạn",
                "summary": f"Có {milestone_due_soon} milestone / nghiệm thu đến hạn trong {CONTRACT_SOON_DAYS} ngày.",
                "priority": "warning",
                "kind": "contract_milestone_due_soon",
            }
        )

    if booking_payout_overdue:
        cards.append(
            {
                "title": "Payout KOC quá hạn",
                "summary": f"Có {booking_payout_overdue} payout KOC đã quá hạn thanh toán.",
                "priority": "critical",
                "kind": "booking_payout_overdue",
            }
        )

    if booking_payout_due_soon:
        cards.append(
            {
                "title": "Payout KOC sắp đến hạn",
                "summary": f"Có {booking_payout_due_soon} payout KOC đến hạn trong {BOOKING_PAYOUT_SOON_DAYS} ngày.",
                "priority": "warning",
                "kind": "booking_payout_due_soon",
            }
        )

    if booking_air_soon:
        cards.append(
            {
                "title": "Video KOC sắp air",
                "summary": f"Có {booking_air_soon} video KOC sắp đến air date trong {BOOKING_AIR_SOON_DAYS} ngày.",
                "priority": "info",
                "kind": "booking_air_soon",
            }
        )

    if booking_air_passed_no_link:
        cards.append(
            {
                "title": "Quá air date nhưng chưa có link video",
                "summary": f"Có {booking_air_passed_no_link} booking đã qua air date nhưng chưa cập nhật link video.",
                "priority": "warning",
                "kind": "booking_air_passed_no_link",
            }
        )

    return {
        "headline": {
            "contract_payment_overdue": payment_overdue,
            "contract_payment_due_soon": payment_due_soon,
            "contract_milestone_overdue": milestone_overdue,
            "contract_milestone_due_soon": milestone_due_soon,
            "booking_payout_overdue": booking_payout_overdue,
            "booking_payout_due_soon": booking_payout_due_soon,
            "booking_air_soon": booking_air_soon,
            "booking_air_passed_no_link": booking_air_passed_no_link,
        },
        "items": cards[:8],
    }
def _contract_work_summary(
    *,
    tenant_id: int,
    company_id=None,
    shop_id=None,
    project_id=None,
):
    qs = WorkItem.objects_all.filter(
        tenant_id=int(tenant_id),
        target_type__in=[
            "contract_payment",
            "contract_milestone",
            "contract_booking_item",
        ],
    ).exclude(status__in=[WorkItem.Status.DONE, WorkItem.Status.CANCELLED])

    if company_id:
        qs = qs.filter(company_id=int(company_id))

    if shop_id:
        qs = qs.filter(shop_id=int(shop_id))

    if project_id:
        qs = qs.filter(project_id=int(project_id))

    now = timezone.now()

    open_count = qs.count()
    overdue_count = qs.filter(due_at__isnull=False, due_at__lt=now).count()
    urgent_count = qs.filter(priority=WorkItem.Priority.URGENT).count()

    items = []
    for x in qs.order_by("-priority", "due_at", "-id")[:8]:
        items.append(
            {
                "id": x.id,
                "title": x.title,
                "description": x.description or "",
                "status": x.status,
                "priority": int(x.priority or 0),
                "company_id": x.company_id,
                "shop_id": x.shop_id,
                "project_id": x.project_id,
                "target_type": x.target_type or "",
                "target_id": x.target_id,
                "due_at": x.due_at.isoformat() if x.due_at else None,
                "updated_at": x.updated_at.isoformat() if x.updated_at else None,
            }
        )

    return {
        "headline": {
            "contract_work_open": open_count,
            "contract_work_overdue": overdue_count,
            "contract_work_urgent": urgent_count,
        },
        "items": items,
    }
class OSHomeApi(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        tenant_id = _get_tenant_id(request)
        if not tenant_id:
            return Response({"ok": False, "message": "Thiếu tenant_id"}, status=400)

        tenant_id = int(tenant_id)

        try:
            role = (resolve_user_role(request.user) or "operator").strip().lower()
        except Exception:
            role = "operator"

        scope = (request.query_params.get("scope") or "tenant").strip().lower()
        company_id = _int_or_none(request.query_params.get("company_id"))
        shop_id = _int_or_none(request.query_params.get("shop_id"))
        project_id = _int_or_none(request.query_params.get("project_id"))

        try:
            ui_schema = build_os_ui_schema(tenant_id=tenant_id, role=role)
        except TypeError:
            ui_schema = build_os_ui_schema(tenant_id=tenant_id)

        insight_resp = FounderInsightApi().get(request)
        insight = getattr(insight_resp, "data", {}) or {}

        overview = insight.get("overview") or {}
        tasks_block = overview.get("tasks") or {}
        shops = insight.get("shops") or []

        context = {
            "tenant_id": tenant_id,
            "role": role,
            "scope": scope,
            "company_id": company_id,
            "shop_id": shop_id,
            "project_id": project_id,
            "overdue_tasks": int(tasks_block.get("overdue") or 0),
            "shops_health": shops,
            "overview": overview,
        }

        decisions = run_decisions(tenant_id=tenant_id, context=context)
        action_results = run_actions(
            tenant_id=tenant_id,
            actions=getattr(decisions, "actions", []) or [],
        )

        risks = detect_risks(context)

        plans = build_strategies(
            tenant_id=tenant_id,
            context=context,
            risks=risks,
        )
        plans_dict = plans_to_dict(plans)

        actions_from_strategy = plans_to_actions(plans_dict)
        action_results_strategy = run_actions(
            tenant_id=tenant_id,
            actions=actions_from_strategy,
        )

        def _is_risk(x):
            lv = str((x or {}).get("level") or (x or {}).get("status") or "").lower()
            return lv in ("high", "critical", "risk")

        work_open = int(
            tasks_block.get("open")
            or tasks_block.get("total_open")
            or tasks_block.get("open_count")
            or 0
        )

        actions_open = len(getattr(decisions, "actions", []) or [])

        headline = {
            "shops_total": len(shops),
            "shops_risk": len([x for x in shops if _is_risk(x)]),
            "work_open": work_open,
            "actions_open": actions_open,
        }

        quyet_dinh = {
            "canh_bao": getattr(decisions, "alerts", []) or [],
            "goi_y": getattr(decisions, "recommendations", []) or [],
            "hanh_dong": getattr(decisions, "actions", []) or [],
        }

        blocks = {
            "overview": overview,
            "alerts": insight.get("alerts") or [],
            "recommendations": insight.get("recommendations") or [],
            "shops_health": shops,
            "tasks": tasks_block,
            "events": overview.get("events") or [],
        }

        chien_luoc = plans_dict

        contract_alerts = _contract_alert_summary(
            tenant_id=int(tenant_id),
            company_id=company_id,
            shop_id=shop_id,
            project_id=project_id,
        )
        contract_work = _contract_work_summary(
            tenant_id=int(tenant_id),
            company_id=company_id,
            shop_id=shop_id,
            project_id=project_id,
        )
        contract_timeline = build_contract_timeline(
            tenant_id=int(tenant_id),
            company_id=company_id,
            shop_id=shop_id,
            project_id=project_id,
            limit=10,
        )
        contract_radar = build_contract_radar(
            tenant_id=int(tenant_id),
            company_id=company_id,
            shop_id=shop_id,
        )
        founder_dashboard = build_founder_dashboard(
            tenant_id=int(tenant_id),
            company_id=company_id,
            shop_id=shop_id,
            project_id=project_id,
        )
        shop_risk_radar = build_shop_risk_radar(
            tenant_id=int(tenant_id),
            company_id=company_id,
            shop_id=shop_id,
            project_id=project_id,
            limit=8,
        )
        cashflow_radar = build_cashflow_radar(
            tenant_id=int(tenant_id),
            company_id=company_id,
            shop_id=shop_id,
        )
        revenue_prediction = build_revenue_prediction(
            tenant_id=int(tenant_id),
            company_id=company_id,
            shop_id=shop_id,
        )
        ai_decisions = build_ai_decisions(
            tenant_id=int(tenant_id),
            company_id=company_id,
            shop_id=shop_id,
            project_id=project_id,
            limit=8,
        )
        contract_health_score = build_contract_health_score(
            tenant_id=int(tenant_id),
            company_id=company_id,
            shop_id=shop_id,
            project_id=project_id,
            limit=10,
        )
        mission_control = build_mission_control(
            tenant_id=int(tenant_id),
            company_id=company_id,
            shop_id=shop_id,
            project_id=project_id,
        )
        agency_health = build_agency_health_score(
            tenant_id=int(tenant_id),
            company_id=company_id,
            shop_id=shop_id,
            project_id=project_id,
        )
        shop_brain = build_shop_brain(
            tenant_id=int(tenant_id),
            shop_id=shop_id,
        )
        product_radar = build_product_radar(
            tenant_id=int(tenant_id),
            company_id=company_id,
            shop_id=shop_id,
            days=30,
            limit=5,
        )
        shop_services_overview = build_shop_services_overview(
            tenant_id=int(tenant_id),
            company_id=company_id,
            shop_id=shop_id,
            limit=20,
        )
        shop_service_timeline = build_shop_service_timeline(
            tenant_id=int(tenant_id),
            company_id=company_id,
            shop_id=shop_id,
            days=14,
            limit=20,
        )
        shop_command_center = build_shop_command_center(
            tenant_id=int(tenant_id),
            company_id=company_id,
            shop_id=shop_id,
        )
        shop_ai_actions = build_shop_ai_actions(
            tenant_id=int(tenant_id),
            company_id=company_id,
            shop_id=shop_id,
            limit=8,
        )
        shop_mission_digest = build_shop_mission_digest(
            tenant_id=int(tenant_id),
            company_id=company_id,
            shop_id=shop_id,
            limit=3,
        )
        shop_kpi_strip = build_shop_kpi_strip(
            tenant_id=int(tenant_id),
            company_id=company_id,
            shop_id=shop_id,
        )

        if not isinstance(headline, dict):
            headline = {}

        headline.update(contract_alerts.get("headline", {}) or {})
        headline.update(contract_work.get("headline", {}) or {})
        headline.update(getattr(contract_timeline, "headline", {}) or {})
        headline.update(getattr(founder_dashboard, "headline", {}) or {})
        headline.update(getattr(shop_risk_radar, "headline", {}) or {})
        headline.update(getattr(cashflow_radar, "headline", {}) or {})
        headline.update(getattr(revenue_prediction, "headline", {}) or {})
        headline.update(getattr(ai_decisions, "headline", {}) or {})
        headline.update(getattr(contract_health_score, "headline", {}) or {})
        headline.update(getattr(mission_control, "headline", {}) or {})
        headline.update(getattr(product_radar, "headline", {}) or {})
        headline.update(getattr(shop_services_overview, "headline", {}) or {})
        headline.update(getattr(shop_service_timeline, "headline", {}) or {})
        headline.update(getattr(shop_command_center, "headline", {}) or {})
        headline.update(getattr(shop_ai_actions, "headline", {}) or {})
        headline.update(getattr(shop_mission_digest, "headline", {}) or {})
        headline.update(getattr(shop_kpi_strip, "headline", {}) or {})

        if not isinstance(blocks, dict):
            blocks = {}

        blocks["contracts_alerts"] = contract_alerts
        blocks["contract_work"] = contract_work
        blocks["contract_timeline"] = {
            "headline": getattr(contract_timeline, "headline", {}) or {},
            "items": getattr(contract_timeline, "items", []) or [],
        }
        blocks["contract_radar"] = contract_radar
        blocks["founder_dashboard"] = {
            "headline": getattr(founder_dashboard, "headline", {}) or {},
            "blocks": getattr(founder_dashboard, "blocks", {}) or {},
        }
        blocks["shop_risk_radar"] = {
            "headline": getattr(shop_risk_radar, "headline", {}) or {},
            "items": getattr(shop_risk_radar, "items", []) or [],
        }
        blocks["cashflow_radar"] = {
            "headline": getattr(cashflow_radar, "headline", {}) or {},
            "items": getattr(cashflow_radar, "items", []) or [],
        }
        blocks["revenue_prediction"] = {
            "headline": getattr(revenue_prediction, "headline", {}) or {},
            "items": getattr(revenue_prediction, "items", []) or [],
        }
        blocks["ai_decisions"] = {
            "headline": getattr(ai_decisions, "headline", {}) or {},
            "items": getattr(ai_decisions, "items", []) or [],
        }
        blocks["contract_health_score"] = {
            "headline": getattr(contract_health_score, "headline", {}) or {},
            "items": getattr(contract_health_score, "items", []) or [],
        }
        blocks["mission_control"] = {
            "headline": getattr(mission_control, "headline", {}) or {},
            "risks": getattr(mission_control, "risks", []) or [],
            "actions": getattr(mission_control, "actions", []) or [],
        }
        blocks["agency_health"] = {
            "score": getattr(agency_health, "score", 0),
            "blocks": getattr(agency_health, "blocks", {}),
        }
        blocks["shop_brain"] = {
            "headline": getattr(shop_brain, "headline", {}),
            "daily_mission": getattr(shop_brain, "daily_mission", []),
            "risks": getattr(shop_brain, "risks", []),
            "growth": getattr(shop_brain, "growth", []),
        }
        blocks["product_radar"] = {
            "headline": getattr(product_radar, "headline", {}) or {},
            "blocks": getattr(product_radar, "blocks", {}) or {},
        }
        blocks["shop_services_overview"] = {
            "headline": getattr(shop_services_overview, "headline", {}) or {},
            "items": getattr(shop_services_overview, "items", []) or [],
        }
        blocks["shop_service_timeline"] = {
            "headline": getattr(shop_service_timeline, "headline", {}) or {},
            "items": getattr(shop_service_timeline, "items", []) or [],
        }
        blocks["shop_command_center"] = {
            "headline": getattr(shop_command_center, "headline", {}) or {},
            "missions": getattr(shop_command_center, "missions", []) or [],
        }
        blocks["shop_ai_actions"] = {
            "headline": getattr(shop_ai_actions, "headline", {}) or {},
            "items": getattr(shop_ai_actions, "items", []) or [],
        }
        blocks["shop_mission_digest"] = {
            "headline": getattr(shop_mission_digest, "headline", {}) or {},
            "items": getattr(shop_mission_digest, "items", []) or [],
        }
        blocks["shop_kpi_strip"] = {
            "headline": getattr(shop_kpi_strip, "headline", {}) or {},
            "items": getattr(shop_kpi_strip, "items", []) or [],
        }
        contract_items = contract_alerts.get("items", []) or []

        if isinstance(chien_luoc, list):
            chien_luoc = contract_items + chien_luoc
        elif isinstance(chien_luoc, dict):
            if isinstance(chien_luoc.get("items"), list):
                chien_luoc["items"] = contract_items + chien_luoc["items"]
            elif isinstance(chien_luoc.get("plans"), list):
                chien_luoc["plans"] = contract_items + chien_luoc["plans"]

        if not isinstance(quyet_dinh, dict):
            quyet_dinh = {}

        goi_y = quyet_dinh.get("goi_y")
        if isinstance(goi_y, list) and contract_items:
            quyet_dinh["goi_y"] = contract_items + goi_y
        elif contract_items and "goi_y" not in quyet_dinh:
            quyet_dinh["goi_y"] = contract_items

        return Response(
            {
                "ok": True,
                "generated_at": timezone.now().isoformat(),
                "tenant_id": tenant_id,
                "role": role,
                "scope": scope,
                "filters": {
                    "company_id": company_id,
                    "shop_id": shop_id,
                    "project_id": project_id,
                },
                "ui_schema": ui_schema or {},
                "headline": headline,
                "quyet_dinh": quyet_dinh,
                "ket_qua_hanh_dong": action_results,
                "rui_ro": risks,
                "chien_luoc": chien_luoc,
                "ket_qua_hanh_dong_chien_luoc": action_results_strategy,
                "layout": [
                    "shop_kpi_strip"
                    "shop_mission_digest",
                    "shop_command_center",
                    "shop_ai_actions"
                    "mission_control",
                    "agency_health",
                    "shop_brain",
                    "product_radar",
                    "shop_services_overview",
                    "shop_service_timeline",
                    "overview",
                    "founder_dashboard",
                    "cashflow_radar",
                    "revenue_prediction",
                    "shop_risk_radar",
                    "ai_decisions",
                    "contract_health_score",
                    "contracts_alerts",
                    "contract_work",
                    "contract_timeline",
                    "contract_radar",
                    "alerts",
                    "recommendations",
                    "shops_health",
                    "tasks",
                    "events",                   
                ],
                "blocks": blocks,
            }
        )