from django.urls import path

from .views import ShopListApi, ShopCreateApi
from .workspace import ShopCreateWorkspaceApi

urlpatterns = [
    path("", ShopListApi.as_view(), name="shop-list"),
    path("create/", ShopCreateApi.as_view(), name="shop-create"),
    path("create-workspace/", ShopCreateWorkspaceApi.as_view(), name="shop-create-workspace"),
]