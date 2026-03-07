from __future__ import annotations

from typing import Any, Dict, Optional

from rest_framework.response import Response


def ok(data: Any, status: int = 200, meta: Optional[Dict[str, Any]] = None) -> Response:
    payload: Dict[str, Any] = {"data": data}
    if meta is not None:
        payload["meta"] = meta
    return Response(payload, status=status)


def error(message: str, status: int = 400, code: str = "bad_request", extra: Optional[Dict[str, Any]] = None) -> Response:
    payload: Dict[str, Any] = {"error": {"code": code, "message": message}}
    if extra:
        payload["error"].update(extra)
    return Response(payload, status=status)