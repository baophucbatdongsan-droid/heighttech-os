from django.urls import path

from .views import (
    ShopListApi,
    ShopCreateApi,
    ShopSkuListApi,
    ShopSkuCreateApi,
)
from .workspace import ShopCreateWorkspaceApi

urlpatterns = [
    path("", ShopListApi.as_view(), name="shop-list"),
    path("create/", ShopCreateApi.as_view(), name="shop-create"),
    path("create-workspace/", ShopCreateWorkspaceApi.as_view(), name="shop-create-workspace"),

    path("skus/", ShopSkuListApi.as_view(), name="shop-sku-list"),
    path("skus/create/", ShopSkuCreateApi.as_view(), name="shop-sku-create"),
]