from __future__ import annotations

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.db import transaction

from apps.accounts.models import Membership, ROLE_FOUNDER
from apps.companies.models import Company
from apps.tenants.models import Tenant

User = get_user_model()


class RegisterForm(forms.Form):
    email = forms.EmailField(
        label="Email",
        required=True,
        widget=forms.EmailInput(
            attrs={
                "placeholder": "Nhập email doanh nghiệp",
                "autocomplete": "email",
            }
        ),
        error_messages={
            "required": "Email không được để trống.",
            "invalid": "Email không đúng định dạng.",
        },
    )

    company_name = forms.CharField(
        label="Tên công ty",
        required=True,
        max_length=255,
        widget=forms.TextInput(
            attrs={
                "placeholder": "Ví dụ: Height Entertainment",
                "autocomplete": "organization",
            }
        ),
        error_messages={
            "required": "Tên công ty không được để trống.",
        },
    )

    password1 = forms.CharField(
        label="Mật khẩu",
        required=True,
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "placeholder": "Tạo mật khẩu",
                "autocomplete": "new-password",
            }
        ),
        error_messages={
            "required": "Mật khẩu không được để trống.",
        },
    )

    password2 = forms.CharField(
        label="Xác nhận mật khẩu",
        required=True,
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "placeholder": "Nhập lại mật khẩu",
                "autocomplete": "new-password",
            }
        ),
        error_messages={
            "required": "Vui lòng xác nhận mật khẩu.",
        },
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for name in self.fields:
            self.fields[name].widget.attrs.update({"class": "input"})

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip().lower()

        if not email:
            raise forms.ValidationError("Email không được để trống.")

        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Email đã tồn tại.")

        return email

    def clean_company_name(self):
        value = (self.cleaned_data.get("company_name") or "").strip()

        if not value:
            raise forms.ValidationError("Tên công ty không được để trống.")

        return value

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get("password1")
        password2 = cleaned_data.get("password2")

        if password1 and password2 and password1 != password2:
            self.add_error("password2", "Mật khẩu xác nhận không khớp.")

        if password1:
            try:
                validate_password(password1)
            except forms.ValidationError as e:
                self.add_error("password1", e)

        return cleaned_data

    @transaction.atomic
    def save(self):
        email = self.cleaned_data["email"].strip().lower()
        company_name = self.cleaned_data["company_name"].strip()
        password = self.cleaned_data["password1"]

        # 1) user
        user = User(
            username=email,
            email=email,
            is_active=True,
        )
        user.set_password(password)
        user.save()

        # 2) tenant
        tenant = Tenant.objects.create(
            name=company_name,
            plan=Tenant.PLAN_BASIC,
            status=Tenant.STATUS_ACTIVE,
            is_active=True,
        )

        # 3) company
        company = Company.objects_all.create(
            tenant=tenant,
            agency=tenant.agency,
            name=company_name,
            max_clients=5,
            months_active=0,
            is_active=True,
        )

        # 4) membership
        membership = Membership.objects.create(
            tenant=tenant,
            user=user,
            company=company,
            role=ROLE_FOUNDER,
            is_active=True,
        )

        return {
            "user": user,
            "tenant": tenant,
            "company": company,
            "membership": membership,
        }