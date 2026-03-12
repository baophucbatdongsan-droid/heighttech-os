from __future__ import annotations

import os
import uuid
from typing import Optional

from django.conf import settings
from rest_framework.authentication import SessionAuthentication, TokenAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Membership


class CsrfExemptSessionAuthentication(SessionAuthentication):
    def enforce_csrf(self, request):
        return


def _tenant_id_from_request(request) -> Optional[int]:
    tid = request.headers.get("X-Tenant-Id")
    if tid:
        try:
            return int(tid)
        except Exception:
            pass

    try:
        user = getattr(request, "user", None)
        if user and user.is_authenticated:
            m = (
                Membership.objects.filter(user=user, is_active=True)
                .order_by("id")
                .first()
            )
            if m and m.tenant_id:
                return int(m.tenant_id)
    except Exception:
        pass

    tenant = getattr(request, "tenant", None)
    tenant_id = getattr(tenant, "id", None) if tenant else None
    if tenant_id:
        try:
            return int(tenant_id)
        except Exception:
            pass

    tenant_id = getattr(request, "tenant_id", None)
    if tenant_id:
        try:
            return int(tenant_id)
        except Exception:
            pass

    return None


class SheetImageUploadApi(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [CsrfExemptSessionAuthentication, TokenAuthentication]

    def post(self, request):
        tenant_id = _tenant_id_from_request(request)
        if not tenant_id:
            return Response({"ok": False, "message": "Không xác định được tenant"}, status=400)

        f = request.FILES.get("file")
        if not f:
            return Response({"ok": False, "message": "Thiếu file"}, status=400)

        ext = os.path.splitext(getattr(f, "name", "") or "")[1].lower() or ".bin"
        if ext not in [".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"]:
            return Response({"ok": False, "message": "Chỉ cho phép file ảnh"}, status=400)

        rel_dir = os.path.join("tenant_%s" % tenant_id, "sheets")
        abs_dir = os.path.join(settings.MEDIA_ROOT, rel_dir)
        os.makedirs(abs_dir, exist_ok=True)

        file_name = f"{uuid.uuid4().hex}{ext}"
        abs_path = os.path.join(abs_dir, file_name)

        with open(abs_path, "wb+") as dest:
            for chunk in f.chunks():
                dest.write(chunk)

        url = f"{settings.MEDIA_URL.rstrip('/')}/{rel_dir}/{file_name}"
        return Response({
            "ok": True,
            "url": url,
            "file_name": file_name,
        })