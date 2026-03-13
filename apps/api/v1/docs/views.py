from __future__ import annotations

import os
import uuid
from typing import Any, Dict, Optional

from django.conf import settings
from rest_framework.authentication import SessionAuthentication, TokenAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Membership
from apps.docs.models import Document


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


def _parse_int(v: Any) -> Optional[int]:
    try:
        if v is None:
            return None
        s = str(v).strip()
        if not s:
            return None
        return int(s)
    except Exception:
        return None


def _normalize_blocks(raw: Any) -> list[dict]:
    if not isinstance(raw, list):
        return []

    out: list[dict] = []

    for item in raw:
        if not isinstance(item, dict):
            continue

        block_type = str(item.get("type") or "").strip()
        data = item.get("data")

        if not block_type:
            continue

        if not isinstance(data, dict):
            data = {}

        out.append(
            {
                "type": block_type,
                "data": data,
            }
        )

    return out


def _serialize_doc(x: Document) -> Dict[str, Any]:
    return {
        "id": x.id,
        "tenant_id": x.tenant_id,
        "title": x.title,
        "doc_type": x.doc_type,
        "linked_target_type": x.linked_target_type or "",
        "linked_target_id": x.linked_target_id,
        "content_html": x.content_html or "",
        "content_blocks": x.content_blocks or [],
        "public_token": x.public_token or "",
        "created_by_id": x.created_by_id,
        "created_at": x.created_at.isoformat() if x.created_at else None,
        "updated_at": x.updated_at.isoformat() if x.updated_at else None,
        "view_url": f"/os/docs/{x.id}/",
    }


class DocumentListApi(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [CsrfExemptSessionAuthentication, TokenAuthentication]

    def get(self, request):
        tenant_id = _tenant_id_from_request(request)
        if not tenant_id:
            return Response({"ok": False, "message": "Không xác định được tenant"}, status=400)

        linked_target_type = (request.GET.get("linked_target_type") or "").strip()
        linked_target_id = _parse_int(request.GET.get("linked_target_id"))
        doc_type = (request.GET.get("doc_type") or "").strip()

        qs = Document.objects.filter(
            tenant_id=int(tenant_id),
            is_deleted=False,
        ).order_by("-id")

        if linked_target_type:
            qs = qs.filter(linked_target_type=linked_target_type)
        if linked_target_id is not None:
            qs = qs.filter(linked_target_id=linked_target_id)
        if doc_type:
            qs = qs.filter(doc_type=doc_type)

        items = [_serialize_doc(x) for x in qs[:200]]
        return Response({"ok": True, "items": items, "count": len(items)})


class DocumentCreateApi(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [CsrfExemptSessionAuthentication, TokenAuthentication]

    def post(self, request):
        tenant_id = _tenant_id_from_request(request)
        if not tenant_id:
            return Response({"ok": False, "message": "Không xác định được tenant"}, status=400)

        payload = request.data or {}
        title = str(payload.get("title") or "").strip()
        if not title:
            return Response({"ok": False, "message": "Thiếu title"}, status=400)

        doc_type = str(payload.get("doc_type") or Document.TYPE_DOC).strip() or Document.TYPE_DOC
        linked_target_type = str(payload.get("linked_target_type") or "").strip()
        linked_target_id = _parse_int(payload.get("linked_target_id"))
        content_html = str(payload.get("content_html") or "").strip()
        content_blocks = _normalize_blocks(payload.get("content_blocks"))

        obj = Document.objects.create(
            tenant_id=int(tenant_id),
            title=title,
            doc_type=doc_type,
            linked_target_type=linked_target_type,
            linked_target_id=linked_target_id,
            content_html=content_html,
            content_blocks=content_blocks,
            created_by=request.user if getattr(request, "user", None) and request.user.is_authenticated else None,
        )

        return Response({"ok": True, "item": _serialize_doc(obj)}, status=201)


class DocumentDetailApi(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [CsrfExemptSessionAuthentication, TokenAuthentication]

    def get(self, request, doc_id: int):
        tenant_id = _tenant_id_from_request(request)
        if not tenant_id:
            return Response({"ok": False, "message": "Không xác định được tenant"}, status=400)

        obj = (
            Document.objects.filter(
                id=int(doc_id),
                tenant_id=int(tenant_id),
                is_deleted=False,
            )
            .first()
        )
        if not obj:
            return Response({"ok": False, "message": "Document không tồn tại"}, status=404)

        return Response({"ok": True, "item": _serialize_doc(obj)})


class DocumentUpdateApi(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [CsrfExemptSessionAuthentication, TokenAuthentication]

    def post(self, request, doc_id: int):
        tenant_id = _tenant_id_from_request(request)
        if not tenant_id:
            return Response({"ok": False, "message": "Không xác định được tenant"}, status=400)

        obj = (
            Document.objects.filter(
                id=int(doc_id),
                tenant_id=int(tenant_id),
                is_deleted=False,
            )
            .first()
        )
        if not obj:
            return Response({"ok": False, "message": "Document không tồn tại"}, status=404)

        payload = request.data or {}

        if "title" in payload:
            title = str(payload.get("title") or "").strip()
            if title:
                obj.title = title

        if "doc_type" in payload:
            obj.doc_type = str(payload.get("doc_type") or Document.TYPE_DOC).strip() or Document.TYPE_DOC

        if "linked_target_type" in payload:
            obj.linked_target_type = str(payload.get("linked_target_type") or "").strip()

        if "linked_target_id" in payload:
            obj.linked_target_id = _parse_int(payload.get("linked_target_id"))

        if "content_html" in payload:
            obj.content_html = str(payload.get("content_html") or "")

        if "content_blocks" in payload:
            obj.content_blocks = _normalize_blocks(payload.get("content_blocks"))

        obj.save()

        return Response({"ok": True, "item": _serialize_doc(obj)})


class DocumentImageUploadApi(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [CsrfExemptSessionAuthentication, TokenAuthentication]

    def post(self, request):
        tenant_id = _tenant_id_from_request(request)
        if not tenant_id:
            return Response({"success": 0, "message": "Không xác định được tenant"}, status=400)

        file_obj = request.FILES.get("file")
        if not file_obj:
            return Response({"success": 0, "message": "Thiếu file"}, status=400)

        ext = os.path.splitext(file_obj.name)[1].lower()
        if ext not in [".png", ".jpg", ".jpeg", ".webp", ".gif"]:
            return Response({"success": 0, "message": "Chỉ cho phép file ảnh"}, status=400)

        folder = os.path.join(settings.MEDIA_ROOT, f"tenant_{tenant_id}", "docs")
        os.makedirs(folder, exist_ok=True)

        filename = f"{uuid.uuid4().hex}{ext}"
        path = os.path.join(folder, filename)

        with open(path, "wb+") as dest:
            for chunk in file_obj.chunks():
                dest.write(chunk)

        url = f"{settings.MEDIA_URL}tenant_{tenant_id}/docs/{filename}"

        return Response(
            {
                "success": 1,
                "file": {
                    "url": url
                }
            }
        )