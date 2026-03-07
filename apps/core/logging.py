# apps/core/logging.py
from __future__ import annotations

import logging


class RequestContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # đảm bảo formatter không nổ KeyError
        record.request_id = getattr(record, "request_id", "") or ""
        record.trace_id = getattr(record, "trace_id", "") or ""
        record.tenant_id = getattr(record, "tenant_id", None)
        record.ip = getattr(record, "ip", "") or ""
        record.method = getattr(record, "method", "") or ""
        record.path = getattr(record, "path", "") or ""

        try:
            # late import: tránh AppRegistryNotReady khi Django chưa setup xong
            from apps.core.middleware import get_current_request_meta, get_current_tenant_id

            meta = get_current_request_meta() or {}
            record.request_id = meta.get("request_id", "") or ""
            record.trace_id = meta.get("trace_id", "") or ""
            record.ip = meta.get("ip", "") or ""
            record.method = meta.get("method", "") or ""
            record.path = meta.get("path", "") or ""
            record.tenant_id = get_current_tenant_id()
        except Exception:
            pass

        return True