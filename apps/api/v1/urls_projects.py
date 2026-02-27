# apps/api/v1/urls_projects.py
from __future__ import annotations

from django.core.exceptions import ImproperlyConfigured
from django.urls import path

from apps.api.v1 import projects as v


def _pick(*names: str):
    """
    Pick first existing attribute from apps.api.v1.projects module.
    Helps avoid ImportError when class names differ.
    """
    for n in names:
        obj = getattr(v, n, None)
        if obj is not None:
            return obj
    return None


# Required: list/create
ProjectListCreateApi = _pick("ProjectListCreateApi", "ProjectListApi", "ProjectsApi")
if ProjectListCreateApi is None:
    raise ImproperlyConfigured(
        "Missing Project list/create API. Expected one of: "
        "ProjectListCreateApi / ProjectListApi / ProjectsApi in apps.api.v1.projects"
    )

# Optional: detail (get/patch/delete)
ProjectDetailApi = _pick(
    "ProjectDetailApi",
    "ProjectRetrieveUpdateDeleteApi",
    "ProjectRetrieveUpdateApi",
    "ProjectDetailUpdateDeleteApi",
    "ProjectDetailUpdateApi",
)
# Optional: project shops nested
ProjectShopListCreateApi = _pick(
    "ProjectShopListCreateApi",
    "ProjectShopApi",
    "ProjectShopsApi",
    "ProjectShopAssignApi",
)
ProjectShopDetailApi = _pick(
    "ProjectShopDetailApi",
    "ProjectShopUpdateDeleteApi",
    "ProjectShopUpdateApi",
)

urlpatterns = [
    # /api/v1/projects/
    path("projects/", ProjectListCreateApi.as_view(), name="api_v1_projects"),

    # /api/v1/projects/<int:project_id>/
    # chỉ add nếu projects.py có class detail tương ứng
    *(
        [path("projects/<int:project_id>/", ProjectDetailApi.as_view(), name="api_v1_project_detail")]
        if ProjectDetailApi
        else []
    ),

    # /api/v1/projects/<int:project_id>/shops/
    *(
        [
            path(
                "projects/<int:project_id>/shops/",
                ProjectShopListCreateApi.as_view(),
                name="api_v1_project_shops",
            )
        ]
        if ProjectShopListCreateApi
        else []
    ),

    # /api/v1/projects/<int:project_id>/shops/<int:project_shop_id>/
    *(
        [
            path(
                "projects/<int:project_id>/shops/<int:project_shop_id>/",
                ProjectShopDetailApi.as_view(),
                name="api_v1_project_shop_detail",
            )
        ]
        if ProjectShopDetailApi
        else []
    ),
]