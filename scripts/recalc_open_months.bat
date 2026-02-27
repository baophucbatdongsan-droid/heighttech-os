@echo off
cd /d C:\Users\Admin\Desktop\crm_height_tech
call venv\Scripts\activate

python manage.py recalc_shop_health_open_months --limit 12 --latest-if-none