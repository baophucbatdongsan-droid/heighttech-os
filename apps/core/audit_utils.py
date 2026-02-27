# apps/core/audit_utils.py
from __future__ import annotations

import datetime as dt
import decimal
import json
import uuid
from typing import Any, Dict, Iterable, Tuple


def json_safe(value: Any) -> Any:
    """
    Convert mọi thứ về dạng JSON serializable.
    - datetime/date -> ISO
    - Decimal -> float
    - UUID -> str
    - model instance -> str(pk)
    """
    if value is None:
        return None

    if isinstance(value, (dt.datetime, dt.date)):
        # ISO format
        try:
            return value.isoformat()
        except Exception:
            return str(value)

    if isinstance(value, dt.time):
        try:
            return value.isoformat()
        except Exception:
            return str(value)

    if isinstance(value, decimal.Decimal):
        try:
            return float(value)
        except Exception:
            return str(value)

    if isinstance(value, uuid.UUID):
        return str(value)

    if isinstance(value, (set, tuple)):
        return [json_safe(x) for x in value]

    if isinstance(value, list):
        return [json_safe(x) for x in value]

    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}

    # Django model instance?
    if hasattr(value, "pk"):
        try:
            return str(value.pk)
        except Exception:
            return str(value)

    # fallback: thử json dumps
    try:
        json.dumps(value)
        return value
    except Exception:
        return str(value)


def model_to_dict_safe(instance, *, fields: Iterable[str] | None = None) -> Dict[str, Any]:
    """
    Serialize instance -> dict (an toàn JSON)
    - Nếu fields=None: lấy toàn bộ field concrete
    """
    data: Dict[str, Any] = {}
    opts = instance._meta

    use_fields = set(fields) if fields else None

    for f in opts.concrete_fields:
        name = f.name
        if use_fields is not None and name not in use_fields:
            continue
        try:
            val = getattr(instance, name)
        except Exception:
            continue
        data[name] = json_safe(val)

    return data


def compute_diff(before: Dict[str, Any], after: Dict[str, Any]) -> Tuple[Dict[str, Any], list[str]]:
    """
    Return:
    - diff: {field: {"before": x, "after": y}}
    - changed_fields: [field...]
    """
    diff: Dict[str, Any] = {}
    changed: list[str] = []

    keys = set(before.keys()) | set(after.keys())
    for k in sorted(keys):
        b = before.get(k)
        a = after.get(k)
        if b != a:
            diff[k] = {"before": b, "after": a}
            changed.append(k)

    return diff, changed