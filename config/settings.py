from pathlib import Path
from datetime import timedelta
from decouple import config
import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = config('SECRET_KEY')
DEBUG = config('DEBUG', default=False, cast=bool)
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='').split(',')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'rest_framework_simplejwt',
    'drf_spectacular',
    'corsheaders',
    'apps.core.apps.CoreConfig',
    'apps.auth.apps.AuthConfig',
    'apps.contact.apps.ContactConfig',
    'apps.payments.apps.PaymentsConfig',
    'apps.blog.apps.BlogConfig',
    'apps.faq.apps.FaqConfig',
    'apps.cars.apps.CarsConfig',
    'apps.appointments.apps.AppointmentsConfig',
    'apps.testimonials.apps.TestimonialsConfig',
    'apps.newsletter.apps.NewsletterConfig',
    'apps.part_exchange.apps.PartExchangeConfig',
    'apps.vehicle_sourcing.apps.VehicleSourcingConfig',
    'apps.delivery.apps.DeliveryConfig',
    'apps.expense.apps.ExpenseConfig',
    'apps.sell_my_car.apps.SellMyCarConfig',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

_database_url = config('DATABASE_URL', default=None)
if _database_url:
    DATABASES = {'default': dj_database_url.parse(_database_url, conn_max_age=600)}
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': config('PGDATABASE', default=config('DB_NAME', default='noorrix_db')),
            'USER': config('PGUSER', default=config('DB_USER', default='postgres')),
            'PASSWORD': config('PGPASSWORD', default=config('DB_PASSWORD', default='')),
            'HOST': config('PGHOST', default=config('DB_HOST', default='localhost')),
            'PORT': config('PGPORT', default=config('DB_PORT', default='5432')),
        }
    }

AUTH_USER_MODEL = 'user_auth.User'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

AUTHENTICATION_BACKENDS = [
    'apps.auth.backends.EmailBackend',
]

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
}

SPECTACULAR_SETTINGS = {
    'TITLE': 'Noorrix API',
    'DESCRIPTION': 'API documentation for the Noorrix backend.',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'SWAGGER_UI_SETTINGS': {
        'persistAuthorization': True,
    },
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=60),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': False,
    'BLACKLIST_AFTER_ROTATION': False,
}

EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.resend.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_USE_SSL = False
EMAIL_HOST_USER = 'resend'
RESEND_API_KEY = config('RESEND_API_KEY', default='')
EMAIL_HOST_PASSWORD = RESEND_API_KEY
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='Noorrix Motors <noreply@noorrix.com>')
ADMIN_EMAIL = config('ADMIN_EMAIL', default='')
EMAIL_TIMEOUT = 10
FRONTEND_URL = config('FRONTEND_URL', default='http://localhost:3000')

STRIPE_SECRET_KEY = config('STRIPE_SECRET_KEY', default='')
STRIPE_PUBLISHABLE_KEY = config('STRIPE_PUBLISHABLE_KEY', default='')
STRIPE_WEBHOOK_SECRET = config('STRIPE_WEBHOOK_SECRET', default='')
# Support multiple signing secrets (comma-separated) so several Stripe
# destinations and/or the Stripe CLI can all be verified, e.g.
# STRIPE_WEBHOOK_SECRET=whsec_aaa,whsec_bbb
STRIPE_WEBHOOK_SECRETS = [s.strip() for s in STRIPE_WEBHOOK_SECRET.split(',') if s.strip()]
STRIPE_CURRENCY = config('STRIPE_CURRENCY', default='gbp')

DVLA_API_KEY = config('DVLA_API_KEY', default='')
DVSA_TOKEN_URL = config('DVSA_TOKEN_URL', default='')
DVSA_CLIENT_ID = config('DVSA_CLIENT_ID', default='')
DVSA_CLIENT_SECRET = config('DVSA_CLIENT_SECRET', default='')
DVSA_SCOPE = config('DVSA_SCOPE', default='https://tapi.dvsa.gov.uk/.default')
DVSA_API_KEY = config('DVSA_API_KEY', default='')

# Origins permitted as Stripe Checkout success/cancel redirect targets. Anything
# not in this allow-list is rejected to prevent open-redirect abuse.
PAYMENT_REDIRECT_ALLOWED_ORIGINS = [
    o.strip()
    for o in [FRONTEND_URL, *config('CORS_ALLOWED_ORIGINS', default='').split(',')]
    if o.strip()
]

CORS_ALLOW_CREDENTIALS = True
if DEBUG:
    CORS_ALLOW_ALL_ORIGINS = True
else:
    CORS_ALLOWED_ORIGINS = [o.strip() for o in config('CORS_ALLOWED_ORIGINS', default='').split(',') if o.strip()]

LANGUAGE_CODE = 'en-gb'
TIME_ZONE = 'Europe/London'
USE_I18N = True
USE_TZ = True
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Uploads live on Cloudflare R2 once USE_R2 is on; until then they stay on the
# Railway volume mounted at MEDIA_ROOT. Flipping this flag is the whole
# migration switch -- and the whole rollback.
USE_R2 = config('USE_R2', default=False, cast=bool)

# Django 5.1 removed STATICFILES_STORAGE/DEFAULT_FILE_STORAGE; both backends
# are declared here instead.
STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
    },
}

if USE_R2:
    STORAGES['default'] = {
        'BACKEND': 'storages.backends.s3.S3Storage',
        'OPTIONS': {
            'bucket_name': config('R2_BUCKET_NAME'),
            'endpoint_url': config('R2_ENDPOINT_URL'),
            'access_key': config('R2_ACCESS_KEY_ID'),
            'secret_key': config('R2_SECRET_ACCESS_KEY'),
            'region_name': 'auto',
            'signature_version': 's3v4',
            # Serve through the bucket's public hostname, unsigned, so image
            # URLs stay stable and cacheable.
            'custom_domain': config('R2_PUBLIC_URL').split('://')[-1].rstrip('/'),
            'querystring_auth': False,
            # R2 has no ACLs, and FileSystemStorage suffixes clashing names
            # rather than overwriting -- keep that behaviour.
            'default_acl': None,
            'file_overwrite': False,
        },
    }

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {'class': 'logging.StreamHandler'},
    },
    'loggers': {
        'apps': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'django.request': {
            'handlers': ['console'],
            'level': 'ERROR',
            'propagate': False,
        },
    },
}

CSRF_TRUSTED_ORIGINS = [
    o.strip()
    for o in config('CSRF_TRUSTED_ORIGINS', default='').split(',')
    if o.strip()
]
