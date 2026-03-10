from __future__ import annotations

from typing import Optional

from django.contrib.auth import get_user_model

from apps.contracts.models import ContractChannelContent
from apps.contracts.services_assignment_intelligence import (
    infer_role_key_from_task,
    pick_assignee_for_role,
)
from apps.work.models import WorkItem

User = get_user_model()


def _task_title_for_priority(content: ContractChannelContent, priority_label: str) -> str:
    base = content.title or f"Content#{content.id}"

    if priority_label == "scale_now":
        return f"[AI] Nhân bản concept • {base}"

    if priority_label == "produce_now":
        return f"[AI] Hoàn thiện & air • {base}"

    if priority_label == "fix_now":
        return f"[AI] Sửa hook / CTA • {base}"

    return f"[AI] Theo dõi content • {base}"


def _task_description_for_priority(content: ContractChannelContent, priority: dict, ai: dict) -> str:
    lines = [
        f"Content: {content.title or ''}",
        f"Priority: {priority.get('priority_label', '')}",
        f"Priority score: {priority.get('priority_score', 0)}",
        f"AI health score: {ai.get('health_score', 0)}",
        f"Reason: {priority.get('reason', '')}",
        f"Action hint: {priority.get('action_hint', '')}",
        f"AI recommendation: {ai.get('recommendation', '')}",
    ]

    if content.video_link:
        lines.append(f"Video link: {content.video_link}")

    return "\n".join(lines)


def _priority_to_status(priority_label: str) -> str:
    return WorkItem.Status.TODO


def _priority_to_priority(priority_label: str) -> int:
    if priority_label == "scale_now":
        return WorkItem.Priority.URGENT
    if priority_label in ("produce_now", "fix_now"):
        return WorkItem.Priority.HIGH
    return WorkItem.Priority.NORMAL


def ensure_auto_task_for_content(
    *,
    tenant_id: int,
    content: ContractChannelContent,
    priority: dict,
    ai: dict,
    assignee_id: Optional[int] = None,
) -> WorkItem:
    """
    Tạo/cập nhật task AI cho content.
    Có assignment intelligence:
    - tự suy luận role
    - tự tìm assignee nếu tenant có người phù hợp
    """
    existing = WorkItem.objects_all.filter(
        tenant_id=int(tenant_id),
        target_type="contract_channel_content",
        target_id=content.id,
        title__icontains="[AI]",
    ).first()

    title = _task_title_for_priority(content, str(priority.get("priority_label") or ""))
    description = _task_description_for_priority(content, priority, ai)
    status = _priority_to_status(str(priority.get("priority_label") or ""))
    priority_value = _priority_to_priority(str(priority.get("priority_label") or ""))

    assignee = None

    # 1) nếu caller truyền rõ assignee thì ưu tiên
    if assignee_id:
        assignee = User.objects.filter(id=assignee_id).first()

    # 2) nếu chưa có thì tự suy luận
    if not assignee:
        role_key = infer_role_key_from_task(
            title=title,
            description=description,
            priority_label=str(priority.get("priority_label") or ""),
        )
        assignee = pick_assignee_for_role(
            tenant_id=int(tenant_id),
            role_key=role_key,
        )

    if existing:
        existing.title = title
        existing.description = description
        existing.status = status
        existing.priority = priority_value
        existing.company_id = content.company_id
        existing.shop_id = content.shop_id
        if assignee:
            existing.assignee = assignee
        existing._actor = None
        existing.save()
        return existing

    item = WorkItem(
        tenant_id=int(tenant_id),
        company_id=content.company_id,
        shop_id=content.shop_id,
        project_id=None,
        title=title,
        description=description,
        status=status,
        priority=priority_value,
        type=WorkItem.Type.TASK,
        target_type="contract_channel_content",
        target_id=content.id,
        visible_to_client=False,
        is_internal=True,
        assignee=assignee,
    )
    item._actor = None
    item.save()
    return item