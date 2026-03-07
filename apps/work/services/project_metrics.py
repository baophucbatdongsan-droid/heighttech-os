from django.utils import timezone
from apps.work.models import WorkItem

def recalc_project_metrics(project):
    if not project:
        return

    qs = WorkItem.objects.filter(project_id=project.id)

    total = qs.exclude(status=WorkItem.Status.CANCELLED).count()
    done = qs.filter(status=WorkItem.Status.DONE).count()

    progress = 0
    if total > 0:
        progress = int(round((done / total) * 100))

    project.progress_percent = progress

    now = timezone.now()
    overdue = qs.filter(
        due_at__isnull=False,
        due_at__lt=now,
    ).exclude(status__in=[WorkItem.Status.DONE, WorkItem.Status.CANCELLED]).count()

    penalty = min(50, overdue * 5)
    project.health_score = max(0, 100 - penalty)

    project.save(update_fields=["progress_percent", "health_score", "updated_at"])