from __future__ import annotations


def decide_priority(content_row: dict) -> dict:
    """
    content_row expected:
    {
        "status": "...",
        "views_14d": 0,
        "orders_14d": 0,
        "ai": {
            "health_score": 0,
            "label": "...",
            "recommendation": "..."
        }
    }
    """

    status = str(content_row.get("status") or "").strip().lower()
    views = int(content_row.get("views_14d") or 0)
    orders = int(content_row.get("orders_14d") or 0)
    ai = content_row.get("ai") or {}
    health = int(ai.get("health_score") or 0)
    ai_label = str(ai.get("label") or "").strip().lower()

    # 1) content mạnh => scale ngay
    if health >= 80 and (views >= 3000 or orders >= 3):
        return {
            "priority_score": 95,
            "priority_label": "scale_now",
            "reason": "Content đang thắng rõ ràng.",
            "action_hint": "Nhân bản concept, làm biến thể hook, tăng tần suất đăng."
        }

    # 2) có script / đang sản xuất nhưng chưa air => ưu tiên sản xuất
    if status in ("script", "pre_production", "production", "post_production", "scheduled"):
        return {
            "priority_score": 88,
            "priority_label": "produce_now",
            "reason": "Content đã ở giữa pipeline nhưng chưa ra thị trường.",
            "action_hint": "Chốt quay, dựng, hậu kỳ và đẩy air sớm."
        }

    # 3) đã air nhưng yếu => sửa ngay
    if status == "aired" and (health < 45 or ai_label in ("weak", "weak-conversion", "no-data")):
        return {
            "priority_score": 82,
            "priority_label": "fix_now",
            "reason": "Content đã lên nhưng hiệu suất yếu hoặc chưa có tín hiệu tốt.",
            "action_hint": "Sửa hook 3 giây đầu, CTA, format và test lại."
        }

    # 4) aired trung bình => theo dõi
    if status == "aired":
        return {
            "priority_score": 58,
            "priority_label": "monitor",
            "reason": "Content đang ở mức trung bình.",
            "action_hint": "Theo dõi thêm 24-48h trước khi quyết định scale hay bỏ."
        }

    # 5) idea => chưa ưu tiên bằng content gần ra thị trường
    if status == "idea":
        return {
            "priority_score": 35,
            "priority_label": "backlog",
            "reason": "Mới ở giai đoạn ý tưởng.",
            "action_hint": "Giữ trong backlog, chỉ đẩy lên khi pipeline trống hoặc có tín hiệu trend."
        }

    return {
        "priority_score": 50,
        "priority_label": "monitor",
        "reason": "Chưa đủ tín hiệu mạnh.",
        "action_hint": "Theo dõi và cập nhật thêm dữ liệu."
    }