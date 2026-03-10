from __future__ import annotations

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.contracts.services_content_work_sync import SYNC_FLAG_ATTR, sync_content_from_workitem
from apps.work.models import WorkItem

logger = logging.getLogger(__name__)


@receiver(post_save, sender=WorkItem)
def auto_sync_content_from_workitem(sender, instance: WorkItem, created: bool, **kwargs):
    try:
        if getattr(instance, SYNC_FLAG_ATTR, False):
            return

        setattr(instance, SYNC_FLAG_ATTR, True)
        try:
            content = sync_content_from_workitem(instance)
            if content:
                logger.info(
                    "Auto synced content from workitem",
                    extra={
                        "workitem_id": instance.id,
                        "content_id": content.id,
                        "content_status": content.status,
                        "tenant_id": getattr(instance, "tenant_id", None),
                    },
                )
        finally:
            setattr(instance, SYNC_FLAG_ATTR, False)

    except Exception as e:
        logger.exception("Failed auto syncing content from workitem: %s", e)