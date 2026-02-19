from django.http import JsonResponse
from django.contrib.auth.decorators import login_required


@login_required
def me_api(request):
    user = request.user

    data = {
        "id": user.id,
        "username": user.username,
        "is_superuser": user.is_superuser,
        "is_staff": user.is_staff,
        "groups": list(user.groups.values_list("name", flat=True)),
    }

    return JsonResponse({
        "ok": True,
        "data": data,
    })