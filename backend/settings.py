"""
Django settings for PharmaERP project.

Environment-driven: use `.env` for local dev; for LAN/production testing set
DEBUG=False, explicit ALLOWED_HOSTS, CSRF_TRUSTED_ORIGINS, and a unique SECRET_KEY.
"""

from pathlib import Path
from dotenv import load_dotenv
from django.core.exceptions import ImproperlyConfigured

# ─── Base Directory ─────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent

import os
load_dotenv(BASE_DIR / '.env')


# ─── Security ───────────────────────────────────────────────────────────────

_DEV_SECRET_FALLBACK = 'django-pharma-erp-dev-secret-key-change-this'
SECRET_KEY = os.getenv('SECRET_KEY', _DEV_SECRET_FALLBACK)

DEBUG = os.getenv('DEBUG', 'True') == 'True'

_raw_hosts = os.getenv('ALLOWED_HOSTS', '*')
ALLOWED_HOSTS = [h.strip() for h in _raw_hosts.split(',') if h.strip()]

# Full origins (scheme + host[:port]) — required for POST/login from LAN URLs (Django 4+).
_csrf_raw = os.getenv('CSRF_TRUSTED_ORIGINS', '')
CSRF_TRUSTED_ORIGINS = [o.strip() for o in _csrf_raw.split(',') if o.strip()]

USE_TLS = os.getenv('USE_TLS', 'False') == 'True'
if USE_TLS:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_SSL_REDIRECT = os.getenv('SECURE_SSL_REDIRECT', 'True') == 'True'
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
else:
    SECURE_SSL_REDIRECT = False
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SECURE = False

_samesite = os.getenv('SESSION_COOKIE_SAMESITE', 'Lax').strip()
if _samesite in ('Lax', 'Strict', 'None'):
    SESSION_COOKIE_SAMESITE = _samesite
else:
    SESSION_COOKIE_SAMESITE = 'Lax'

if not DEBUG:
    if not ALLOWED_HOSTS or '*' in ALLOWED_HOSTS:
        raise ImproperlyConfigured(
            'When DEBUG=False, set ALLOWED_HOSTS to explicit hostnames or IPs '
            '(comma-separated). Wildcard * is not allowed.'
        )
    if SECRET_KEY == _DEV_SECRET_FALLBACK or not SECRET_KEY:
        raise ImproperlyConfigured(
            'When DEBUG=False, set a unique SECRET_KEY in the environment (not the dev default).'
        )
    if not CSRF_TRUSTED_ORIGINS:
        raise ImproperlyConfigured(
            'When DEBUG=False, set CSRF_TRUSTED_ORIGINS to every origin users use '
            '(comma-separated), e.g. http://192.168.1.50:8000,http://erp-server'
        )


# ─── Installed Apps ─────────────────────────────────────────────────────────
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    'users',
    'dashboard',
    'masters',
    'transactions',
    'admin_utils',
    'reports',
    'inventory',
]

# Printed / PDF report header (override via environment if needed).
REPORT_COMPANY_HEADER = os.getenv(
    'REPORT_COMPANY_HEADER',
    'RENUMED Pharmaceutical Labs.',
)

# Optional: list of strings (Factory / Godown lines) for Goods Receipt Note header.
# If unset, built-in defaults are used. Set to [] to hide address lines under the company name.
# GRN_RECEIPT_ADDRESS_LINES = []


# ─── Middleware ──────────────────────────────────────────────────────────────
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    # Full-request timing + structured logs (user id, not only IP). Must stay near the top.
    'backend.request_logging.RequestContextLoggingMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    # C3: redirects authenticated users with must_change_password=True to
    # /change-password/ before they can access any other page.
    'users.middleware.ForcePasswordChangeMiddleware',
    'users.access_middleware.ModuleAccessMiddleware',
]

ROOT_URLCONF = 'backend.urls'


# ─── Templates ──────────────────────────────────────────────────────────────
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'backend.context_processors.htmx_base',
                'users.context_processors.erp_access',
            ],
        },
    },
]

WSGI_APPLICATION = 'backend.wsgi.application'

try:
    _db_conn_max_age = int(os.getenv('DB_CONN_MAX_AGE', '60'))
except ValueError:
    _db_conn_max_age = 60


