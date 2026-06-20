"""
Django settings for Wildlife_Tracking_System project.
"""

from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent

# ─── SECURITY ───
SECRET_KEY = os.environ.get(
    'SECRET_KEY',
    'django-insecure-CHANGE-THIS-IN-PRODUCTION-abcdefghijklmnopqrstuvwxyz123456789'
)

# Set False in production
DEBUG = os.environ.get('DEBUG', 'False').lower() == 'true'

# ─── RAILWAY PROXY FIX ───
# Railway sits between the browser and Django. It sends HTTPS requests to the
# browser but HTTP internally. These settings tell Django to trust Railway's
# headers so it knows the original request was HTTPS.
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = True

# ─── ALLOWED HOSTS ───
# NEVER use '*' in production. It breaks CSRF origin checking.
ALLOWED_HOSTS = [
    'traceit-web.up.railway.app',
    'localhost',
    '127.0.0.1',
]

# ─── CSRF TRUSTED ORIGINS ───
# Must be HTTPS only in production. Must match your exact domain.
CSRF_TRUSTED_ORIGINS = [
    'https://traceit-web.up.railway.app',
    'https://localhost',
    'http://localhost',
]

# ─── CSRF COOKIE SETTINGS ───
# These fix issues where CSRF cookie isn't sent properly behind proxy
CSRF_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_HTTPONLY = False  # Must be False so JS can read it for AJAX
CSRF_USE_SESSIONS = False     # Use separate CSRF cookie (not session)

# ─── SESSION COOKIE SETTINGS ───
SESSION_COOKIE_SAMESITE = 'Lax'

# ─── AUTH REDIRECTS ───
LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/'

# ─── APPLICATIONS ───
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
    'Trace_It',
]

# ─── MIDDLEWARE ───
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'Wildlife_Tracking_System.urls'

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
            ],
        },
    },
]

WSGI_APPLICATION = 'Wildlife_Tracking_System.wsgi.application'

# ─── DATABASE ───
DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL:
    import dj_database_url
    DATABASES = {
        'default': dj_database_url.parse(DATABASE_URL)
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

# ─── PASSWORD VALIDATION ───
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# ─── INTERNATIONALIZATION ───
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# ─── STATIC FILES ───
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATICFILES_STORAGE = 'whitenoise.storage.CompressedStaticFilesStorage'

# ─── DEFAULT FIELD TYPE ───
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ─── EMAIL ───
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
DEFAULT_FROM_EMAIL = 'trace-it@wildlife.org'

# ─── PRODUCTION SECURITY HEADERS ───
if not DEBUG:
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = 'DENY'

    # Railway handles HTTPS at the edge proxy. Don't redirect internally.
    SECURE_SSL_REDIRECT = False

    # Cookies are secure because browser sees HTTPS (Railway edge terminates SSL)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

    # HSTS: Tell browsers to always use HTTPS
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

# ─── CSRF DEBUGGING (Temporary) ───
# Uncomment this to see detailed CSRF failure info in logs
# CSRF_FAILURE_VIEW = 'django.views.csrf.csrf_failure'