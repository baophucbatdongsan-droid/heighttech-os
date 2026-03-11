from __future__ import annotations

from django.shortcuts import render
from apps.companies.models import Company


def company_workspace_page(request, company_id: int):
    company = Company.objects_all.filter(id=company_id).first()

    return render(
        request,
        "os_company_workspace.html",
        {
            "company": company,
        },
    )