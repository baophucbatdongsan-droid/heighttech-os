"""
Django settings for config project.
(Compatible with Django 5.x / 6.x style)
"""

from __future__ import annotations

from pathlib import Path

# ==================================================
# PATHS
# ==================================================
BASE_DIR = Path(__file__).resolve().parent.parent

# ==================================================
# CORE
# ==================================================
SECRET_KEY = "django-insecure-change-me"
DEBUG = True
ALLOWED_HOSTS: list[str] = ["*"]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ==================================================
# TENANT DEFAULT
# ==================================================
DEFAULT_TENANT_ID = 1

# DEV: cho phép override tenant bằng header (X-Tenant-Id / X-Tenant)
# Prod muốn bật thì set True (hoặc bỏ dòng này để default False).
ALLOW_TENANT_HEADER = True

# ==================================================
# AUTH
# ==================================================
AUTH_USER_MODEL = "accounts.User"
LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/dashboard/"
LOGOUT_REDIRECT_URL = "/login/"

# ==================================================
# APPLICATIONS
# ==================================================
INSTALLED_APPS = [
    # --------------------------
    # DJANGO CORE
    # --------------------------
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    # --------------------------
    # FOUNDATION
    # --------------------------
    "apps.tenants.apps.TenantsConfig",  # phải đứng trước companies
    "apps.core.apps.CoreConfig",

    # --------------------------
    # ORG / ACCESS
    # --------------------------
    "apps.accounts.apps.AccountsConfig",
    "apps.companies.apps.CompaniesConfig",
    "apps.clients.apps.ClientsConfig",

    # --------------------------
    # BUSINESS STRUCTURE
    # --------------------------
    "apps.brands.apps.BrandsConfig",
    "apps.shops.apps.ShopsConfig",

    # --------------------------
    # DOMAIN
    # --------------------------
    "apps.projects.apps.ProjectsConfig",
    "apps.channels.apps.ChannelsConfig",
    "apps.booking.apps.BookingConfig",
    "apps.performance.apps.PerformanceConfig",
    "apps.finance.apps.FinanceConfig",
    "apps.intelligence.apps.IntelligenceConfig",
    "apps.work.apps.WorkConfig",

    # --------------------------
    # DASHBOARD + BILLING
    # --------------------------
    "apps.dashboard.apps.DashboardConfig",
    "apps.billing.apps.BillingConfig",

    # --------------------------
    # API
    # --------------------------
    "apps.api.apps.ApiConfig",

    # --------------------------
    # THIRD PARTY
    # --------------------------
    "django_extensions",
    "rest_framework",
    "rest_framework.authtoken",
    "django_celery_beat",

    "apps.rules.apps.RulesConfig",
]

# ==================================================
# MIDDLEWARE
# ==================================================
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",

    # ✅ resolve tenant trước
    "apps.tenants.middleware.TenantResolveMiddleware",

    # ✅ request_id/trace_id + tenant_context/audit/quota...
    "apps.core.middleware.CurrentRequestMiddleware",

    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
# ==================================================
# TEMPLATES
# ==================================================
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],  # nếu bạn có templates root thì add BASE_DIR / "templates"
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# ==================================================
# DATABASE
# ==================================================
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "heighttech",
        "USER": "heighttech_user",
        "PASSWORD": "@Haiphuc2001",
        "HOST": "127.0.0.1",
        "PORT": "5432",
    }
}

# ==================================================
# I18N / TZ
# ==================================================
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# ==================================================
# STATIC
# ==================================================
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# ==================================================
# CACHE (Redis)
# ==================================================
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": "redis://127.0.0.1:6379/1",
        "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
        "TIMEOUT": 300,
    }
}

# ==================================================
# CELERY
# ==================================================
CELERY_BROKER_URL = "redis://127.0.0.1:6379/2"
CELERY_RESULT_BACKEND = "redis://127.0.0.1:6379/3"
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"

# ==================================================
# DRF
# ==================================================
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.BasicAuthentication",
        # nếu dùng token:
        "rest_framework.authentication.TokenAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.UserRateThrottle",
        "rest_framework.throttling.AnonRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "user": "120/min",
        "anon": "30/min",
    },
}

# ==================================================
# LOGGING (Level 12)
# ==================================================
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "request_context": {"()": "apps.core.logging.RequestContextFilter"},
    },
    "formatters": {
        "json": {
            "class": "pythonjsonlogger.jsonlogger.JsonFormatter",
            "format": (
                "%(asctime)s %(levelname)s %(name)s %(message)s "
                "%(request_id)s %(trace_id)s %(tenant_id)s %(ip)s %(method)s %(path)s"
            ),
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "filters": ["request_context"],
            "formatter": "json",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "api.audit": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
}

# ==================================================
# OPTIONAL
# ==================================================
FOUNDER_ALERT_WEBHOOK = "https://...."