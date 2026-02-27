from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from django.db import transaction
from django.utils import timezone

from apps.work.models import WorkItem, WorkComment
from apps.core.audit import log_change


@dataclass(frozen=True)
class WorkCreateInput:
    title: str
    description: str = ""
    status: str = WorkItem.Status.TODO
    priority: int = WorkItem.Priority.NORMAL
    tags: list[str] | None = None
    due_at: Optional[timezone.datetime] = None

    company_id: int | None = None
    project_id: int | None = None

    target_type: str = ""
    target_id: int | None = None

    assignee_id: int | None = None
    requester_id: int | None = None


class WorkService:
    @staticmethod
    @transaction.atomic
    def create(*, tenant_id: int, actor_id: int | None, data: WorkCreateInput) -> WorkItem:
        item = WorkItem.objects_all.create(  # dùng objects_all vì tenant middleware có thể chưa set context
            tenant_id=tenant_id,
            title=data.title.strip(),
            description=(data.description or "").strip(),
            status=data.status,
            priority=int(data.priority),
            tags=data.tags or [],
            due_at=data.due_at,

            company_id=data.company_id,
            project_id=data.project_id,
            target_type=(data.target_type or "").strip(),
            target_id=data.target_id,

            created_by_id=actor_id,
            assignee_id=data.assignee_id,
            requester_id=data.requester_id,
        )

        WorkComment.objects_all.create(
            tenant_id=tenant_id,
            work_item_id=item.id,
            actor_id=actor_id,
            body="Created",
            meta={"status": item.status, "priority": item.priority},
        )

        log_change(
            action="work_created",
            model="work.WorkItem",
            object_id=item.id,
            tenant_id=tenant_id,
            meta={
                "status": item.status,
                "priority": item.priority,
                "target_type": item.target_type,
                "target_id": item.target_id,
            },
        )
        return item

    @staticmethod
    @transaction.atomic
    def change_status(*, item: WorkItem, actor_id: int | None, new_status: str, note: str = "") -> WorkItem:
        old = item.status
        if old == new_status:
            return item

        item.status = new_status
        if new_status == WorkItem.Status.DOING and not item.started_at:
            item.started_at = timezone.now()
        if new_status in (WorkItem.Status.DONE, WorkItem.Status.CANCELLED):
            item.done_at = timezone.now()
        if new_status not in (WorkItem.Status.DONE, WorkItem.Status.CANCELLED):
            item.done_at = None

        item.save(update_fields=["status", "started_at", "done_at", "updated_at"])

        WorkComment.objects_all.create(
            tenant_id=item.tenant_id,
            work_item_id=item.id,
            actor_id=actor_id,
            body=note.strip() or f"Status: {old} → {new_status}",
            meta={"from": old, "to": new_status},
        )

        log_change(
            action="work_status_changed",
            model="work.WorkItem",
            object_id=item.id,
            tenant_id=item.tenant_id,
            meta={"from": old, "to": new_status},
        )
        return item

    @staticmethod
    @transaction.atomic
    def add_comment(*, item: WorkItem, actor_id: int | None, body: str, meta: dict | None = None) -> WorkComment:
        c = WorkComment.objects_all.create(
            tenant_id=item.tenant_id,
            work_item_id=item.id,
            actor_id=actor_id,
            body=(body or "").strip(),
            meta=meta or {},
        )
        log_change(
            action="work_comment_added",
            model="work.WorkComment",
            object_id=c.id,
            tenant_id=item.tenant_id,
            meta={"work_item_id": item.id},
        )
        return c