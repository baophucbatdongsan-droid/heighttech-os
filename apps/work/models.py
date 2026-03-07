# apps/work/models.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, models, transaction
from django.utils import timezone

from apps.core.managers import TenantAllManager, TenantManager
from apps.work.engine import WorkflowEngine

# Event bus (outbox)
from apps.events.bus import emit_event, make_dedupe_key


def _raw_manager(Model):
    if hasattr(Model, "_base_manager") and Model._base_manager is not None:
        return Model._base_manager
    return Model.objects


@dataclass(frozen=True)
class WorkItemGuardResult:
    ok: bool
    reason: str = ""


def _project_status_value(p) -> str:
    if p is None:
        return ""
    v = getattr(p, "status", "")
    if v is None:
        return ""
    if hasattr(v, "value"):
        return str(v.value)
    return str(v)


def _project_allows_work_mutation(project) -> WorkItemGuardResult:
    if project is None:
        return WorkItemGuardResult(True)

    st = _project_status_value(project).lower().strip()
    if st == "active":
        return WorkItemGuardResult(True)

    if st in {"paused", "done", "inactive", "archived"}:
        return WorkItemGuardResult(False, f"Project is '{st}', transition locked.")

    return WorkItemGuardResult(False, f"Project status '{st}' not allowed.")


def _parse_rule_version_to_int(v) -> int:
    """
    Support: 1, "1", "v1", "V2", None
    Fallback -> 1
    """
    try:
        if v is None:
            return 1
        s = str(v).strip()
        if not s:
            return 1
        if s.lower().startswith("v"):
            s = s[1:].strip()
        n = int(s)
        return n if n > 0 else 1
    except Exception:
        return 1


def _recalc_project_metrics(project_id: int) -> None:
    if not project_id:
        return

    from apps.projects.models import Project

    project = Project.objects.filter(id=project_id).first()
    if not project:
        return

    qs = WorkItem.objects.filter(project_id=project.id)

    total = qs.exclude(status=WorkItem.Status.CANCELLED).count()
    done = qs.filter(status=WorkItem.Status.DONE).count()

    progress = int(round((done / total) * 100)) if total > 0 else 0

    now = timezone.now()
    overdue = (
        qs.filter(due_at__isnull=False, due_at__lt=now)
        .exclude(status__in=[WorkItem.Status.DONE, WorkItem.Status.CANCELLED])
        .count()
    )

    penalty = min(50, overdue * 5)
    health = max(0, 100 - penalty)

    if hasattr(project, "progress_percent"):
        project.progress_percent = progress
    if hasattr(project, "health_score"):
        project.health_score = health
    if hasattr(project, "last_activity_at"):
        project.last_activity_at = now

    update_fields = []
    for f in ("progress_percent", "health_score", "last_activity_at", "updated_at"):
        if hasattr(project, f):
            update_fields.append(f)

    project.save(update_fields=update_fields or None)


