from django.shortcuts import redirect
from django.contrib.auth.decorators import login_required

from apps.core.permissions import (
    is_founder,
    is_head,
    is_account,
    is_operator,
)


@login_required
def home_redirect(request):
    user = request.user

    # Founder / Head → Intelligence
    if user.is_superuser or is_founder(user) or is_head(user):
        return redirect("/intelligence/")

    # Account / Operator → Dashboard
    if is_account(user) or is_operator(user):
        return redirect("/dashboard/")

    return redirect("/dashboard/")