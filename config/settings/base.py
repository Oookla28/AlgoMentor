import os
from pathlib import Path
from dotenv import load_dotenv
BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BASE_DIR / '.env')
SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'development-only-change-before-production')
DEBUG = False
ALLOWED_HOSTS = os.getenv('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1,testserver').split(',')
INSTALLED_APPS = ['django.contrib.admin','django.contrib.auth','django.contrib.contenttypes','django.contrib.sessions','django.contrib.messages','django.contrib.staticfiles'] + [f'apps.{x}' for x in ['accounts','knowledge','tutor','agents','problems','learning','graph','reports','analytics']]
MIDDLEWARE = ['django.middleware.security.SecurityMiddleware','django.contrib.sessions.middleware.SessionMiddleware','django.middleware.common.CommonMiddleware','django.middleware.csrf.CsrfViewMiddleware','django.contrib.auth.middleware.AuthenticationMiddleware','django.contrib.messages.middleware.MessageMiddleware','django.middleware.clickjacking.XFrameOptionsMiddleware']
ROOT_URLCONF = 'config.urls'
TEMPLATES = [{'BACKEND':'django.template.backends.django.DjangoTemplates','DIRS':[BASE_DIR/'templates'],'APP_DIRS':True,'OPTIONS':{'context_processors':['django.template.context_processors.request','django.contrib.auth.context_processors.auth','django.contrib.messages.context_processors.messages','core.context_processors.platform_context']}}]
WSGI_APPLICATION = 'config.wsgi.application'
DATABASES = {'default': {'ENGINE':'django.db.backends.sqlite3','NAME':BASE_DIR/'data/db.sqlite3','OPTIONS':{'timeout':20,'transaction_mode':'IMMEDIATE'}}}
AUTH_PASSWORD_VALIDATORS = [{'NAME':'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},{'NAME':'django.contrib.auth.password_validation.MinimumLengthValidator'},{'NAME':'django.contrib.auth.password_validation.CommonPasswordValidator'},{'NAME':'django.contrib.auth.password_validation.NumericPasswordValidator'}]
LANGUAGE_CODE = 'zh-hans'
TIME_ZONE = 'Asia/Shanghai'
USE_I18N = True
USE_TZ = True
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR/'static']
STATIC_ROOT = BASE_DIR/'data/static'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/accounts/login/'
DATA_UPLOAD_MAX_MEMORY_SIZE = 131072
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SAMESITE = 'Lax'
X_FRAME_OPTIONS = 'DENY'
SECURE_CONTENT_TYPE_NOSNIFF = True
APP_ENCRYPTION_KEY = os.getenv('APP_ENCRYPTION_KEY', '')
APP_ENCRYPTION_PREVIOUS_KEYS = os.getenv('APP_ENCRYPTION_PREVIOUS_KEYS', '')
DEEPSEEK_BASE_URL = os.getenv('DEEPSEEK_BASE_URL', 'https://api.deepseek.com')
LLM_TIMEOUT = int(os.getenv('LLM_TIMEOUT','45'))
LLM_DAILY_REQUEST_LIMIT = int(os.getenv('LLM_DAILY_REQUEST_LIMIT','100'))
LLM_DAILY_TOKEN_LIMIT = int(os.getenv('LLM_DAILY_TOKEN_LIMIT','100000'))
LLM_MAX_TOKENS = int(os.getenv('LLM_MAX_TOKENS','2048'))
AGENT_MAX_TOOL_CALLS = 8
AGENT_TIMEOUT = 90
REPORT_TIMEOUT = 120
EXECUTION_PROVIDER = os.getenv('EXECUTION_PROVIDER','piston')
PISTON_BASE_URL = os.getenv('PISTON_BASE_URL','https://emkc.org/api/v2/piston')
PISTON_API_KEY = os.getenv('PISTON_API_KEY','')
JUDGE0_BASE_URL = os.getenv('JUDGE0_BASE_URL','https://ce.judge0.com')
JUDGE0_API_KEY = os.getenv('JUDGE0_API_KEY','')
JUDGE0_AUTH_HEADER = os.getenv('JUDGE0_AUTH_HEADER','X-Auth-Token')
JUDGE0_PYTHON_LANGUAGE_ID = int(os.getenv('JUDGE0_PYTHON_LANGUAGE_ID','71'))
EXECUTION_TIMEOUT = 15
CODE_MAX_LENGTH = 20000
CODE_MAX_TEST_CASES = 20
CODE_OUTPUT_LIMIT = 10000
CODE_TIME_LIMIT = 2
CODE_MEMORY_LIMIT = 134217728
CODE_RATE_LIMIT = 20
MASTERY_ESTIMATOR = os.getenv('MASTERY_ESTIMATOR','rule')
EMBEDDING_PROVIDER = os.getenv('EMBEDDING_PROVIDER','bge')
EMBEDDING_MODEL = os.getenv('EMBEDDING_MODEL','BAAI/bge-small-zh-v1.5')
EMBEDDING_REVISION = os.getenv('EMBEDDING_REVISION','main')
CHROMA_PATH = BASE_DIR/'data/chroma'
KNOWLEDGE_PATH = BASE_DIR/'knowledge/original'
RAG_TOP_K = 4
RAG_MIN_SCORE = float(os.getenv('RAG_MIN_SCORE','0.45'))
LOGGING = {'version':1,'disable_existing_loggers':False,'handlers':{'console':{'class':'logging.StreamHandler'}},'loggers':{'algomentor':{'handlers':['console'],'level':'INFO'}}}

# Remote execution credentials are administrator-configured, never accepted from students.
PISTON_API_TOKEN = os.getenv('PISTON_API_TOKEN',PISTON_API_KEY)
PISTON_PYTHON_VERSION = os.getenv('PISTON_PYTHON_VERSION','3.x')
JUDGE0_API_TOKEN = os.getenv('JUDGE0_API_TOKEN',JUDGE0_API_KEY)
JUDGE0_RAPIDAPI_KEY = os.getenv('JUDGE0_RAPIDAPI_KEY','')
JUDGE0_RAPIDAPI_HOST = os.getenv('JUDGE0_RAPIDAPI_HOST','judge0-ce.p.rapidapi.com')
EXECUTION_POLL_TIMEOUT = 15
EXECUTION_REQUESTS_PER_MINUTE = 8
MAX_TEST_CASES = 10
BKT_PARAMETERS = {'initial':0.15,'learn':0.12,'guess':0.2,'slip':0.1}

# Optional offline / external knowledge settings are validated without blocking startup.
def _optional_bool(name, default=True):
    value = os.getenv(name, str(default)).strip().lower()
    return {'true': True, '1': True, 'yes': True, 'false': False, '0': False, 'no': False}.get(value, default)


def _optional_int(name, default, minimum, maximum):
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        return default
    return value if minimum <= value <= maximum else default


WIKIPEDIA_ENABLED = _optional_bool('WIKIPEDIA_ENABLED')
WIKIPEDIA_DEFAULT_LANGUAGE = os.getenv('WIKIPEDIA_DEFAULT_LANGUAGE', 'zh')
if WIKIPEDIA_DEFAULT_LANGUAGE not in ('zh', 'en'):
    WIKIPEDIA_DEFAULT_LANGUAGE = 'zh'
WIKIPEDIA_FALLBACK_LANGUAGE = os.getenv('WIKIPEDIA_FALLBACK_LANGUAGE', 'en')
if WIKIPEDIA_FALLBACK_LANGUAGE not in ('zh', 'en'):
    WIKIPEDIA_FALLBACK_LANGUAGE = 'en'
_wikipedia_read_timeout = _optional_int('WIKIPEDIA_TIMEOUT', 6, 1, 30)
WIKIPEDIA_TIMEOUT = (min(3, _wikipedia_read_timeout), _wikipedia_read_timeout)
WIKIPEDIA_CACHE_TTL_DAYS = _optional_int('WIKIPEDIA_CACHE_TTL_DAYS', 7, 1, 365)
WIKIPEDIA_USER_AGENT = os.getenv('WIKIPEDIA_USER_AGENT', 'AlgoMentor/1.1 (https://github.com/Oookla28/AlgoMentor; educational knowledge retrieval)')
if not 8 <= len(WIKIPEDIA_USER_AGENT) <= 250 or '\n' in WIKIPEDIA_USER_AGENT or '\r' in WIKIPEDIA_USER_AGENT:
    WIKIPEDIA_USER_AGENT = 'AlgoMentor/1.1 (https://github.com/Oookla28/AlgoMentor)'
OFFLINE_FALLBACK_ENABLED = _optional_bool('OFFLINE_FALLBACK_ENABLED')
EXTERNAL_SERVICE_CHECK_INTERVAL = _optional_int('EXTERNAL_SERVICE_CHECK_INTERVAL', 60, 5, 3600)
LOCAL_EMBEDDING_OFFLINE_MODE = _optional_bool('LOCAL_EMBEDDING_OFFLINE_MODE')
