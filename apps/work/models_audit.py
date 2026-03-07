# apps/work/models.py
from django.conf import settings
from django.db import models

class WorkItemTransitionLog(models.Model):
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE)
    company = models.ForeignKey("companies.Company", on_delete=models.CASCADE)
    project = models.ForeignKey("projects.Project", on_delete=models.CASCADE)
    workitem = models.ForeignKey("work.WorkItem", on_delete=models.CASCADE, related_name="transition_logs")

    from_status = models.CharField(max_length=50)
    to_status = models.CharField(max_length=50)

    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    reason = models.TextField(blank=True, default="")

    request_id = models.CharField(max_length=64, blank=True, default="")
    trace_id = models.CharField(max_length=64, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["tenant", "company", "project", "workitem", "created_at"]),
        ]
        ordering = ["-id"]