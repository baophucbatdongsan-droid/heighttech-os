from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework.authtoken.models import Token

from apps.tenants.models import Tenant
from apps.companies.models import Company
from apps.brands.models import Brand
from apps.shops.models import Shop
from apps.accounts.models import Membership
from apps.projects.models import Project


class ProjectsApiTests(TestCase):
    def setUp(self):
        self.client_api = APIClient()

        # tenant/company/shop
        self.tenant = Tenant.objects.create(id=1, name="Tenant 1")
        self.company1 = Company.objects.create(id=1, tenant_id=self.tenant.id, name="Company 1")
        self.brand1 = Brand.objects.create(id=1, name="Brand 1", company_id=self.company1.id)
        self.shop1 = Shop.objects.create(id=1, name="Shop 1", brand_id=self.brand1.id)

        # company2 (để test out-of-scope)
        self.company2 = Company.objects.create(id=2, tenant_id=self.tenant.id, name="Company 2")
        self.brand2 = Brand.objects.create(id=2, name="Brand 2", company_id=self.company2.id)
        self.shop2 = Shop.objects.create(id=2, name="Shop 2", brand_id=self.brand2.id)

        # users + token
        User = get_user_model()
        self.admin = User.objects.create_user(username="admin", password="123456", is_staff=True, is_superuser=True)
        self.client = User.objects.create_user(username="client1", password="123456")

        self.admin_token = Token.objects.create(user=self.admin).key
        self.client_token = Token.objects.create(user=self.client).key

        Membership.objects.create(user=self.client, company_id=self.company1.id, is_active=True, role="owner")

        # seed projects
        Project.objects_all.create(
            tenant_id=self.tenant.id, company_id=self.company1.id,
            name="P1", type="shop_operation", status="active"
        )
        Project.objects_all.create(
            id=200, tenant_id=self.tenant.id, company_id=self.company2.id,
            name="P2", type="shop_operation", status="active"
        )

    def _h_client(self):
        return {
            "HTTP_X_TENANT_ID": "1",
            "HTTP_X_COMPANY_ID": "1",
            "HTTP_AUTHORIZATION": f"Token {self.client_token}",
        }

    def _h_admin(self):
        return {
            "HTTP_X_TENANT_ID": "1",
            "HTTP_AUTHORIZATION": f"Token {self.admin_token}",
        }

    def test_post_uppercase_type_is_normalized(self):
        url = "/api/v1/projects/"
        payload = {"name": "Upper", "type": "SHOP_OPERATION", "status": "active"}
        res = self.client_api.post(url, payload, format="json", **self._h_client())
        self.assertEqual(res.status_code, 200)
        data = res.json()["data"]["item"]
        self.assertEqual(data["type"], "SHOP_OPERATION")       # display
        self.assertEqual(data["type_code"], "shop_operation")  # db code

        p = Project.objects_all.get(id=data["id"])
        self.assertEqual(p.type, "shop_operation")

    def test_patch_uppercase_type_is_normalized(self):
        p = Project.objects_all.filter(company_id=self.company1.id).first()
        url = f"/api/v1/projects/{p.id}/"
        res = self.client_api.patch(url, {"type": "BUILD_CHANNEL"}, format="json", **self._h_client())
        self.assertEqual(res.status_code, 200)
        data = res.json()["data"]["item"]
        self.assertEqual(data["type"], "BUILD_CHANNEL")
        self.assertEqual(data["type_code"], "build_channel")

        p.refresh_from_db()
        self.assertEqual(p.type, "build_channel")

    def test_get_filter_type_supports_upper_and_lower(self):
        url_up = "/api/v1/projects/?type=BUILD_CHANNEL"
        url_lo = "/api/v1/projects/?type=build_channel"

        # tạo 1 project build_channel
        Project.objects_all.create(
            tenant_id=self.tenant.id, company_id=self.company1.id,
            name="BC", type="build_channel", status="active"
        )

        res1 = self.client_api.get(url_up, **self._h_client())
        res2 = self.client_api.get(url_lo, **self._h_client())
        self.assertEqual(res1.status_code, 200)
        self.assertEqual(res2.status_code, 200)

        items1 = res1.json()["data"]["items"]
        items2 = res2.json()["data"]["items"]
        self.assertEqual(len(items1), 1)
        self.assertEqual(len(items2), 1)
        self.assertEqual(items1[0]["type_code"], "build_channel")
        self.assertEqual(items2[0]["type_code"], "build_channel")

    def test_client_cannot_access_other_company_project(self):
        # project 200 thuộc company2, client scope company1 => phải 404
        url = "/api/v1/projects/200/"
        res = self.client_api.get(url, **self._h_client())
        self.assertEqual(res.status_code, 404)

    def test_admin_can_filter_company_id_in_dashboard(self):
        url = "/api/v1/projects/dashboard/?company_id=1"
        res = self.client_api.get(url, **self._h_admin())
        self.assertEqual(res.status_code, 200)
        data = res.json()["data"]
        self.assertEqual(data["tenant_id"], 1)
        self.assertEqual(data["company_id"], 1)