class WorkItem(models.Model):
    class Status(models.TextChoices):
        TODO = "todo", "Todo"
        DOING = "doing", "Doing"
        BLOCKED = "blocked", "Blocked"
        DONE = "done", "Done"
        CANCELLED = "cancelled", "Cancelled"

    class Priority(models.IntegerChoices):
        LOW = 1, "Low"
        NORMAL = 2, "Normal"
        HIGH = 3, "High"
        URGENT = 4, "Urgent"

    class Type(models.TextChoices):
        TASK = "task", "Task"
        BUG = "bug", "Bug"
        CAMPAIGN = "campaign", "Campaign"
        REPORT = "report", "Report"

    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, db_index=True)

    company = models.ForeignKey("companies.Company", null=True, blank=True, on_delete=models.SET_NULL, db_index=True)

    # ✅ company_key: dùng cho UNIQUE rank khi company NULL (NULL -> 0)
    # Tránh dùng UniqueConstraint(expressions=...) vì Django version của anh không hỗ trợ.
    company_key = models.PositiveIntegerField(default=0, db_index=True)

    project = models.ForeignKey("projects.Project", null=True, blank=True, on_delete=models.SET_NULL, db_index=True)

    # Phase 2: task theo workspace Shop (nullable)
    shop = models.ForeignKey(
        "shops.Shop",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        db_index=True,
        related_name="work_items",
    )

    # Client portal visibility
    visible_to_client = models.BooleanField(default=False, db_index=True)

    # Type: task/bug/campaign/report
    type = models.CharField(max_length=20, choices=Type.choices, default=Type.TASK, db_index=True)

    # generic target (optional)
    target_type = models.CharField(max_length=50, blank=True, default="", db_index=True)
    target_id = models.PositiveIntegerField(null=True, blank=True, db_index=True)

    title = models.CharField(max_length=255, db_index=True)
    description = models.TextField(blank=True, default="")

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.TODO, db_index=True)

    workflow_version = models.PositiveIntegerField(
        default=1,
        db_index=True,
        help_text="Workflow version frozen at creation time",
    )

    priority = models.PositiveSmallIntegerField(choices=Priority.choices, default=Priority.NORMAL, db_index=True)

    # rank is ordering source of truth (lexicographic ASC)
    rank = models.CharField(max_length=32, blank=True, default="", db_index=True)

    # derived/display position (optional), maintained by services_move
    position = models.PositiveIntegerField(default=1, db_index=True)

    due_at = models.DateTimeField(null=True, blank=True, db_index=True)
    started_at = models.DateTimeField(null=True, blank=True)
    done_at = models.DateTimeField(null=True, blank=True, db_index=True)

    is_internal = models.BooleanField(default=False, db_index=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="work_items_created",
    )
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="work_items_assigned",
    )
    requester = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="work_items_requested",
    )

    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    objects = TenantManager()
    objects_all = TenantAllManager()

    class Meta:
        ordering = ["-id"]
        indexes = [
            models.Index(fields=["tenant", "status"], name="wi_t_st_idx"),
            models.Index(fields=["tenant", "priority"], name="wi_t_pri_idx"),
            models.Index(fields=["tenant", "company"], name="wi_t_co_idx"),
            models.Index(fields=["tenant", "project"], name="wi_t_pj_idx"),
            models.Index(fields=["tenant", "target_type", "target_id"], name="wi_t_tg_idx"),
            models.Index(fields=["tenant", "company", "status", "rank"], name="wi_t_c_sr_idx"),
            models.Index(fields=["tenant", "is_internal"], name="wi_t_int_idx"),
            models.Index(fields=["tenant", "workflow_version"], name="wi_t_wfv_idx"),
            # Phase 2 indexes
            models.Index(fields=["tenant", "shop"], name="wi_t_shop_idx"),
            models.Index(fields=["tenant", "shop", "status", "rank"], name="wi_t_shop_sr_idx"),
            models.Index(fields=["tenant", "shop", "visible_to_client"], name="wi_t_shop_vtc_idx"),
            models.Index(fields=["tenant", "type"], name="wi_t_type_idx"),
            # ✅ company_key index for uniqueness grouping
            models.Index(fields=["tenant", "company_key", "status", "rank"], name="wi_t_ck_sr_idx"),
        ]
        constraints = [
            # ✅ Compatible UNIQUE (no expressions=)
            models.UniqueConstraint(
                fields=["tenant", "company_key", "status", "rank"],
                name="uq_wi_tenant_companykey_status_rank",
            ),
            models.CheckConstraint(check=models.Q(position__gte=1), name="ck_wi_position_gte_1"),
        ]

    # --------------------------
    # Workflow version helpers
    # --------------------------
    def _resolve_workflow_version(self) -> int:
        """
        ưu tiên project.shop.rule_version (Shop.rule_version: 'v1'/'1')
        """
        try:
            if self.project and hasattr(self.project, "shop") and self.project.shop:
                return _parse_rule_version_to_int(getattr(self.project.shop, "rule_version", None))
        except Exception:
            pass
        return 1

    def _workflow_version_exists(self, version: int) -> bool:
        try:
            from apps.work.engine.workflow_registry import registry

            registry.require("workitem", int(version))
            return True
        except Exception:
            return False

    def _effective_workflow_version(self) -> int:
        v = int(self.workflow_version or 1)
        if v <= 0:
            v = 1
        return v if self._workflow_version_exists(v) else 1

    # --------------------------
    # Rank assignment (safety net)
    # --------------------------
    def _ensure_rank_on_create(self) -> None:
        """
        Safety net: nếu create không qua services_move, auto assign rank bottom.
        """
        if (self.rank or "").strip():
            return

        from apps.work.services_move import _lock_column, _rank_for_pos, _rebuild_ranks_for_column

        tenant_id = int(self.tenant_id)
        company_id = self.company_id  # can be None
        st = (self.status or "todo").strip().lower() or "todo"

        _lock_column(tenant_id=tenant_id, company_id=int(company_id or 0), status=st)

        qs = WorkItem.objects_all.filter(tenant_id=tenant_id, company_id=company_id, status=st)

        has_blank = qs.filter(models.Q(rank__isnull=True) | models.Q(rank="")).exists()
        if has_blank:
            ids = list(qs.order_by("rank", "id").values_list("id", flat=True))
            _rebuild_ranks_for_column(
                tenant_id=tenant_id,
                company_id=company_id,
                status=st,
                ordered_ids=ids,
            )
            qs = WorkItem.objects_all.filter(tenant_id=tenant_id, company_id=company_id, status=st)

        n = qs.count()
        self.rank = _rank_for_pos(n + 1)

    # --------------------------
    # Transition
    # --------------------------
    def transition_to(self, new_status: str, *, actor=None, note: str = "") -> None:
        new_status = str(new_status).strip().lower()
        old_status = str(self.status).strip().lower()

        version = self._effective_workflow_version()
        engine = WorkflowEngine("workitem")
        engine.ensure(version=version, from_state=old_status, to_state=new_status)

        guard = _project_allows_work_mutation(self.project)
        if not guard.ok:
            raise ValidationError(guard.reason)

        safe_actor = actor if getattr(actor, "is_authenticated", False) and getattr(actor, "pk", None) else None

        from apps.work.services_move import move_work_item  # local import

        with transaction.atomic():
            move_work_item(
                tenant_id=self.tenant_id,
                item_id=self.id,
                to_status=new_status,
                to_position=None,
            )

            self.refresh_from_db(fields=["status", "rank", "position", "started_at", "done_at"])

            now = timezone.now()
            upd = set()

            if self.status == self.Status.DOING and not self.started_at:
                self.started_at = now
                upd.add("started_at")

            if self.status in (self.Status.DONE, self.Status.CANCELLED) and not self.done_at:
                self.done_at = now
                upd.add("done_at")

            if self.status not in (self.Status.DONE, self.Status.CANCELLED) and self.done_at is not None:
                self.done_at = None
                upd.add("done_at")

            if upd:
                super().save(update_fields=list(upd) + ["updated_at"])

            WorkComment.objects.create(
                tenant_id=self.tenant_id,
                work_item_id=self.id,
                actor=safe_actor,
                body=note or f"Transition {old_status} → {new_status}",
                meta={"event": "transition", "from": old_status, "to": new_status, "workflow_version": version},
            )

            WorkItemTransitionLog.objects.create(
                tenant_id=self.tenant_id,
                company_id=self.company_id,
                project_id=self.project_id,
                workitem_id=self.id,
                from_status=old_status,
                to_status=new_status,
                actor=safe_actor,
                reason=note or "",
                workflow_version=version,
                request_id="",
                trace_id="",
            )

            if self.project_id:
                _recalc_project_metrics(self.project_id)

            # ✅ Emit transition event AFTER COMMIT
            try:
                payload = {
                    "id": self.id,
                    "tenant_id": self.tenant_id,
                    "company_id": self.company_id,
                    "project_id": self.project_id,
                    "shop_id": getattr(self, "shop_id", None),
                    "from_status": old_status,
                    "to_status": new_status,
                    "workflow_version": int(version or 1),
                }
                dedupe = make_dedupe_key(
                    name="work.item.transitioned",
                    tenant_id=self.tenant_id,
                    entity="workitem",
                    entity_id=self.id,
                    extra={"from": old_status, "to": new_status, "workflow_version": str(version)},
                )

                def _emit():
                    emit_event(
                        tenant_id=self.tenant_id,
                        company_id=self.company_id,
                        shop_id=getattr(self, "shop_id", None),
                        actor_id=getattr(safe_actor, "id", None),
                        name="work.item.transitioned",
                        version=1,
                        dedupe_key=dedupe,
                        payload=payload,
                    )

                transaction.on_commit(_emit)
            except Exception:
                pass

    # --------------------------
    # Save Override
    # --------------------------
    def save(self, *args, **kwargs):
        """
        FINAL:
        - CREATE path: outer atomic + inner atomic(savepoint) retry IntegrityError
        - Rank assignment safety net
        - Metrics recalculation
        - Emit Outbox event via transaction.on_commit() (safe, no phantom events)
        - Updated event: chỉ bắn khi thay đổi "meaningful"
        """
        M = _raw_manager(WorkItem)

        old_status = None
        old_due = None
        old_priority = None
        old_title = None
        old_assignee_id = None
        old_requester_id = None
        old_is_internal = None
        old_visible = None

        is_create = not bool(self.pk)

        if self.pk:
            try:
                old = M.get(pk=self.pk)
                old_status = (old.status or "").strip().lower()
                old_due = old.due_at
                old_priority = getattr(old, "priority", None)
                old_title = getattr(old, "title", None)
                old_assignee_id = getattr(old, "assignee_id", None)
                old_requester_id = getattr(old, "requester_id", None)
                old_is_internal = getattr(old, "is_internal", None)
                old_visible = getattr(old, "visible_to_client", None)
            except WorkItem.DoesNotExist:
                pass

        # freeze workflow_version on create
        if not self.pk:
            v = int(self.workflow_version or 1)
            if v <= 0:
                v = 1
            if v == 1:
                v = int(self._resolve_workflow_version() or 1)
            if not self._workflow_version_exists(v):
                v = 1
            self.workflow_version = v

        # normalize status
        self.status = (self.status or "").strip().lower() or self.Status.TODO

        # ✅ normalize company_key (NULL -> 0) for UNIQUE constraint
        try:
            self.company_key = int(self.company_id or 0)
        except Exception:
            self.company_key = 0

        # position safety
        try:
            p = int(self.position or 0)
        except Exception:
            p = 0
        if p < 1:
            self.position = 1

        # timestamps
        now = timezone.now()
        if self.status == self.Status.DOING and not self.started_at:
            self.started_at = now
        if self.status in (self.Status.DONE, self.Status.CANCELLED) and not self.done_at:
            self.done_at = now
        if self.status not in (self.Status.DONE, self.Status.CANCELLED):
            self.done_at = None

        # do save
        if not self.pk:
            with transaction.atomic():
                if not (self.rank or "").strip():
                    self._ensure_rank_on_create()

                for attempt in range(6):
                    try:
                        with transaction.atomic():
                            super().save(*args, **kwargs)
                        break
                    except IntegrityError:
                        if attempt >= 5:
                            raise
                        self.rank = ""
                        self._ensure_rank_on_create()
        else:
            super().save(*args, **kwargs)

        # metrics (only when status/due changed)
        if self.project_id and ((old_status or "") != (self.status or "") or old_due != self.due_at):
            try:
                _recalc_project_metrics(self.project_id)
            except Exception:
                pass

        # =========================
        # OUTBOX EVENT (SAFE)
        # =========================
        try:
            # only emit updated if meaningful change
            if is_create:
                event_name: Optional[str] = "work.item.created"
            else:
                meaningful = any(
                    [
                        (old_status or "") != (self.status or ""),
                        old_due != self.due_at,
                        (old_priority != getattr(self, "priority", None)),
                        (old_title != getattr(self, "title", None)),
                        (old_assignee_id != getattr(self, "assignee_id", None)),
                        (old_requester_id != getattr(self, "requester_id", None)),
                        (old_is_internal != getattr(self, "is_internal", None)),
                        (old_visible != getattr(self, "visible_to_client", None)),
                    ]
                )
                event_name = "work.item.updated" if meaningful else None

            if not event_name:
                return

            actor_id = getattr(getattr(self, "_actor", None), "id", None)

            payload: Dict[str, Any] = {
                "id": self.id,
                "tenant_id": self.tenant_id,
                "company_id": self.company_id,
                "project_id": self.project_id,
                "shop_id": getattr(self, "shop_id", None),
                "status": self.status,
                "priority": int(self.priority or 0),
                "title": self.title,
                "is_internal": bool(self.is_internal),
                "visible_to_client": bool(getattr(self, "visible_to_client", False)),
                "assignee_id": getattr(self, "assignee_id", None),
                "requester_id": getattr(self, "requester_id", None),
                "updated_at": self.updated_at.isoformat() if getattr(self, "updated_at", None) else "",
            }

            dedupe = make_dedupe_key(
                name=event_name,
                tenant_id=self.tenant_id,
                entity="workitem",
                entity_id=self.id,
                extra={"status": self.status, "updated_at": payload.get("updated_at", "")},
            )

            def _emit():
                emit_event(
                    tenant_id=self.tenant_id,
                    company_id=self.company_id,
                    shop_id=getattr(self, "shop_id", None),
                    actor_id=actor_id,
                    name=event_name,
                    version=1,
                    dedupe_key=dedupe,
                    payload=payload,
                )

            transaction.on_commit(_emit)
        except Exception:
            pass

    def __str__(self) -> str:
        return f"[{self.status}] {self.title}"


