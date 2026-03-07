from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from apps.core.permissions import AbilityPermission, VIEW_API_DASHBOARD
from apps.intelligence.action_engine.runner import run_action_engine


class ActionEngineApi(APIView):

    permission_classes = [IsAuthenticated, AbilityPermission]
    required_ability = VIEW_API_DASHBOARD

    def get(self, request):

        tenant_id = getattr(request, "tenant_id", None)

        alerts = run_action_engine(tenant_id)

        return Response({
            "ok": True,
            "alerts": alerts
        })