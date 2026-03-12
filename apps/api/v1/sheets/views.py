from __future__ import annotations
import os
import uuid
from django.conf import settings
from io import BytesIO
from typing import Any, Dict, Optional

from django.http import HttpResponse
from django.utils.text import slugify
from openpyxl import Workbook
from rest_framework.authentication import SessionAuthentication, TokenAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Membership
from apps.sheets.models import Sheet, SheetCell, SheetColumn, SheetRow


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


def _sheet_or_404(sheet_id: int, tenant_id: int) -> Optional[Sheet]:
    return (
        Sheet.objects.filter(
            id=int(sheet_id),
            tenant_id=int(tenant_id),
            is_deleted=False,
        )
        .first()
    )


def _serialize_sheet(x: Sheet) -> Dict[str, Any]:
    return {
        "id": x.id,
        "tenant_id": x.tenant_id,
        "name": x.name,
        "slug": x.slug or "",
        "module_code": x.module_code or "",
        "linked_target_type": x.linked_target_type or "",
        "linked_target_id": x.linked_target_id,
        "created_by_id": x.created_by_id,
        "created_at": x.created_at.isoformat() if x.created_at else None,
        "updated_at": x.updated_at.isoformat() if x.updated_at else None,
    }


def _serialize_column(x: SheetColumn) -> Dict[str, Any]:
    return {
        "id": x.id,
        "sheet_id": x.sheet_id,
        "name": x.name,
        "key": x.key or "",
        "data_type": x.data_type,
        "position": x.position,
        "is_required": x.is_required,
    }


