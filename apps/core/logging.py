from __future__ import annotations

import logging
from typing import Any, Dict

from apps.core.middleware import get_current_request_meta, get_current_tenant_id


class RequestContextFilter(logging.Filter):

    def filter(self, record: logging.LogRecord) -> bool:
        meta: Dict[str, Any] = get_current_request_meta()
        record.request_id = meta.get("request_id") or ""
        record.trace_id = meta.get("trace_id") or ""
        record.tenant_id = get_current_tenant_id()
        record.ip = meta.get("ip") or ""
        record.path = meta.get("path") or ""
        record.method = meta.get("method") or ""
        return True