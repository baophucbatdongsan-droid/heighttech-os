# apps/work/management/commands/stress_work_move_db.py
from __future__ import annotations

import random
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Tuple

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import IntegrityError, close_old_connections, connection, transaction

from apps.work.models import WorkItem, WorkComment, WorkItemTransitionLog
from apps.work.services_move import create_work_item, move_work_item


STRESS_PREFIX_DEFAULT = "STRESS_RANK"


class Command(BaseCommand):
    help = "DB-level stress test (RANK): create + transition + move concurrently."

    def add_arguments(self, parser):
        parser.add_argument("--tenant-id", type=int, required=True)
        parser.add_argument("--company-id", type=int, required=True)
        parser.add_argument("--username", type=str, default="admin")

        parser.add_argument("--workers", type=int, default=6)
        parser.add_argument("--iterations", type=int, default=120)
        parser.add_argument("--seed", type=int, default=7)
        parser.add_argument("--sleep-ms", type=int, default=0)
        parser.add_argument("--verbose-errors", action="store_true")

        parser.add_argument("--top-rate", type=float, default=0.15)
        parser.add_argument("--cross-rate", type=float, default=0.15)
        parser.add_argument("--max-pos", type=int, default=25)

        parser.add_argument("--stress-prefix", type=str, default=STRESS_PREFIX_DEFAULT)
        parser.add_argument("--purge", action="store_true", help="Delete old stress items by prefix before running")

        parser.add_argument("--print-errors", type=int, default=200)
        parser.add_argument("--purge-batch", type=int, default=500, help="Batch size for purge deletes")

    def handle(self, *args, **opts):
        tenant_id = int(opts["tenant_id"])
        company_id = int(opts["company_id"])
        username = str(opts["username"])

        workers = int(opts["workers"])
        iterations = int(opts["iterations"])
        seed = int(opts["seed"])
        sleep_ms = int(opts["sleep_ms"])
        verbose_errors = bool(opts["verbose_errors"])

        top_rate = float(opts["top_rate"])
        cross_rate = float(opts["cross_rate"])
        max_pos = int(opts["max_pos"])

        stress_prefix = str(opts["stress_prefix"] or STRESS_PREFIX_DEFAULT).strip()
        purge = bool(opts["purge"])
        print_errors = int(opts["print_errors"])
        purge_batch = int(opts["purge_batch"])

        random.seed(seed)

        user = get_user_model().objects.filter(username=username).first()
        if not user:
            raise SystemExit(f"User '{username}' not found")

        self.stdout.write(self.style.WARNING("=== WORK DB STRESS START (RANK) ==="))
        self.stdout.write(
            f"tenant_id={tenant_id} company_id={company_id} user={username} "
            f"workers={workers} iterations={iterations} top_rate={top_rate} "
            f"cross_rate={cross_rate} max_pos={max_pos} prefix={stress_prefix!r} purge={purge}"
        )

        if purge:
            deleted = _purge_stress_rows(
                tenant_id=tenant_id,
                company_id=company_id,
                stress_prefix=stress_prefix,
                batch_size=purge_batch,
            )
            self.stdout.write(self.style.WARNING(f"Purged {deleted} old stress items (prefix={stress_prefix!r})"))

        t0 = time.time()
        errors: List[Tuple[int, str]] = []

        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = [
                ex.submit(
                    _worker,
                    wid,
                    tenant_id,
                    company_id,
                    user.pk,
                    iterations,
                    sleep_ms,
                    top_rate,
                    cross_rate,
                    max_pos,
                    seed,
                    stress_prefix,
                    verbose_errors,  # pass down
                )
                for wid in range(1, workers + 1)
            ]
            for fut in as_completed(futs):
                _ok, worker_errors = fut.result()
                errors.extend(worker_errors)

        inv_ok, inv_msg = _validate_rank(tenant_id=tenant_id, company_id=company_id)
        dt = int((time.time() - t0) * 1000)

        if errors:
            self.stdout.write(self.style.ERROR(f"[FAIL] errors={len(errors)} duration_ms={dt}"))
            if verbose_errors:
                for wid, msg in errors[: max(1, print_errors)]:
                    self.stdout.write(self.style.ERROR(f"  worker#{wid}: {msg}"))
            raise SystemExit("DB stress failed (see errors).")

        if not inv_ok:
            self.stdout.write(self.style.ERROR(f"[FAIL] invariant: {inv_msg} duration_ms={dt}"))
            raise SystemExit("Invariant check failed.")

        self.stdout.write(self.style.SUCCESS(f"[OK] duration_ms={dt} workers={workers} iterations={iterations}"))
        self.stdout.write(self.style.SUCCESS(inv_msg))
        self.stdout.write(self.style.WARNING("=== WORK DB STRESS DONE ==="))


