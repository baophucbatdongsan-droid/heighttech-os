# apps/core/management/commands/seed_demo.py
from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from django.db import transaction, connection, IntegrityError
from django.utils import timezone
from django.db import IntegrityError, transaction

def _has_field(model, name: str) -> bool:
    try:
        return any(f.name == name for f in model._meta.get_fields())
    except Exception:
        return False


def _set_if_field(model, defaults: dict, field: str, value):
    if _has_field(model, field):
        defaults[field] = value


def _shift_month(d: date, back: int) -> date:
    y = d.year
    m = d.month - back
    while m <= 0:
        m += 12
        y -= 1
    return date(y, m, 1)


def _db_columns(table_name: str, table_schema: str = "public") -> dict[str, dict]:
    sql = """
        SELECT
            column_name,
            data_type,
            udt_name,
            is_nullable,
            column_default,
            numeric_scale,
            character_maximum_length
        FROM information_schema.columns
        WHERE table_name = %s
          AND table_schema = %s
        ORDER BY ordinal_position
    """
    out: dict[str, dict] = {}
    with connection.cursor() as cur:
        cur.execute(sql, [table_name, table_schema])
        for (
            column_name,
            data_type,
            udt_name,
            is_nullable,
            column_default,
            numeric_scale,
            char_len,
        ) in cur.fetchall():
            out[str(column_name)] = {
                "data_type": data_type,
                "udt_name": udt_name,
                "is_nullable": is_nullable,
                "column_default": column_default,
                "numeric_scale": numeric_scale,
                "character_maximum_length": char_len,
            }
    return out


def _fallback_value_for_db_column(col: str, info: dict) -> object | None:
    if col == "service_percent":
        return Decimal("0.15")

    dt = (info.get("data_type") or "").lower()
    udt = (info.get("udt_name") or "").lower()

    if dt in {"numeric", "decimal"}:
        return Decimal("0")
    if dt in {"integer", "bigint", "smallint"} or udt in {"int2", "int4", "int8"}:
        return 0
    if dt in {"double precision", "real"} or udt in {"float4", "float8"}:
        return 0.0
    if dt == "boolean":
        return False
    if dt in {"character varying", "character", "text"}:
        return ""
    if dt == "date":
        return timezone.now().date().replace(day=1)
    if dt in {"timestamp without time zone", "timestamp with time zone"}:
        return timezone.now()

    return None




def _safe_get_or_create_unique(model, lookup: dict, defaults: dict):
    """
    Safe get_or_create for models with UNIQUE constraints but custom managers/scopes.
    Always use _base_manager to bypass filters (soft-delete / tenant-scope).
    On IntegrityError: fetch again by lookup via _base_manager, then update defaults.
    """
    base = getattr(model, "_base_manager", model.objects)

    # normalize common fields (optional but helpful)
    if "name" in lookup and isinstance(lookup["name"], str):
        lookup["name"] = lookup["name"].strip()

    try:
        with transaction.atomic():
            obj, created = base.get_or_create(**lookup, defaults=defaults)
            return obj, created
    except IntegrityError:
        # someone/previous run created it (or hidden by default manager)
        obj = base.filter(**lookup).first()
        if obj is None:
            # last resort: try to locate by common unique pair (tenant_id + name)
            tenant_id = lookup.get("tenant_id") or getattr(lookup.get("tenant", None), "id", None)
            name = lookup.get("name")
            if tenant_id and name:
                obj = base.filter(tenant_id=int(tenant_id), name=name).first()

        if obj is None:
            # still not found -> re-raise (something else is wrong)
            raise

        # keep it idempotent: update defaults if provided
        changed = False
        for k, v in (defaults or {}).items():
            if hasattr(obj, k) and getattr(obj, k) != v:
                setattr(obj, k, v)
                changed = True
        if changed:
            obj.save(update_fields=list((defaults or {}).keys()))
        return obj, False


