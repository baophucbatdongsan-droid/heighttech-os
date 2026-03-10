from django.urls import path
from .views import RegisterApi

urlpatterns = [
    path("register/", RegisterApi.as_view()),
]