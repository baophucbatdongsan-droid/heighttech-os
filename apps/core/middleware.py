# apps/core/middleware.py
from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass
from threading import local
from typing import Any, Dict, Optional
from uuid import uuid4

from django.conf import settings
from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin

from apps.core.audit import log_change
from apps.core.tenant_context import set_current_tenant, clear_current_tenant

_thread_locals = local()
logger = logging.getLogger("apps.request")

# =========================
# LOG CONFIG
# =========================
REQUEST_LOG_SAMPLE_RATE = 0.15  # 15% request OK sẽ log
SLOW_WARN_MS = 800
SLOW_ERROR_MS = 2000
SLOW_REQUEST_MS = 800  # ngưỡng request chậm => log DB (audit)

LOG_PATH_PREFIXES = ("/dashboard/", "/api/")
SKIP_PATH_PREFIXES = ("/static/", "/media/", "/admin/")
SKIP_PATH_EXACT = ("/favicon.ico", "/robots.txt", "/healthz")

# =========================
# SUSPEND / BILLING GATE (Level 17)
# =========================
SUSPEND_ALLOW_PREFIXES = (
    "/admin/",
    "/healthz",
    "/billing/",
    "/login/",
    "/logout/",
    "/static/",
    "/media/",
)

SUSPEND_ALLOW_EXACT = ("/",)


def _should_sample(status_code: int) -> bool:
    if status_code >= 400:
        return True
    return random.random() < REQUEST_LOG_SAMPLE_RATE


def _should_skip_log(path: str) -> bool:
    if not path:
        return True
    if path in SKIP_PATH_EXACT:
        return True
    return any(path.startswith(p) for p in SKIP_PATH_PREFIXES)


def _should_force_log(path: str) -> bool:
    return any(path.startswith(p) for p in LOG_PATH_PREFIXES)


def _get_client_ip(request) -> str:
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "") or ""


def _extract_trace_id(request) -> str:
    h = request.headers
    trace_id = (h.get("X-Trace-Id") or h.get("X-Trace-ID") or "").strip()
    if trace_id:
        return trace_id

    rid_up = (h.get("X-Request-Id") or h.get("X-Request-ID") or "").strip()
    if rid_up:
        return rid_up

    tp = (h.get("traceparent") or "").strip()
    if tp and "-" in tp:
        parts = tp.split("-")
        if len(parts) >= 2 and parts[1]:
            return parts[1]
    return ""


@dataclass
class RequestMeta:
    path: str = ""
    method: str = ""
    ip: str = ""
    user_agent: str = ""
    referer: str = ""
    request_id: str = ""
    trace_id: str = ""
    started_at: float = 0.0


def set_current_request(request) -> None:
    _thread_locals.request = request
    _thread_locals.user = getattr(request, "user", None)

    req_id = (
        request.headers.get("X-Request-Id")
        or request.headers.get("X-Request-ID")
        or request.META.get("HTTP_X_REQUEST_ID")
        or ""
    ).strip()
    if not req_id:
        req_id = uuid4().hex

    trace_id = _extract_trace_id(request)

    request.request_id = req_id
    request.trace_id = trace_id

    _thread_locals.meta = RequestMeta(
        path=getattr(request, "path", "") or "",
        method=getattr(request, "method", "") or "",
        ip=_get_client_ip(request),
        user_agent=request.META.get("HTTP_USER_AGENT", "") or "",
        referer=request.META.get("HTTP_REFERER", "") or "",
        request_id=req_id,
        trace_id=trace_id,
        started_at=time.time(),
    )


def clear_current_request() -> None:
    for k in ("request", "user", "meta"):
        if hasattr(_thread_locals, k):
            delattr(_thread_locals, k)


def get_current_request_meta() -> Dict[str, Any]:
    meta: Optional[RequestMeta] = getattr(_thread_locals, "meta", None)
    if not meta:
        return {}
    return {
        "path": meta.path,
        "method": meta.method,
        "ip": meta.ip,
        "user_agent": meta.user_agent,
        "referer": meta.referer,
        "request_id": meta.request_id,
        "trace_id": meta.trace_id,
        "started_at": meta.started_at,
    }


def get_current_tenant_id() -> Optional[int]:
    """
    Backward-compatible helper for RequestContextFilter.
    """
    try:
        req = getattr(_thread_locals, "request", None)
        tenant = getattr(req, "tenant", None) if req else None
        tid = getattr(tenant, "id", None) if tenant else getattr(req, "tenant_id", None)
        if tid:
            return int(tid)
    except Exception:
        pass
    return None


