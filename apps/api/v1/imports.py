# apps/api/v1/imports.py
from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated

from apps.api.v1.base import BaseApi, api_error, api_ok
from apps.api.v1.permissions import AbilityPermission
from apps.core.audit import log_change, make_snapshot, disable_audit_signals
from apps.core.policy import IMPORT_MONTHLY_PERFORMANCE
from apps.performance.models import MonthlyPerformance, ImportJob


# -----------------------------
# helpers
# -----------------------------
def _has_field(model, name: str) -> bool:
    try:
        return any(f.name == name for f in model._meta.get_fields())
    except Exception:
        return False


def _d(x: Any) -> Decimal:
    try:
        if x is None:
            return Decimal("0")
        s = str(x).strip()
        if s == "":
            return Decimal("0")
        s = s.replace(",", "")
        return Decimal(s)
    except Exception:
        return Decimal("0")


def _read_csv(file_obj) -> List[Dict[str, str]]:
    raw = file_obj.read()
    if isinstance(raw, bytes):
        text = raw.decode("utf-8-sig", errors="replace")
    else:
        text = str(raw)

    f = io.StringIO(text)
    reader = csv.DictReader(f)
    rows: List[Dict[str, str]] = []
    for r in reader:
        rows.append({(k or "").strip(): (v or "").strip() for k, v in (r or {}).items()})
    return rows


def _schema_required_key() -> str:
    return "shop_id" if _has_field(MonthlyPerformance, "shop") else "company_id"


def _coerce_month(x: str) -> Optional[date]:
    return parse_date((x or "").strip())


@dataclass
class ParsedRow:
    idx: int
    month: date
    shop_id: Optional[int] = None
    company_id: Optional[int] = None
    payload: Dict[str, Any] = None


def _parse_and_validate(rows: List[Dict[str, str]], limit: int = 5000) -> Tuple[List[ParsedRow], List[Dict[str, Any]]]:
    errors: List[Dict[str, Any]] = []
    valid: List[ParsedRow] = []
    required_key = _schema_required_key()

    numeric_fields: List[str] = []
    for f in ("revenue", "cost", "profit", "company_net_profit"):
        if _has_field(MonthlyPerformance, f):
            numeric_fields.append(f)

    for i, r in enumerate(rows[:limit], start=1):
        m = _coerce_month(r.get("month", ""))
        if not m:
            errors.append({"row": i, "field": "month", "message": "month phải là YYYY-MM-DD (ví dụ 2026-02-01)"})
            continue

        id_raw = r.get(required_key, "")
        if not id_raw:
            errors.append({"row": i, "field": required_key, "message": f"Thiếu {required_key}"})
            continue

        try:
            id_val = int(str(id_raw).strip())
        except Exception:
            errors.append({"row": i, "field": required_key, "message": f"{required_key} phải là số"})
            continue

        payload: Dict[str, Any] = {"month": m}
        payload[required_key] = id_val

        for f in numeric_fields:
            payload[f] = _d(r.get(f))

        valid.append(
            ParsedRow(
                idx=i,
                month=m,
                shop_id=payload.get("shop_id"),
                company_id=payload.get("company_id"),
                payload=payload,
            )
        )

    return valid, errors


def _unique_lookup(payload: Dict[str, Any]) -> Dict[str, Any]:
    lookup = {"month": payload["month"]}
    if payload.get("shop_id") is not None:
        lookup["shop_id"] = payload["shop_id"]
    if payload.get("company_id") is not None:
        lookup["company_id"] = payload["company_id"]
    return lookup


