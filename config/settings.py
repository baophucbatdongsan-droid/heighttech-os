
"""
Django settings for config project.
"""

from __future__ import annotations

from pathlib import Path

from decouple import Csv, config as env

# ==================================================
# PATHS
# ==================================================
BASE_DIR = Path(__file__).resolve().parent.parent

# ==================================================
# CORE
# ==================================================
SECRET_KEY = env("DJANGO_SECRET_KEY", default="django-insecure-change-me")
DEBUG = env("DJANGO_DEBUG", default=True, cast=bool)

ALLOWED_HOSTS: list[str] = env("DJANGO_ALLOWED_HOSTS", default="*", cast=Csv())

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ==================================================
# TENANT DEFAULT
# ==================================================
DEFAULT_TENANT_ID = env("DEFAULT_TENANT_ID", default=1, cast=int)
ALLOW_TENANT_HEADER = env("ALLOW_TENANT_HEADER", default=True, cast=bool)

# ==================================================
# AUTH
# ==================================================
AUTH_USER_MODEL = "accounts.User"
LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/os/"
LOGOUT_REDIRECT_URL = "/login/"

AUTHENTICATION_BACKENDS = [
    "apps.accounts.backends.EmailAuthBackend",
    "django.contrib.auth.backends.ModelBackend",
]
# ==================================================
# APPLICATIONS
# ==================================================
INSTALLED_APPS = [
    # Django core
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    # Foundation (tenant trước)
    "apps.tenants.apps.TenantsConfig",
    "apps.core.apps.CoreConfig",
    "apps.events.apps.EventsConfig",

    # Org / access
    "apps.accounts.apps.AccountsConfig",
    "apps.companies.apps.CompaniesConfig",
    "apps.clients.apps.ClientsConfig",

    # Business structure
    "apps.brands.apps.BrandsConfig",
    "apps.shops.apps.ShopsConfig",
    "apps.shop_services.apps.ShopServicesConfig",
    "apps.products.apps.ProductsConfig",

    # Domain
    "apps.projects.apps.ProjectsConfig",
    "apps.channels.apps.ChannelsConfig",
    "apps.booking.apps.BookingConfig",
    "apps.performance.apps.PerformanceConfig",
    "apps.finance.apps.FinanceConfig",
    "apps.intelligence.apps.IntelligenceConfig",
    "apps.work.apps.WorkConfig",
    "apps.contracts.apps.ContractsConfig",

    # Dashboard + Billing
    "apps.dashboard.apps.DashboardConfig",
    "apps.billing.apps.BillingConfig",

    # API
    "apps.api.apps.ApiConfig",

    # Third party
    "django_extensions",
    "rest_framework",
    "rest_framework.authtoken",
    "django_celery_beat",

    # Rules
    "apps.rules.apps.RulesConfig",

    "apps.sales.apps.SalesConfig",

    "apps.notifications.apps.NotificationsConfig",

    "apps.os.apps.OSConfig",
    "apps.finance_ledger.apps.FinanceLedgerConfig",


]

# ==================================================
# MIDDLEWARE (FINAL - KHÔNG TRÙNG, ĐÚNG THỨ TỰ)
# ==================================================
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",

    # 1) Resolve tenant trước
    "apps.tenants.middleware.TenantResolveMiddleware",

    # 2) Resolve actor/role (dựa trên user + tenant)
    "apps.core.middleware.ActorContextMiddleware",

    # 3) request_id/trace_id + tenant context + log/audit/quota...
    "apps.core.middleware.CurrentRequestMiddleware",

    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",

    # ✅ ONLY ONE workspace guard
    "apps.dashboard.middleware.WorkspaceRequiredMiddleware",
]

# ==================================================
# TEMPLATES
# ==================================================
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.core.context_processors.actor_context",
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
        "NAME": env("DB_NAME", default="heighttech"),
        "USER": env("DB_USER", default="heighttech_user"),
        "PASSWORD": env("DB_PASSWORD", default=""),
        "HOST": env("DB_HOST", default="127.0.0.1"),
        "PORT": env("DB_PORT", default="5432"),
        "CONN_MAX_AGE": env("DB_CONN_MAX_AGE", default=60, cast=int),
    }
}

# ==================================================
# I18N / TZ
# ==================================================
LANGUAGE_CODE = env("DJANGO_LANGUAGE_CODE", default="vi")
TIME_ZONE = env("DJANGO_TIME_ZONE", default="Asia/Ho_Chi_Minh")
USE_I18N = True
USE_TZ = True

# ==================================================
# STATIC
# ==================================================
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [
    BASE_DIR / "static",
]
# ==================================================
# SECURITY
# ==================================================
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = env("SESSION_COOKIE_SECURE", default=not DEBUG, cast=bool)
CSRF_COOKIE_SECURE = env("CSRF_COOKIE_SECURE", default=not DEBUG, cast=bool)

CSRF_TRUSTED_ORIGINS = env(
    "CSRF_TRUSTED_ORIGINS",
    default="https://app.heighttech.vn,https://api.heighttech.vn,https://staging.heighttech.vn",
    cast=Csv(),
)

# ==================================================
# CACHE (Redis)
# ==================================================
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": env("REDIS_CACHE_URL", default="redis://127.0.0.1:6379/1"),
        "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
        "TIMEOUT": env("CACHE_TIMEOUT", default=300, cast=int),
    }
}

# ==================================================
# CELERY
# ==================================================
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="redis://127.0.0.1:6379/2")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default="redis://127.0.0.1:6379/3")
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
        "user": env("DRF_USER_RATE", default="120/min"),
        "anon": env("DRF_ANON_RATE", default="30/min"),
    },
}

# ==================================================
# LOGGING
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
        "level": env("DJANGO_LOG_LEVEL", default="INFO"),
    },
    "loggers": {
        "api.audit": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
}

FOUNDER_ALERT_WEBHOOK = env("FOUNDER_ALERT_WEBHOOK", default="")