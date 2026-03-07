from __future__ import annotations

from django.db import migrations, models
from django.db.models import F


def normalize_positions(apps, schema_editor):
    WorkItem = apps.get_model("work", "WorkItem")

    # Fix NULL -> 1
    WorkItem.objects.filter(position__isnull=True).update(position=1)

    # Normalize per (tenant_id, company_id, status) by ordering (position, id)
    # Reassign 1..N to guarantee uniqueness deterministically
    qs = WorkItem.objects.all().order_by("tenant_id", "company_id", "status", "position", "id")

    current_key = None
    counter = 0
    buffer_ids = []

    def flush():
        nonlocal counter, buffer_ids
        if not buffer_ids:
            return
        # bulk update with deterministic positions
        # We update one-by-one to keep it simple & safe; dataset is manageable.
        pos = 1
        for _id in buffer_ids:
            WorkItem.objects.filter(id=_id).update(position=pos)
            pos += 1
        buffer_ids = []
        counter = 0

    for wi in qs.iterator(chunk_size=2000):
        key = (wi.tenant_id, wi.company_id, wi.status)
        if current_key != key:
            flush()
            current_key = key
            buffer_ids = []
        buffer_ids.append(wi.id)

    flush()


class Migration(migrations.Migration):

    dependencies = [
        ("work", "0005_workitem_workflow_version_and_more"),
    ]

    operations = [
        migrations.RunPython(normalize_positions, migrations.RunPython.noop),

        migrations.AlterField(
            model_name="workitem",
            name="position",
            field=models.PositiveIntegerField(default=1, db_index=True),
        ),

        migrations.AddConstraint(
            model_name="workitem",
            constraint=models.UniqueConstraint(
                fields=("tenant", "company", "status", "position"),
                name="uq_wi_tenant_company_status_pos",
            ),
        ),
    ]