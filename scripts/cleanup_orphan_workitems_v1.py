# scripts/cleanup_orphan_workitems_v1.py
from django.db import transaction
from django.db.models import Count

from apps.work.models import WorkItem

# Optional imports
try:
    from apps.shops.models import Shop
except Exception:
    Shop = None

try:
    from apps.brands.models import Brand
except Exception:
    Brand = None

try:
    from apps.projects.models import Project
except Exception:
    Project = None

try:
    from apps.companies.models import Company
except Exception:
    Company = None

try:
    from apps.channels.models import ChannelShopLink
except Exception:
    ChannelShopLink = None

try:
    from apps.booking.models import Booking
except Exception:
    Booking = None


DRY_RUN = False  # <-- đổi False để xoá thật


def _exists_ids(Model, ids):
    if Model is None or not ids:
        return set()
    return set(Model.objects_all.filter(id__in=list(ids)).values_list("id", flat=True))


def main():
    qs0 = WorkItem.objects_all.filter(company_id__isnull=True)

    print("==== ORPHAN WORKITEM CLEANUP v1 ====")
    print("company_id IS NULL:", qs0.count())
    print("By target_type:", list(qs0.values("target_type").annotate(n=Count("id")).order_by("-n")))

    to_delete_ids = set()

    # ---- booking: nếu Booking table rỗng thì tất cả booking target chắc chắn orphan
    booking_ids = set(qs0.filter(target_type="booking").values_list("id", flat=True))
    if booking_ids:
        if Booking is None:
            print("[booking] Booking model not available -> mark all booking items orphan:", len(booking_ids))
            to_delete_ids |= booking_ids
        else:
            b_tids = set(qs0.filter(target_type="booking").values_list("target_id", flat=True))
            b_tids.discard(None)
            exist = _exists_ids(Booking, b_tids)
            # nếu booking tồn tại thì ok, không tồn tại -> orphan
            for wi_id, tid in qs0.filter(target_type="booking").values_list("id", "target_id"):
                if tid is None or tid not in exist:
                    to_delete_ids.add(wi_id)
            print("[booking] target_ids:", len(b_tids), "exist:", len(exist), "orphan items:", len(to_delete_ids & booking_ids))

    # ---- shop
    shop_qs = qs0.filter(target_type="shop")
    if shop_qs.exists():
        s_tids = set(shop_qs.values_list("target_id", flat=True))
        s_tids.discard(None)
        exist = _exists_ids(Shop, s_tids)
        orphan = set(shop_qs.exclude(target_id__in=list(exist)).values_list("id", flat=True)) if exist else set(shop_qs.values_list("id", flat=True))
        to_delete_ids |= orphan
        print("[shop] target_ids:", len(s_tids), "exist:", len(exist), "orphan items:", len(orphan))

    # ---- brand
    brand_qs = qs0.filter(target_type="brand")
    if brand_qs.exists():
        b_tids = set(brand_qs.values_list("target_id", flat=True))
        b_tids.discard(None)
        exist = _exists_ids(Brand, b_tids)
        orphan = set(brand_qs.exclude(target_id__in=list(exist)).values_list("id", flat=True)) if exist else set(brand_qs.values_list("id", flat=True))
        to_delete_ids |= orphan
        print("[brand] target_ids:", len(b_tids), "exist:", len(exist), "orphan items:", len(orphan))

    # ---- project (target_type=project)
    proj_qs = qs0.filter(target_type="project")
    if proj_qs.exists():
        p_tids = set(proj_qs.values_list("target_id", flat=True))
        p_tids.discard(None)
        exist = _exists_ids(Project, p_tids)
        orphan = set(proj_qs.exclude(target_id__in=list(exist)).values_list("id", flat=True)) if exist else set(proj_qs.values_list("id", flat=True))
        to_delete_ids |= orphan
        print("[project] target_ids:", len(p_tids), "exist:", len(exist), "orphan items:", len(orphan))

    # ---- company (target_type=company)
    comp_qs = qs0.filter(target_type="company")
    if comp_qs.exists():
        c_tids = set(comp_qs.values_list("target_id", flat=True))
        c_tids.discard(None)
        exist = _exists_ids(Company, c_tids)
        orphan = set(comp_qs.exclude(target_id__in=list(exist)).values_list("id", flat=True)) if exist else set(comp_qs.values_list("id", flat=True))
        to_delete_ids |= orphan
        print("[company] target_ids:", len(c_tids), "exist:", len(exist), "orphan items:", len(orphan))

    # ---- channel: orphan nếu channel không có link ra shop
    chan_qs = qs0.filter(target_type="channel")
    if chan_qs.exists():
        ch_tids = set(chan_qs.values_list("target_id", flat=True))
        ch_tids.discard(None)
        if ChannelShopLink is None:
            orphan = set(chan_qs.values_list("id", flat=True))
            to_delete_ids |= orphan
            print("[channel] ChannelShopLink not available -> orphan items:", len(orphan))
        else:
            linked = set(ChannelShopLink.objects_all.filter(channel_id__in=list(ch_tids)).values_list("channel_id", flat=True).distinct())
            orphan = set(chan_qs.exclude(target_id__in=list(linked)).values_list("id", flat=True)) if linked else set(chan_qs.values_list("id", flat=True))
            to_delete_ids |= orphan
            print("[channel] target_ids:", len(ch_tids), "linked:", len(linked), "orphan items:", len(orphan))

    # ---- fallback: các target_type khác / trống mà company_id null
    other_qs = qs0.exclude(target_type__in=["booking", "shop", "brand", "project", "company", "channel"])
    if other_qs.exists():
        other_ids = set(other_qs.values_list("id", flat=True))
        to_delete_ids |= other_ids
        print("[other] types:", list(other_qs.values("target_type").annotate(n=Count("id")).order_by("-n")))
        print("[other] orphan items:", len(other_ids))

    to_delete_ids = sorted(to_delete_ids)
    print("----")
    print("Total orphan WorkItems to delete:", len(to_delete_ids))
    print("Sample ids:", to_delete_ids[:30])

    if DRY_RUN:
        print("DRY_RUN=True => chưa xoá gì.")
        return

    with transaction.atomic():
        deleted, _ = WorkItem.objects_all.filter(id__in=to_delete_ids).delete()
        print("DELETED:", deleted)

    print("After cleanup, still company_id IS NULL:", WorkItem.objects_all.filter(company_id__isnull=True).count())


main()