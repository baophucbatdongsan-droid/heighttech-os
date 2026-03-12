from django.urls import path

from apps.api.v1.sheets.views import (
    SheetCellUpdateApi,
    SheetColumnCreateApi,
    SheetCreateApi,
    SheetDetailApi,
    SheetExportExcelApi,
    SheetListApi,
    SheetRowCreateApi,
)
from apps.api.v1.sheets.views_upload import SheetImageUploadApi

urlpatterns = [
    path("", SheetListApi.as_view()),
    path("create/", SheetCreateApi.as_view()),
    path("cells/update/", SheetCellUpdateApi.as_view()),
    path("upload-image/", SheetImageUploadApi.as_view()),
    path("<int:sheet_id>/", SheetDetailApi.as_view()),
    path("<int:sheet_id>/columns/create/", SheetColumnCreateApi.as_view()),
    path("<int:sheet_id>/rows/create/", SheetRowCreateApi.as_view()),
    path("<int:sheet_id>/export.xlsx", SheetExportExcelApi.as_view()),
]