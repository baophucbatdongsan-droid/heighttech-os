from __future__ import annotations

from django.utils import timezone

from apps.contracts.models import ContractChannelContent
from apps.work.models import WorkItem


SYNC_FLAG_ATTR = "_content_sync_in_progress"


def _normalize(s: str) -> str:
    return str(s or "").strip().lower()


def sync_content_from_workitem(workitem: WorkItem) -> ContractChannelContent | None:
    """
    Đồng bộ ngược từ WorkItem sang ContractChannelContent.
    Chỉ áp dụng khi:
      target_type = contract_channel_content
      target_id tồn tại
    """

    if getattr(workitem, SYNC_FLAG_ATTR, False):
        return None

    if _normalize(getattr(workitem, "target_type", "")) != "contract_channel_content":
        return None

    content_id = getattr(workitem, "target_id", None)
    tenant_id = getattr(workitem, "tenant_id", None)
    if not content_id or not tenant_id:
        return None

    content = ContractChannelContent.objects_all.filter(
        id=int(content_id),
        tenant_id=int(tenant_id),
    ).first()
    if not content:
        return None

    wi_status = _normalize(getattr(workitem, "status", ""))
    wi_title = _normalize(getattr(workitem, "title", ""))

    update_fields = []
    current_status = _normalize(content.status)

    # doing => content vào production nếu còn đang ở đầu pipeline
    if wi_status == WorkItem.Status.DOING:
        if current_status in {"idea", "script", "pre_production"}:
            content.status = ContractChannelContent.Status.PRODUCTION
            update_fields.append("status")

    # done => suy luận theo title
    elif wi_status == WorkItem.Status.DONE:
        if "air" in wi_title or "đăng" in wi_title or "publish" in wi_title:
            if current_status != ContractChannelContent.Status.AIRED:
                content.status = ContractChannelContent.Status.AIRED
                update_fields.append("status")
            if not content.aired_at:
                content.aired_at = timezone.now()
                update_fields.append("aired_at")

        elif "hook" in wi_title or "cta" in wi_title or "sửa" in wi_title or "fix" in wi_title:
            if current_status != ContractChannelContent.Status.AIRED:
                content.status = ContractChannelContent.Status.SCHEDULED
                update_fields.append("status")

        elif "quay" in wi_title or "production" in wi_title or "dựng" in wi_title or "hoàn thiện" in wi_title:
            if current_status in {
                ContractChannelContent.Status.IDEA,
                ContractChannelContent.Status.SCRIPT,
                ContractChannelContent.Status.PRE_PRODUCTION,
                ContractChannelContent.Status.PRODUCTION,
                ContractChannelContent.Status.POST_PRODUCTION,
            }:
                content.status = ContractChannelContent.Status.SCHEDULED
                update_fields.append("status")

        elif "concept" in wi_title or "nhân bản" in wi_title or "scale" in wi_title:
            if current_status == ContractChannelContent.Status.IDEA:
                content.status = ContractChannelContent.Status.SCRIPT
                update_fields.append("status")

    if update_fields:
        content.save(update_fields=list(dict.fromkeys(update_fields + ["updated_at"])))

    return content