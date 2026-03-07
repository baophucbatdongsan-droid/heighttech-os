# apps/work/management/commands/stress_work_move.py
from __future__ import annotations

import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Tuple

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import close_old_connections, connection, transaction
from django.test import Client
from django.utils import timezone

from apps.work.models import WorkItem


class Command(BaseCommand):
    help = (
        "Stress test Work move/reorder under concurrency.\n"
        "Creates + transitions + moves many items in parallel to catch UNIQUE collisions/races."
    )

    def add_arguments(self, parser):
        parser.add_argument("--tenant-id", type=int, required=True)
        parser.add_argument("--company-id", type=int, required=True)
        parser.add_argument("--username", type=str, default="admin")
        parser.add_argument("--workers", type=int, default=6, help="Number of concurrent workers (threads).")
        parser.add_argument("--iterations", type=int, default=50, help="Ops per worker.")
        parser.add_argument("--seed", type=int, default=7)
        parser.add_argument("--sleep-ms", type=int, default=0, help="Optional tiny sleep between ops per worker.")
        parser.add_argument("--verbose-errors", action="store_true")

    def handle(self, *args, **opts):
        tenant_id = int(opts["tenant_id"])
        company_id = int(opts["company_id"])
        username = str(opts["username"])
        workers = int(opts["workers"])
        iterations = int(opts["iterations"])
        seed = int(opts["seed"])
        sleep_ms = int(opts["sleep_ms"])
        verbose_errors = bool(opts["verbose_errors"])

        random.seed(seed)

        user = get_user_model().objects.filter(username=username).first()
        if not user:
            raise SystemExit(f"User '{username}' not found")

        self.stdout.write(self.style.WARNING("=== WORK STRESS START ==="))
        self.stdout.write(f"tenant_id={tenant_id} company_id={company_id} user={username} workers={workers} iterations={iterations}")

        t0 = time.time()
        errors: List[Tuple[int, str]] = []

        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = []
            for wid in range(1, workers + 1):
                futs.append(
                    ex.submit(
                        _worker_run,
                        wid,
                        tenant_id,
                        company_id,
                        user.pk,
                        iterations,
                        sleep_ms,
                    )
                )

            for fut in as_completed(futs):
                ok, worker_errors = fut.result()
                errors.extend(worker_errors)

        # Validate invariants at end
        inv_ok, inv_msg = _validate_positions(tenant_id=tenant_id, company_id=company_id)

        dt = int((time.time() - t0) * 1000)

        if errors:
            self.stdout.write(self.style.ERROR(f"[FAIL] errors={len(errors)} duration_ms={dt}"))
            if verbose_errors:
                for wid, msg in errors[:200]:
                    self.stdout.write(self.style.ERROR(f"  worker#{wid}: {msg}"))
            raise SystemExit("Stress test failed (see errors).")

        if not inv_ok:
            self.stdout.write(self.style.ERROR(f"[FAIL] invariant: {inv_msg} duration_ms={dt}"))
            raise SystemExit("Invariant check failed.")

        self.stdout.write(self.style.SUCCESS(f"[OK] duration_ms={dt} workers={workers} iterations={iterations}"))
        self.stdout.write(self.style.SUCCESS(inv_msg))
        self.stdout.write(self.style.WARNING("=== WORK STRESS DONE ==="))


