"""
Django settings for Wildlife_Tracking_System project.
"""

from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get('SECRET_KEY', 'django-insecure-CHANGE-THIS-IN-PRODUCTION-abcdefghijklmnopqrstuvwxyz123456789')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.environ.get('DEBUG', 'True').lower() in ['true', '1', 'yes']

# Railway domain + local development
ALLOWED_HOSTS = [
    'web-production-050c1a.up.railway.app',
    'localhost',
    '127.0.0.1',
    '*',
]

# CSRF trusted origins for Railway deployment
CSRF_TRUSTED_ORIGINS = [
    'https://web-production-050c1a.up.railway.app',
    'http://web-production-050c1a.up.railway.app',
    'https://*.railway.app',
    'http://*.railway.app',
    'http://localhost:8000',
    'http://127.0.0.1:8000',
]

# For Railway proxy (handles HTTPS -> HTTP forwarding)
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = True

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

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
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

# Database - Railway provides DATABASE_URL env var, fallback to SQLite
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

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Static files
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Email settings
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
DEFAULT_FROM_EMAIL = 'trace-it@wildlife.org'

# Logging
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {'class': 'logging.StreamHandler'},
    },
    'root': {'handlers': ['console'], 'level': 'INFO'},
    'loggers': {
        'django': {'handlers': ['console'], 'level': 'INFO', 'propagate': True},
        'Trace_It': {'handlers': ['console'], 'level': 'DEBUG', 'propagate': False},
    },
}

# Add these to settings.py
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False