# ─── Database ────────────────────────────────────────────────────────────────
DATABASES = {
    'default': {
        'ENGINE':   'django.db.backends.mysql',
        'NAME':     os.getenv('DB_NAME'),
        'USER':     os.getenv('DB_USER'),
        'PASSWORD': os.getenv('DB_PASSWORD'),
        'HOST':     os.getenv('DB_HOST'),
        'PORT':     os.getenv('DB_PORT'),
        'OPTIONS': {
            'charset': 'utf8mb4',
            # M5: strict mode — MySQL raises an error instead of silently
            # truncating values that exceed a column's max_length.
            'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
        },
        # M5: reuse DB connections across requests instead of opening a new
        # TCP connection on every request.  60 seconds is a safe default.
        'CONN_MAX_AGE': _db_conn_max_age,
    }
}

# MySQL max_connections should exceed peak concurrent requests (default Waitress threads
# are sized for ~30–35 concurrent users; see README). Tune MySQL and WAITRESS_THREADS together.

# Log requests slower than this many milliseconds at WARNING (0 = disable).
try:
    SLOW_REQUEST_MS = int(os.getenv('SLOW_REQUEST_MS', '2000'))
except ValueError:
    SLOW_REQUEST_MS = 2000

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'pharmaerp_request': {
            'format': '{levelname} {asctime} {name} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'pharmaerp_request',
        },
    },
    'loggers': {
        'pharmaerp.request': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}


# ─── Password Validation ─────────────────────────────────────────────────────
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {'min_length': 8},
    },
]


# ─── Static Files (CSS, JS, Images) ─────────────────────────────────────────
STATIC_URL = '/static/'
MEDIA_URL  = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')
STATICFILES_DIRS = [BASE_DIR / 'static']
# C7: required by collectstatic for production deployments.
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Logical MySQL backups (mysqldump). See README "Database backups".
# Set DATABASE_BACKUP_DIR in .env to an absolute path (e.g. D:/Backups/PharmaERP or /var/backups/pharmaerp).
_backup_dir_env = (os.getenv('DATABASE_BACKUP_DIR') or '').strip()
if _backup_dir_env:
    DATABASE_BACKUP_DIR = Path(_backup_dir_env).expanduser().resolve()
else:
    DATABASE_BACKUP_DIR = (BASE_DIR / 'database_backups').resolve()
try:
    DATABASE_BACKUP_RETENTION = int(os.getenv('DATABASE_BACKUP_RETENTION', '30'))
except ValueError:
    DATABASE_BACKUP_RETENTION = 30
_mysql_dump = (os.getenv('MYSQLDUMP_PATH') or '').strip()
MYSQLDUMP_PATH = _mysql_dump or None
DATABASE_BACKUP_FILE_PREFIX = (os.getenv('DATABASE_BACKUP_FILE_PREFIX') or 'renumederp_').strip() or 'pharmaerp_'

# When True, a daemon thread in the web process checks Utilities → periodic backup settings
# periodically (see DATABASE_BACKUP_SCHEDULER_INTERVAL_SECONDS). Set False to rely only on
# Task Scheduler / cron running ``manage.py run_scheduled_backup``.
_DATABASE_BACKUP_BG = (os.getenv('DATABASE_BACKUP_BACKGROUND_SCHEDULER', 'True') or '').strip().lower()
DATABASE_BACKUP_BACKGROUND_SCHEDULER = _DATABASE_BACKUP_BG not in ('0', 'false', 'no', 'off')
try:
    DATABASE_BACKUP_SCHEDULER_INTERVAL_SECONDS = int(
        os.getenv('DATABASE_BACKUP_SCHEDULER_INTERVAL_SECONDS', '3600')
    )
except ValueError:
    DATABASE_BACKUP_SCHEDULER_INTERVAL_SECONDS = 3600

# Serve collected static files when DEBUG=False (LAN/production) without a separate nginx step.
WHITENOISE_USE_FINDERS = DEBUG


# ─── Login / Logout Redirects ────────────────────────────────────────────────
LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/dashboard/'
LOGOUT_REDIRECT_URL = '/login/'


# ─── Internationalisation ────────────────────────────────────────────────────
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Kolkata'
USE_I18N = True
USE_TZ = True

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'