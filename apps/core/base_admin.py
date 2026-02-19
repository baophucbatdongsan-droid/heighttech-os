from django.contrib import admin


class BaseCompanyAdmin(admin.ModelAdmin):
    """
    Base admin cho toàn bộ model có field 'company'
    Áp dụng multi-tenant + role permission chuẩn SaaS
    """

    def get_queryset(self, request):
        qs = super().get_queryset(request)

        if request.user.is_superuser:
            return qs

        memberships = request.user.memberships.filter(is_active=True)

        if not memberships.exists():
            return qs.none()

        roles = memberships.values_list("role", flat=True)
        company_ids = memberships.values_list("company_id", flat=True)

        # Founder = toàn hệ thống
        if "founder" in roles:
            return qs

        # Head = toàn bộ company mình
        if "head" in roles:
            return qs.filter(company_id__in=company_ids)

        # Account
        if "account" in roles and hasattr(self.model, "account_manager"):
            return qs.filter(account_manager=request.user)

        # Operator
        if "operator" in roles and hasattr(self.model, "operator"):
            return qs.filter(operator=request.user)

        return qs.none()

    def save_model(self, request, obj, form, change):
        if not change and hasattr(obj, "company"):
            membership = request.user.memberships.filter(is_active=True).first()
            if membership:
                obj.company = membership.company
        super().save_model(request, obj, form, change)

    def has_change_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True

        if obj is None:
            return True

        memberships = request.user.memberships.filter(is_active=True)
        roles = memberships.values_list("role", flat=True)

        if "founder" in roles:
            return True

        if "head" in roles and obj.company in [m.company for m in memberships]:
            return True

        if "account" in roles and hasattr(obj, "account_manager"):
            return obj.account_manager == request.user

        if "operator" in roles and hasattr(obj, "operator"):
            return obj.operator == request.user

        return False

    def has_delete_permission(self, request, obj=None):
        if request.user.is_superuser:
            return True

        memberships = request.user.memberships.filter(is_active=True)
        roles = memberships.values_list("role", flat=True)

        if "founder" in roles:
            return True

        if "head" in roles:
            return True

        return False