class Command(BaseCommand):
    help = "Seed demo data: tenant + users + company/brand/shop + memberships + shopmember + monthly performance (DB-safe NOT NULL)"

    def add_arguments(self, parser):
        parser.add_argument("--tenant", default="HeightTech", help="Tenant name")
        parser.add_argument("--company", default="Height Media")
        parser.add_argument("--brand", default="Demo Brand")
        parser.add_argument("--shop", default="Demo Shop")
        parser.add_argument("--admin-user", default="admin")
        parser.add_argument("--admin-pass", default="admin123")
        parser.add_argument("--client-user", default="client1")
        parser.add_argument("--client-pass", default="client123")
        parser.add_argument("--months", type=int, default=6)
        parser.add_argument("--reset-performance", action="store_true")

    @transaction.atomic
    def handle(self, *args, **opts):
        tenant_name = (opts["tenant"] or "").strip()
        company_name = (opts["company"] or "").strip()
        brand_name = (opts["brand"] or "").strip()
        shop_name = (opts["shop"] or "").strip()

        admin_user = (opts["admin_user"] or "").strip()
        admin_pass = opts["admin_pass"]
        client_user = (opts["client_user"] or "").strip()
        client_pass = opts["client_pass"]

        months = max(1, min(int(opts["months"]), 24))
        reset_perf = bool(opts.get("reset_performance"))

        # -------------------------
        # Import models
        # -------------------------
        from apps.tenants.models import Tenant
        from apps.companies.models import Company
        from apps.brands.models import Brand
        from apps.shops.models import Shop, ShopMember
        from apps.accounts.models import Membership
        from apps.performance.models import MonthlyPerformance

        User = get_user_model()

        # -------------------------
        # Tenant
        # -------------------------
        t_defaults = {}
        _set_if_field(Tenant, t_defaults, "status", "active")
        _set_if_field(Tenant, t_defaults, "is_active", True)

        tenant, created = Tenant.objects.get_or_create(name=tenant_name, defaults=t_defaults)
        if not created:
            changed = False
            if _has_field(Tenant, "status") and getattr(tenant, "status", None) != "active":
                tenant.status = "active"
                changed = True
            if _has_field(Tenant, "is_active") and getattr(tenant, "is_active", True) is not True:
                tenant.is_active = True
                changed = True
            if changed:
                tenant.save()

        self.stdout.write(self.style.SUCCESS(f"✅ Tenant: {tenant.name} (id={tenant.id})"))

        # -------------------------
        # Users
        # -------------------------
        admin, created = User.objects.get_or_create(
            username=admin_user,
            defaults={"is_staff": True, "is_superuser": True},
        )
        if created:
            admin.set_password(admin_pass)
            admin.save()
            self.stdout.write(self.style.SUCCESS(f"✅ Created superuser: {admin_user}/{admin_pass}"))
        else:
            need_save = False
            if not getattr(admin, "is_staff", False):
                admin.is_staff = True
                need_save = True
            if not getattr(admin, "is_superuser", False):
                admin.is_superuser = True
                need_save = True
            if need_save:
                admin.save(update_fields=["is_staff", "is_superuser"])
            self.stdout.write(f"ℹ️ Superuser exists: {admin_user}")

        client, created = User.objects.get_or_create(
            username=client_user,
            defaults={"is_staff": False, "is_superuser": False},
        )
        if created:
            client.set_password(client_pass)
            client.save()
            self.stdout.write(self.style.SUCCESS(f"✅ Created client user: {client_user}/{client_pass}"))
        else:
            self.stdout.write(f"ℹ️ Client user exists: {client_user}")

        # =====================================================
        # Company (FINAL FIX: lookup đúng unique + chống IntegrityError)
        # =====================================================
        company_defaults = {}
        _set_if_field(Company, company_defaults, "is_active", True)

        if _has_field(Company, "tenant"):
            # UNIQUE KEY của bạn: (tenant_id, name)
            company_lookup = {"tenant_id": tenant.id, "name": company_name}
        else:
            company_lookup = {"name": company_name}

        company, _ = _safe_get_or_create_unique(Company, lookup=company_lookup, defaults=company_defaults)

        # đảm bảo đúng tenant
        if _has_field(Company, "tenant") and getattr(company, "tenant_id", None) != tenant.id:
            company.tenant = tenant
            company.save(update_fields=["tenant"])

        self.stdout.write(self.style.SUCCESS(f"✅ Company: {company.name} (id={company.id})"))

        # =====================================================
        # Brand (làm “chuẩn unique” tương tự để khỏi vỡ)
        # =====================================================
        brand_defaults = {}

        if _has_field(Brand, "company"):
            # thường unique sẽ là (company_id, name) hoặc bạn tự set
            brand_lookup = {"company_id": company.id, "name": brand_name}
        else:
            brand_lookup = {"name": brand_name}
            _set_if_field(Brand, brand_defaults, "company", company)

        brand, _ = _safe_get_or_create_unique(Brand, lookup=brand_lookup, defaults=brand_defaults)

        if _has_field(Brand, "company") and getattr(brand, "company_id", None) != company.id:
            brand.company = company
            brand.save(update_fields=["company"])

        self.stdout.write(self.style.SUCCESS(f"✅ Brand: {brand.name} (id={brand.id})"))

        # =====================================================
        # Shop (chuẩn unique theo tenant/brand/name nếu có)
        # =====================================================
        shop_defaults = {}
        _set_if_field(Shop, shop_defaults, "platform", "Shopee")
        _set_if_field(Shop, shop_defaults, "industry_code", "ecommerce")
        _set_if_field(Shop, shop_defaults, "rule_version", "v1")
        _set_if_field(Shop, shop_defaults, "status", "active")
        _set_if_field(Shop, shop_defaults, "is_active", True)

        shop_lookup = {"name": shop_name}
        if _has_field(Shop, "tenant"):
            shop_lookup["tenant_id"] = tenant.id
        if _has_field(Shop, "brand"):
            shop_lookup["brand_id"] = brand.id

        shop, _ = _safe_get_or_create_unique(Shop, lookup=shop_lookup, defaults=shop_defaults)

        update_fields = []
        if _has_field(Shop, "tenant") and getattr(shop, "tenant_id", None) != tenant.id:
            shop.tenant = tenant
            update_fields.append("tenant")
        if _has_field(Shop, "brand") and getattr(shop, "brand_id", None) != brand.id:
            shop.brand = brand
            update_fields.append("brand")
        if update_fields:
            shop.save(update_fields=update_fields)

        self.stdout.write(self.style.SUCCESS(f"✅ Shop: {shop.name} (id={shop.id})"))

        # -------------------------
        # ShopMember
        # -------------------------
        sm_defaults_owner = {}
        sm_defaults_client = {}
        _set_if_field(ShopMember, sm_defaults_owner, "role", "owner")
        _set_if_field(ShopMember, sm_defaults_owner, "is_active", True)
        _set_if_field(ShopMember, sm_defaults_client, "role", "client")
        _set_if_field(ShopMember, sm_defaults_client, "is_active", True)

        ShopMember.objects.get_or_create(shop=shop, user=admin, defaults=sm_defaults_owner)
        ShopMember.objects.get_or_create(shop=shop, user=client, defaults=sm_defaults_client)

        # -------------------------
        # Membership (tenant-safe)
        # -------------------------
        def membership_get_or_create(user, role: str):
            lookup = {"user": user, "company": company}
            defaults = {"role": role, "is_active": True}
            if _has_field(Membership, "tenant"):
                lookup["tenant"] = tenant

            obj, _ = Membership._base_manager.get_or_create(**lookup, defaults=defaults)

            changed = False
            if _has_field(Membership, "role") and getattr(obj, "role", None) != role:
                obj.role = role
                changed = True
            if _has_field(Membership, "is_active") and getattr(obj, "is_active", True) is not True:
                obj.is_active = True
                changed = True
            if _has_field(Membership, "tenant") and getattr(obj, "tenant_id", None) != tenant.id:
                obj.tenant = tenant
                changed = True
            if changed:
                obj.save()
            return obj

        membership_get_or_create(admin, "founder")
        membership_get_or_create(client, "operator")

        # --------------------------------------------------
        # MonthlyPerformance seed (DB NOT NULL safe UPSERT)
        # --------------------------------------------------
        MP = MonthlyPerformance
        mp_table = MP._meta.db_table

        if reset_perf:
            qs = MP._base_manager.all()
            if _has_field(MP, "tenant"):
                qs = qs.filter(tenant_id=tenant.id)
            if _has_field(MP, "shop"):
                qs = qs.filter(shop_id=shop.id)
            elif _has_field(MP, "company"):
                qs = qs.filter(company_id=company.id)
            deleted, _ = qs.delete()
            self.stdout.write(self.style.WARNING(f"🧹 Deleted MonthlyPerformance: {deleted}"))

        schema = _db_columns(mp_table, table_schema="public")

        reserved_cols = {
            "id",
            "tenant_id",
            "shop_id",
            "company_id",
            "month",
        }

        required_fill: dict[str, object] = {}
        missing_unfillable: list[str] = []

        for col, info in schema.items():
            if col in reserved_cols:
                continue
            if (info.get("is_nullable") or "").upper() != "NO":
                continue
            if info.get("column_default") is not None:
                continue

            val = _fallback_value_for_db_column(col, info)
            if val is None:
                missing_unfillable.append(col)
            else:
                required_fill[col] = val

        if "service_percent" in schema and (schema["service_percent"].get("is_nullable") or "").upper() == "NO":
            required_fill["service_percent"] = Decimal("0.15")
            if "service_percent" in missing_unfillable:
                missing_unfillable.remove("service_percent")

        if missing_unfillable:
            raise CommandError(
                "MonthlyPerformance has NOT NULL columns without default that seed_demo cannot auto-fill safely: "
                + ", ".join(sorted(set(missing_unfillable)))
                + ". Add fallback rules in _fallback_value_for_db_column() for these columns."
            )

        today = timezone.now().date()
        first_month = today.replace(day=1)

        conflict_sql = "ON CONFLICT ON CONSTRAINT uq_perf_tenant_shop_month"

        with transaction.atomic():
            for i in range(months):
                mdate = _shift_month(first_month, i)

                revenue = Decimal("100000000") - Decimal(str(i * 5000000))
                if revenue < 0:
                    revenue = Decimal("0")
                cost = revenue * Decimal("0.75")
                profit = revenue - cost
                net = profit * Decimal("0.85")

                now_ts = timezone.now()

                cols = ["tenant_id", "shop_id", "month"]
                vals = [tenant.id, shop.id, mdate]
                set_parts = []

                if "company_id" in schema:
                    cols.append("company_id")
                    vals.append(company.id)
                    set_parts.append("company_id = EXCLUDED.company_id")

                if "revenue" in schema:
                    cols.append("revenue")
                    vals.append(revenue)
                    set_parts.append("revenue = EXCLUDED.revenue")
                if "cost" in schema:
                    cols.append("cost")
                    vals.append(cost)
                    set_parts.append("cost = EXCLUDED.cost")
                if "profit" in schema:
                    cols.append("profit")
                    vals.append(profit)
                    set_parts.append("profit = EXCLUDED.profit")
                if "company_net_profit" in schema:
                    cols.append("company_net_profit")
                    vals.append(net)
                    set_parts.append("company_net_profit = EXCLUDED.company_net_profit")

                for col, v in required_fill.items():
                    if col in cols:
                        continue
                    cols.append(col)
                    vals.append(v)
                    set_parts.append(f"{col} = EXCLUDED.{col}")

                if "created_at" in schema:
                    info = schema["created_at"]
                    if (info.get("is_nullable") or "").upper() == "NO" and info.get("column_default") is None:
                        if "created_at" not in cols:
                            cols.append("created_at")
                            vals.append(now_ts)

                if "updated_at" in schema:
                    info = schema["updated_at"]
                    if (info.get("is_nullable") or "").upper() == "NO" and info.get("column_default") is None:
                        if "updated_at" not in cols:
                            cols.append("updated_at")
                            vals.append(now_ts)
                        if "updated_at = EXCLUDED.updated_at" not in set_parts:
                            set_parts.append("updated_at = EXCLUDED.updated_at")

                placeholders = ", ".join(["%s"] * len(vals))
                col_sql = ", ".join(cols)
                set_sql = ", ".join(set_parts) if set_parts else "month = EXCLUDED.month"

                sql = f"""
                    INSERT INTO {mp_table} ({col_sql})
                    VALUES ({placeholders})
                    {conflict_sql}
                    DO UPDATE SET {set_sql}
                """

                with connection.cursor() as cur:
                    cur.execute(sql, vals)

        self.stdout.write(self.style.SUCCESS("✅ MonthlyPerformance upsert OK (DB NOT NULL safe)"))

        # -------------------------
        # Done
        # -------------------------
        self.stdout.write(self.style.SUCCESS("✅ Seed demo OK"))
        self.stdout.write(f"Tenant:  {tenant.name} (id={tenant.id})")
        self.stdout.write(f"Company: {company.name} (id={company.id})")
        self.stdout.write(f"Brand:   {brand.name} (id={brand.id})")
        self.stdout.write(f"Shop:    {shop.name} (id={shop.id})")
        self.stdout.write("URLs:")
        self.stdout.write(" - http://127.0.0.1:8000/admin/")
        self.stdout.write(" - http://127.0.0.1:8000/dashboard/")
        self.stdout.write(" - http://127.0.0.1:8000/dashboard/projects/")
        self.stdout.write(" - http://127.0.0.1:8000/founder/")
        self.stdout.write("API:")
        self.stdout.write(" - http://127.0.0.1:8000/api/v1/dashboard/")
        self.stdout.write(" - http://127.0.0.1:8000/api/v1/founder/")
        self.stdout.write(" - http://127.0.0.1:8000/api/v1/founder/shops/1/")