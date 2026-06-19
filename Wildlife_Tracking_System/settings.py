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

ALLOWED_HOSTS = [
    'traceit-web.up.railway.app',
    'localhost',
    '127.0.0.1',
    '*',
]

CSRF_TRUSTED_ORIGINS = [
    'https://traceit-web.up.railway.app',
    'http://traceit-web.up.railway.app',
    'https://localhost',
    'http://localhost',
]

# ─── AUTH REDIRECTS (stay on same site, no new windows) ───
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
    SECURE_SSL_REDIRECT = False  # Railway handles HTTPS
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True