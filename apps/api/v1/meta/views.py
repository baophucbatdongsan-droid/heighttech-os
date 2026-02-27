from __future__ import annotations

from rest_framework.views import APIView
from rest_framework.response import Response

from apps.core.catalogs.industry import v2026_02 as industry_catalog


class IndustryMetaView(APIView):

    def get(self, request):
        return Response({
            "ok": True,
            "version": industry_catalog.VERSION,
            "clusters": industry_catalog.CLUSTERS,
        })