# apps/api/v1/work/serializers.py
from __future__ import annotations

from typing import Any, Dict, List, Optional

from django.apps import apps
from rest_framework import serializers

from apps.core.permissions import ROLE_CLIENT, resolve_user_role
from apps.work.models import WorkItem
from apps.work.models_comment import WorkComment


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


def _clean_bool(v: Any) -> Optional[bool]:
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    if s in {"true", "1", "yes", "y", "on"}:
        return True
    if s in {"false", "0", "no", "n", "off"}:
        return False
    return None


def _clean_tags(v: Any) -> List[str]:
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


def _raw_manager(Model):
    """
    An toàn cho codebase có TenantManager scoping.
    Nếu có objects_all -> dùng objects_all.
    Fallback: _base_manager / objects.
    """
    if hasattr(Model, "objects_all"):
        return Model.objects_all
    if hasattr(Model, "_base_manager") and Model._base_manager is not None:
        return Model._base_manager
    return Model.objects


def _resolve_company_tenant_from_project(project_id: Optional[int]) -> Dict[str, Optional[int]]:
    if not project_id:
        return {"company_id": None, "tenant_id": None, "shop_id": None}

    Project = apps.get_model("projects", "Project")
    PM = _raw_manager(Project)

    # NOTE: project có shop_id hay không tùy codebase, nên getattr an toàn
    p = PM.filter(id=project_id).only("id", "company_id", "tenant_id").first()
    if not p:
        return {"company_id": None, "tenant_id": None, "shop_id": None}

    return {
        "company_id": getattr(p, "company_id", None),
        "tenant_id": getattr(p, "tenant_id", None),
        "shop_id": getattr(p, "shop_id", None),
    }


def _resolve_company_tenant_from_target(target_type: str, target_id: Optional[int]) -> Dict[str, Optional[int]]:
    tt = (target_type or "").strip().lower()
    tid = target_id
    if not tt or not tid:
        return {"company_id": None, "tenant_id": None, "shop_id": None}

    # shop
    if tt == "shop":
        try:
            Shop = apps.get_model("shops", "Shop")
            SM = _raw_manager(Shop)
            s = SM.filter(id=tid).only("id", "tenant_id").first()
            if s:
                return {"company_id": None, "tenant_id": getattr(s, "tenant_id", None), "shop_id": getattr(s, "id", None)}
        except Exception:
            pass

    # channel -> shop
    if tt == "channel":
        try:
            ChannelShopLink = apps.get_model("channels", "ChannelShopLink")
            Shop = apps.get_model("shops", "Shop")
            LM = _raw_manager(ChannelShopLink)
            SM = _raw_manager(Shop)

            link = LM.filter(channel_id=tid).only("shop_id").first()
            if link and getattr(link, "shop_id", None):
                s = SM.filter(id=link.shop_id).only("id", "tenant_id").first()
                if s:
                    return {"company_id": None, "tenant_id": getattr(s, "tenant_id", None), "shop_id": getattr(s, "id", None)}
        except Exception:
            pass

    # booking -> shop
    if tt == "booking":
        try:
            Booking = apps.get_model("booking", "Booking")
            Shop = apps.get_model("shops", "Shop")
            BM = _raw_manager(Booking)
            SM = _raw_manager(Shop)

            b = BM.filter(id=tid).only("shop_id").first()
            if b and getattr(b, "shop_id", None):
                s = SM.filter(id=b.shop_id).only("id", "tenant_id").first()
                if s:
                    return {"company_id": None, "tenant_id": getattr(s, "tenant_id", None), "shop_id": getattr(s, "id", None)}
        except Exception:
            pass

    return {"company_id": None, "tenant_id": None, "shop_id": None}


