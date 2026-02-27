# apps/core/catalogs/industry/v2026_02.py
from __future__ import annotations

VERSION = "v2026_02"

CLUSTERS = [
    {
        "code": "BEAUTY",
        "label": "Làm đẹp",
        "items": [
            {"code": "BEAUTY_SKINCARE", "label": "Chăm sóc da"},
            {"code": "BEAUTY_MAKEUP", "label": "Trang điểm"},
            {"code": "BEAUTY_HAIR", "label": "Chăm sóc tóc"},
            {"code": "BEAUTY_BODY", "label": "Chăm sóc cơ thể"},
            {"code": "BEAUTY_PERFUME", "label": "Nước hoa"},
        ],
    },
    {
        "code": "FASHION",
        "label": "Thời trang",
        "items": [
            {"code": "FASHION_MEN", "label": "Nam"},
            {"code": "FASHION_WOMEN", "label": "Nữ"},
            {"code": "FASHION_KIDS", "label": "Trẻ em"},
            {"code": "FASHION_SHOES", "label": "Giày dép"},
            {"code": "FASHION_ACCESSORIES", "label": "Phụ kiện"},
        ],
    },
    {
        "code": "FMCG",
        "label": "FMCG",
        "items": [
            {"code": "FMCG_SNACK", "label": "Snack"},
            {"code": "FMCG_BEVERAGE", "label": "Đồ uống"},
            {"code": "FMCG_GROCERY", "label": "Tạp hoá"},
        ],
    },
    {
        "code": "HEALTH",
        "label": "Sức khỏe",
        "items": [
            {"code": "HEALTH_SUPPLEMENT", "label": "Thực phẩm chức năng"},
            {"code": "HEALTH_MEDICAL_DEVICE", "label": "Thiết bị y tế"},
        ],
    },
    {
        "code": "ELECTRONICS",
        "label": "Điện tử",
        "items": [
            {"code": "ELECTRONICS_PHONE", "label": "Điện thoại"},
            {"code": "ELECTRONICS_ACCESSORIES", "label": "Phụ kiện điện tử"},
        ],
    },
    {
        "code": "HOME",
        "label": "Nhà cửa",
        "items": [
            {"code": "HOME_FURNITURE", "label": "Nội thất"},
            {"code": "HOME_KITCHEN", "label": "Nhà bếp"},
        ],
    },
]

# flat index để validate nhanh
INDEX = {
    item["code"]: item
    for cluster in CLUSTERS
    for item in cluster["items"]
}