from django.contrib.auth import get_user_model
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.models import Membership
from apps.companies.models import Company

User = get_user_model()


class TeamListApi(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        tenant_id = getattr(request, "tenant_id", 1)

        members = (
            Membership.objects
            .select_related("user", "company")
            .filter(tenant_id=tenant_id, is_active=True)
        )

        items = []

        for m in members:
            u = m.user

            items.append({
                "user_id": u.id,
                "email": u.email,
                "username": u.username,
                "role": m.role,
                "company_id": m.company_id,
            })

        return Response({
            "ok": True,
            "items": items
        })


class TeamCreateApi(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):

        tenant_id = getattr(request, "tenant_id", 1)

        email = request.data.get("email")
        username = request.data.get("username")
        password = request.data.get("password")
        role = request.data.get("role", "operator")
        company_id = request.data.get("company_id")

        if not email or not password:
            return Response({"ok": False, "message": "email/password required"}, status=400)

        user = User.objects.create_user(
            email=email,
            username=username or email,
            password=password
        )

        company = Company.objects.filter(id=company_id).first()

        Membership.objects.create(
            tenant_id=tenant_id,
            user=user,
            company=company,
            role=role,
            is_active=True
        )

        return Response({
            "ok": True,
            "user_id": user.id
        })