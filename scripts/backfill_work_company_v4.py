# scripts/backfill_work_company_v4.py
from __future__ import annotations

from django.db import IntegrityError
from django.db.models import Count

from apps.work.models import WorkItem
from apps.projects.models import Project
from apps.shops.models import Shop

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

try:
    from apps.brands.models import Brand
except Exception:
    Brand = None


def _has_field(Model, field_name: str) -> bool:
    try:
        return any(f.name == field_name for f in Model._meta.get_fields())
    except Exception:
        return False


HAS_PROJECT_COMPANY_ID = _has_field(Project, "company_id")
HAS_SHOP_COMPANY_ID = _has_field(Shop, "company_id")
HAS_SHOP_BRAND_ID = _has_field(Shop, "brand_id")
HAS_BRAND_COMPANY_ID = (Brand is not None) and _has_field(Brand, "company_id")
HAS_BOOKING_SHOP_ID = (Booking is not None) and _has_field(Booking, "shop_id")


def _company_exists(cid: int, tenant_id: int | None = None) -> bool:
    if not cid or Company is None:
        return False
    qs = Company.objects_all.filter(id=cid)
    if tenant_id is not None and _has_field(Company, "tenant_id"):
        qs = qs.filter(tenant_id=int(tenant_id))
    return qs.exists()


def company_id_from_project(project_id: int):
    if not project_id or not HAS_PROJECT_COMPANY_ID:
        return None
    return (
        Project.objects_all.filter(id=project_id)
        .values_list("company_id", flat=True)
        .first()
    )


def company_id_from_brand(brand_id: int):
    if not brand_id or Brand is None or not HAS_BRAND_COMPANY_ID:
        return None
    return (
        Brand.objects_all.filter(id=brand_id)
        .values_list("company_id", flat=True)
        .first()
    )


def company_id_from_shop(shop_id: int):
    if not shop_id:
        return None

    # A) Shop has company_id
    if HAS_SHOP_COMPANY_ID:
        return (
            Shop.objects_all.filter(id=shop_id)
            .values_list("company_id", flat=True)
            .first()
        )

    # B) Shop has brand_id -> Brand.company_id
    if HAS_SHOP_BRAND_ID:
        bid = (
            Shop.objects_all.filter(id=shop_id)
            .values_list("brand_id", flat=True)
            .first()
        )
        if bid:
            return company_id_from_brand(int(bid))

    return None


def company_id_from_channel(channel_id: int):
    if not channel_id or ChannelShopLink is None:
        return None
    shop_id = (
        ChannelShopLink.objects_all.filter(channel_id=channel_id)
        .values_list("shop_id", flat=True)
        .first()
    )
    if not shop_id:
        return None
    return company_id_from_shop(int(shop_id))


def company_id_from_booking(booking_id: int):
    if not booking_id or Booking is None or not HAS_BOOKING_SHOP_ID:
        return None
    shop_id = (
        Booking.objects_all.filter(id=booking_id)
        .values_list("shop_id", flat=True)
        .first()
    )
    if not shop_id:
        return None
    return company_id_from_shop(int(shop_id))


def run(limit: int | None = None):
    qs = WorkItem.objects_all.filter(company_id__isnull=True).order_by("id")
    if limit:
        qs = qs[: int(limit)]

    need = qs.count()
    print("Need backfill company_id:", need)
    if not need:
        return

    print(
        "By target_type:",
        list(
            WorkItem.objects_all.filter(company_id__isnull=True)
            .values("target_type")
            .annotate(n=Count("id"))
            .order_by("-n")
        ),
    )

    updated = 0
    skipped_bad_fk = 0
    still_null = 0
    errors = 0
    unresolved = []

    for wi in qs.iterator(chunk_size=200):
        cid = None
        tenant_id = getattr(wi, "tenant_id", None)

        # 0) project_id -> project.company_id
        if wi.project_id:
            cid = company_id_from_project(int(wi.project_id))

        # 1) target direct
        if not cid and wi.target_type == "company" and wi.target_id:
            cid = int(wi.target_id)

        if not cid and wi.target_type == "project" and wi.target_id:
            cid = company_id_from_project(int(wi.target_id))

        if not cid and wi.target_type == "brand" and wi.target_id:
            cid = company_id_from_brand(int(wi.target_id))

        # 2) shop/channel/booking
        if not cid and wi.target_type == "shop" and wi.target_id:
            cid = company_id_from_shop(int(wi.target_id))

        if not cid and wi.target_type == "channel" and wi.target_id:
            cid = company_id_from_channel(int(wi.target_id))

        if not cid and wi.target_type == "booking" and wi.target_id:
            cid = company_id_from_booking(int(wi.target_id))

        if cid:
            # ✅ chặn FK fail: company phải tồn tại
            if not _company_exists(int(cid), tenant_id=tenant_id):
                skipped_bad_fk += 1
                if len(unresolved) < 30:
                    unresolved.append(
                        {
                            "id": wi.id,
                            "tenant_id": tenant_id,
                            "target_type": wi.target_type,
                            "target_id": wi.target_id,
                            "suggest_cid": int(cid),
                            "reason": "company_not_found",
                        }
                    )
                continue

            try:
                wi.company_id = int(cid)
                wi.save(update_fields=["company_id", "updated_at"])
                updated += 1
            except IntegrityError as e:
                errors += 1
                if len(unresolved) < 30:
                    unresolved.append(
                        {
                            "id": wi.id,
                            "tenant_id": tenant_id,
                            "target_type": wi.target_type,
                            "target_id": wi.target_id,
                            "suggest_cid": int(cid),
                            "reason": f"integrity_error: {str(e)[:120]}",
                        }
                    )
        else:
            still_null += 1
            if len(unresolved) < 30:
                unresolved.append(
                    {
                        "id": wi.id,
                        "tenant_id": tenant_id,
                        "target_type": wi.target_type,
                        "target_id": wi.target_id,
                        "reason": "no_mapping",
                    }
                )

    print("Updated:", updated)
    print("Skipped bad FK (company not found):", skipped_bad_fk)
    print("Still null (no mapping):", still_null)
    print("Integrity errors:", errors)
    if unresolved:
        print("Unresolved sample (first 30):", unresolved)

    print("After run still null:", WorkItem.objects_all.filter(company_id__isnull=True).count())


run()