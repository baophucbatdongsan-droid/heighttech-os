from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q

from apps.work.models import WorkItem

INT32_MAX = 2_147_483_647
TEMP_BAND_GAP = 50_000  # giống services_move.py (chừa band cao an toàn)


class Command(BaseCommand):
    help = (
        "Normalize WorkItem.position to be 1..n per (tenant, company, status). "
        "Fix legacy duplicates safely under UNIQUE(tenant,company,status,position)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--tenant-id", type=int, required=True)
        parser.add_argument("--company-id", type=int, required=True)
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument(
            "--repair-extremes",
            action="store_true",
            help="(Optional) Also repair extreme positions (still done safely).",
        )
        parser.add_argument("--batch-size", type=int, default=500)

    @transaction.atomic
    def handle(self, *args, **opts):
        tenant_id = int(opts["tenant_id"])
        company_id = int(opts["company_id"])
        dry = bool(opts["dry_run"])
        repair_extremes = bool(opts["repair_extremes"])
        batch_size = int(opts["batch_size"] or 500)

        qs = (
            WorkItem.objects_all.select_for_update()
            .filter(tenant_id=tenant_id, company_id=company_id)
            .only("id", "tenant_id", "company_id", "status", "position")
        )

        statuses = sorted(set(qs.values_list("status", flat=True)))

        # threshold để coi là "extreme" (ví dụ: do temp band cũ, hoặc bug đẩy quá cao)
        # Bạn có thể chỉnh lại nếu muốn.
        extreme_threshold = 1_000_000_000

        total_rows = 0
        repaired = 0

        for st in statuses:
            col_qs = qs.filter(status=st).order_by("position", "id")
            ids = list(col_qs.values_list("id", flat=True))
            n = len(ids)
            if n == 0:
                continue

            total_rows += n

            # (Optional) repair extremes nhưng phải làm an toàn -> KHÔNG bao giờ set về 1 trực tiếp
            if repair_extremes:
                extreme_ids = list(
                    col_qs.filter(
                        Q(position__lt=1) | Q(position__gte=extreme_threshold)
                    ).values_list("id", flat=True)
                )
                repaired += len(extreme_ids)

            if dry:
                continue

            # ===== Phase 1: đưa toàn bộ items trong column vào temp band (unique, positive, int4) =====
            # temp_pos giảm dần theo index để chắc chắn unique trong column
            # temp_pos tối đa: INT32_MAX - TEMP_BAND_GAP - 1
            # temp_pos tối thiểu vẫn > 0 nếu n << 2e9 (đương nhiên)
            tmp_objs = []
            base = INT32_MAX - TEMP_BAND_GAP
            for i, wid in enumerate(ids, start=1):
                tmp_objs.append(WorkItem(id=wid, position=base - i))

            WorkItem.objects_all.bulk_update(tmp_objs, ["position"], batch_size=batch_size)

            # ===== Phase 2: gán lại 1..n theo order position,id ban đầu =====
            norm_objs = []
            for i, wid in enumerate(ids, start=1):
                norm_objs.append(WorkItem(id=wid, position=i))

            WorkItem.objects_all.bulk_update(norm_objs, ["position"], batch_size=batch_size)

        if dry:
            self.stdout.write(self.style.WARNING("[DRY-RUN] no changes applied"))

        msg = f"Normalized positions tenant={tenant_id} company={company_id} rows={total_rows}"
        if repair_extremes:
            msg += f" repaired_extremes={repaired}"
        self.stdout.write(self.style.SUCCESS(msg))