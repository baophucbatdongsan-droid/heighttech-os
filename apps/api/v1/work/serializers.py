# apps/api/v1/work/serializers.py
from __future__ import annotations

from typing import Any, Dict, List, Optional

from django.apps import apps
from rest_framework import serializers

from apps.core.permissions import ROLE_CLIENT, resolve_user_role
from apps.work.models import WorkComment, WorkItem


# =====================================================
# Helpers clean input
# =====================================================
def _clean_str(v: Any) -> str:
    s = (v or "").strip()
    if s.lower() in {"none", "null", "undefined"}:
        return ""
    return s


def _clean_int(v: Any) -> Optional[int]:
    if v is None:
        return None
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    s = str(v).strip()
    if not s or s.lower() in {"none", "null", "undefined"}:
        return None
    try:
        return int(s)
    except Exception:
        return None


def _clean_tags(v: Any) -> List[str]:
    """
    tags: chuẩn list[str]
    - None -> []
    - "a,b" -> ["a","b"]
    - ["a","b"] -> giữ
    - "[]" -> []
    """
    if v is None:
        return []
    if isinstance(v, list):
        out: List[str] = []
        for x in v:
            s = _clean_str(x)
            if s:
                out.append(s)
        return out

    s = str(v).strip()
    if not s or s.lower() in {"none", "null", "undefined", "[]"}:
        return []
    if "," in s:
        return [x.strip() for x in s.split(",") if x.strip()]
    return [s]


def _resolve_company_tenant_from_project(project_id: Optional[int]) -> Dict[str, Optional[int]]:
    """
    project -> company_id + tenant_id (nếu có)
    """
    if not project_id:
        return {"company_id": None, "tenant_id": None}

    Project = apps.get_model("projects", "Project")
    p = Project.objects_all.filter(id=project_id).only("id", "company_id", "tenant_id").first()
    if not p:
        return {"company_id": None, "tenant_id": None}

    return {
        "company_id": getattr(p, "company_id", None),
        "tenant_id": getattr(p, "tenant_id", None),
    }


def _resolve_company_tenant_from_target(target_type: str, target_id: Optional[int]) -> Dict[str, Optional[int]]:
    """
    target (shop/channel/booking) -> company_id + tenant_id (nếu có)
    """
    tt = (target_type or "").strip().lower()
    tid = target_id
    if not tt or not tid:
        return {"company_id": None, "tenant_id": None}

    # shop -> company
    if tt == "shop":
        try:
            Shop = apps.get_model("shops", "Shop")
            s = Shop.objects_all.filter(id=tid).only("id", "company_id", "tenant_id").first()
            if s:
                return {"company_id": getattr(s, "company_id", None), "tenant_id": getattr(s, "tenant_id", None)}
        except Exception:
            pass

    # channel -> shop -> company
    if tt == "channel":
        try:
            ChannelShopLink = apps.get_model("channels", "ChannelShopLink")
            Shop = apps.get_model("shops", "Shop")
            link = ChannelShopLink.objects_all.filter(channel_id=tid).only("shop_id").first()
            if link and getattr(link, "shop_id", None):
                s = Shop.objects_all.filter(id=link.shop_id).only("company_id", "tenant_id").first()
                if s:
                    return {"company_id": getattr(s, "company_id", None), "tenant_id": getattr(s, "tenant_id", None)}
        except Exception:
            pass

    # booking -> shop -> company
    if tt == "booking":
        try:
            Booking = apps.get_model("booking", "Booking")
            Shop = apps.get_model("shops", "Shop")
            b = Booking.objects_all.filter(id=tid).only("shop_id").first()
            if b and getattr(b, "shop_id", None):
                s = Shop.objects_all.filter(id=b.shop_id).only("company_id", "tenant_id").first()
                if s:
                    return {"company_id": getattr(s, "company_id", None), "tenant_id": getattr(s, "tenant_id", None)}
        except Exception:
            pass

    return {"company_id": None, "tenant_id": None}


