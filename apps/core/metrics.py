# apps/core/metrics.py
from __future__ import annotations

from prometheus_client import Counter, Histogram


REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "path_prefix", "status", "tenant_id"],
)

REQUEST_LATENCY = Histogram(
    "http_request_latency_ms",
    "Request latency in ms",
    ["method", "path_prefix", "tenant_id"],
    buckets=(50, 100, 200, 300, 500, 800, 1200, 2000, 5000),
)

SLOW_REQUEST_COUNT = Counter(
    "http_slow_requests_total",
    "Slow requests total",
    ["path_prefix", "tenant_id"],
)

EXCEPTION_COUNT = Counter(
    "http_exceptions_total",
    "Exceptions total",
    ["exception_type", "path_prefix", "tenant_id"],
)


def path_prefix(path: str) -> str:
    """
    Gom path thành prefix để tránh label quá nhiều (cardinality explosion).
    """
    if not path:
        return "/"
    for p in ("/api/", "/dashboard/", "/admin/"):
        if path.startswith(p):
            return p

    # fallback: lấy cấp 1
    parts = path.split("/")
    if len(parts) > 1 and parts[1]:
        return f"/{parts[1]}/"
    return "/"