def _is_allowed_when_suspended(path: str) -> bool:
    if not path:
        return True
    if path in SUSPEND_ALLOW_EXACT:
        return True
    return any(path.startswith(p) for p in SUSPEND_ALLOW_PREFIXES)


# =========================
# TENANT FALLBACK (FINAL FIX)
# =========================
def _pick_tenant_from_headers(request):
    """
    Hỗ trợ các header phổ biến cho tenant:
      - X-Tenant-Id / X-Tenant-ID
      - X-Tenant
      - X-Tenant-Name
    """
    h = request.headers
    raw_id = (h.get("X-Tenant-Id") or h.get("X-Tenant-ID") or h.get("X-Tenant") or "").strip()
    raw_name = (h.get("X-Tenant-Name") or "").strip()

    try:
        from apps.tenants.models import Tenant
    except Exception:
        return None

    if raw_id:
        try:
            tid = int(raw_id)
            t = Tenant.objects.filter(id=tid).first()
            if t:
                return t
        except Exception:
            pass

    if raw_name:
        # nếu tenant model bạn dùng field khác (slug/name), đổi ở đây
        t = Tenant.objects.filter(name__iexact=raw_name).first()
        if t:
            return t

    return None


def _fallback_tenant():
    """
    Fallback cứng: DEFAULT_TENANT_ID -> Tenant.first()
    """
    try:
        from apps.tenants.models import Tenant
    except Exception:
        return None

    default_tid = getattr(settings, "DEFAULT_TENANT_ID", 1)
    t = Tenant.objects.filter(id=int(default_tid)).first()
    if t:
        return t
    return Tenant.objects.first()


