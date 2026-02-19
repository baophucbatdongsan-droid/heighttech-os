from django.urls import include, path
from .views import ApiRoot

urlpatterns = [
    path("", ApiRoot.as_view(), name="api-root"),
    path("v1/", include("apps.api.v1.urls")),
]