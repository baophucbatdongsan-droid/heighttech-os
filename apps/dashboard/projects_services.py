# apps/dashboard/projects_services.py
from __future__ import annotations

import csv
import hashlib
import io
import json
from datetime import datetime, time
from typing import Any, Dict, Iterable, List, Optional, Tuple

from django.core.cache import cache
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, IntegerField, QuerySet, Value
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.utils import timezone

from apps.core.audit import log_change  # ✅ Level 9 audit
from apps.dashboard.projects_common import mgr
from apps.dashboard.projects_queries import ProjectsDashboardQuery
from apps.projects.models import Project, ProjectShop
from apps.projects.types import get_type_display_safe, normalize_project_type


# ==========================================================
# CẤU HÌNH CHUNG
# ==========================================================

CACHE_TTL_SECONDS = 60  # dashboard cache TTL
EXPORT_LIMIT = 5000     # giới hạn export an toàn
MAX_BULK_LIMIT = 5000   # giới hạn bulk an toàn

# Rate limit (chống spam)
EXPORT_RATE_SECONDS = 10
BULK_RATE_SECONDS = 5


# ==========================================================
# CACHE VERSION BUMP (invalidate cache dashboard)
# ==========================================================

def _bump_key(tid: int) -> str:
    return f"dash_projects_bump:{int(tid)}"


def _get_bump(tid: int) -> int:
    try:
        return int(cache.get(_bump_key(tid)) or 0)
    except Exception:
        return 0


def bump_dashboard_cache(tid: int) -> None:
    """
    Tăng version để invalidate cache dashboard (an toàn mọi backend cache).
    """
    k = _bump_key(int(tid))
    try:
        v = int(cache.get(k) or 0) + 1
    except Exception:
        v = 1
    cache.set(k, v, 24 * 3600)


# ==========================================================
# HASH HELPERS (query_hash, cache keys)
# ==========================================================

