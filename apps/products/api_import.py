from __future__ import annotations

import csv
import io
from decimal import Decimal
from typing import Any, Dict, List, Tuple

from django.db import transaction
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.v1.insight import _get_tenant_id
from apps.products.models import Product


def _to_decimal(v: Any) -> Decimal:
    try:
        return Decimal(str(v or 0).strip())
    except Exception:
        return Decimal("0")


def _to_int(v: Any) -> int:
    try:
        return int(str(v or 0).strip())
    except Exception:
        return 0


def _norm_text(v: Any) -> str:
    return str(v or "").strip()


def _get_csv_file(request):
    return request.FILES.get("file") or request.FILES.get("csv") or request.FILES.get("upload")


def _parse_csv(uploaded_file) -> List[Dict[str, str]]:
    raw = uploaded_file.read()
    text = raw.decode("utf-8-sig", errors="ignore")
    reader = csv.DictReader(io.StringIO(text))
    return [dict(row or {}) for row in reader]


class ProductCSVImportApi(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        tenant_id = _get_tenant_id(request)
        if not tenant_id:
            return Response({"ok": False, "message": "Thiếu tenant_id"}, status=400)

        uploaded = _get_csv_file(request)
        if not uploaded:
            return Response(
                {
                    "ok": False,
                    "message": "Thiếu file CSV. Header tối thiểu: sku,name,price,cost,stock",
                },
                status=400,
            )

        shop_id = request.data.get("shop_id") or request.query_params.get("shop_id")
        company_id = request.data.get("company_id") or request.query_params.get("company_id")

        try:
            rows = _parse_csv(uploaded)
        except Exception as e:
            return Response({"ok": False, "message": f"Không đọc được CSV: {e}"}, status=400)

        created = 0
        updated = 0
        errors: List[Dict[str, Any]] = []

        for idx, row in enumerate(rows, start=2):
            sku = _norm_text(row.get("sku"))
            name = _norm_text(row.get("name"))

            if not sku:
                errors.append({"row": idx, "error": "Thiếu sku"})
                continue

            if not name:
                errors.append({"row": idx, "error": "Thiếu name"})
                continue

            if not shop_id:
                errors.append({"row": idx, "error": "Thiếu shop_id ở request"})
                continue

            defaults = {
                "tenant_id": int(tenant_id),
                "company_id": int(company_id) if company_id else None,
                "name": name,
                "price": _to_decimal(row.get("price")),
                "cost": _to_decimal(row.get("cost")),
                "stock": _to_int(row.get("stock")),
                "status": _norm_text(row.get("status")) or "active",
                "meta": {
                    "import_source": "csv",
                    "raw_row": row,
                },
            }

            obj, is_created = Product.objects_all.update_or_create(
                shop_id=int(shop_id),
                sku=sku,
                defaults=defaults,
            )

            if is_created:
                created += 1
            else:
                updated += 1

        return Response(
            {
                "ok": True,
                "tenant_id": int(tenant_id),
                "shop_id": int(shop_id) if shop_id else None,
                "company_id": int(company_id) if company_id else None,
                "created": created,
                "updated": updated,
                "errors_count": len(errors),
                "errors": errors[:30],
                "sample_headers": ["sku", "name", "price", "cost", "stock", "status"],
            }
        )