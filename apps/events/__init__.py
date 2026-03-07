# apps/events/__init__.py
from __future__ import annotations

def setup_event_handlers():
    from apps.events.handlers import bootstrap_handlers
    bootstrap_handlers()