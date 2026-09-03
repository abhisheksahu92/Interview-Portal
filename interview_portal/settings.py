"""Django settings for Interview Portal v2.

All secrets/config come from the environment (see .env.example).
"""

import os
import sys
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
    SECRET_KEY=(str, "django-insecure-dev-only-change-me"),
    EMAIL_BACKEND=(str, "django.core.mail.backends.console.EmailBackend"),
    EMAIL_HOST=(str, "localhost"),
    EMAIL_PORT=(int, 25),
    EMAIL_HOST_USER=(str, ""),
    EMAIL_HOST_PASSWORD=(str, ""),
    EMAIL_USE_TLS=(bool, False),
    EMAIL_FILE_PATH=(str, ""),
    DEFAULT_FROM_EMAIL=(str, "no-reply@interview-portal.local"),
    ANTHROPIC_API_KEY=(str, ""),
    STRIPE_SECRET_KEY=(str, ""),
    STRIPE_PUBLISHABLE_KEY=(str, ""),
    STRIPE_WEBHOOK_SECRET=(str, ""),
    STRIPE_PRICE_ID_PRO=(str, ""),
    CSRF_TRUSTED_ORIGINS=(list, []),
    LOG_LEVEL=(str, "INFO"),
    DJANGO_LOG_LEVEL=(str, "INFO"),
    AWS_STORAGE_BUCKET_NAME=(str, ""),
    AWS_S3_REGION_NAME=(str, "auto"),
    AWS_S3_ENDPOINT_URL=(str, ""),
    AWS_ACCESS_KEY_ID=(str, ""),
    AWS_SECRET_ACCESS_KEY=(str, ""),
    # --- Phase 3 (monetization) integrations; blank = feature not configured.
    RAZORPAY_KEY_ID=(str, ""),
    RAZORPAY_KEY_SECRET=(str, ""),
    RAZORPAY_WEBHOOK_SECRET=(str, ""),
    WHATSAPP_TOKEN=(str, ""),
    WHATSAPP_PHONE_ID=(str, ""),
    GOOGLE_OAUTH_CLIENT_ID=(str, ""),
    GOOGLE_OAUTH_CLIENT_SECRET=(str, ""),
    MS_OAUTH_CLIENT_ID=(str, ""),
    MS_OAUTH_CLIENT_SECRET=(str, ""),
    COMPANY_GSTIN=(str, ""),
    COMPANY_STATE_CODE=(str, ""),
    SITE_URL=(str, "http://127.0.0.1:8000"),
)

environ.Env.read_env(BASE_DIR / ".env")

# True while running under pytest, so tests never depend on a collectstatic run.
TESTING = "PYTEST_VERSION" in os.environ or Path(sys.argv[0]).name.startswith("pytest")

SECRET_KEY = env("SECRET_KEY")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")

# --- Applications ---------------------------------------------------------
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework.authtoken",
    "drf_spectacular",
    "django_htmx",
    "crispy_forms",
    "crispy_bootstrap5",
]

LOCAL_APPS = [
    "core",
    "jobs",
    "assessments",
    "api",
    "web",
    "billing",
    "scheduling",
    "clients",
    "notifications",
    "talent",
    "video",
    "careers",
    "analytics",
    "offers",
    "partners",
    "marketplace",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
    "core.middleware.TenantMiddleware",
    "core.middleware.HtmxRedirectMiddleware",
]

ROOT_URLCONF = "interview_portal.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.tenant",
                "billing.context_processors.billing",
            ],
        },
    },
]

WSGI_APPLICATION = "interview_portal.wsgi.application"
ASGI_APPLICATION = "interview_portal.asgi.application"

# --- Database -------------------------------------------------------------
DATABASES = {
    "default": env.db_url(
        "DATABASE_URL",
        default=f"sqlite:///{BASE_DIR / 'db_v2.sqlite3'}",
    )
}

# Persistent connections: managed Postgres has a low connection cap, but
# CONN_MAX_AGE must stay 0 under pytest (it breaks test-database teardown).
DATABASES["default"]["CONN_MAX_AGE"] = env.int(
    "CONN_MAX_AGE", default=0 if (DEBUG or TESTING) else 60
)
DATABASES["default"]["CONN_HEALTH_CHECKS"] = not (DEBUG or TESTING)
if DATABASES["default"].get("ENGINE", "").endswith("postgresql"):
    DATABASES["default"].setdefault("OPTIONS", {}).setdefault("connect_timeout", 5)

# --- Auth -----------------------------------------------------------------
AUTH_USER_MODEL = "core.User"

# Single backend (a ModelBackend subclass) so email logins ignore case and
# ``auth_login`` after signup does not need an explicit backend argument.
AUTHENTICATION_BACKENDS = ["core.backends.CaseInsensitiveEmailBackend"]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "core:login"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "core:login"

# --- I18N -----------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# --- Static / media -------------------------------------------------------
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [d for d in [BASE_DIR / "static"] if d.is_dir()]

MEDIA_URL = "media/"
MEDIA_ROOT = Path(env.str("MEDIA_ROOT", default=str(BASE_DIR / "media")))

# Manifest hashing is only useful for a real collectstatic run; in DEBUG (and
# under pytest) templates must render without a staticfiles.json manifest.
_STATIC_BACKEND = (
    "whitenoise.storage.CompressedStaticFilesStorage"
    if DEBUG or TESTING
    else "whitenoise.storage.CompressedManifestStaticFilesStorage"
)

# WhiteNoise warns loudly when STATIC_ROOT is missing before the first
# collectstatic; the directory is gitignored, so just make sure it exists.
STATIC_ROOT.mkdir(parents=True, exist_ok=True)

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": _STATIC_BACKEND},
}

