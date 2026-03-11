from __future__ import annotations

from typing import Optional, Tuple

from django.db import transaction

from apps.brands.models import Brand
from apps.contracts.models import Contract
from apps.shops.models import Shop


def _clean_name(value: Optional[str], fallback: str = "") -> str:
    v = (value or "").strip()
    return v or fallback


def _make_shop_code(contract: Contract, base_name: str) -> str:
    raw = (base_name or contract.code or "SHOP").upper().strip()
    raw = raw.replace(" ", "-")
    raw = raw.replace("/", "-")
    raw = raw.replace("\\", "-")
    raw = raw.replace("_", "-")

    while "--" in raw:
        raw = raw.replace("--", "-")

    raw = raw.strip("-")
    if not raw:
        raw = f"SHOP-{contract.code}"

    code = raw[:50]

    # tránh trùng code trong tenant
    original = code
    i = 1
    while Shop.objects_all.filter(tenant_id=contract.tenant_id, code=code).exists():
        i += 1
        suffix = f"-{i}"
        code = f"{original[:50-len(suffix)]}{suffix}"

    return code


@transaction.atomic
def provision_shop_from_contract(contract: Contract) -> Tuple[Optional[Brand], Optional[Shop], bool]:
    """
    Tạo Brand + Shop từ Contract nếu phù hợp.

    Return:
        (brand, shop, created)

    Logic:
    - Nếu contract type không phải operation / channel thì không tạo shop
    - Nếu đã có shop gắn với contract rồi thì trả về shop cũ
    - Nếu chưa có thì tạo brand (nếu cần), tạo shop, rồi tạo liên kết ContractShop
    """

    contract = Contract.objects_all.select_for_update().get(id=contract.id)

    ctype = (contract.contract_type or "").strip().lower()

    # Chỉ auto provision cho loại cần shop / channel
    auto_types = {
        getattr(Contract.Type, "OPERATION", "operation"),
        getattr(Contract.Type, "CHANNEL", "channel"),
    }

    if ctype not in auto_types:
        return None, None, False

    # import ở đây để tránh vòng import
    from apps.contracts.models import ContractShop

    # 1) Nếu contract đã gắn shop rồi thì trả shop hiện có
    existing_link = (
        ContractShop.objects_all
        .select_related("shop")
        .filter(contract_id=contract.id, tenant_id=contract.tenant_id)
        .order_by("id")
        .first()
    )
    if existing_link and existing_link.shop_id:
        shop = existing_link.shop
        brand = getattr(shop, "brand", None)
        return brand, shop, False

    # 2) Tạo / lấy brand
    brand_name = _clean_name(
        getattr(contract, "brand_name", None),
        fallback=_clean_name(getattr(contract, "partner_name", None), fallback=contract.code),
    )

    brand = Brand.objects_all.filter(
        tenant_id=contract.tenant_id,
        name__iexact=brand_name,
    ).first()

    if not brand:
        brand = Brand.objects_all.create(
            tenant_id=contract.tenant_id,
            name=brand_name,
            is_active=True,
        )

    # 3) Tạo shop
    shop_name = _clean_name(
        getattr(contract, "shop_name", None),
        fallback=brand_name,
    )
    shop_code = _make_shop_code(contract, shop_name)

    shop = Shop.objects_all.create(
        tenant_id=contract.tenant_id,
        company_id=contract.company_id,
        brand=brand,
        code=shop_code,
        name=shop_name,
        is_active=True,
    )

    # 4) Tạo link Contract -> Shop
    ContractShop.objects_all.create(
        tenant_id=contract.tenant_id,
        contract_id=contract.id,
        shop_id=shop.id,
    )

    return brand, shop, True