# apps/work/migrations/0009_work_rank.py
from __future__ import annotations

from django.db import migrations, models
import django.db.models.constraints

ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
BASE = len(ALPHABET)

def _base62(n: int) -> str:
    if n <= 0:
        return "0"
    s = []
    while n > 0:
        n, r = divmod(n, BASE)
        s.append(ALPHABET[r])
    return "".join(reversed(s))

def backfill_rank(apps, schema_editor):
    WorkItem = apps.get_model("work", "WorkItem")
    db = schema_editor.connection.alias

    # backfill per (tenant,company,status) ordered by (position,id)
    rows = (
        WorkItem.objects.using(db)
        .all()
        .values_list("id", "tenant_id", "company_id", "status", "position")
        .order_by("tenant_id", "company_id", "status", "position", "id")
    )

    last_key = None
    idx = 0
    batch = []
    for (wid, tid, cid, st, pos) in rows.iterator(chunk_size=2000):
        key = (tid, cid, st)
        if key != last_key:
            last_key = key
            idx = 0
        idx += 1
        rank = _base62(idx).rjust(10, "0")
        batch.append((wid, rank))
        if len(batch) >= 2000:
            for _id, _rank in batch:
                WorkItem.objects.using(db).filter(id=_id).update(rank=_rank)
            batch = []
    for _id, _rank in batch:
        WorkItem.objects.using(db).filter(id=_id).update(rank=_rank)

class Migration(migrations.Migration):
    dependencies = [
        ("work", "0008_remove_workitem_uq_wi_tenant_company_status_pos_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="workitem",
            name="rank",
            field=models.CharField(max_length=32, default="m", db_index=True),
        ),
        migrations.RunPython(backfill_rank, migrations.RunPython.noop),

        # remove old unique position constraint
        migrations.RemoveConstraint(
            model_name="workitem",
            name="uq_wi_tenant_company_status_pos",
        ),

        # add unique rank constraint (DEFERRABLE helps concurrency)
        migrations.AddConstraint(
            model_name="workitem",
            constraint=models.UniqueConstraint(
                deferrable=django.db.models.constraints.Deferrable.DEFERRED,
                fields=("tenant", "company", "status", "rank"),
                name="uq_wi_tenant_company_status_rank",
            ),
        ),
    ]