def _purge_stress_rows(*, tenant_id: int, company_id: int, stress_prefix: str, batch_size: int = 500) -> int:
    """
    Purge stress WorkItem rows by prefix without FK violations:
    delete children first (transition logs, comments) then parent (workitems).
    """
    total_deleted = 0

    while True:
        wi_ids = list(
            WorkItem.objects_all.filter(
                tenant_id=tenant_id,
                company_id=company_id,
                title__startswith=stress_prefix,
            )
            .order_by("id")
            .values_list("id", flat=True)[:batch_size]
        )

        if not wi_ids:
            break

        with transaction.atomic():
            WorkItemTransitionLog.objects.filter(
                tenant_id=tenant_id,
                company_id=company_id,
                workitem_id__in=wi_ids,
            ).delete()

            WorkComment.objects_all.filter(
                tenant_id=tenant_id,
                work_item_id__in=wi_ids,
            ).delete()

            deleted, _ = WorkItem.objects_all.filter(id__in=wi_ids).delete()
            total_deleted += int(deleted)

    return total_deleted


def _reset_db_connection_for_thread() -> None:
    """
    ThreadPool + Django:
    - close_old_connections()
    - ensure autocommit ON
    - close connection to force a clean one next query
    """
    try:
        close_old_connections()
    except Exception:
        pass

    # ensure autocommit ON (thread may inherit weird state)
    try:
        transaction.set_autocommit(True)
    except Exception:
        pass

    try:
        connection.close()
    except Exception:
        pass

    try:
        close_old_connections()
    except Exception:
        pass

    try:
        transaction.set_autocommit(True)
    except Exception:
        pass


def _db_cleanup_after_error() -> None:
    """
    After any DB error:
    - rollback if possible
    - restore autocommit
    - close connection to clear broken transaction state
    """
    try:
        connection.rollback()
    except Exception:
        pass

    try:
        transaction.set_autocommit(True)
    except Exception:
        pass

    try:
        connection.close()
    except Exception:
        pass

    try:
        close_old_connections()
    except Exception:
        pass

    try:
        transaction.set_autocommit(True)
    except Exception:
        pass


def _format_exc_short(limit: int = 12) -> str:
    try:
        return traceback.format_exc(limit=limit)
    except Exception:
        return ""


