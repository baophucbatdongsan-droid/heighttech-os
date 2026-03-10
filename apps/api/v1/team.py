from __future__ import annotations

from django.contrib.auth import get_user_model
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import (
    Membership,
    ROLE_ACCOUNT,
    ROLE_EDITOR,
    ROLE_FOUNDER,
    ROLE_HEAD,
    ROLE_LEADER_BOOKING,
    ROLE_LEADER_CHANNEL,
    ROLE_LEADER_OPERATION,
    ROLE_OPERATOR,
    ROLE_SALE,
)
from apps.companies.models import Company

User = get_user_model()


ALLOWED_ROLES = {
    ROLE_FOUNDER,
    ROLE_HEAD,  # legacy
    ROLE_LEADER_CHANNEL,
    ROLE_LEADER_BOOKING,
    ROLE_LEADER_OPERATION,
    ROLE_ACCOUNT,
    ROLE_SALE,
    ROLE_OPERATOR,
    ROLE_EDITOR,
}


def _tenant_id_from_request(request):
    tid = request.headers.get("X-Tenant-Id")
    if tid:
        try:
            return int(tid)
        except Exception:
            pass

    tid = getattr(request, "tenant_id", None)
    if tid:
        try:
            return int(tid)
        except Exception:
            pass

    tenant = getattr(request, "tenant", None)
    tid = getattr(tenant, "id", None) if tenant else None
    if tid:
        try:
            return int(tid)
        except Exception:
            pass

    user = getattr(request, "user", None)
    if user and user.is_authenticated:
        m = (
            Membership.objects.filter(user=user, is_active=True)
            .order_by("id")
            .first()
        )
        if m and m.tenant_id:
            try:
                return int(m.tenant_id)
            except Exception:
                pass

    return None


def _default_company_for_actor(request, tenant_id: int):
    user = getattr(request, "user", None)
    if user and user.is_authenticated:
        m = (
            Membership.objects.select_related("company")
            .filter(user=user, tenant_id=tenant_id, is_active=True)
            .order_by("id")
            .first()
        )
        if m and m.company_id:
            return m.company

    return (
        Company.objects_all
        .filter(tenant_id=tenant_id, is_active=True)
        .order_by("id")
        .first()
    )


class TeamListApi(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        tenant_id = _tenant_id_from_request(request)
        if not tenant_id:
            return Response(
                {"ok": False, "message": "Không xác định được tenant hiện tại"},
                status=400,
            )

        members = (
            Membership.objects
            .select_related("user", "company")
            .filter(tenant_id=int(tenant_id), is_active=True)
            .order_by("-id")
        )

        items = []
        for m in members:
            u = m.user
            items.append(
                {
                    "user_id": u.id,
                    "email": u.email,
                    "username": u.username,
                    "role": m.role,
                    "company_id": m.company_id,
                    "company_name": getattr(m.company, "name", "") if m.company_id else "",
                }
            )

        return Response(
            {
                "ok": True,
                "items": items,
            }
        )


class TeamCreateApi(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        tenant_id = _tenant_id_from_request(request)
        if not tenant_id:
            return Response(
                {"ok": False, "message": "Không xác định được tenant hiện tại"},
                status=400,
            )

        email = str(request.data.get("email") or "").strip().lower()
        username = str(request.data.get("username") or "").strip()
        password = str(request.data.get("password") or "").strip()
        role = str(request.data.get("role") or ROLE_OPERATOR).strip()
        company_id = request.data.get("company_id")

        if not email or not password:
            return Response(
                {"ok": False, "message": "Cần nhập email và mật khẩu"},
                status=400,
            )

        if not username:
            username = email.split("@")[0]

        if role not in ALLOWED_ROLES:
            return Response(
                {"ok": False, "message": f"Vai trò không hợp lệ: {role}"},
                status=400,
            )

        if User.objects.filter(email__iexact=email).exists():
            return Response(
                {"ok": False, "message": "Email đã tồn tại"},
                status=400,
            )

        if User.objects.filter(username__iexact=username).exists():
            return Response(
                {"ok": False, "message": "Username đã tồn tại"},
                status=400,
            )

        company = None

        if company_id not in (None, "", "null"):
            try:
                company = (
                    Company.objects_all
                    .filter(id=int(company_id), tenant_id=int(tenant_id))
                    .first()
                )
            except Exception:
                company = None

            if not company:
                return Response(
                    {"ok": False, "message": "Company không tồn tại trong tenant hiện tại"},
                    status=400,
                )
        else:
            company = _default_company_for_actor(request, int(tenant_id))

        if not company:
            return Response(
                {
                    "ok": False,
                    "message": "Không tìm thấy company mặc định. Anh cần chọn Company ID hoặc tạo company trước.",
                },
                status=400,
            )

        user = User.objects.create_user(
            email=email,
            username=username,
            password=password,
        )

        Membership.objects.create(
            tenant_id=int(tenant_id),
            user=user,
            company=company,
            role=role,
            is_active=True,
        )

        return Response(
            {
                "ok": True,
                "user_id": user.id,
                "email": user.email,
                "username": user.username,
                "role": role,
                "company_id": company.id,
                "company_name": company.name,
            }
        )