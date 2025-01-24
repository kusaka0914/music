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