def _worker(
    worker_id: int,
    tenant_id: int,
    company_id: int,
    user_id: int,
    iterations: int,
    sleep_ms: int,
    top_rate: float,
    cross_rate: float,
    max_pos: int,
    seed: int,
    stress_prefix: str,
    verbose_errors: bool,
):
    _reset_db_connection_for_thread()

    rnd = random.Random((seed * 100_000) + worker_id)
    actor = get_user_model().objects.get(pk=user_id)

    errs: List[Tuple[int, str]] = []

    try:
        for it in range(1, iterations + 1):
            title = f"{stress_prefix} w{worker_id} it{it} r{rnd.randint(100000, 999999)}"

            # CREATE
            try:
                wi = create_work_item(
                    tenant_id=tenant_id,
                    company_id=company_id,
                    title=title,
                    status="todo",
                    created_by_id=actor.pk,
                    requester_id=actor.pk,
                )
            except Exception as e:
                tb = _format_exc_short() if verbose_errors else ""
                msg = f"create err: {repr(e)}"
                if tb:
                    msg += f"\n{tb}"
                errs.append((worker_id, msg))
                _db_cleanup_after_error()
                continue

            # TRANSITION todo -> doing
            try:
                wi.transition_to("doing", actor=actor, note="stress")
            except Exception as e:
                tb = _format_exc_short() if verbose_errors else ""
                msg = f"transition err item={wi.id}: {repr(e)}"
                if tb:
                    msg += f"\n{tb}"
                errs.append((worker_id, msg))
                _db_cleanup_after_error()
                continue

            # MOVE within doing
            try:
                to_pos = 1 if rnd.random() < top_rate else rnd.randint(1, max_pos)
                move_work_item(
                    tenant_id=tenant_id,
                    item_id=wi.id,
                    to_status="doing",
                    to_position=to_pos,
                )
            except IntegrityError as e:
                tb = _format_exc_short() if verbose_errors else ""
                msg = f"move same-col IntegrityError item={wi.id}: {repr(e)}"
                if tb:
                    msg += f"\n{tb}"
                errs.append((worker_id, msg))
                _db_cleanup_after_error()
                continue
            except Exception as e:
                tb = _format_exc_short() if verbose_errors else ""
                msg = f"move same-col err item={wi.id}: {repr(e)}"
                if tb:
                    msg += f"\n{tb}"
                errs.append((worker_id, msg))
                _db_cleanup_after_error()
                continue

            # CROSS todo/doing
            if rnd.random() < cross_rate:
                try:
                    to_status = "todo" if rnd.random() < 0.5 else "doing"
                    to_pos2 = 1 if rnd.random() < top_rate else rnd.randint(1, max_pos)
                    move_work_item(
                        tenant_id=tenant_id,
                        item_id=wi.id,
                        to_status=to_status,
                        to_position=to_pos2,
                    )
                except IntegrityError as e:
                    tb = _format_exc_short() if verbose_errors else ""
                    msg = f"move cross-col IntegrityError item={wi.id}: {repr(e)}"
                    if tb:
                        msg += f"\n{tb}"
                    errs.append((worker_id, msg))
                    _db_cleanup_after_error()
                    continue
                except Exception as e:
                    tb = _format_exc_short() if verbose_errors else ""
                    msg = f"move cross-col err item={wi.id}: {repr(e)}"
                    if tb:
                        msg += f"\n{tb}"
                    errs.append((worker_id, msg))
                    _db_cleanup_after_error()
                    continue

            if sleep_ms > 0:
                time.sleep(sleep_ms / 1000.0)

    except Exception as e:
        tb = _format_exc_short() if verbose_errors else ""
        msg = f"worker exception: {repr(e)}"
        if tb:
            msg += f"\n{tb}"
        errs.append((worker_id, msg))
        _db_cleanup_after_error()
    finally:
        _reset_db_connection_for_thread()

    return (len(errs) == 0), errs


def _validate_rank(*, tenant_id: int, company_id: int):
    qs = WorkItem.objects_all.filter(tenant_id=tenant_id, company_id=company_id).only("id", "status", "rank")
    statuses = sorted(set(qs.values_list("status", flat=True)))

    for st in statuses:
        rows = list(qs.filter(status=st).order_by("rank", "id").values_list("rank", flat=True))
        if not rows:
            continue

        if any((r is None or str(r).strip() == "") for r in rows):
            return False, f"status={st}: empty rank found"

        if len(set(rows)) != len(rows):
            return False, f"status={st}: duplicate ranks found"

    return True, f"Rank invariant OK for tenant={tenant_id} company={company_id} (unique ranks per status)"