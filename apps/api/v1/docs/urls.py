from django.urls import path

from apps.api.v1.docs.views import (
    DocumentCreateApi,
    DocumentDetailApi,
    DocumentImageUploadApi,
    DocumentListApi,
    DocumentUpdateApi,
)

urlpatterns = [
    path("", DocumentListApi.as_view()),
    path("create/", DocumentCreateApi.as_view()),
    path("upload-image/", DocumentImageUploadApi.as_view()),
    path("<int:doc_id>/", DocumentDetailApi.as_view()),
    path("<int:doc_id>/update/", DocumentUpdateApi.as_view()),
]