# Object storage for user uploads (resumes). Only active when a bucket is
# configured, so local dev and tests keep using the filesystem. Works with S3
# and Cloudflare R2 (AWS_S3_ENDPOINT_URL + AWS_S3_REGION_NAME=auto).
AWS_STORAGE_BUCKET_NAME = env("AWS_STORAGE_BUCKET_NAME")
if AWS_STORAGE_BUCKET_NAME:
    STORAGES["default"] = {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "bucket_name": AWS_STORAGE_BUCKET_NAME,
            "region_name": env("AWS_S3_REGION_NAME"),
            "endpoint_url": env("AWS_S3_ENDPOINT_URL") or None,
            "access_key": env("AWS_ACCESS_KEY_ID"),
            "secret_key": env("AWS_SECRET_ACCESS_KEY"),
            "default_acl": "private",
            "querystring_auth": True,  # resumes are served as signed URLs only
            "file_overwrite": False,
            "signature_version": "s3v4",
        },
    }

# Cap upload sizes (resumes are small documents).
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024

WHITENOISE_AUTOREFRESH = DEBUG or TESTING

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Email ----------------------------------------------------------------
EMAIL_BACKEND = env("EMAIL_BACKEND")
EMAIL_HOST = env("EMAIL_HOST")
EMAIL_PORT = env("EMAIL_PORT")
EMAIL_HOST_USER = env("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD")
EMAIL_USE_TLS = env("EMAIL_USE_TLS")
# Only used by django.core.mail.backends.filebased.EmailBackend.
EMAIL_FILE_PATH = env("EMAIL_FILE_PATH") or str(BASE_DIR / "sent_emails")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL")

# --- Third party ----------------------------------------------------------
CRISPY_ALLOWED_TEMPLATE_PACKS = "bootstrap5"
CRISPY_TEMPLATE_PACK = "bootstrap5"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        # Token first: it returns 401 (with WWW-Authenticate) for anonymous
        # calls, where SessionAuthentication would answer 403.
        "rest_framework.authentication.TokenAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 25,
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Interview Portal API",
    "DESCRIPTION": "Multi-tenant hiring platform API",
    "VERSION": "2.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    # jobs.PipelineStage.kind and assessments.Question.kind are unrelated enums
    # that happen to share a field name; name them explicitly.
    "ENUM_NAME_OVERRIDES": {
        "PipelineStageKindEnum": "jobs.models.PipelineStage.KIND_CHOICES",
        "QuestionKindEnum": "assessments.models.Question.KIND_CHOICES",
    },
}

# --- AI -------------------------------------------------------------------
ANTHROPIC_API_KEY = env("ANTHROPIC_API_KEY")

# --- Billing (Stripe) -----------------------------------------------------
STRIPE_SECRET_KEY = env("STRIPE_SECRET_KEY")
STRIPE_PUBLISHABLE_KEY = env("STRIPE_PUBLISHABLE_KEY")
STRIPE_WEBHOOK_SECRET = env("STRIPE_WEBHOOK_SECRET")
STRIPE_PRICE_ID_PRO = env("STRIPE_PRICE_ID_PRO")

# --- Billing (Razorpay, India) -------------------------------------------
RAZORPAY_KEY_ID = env("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = env("RAZORPAY_KEY_SECRET")
RAZORPAY_WEBHOOK_SECRET = env("RAZORPAY_WEBHOOK_SECRET")

# GST details printed on invoices.
COMPANY_GSTIN = env("COMPANY_GSTIN")
COMPANY_STATE_CODE = env("COMPANY_STATE_CODE")

# --- Notifications (WhatsApp Business Cloud API) --------------------------
WHATSAPP_TOKEN = env("WHATSAPP_TOKEN")
WHATSAPP_PHONE_ID = env("WHATSAPP_PHONE_ID")

# --- Calendar OAuth (scheduling) -----------------------------------------
GOOGLE_OAUTH_CLIENT_ID = env("GOOGLE_OAUTH_CLIENT_ID")
GOOGLE_OAUTH_CLIENT_SECRET = env("GOOGLE_OAUTH_CLIENT_SECRET")
MS_OAUTH_CLIENT_ID = env("MS_OAUTH_CLIENT_ID")
MS_OAUTH_CLIENT_SECRET = env("MS_OAUTH_CLIENT_SECRET")

# Absolute base URL used in emails, .ics files, careers pages and share links.
SITE_URL = env("SITE_URL").rstrip("/")


# --- Security / proxy -----------------------------------------------------
# Fly.io and Railway terminate TLS at the edge and forward plain HTTP.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True

SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=not (DEBUG or TESTING))
SECURE_REDIRECT_EXEMPT = [r"^healthz/$"]

SESSION_COOKIE_SECURE = not (DEBUG or TESTING)
CSRF_COOKIE_SECURE = not (DEBUG or TESTING)
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False  # HTMX reads the CSRF token from the cookie
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True

# Must include the scheme, e.g. https://interview-portal.fly.dev
CSRF_TRUSTED_ORIGINS = env("CSRF_TRUSTED_ORIGINS")

SECURE_HSTS_SECONDS = env.int(
    "SECURE_HSTS_SECONDS", default=0 if (DEBUG or TESTING) else 31536000
)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# --- Logging (containers collect stdout/stderr) ---------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "verbose"},
    },
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL")},
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": env("DJANGO_LOG_LEVEL"),
            "propagate": False,
        },
        "django.request": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        # assessments.ai logs when ANTHROPIC_API_KEY is missing — keep it visible.
        "assessments": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "billing": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
}