class WorkComment(models.Model):
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, db_index=True)
    work_item = models.ForeignKey("work.WorkItem", on_delete=models.CASCADE, related_name="comments", db_index=True)

    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)

    body = models.TextField(blank=True, default="")
    meta = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    objects = TenantManager()
    objects_all = TenantAllManager()

    class Meta:
        ordering = ["-id"]
        indexes = [
            models.Index(fields=["tenant", "work_item"], name="wc_t_wi_idx"),
            models.Index(fields=["tenant", "created_at"], name="wc_t_ct_idx"),
        ]

    def __str__(self) -> str:
        return f"Comment#{self.pk} item={self.work_item_id}"


class WorkItemTransitionLog(models.Model):
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, db_index=True)
    company = models.ForeignKey("companies.Company", null=True, blank=True, on_delete=models.SET_NULL, db_index=True)
    project = models.ForeignKey("projects.Project", null=True, blank=True, on_delete=models.SET_NULL, db_index=True)
    workitem = models.ForeignKey(
        "work.WorkItem", on_delete=models.CASCADE, related_name="transition_logs", db_index=True
    )

    from_status = models.CharField(max_length=50)
    to_status = models.CharField(max_length=50)

    workflow_version = models.PositiveIntegerField(default=1, db_index=True)

    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    reason = models.TextField(blank=True, default="")

    request_id = models.CharField(max_length=64, blank=True, default="")
    trace_id = models.CharField(max_length=64, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    # ✅ QUAN TRỌNG: thêm managers cho timeline_engine dùng objects_all
    objects = TenantManager()
    objects_all = TenantAllManager()

    class Meta:
        ordering = ["-id"]
        indexes = [
            models.Index(fields=["tenant", "company", "project", "workitem", "created_at"], name="wlt_t_c_p_w_ct_idx"),
            models.Index(fields=["tenant", "workflow_version", "created_at"], name="wlt_t_wfv_ct_idx"),
        ]

    def __str__(self) -> str:
        return f"TransitionLog#{self.pk} wi={self.workitem_id} {self.from_status}->{self.to_status}"