# -----------------------------
# API
# -----------------------------
class ImportMonthlyPerformanceApi(BaseApi):
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [IsAuthenticated, AbilityPermission]
    required_ability = IMPORT_MONTHLY_PERFORMANCE

    def post(self, request):
        f = request.FILES.get("file")
        if not f:
            return api_error("missing_file", "Thiếu file CSV", status=400)

        max_mb = 5
        size = int(getattr(f, "size", 0) or 0)
        if size > max_mb * 1024 * 1024:
            return api_error("file_too_large", f"File quá lớn (>{max_mb}MB).", status=400)

        dry_run = str(request.data.get("dry_run", "1")).strip().lower() in ("1", "true", "yes", "on")
        tenant_id = getattr(request, "tenant_id", None) or getattr(getattr(request, "tenant", None), "id", None)

        # ImportJob schema mới
        job = ImportJob.objects.create(
            actor=request.user if getattr(request.user, "is_authenticated", False) else None,
            tenant_id=tenant_id,
            filename=getattr(f, "name", "") or "",
            file_size=int(size),
            dry_run=dry_run,
            status=getattr(ImportJob, "STATUS_RUNNING", "running"),
        )

        try:
            raw_rows = _read_csv(f)
        except Exception as e:
            job.status = getattr(ImportJob, "STATUS_FAILED", "failed")
            job.message = f"Không đọc được CSV: {e}"
            job.finished_at = timezone.now()
            job.save(update_fields=["status", "message", "finished_at"])
            return api_error("bad_csv", job.message, status=400)

        valid, errors = _parse_and_validate(raw_rows, limit=5000)

        job.total_rows = len(raw_rows)
        job.valid_rows = len(valid)
        job.error_rows = len(errors)

        if errors:
            job.status = getattr(ImportJob, "STATUS_FAILED", "failed")
            job.errors_preview = errors[:200]
            job.message = "CSV có lỗi, chưa commit."
            job.finished_at = timezone.now()
            job.save(update_fields=[
                "total_rows", "valid_rows", "error_rows",
                "status", "errors_preview", "message", "finished_at"
            ])

            return api_ok(
                {
                    "import_id": job.id,
                    "dry_run": True,
                    "summary": {
                        "total_rows": len(raw_rows),
                        "valid_rows": len(valid),
                        "error_rows": len(errors),
                    },
                    "errors": errors[:200],
                },
                meta={"hint": "Fix lỗi CSV rồi upload lại"},
            )

        # preview payload (first 30)
        preview: List[Dict[str, Any]] = []
        for x in valid[:30]:
            p = dict(x.payload)
            for k, v in list(p.items()):
                if isinstance(v, Decimal):
                    p[k] = float(v)
                if isinstance(v, date):
                    p[k] = v.isoformat()
            preview.append(p)

        job.preview = preview

        if dry_run:
            job.status = getattr(ImportJob, "STATUS_SUCCESS", "success")
            job.message = "Dry-run OK (chưa commit)."
            job.finished_at = timezone.now()
            job.save(update_fields=[
                "total_rows", "valid_rows", "error_rows",
                "preview", "status", "message", "finished_at"
            ])

            return api_ok(
                {
                    "import_id": job.id,
                    "dry_run": True,
                    "summary": {
                        "total_rows": len(raw_rows),
                        "valid_rows": len(valid),
                        "error_rows": 0,
                    },
                    "preview": preview,
                },
                meta={"hint": "Gửi lại với dry_run=0 để commit"},
            )

        # COMMIT
        created_count = 0
        updated_count = 0
        months_touched: set[date] = set()

        audit_fields: List[str] = ["month", "shop_id", "company_id", "revenue", "cost", "profit", "company_net_profit"]

        try:
            with transaction.atomic():
                # ✅ tắt auto-audit signals trong khi import để tránh log đôi
                with disable_audit_signals():
                    for r in valid:
                        payload = r.payload
                        months_touched.add(payload["month"])
                        lookup = _unique_lookup(payload)

                        # ✅ MonthlyPerformance đã có tenant -> phải set
                        if _has_field(MonthlyPerformance, "tenant"):
                            payload["tenant_id"] = tenant_id

                        obj = MonthlyPerformance.objects.filter(**lookup, **({"tenant_id": tenant_id} if _has_field(MonthlyPerformance, "tenant") else {})).first()
                        if obj:
                            before = make_snapshot(obj, audit_fields)
                            for k, v in payload.items():
                                setattr(obj, k, v)
                            obj.full_clean()
                            obj.save()
                            after = make_snapshot(obj, audit_fields)
                            updated_count += 1

                            log_change(
                                actor=request.user,
                                action="update",
                                model="performance.MonthlyPerformance",
                                object_id=obj.pk,
                                before=before,
                                after=after,
                                note=f"CSV import job#{job.id}",
                                tenant_id=tenant_id,
                            )
                        else:
                            obj = MonthlyPerformance(**payload)
                            obj.full_clean()
                            obj.save()
                            created_count += 1

                            after = make_snapshot(obj, audit_fields)
                            log_change(
                                actor=request.user,
                                action="create",
                                model="performance.MonthlyPerformance",
                                object_id=obj.pk,
                                before=None,
                                after=after,
                                note=f"CSV import job#{job.id}",
                                tenant_id=tenant_id,
                            )

        except ValidationError as e:
            job.status = getattr(ImportJob, "STATUS_FAILED", "failed")
            job.message = f"Validation error: {e}"
            job.finished_at = timezone.now()
            job.save(update_fields=["status", "message", "finished_at"])
            return api_error("validation_error", f"{e}", status=400)
        except Exception as e:
            job.status = getattr(ImportJob, "STATUS_FAILED", "failed")
            job.message = f"Import thất bại: {e}"
            job.finished_at = timezone.now()
            job.save(update_fields=["status", "message", "finished_at"])
            return api_error("import_failed", f"Import thất bại: {e}", status=400)

        job.created = created_count
        job.updated = updated_count
        job.months_touched = [m.isoformat() for m in sorted(months_touched)]
        job.status = getattr(ImportJob, "STATUS_SUCCESS", "success")
        job.message = "Commit OK."
        job.finished_at = timezone.now()
        job.save(update_fields=[
            "created", "updated", "months_touched",
            "status", "message", "finished_at",
            "total_rows", "valid_rows", "error_rows", "preview"
        ])

        return api_ok(
            {
                "import_id": job.id,
                "dry_run": False,
                "summary": {
                    "total_rows": len(raw_rows),
                    "valid_rows": len(valid),
                    "created": created_count,
                    "updated": updated_count,
                    "months_touched": job.months_touched,
                },
            }
        )