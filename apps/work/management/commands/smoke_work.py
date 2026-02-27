# apps/work/management/commands/smoke_work.py
from __future__ import annotations

import json
from typing import Any, Dict, Optional

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.test import Client


class Command(BaseCommand):
    help = "Smoke test Work APIs (create/move/board/analytics/portal)."

    def add_arguments(self, parser):
        parser.add_argument("--username", default="staff1", help="Username to login for staff/operator tests")
        parser.add_argument("--company-id", type=int, default=None, help="Company ID for create task (optional)")
        parser.add_argument("--host", default="localhost", help="HTTP_HOST for Django test client (default: localhost)")
        parser.add_argument("--top", type=int, default=10, help="Top N for analytics endpoints")
        parser.add_argument("--days", type=int, default=30, help="Days window for analytics endpoints")

    def _json(self, r) -> Dict[str, Any]:
        try:
            return r.json()
        except Exception:
            return {"_raw": r.content[:500].decode("utf-8", errors="ignore")}

    def _must(self, ok: bool, msg: str):
        if not ok:
            raise CommandError(msg)

    def handle(self, *args, **opts):
        username: str = opts["username"]
        company_id: Optional[int] = opts["company_id"]
        host: str = opts["host"]
        top: int = int(opts["top"])
        days: int = int(opts["days"])

        U = get_user_model()
        u = U.objects.filter(username=username).first()
        self._must(u is not None, f"User not found: {username}")

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

        r = c.post("/api/v1/work/items/", data=json.dumps(payload), content_type="application/json")
        self._must(r.status_code in (201, 200), f"create failed: {r.status_code} {r.content[:200]}")
        j = self._json(r)
        self._must(j.get("ok") is True, f"create response not ok: {j}")
        item = j.get("item") or {}
        item_id = item.get("id")
        self._must(bool(item_id), f"create missing item.id: {j}")
        self.stdout.write(self.style.SUCCESS(f"[OK] create id={item_id} company_id={item.get('company_id')}"))

        # 2.1) Nếu company_id bị None => patch bằng SUPERUSER (staff patch sẽ 404 vì out-of-scope)
        if company_id is not None and (item.get("company_id") is None):
            admin = U.objects.filter(is_superuser=True).first()
            self._must(admin is not None, "No superuser found to patch company_id")

            c_admin = Client(HTTP_HOST=host)
            c_admin.force_login(admin)

            r_fix = c_admin.patch(
                f"/api/v1/work/items/{item_id}/",
                data=json.dumps({"company_id": int(company_id)}),
                content_type="application/json",
            )
            self._must(r_fix.status_code == 200, f"patch company_id failed: {r_fix.status_code} {r_fix.content[:200]}")
            j_fix = self._json(r_fix)
            self._must(j_fix.get("ok") is True, f"patch response not ok: {j_fix}")
            fixed_company = (j_fix.get("item") or {}).get("company_id")
            self._must(int(fixed_company or 0) == int(company_id), f"patch not applied expected={company_id} got={fixed_company}")
            self.stdout.write(self.style.SUCCESS(f"[OK] patched company_id={fixed_company} for item={item_id}"))

        # 3) Move item (staff1 move)
        r = c.post(
            f"/api/v1/work/items/{item_id}/move/",
            data=json.dumps({"to_status": "doing", "to_position": 1}),
            content_type="application/json",
        )
        self._must(r.status_code == 200, f"move failed: {r.status_code} {r.content[:200]}")
        j = self._json(r)
        self._must(j.get("ok") is True, f"move response not ok: {j}")
        moved = j.get("moved") or {}
        self.stdout.write(self.style.SUCCESS(f"[OK] move {moved.get('from_status')} -> {moved.get('to_status')}"))

        # 4) List items (page_size=1) + FE flags exist
        r = c.get("/api/v1/work/items/?page_size=1")
        self._must(r.status_code == 200, f"list failed: {r.status_code} {r.content[:200]}")
        j = self._json(r)
        self._must(j.get("ok") is True, f"list response not ok: {j}")
        first = (j.get("items") or [{}])[0] or {}
        for k in ["role", "can_view", "can_comment", "can_edit", "can_move", "can_delete"]:
            self._must(k in first, f"list missing field '{k}'. got keys={list(first.keys())[:30]}")
        self.stdout.write(self.style.SUCCESS(f"[OK] list flags role={first.get('role')} can_edit={first.get('can_edit')}"))

        # 5) Analytics endpoints
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

        # 6) Portal summary (optional)
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