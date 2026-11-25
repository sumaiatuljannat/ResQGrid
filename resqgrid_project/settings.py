"""
Django settings for resqgrid_project.
Intelligent Emergency Response & Humanitarian Coordination Network
"""

from pathlib import Path
import os
import dj_database_url
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

def _env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in ('1', 'true', 'yes', 'on'):
        return True
    if normalized in ('0', 'false', 'no', 'off'):
        return False
    raise ImproperlyConfigured(f'{name} must be a boolean value.')


RESQGRID_ENV = os.environ.get('RESQGRID_ENV', 'development').strip().lower()
DEBUG = _env_bool('DEBUG', default=RESQGRID_ENV != 'production')
if RESQGRID_ENV == 'production' and DEBUG:
    raise ImproperlyConfigured('DEBUG must be False when RESQGRID_ENV=production.')

SECRET_KEY = os.environ.get('SECRET_KEY')
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured('SECRET_KEY must be configured when DEBUG=False.')
    SECRET_KEY = 'resqgrid-insecure-local-development-key'

render_hostname = os.environ.get('RENDER_EXTERNAL_HOSTNAME', '').strip()
default_allowed_hosts = 'localhost,127.0.0.1,testserver' if DEBUG else ''
ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get('ALLOWED_HOSTS', default_allowed_hosts).split(',')
    if host.strip()
]
if render_hostname and render_hostname not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(render_hostname)
if not DEBUG and '*' in ALLOWED_HOSTS:
    raise ImproperlyConfigured('ALLOWED_HOSTS must not contain * when DEBUG=False.')
if not DEBUG and not ALLOWED_HOSTS:
    raise ImproperlyConfigured('ALLOWED_HOSTS must be configured when DEBUG=False.')

if render_hostname:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

CSRF_TRUSTED_ORIGINS = [
    origin.strip().rstrip('/')
    for origin in os.environ.get('CSRF_TRUSTED_ORIGINS', '').split(',')
    if origin.strip()
]
if render_hostname:
    render_origin = f'https://{render_hostname}'
    if render_origin not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(render_origin)

SECURE_SSL_REDIRECT = _env_bool(
    'SECURE_SSL_REDIRECT',
    default=not DEBUG,
)
try:
    SECURE_HSTS_SECONDS = int(os.environ.get('SECURE_HSTS_SECONDS', '0'))
except ValueError as error:
    raise ImproperlyConfigured('SECURE_HSTS_SECONDS must be an integer.') from error
if SECURE_HSTS_SECONDS < 0:
    raise ImproperlyConfigured('SECURE_HSTS_SECONDS cannot be negative.')
SECURE_HSTS_INCLUDE_SUBDOMAINS = _env_bool('SECURE_HSTS_INCLUDE_SUBDOMAINS', default=False)
SECURE_HSTS_PRELOAD = _env_bool('SECURE_HSTS_PRELOAD', default=False)
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'strict-origin-when-cross-origin'
SECURE_CROSS_ORIGIN_OPENER_POLICY = 'same-origin'
CARTO_API_KEY = os.environ.get('CARTO_API_KEY', '')
DEMO_PASSWORD = os.environ.get('RESQGRID_DEMO_PASSWORD', '')
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'core',
]

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

ROOT_URLCONF = 'resqgrid_project.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'core.context_processors.resqgrid_globals',
            ],
        },
    },
]

WSGI_APPLICATION = 'resqgrid_project.wsgi.application'

DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL:
    database_config = dj_database_url.parse(
        DATABASE_URL,
        conn_max_age=600,
        conn_health_checks=True,
        ssl_require=not DEBUG,
    )
    if not DEBUG and database_config['ENGINE'] != 'django.db.backends.postgresql':
        raise ImproperlyConfigured('DATABASE_URL must use PostgreSQL when DEBUG=False.')
    DATABASES = {'default': database_config}
else:
    if not DEBUG:
        raise ImproperlyConfigured('DATABASE_URL must be configured when DEBUG=False.')
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {
            'min_length': 8,
        }
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Dhaka'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [
    BASE_DIR / 'static',
]

STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedStaticFilesStorage',
    },
}

LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'dashboard'
LOGOUT_REDIRECT_URL = 'home'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
