from django.views.generic import TemplateView
from apps.core.mixins import RoleRequiredMixin

class AppHomeView(RoleRequiredMixin, TemplateView):
    allowed_roles = ("operator", "client", "admin", "founder")
    template_name = "app/home.html"