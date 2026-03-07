from __future__ import annotations

import json
from typing import Any, Dict, Optional

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.test import Client

from apps.accounts.models import Membership


class Command(BaseCommand):
    help = "Smoke test Work APIs (create/move/board/transition/analytics/portal)."

    def add_arguments(self, parser):
        parser.add_argument("--username", default="staff1")
        parser.add_argument("--company-id", type=int, default=None)
        parser.add_argument("--host", default="localhost")
        parser.add_argument("--top", type=int, default=10)
        parser.add_argument("--days", type=int, default=30)

    # =========================================================
    # Helpers
    # =========================================================
    def _json(self, r) -> Dict[str, Any]:
        try:
            return r.json()
        except Exception:
            return {"_raw": r.content[:500].decode("utf-8", errors="ignore")}

    def _must(self, ok: bool, msg: str):
        if not ok:
            raise CommandError(msg)

    def _post_json(self, c: Client, url: str, payload: Dict[str, Any]):
        return c.post(url, data=json.dumps(payload), content_type="application/json")

    def _has_field(self, model_cls, field_name: str) -> bool:
        try:
            return field_name in {f.name for f in model_cls._meta.concrete_fields}
        except Exception:
            return False

    # =========================================================
    # AUTO BOOTSTRAP
    # =========================================================
    def _ensure_user_and_membership(self, username: str, company_id: Optional[int]):
        U = get_user_model()

        # 1) Ensure user exists
        u = U.objects.filter(username=username).first()
        if not u:
            u = U.objects.create_user(username=username, password="123456")
            self.stdout.write(self.style.WARNING(f"[BOOTSTRAP] created user={username}"))

        # Make sure staff can pass IsAuthenticated + AbilityPermission flows (via membership role)
        if not getattr(u, "is_staff", False):
            u.is_staff = True
            u.save(update_fields=["is_staff"])
            self.stdout.write(self.style.WARNING(f"[BOOTSTRAP] set is_staff=True for user={username}"))

        # 2) Ensure membership if company_id provided
        if company_id is not None:
            company_id = int(company_id)

            # Build lookup only with existing fields (schema-safe)
            lookup: Dict[str, Any] = {"user_id": u.id, "company_id": company_id}

            # tenant_id may or may not exist in your schema
            # If it exists and request has tenant context later, you can refine;
            # For smoke command we keep it minimal.
            if self._has_field(Membership, "tenant_id"):
                # Best-effort: set tenant_id to 1 if you have tenant table; if not, user can pass later.
                lookup["tenant_id"] = 1

            m = Membership.objects.filter(**lookup).first()
            created = False
            if not m:
                create_payload = dict(lookup)
                # defaults
                if self._has_field(Membership, "role"):
                    create_payload["role"] = "operator"
                if self._has_field(Membership, "is_active"):
                    create_payload["is_active"] = True
                m = Membership.objects.create(**create_payload)
                created = True

            # enforce operator + active
            dirty_fields = []
            if self._has_field(Membership, "role") and getattr(m, "role", None) != "operator":
                m.role = "operator"
                dirty_fields.append("role")
            if self._has_field(Membership, "is_active") and getattr(m, "is_active", None) is not True:
                m.is_active = True
                dirty_fields.append("is_active")
            if dirty_fields:
                m.save(update_fields=dirty_fields)

            if created:
                self.stdout.write(
                    self.style.WARNING(
                        f"[BOOTSTRAP] membership created company={company_id} role=operator"
                    )
                )

        return u

    # =========================================================
    # MAIN
    # =========================================================
    def handle(self, *args, **opts):
        username: str = opts["username"]
        company_id: Optional[int] = opts["company_id"]
        host: str = opts["host"]
        top: int = int(opts["top"])
        days: int = int(opts["days"])

        u = self._ensure_user_and_membership(username, company_id)

        c = Client(HTTP_HOST=host)
        c.force_login(u)

        self.stdout.write(self.style.MIGRATE_HEADING("=== WORK SMOKE START ==="))
        self.stdout.write(f"User={username} host={host} company_id={company_id} days={days} top={top}")

        # 1) Board
        r = c.get("/api/v1/work/board/")
        self._must(r.status_code == 200, f"board failed: {r.status_code} {r.content[:200]}")
        j = self._json(r)
        self._must(j.get("ok") is True, f"board response not ok: {j}")
        self.stdout.write(self.style.SUCCESS(f"[OK] board totals={j.get('totals')}"))

        # 2) Create item
        payload: Dict[str, Any] = {"title": "SMOKE task", "status": "todo"}
        if company_id is not None:
            payload["company_id"] = int(company_id)

        r = self._post_json(c, "/api/v1/work/items/", payload)
        self._must(r.status_code in (201, 200), f"create failed: {r.status_code} {r.content[:200]}")
        j = self._json(r)
        self._must(j.get("ok") is True, f"create response not ok: {j}")

        item = j.get("item") or {}
        item_id = item.get("id")
        self._must(bool(item_id), f"create missing item.id: {j}")
        self.stdout.write(self.style.SUCCESS(f"[OK] create id={item_id} company_id={item.get('company_id')}"))

        # 3) Transition (prefer /work/items/... ; fallback /work-items/...)
        transition_payload = {"to": "doing"}
        url_new = f"/api/v1/work/items/{item_id}/transition/"
        url_old = f"/api/v1/work-items/{item_id}/transition/"

        r = self._post_json(c, url_new, transition_payload)
        if r.status_code == 404:
            r = self._post_json(c, url_old, transition_payload)

        self._must(r.status_code in (200, 400), f"transition unexpected: {r.status_code} {r.content[:200]}")
        j = self._json(r)
        self._must(j.get("ok") is True, f"transition response not ok: {j}")
        self.stdout.write(self.style.SUCCESS("[OK] transition"))

        # 4) Move item
        r = self._post_json(
            c,
            f"/api/v1/work/items/{item_id}/move/",
            {"to_status": "doing", "to_position": 1},
        )
        self._must(r.status_code == 200, f"move failed: {r.status_code} {r.content[:200]}")
        j = self._json(r)
        self._must(j.get("ok") is True, f"move response not ok: {j}")
        moved = j.get("moved") or {}
        self.stdout.write(self.style.SUCCESS(f"[OK] move {moved.get('from_status')} -> {moved.get('to_status')}"))

        # 5) List items (page_size=1)
        r = c.get("/api/v1/work/items/?page_size=1")
        self._must(r.status_code == 200, f"list failed: {r.status_code} {r.content[:200]}")
        j = self._json(r)
        self._must(j.get("ok") is True, f"list response not ok: {j}")
        first = (j.get("items") or [{}])[0] or {}
        for k in ["role", "can_view", "can_comment", "can_edit", "can_move", "can_delete"]:
            self._must(k in first, f"list missing field '{k}'. got keys={list(first.keys())[:30]}")
        self.stdout.write(self.style.SUCCESS(f"[OK] list flags role={first.get('role')} can_edit={first.get('can_edit')}"))

        # 6) Analytics
        endpoints = [
            f"/api/v1/work/analytics/workload/?days={days}&top={top}",
            f"/api/v1/work/analytics/overdue/?top={top}",
            f"/api/v1/work/analytics/velocity/?days={days}",
            f"/api/v1/work/analytics/performance/company/?top={top}&days={days}",
        ]
        for url in endpoints:
            r = c.get(url)
            self._must(r.status_code == 200, f"analytics failed {url}: {r.status_code} {r.content[:200]}")
            j = self._json(r)
            self._must(j.get("ok") is True, f"analytics not ok {url}: {j}")
            self.stdout.write(self.style.SUCCESS(f"[OK] {url}"))

        # 7) Portal summary (optional)
        r = c.get("/api/v1/work/portal/summary/")
        if r.status_code == 200:
            j = self._json(r)
            if j.get("ok") is True:
                self.stdout.write(self.style.SUCCESS(f"[OK] portal summary role={j.get('role')} totals={j.get('counts')}"))
            else:
                self.stdout.write(self.style.WARNING(f"[WARN] portal summary not ok: {j}"))
        else:
            self.stdout.write(self.style.WARNING(f"[WARN] portal summary not available: {r.status_code}"))

        self.stdout.write(self.style.SUCCESS("=== WORK SMOKE DONE ==="))