# =====================================================
# WorkItem Serializer (FINAL)
# =====================================================
class WorkItemSerializer(serializers.ModelSerializer):
    """
    ✅ FINAL FIX (đã PASS smoke_work):
    - KHAI BÁO EXPLICIT *_id fields để DRF chắc chắn accept input
      (fix triệt để create bị company_id=None do validated_data thiếu key)
    - Clean None/null/undefined
    - Auto-fill company_id từ project/target
    - Trả role + can_* cho FE
    """

    # ✅ Explicit ID fields (chìa khoá fix)
    tenant_id = serializers.IntegerField(required=False, allow_null=True)
    company_id = serializers.IntegerField(required=False, allow_null=True)
    project_id = serializers.IntegerField(required=False, allow_null=True)
    assignee_id = serializers.IntegerField(required=False, allow_null=True)
    requester_id = serializers.IntegerField(required=False, allow_null=True)
    target_id = serializers.IntegerField(required=False, allow_null=True)
    position = serializers.IntegerField(required=False, allow_null=True)

    # tags: normalize về list[str]
    tags = serializers.ListField(child=serializers.CharField(), required=False, allow_null=True)

    # ===== FE flags =====
    role = serializers.SerializerMethodField()
    can_view = serializers.SerializerMethodField()
    can_comment = serializers.SerializerMethodField()
    can_edit = serializers.SerializerMethodField()
    can_move = serializers.SerializerMethodField()
    can_delete = serializers.SerializerMethodField()

    class Meta:
        model = WorkItem
        fields = [
            "id",
            "tenant_id",
            "company_id",
            "project_id",
            "title",
            "description",
            "status",
            "priority",
            "position",
            "tags",
            "due_at",
            "started_at",
            "done_at",
            "assignee_id",
            "requester_id",
            "target_type",
            "target_id",
            "is_internal",
            "created_at",
            "updated_at",
            # FE flags
            "role",
            "can_view",
            "can_comment",
            "can_edit",
            "can_move",
            "can_delete",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    # -------------------------
    # role + can_* helpers
    # -------------------------
    def _get_user_role(self) -> str:
        req = self.context.get("request")
        u = getattr(req, "user", None) if req else None
        return resolve_user_role(u)

    def get_role(self, obj: WorkItem) -> str:
        return self._get_user_role()

    def get_can_view(self, obj: WorkItem) -> bool:
        role = self._get_user_role()
        if role == ROLE_CLIENT:
            return not bool(getattr(obj, "is_internal", False))
        return True

    def get_can_comment(self, obj: WorkItem) -> bool:
        role = self._get_user_role()
        if role == ROLE_CLIENT:
            return not bool(getattr(obj, "is_internal", False))
        return True

    def get_can_edit(self, obj: WorkItem) -> bool:
        return self._get_user_role() != ROLE_CLIENT

    def get_can_move(self, obj: WorkItem) -> bool:
        return self._get_user_role() != ROLE_CLIENT

    def get_can_delete(self, obj: WorkItem) -> bool:
        return self._get_user_role() != ROLE_CLIENT

    # -------------------------
    # validate (clean + autofill)
    # -------------------------
    def validate(self, attrs: Dict[str, Any]) -> Dict[str, Any]:
        if "target_type" in attrs:
            attrs["target_type"] = _clean_str(attrs.get("target_type"))

        # clean ints
        for k in ["tenant_id", "company_id", "project_id", "assignee_id", "requester_id", "target_id", "position"]:
            if k in attrs:
                attrs[k] = _clean_int(attrs.get(k))

        # clean tags
        if "tags" in attrs:
            attrs["tags"] = _clean_tags(attrs.get("tags"))

        company_id = attrs.get("company_id")
        tenant_id = attrs.get("tenant_id")
        project_id = attrs.get("project_id")

        # 1) project -> company/tenant
        if project_id and not company_id:
            resolved = _resolve_company_tenant_from_project(project_id)
            if resolved.get("company_id"):
                attrs["company_id"] = resolved["company_id"]
                company_id = attrs["company_id"]
            if (not tenant_id) and resolved.get("tenant_id"):
                attrs["tenant_id"] = resolved["tenant_id"]
                tenant_id = attrs["tenant_id"]

        # 2) target -> company/tenant
        if not company_id:
            tt = attrs.get("target_type") or ""
            tid = attrs.get("target_id")
            resolved = _resolve_company_tenant_from_target(tt, tid)
            if resolved.get("company_id"):
                attrs["company_id"] = resolved["company_id"]
                company_id = attrs["company_id"]
            if (not tenant_id) and resolved.get("tenant_id"):
                attrs["tenant_id"] = resolved["tenant_id"]
                tenant_id = attrs["tenant_id"]

        return attrs


# =====================================================
# Comments
# =====================================================
class WorkCommentSerializer(serializers.ModelSerializer):
    actor_username = serializers.CharField(source="actor.username", read_only=True)

    class Meta:
        model = WorkComment
        fields = [
            "id",
            "tenant_id",
            "work_item_id",
            "actor_id",
            "actor_username",
            "body",
            "meta",
            "created_at",
        ]


class WorkCommentCreateSerializer(serializers.Serializer):
    body = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    meta = serializers.JSONField(required=False)

    def validate(self, attrs: Dict[str, Any]) -> Dict[str, Any]:
        body = (attrs.get("body") or "").strip()
        meta = attrs.get("meta")

        if not body and (meta is None or meta == {}):
            raise serializers.ValidationError("body hoặc meta là bắt buộc")
        if meta is not None and not isinstance(meta, dict):
            raise serializers.ValidationError("meta phải là object/dict")

        attrs["body"] = body
        attrs["meta"] = meta or {}
        return attrs


class WorkItemMoveSerializer(serializers.Serializer):
    to_status = serializers.ChoiceField(choices=WorkItem.Status.choices, required=False)
    to_position = serializers.IntegerField(min_value=1, required=False)

    def validate(self, attrs):
        if "to_status" not in attrs and "to_position" not in attrs:
            raise serializers.ValidationError("to_status hoặc to_position là bắt buộc")
        return attrs