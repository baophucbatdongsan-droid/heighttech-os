from __future__ import annotations

from decimal import Decimal


def _to_decimal(v):
    try:
        return Decimal(str(v or 0))
    except Exception:
        return Decimal("0")


def score_content(metrics: list[dict]) -> dict:
    """
    Deterministic scoring v1
    Input:
      metrics = [
        {
          "views": 1000,
          "likes": 50,
          "comments": 10,
          "shares": 5,
          "orders": 2,
          "revenue": "300000"
        }
      ]
    """

    if not metrics:
        return {
            "health_score": 0,
            "risk_level": "high",
            "label": "no-data",
            "recommendation": "Chưa có dữ liệu. Cần đăng video và theo dõi 24-48h đầu."
        }

    total_views = sum(int(x.get("views") or 0) for x in metrics)
    total_likes = sum(int(x.get("likes") or 0) for x in metrics)
    total_comments = sum(int(x.get("comments") or 0) for x in metrics)
    total_shares = sum(int(x.get("shares") or 0) for x in metrics)
    total_orders = sum(int(x.get("orders") or 0) for x in metrics)
    total_revenue = sum(_to_decimal(x.get("revenue")) for x in metrics)

    if total_views <= 0:
        return {
            "health_score": 5,
            "risk_level": "high",
            "label": "no-data",
            "recommendation": "Video chưa có view. Kiểm tra lịch đăng, hook và phân phối ban đầu."
        }

    like_rate = (total_likes / total_views) * 100
    comment_rate = (total_comments / total_views) * 100
    share_rate = (total_shares / total_views) * 100
    order_rate = (total_orders / total_views) * 100

    score = 0

    # view base
    if total_views >= 50000:
        score += 25
    elif total_views >= 10000:
        score += 18
    elif total_views >= 3000:
        score += 12
    elif total_views >= 1000:
        score += 8
    else:
        score += 3

    # engagement
    if like_rate >= 8:
        score += 18
    elif like_rate >= 5:
        score += 12
    elif like_rate >= 3:
        score += 8
    else:
        score += 2

    if comment_rate >= 1:
        score += 10
    elif comment_rate >= 0.4:
        score += 6
    else:
        score += 2

    if share_rate >= 0.8:
        score += 16
    elif share_rate >= 0.3:
        score += 10
    else:
        score += 2

    # conversion
    if order_rate >= 1:
        score += 18
    elif order_rate >= 0.3:
        score += 10
    elif total_orders > 0:
        score += 5
    else:
        score += 1

    if total_revenue >= Decimal("10000000"):
        score += 13
    elif total_revenue >= Decimal("3000000"):
        score += 9
    elif total_revenue > 0:
        score += 5
    else:
        score += 1

    if score > 100:
        score = 100

    # label + recommendation
    if score >= 80:
        return {
            "health_score": score,
            "risk_level": "low",
            "label": "boostable",
            "recommendation": "Video đang mạnh. Nên nhân bản concept, tăng phân phối và làm tiếp biến thể nội dung."
        }

    if score >= 55:
        return {
            "health_score": score,
            "risk_level": "medium",
            "label": "normal",
            "recommendation": "Video ổn. Theo dõi thêm 1-2 ngày, tối ưu CTA và caption để tăng chuyển đổi."
        }

    if share_rate >= 0.5 and order_rate < 0.1:
        return {
            "health_score": score,
            "risk_level": "medium",
            "label": "weak-conversion",
            "recommendation": "Nội dung có tính lan truyền nhưng chuyển đổi yếu. Cần sửa CTA, offer hoặc link sản phẩm."
        }

    return {
        "health_score": score,
        "risk_level": "high",
        "label": "weak",
        "recommendation": "Video đang yếu. Nên thay hook 3 giây đầu, chỉnh nội dung và test lại khung giờ đăng."
    }