class CurrentRequestMiddleware(MiddlewareMixin):
    """
    Level 11: request_id/trace_id + tenant context + audit
    Level 12: structured log + sampling
    Level 13: tenant resolver cached + rate limit
    Level 14: Prometheus metrics
    Level 15: quota theo plan + feature flags
    Level 16: Usage metering (Redis) -> invoice-ready
    Level 17: Billing enforcement (SUSPENDED -> block 402)
    """

    def process_request(self, request):
        set_current_request(request)

        # ✅ Level 13: tenant resolver cached
        from apps.core.tenant_resolver import resolve_tenant_cached
        tenant = resolve_tenant_cached(request)

        # ✅ FINAL FIX:
        # 1) nếu resolver fail => thử lấy từ header
        # 2) vẫn fail => fallback default tenant
        if tenant is None:
            tenant = _pick_tenant_from_headers(request)
        if tenant is None:
            tenant = _fallback_tenant()

        request.tenant = tenant
        request.tenant_id = getattr(tenant, "id", None)
        set_current_tenant(tenant)

        path = getattr(request, "path", "") or ""

        # ✅ Level 17: block suspended tenant (trừ allowlist)
        try:
            status = getattr(tenant, "status", "active") if tenant else "active"
            if status == "suspended" and not _is_allowed_when_suspended(path):
                try:
                    from apps.billing.metering import incr_usage
                    incr_usage(request.tenant_id, "requests", 1)
                    incr_usage(request.tenant_id, "errors", 1)
                except Exception:
                    pass

                return JsonResponse(
                    {
                        "detail": "Tenant is suspended. Please upgrade or pay invoice.",
                        "code": "TENANT_SUSPENDED",
                        "tenant_id": request.tenant_id,
                        "plan": getattr(tenant, "plan", "basic"),
                    },
                    status=402,
                )
        except Exception:
            pass

        # ✅ Level 15: rate limit theo plan + feature flags
        from apps.core.rate_limit import is_rate_limited
        from apps.core.tenant_quota import get_tenant_quota, has_feature

        if has_feature(tenant, "rate_limit", True):
            quota = get_tenant_quota(tenant)
            if is_rate_limited(request.tenant_id, max_requests=quota.req_per_min):
                try:
                    from apps.billing.metering import incr_usage
                    incr_usage(request.tenant_id, "rate_limited", 1)
                    incr_usage(request.tenant_id, "requests", 1)
                except Exception:
                    pass

                return JsonResponse(
                    {
                        "detail": "Rate limit exceeded",
                        "plan": getattr(tenant, "plan", "basic"),
                        "limit_req_per_min": quota.req_per_min,
                    },
                    status=429,
                    headers={"Retry-After": "60"},
                )

        return None

    def process_response(self, request, response):
        meta = get_current_request_meta()

        rid = getattr(request, "request_id", "") or meta.get("request_id") or ""
        tid = getattr(request, "tenant_id", None)

        if rid:
            response["X-Request-ID"] = rid

        trace_id = getattr(request, "trace_id", "") or meta.get("trace_id") or ""
        if trace_id:
            response["X-Trace-ID"] = trace_id

        started_at = float(meta.get("started_at") or 0.0)
        duration_ms = int((time.time() - started_at) * 1000) if started_at else 0

        path = (meta.get("path") or "")
        method = (meta.get("method") or "")
        status_code = int(getattr(response, "status_code", 0) or 0)

        # ✅ Level 16: usage metering (Redis) (không double count 429)
        try:
            if status_code != 429:
                from apps.billing.metering import incr_usage
                incr_usage(tid, "requests", 1)
                if status_code >= 400:
                    incr_usage(tid, "errors", 1)
                if duration_ms >= SLOW_REQUEST_MS:
                    incr_usage(tid, "slow", 1)
        except Exception:
            pass

        # ✅ Level 12: structured log (sampling)
        try:
            if (not _should_skip_log(path)) and _should_sample(status_code):
                level = logging.INFO
                if duration_ms >= SLOW_ERROR_MS or status_code >= 500:
                    level = logging.ERROR
                elif duration_ms >= SLOW_WARN_MS or status_code >= 400:
                    level = logging.WARNING

                logger.log(
                    level,
                    "request_completed",
                    extra={
                        "status_code": status_code,
                        "duration_ms": duration_ms,
                        "tenant_id": tid,
                        "request_id": rid,
                        "trace_id": trace_id,
                        "path": path,
                        "method": method,
                    },
                )
        except Exception:
            pass

        # ✅ Level 14: Prometheus metrics
        try:
            from apps.core.metrics import (
                REQUEST_COUNT,
                REQUEST_LATENCY,
                SLOW_REQUEST_COUNT,
                path_prefix as _pp,
            )
            tenant_label = str(tid or 0)
            pfx = _pp(path)

            REQUEST_COUNT.labels(
                method=method,
                path_prefix=pfx,
                status=str(status_code),
                tenant_id=tenant_label,
            ).inc()

            REQUEST_LATENCY.labels(
                method=method,
                path_prefix=pfx,
                tenant_id=tenant_label,
            ).observe(float(duration_ms))

            if duration_ms >= SLOW_REQUEST_MS:
                SLOW_REQUEST_COUNT.labels(path_prefix=pfx, tenant_id=tenant_label).inc()
        except Exception:
            pass

        # ✅ Level 11: audit log anti-spam
        try:
            if (not _should_skip_log(path)) and (
                status_code >= 400
                or duration_ms >= SLOW_REQUEST_MS
                or _should_force_log(path)
            ):
                log_change(
                    action="request",
                    model="system.Request",
                    object_id=rid or "unknown",
                    tenant_id=tid,
                    meta={
                        "status_code": status_code,
                        "duration_ms": duration_ms,
                        "path": path,
                        "method": method,
                        "request_id": rid,
                        "trace_id": trace_id,
                    },
                )
        except Exception:
            pass

        clear_current_tenant()
        clear_current_request()
        return response

    def process_exception(self, request, exception):
        meta = get_current_request_meta()
        rid = getattr(request, "request_id", "") or meta.get("request_id") or ""
        tid = getattr(request, "tenant_id", None)

        # ✅ Level 16: metering lỗi exception
        try:
            from apps.billing.metering import incr_usage
            incr_usage(tid, "errors", 1)
        except Exception:
            pass

        # ✅ Level 14: exception metrics
        try:
            from apps.core.metrics import EXCEPTION_COUNT, path_prefix as _pp
            tenant_label = str(tid or 0)
            pfx = _pp(meta.get("path") or "")
            EXCEPTION_COUNT.labels(
                exception_type=type(exception).__name__,
                path_prefix=pfx,
                tenant_id=tenant_label,
            ).inc()
        except Exception:
            pass

        # ✅ Level 11: audit exception
        try:
            log_change(
                action="exception",
                model="system.Exception",
                object_id=rid or "unknown",
                tenant_id=tid,
                meta={
                    "path": meta.get("path"),
                    "method": meta.get("method"),
                    "request_id": meta.get("request_id"),
                    "trace_id": meta.get("trace_id"),
                    "exception_type": type(exception).__name__,
                    "message": str(exception),
                },
            )
        except Exception:
            pass

        clear_current_tenant()
        clear_current_request()
        return None