class SheetListApi(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [CsrfExemptSessionAuthentication, TokenAuthentication]

    def get(self, request):
        tenant_id = _tenant_id_from_request(request)
        if not tenant_id:
            return Response({"ok": False, "message": "Không xác định được tenant"}, status=400)

        linked_target_type = (request.GET.get("linked_target_type") or "").strip()
        linked_target_id = _parse_int(request.GET.get("linked_target_id"))
        module_code = (request.GET.get("module_code") or "").strip()

        qs = Sheet.objects.filter(tenant_id=tenant_id, is_deleted=False).order_by("-id")

        if linked_target_type:
            qs = qs.filter(linked_target_type=linked_target_type)
        if linked_target_id is not None:
            qs = qs.filter(linked_target_id=linked_target_id)
        if module_code:
            qs = qs.filter(module_code=module_code)

        items = [_serialize_sheet(x) for x in qs[:200]]
        return Response({"ok": True, "items": items, "count": len(items)})


class SheetCreateApi(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [CsrfExemptSessionAuthentication, TokenAuthentication]

    def post(self, request):
        tenant_id = _tenant_id_from_request(request)
        if not tenant_id:
            return Response({"ok": False, "message": "Không xác định được tenant"}, status=400)

        payload = request.data or {}
        name = str(payload.get("name") or "").strip()
        if not name:
            return Response({"ok": False, "message": "Thiếu tên sheet"}, status=400)

        module_code = str(payload.get("module_code") or Sheet.MODULE_CUSTOM).strip() or Sheet.MODULE_CUSTOM
        linked_target_type = str(payload.get("linked_target_type") or "").strip()
        linked_target_id = _parse_int(payload.get("linked_target_id"))

        obj = Sheet.objects.create(
            tenant_id=int(tenant_id),
            name=name,
            slug=slugify(name)[:255],
            module_code=module_code,
            linked_target_type=linked_target_type,
            linked_target_id=linked_target_id,
            created_by=request.user if getattr(request, "user", None) and request.user.is_authenticated else None,
        )

        default_columns = payload.get("columns") or []
        position = 1
        for col in default_columns:
            col_name = str((col or {}).get("name") or "").strip()
            if not col_name:
                continue
            data_type = str((col or {}).get("data_type") or SheetColumn.DATA_TEXT).strip() or SheetColumn.DATA_TEXT

            SheetColumn.objects.create(
                sheet=obj,
                name=col_name,
                key=slugify(col_name)[:255],
                data_type=data_type,
                position=position,
            )
            position += 1

        return Response({"ok": True, "item": _serialize_sheet(obj)}, status=201)


class SheetDetailApi(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [CsrfExemptSessionAuthentication, TokenAuthentication]

    def get(self, request, sheet_id: int):
        tenant_id = _tenant_id_from_request(request)
        if not tenant_id:
            return Response({"ok": False, "message": "Không xác định được tenant"}, status=400)

        sheet = _sheet_or_404(sheet_id, tenant_id)
        if not sheet:
            return Response({"ok": False, "message": "Sheet không tồn tại"}, status=404)

        columns = list(sheet.columns.all().order_by("position", "id"))
        rows = list(sheet.rows.all().order_by("position", "id"))

        cell_map: Dict[tuple[int, int], str] = {}
        for cell in SheetCell.objects.filter(row__sheet_id=sheet.id).select_related("row", "column"):
            cell_map[(cell.row_id, cell.column_id)] = cell.value_text or ""

        rows_payload = []
        for row in rows:
            rows_payload.append({
                "id": row.id,
                "position": row.position,
                "cells": {
                    str(col.id): cell_map.get((row.id, col.id), "")
                    for col in columns
                },
            })

        return Response({
            "ok": True,
            "sheet": _serialize_sheet(sheet),
            "columns": [_serialize_column(x) for x in columns],
            "rows": rows_payload,
        })


class SheetColumnCreateApi(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [CsrfExemptSessionAuthentication, TokenAuthentication]

    def post(self, request, sheet_id: int):

        tenant_id = _tenant_id_from_request(request)
        if not tenant_id:
            return Response(
                {"ok": False, "message": "Không xác định được tenant"},
                status=400,
            )

        sheet = _sheet_or_404(sheet_id, tenant_id)
        if not sheet:
            return Response(
                {"ok": False, "message": "Sheet không tồn tại"},
                status=404,
            )

        payload = request.data or {}

        name = str(payload.get("name") or "").strip()
        if not name:
            return Response(
                {"ok": False, "message": "Thiếu tên cột"},
                status=400,
            )

        # ===== VALID DATA TYPE =====

        valid_types = {
            SheetColumn.DATA_TEXT,
            SheetColumn.DATA_NUMBER,
            SheetColumn.DATA_DATE,
            SheetColumn.DATA_SELECT,
            SheetColumn.DATA_IMAGE,
        }

        data_type = str(
            payload.get("data_type") or SheetColumn.DATA_TEXT
        ).strip()

        if data_type not in valid_types:
            data_type = SheetColumn.DATA_TEXT

        # ===== POSITION =====

        max_pos = (
            sheet.columns
            .order_by("-position")
            .values_list("position", flat=True)
            .first()
            or 0
        )

        # ===== CREATE COLUMN =====

        obj = SheetColumn.objects.create(
            sheet=sheet,
            name=name,
            key=slugify(name)[:255],
            data_type=data_type,
            position=int(max_pos) + 1,
        )

        return Response(
            {
                "ok": True,
                "item": _serialize_column(obj),
            },
            status=201,
        )

class SheetRowCreateApi(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [CsrfExemptSessionAuthentication, TokenAuthentication]

    def post(self, request, sheet_id: int):
        tenant_id = _tenant_id_from_request(request)
        if not tenant_id:
            return Response({"ok": False, "message": "Không xác định được tenant"}, status=400)

        sheet = _sheet_or_404(sheet_id, tenant_id)
        if not sheet:
            return Response({"ok": False, "message": "Sheet không tồn tại"}, status=404)

        max_pos = sheet.rows.order_by("-position").values_list("position", flat=True).first() or 0
        row = SheetRow.objects.create(
            sheet=sheet,
            position=int(max_pos) + 1,
            created_by=request.user if getattr(request, "user", None) and request.user.is_authenticated else None,
        )

        return Response({
            "ok": True,
            "item": {
                "id": row.id,
                "sheet_id": row.sheet_id,
                "position": row.position,
            },
        }, status=201)


class SheetCellUpdateApi(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [CsrfExemptSessionAuthentication, TokenAuthentication]

    def post(self, request):
        tenant_id = _tenant_id_from_request(request)
        if not tenant_id:
            return Response({"ok": False, "message": "Không xác định được tenant"}, status=400)

        payload = request.data or {}
        row_id = _parse_int(payload.get("row_id"))
        column_id = _parse_int(payload.get("column_id"))
        value_text = str(payload.get("value") or "")

        if not row_id or not column_id:
            return Response({"ok": False, "message": "Thiếu row_id / column_id"}, status=400)

        row = (
            SheetRow.objects.filter(
                id=int(row_id),
                sheet__tenant_id=int(tenant_id),
                sheet__is_deleted=False,
            )
            .select_related("sheet")
            .first()
        )
        if not row:
            return Response({"ok": False, "message": "Row không tồn tại"}, status=404)

        column = (
            SheetColumn.objects.filter(
                id=int(column_id),
                sheet_id=int(row.sheet_id),
            )
            .first()
        )
        if not column:
            return Response({"ok": False, "message": "Column không tồn tại"}, status=404)

        cell, _ = SheetCell.objects.get_or_create(
            row=row,
            column=column,
            defaults={
                "value_text": value_text,
                "updated_by": request.user if getattr(request, "user", None) and request.user.is_authenticated else None,
            },
        )

        if cell.value_text != value_text:
            cell.value_text = value_text
            cell.updated_by = request.user if getattr(request, "user", None) and request.user.is_authenticated else None
            cell.save(update_fields=["value_text", "updated_by", "updated_at"])

        return Response({
            "ok": True,
            "item": {
                "row_id": row.id,
                "column_id": column.id,
                "value": cell.value_text,
            },
        })


class SheetExportExcelApi(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [CsrfExemptSessionAuthentication, TokenAuthentication]

    def get(self, request, sheet_id: int):
        tenant_id = _tenant_id_from_request(request)
        if not tenant_id:
            return Response({"ok": False, "message": "Không xác định được tenant"}, status=400)

        sheet = _sheet_or_404(sheet_id, tenant_id)
        if not sheet:
            return Response({"ok": False, "message": "Sheet không tồn tại"}, status=404)

        columns = list(sheet.columns.all().order_by("position", "id"))
        rows = list(sheet.rows.all().order_by("position", "id"))

        wb = Workbook()
        ws = wb.active
        ws.title = (sheet.name or "Sheet")[:31]

        ws.append([x.name for x in columns])

        cell_map: Dict[tuple[int, int], str] = {}
        for cell in SheetCell.objects.filter(row__sheet_id=sheet.id):
            cell_map[(cell.row_id, cell.column_id)] = cell.value_text or ""

        for row in rows:
            ws.append([cell_map.get((row.id, col.id), "") for col in columns])

        fp = BytesIO()
        wb.save(fp)
        fp.seek(0)

        filename = slugify(sheet.name or f"sheet-{sheet.id}") or f"sheet-{sheet.id}"
        resp = HttpResponse(
            fp.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        resp["Content-Disposition"] = f'attachment; filename="{filename}.xlsx"'
        return resp
    
class SheetImageUploadApi(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [CsrfExemptSessionAuthentication, TokenAuthentication]

    def post(self, request):

        tenant_id = _tenant_id_from_request(request)
        if not tenant_id:
            return Response({"ok": False, "message": "Không xác định tenant"}, status=400)

        f = request.FILES.get("file")
        if not f:
            return Response({"ok": False, "message": "Thiếu file"}, status=400)

        ext = os.path.splitext(f.name)[1].lower()

        if ext not in [".png",".jpg",".jpeg",".webp",".gif",".svg"]:
            return Response({"ok": False, "message": "Chỉ cho phép file ảnh"}, status=400)

        folder = os.path.join(
            settings.MEDIA_ROOT,
            f"tenant_{tenant_id}",
            "sheets"
        )

        os.makedirs(folder, exist_ok=True)

        filename = f"{uuid.uuid4().hex}{ext}"

        path = os.path.join(folder, filename)

        with open(path, "wb+") as dest:
            for chunk in f.chunks():
                dest.write(chunk)

        url = f"{settings.MEDIA_URL}tenant_{tenant_id}/sheets/{filename}"

        return Response({
            "ok": True,
            "url": url
        })