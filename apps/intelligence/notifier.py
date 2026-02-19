from __future__ import annotations

import json
import urllib.request
from django.conf import settings


def send_webhook(payload: dict) -> None:
    url = getattr(settings, "FOUNDER_ALERT_WEBHOOK", "")
    if not url:
        return

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=5)  # nosec
    except Exception:
        # fail silent (đừng làm crash hệ thống)
        return