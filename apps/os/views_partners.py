# apps/os/views_partners.py
from __future__ import annotations

from django.contrib import messages
from django.shortcuts import redirect, render
from django.views import View

from apps.companies.models import Company


def _tenant_id_from_request(request):
    tid = request.headers.get("X-Tenant-Id")
    if tid:
        try:
            return int(tid)
        except Exception:
            pass

    try:
        from apps.accounts.models import Membership

        user = getattr(request, "user", None)
        if user and user.is_authenticated:
            m = (
                Membership.objects.filter(user=user, is_active=True)
                .order_by("id")
                .first()
            )
            if m and m.tenant_id:
                return int(m.tenant_id)
    except Exception:
        pass

    tenant = getattr(request, "tenant", None)
    tid = getattr(tenant, "id", None) if tenant else None
    if tid:
        try:
            return int(tid)
        except Exception:
            pass

    tid = getattr(request, "tenant_id", None)
    if tid:
        try:
            return int(tid)
        except Exception:
            pass

    return None


def _company_qs():
    return getattr(Company, "objects_all", Company.objects)


class PartnerListView(View):
    template_name = "os_partners.html"

    def get(self, request):
        tenant_id = _tenant_id_from_request(request)
        q = (request.GET.get("q") or "").strip()

        items = _company_qs().filter(tenant_id=tenant_id).order_by("-id") if tenant_id else _company_qs().none()

        if q:
            items = items.filter(name__icontains=q)

        return render(
            request,
            self.template_name,
            {
                "tenant_id": tenant_id,
                "items": items[:100],
                "q": q,
            },
        )


class PartnerCreateView(View):
    template_name = "os_partner_new.html"

    def get(self, request):
        tenant_id = _tenant_id_from_request(request)
        return render(
            request,
            self.template_name,
            {
                "tenant_id": tenant_id,
            },
        )

    def post(self, request):
        tenant_id = _tenant_id_from_request(request)
        name = (request.POST.get("name") or "").strip()

        if not tenant_id:
            messages.error(request, "Không xác định được tenant hiện tại.")
            return render(request, self.template_name, {"tenant_id": tenant_id})

        if not name:
            messages.error(request, "Anh cần nhập tên Công Ty / Đối Tác.")
            return render(request, self.template_name, {"tenant_id": tenant_id})

        exists = _company_qs().filter(tenant_id=tenant_id, name__iexact=name).first()
        if exists:
            messages.warning(request, "Công Ty / Đối Tác này đã tồn tại.")
            return redirect("/os/partners/")

        try:
            obj = _company_qs().create(
                tenant_id=tenant_id,
                name=name,
            )
            messages.success(request, f"Đã tạo Công Ty / Đối Tác: {obj.name}")
            return redirect("/os/partners/")
        except Exception as e:
            messages.error(request, f"Không tạo được Công Ty / Đối Tác: {e}")
            return render(request, self.template_name, {"tenant_id": tenant_id})