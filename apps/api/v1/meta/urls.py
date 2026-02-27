from django.urls import path, include

urlpatterns = [
    path("meta/", include("apps.api.v1.meta.urls")),
]