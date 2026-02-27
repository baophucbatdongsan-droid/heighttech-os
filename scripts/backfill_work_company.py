from django.db import transaction
from apps.work.models import WorkItem
from apps.projects.models import Project
from apps.shops.models import Shop

try:
    from apps.channels.models import ChannelShopLink
except Exception:
    ChannelShopLink = None

try:
    from apps.booking.models import Booking
except Exception:
    Booking = None


@transaction.atomic
def run(limit=None):
    qs = WorkItem.objects_all.filter(company_id__isnull=True).order_by("id")
    if limit:
        qs = qs[:int(limit)]

    need = qs.count()
    print("Need backfill company_id:", need)
    if not need:
        return

    updated = 0
    still_null = 0

    for wi in qs.iterator(chunk_size=200):
        cid = None

        # 1) project -> company
        if wi.project_id:
            cid = (
                Project.objects_all.filter(id=wi.project_id)
                .values_list("company_id", flat=True)
                .first()
            )

        # 2) target shop -> company
        if (not cid) and wi.target_type == "shop" and wi.target_id:
            cid = (
                Shop.objects_all.filter(id=wi.target_id)
                .values_list("company_id", flat=True)
                .first()
            )

        # 3) target channel -> shop -> company
        if (not cid) and wi.target_type == "channel" and wi.target_id and ChannelShopLink is not None:
            shop_id = (
                ChannelShopLink.objects_all.filter(channel_id=wi.target_id)
                .values_list("shop_id", flat=True)
                .first()
            )
            if shop_id:
                cid = (
                    Shop.objects_all.filter(id=shop_id)
                    .values_list("company_id", flat=True)
                    .first()
                )

        # 4) target booking -> shop -> company
        if (not cid) and wi.target_type == "booking" and wi.target_id and Booking is not None:
            shop_id = (
                Booking.objects_all.filter(id=wi.target_id)
                .values_list("shop_id", flat=True)
                .first()
            )
            if shop_id:
                cid = (
                    Shop.objects_all.filter(id=shop_id)
                    .values_list("company_id", flat=True)
                    .first()
                )

        if cid:
            wi.company_id = int(cid)
            wi.save(update_fields=["company_id", "updated_at"])
            updated += 1
        else:
            still_null += 1

    print("Updated:", updated)
    print("Still null after:", still_null)


run()
print("still null:", WorkItem.objects_all.filter(company_id__isnull=True).count())