from __future__ import annotations

import logging

from celery import shared_task

from apps.contracts.alerts import run_contract_alerts
from apps.contracts.booking_workflow import run_booking_workflow

logger = logging.getLogger(__name__)


@shared_task(name="apps.contracts.tasks.contracts_alert_job")
def contracts_alert_job():
    alert_res = run_contract_alerts()
    workflow_res = run_booking_workflow()

    data = {
        "alerts": {
            "payments_due_today": alert_res.payments_due_today,
            "payments_overdue": alert_res.payments_overdue,
            "milestones_due_today": alert_res.milestones_due_today,
            "milestones_overdue": alert_res.milestones_overdue,
            "booking_payout_overdue": alert_res.booking_payout_overdue,
            "booking_air_passed_no_link": alert_res.booking_air_passed_no_link,
            "created_notifications": alert_res.created_notifications,
            "created_tasks": alert_res.created_tasks,
        },
        "booking_workflow": {
            "prep_created": workflow_res.prep_created,
            "waiting_link_created": workflow_res.waiting_link_created,
            "payout_created": workflow_res.payout_created,
            "auto_closed": workflow_res.auto_closed,
        },
    }

    logger.info("contracts_alert_job done: %s", data)
    return data


@shared_task(name="apps.contracts.tasks.booking_workflow_job")
def booking_workflow_job():
    res = run_booking_workflow()

    data = {
        "prep_created": res.prep_created,
        "waiting_link_created": res.waiting_link_created,
        "payout_created": res.payout_created,
        "auto_closed": res.auto_closed,
    }

    logger.info("booking_workflow_job done: %s", data)
    return data