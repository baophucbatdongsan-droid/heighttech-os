from datetime import timedelta
from django.utils import timezone

RULES = [

{
"id": "shop_no_order",
"title": "Shop không có đơn 24h",
"severity": "high",
"check": "shop_no_order"
},

{
"id": "task_overdue",
"title": "Task quá hạn",
"severity": "medium",
"check": "task_overdue"
},

]