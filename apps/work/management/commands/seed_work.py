# apps/work/management/commands/seed_work.py
from __future__ import annotations

import random
import string
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Dict, Optional, Tuple, Type

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone


def _mgr_all(model):
    """
    Prefer objects_all (TenantAllManager) if exists, else fallback objects.
    """
    return getattr(model, "objects_all", None) or model.objects


def _now():
    return timezone.now()


def _rand_code(n=4):
    return "".join(random.choice(string.ascii_uppercase + string.digits) for _ in range(n))


def _rand_name(prefix: str, n=4):
    return f"{prefix} {_rand_code(n)}"


def _safe_fields(model, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Allow both field.name (e.g. 'tenant') and field.attname (e.g. 'tenant_id').
    This is critical for FK *_id assignments.
    """
    allowed = set()
    for f in model._meta.concrete_fields:
        allowed.add(f.name)       # e.g. 'tenant'
        allowed.add(f.attname)    # e.g. 'tenant_id'

    out = {}
    for k, v in payload.items():
        if k in allowed:
            out[k] = v
    return out


def _create_safe(model, **payload):
    safe = _safe_fields(model, payload)
    return _mgr_all(model).create(**safe)


def _bulk_get_ids(qs, field="id"):
    return list(qs.values_list(field, flat=True))


@dataclass
class SeedInfo:
    companies: int = 0
    projects: int = 0
    brands: int = 0
    shops: int = 0
    channels: int = 0
    workitems: int = 0
    comments: int = 0


@transaction.atomic
def seed_work(
    *,
    tenant,
    items: int = 120,
    companies: int = 3,
    seed: int = 2026,
    comments_per_item: Tuple[int, int] = (0, 2),
) -> SeedInfo:
    random.seed(seed)

    # Imports inside func to avoid app loading issues
    from apps.companies.models import Company
    from apps.projects.models import Project
    from apps.brands.models import Brand
    from apps.shops.models import Shop
    from apps.channels.models import Channel, ChannelShopLink
    from apps.work.models import WorkItem, WorkComment

    # Booking is optional in your project
    try:
        from apps.booking.models import Booking
    except Exception:
        Booking = None

    info = SeedInfo()

    # -------------------------
    # 1) Companies
    # -------------------------
    company_objs = []
    for i in range(companies):
        # make name unique-ish
        name = f"Company {i+1} - {_rand_code(3)}"
        c = _create_safe(
            Company,
            tenant_id=tenant.id,
            name=name,
            code=f"C{i+1}-{_rand_code(4)}",
            is_active=True,
            created_at=_now(),
            updated_at=_now(),
        )
        company_objs.append(c)
    info.companies = len(company_objs)

    # -------------------------
    # 2) Projects (company required in your db)
    # -------------------------
    project_objs = []
    # 5 projects/company
    for c in company_objs:
        for _ in range(5):
            p = _create_safe(
                Project,
                tenant_id=tenant.id,
                company_id=c.id,
                name=_rand_name(f"Project - {c.id}", 4),
                code=f"P{c.id}-{_rand_code(4)}",
                status="active" if "status" in [f.name for f in Project._meta.concrete_fields] else None,
                created_at=_now(),
                updated_at=_now(),
            )
            project_objs.append(p)
    info.projects = len(project_objs)

    # -------------------------
    # 3) Brands (Brand.company NOT NULL + UNIQUE(tenant, company, name))
    # -------------------------
    brand_objs = []
    for c in company_objs:
        # 2 brands/company
        for bi in range(2):
            # ensure unique name within (tenant, company)
            name = f"Brand {c.id}-{bi+1} - {_rand_code(4)}"
            b = _create_safe(
                Brand,
                tenant_id=tenant.id,
                company_id=c.id,
                name=name,
                code=f"B{c.id}-{_rand_code(4)}",
                is_active=True,
                created_at=_now(),
                updated_at=_now(),
            )
            brand_objs.append(b)
    info.brands = len(brand_objs)

    # -------------------------
    # 4) Shops (Shop has tenant + brand, no company field in your schema)
    # -------------------------
    shop_objs = []
    # 2-3 shops/brand
    for b in brand_objs:
        k = random.randint(2, 3)
        for si in range(k):
            s = _create_safe(
                Shop,
                tenant_id=tenant.id,
                brand_id=b.id,
                name=_rand_name(f"Shop - {b.id}", 4),
                code=f"S{b.id}-{_rand_code(4)}",
                platform=random.choice(["tiktok", "shopee", "lazada", "other"]),
                description="seed work",
                status="active" if "status" in [f.name for f in Shop._meta.concrete_fields] else None,
                is_active=True if "is_active" in [f.name for f in Shop._meta.concrete_fields] else None,
                created_at=_now(),
                updated_at=_now(),
            )
            shop_objs.append(s)
    info.shops = len(shop_objs)

    # -------------------------
    # 5) Channels (Channel has company)
    # -------------------------
    channel_objs = []
    # 3 channels/company
    for c in company_objs:
        for _ in range(3):
            ch = _create_safe(
                Channel,
                tenant_id=tenant.id,
                company_id=c.id,
                type=random.choice(["tiktok", "facebook", "google", "other"]),
                name=_rand_name(f"Channel - {c.id}", 4),
                is_active=True,
                created_at=_now(),
                updated_at=_now(),
            )
            channel_objs.append(ch)
    info.channels = len(channel_objs)

    # -------------------------
    # 6) ChannelShopLink (map channel -> some shops in same company)
    #   Shop -> Brand -> Company
    # -------------------------
    # helper map: shop_id -> company_id
    brand_company = {b.id: b.company_id for b in brand_objs}
    shop_company = {s.id: brand_company.get(s.brand_id) for s in shop_objs}

    # link each channel to 2-4 shops in its company
    for ch in channel_objs:
        same_company_shops = [sid for sid, cid in shop_company.items() if cid == ch.company_id]
        random.shuffle(same_company_shops)
        for sid in same_company_shops[: random.randint(2, 4)]:
            _create_safe(
                ChannelShopLink,
                tenant_id=tenant.id,
                channel_id=ch.id,
                shop_id=sid,
                created_at=_now(),
            )

    # -------------------------
    # 7) Booking (optional)
    # Booking fields: tenant, company, shop ...
    # -------------------------
    booking_objs = []
    if Booking is not None:
        # create 0-10 bookings total
        for _ in range(random.randint(0, 10)):
            shop = random.choice(shop_objs)
            cid = shop_company.get(shop.id)
            if not cid:
                continue
            bk = _create_safe(
                Booking,
                tenant_id=tenant.id,
                company_id=cid,
                shop_id=shop.id,
                code=f"BK-{_rand_code(6)}",
                title=_rand_name("Booking", 4),
                status=random.choice(["new", "confirmed", "done", "cancelled"]),
                amount=random.randint(100000, 5000000),
                scheduled_at=_now() + timedelta(days=random.randint(-7, 14)),
                note="seed work",
                created_at=_now(),
                updated_at=_now(),
            )
            booking_objs.append(bk)

    # -------------------------
    # 8) WorkItems
    # Ensure company_id is always set (no null)
    # Targets:
    # - project, brand, shop, channel, booking, company
    # -------------------------
    statuses = ["todo", "doing", "blocked", "done", "cancelled"]
    priorities = [1, 2, 3, 4]
    target_types = ["project", "brand", "shop", "channel", "company"]
    if booking_objs:
        target_types.append("booking")

    # pool by company
    projects_by_company = {}
    for p in project_objs:
        projects_by_company.setdefault(p.company_id, []).append(p)

    brands_by_company = {}
    for b in brand_objs:
        brands_by_company.setdefault(b.company_id, []).append(b)

    shops_by_company = {}
    for s in shop_objs:
        cid = shop_company.get(s.id)
        if cid:
            shops_by_company.setdefault(cid, []).append(s)

    channels_by_company = {}
    for ch in channel_objs:
        channels_by_company.setdefault(ch.company_id, []).append(ch)

    bookings_by_company = {}
    for bk in booking_objs:
        bookings_by_company.setdefault(bk.company_id, []).append(bk)

    # optional user assignment
    try:
        from django.contrib.auth import get_user_model

        User = get_user_model()
        users = list(User.objects.all()[:20])
    except Exception:
        users = []

    created_items = []
    for i in range(items):
        c = random.choice(company_objs)
        cid = c.id

        tt = random.choice(target_types)
        tid = None
        project_id = None

        if tt == "project":
            ps = projects_by_company.get(cid) or []
            if ps:
                p = random.choice(ps)
                tid = p.id
                project_id = p.id

        elif tt == "brand":
            bs = brands_by_company.get(cid) or []
            if bs:
                b = random.choice(bs)
                tid = b.id

        elif tt == "shop":
            ss = shops_by_company.get(cid) or []
            if ss:
                s = random.choice(ss)
                tid = s.id

        elif tt == "channel":
            cs = channels_by_company.get(cid) or []
            if cs:
                ch = random.choice(cs)
                tid = ch.id

        elif tt == "booking":
            bks = bookings_by_company.get(cid) or []
            if bks:
                bk = random.choice(bks)
                tid = bk.id

        elif tt == "company":
            tid = cid

        # fallback if tid missing (due to empty pools): force company target
        if tid is None:
            tt = "company"
            tid = cid

        st = random.choice(statuses)
        due = _now() + timedelta(days=random.randint(-3, 21))

        assignee_id = random.choice(users).id if users and random.random() < 0.7 else None
        requester_id = random.choice(users).id if users and random.random() < 0.3 else None

        wi = _create_safe(
            WorkItem,
            tenant_id=tenant.id,
            company_id=cid,
            project_id=project_id,
            title=f"Task {i+1} - {_rand_code(4)}",
            description="seed work",
            status=st,
            priority=random.choice(priorities),
            due_at=due,
            assignee_id=assignee_id,
            requester_id=requester_id,
            target_type=tt,
            target_id=tid,
            created_by_id=random.choice(users).id if users and random.random() < 0.8 else None,
            created_at=_now() - timedelta(days=random.randint(0, 30)),
            updated_at=_now(),
        )
        created_items.append(wi)

    info.workitems = len(created_items)

    # -------------------------
    # 9) Comments
    # -------------------------
    comment_count = 0
    for wi in created_items:
        k = random.randint(comments_per_item[0], comments_per_item[1])
        for _ in range(k):
            actor_id = random.choice(users).id if users else None
            _create_safe(
                WorkComment,
                tenant_id=tenant.id,
                work_item_id=wi.id,
                actor_id=actor_id,
                body=f"Update {_rand_code(6)}",
                meta={"event": "comment", "seed": True},
                created_at=_now() - timedelta(days=random.randint(0, 15)),
            )
            comment_count += 1

    info.comments = comment_count
    return info


class Command(BaseCommand):
    help = "Seed demo data for Work (companies/projects/brands/shops/channels/workitems/comments)."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", type=int, default=None)
        parser.add_argument("--items", type=int, default=120)
        parser.add_argument("--companies", type=int, default=3)
        parser.add_argument("--seed", type=int, default=2026)
        parser.add_argument("--min-comments", type=int, default=0)
        parser.add_argument("--max-comments", type=int, default=2)

    @transaction.atomic
    def handle(self, *args, **options):
        from apps.tenants.models import Tenant

        tenant_id = options.get("tenant")
        if tenant_id:
            tenant = _mgr_all(Tenant).filter(id=int(tenant_id)).first()
        else:
            tenant = _mgr_all(Tenant).order_by("id").first()

        if not tenant:
            self.stderr.write(self.style.ERROR("No tenant found. Create a Tenant first."))
            return

        self.stdout.write(f"Using tenant: {tenant.id}")

        items = int(options["items"])
        companies = int(options["companies"])
        seed = int(options["seed"])
        min_c = int(options["min_comments"])
        max_c = int(options["max_comments"])
        if max_c < min_c:
            max_c = min_c

        info = seed_work(
            tenant=tenant,
            items=items,
            companies=companies,
            seed=seed,
            comments_per_item=(min_c, max_c),
        )

        self.stdout.write(self.style.SUCCESS("==== SEED DONE ===="))
        self.stdout.write(f"Companies: {info.companies}")
        self.stdout.write(f"Projects: {info.projects}")
        self.stdout.write(f"Brands: {info.brands}")
        self.stdout.write(f"Shops: {info.shops}")
        self.stdout.write(f"Channels: {info.channels}")
        self.stdout.write(f"WorkItems created: {info.workitems}")
        self.stdout.write(f"Comments created: {info.comments}")