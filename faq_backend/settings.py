from pathlib import Path
from datetime import timedelta
import os
import sys

BASE_DIR = Path(__file__).resolve().parent

MY_SETTINGS_PATH = os.path.join(BASE_DIR, 'my_settings.py')

# my_settings.py 파일의 위치를 시스템 경로에 추가합니다.
sys.path.append(os.path.dirname(MY_SETTINGS_PATH))

# my_settings에서 설정 값을 가져옵니다.
try:
    from my_settings import SECRET_KEY, DATABASES, ALIGO_API_KEY, ALIGO_USER_ID, ALIGO_SENDER
except ImportError:
    raise ImportError("my_settings.py 파일이 누락되었습니다. 올바르게 설정해 주세요.")

DEBUG = False  # 개발 시에는 True, 배포 시에는 False로 변경
ALLOWED_HOSTS = ['4.230.17.234', 'mumulai.com']  # 개발 시에는 *, 배포 시에는 도메인만 허용

MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'faq',
    'corsheaders',
    'django.core.files',
    'chatbot',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

CORS_ALLOWED_ORIGINS = [
    'http://localhost:3000',
    'http://127.0.0.1:3000',
    'http://4.230.17.234:3000',
    'https://mumulai.com',
    'https://www.mumulai.com',
    'http://localhost:3002',
    'http://localhost:3003',

]

AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
]

ROOT_URLCONF = 'faq_backend.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
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

WSGI_APPLICATION = 'faq_backend.wsgi.application'

APPEND_SLASH = False

# 데이터베이스 설정은 my_settings.py에서 가져옵니다.

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

LANGUAGE_CODE = 'ko-kr'
TIME_ZONE = 'Asia/Seoul'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'

STATIC_ROOT = os.path.join(BASE_DIR, 'static/')

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# 외부 API 설정을 my_settings.py에서 가져옵니다.
SIMPLE_JWT = {
    'USER_ID_FIELD': 'user_id',
    'USER_ID_CLAIM': 'user_id',
    'AUTH_HEADER_TYPES': ('Bearer',),
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=2),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
}

AUTH_USER_MODEL = 'faq.User'

SESSION_COOKIE_AGE = 1209600  # 2주 동안 세션 유지
SESSION_SAVE_EVERY_REQUEST = True  # 모든 요청마다 세션 갱신

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.AllowAny',
    ),
}

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'file': {
            'level': 'DEBUG',  # DEBUG 레벨로 설정되어야 함
            'class': 'logging.FileHandler',
            'filename': '/var/log/django/django.log',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['file'],
            'level': 'DEBUG',  # DEBUG 레벨로 설정되어야 함
            'propagate': True,
        },
        '__main__': {  # __main__을 포함하여 다른 로거도 설정 가능
            'handlers': ['file'],
            'level': 'DEBUG',
            'propagate': True,
        },
        'faq': {  # 여기에 올바른 모듈 이름을 넣으세요
            'handlers': ['file'],
            'level': 'DEBUG',
            'propagate': True,
        },
    },
}
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': 'redis://127.0.0.1:6379/1',
    }
}