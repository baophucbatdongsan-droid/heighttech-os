from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.core.tenant_context import set_current_tenant
from apps.core.audit import audit_disabled, disable_audit_signals
from apps.tenants.models import Tenant
from apps.projects.models import Project
from apps.work.models import WorkItem


def _project_status_active():
    # ưu tiên ProjectStatus enum nếu có
    try:
        from apps.projects.models import ProjectStatus
        return ProjectStatus.ACTIVE
    except Exception:
        return "active"


def _project_status_paused():
    try:
        from apps.projects.models import ProjectStatus
        return ProjectStatus.PAUSED
    except Exception:
        return "paused"


class WorkItemEngineTests(TestCase):
    def setUp(self):
        # ✅ tuyệt đối không để audit chạy trong test
        with audit_disabled(), disable_audit_signals():
            self.tenant = Tenant.objects.create(name="T1")
            set_current_tenant(self.tenant)

            from apps.companies.models import Company

            self.company = Company._base_manager.create(
                tenant=self.tenant,
                agency=getattr(self.tenant, "agency", None),
                name="C1",
                max_clients=10,
                months_active=0,
                is_active=True,
            )

            self.project = Project.objects.create(
                tenant=self.tenant,
                company=self.company,
                name="P1",
                status=_project_status_active(),
            )

    def test_transition_happy_path(self):
        wi = WorkItem.objects.create(
            tenant=self.tenant,
            project=self.project,
            title="T",
            status=WorkItem.Status.TODO,
        )

        wi.transition_to(WorkItem.Status.DOING)
        self.assertEqual(wi.status, WorkItem.Status.DOING)
        self.assertIsNotNone(wi.started_at)

        wi.transition_to(WorkItem.Status.DONE)
        self.assertEqual(wi.status, WorkItem.Status.DONE)
        self.assertIsNotNone(wi.done_at)

        self.project.refresh_from_db()
        self.assertEqual(self.project.progress_percent, 100)

    def test_invalid_transition_blocked(self):
        wi = WorkItem.objects.create(
            tenant=self.tenant,
            project=self.project,
            title="T",
            status=WorkItem.Status.TODO,
        )
        with self.assertRaises(ValidationError):
            wi.transition_to(WorkItem.Status.DONE)

    def test_project_paused_locks_transitions(self):
        self.project.status = _project_status_paused()
        self.project.save(update_fields=["status", "updated_at"])

        wi = WorkItem.objects.create(
            tenant=self.tenant,
            project=self.project,
            title="T",
            status=WorkItem.Status.TODO,
        )

        with self.assertRaises(ValidationError):
            wi.transition_to(WorkItem.Status.DOING)

    def test_overdue_reduces_health_score(self):
        WorkItem.objects.create(
            tenant=self.tenant,
            project=self.project,
            title="T",
            status=WorkItem.Status.TODO,
            due_at=timezone.now() - timezone.timedelta(days=2),
        )

        self.project.refresh_from_db()
        self.assertLess(self.project.health_score, 100)