def _worker_run(
    worker_id: int,
    tenant_id: int,
    company_id: int,
    user_id: int,
    iterations: int,
    sleep_ms: int,
) -> Tuple[bool, List[Tuple[int, str]]]:
    """
    IMPORTANT:
    - Each thread must have its own DB connection lifecycle.
    - Close old connections at start + end.
    - Use Django test Client (isolated per thread).
    """
    close_old_connections()

    # Each worker gets its own RNG stream
    rnd = random.Random(10_000 + worker_id)

    c = Client()
    # Force login by user_id (works in tests)
    c.force_login(get_user_model().objects.get(pk=user_id))

    errs: List[Tuple[int, str]] = []

    try:
        for it in range(1, iterations + 1):
            # 1) create
            title = f"STRESS w{worker_id} it{it} {timezone.now().isoformat()}"
            payload = {
                "title": title,
                "company_id": company_id,
                "status": "todo",
            }
            r = c.post("/api/v1/work/items/", data=payload)
            if r.status_code not in (200, 201):
                errs.append((worker_id, f"create status={r.status_code} body={_safe_body(r)}"))
                continue

            try:
                item_id = r.json().get("id")
            except Exception:
                item_id = None

            if not item_id:
                # fallback: extremely defensive
                item_id = _find_latest_item_id(tenant_id, company_id, title)
                if not item_id:
                    errs.append((worker_id, "create ok but cannot resolve item_id"))
                    continue

            # 2) transition to doing
            r = c.post(
                f"/api/v1/work/items/{item_id}/transition/",
                data={"to_status": "doing", "note": "stress"},
                content_type="application/json",
            )
            if r.status_code != 200:
                errs.append((worker_id, f"transition status={r.status_code} body={_safe_body(r)}"))
                continue

            # 3) move within doing (randomly to 1 or last-ish)
            to_pos = 1 if rnd.random() < 0.7 else rnd.randint(1, 10)
            r = c.post(
                f"/api/v1/work/items/{item_id}/move/",
                data={"to_status": "doing", "to_position": to_pos},
                content_type="application/json",
            )
            if r.status_code != 200:
                errs.append((worker_id, f"move same-col status={r.status_code} body={_safe_body(r)}"))
                continue

            # 4) sometimes move across columns to trigger both sides shifting
            if rnd.random() < 0.30:
                to_status = "todo" if rnd.random() < 0.5 else "doing"
                to_pos2 = 1 if rnd.random() < 0.7 else rnd.randint(1, 10)
                r = c.post(
                    f"/api/v1/work/items/{item_id}/move/",
                    data={"to_status": to_status, "to_position": to_pos2},
                    content_type="application/json",
                )
                if r.status_code != 200:
                    errs.append((worker_id, f"move cross-col status={r.status_code} body={_safe_body(r)}"))
                    continue

            if sleep_ms > 0:
                time.sleep(sleep_ms / 1000.0)

    except Exception as e:
        errs.append((worker_id, f"worker exception: {repr(e)}"))
    finally:
        # Close thread DB connection
        try:
            connection.close()
        except Exception:
            pass
        close_old_connections()

    return (len(errs) == 0), errs


def _safe_body(resp) -> str:
    try:
        return (resp.content or b"")[:500].decode("utf-8", errors="ignore")
    except Exception:
        return "<no-body>"


def _find_latest_item_id(tenant_id: int, company_id: int, title: str) -> int | None:
    wi = (
        WorkItem.objects_all.filter(tenant_id=tenant_id, company_id=company_id, title=title)
        .order_by("-id")
        .first()
    )
    return wi.id if wi else None


def _validate_positions(*, tenant_id: int, company_id: int) -> Tuple[bool, str]:
    """
    Validate per (tenant, company, status):
    - positions are 1..n
    - no duplicates
    """
    qs = WorkItem.objects_all.filter(tenant_id=tenant_id, company_id=company_id).only("id", "status", "position")
    statuses = sorted(set(qs.values_list("status", flat=True)))

    for st in statuses:
        rows = list(qs.filter(status=st).order_by("position", "id").values_list("position", flat=True))
        if not rows:
            continue

        # all >=1
        if any((p is None or int(p) < 1) for p in rows):
            return False, f"status={st}: has position < 1"

        # no duplicates
        if len(set(rows)) != len(rows):
            return False, f"status={st}: duplicate positions found"

        # should be 1..n (strong invariant after normalize)
        n = len(rows)
        expected = list(range(1, n + 1))
        if [int(x) for x in rows] != expected:
            return False, f"status={st}: positions not contiguous 1..n (n={n})"

    return True, f"Invariant OK for tenant={tenant_id} company={company_id} (all statuses contiguous 1..n)"