# =====================================================
# WorkItem Serializer (FINAL)
# =====================================================
class WorkItemSerializer(serializers.ModelSerializer):
    """
    FINAL:
    - Explicit *_id fields để DRF accept input chắc chắn
    - Expose *_username để FE render assignee/requester/created_by
    - Support Phase 2: shop_id, visible_to_client, type
    - Client bị giới hạn bởi visible_to_client + is_internal
    """

    # ✅ Explicit ID fields
    tenant_id = serializers.IntegerField(required=False, allow_null=True)
    company_id = serializers.IntegerField(required=False, allow_null=True)
    project_id = serializers.IntegerField(required=False, allow_null=True)
    shop_id = serializers.IntegerField(required=False, allow_null=True)

    created_by_id = serializers.IntegerField(required=False, allow_null=True)
    assignee_id = serializers.IntegerField(required=False, allow_null=True)
    requester_id = serializers.IntegerField(required=False, allow_null=True)

    target_id = serializers.IntegerField(required=False, allow_null=True)
    position = serializers.IntegerField(required=False, allow_null=True)

    # ✅ Phase 2
    visible_to_client = serializers.BooleanField(required=False)
    type = serializers.ChoiceField(choices=WorkItem.Type.choices, required=False)

    # tags
    tags = serializers.ListField(child=serializers.CharField(), required=False, allow_null=True)

    # ✅ usernames for UI
    assignee_username = serializers.CharField(source="assignee.username", read_only=True)
    requester_username = serializers.CharField(source="requester.username", read_only=True)
    created_by_username = serializers.CharField(source="created_by.username", read_only=True)

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
            "shop_id",
            "title",
            "description",
            "status",
            "priority",
            "position",
            "tags",
            "due_at",
            "started_at",
            "done_at",
            "type",
            "visible_to_client",
            "created_by_id",
            "assignee_id",
            "requester_id",
            "assignee_username",
            "requester_username",
            "created_by_username",
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
        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
            "assignee_username",
            "requester_username",
            "created_by_username",
            "role",
            "can_view",
            "can_comment",
            "can_edit",
            "can_move",
            "can_delete",
        ]

    # -------------------------
    # role + can_* helpers
    # -------------------------
    def _get_user_role(self) -> str:
        req = self.context.get("request")
        u = getattr(req, "user", None) if req else None
        return resolve_user_role(u)

    def get_role(self, obj: WorkItem) -> str:
        return self._get_user_role()

    def _client_can_see(self, obj: WorkItem) -> bool:
        if bool(getattr(obj, "is_internal", False)):
            return False
        return bool(getattr(obj, "visible_to_client", False))

    def get_can_view(self, obj: WorkItem) -> bool:
        if self._get_user_role() == ROLE_CLIENT:
            return self._client_can_see(obj)
        return True

    def get_can_comment(self, obj: WorkItem) -> bool:
        if self._get_user_role() == ROLE_CLIENT:
            return self._client_can_see(obj)
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
        for k in [
            "tenant_id",
            "company_id",
            "project_id",
            "shop_id",
            "created_by_id",
            "assignee_id",
            "requester_id",
            "target_id",
            "position",
        ]:
            if k in attrs:
                attrs[k] = _clean_int(attrs.get(k))

        # clean bool
        if "visible_to_client" in attrs:
            vb = _clean_bool(attrs.get("visible_to_client"))
            if vb is not None:
                attrs["visible_to_client"] = vb

        # clean tags
        if "tags" in attrs:
            attrs["tags"] = _clean_tags(attrs.get("tags"))

        company_id = attrs.get("company_id")
        tenant_id = attrs.get("tenant_id")
        project_id = attrs.get("project_id")
        shop_id = attrs.get("shop_id")

        # 1) project -> company/tenant/shop
        if project_id and (not company_id or not tenant_id or not shop_id):
            resolved = _resolve_company_tenant_from_project(project_id)
            if (not company_id) and resolved.get("company_id"):
                attrs["company_id"] = resolved["company_id"]
                company_id = attrs["company_id"]
            if (not tenant_id) and resolved.get("tenant_id"):
                attrs["tenant_id"] = resolved["tenant_id"]
                tenant_id = attrs["tenant_id"]
            if (not shop_id) and resolved.get("shop_id"):
                attrs["shop_id"] = resolved["shop_id"]
                shop_id = attrs["shop_id"]

        # 2) target -> tenant/shop (company có thể None)
        if (not tenant_id) or (not shop_id):
            tt = attrs.get("target_type") or ""
            tid = attrs.get("target_id")
            resolved = _resolve_company_tenant_from_target(tt, tid)
            if (not company_id) and resolved.get("company_id"):
                attrs["company_id"] = resolved["company_id"]
                company_id = attrs["company_id"]
            if (not tenant_id) and resolved.get("tenant_id"):
                attrs["tenant_id"] = resolved["tenant_id"]
                tenant_id = attrs["tenant_id"]
            if (not shop_id) and resolved.get("shop_id"):
                attrs["shop_id"] = resolved["shop_id"]
                shop_id = attrs["shop_id"]

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