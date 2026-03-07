# apps/api/views_health.py
from __future__ import annotations

from django.http import JsonResponse
from django.utils import timezone

def health_view(request):
    return JsonResponse(
        {
            "ok": True,
            "service": "heighttech",
            "ts": timezone.now().isoformat(),
        }
    )