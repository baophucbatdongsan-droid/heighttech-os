# apps/api/v1/tests/test_workitem_transition_api.py
from django.test import TestCase
from django.test.utils import override_settings
from rest_framework.test import APIClient

from apps.core.tenant_context import set_current_tenant
from apps.tenants.models import Tenant
from apps.companies.models import Company
from apps.projects.models import Project
from apps.work.models import WorkItem


@override_settings(AUDIT_ENABLED=False)
class WorkItemTransitionApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()

        # Tạo tenant
        self.tenant = Tenant.objects.create(name="T1")
        set_current_tenant(self.tenant)

        # 🔥 QUAN TRỌNG: inject tenant vào HTTP layer
        self.client.defaults["HTTP_X_TENANT_ID"] = str(self.tenant.id)

        # Company
        self.company = Company._base_manager.create(
            tenant=self.tenant,
            agency=getattr(self.tenant, "agency", None),
            name="C1",
            max_clients=10,
            months_active=0,
            is_active=True,
        )

        # Project
        self.project = Project.objects.create(
            tenant=self.tenant,
            company=self.company,
            name="P1",
            status="active",
        )

        # WorkItem
        self.wi = WorkItem.objects.create(
            tenant=self.tenant,
            company=self.company,
            project=self.project,
            title="W1",
            status=WorkItem.Status.TODO,
        )

    def test_todo_to_doing_ok(self):
        r = self.client.post(
            f"/api/v1/work-items/{self.wi.id}/transition/",
            {"to": "doing"},
            format="json",
        )
        self.assertEqual(r.status_code, 200)
        self.wi.refresh_from_db()
        self.assertEqual(self.wi.status, "doing")

    def test_doing_to_done_ok(self):
        self.wi.transition_to("doing")
        r = self.client.post(
            f"/api/v1/work-items/{self.wi.id}/transition/",
            {"to": "done"},
            format="json",
        )
        self.assertEqual(r.status_code, 200)
        self.wi.refresh_from_db()
        self.assertEqual(self.wi.status, "done")

    def test_invalid_transition_blocked(self):
        r = self.client.post(
            f"/api/v1/work-items/{self.wi.id}/transition/",
            {"to": "done"},
            format="json",
        )
        self.assertEqual(r.status_code, 400)

    def test_archived_project_blocks(self):
        self.project.status = "archived"
        self.project.save(update_fields=["status", "updated_at"])

        r = self.client.post(
            f"/api/v1/work-items/{self.wi.id}/transition/",
            {"to": "doing"},
            format="json",
        )
        self.assertEqual(r.status_code, 400)