def _hash_payload(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.md5(raw).hexdigest()


def _query_hash(*, tid: int, company_id: Optional[int], query: ProjectsDashboardQuery) -> str:
    """
    Hash bộ lọc để audit truy vết "export/bulk theo bộ lọc nào".
    """
    payload = {
        "tid": tid,
        "company_id": company_id,
        "q": query.q,
        "status": query.status,
        "type": query.type,
        "health_min": query.health_min,
        "health_max": query.health_max,
        "shops_min": query.shops_min,
        "shops_max": query.shops_max,
        "updated_from": query.updated_from,
        "updated_to": query.updated_to,
        "sort": query.sort,
        "dir": query.direction,
        "page_size": query.page_size,
    }
    return _hash_payload(payload)


# ==========================================================
# DATE PARSERS
# ==========================================================

def _parse_date_yyyy_mm_dd(s: str) -> Optional[datetime]:
    """
    Nhận 'YYYY-MM-DD' -> datetime (00:00:00)
    """
    s = (s or "").strip()
    if not s:
        return None
    try:
        d = datetime.strptime(s, "%Y-%m-%d").date()
        return datetime.combine(d, time.min)
    except Exception:
        return None


def _parse_date_end_yyyy_mm_dd(s: str) -> Optional[datetime]:
    """
    Nhận 'YYYY-MM-DD' -> datetime (23:59:59.999999)
    """
    s = (s or "").strip()
    if not s:
        return None
    try:
        d = datetime.strptime(s, "%Y-%m-%d").date()
        return datetime.combine(d, time.max)
    except Exception:
        return None


# ==========================================================
# RATE LIMIT HELPERS
# ==========================================================

def _rate_key(kind: str, tid: int, user_id: Optional[int]) -> str:
    return f"rate:{kind}:tid{int(tid)}:u{int(user_id or 0)}"


def _hit_rate(kind: str, tid: int, user_id: Optional[int], seconds: int) -> bool:
    """
    True = bị chặn (rate limit)
    False = ok
    """
    k = _rate_key(kind, tid, user_id)
    if cache.get(k):
        return True
    cache.set(k, 1, seconds)
    return False


# ==========================================================
# SERVICE
# ==========================================================

class ProjectsDashboardService:
    # -------------------------
    # Base queryset
    # -------------------------
    @staticmethod
    def _base_qs() -> QuerySet:
        qs = mgr(Project).all()
        try:
            qs = qs.select_related("company")
        except Exception:
            pass
        return qs

    # -------------------------
    # Annotations
    # -------------------------
    @staticmethod
    def _annotate_metrics(qs: QuerySet) -> QuerySet:
        """
        - _health_sort: null health -> 100
        - _shops_total: tổng link shop
        """
        return qs.annotate(
            _health_sort=Coalesce("health_score", Value(100), output_field=IntegerField()),
            _shops_total=Count("project_shops", distinct=True),
        )

    # -------------------------
    # Filters
    # -------------------------
    @staticmethod
    def _apply_filters(qs: QuerySet, *, tid: int, company_id: int | None, query: ProjectsDashboardQuery) -> QuerySet:
        qs = qs.filter(tenant_id=tid)

        if company_id is not None:
            qs = qs.filter(company_id=int(company_id))

        if query.status:
            qs = qs.filter(status=query.status)

        if query.type:
            t_norm = normalize_project_type(query.type)
            candidates = {t_norm, query.type, query.type.lower(), query.type.upper()}
            qs = qs.filter(type__in=list(candidates))

        if query.q:
            qtxt = query.q.strip()
            qs2 = qs.filter(name__icontains=qtxt)
            try:
                q_int = int(qtxt)
                qs2 = qs2 | qs.filter(id=q_int)
            except Exception:
                pass
            qs = qs2

        # lọc theo ngày updated
        dt_from = _parse_date_yyyy_mm_dd(query.updated_from)
        dt_to = _parse_date_end_yyyy_mm_dd(query.updated_to)
        if dt_from:
            qs = qs.filter(updated_at__gte=dt_from)
        if dt_to:
            qs = qs.filter(updated_at__lte=dt_to)

        return qs

    # -------------------------
    # Sort
    # -------------------------
    @staticmethod
    def _apply_sort(qs: QuerySet, *, sort: str, direction: str) -> QuerySet:
        desc = (direction or "").lower() != "asc"
        p = "-" if desc else ""

        if sort == "id":
            return qs.order_by(f"{p}id")
        if sort == "name":
            return qs.order_by(f"{p}name", "-id")
        if sort == "type":
            return qs.order_by(f"{p}type", "-id")
        if sort == "status":
            return qs.order_by(f"{p}status", "-id")
        if sort == "health":
            return qs.order_by(f"{p}_health_sort", "-id")
        if sort == "shops":
            return qs.order_by(f"{p}_shops_total", "-id")

        # updated: ưu tiên updated_at, fallback id
        try:
            return qs.order_by(f"{p}updated_at", "-id")
        except Exception:
            return qs.order_by(f"{p}id")

    # -------------------------
    # Summary (cache)
    # -------------------------
    @staticmethod
    def _build_summary(*, tid: int, qs_filtered: QuerySet, cache_key: str) -> Dict[str, Any]:
        cached = cache.get(cache_key)
        if cached:
            return cached

        total_projects = qs_filtered.count()

        by_status: Dict[str, int] = {}
        for row in qs_filtered.values("status").annotate(c=Count("id")):
            by_status[row["status"] or ""] = int(row["c"] or 0)

        by_type: Dict[str, int] = {}
        for row in qs_filtered.values("type").annotate(c=Count("id")):
            t_code = normalize_project_type(row["type"] or "")
            by_type[t_code] = by_type.get(t_code, 0) + int(row["c"] or 0)

        links_qs = mgr(ProjectShop).filter(tenant_id=tid, project_id__in=qs_filtered.values("id"))
        shops_total = links_qs.count()
        shops_status = {"active": 0, "paused": 0, "done": 0, "inactive": 0}
        for row in links_qs.values("status").annotate(c=Count("id")):
            st = (row["status"] or "").strip()
            if st in shops_status:
                shops_status[st] = int(row["c"] or 0)

        summary = {
            "total_projects": total_projects,
            "by_status": by_status,
            "by_type": by_type,
            "shops": {"total": shops_total, **shops_status},
        }

        cache.set(cache_key, summary, CACHE_TTL_SECONDS)
        return summary

    # -------------------------
    # Founder extra (cache)
    # -------------------------
    @staticmethod
    def _bucket(score: int) -> str:
        if score <= 39:
            return "0_39"
        if score <= 69:
            return "40_69"
        return "70_100"

    @staticmethod
    def _build_founder_extra(qs_annotated: QuerySet, cache_key: str, *, top_limit: int = 10) -> Dict[str, Any]:
        cached = cache.get(cache_key)
        if cached:
            return cached

        buckets = {"0_39": 0, "40_69": 0, "70_100": 0}
        for row in qs_annotated.values("_health_sort").annotate(c=Count("id")):
            s = int(row["_health_sort"] or 100)
            buckets[ProjectsDashboardService._bucket(s)] += int(row["c"] or 0)

        top_risk_qs = qs_annotated.order_by("_health_sort", "-id")[:top_limit]
        top_risk: List[Dict[str, Any]] = [ProjectsDashboardService._to_item(p) for p in top_risk_qs]

        founder_extra = {
            "health_buckets": buckets,
            "top_risk": top_risk,
            "generated_at": timezone.now(),
        }

        cache.set(cache_key, founder_extra, CACHE_TTL_SECONDS)
        return founder_extra

    # -------------------------
    # Item mapping (khớp template)
    # -------------------------
    @staticmethod
    def _to_item(p) -> Dict[str, Any]:
        return {
            "id": p.id,
            "name": getattr(p, "name", ""),
            "type": getattr(p, "type", ""),
            "type_code": normalize_project_type(getattr(p, "type", "") or ""),
            "type_display": get_type_display_safe(p),
            "status": getattr(p, "status", ""),
            "health_score": int(getattr(p, "_health_sort", 100) or 100),
            "shops": {"total": int(getattr(p, "_shops_total", 0) or 0)},
            "updated_at": getattr(p, "updated_at", None),
        }

    # -------------------------
    # Public API (dashboard)
    # -------------------------
    @staticmethod
    def build(*, tid: int, company_id: int | None, query: ProjectsDashboardQuery, is_founder: bool) -> Dict[str, Any]:
        bump = _get_bump(tid)

        qs = ProjectsDashboardService._base_qs()
        qs_filtered = ProjectsDashboardService._apply_filters(qs, tid=tid, company_id=company_id, query=query)

        summary_key_payload = {
            "v": 9,
            "bump": bump,
            "kind": "summary",
            "tid": tid,
            "company_id": company_id,
            "q": query.q,
            "status": query.status,
            "type": query.type,
            "health_min": query.health_min,
            "health_max": query.health_max,
            "shops_min": query.shops_min,
            "shops_max": query.shops_max,
            "updated_from": query.updated_from,
            "updated_to": query.updated_to,
        }
        summary_cache_key = "dash_projects_" + _hash_payload(summary_key_payload)
        summary = ProjectsDashboardService._build_summary(tid=tid, qs_filtered=qs_filtered, cache_key=summary_cache_key)

        qs_annotated = ProjectsDashboardService._annotate_metrics(qs_filtered)

        # filters cần annotation
        if query.health_min is not None:
            qs_annotated = qs_annotated.filter(_health_sort__gte=int(query.health_min))
        if query.health_max is not None:
            qs_annotated = qs_annotated.filter(_health_sort__lte=int(query.health_max))
        if query.shops_min is not None:
            qs_annotated = qs_annotated.filter(_shops_total__gte=int(query.shops_min))
        if query.shops_max is not None:
            qs_annotated = qs_annotated.filter(_shops_total__lte=int(query.shops_max))

        founder_extra = None
        if is_founder:
            founder_key_payload = dict(summary_key_payload)
            founder_key_payload["kind"] = "founder_extra"
            founder_cache_key = "dash_projects_" + _hash_payload(founder_key_payload)
            founder_extra = ProjectsDashboardService._build_founder_extra(qs_annotated, cache_key=founder_cache_key)

        qs_sorted = ProjectsDashboardService._apply_sort(qs_annotated, sort=query.sort, direction=query.direction)

        paginator = Paginator(qs_sorted, query.page_size)
        page_obj = paginator.get_page(query.page)

        items = [ProjectsDashboardService._to_item(p) for p in page_obj.object_list]

        return {
            "summary": summary,
            "items": items,
            "founder_extra": founder_extra,
            "page_obj": page_obj,
            "paginator": paginator,
        }

    # -------------------------
    # Export CSV (Level 9: rate limit + audit)
    # -------------------------
    @staticmethod
    def export_csv_response(
        *,
        tid: int,
        company_id: int | None,
        query: ProjectsDashboardQuery,
        user_id: Optional[int] = None,
    ) -> HttpResponse:
        """
        Export theo filter hiện tại.
        Level 9:
        - rate limit
        - audit meta: query_hash, duration_ms, export_count, limit
        """
        t0 = timezone.now()

        # Rate limit theo user
        if _hit_rate("export_csv", tid, user_id, EXPORT_RATE_SECONDS):
            # audit bị chặn vẫn log để truy vết
            log_change(
                action="export_csv",
                model="projects.Project",
                object_id="export",
                tenant_id=tid,
                note="rate_limited",
                meta={
                    "tid": tid,
                    "company_id": company_id,
                    "query_hash": _query_hash(tid=tid, company_id=company_id, query=query),
                    "rate_seconds": EXPORT_RATE_SECONDS,
                    "blocked": True,
                },
            )
            resp = HttpResponse("Bạn thao tác quá nhanh. Vui lòng thử lại sau.", status=429)
            return resp

        qs = ProjectsDashboardService._base_qs()
        qs_filtered = ProjectsDashboardService._apply_filters(qs, tid=tid, company_id=company_id, query=query)
        qs_annotated = ProjectsDashboardService._annotate_metrics(qs_filtered)

        # filters cần annotation
        if query.health_min is not None:
            qs_annotated = qs_annotated.filter(_health_sort__gte=int(query.health_min))
        if query.health_max is not None:
            qs_annotated = qs_annotated.filter(_health_sort__lte=int(query.health_max))
        if query.shops_min is not None:
            qs_annotated = qs_annotated.filter(_shops_total__gte=int(query.shops_min))
        if query.shops_max is not None:
            qs_annotated = qs_annotated.filter(_shops_total__lte=int(query.shops_max))

        qs_sorted = ProjectsDashboardService._apply_sort(qs_annotated, sort=query.sort, direction=query.direction)

        # giới hạn export an toàn
        qs_sorted = qs_sorted[:EXPORT_LIMIT]
        export_count = qs_sorted.count()

        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["ID", "Tên dự án", "Trạng thái", "Loại (gốc)", "Loại (chuẩn)", "Health", "Số shop", "Cập nhật lúc"])

        for p in qs_sorted:
            item = ProjectsDashboardService._to_item(p)
            w.writerow(
                [
                    item["id"],
                    item["name"],
                    item["status"],
                    item["type"],
                    item["type_code"],
                    item["health_score"],
                    item["shops"]["total"],
                    item["updated_at"] or "",
                ]
            )

        filename = f"du_an_t{tid}_c{company_id or 'tat_ca'}_{timezone.now().strftime('%Y%m%d_%H%M%S')}.csv"
        resp = HttpResponse(buf.getvalue(), content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = f'attachment; filename="{filename}"'

        duration_ms = int((timezone.now() - t0).total_seconds() * 1000)

        # ✅ Audit export
        log_change(
            action="export_csv",
            model="projects.Project",
            object_id="export",
            tenant_id=tid,
            meta={
                "tid": tid,
                "company_id": company_id,
                "query_hash": _query_hash(tid=tid, company_id=company_id, query=query),
                "export_count": export_count,
                "limit": EXPORT_LIMIT,
                "duration_ms": duration_ms,
            },
        )

        return resp

    # -------------------------
    # Bulk update (Level 9: select_all_filtered + audit)
    # -------------------------
    @staticmethod
    def bulk_update(
        *,
        tid: int,
        company_id: Optional[int],
        project_ids: List[str],
        new_status: Optional[str],
        new_type: Optional[str],
        select_all_filtered: bool = False,
        query: Optional[ProjectsDashboardQuery] = None,
        user_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Level 9:
        - hỗ trợ tick ids hoặc apply all filtered
        - giới hạn MAX_BULK_LIMIT
        - audit meta: query_hash, affected_count, duration_ms, updates
        - rate limit
        """
        t0 = timezone.now()

        # Rate limit theo user
        if _hit_rate("bulk_update", tid, user_id, BULK_RATE_SECONDS):
            log_change(
                action="bulk_update",
                model="projects.Project",
                object_id="bulk",
                tenant_id=tid,
                note="rate_limited",
                meta={
                    "tid": tid,
                    "company_id": company_id,
                    "blocked": True,
                    "rate_seconds": BULK_RATE_SECONDS,
                },
            )
            return {"ok": False, "message": "Bạn thao tác quá nhanh. Vui lòng thử lại sau."}

        ids: List[int] = []

        # 1) Nếu áp dụng cho tất cả theo bộ lọc
        if select_all_filtered:
            if query is None:
                return {"ok": False, "message": "Thiếu bộ lọc (query)."}

            qs_filtered = ProjectsDashboardService._apply_filters(
                ProjectsDashboardService._base_qs(),
                tid=tid,
                company_id=company_id,
                query=query,
            )

            qs_annotated = ProjectsDashboardService._annotate_metrics(qs_filtered)

            # filters cần annotation
            if query.health_min is not None:
                qs_annotated = qs_annotated.filter(_health_sort__gte=int(query.health_min))
            if query.health_max is not None:
                qs_annotated = qs_annotated.filter(_health_sort__lte=int(query.health_max))
            if query.shops_min is not None:
                qs_annotated = qs_annotated.filter(_shops_total__gte=int(query.shops_min))
            if query.shops_max is not None:
                qs_annotated = qs_annotated.filter(_shops_total__lte=int(query.shops_max))

            total = qs_annotated.count()
            if total > MAX_BULK_LIMIT:
                return {
                    "ok": False,
                    "message": f"Số lượng {total} vượt quá giới hạn {MAX_BULK_LIMIT}. Vui lòng thu hẹp bộ lọc.",
                }

            ids = list(qs_annotated.values_list("id", flat=True))

        # 2) Nếu chỉ update ids được tick
        else:
            for x in project_ids or []:
                try:
                    ids.append(int(x))
                except Exception:
                    pass

        if not ids:
            return {"ok": False, "message": "Bạn chưa chọn dự án nào để cập nhật."}

        updates: Dict[str, Any] = {}
        if new_status:
            updates["status"] = (new_status or "").strip()
        if new_type:
            updates["type"] = normalize_project_type((new_type or "").strip())

        if not updates:
            return {"ok": False, "message": "Không có dữ liệu cập nhật (trạng thái/loại)."}

        # Query hash để audit (nếu có filter)
        qh = None
        if query is not None:
            qh = _query_hash(tid=tid, company_id=company_id, query=query)

        with transaction.atomic():
            qs = mgr(Project).filter(tenant_id=tid, id__in=ids)
            if company_id is not None:
                qs = qs.filter(company_id=int(company_id))

            affected = qs.update(**updates)

        bump_dashboard_cache(tid)

        duration_ms = int((timezone.now() - t0).total_seconds() * 1000)

        # ✅ Audit bulk update
        log_change(
            action="bulk_update",
            model="projects.Project",
            object_id="bulk",
            tenant_id=tid,
            meta={
                "tid": tid,
                "company_id": company_id,
                "select_all_filtered": bool(select_all_filtered),
                "query_hash": qh,
                "requested_ids": len(ids) if not select_all_filtered else None,
                "affected": affected,
                "updates": updates,
                "duration_ms": duration_ms,
            },
            changed_fields=list(updates.keys()),
        )

        scope_msg = "tất cả dự án theo bộ lọc" if select_all_filtered else "các dự án đã chọn"
        return {"ok": True, "message": f"Đã cập nhật {affected} dự án ({scope_msg}).", "updated": affected}