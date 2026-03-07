# apps/work/management/commands/upgrade_workflow_version.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, List

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q

from apps.work.models import WorkItem


@dataclass
class UpgradeResult:
    matched: int = 0
    updated: int = 0
    skipped: int = 0


def _to_int(x, default: Optional[int] = None) -> Optional[int]:
    if x is None:
        return default
    try:
        return int(x)
    except Exception:
        return default


def _resolve_target_version(wi: WorkItem) -> int:
    """
    Default resolver:
    - prefer wi.project.shop.rule_version if available
    - else 1
    """
    try:
        p = getattr(wi, "project", None)
        if not p:
            return 1
        shop = getattr(p, "shop", None)
        if not shop:
            return 1
        v = getattr(shop, "rule_version", None)
        return int(v or 1)
    except Exception:
        return 1


class Command(BaseCommand):
    help = "Upgrade WorkItem.workflow_version in a controlled way (dry-run/apply, scoped filters, batched)."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", type=int, required=True, help="Tenant ID (required)")
        parser.add_argument("--company", type=int, default=None, help="Company ID (optional)")
        parser.add_argument("--project", type=int, default=None, help="Project ID (optional)")
        parser.add_argument(
            "--status",
            default=None,
            help="Comma separated statuses to include (optional). Example: todo,doing,blocked",
        )

        # strategy
        parser.add_argument(
            "--to-version",
            type=int,
            default=None,
            help="Force set workflow_version to this value (overrides resolver).",
        )
        parser.add_argument(
            "--only-if",
            default="lt",
            choices=["lt", "ne", "any"],
            help="Update condition: lt (only if current < target), ne (current != target), any (always set). Default=lt",
        )

        # execution
        parser.add_argument("--apply", action="store_true", help="Actually apply changes. Default is dry-run.")
        parser.add_argument("--batch", type=int, default=500, help="Batch size. Default=500")
        parser.add_argument("--limit", type=int, default=None, help="Limit number of items processed (optional)")

    def handle(self, *args, **opts):
        tenant_id = _to_int(opts.get("tenant"))
        if not tenant_id:
            raise CommandError("--tenant is required")

        company_id = _to_int(opts.get("company"))
        project_id = _to_int(opts.get("project"))
        to_version = _to_int(opts.get("to_version"))
        only_if: str = str(opts.get("only_if") or "lt")
        apply: bool = bool(opts.get("apply"))
        batch: int = max(50, _to_int(opts.get("batch"), 500) or 500)
        limit: Optional[int] = _to_int(opts.get("limit"))

        statuses_csv = (opts.get("status") or "").strip()
        statuses: List[str] = []
        if statuses_csv:
            statuses = [s.strip().lower() for s in statuses_csv.split(",") if s.strip()]

        qs = WorkItem.objects_all.select_related("project").filter(tenant_id=tenant_id)

        if company_id:
            qs = qs.filter(company_id=company_id)
        if project_id:
            qs = qs.filter(project_id=project_id)
        if statuses:
            qs = qs.filter(status__in=statuses)

        # NOTE: we typically don't upgrade done/cancelled unless explicit
        if not statuses_csv:
            qs = qs.exclude(status__in=[WorkItem.Status.DONE, WorkItem.Status.CANCELLED])

        qs = qs.order_by("id")

        if limit:
            qs = qs[:limit]

        total = qs.count()
        self.stdout.write(self.style.MIGRATE_HEADING("=== WORKFLOW VERSION UPGRADE ==="))
        self.stdout.write(
            f"tenant={tenant_id} company={company_id} project={project_id} "
            f"statuses={statuses or '[default exclude done/cancelled]'} "
            f"to_version={to_version or '[resolver]'} only_if={only_if} "
            f"batch={batch} apply={apply} limit={limit or 'none'}"
        )
        self.stdout.write(f"matched={total}")

        res = UpgradeResult(matched=total)

        if total == 0:
            self.stdout.write(self.style.WARNING("No workitems matched."))
            return

        # Iterate in batches without loading everything
        start = 0
        while start < total:
            chunk = list(qs[start : start + batch])
            if not chunk:
                break

            with transaction.atomic():
                for wi in chunk:
                    target = int(to_version or _resolve_target_version(wi) or 1)
                    cur = int(getattr(wi, "workflow_version", 1) or 1)

                    should = False
                    if only_if == "lt":
                        should = cur < target
                    elif only_if == "ne":
                        should = cur != target
                    else:  # any
                        should = True

                    if not should:
                        res.skipped += 1
                        continue

                    if apply:
                        wi.workflow_version = target
                        wi.save(update_fields=["workflow_version"])
                    res.updated += 1

            start += batch
            self.stdout.write(f"progress: {min(start, total)}/{total} updated={res.updated} skipped={res.skipped}")

        if apply:
            self.stdout.write(self.style.SUCCESS(f"DONE ✅ updated={res.updated} skipped={res.skipped} matched={res.matched}"))
        else:
            self.stdout.write(self.style.WARNING(f"DRY-RUN ✅ would_update={res.updated} would_skip={res.skipped} matched={res.matched}"))
            self.stdout.write("Tip: rerun with --apply to commit.")