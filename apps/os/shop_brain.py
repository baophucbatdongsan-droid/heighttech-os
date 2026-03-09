from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from django.utils import timezone

from apps.work.models import WorkItem


def _safe_import_order_model():
    try:
        m = __import__("apps.orders.models", fromlist=["Order"])
        return getattr(m, "Order")
    except Exception:
        return None


def _safe_import_product_model():
    try:
        m = __import__("apps.products.models", fromlist=["Product"])
        return getattr(m, "Product")
    except Exception:
        return None


Order = _safe_import_order_model()
Product = _safe_import_product_model()


@dataclass(frozen=True)
class ShopBrainResult:
    headline: Dict[str, Any]
    daily_mission: List[Dict[str, Any]]
    risks: List[Dict[str, Any]]
    growth: List[Dict[str, Any]]


def _safe_count(qs) -> int:
    try:
        return int(qs.count())
    except Exception:
        return 0


def build_shop_brain(
    *,
    tenant_id: int,
    shop_id: Optional[int] = None,
) -> ShopBrainResult:
    now = timezone.now()

    today_orders = 0
    pending_orders = 0
    cancelled_orders = 0
    low_stock = 0

    # =========================
    # Orders (nếu app tồn tại)
    # =========================
    if Order is not None:
        try:
            orders = Order.objects_all.filter(tenant_id=int(tenant_id))
        except Exception:
            try:
                orders = Order.objects.filter(tenant_id=int(tenant_id))
            except Exception:
                orders = None

        if orders is not None:
            if shop_id:
                try:
                    orders = orders.filter(shop_id=int(shop_id))
                except Exception:
                    pass

            try:
                today_orders = _safe_count(
                    orders.filter(created_at__date=now.date())
                )
            except Exception:
                today_orders = 0

            try:
                pending_orders = _safe_count(
                    orders.filter(status__in=["pending", "waiting_confirm"])
                )
            except Exception:
                pending_orders = 0

            try:
                cancelled_orders = _safe_count(
                    orders.filter(
                        status="cancelled",
                        created_at__gte=now - timezone.timedelta(days=1),
                    )
                )
            except Exception:
                cancelled_orders = 0

    # =========================
    # Products (nếu app tồn tại)
    # =========================
    if Product is not None:
        try:
            products = Product.objects_all.filter(tenant_id=int(tenant_id))
        except Exception:
            try:
                products = Product.objects.filter(tenant_id=int(tenant_id))
            except Exception:
                products = None

        if products is not None:
            if shop_id:
                try:
                    products = products.filter(shop_id=int(shop_id))
                except Exception:
                    pass

            try:
                low_stock = _safe_count(products.filter(stock__lt=10))
            except Exception:
                low_stock = 0

    # =========================
    # Work OS (luôn có)
    # =========================
    tasks = WorkItem.objects_all.filter(tenant_id=int(tenant_id))

    if shop_id:
        tasks = tasks.filter(shop_id=int(shop_id))

    tasks = tasks.exclude(
        status__in=[WorkItem.Status.DONE, WorkItem.Status.CANCELLED]
    )

    overdue_tasks = _safe_count(
        tasks.filter(due_at__isnull=False, due_at__lt=now)
    )

    urgent_tasks = _safe_count(
        tasks.filter(priority=WorkItem.Priority.URGENT)
    )

    open_tasks = _safe_count(tasks)

    # =========================
    # Daily Mission
    # =========================
    daily_mission: List[Dict[str, Any]] = []

    if pending_orders > 0:
        daily_mission.append(
            {
                "title": "Xử lý đơn hàng đang chờ",
                "summary": f"Có {pending_orders} đơn cần xác nhận.",
                "priority": "warning",
            }
        )

    if low_stock > 0:
        daily_mission.append(
            {
                "title": "Sản phẩm sắp hết hàng",
                "summary": f"Có {low_stock} sản phẩm tồn kho thấp.",
                "priority": "warning",
            }
        )

    if overdue_tasks > 0:
        daily_mission.append(
            {
                "title": "Task bị quá hạn",
                "summary": f"Có {overdue_tasks} công việc cần xử lý ngay.",
                "priority": "critical",
            }
        )

    if urgent_tasks > 0:
        daily_mission.append(
            {
                "title": "Có task gấp cần ưu tiên",
                "summary": f"Có {urgent_tasks} task mức độ gấp trong Work OS.",
                "priority": "critical",
            }
        )

    if not daily_mission:
        daily_mission.append(
            {
                "title": "Vận hành ổn định",
                "summary": "Hiện chưa có đầu việc nổi bật cần xử lý gấp.",
                "priority": "info",
            }
        )

    # =========================
    # Risks
    # =========================
    risks: List[Dict[str, Any]] = []

    if cancelled_orders > 5:
        risks.append(
            {
                "title": "Tỷ lệ hủy đơn tăng",
                "summary": f"Có {cancelled_orders} đơn bị hủy trong 24h gần nhất.",
                "priority": "warning",
            }
        )

    if overdue_tasks > 0:
        risks.append(
            {
                "title": "Backlog công việc đang nghẽn",
                "summary": f"Có {overdue_tasks} task quá hạn.",
                "priority": "critical",
            }
        )

    if low_stock > 0:
        risks.append(
            {
                "title": "Tồn kho thấp",
                "summary": f"Có {low_stock} sản phẩm sắp hết hàng.",
                "priority": "warning",
            }
        )

    # =========================
    # Growth Suggestions
    # =========================
    growth: List[Dict[str, Any]] = []

    if Order is not None and today_orders < 5:
        growth.append(
            {
                "title": "Traffic / đơn hôm nay đang thấp",
                "summary": "Nên tăng nội dung, livestream hoặc ads để kéo traffic.",
                "priority": "info",
            }
        )

    if low_stock > 0:
        growth.append(
            {
                "title": "Bổ sung hàng cho sản phẩm có tín hiệu bán",
                "summary": "Tránh mất doanh thu do sản phẩm hết hàng giữa chiến dịch.",
                "priority": "warning",
            }
        )

    if open_tasks < 3:
        growth.append(
            {
                "title": "Có thể đẩy thêm đầu việc tăng trưởng",
                "summary": "Hiện backlog chưa cao, có thể thêm task content / ads / CSKH.",
                "priority": "info",
            }
        )

    if not growth:
        growth.append(
            {
                "title": "Giữ nhịp tăng trưởng ổn định",
                "summary": "Tiếp tục bám sát nội dung, đơn hàng và phản hồi khách mỗi ngày.",
                "priority": "info",
            }
        )

    headline = {
        "today_orders": today_orders,
        "pending_orders": pending_orders,
        "low_stock": low_stock,
        "overdue_tasks": overdue_tasks,
        "urgent_tasks": urgent_tasks,
        "open_tasks": open_tasks,
    }

    return ShopBrainResult(
        headline=headline,
        daily_mission=daily_mission[:5],
        risks=risks[:5],
        growth=growth[:5],
    )