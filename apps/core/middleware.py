from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass
from threading import local
from typing import Any, Dict, Optional
from uuid import uuid4

from django.conf import settings
from django.http import Http404, JsonResponse
from django.utils.deprecation import MiddlewareMixin

from apps.core.audit import log_change
from apps.core.authz import get_actor_ctx
from apps.core.tenant_context import clear_current_tenant, set_current_tenant

# =========================================================
# ACTOR CONTEXT
# =========================================================


class ActorContextMiddleware(MiddlewareMixin):
    """
    Attach:
      request.actor_ctx
      request.role

    SAFE MODE:
    - Không được làm hỏng request nếu authz có lỗi
    - Nếu chưa resolve được thì fallback nhẹ
    """

    def process_request(self, request):
        try:
            ctx = get_actor_ctx(request)
            request.actor_ctx = ctx
            request.role = getattr(ctx, "role", None)
        except Exception:
            request.actor_ctx = None
            user = getattr(request, "user", None)
            if user and getattr(user, "is_authenticated", False):
                request.role = "admin" if (getattr(user, "is_staff", False) or getattr(user, "is_superuser", False)) else "operator"
            else:
                request.role = "anonymous"
        return None


# =========================================================
# REQUEST META / LOG
# =========================================================

_thread_locals = local()
logger = logging.getLogger("apps.request")

REQUEST_LOG_SAMPLE_RATE = 0.15
SLOW_WARN_MS = 800
SLOW_ERROR_MS = 2000
SLOW_REQUEST_MS = 800

LOG_PATH_PREFIXES = ("/dashboard/", "/api/", "/os/", "/work/")
SKIP_PATH_PREFIXES = ("/static/", "/media/")
SKIP_PATH_EXACT = ("/favicon.ico", "/robots.txt", "/healthz")

# route được phép đi tiếp kể cả tenant chưa fully ready
SAFE_BYPASS_PREFIXES = (
    "/admin/",
    "/login/",
    "/register/",
    "/logout/",
    "/static/",
    "/media/",
    "/metrics/",
    "/favicon.ico",
    "/robots.txt",
    "/app/",
    "/os/",
    "/api/",
    "/work/",
)

SAFE_BYPASS_EXACT = {
    "/",
}

SUSPEND_ALLOW_PREFIXES = (
    "/admin/",
    "/healthz",
    "/billing/",
    "/login/",
    "/register/",
    "/logout/",
    "/static/",
    "/media/",
    "/app/",
    "/os/",
    "/api/",
    "/work/",
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


def _is_allowed_when_suspended(path: str) -> bool:
    if not path:
        return True
    if path in SUSPEND_ALLOW_EXACT:
        return True
    return any(path.startswith(p) for p in SUSPEND_ALLOW_PREFIXES)


def _is_safe_bypass_path(path: str) -> bool:
    if not path:
        return True
    if path in SAFE_BYPASS_EXACT:
        return True
    return any(path.startswith(p) for p in SAFE_BYPASS_PREFIXES)


# =========================================================
# CURRENT REQUEST / TENANT / RATE LIMIT
# =========================================================


class CurrentRequestMiddleware(MiddlewareMixin):
    """
    SAFE FINAL:
    - TenantResolveMiddleware nên chạy trước
    - Nhưng nếu path public/system thì không ép tenant
    - Dev/local không bật rate limit để tránh 429
    """

    def process_request(self, request):
        set_current_request(request)

        path = getattr(request, "path", "") or ""

        # admin / static / login / register / os / api / work -> bypass nhẹ
        if _is_safe_bypass_path(path):
            tenant = getattr(request, "tenant", None)
            if tenant is not None:
                request.tenant_id = getattr(tenant, "id", None)
                set_current_tenant(tenant)
            else:
                request.tenant_id = None
            return None

        tenant = getattr(request, "tenant", None)
        if tenant is None:
            raise Http404("Tenant not resolved. Check MIDDLEWARE order.")

        request.tenant_id = getattr(tenant, "id", None)
        set_current_tenant(tenant)

        # billing gate
        try:
            status = getattr(tenant, "status", "active")
            if status == "suspended" and not _is_allowed_when_suspended(path):
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

        # RATE LIMIT:
        # local/dev thì tắt hẳn để không bị 429 lúc boot OS
        try:
            host = request.get_host().split(":")[0].lower()
        except Exception:
            host = ""

        is_dev_host = host in {"127.0.0.1", "localhost", "testserver"}
        enable_rate_limit = not settings.DEBUG and not is_dev_host

        if enable_rate_limit:
            try:
                from apps.core.rate_limit import is_rate_limited
                from apps.core.tenant_quota import get_tenant_quota, has_feature

                if has_feature(tenant, "rate_limit", True):
                    quota = get_tenant_quota(tenant)
                    if is_rate_limited(request.tenant_id, max_requests=quota.req_per_min):
                        return JsonResponse(
                            {
                                "detail": "Rate limit exceeded",
                                "plan": getattr(tenant, "plan", "basic"),
                                "limit_req_per_min": quota.req_per_min,
                            },
                            status=429,
                            headers={"Retry-After": "60"},
                        )
            except Exception:
                # không để rate limit làm sập app local
                pass

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

        path = meta.get("path") or ""
        method = meta.get("method") or ""
        status_code = int(getattr(response, "status_code", 0) or 0)

        try:
            if (not _should_skip_log(path)) and (_should_sample(status_code) or _should_force_log(path)):
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

        try:
            if (not _should_skip_log(path)) and (
                status_code >= 400 or duration_ms >= SLOW_REQUEST_MS or _should_force_log(path)
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
        path = meta.get("path") or ""

        try:
            if not _is_safe_bypass_path(path):
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
