from __future__ import annotations

from django import forms
from django.contrib.auth import authenticate


class EmailLoginForm(forms.Form):
    username = forms.EmailField(
        label="Email",
        required=True,
        widget=forms.EmailInput(
            attrs={
                "placeholder": "Nhập email",
                "autocomplete": "email",
            }
        ),
        error_messages={
            "required": "Email không được để trống.",
            "invalid": "Email không đúng định dạng.",
        },
    )

    password = forms.CharField(
        label="Mật khẩu",
        required=True,
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "placeholder": "Nhập mật khẩu",
                "autocomplete": "current-password",
            }
        ),
        error_messages={
            "required": "Mật khẩu không được để trống.",
        },
    )

    error_messages = {
        "invalid_login": "Email hoặc mật khẩu không đúng.",
        "inactive": "Tài khoản đã bị khóa.",
    }

    def __init__(self, request=None, *args, **kwargs):
        self.request = request
        self.user_cache = None
        super().__init__(*args, **kwargs)

        self.fields["username"].widget.attrs.update({"class": "input"})
        self.fields["password"].widget.attrs.update({"class": "input"})

    def clean(self):
        cleaned_data = super().clean()
        email = (cleaned_data.get("username") or "").strip().lower()
        password = cleaned_data.get("password")

        if email and password:
            self.user_cache = authenticate(
                self.request,
                username=email,
                password=password,
            )

            if self.user_cache is None:
                raise forms.ValidationError(
                    self.error_messages["invalid_login"],
                    code="invalid_login",
                )

            if not self.user_cache.is_active:
                raise forms.ValidationError(
                    self.error_messages["inactive"],
                    code="inactive",
                )

        return cleaned_data

    def get_user(self):
        return self.user_cache