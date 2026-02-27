from django.db import transaction
from django.utils import timezone

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

try:
    from apps.brands.models import Brand
except Exception:
    Brand = None


def _brand_company_map(brand_ids):
    """
    Trả dict {brand_id: company_id} theo schema thực tế của Brand.
    Ưu tiên:
      - Brand.company_id
      - Brand.company (FK)
      - Brand.shop_id -> Shop.company_id
    """
    if not Brand or not brand_ids:
        return {}

    field_names = {f.name for f in Brand._meta.fields}

    # Case 1: Brand.company_id hoặc FK company
    if "company" in field_names or "company_id" in field_names:
        rows = Brand.objects_all.filter(id__in=list(brand_ids)).values_list("id", "company_id")
        return {bid: cid for bid, cid in rows if cid}

    # Case 2: Brand.shop_id -> Shop.company_id
    if "shop" in field_names or "shop_id" in field_names:
        rows = Brand.objects_all.filter(id__in=list(brand_ids)).values_list("id", "shop_id")
        brand_to_shop = {bid: sid for bid, sid in rows if sid}
        shop_ids = set(brand_to_shop.values())
        shop_to_company = dict(
            Shop.objects_all.filter(id__in=list(shop_ids)).values_list("id", "company_id")
        )
        out = {}
        for bid, sid in brand_to_shop.items():
            cid = shop_to_company.get(sid)
            if cid:
                out[bid] = cid
        return out

    return {}


@transaction.atomic
def run(limit=None):
    qs = WorkItem.objects_all.filter(company_id__isnull=True).order_by("id")
    if limit:
        qs = qs[:int(limit)]

    need = qs.count()
    print("Need backfill company_id:", need)
    if not need:
        return

    # gom ids theo target_type
    shop_ids = set()
    channel_ids = set()
    booking_ids = set()
    project_ids = set()
    brand_ids = set()
    company_target_ids = set()

    items = list(qs.values("id", "project_id", "target_type", "target_id"))
    for it in items:
        tt = (it["target_type"] or "").strip()
        tid = it["target_id"]
        if tt == "shop" and tid:
            shop_ids.add(tid)
        elif tt == "channel" and tid:
            channel_ids.add(tid)
        elif tt == "booking" and tid:
            booking_ids.add(tid)
        elif tt == "project" and tid:
            project_ids.add(tid)
        elif tt == "brand" and tid:
            brand_ids.add(tid)
        elif tt == "company" and tid:
            company_target_ids.add(tid)

    # maps
    shop_to_company = dict(
        Shop.objects_all.filter(id__in=list(shop_ids)).values_list("id", "company_id")
    )

    project_to_company = dict(
        Project.objects_all.filter(id__in=list(project_ids)).values_list("id", "company_id")
    )

    channel_to_company = {}
    if ChannelShopLink and channel_ids:
        channel_to_shop = dict(
            ChannelShopLink.objects_all.filter(channel_id__in=list(channel_ids)).values_list("channel_id", "shop_id")
        )
        # lấy thêm company từ shop
        missing_shop_ids = set(channel_to_shop.values()) - set(shop_to_company.keys())
        if missing_shop_ids:
            shop_to_company.update(
                dict(Shop.objects_all.filter(id__in=list(missing_shop_ids)).values_list("id", "company_id"))
            )
        for ch_id, sh_id in channel_to_shop.items():
            cid = shop_to_company.get(sh_id)
            if cid:
                channel_to_company[ch_id] = cid

    booking_to_company = {}
    if Booking and booking_ids:
        booking_to_shop = dict(
            Booking.objects_all.filter(id__in=list(booking_ids)).values_list("id", "shop_id")
        )
        missing_shop_ids = set(booking_to_shop.values()) - set(shop_to_company.keys())
        if missing_shop_ids:
            shop_to_company.update(
                dict(Shop.objects_all.filter(id__in=list(missing_shop_ids)).values_list("id", "company_id"))
            )
        for bk_id, sh_id in booking_to_shop.items():
            cid = shop_to_company.get(sh_id)
            if cid:
                booking_to_company[bk_id] = cid

    brand_to_company = _brand_company_map(brand_ids)

    updated = 0
    still_null = 0
    by_type = {"shop": 0, "channel": 0, "booking": 0, "company": 0, "project": 0, "brand": 0}

    # update từng item (để chắc chắn + dễ debug)
    for it in items:
        wi_id = it["id"]
        cid = None

        # ưu tiên: project_id (FK) nếu có
        if it["project_id"]:
            cid = Project.objects_all.filter(id=it["project_id"]).values_list("company_id", flat=True).first()

        tt = (it["target_type"] or "").strip()
        tid = it["target_id"]

        if not cid and tt == "company" and tid:
            cid = int(tid)

        if not cid and tt == "project" and tid:
            cid = project_to_company.get(int(tid))

        if not cid and tt == "shop" and tid:
            cid = shop_to_company.get(int(tid))

        if not cid and tt == "channel" and tid:
            cid = channel_to_company.get(int(tid))

        if not cid and tt == "booking" and tid:
            cid = booking_to_company.get(int(tid))

        if not cid and tt == "brand" and tid:
            cid = brand_to_company.get(int(tid))

        if cid:
            WorkItem.objects_all.filter(id=wi_id).update(company_id=int(cid), updated_at=timezone.now())
            updated += 1
            if tt in by_type:
                by_type[tt] += 1
        else:
            still_null += 1

    print("Updated:", updated)
    print("By type:", by_type)
    print("Still null after:", still_null)

    # show sample unresolved
    if still_null:
        unresolved = list(
            WorkItem.objects_all.filter(company_id__isnull=True)
            .values("id", "project_id", "target_type", "target_id")[:20]
        )
        print("Unresolved sample (first 20):", unresolved)


run()
print("still null:", WorkItem.objects_all.filter(company_id__isnull=True).count())