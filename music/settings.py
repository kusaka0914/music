INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'core.apps.CoreConfig',
    'django_ngrok',
]

# ngrokの設定
NGROK_URL = ""
NGROK_ENABLED = True

ALLOWED_HOSTS = ['localhost', '127.0.0.1', '.ngrok.io']

# Cloudflareの設定
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# 静的ファイルの設定
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# WhiteNoiseの追加
MIDDLEWARE = [
    # ... 既存のミドルウェア ...
    'whitenoise.middleware.WhiteNoiseMiddleware',
] 