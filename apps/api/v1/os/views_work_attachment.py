from __future__ import annotations

import mimetypes
import os

from django.http import FileResponse, Http404
from django.utils.decorators import method_decorator
from django.views.decorators.clickjacking import xframe_options_exempt
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Membership
from apps.work.models import WorkItem
from apps.work.models_attachment import TaskAttachment


def _tenant_id_from_request(request):
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


def _get_task_or_404(task_id: int, tenant_id: int):
    qs = WorkItem.objects_all.all() if hasattr(WorkItem, "objects_all") else WorkItem.objects.all()

    obj = (
        qs.filter(
            id=int(task_id),
            tenant_id=int(tenant_id),
        )
        .first()
    )

    if not obj:
        raise Http404("Task không tồn tại trong tenant hiện tại")

    return obj


def _get_attachment_or_404(task_id: int, attachment_id: int, tenant_id: int):
    obj = (
        TaskAttachment.objects.filter(
            id=int(attachment_id),
            task_id=int(task_id),
            tenant_id=int(tenant_id),
            is_deleted=False,
        )
        .select_related("task", "uploaded_by")
        .first()
    )

    if not obj:
        raise Http404("Attachment không tồn tại trong tenant hiện tại")

    return obj


def _attachment_payload(obj: TaskAttachment):
    return {
        "id": obj.id,
        "task_id": obj.task_id,
        "tenant_id": obj.tenant_id,
        "company_id": obj.company_id,
        "shop_id": obj.shop_id,
        "project_id": obj.project_id,
        "target_type": obj.target_type or "",
        "target_id": obj.target_id,
        "file_name": obj.file_name or "",
        "original_name": obj.original_name or "",
        "content_type": obj.content_type or "",
        "file_size": obj.file_size or 0,
        "uploaded_by_id": obj.uploaded_by_id,
        "uploaded_by_name": (
            getattr(obj.uploaded_by, "get_full_name", lambda: "")()
            if obj.uploaded_by_id else ""
        ),
        "created_at": obj.created_at,
        "updated_at": obj.updated_at,
        "download_url": f"/api/v1/os/work/{obj.task_id}/attachments/{obj.id}/download/",
        "preview_url": f"/api/v1/os/work/{obj.task_id}/attachments/{obj.id}/preview/",
        "viewer_url": f"/os/files/{obj.id}/",
    }


class WorkAttachmentListApi(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, task_id: int):
        tenant_id = _tenant_id_from_request(request)
        if not tenant_id:
            return Response({"ok": False, "message": "Không xác định được tenant"}, status=400)

        _get_task_or_404(task_id, tenant_id)

        items = (
            TaskAttachment.objects.filter(
                task_id=int(task_id),
                tenant_id=int(tenant_id),
                is_deleted=False,
            )
            .select_related("uploaded_by")
            .order_by("-id")
        )

        return Response(
            {
                "ok": True,
                "items": [_attachment_payload(x) for x in items],
                "count": items.count(),
            }
        )


class WorkAttachmentUploadApi(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, task_id: int):
        tenant_id = _tenant_id_from_request(request)
        if not tenant_id:
            return Response({"ok": False, "message": "Không xác định được tenant"}, status=400)

        task = _get_task_or_404(task_id, tenant_id)

        f = request.FILES.get("file")
        if not f:
            return Response({"ok": False, "message": "Thiếu file upload"}, status=400)

        original_name = getattr(f, "name", "") or "file"
        content_type = getattr(f, "content_type", "") or ""
        if not content_type:
            guessed, _ = mimetypes.guess_type(original_name)
            content_type = guessed or ""

        obj = TaskAttachment.objects.create(
            task=task,
            tenant_id=int(tenant_id),
            file=f,
            file_name=os.path.basename(original_name),
            original_name=original_name,
            content_type=content_type,
            file_size=int(getattr(f, "size", 0) or 0),
            uploaded_by=(
                request.user
                if getattr(request, "user", None) and request.user.is_authenticated
                else None
            ),
        )

        return Response(
            {
                "ok": True,
                "item": _attachment_payload(obj),
                "message": "Upload file thành công",
            }
        )


class WorkAttachmentDownloadApi(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, task_id: int, attachment_id: int):
        tenant_id = _tenant_id_from_request(request)
        if not tenant_id:
            raise Http404("Không xác định được tenant")

        obj = _get_attachment_or_404(task_id, attachment_id, tenant_id)

        if not obj.file:
            raise Http404("File không tồn tại")

        file_handle = obj.file.open("rb")
        filename = obj.original_name or obj.file_name or f"attachment-{obj.id}"
        return FileResponse(file_handle, as_attachment=True, filename=filename)


@method_decorator(xframe_options_exempt, name="dispatch")
class WorkAttachmentPreviewApi(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, task_id: int, attachment_id: int):
        tenant_id = _tenant_id_from_request(request)
        if not tenant_id:
            raise Http404("Không xác định được tenant")

        obj = _get_attachment_or_404(task_id, attachment_id, tenant_id)

        if not obj.file:
            raise Http404("File không tồn tại")

        file_handle = obj.file.open("rb")
        response = FileResponse(file_handle, as_attachment=False)

        if obj.content_type:
            response["Content-Type"] = obj.content_type

        filename = obj.original_name or obj.file_name or f"attachment-{obj.id}"
        response["Content-Disposition"] = f'inline; filename="{filename}"'
        response["X-Frame-Options"] = "SAMEORIGIN"
        return response