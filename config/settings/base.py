import os
from pathlib import Path
from dotenv import load_dotenv
BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BASE_DIR / '.env')
SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'development-only-change-before-production')
DEBUG = False
ALLOWED_HOSTS = os.getenv('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1,testserver').split(',')
INSTALLED_APPS = ['django.contrib.admin','django.contrib.auth','django.contrib.contenttypes','django.contrib.sessions','django.contrib.messages','django.contrib.staticfiles'] + [f'apps.{x}' for x in ['accounts','knowledge','tutor','agents','problems','learning','graph','reports','analytics','platform']]
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
CHROMA_PATH = Path(os.getenv('CHROMA_PATH', str(BASE_DIR/'data/chroma')))
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


def _optional_float(name, default, minimum, maximum):
    try:
        value = float(os.getenv(name, str(default)))
    except ValueError:
        return default
    return value if minimum <= value <= maximum else default


# EvidenceRAG Studio: research extensions are additive and default to the legacy
# retrieval path so existing deployments keep working without re-indexing.
EVIDENCE_RAG_ENABLED = _optional_bool('EVIDENCE_RAG_ENABLED')
EVIDENCE_RAG_DEFAULT_MODE = os.getenv('EVIDENCE_RAG_DEFAULT_MODE', 'legacy').strip().lower()
if EVIDENCE_RAG_DEFAULT_MODE not in ('legacy', 'advanced'):
    EVIDENCE_RAG_DEFAULT_MODE = 'legacy'
EVIDENCE_RAG_CHAT_MODE = os.getenv('EVIDENCE_RAG_CHAT_MODE', 'legacy').strip().lower()
if EVIDENCE_RAG_CHAT_MODE not in ('legacy', 'advanced'):
    EVIDENCE_RAG_CHAT_MODE = 'legacy'
EVIDENCE_RAG_INDEX_VERSION = os.getenv('EVIDENCE_RAG_INDEX_VERSION', 'adv-v1').strip() or 'adv-v1'
EVIDENCE_RAG_PARENT_TOKEN_MIN = _optional_int('EVIDENCE_RAG_PARENT_TOKEN_MIN', 1200, 400, 4000)
EVIDENCE_RAG_PARENT_TOKEN_MAX = _optional_int('EVIDENCE_RAG_PARENT_TOKEN_MAX', 2000, 600, 6000)
if EVIDENCE_RAG_PARENT_TOKEN_MAX < EVIDENCE_RAG_PARENT_TOKEN_MIN:
    EVIDENCE_RAG_PARENT_TOKEN_MAX = EVIDENCE_RAG_PARENT_TOKEN_MIN
EVIDENCE_RAG_CHILD_TOKEN_MIN = _optional_int('EVIDENCE_RAG_CHILD_TOKEN_MIN', 300, 50, 1000)
EVIDENCE_RAG_CHILD_TOKEN_MAX = _optional_int('EVIDENCE_RAG_CHILD_TOKEN_MAX', 500, 80, 2000)
if EVIDENCE_RAG_CHILD_TOKEN_MAX < EVIDENCE_RAG_CHILD_TOKEN_MIN:
    EVIDENCE_RAG_CHILD_TOKEN_MAX = EVIDENCE_RAG_CHILD_TOKEN_MIN
EVIDENCE_RAG_CHILD_OVERLAP_RATIO = _optional_float('EVIDENCE_RAG_CHILD_OVERLAP_RATIO', 0.12, 0.0, 0.5)
EVIDENCE_RAG_RRF_K = _optional_int('EVIDENCE_RAG_RRF_K', 60, 1, 500)
EVIDENCE_RAG_TOP_K = _optional_int('EVIDENCE_RAG_TOP_K', 6, 1, 20)
EVIDENCE_RAG_ROUTE_TOP_K = _optional_int('EVIDENCE_RAG_ROUTE_TOP_K', 20, 1, 100)
EVIDENCE_RAG_MAX_QUERY_VARIANTS = _optional_int('EVIDENCE_RAG_MAX_QUERY_VARIANTS', 5, 1, 8)
EVIDENCE_RAG_CONTEXT_TOKEN_BUDGET = _optional_int('EVIDENCE_RAG_CONTEXT_TOKEN_BUDGET', 1800, 200, 8000)
EVIDENCE_RAG_DENSE_MIN_SCORE = _optional_float('EVIDENCE_RAG_DENSE_MIN_SCORE', 0.20, 0.0, 1.0)
EVIDENCE_RAG_MIN_RERANK_SCORE = _optional_float('EVIDENCE_RAG_MIN_RERANK_SCORE', 0.12, 0.0, 1.0)
EVIDENCE_RAG_MIN_LEXICAL_OVERLAP = _optional_float('EVIDENCE_RAG_MIN_LEXICAL_OVERLAP', 0.20, 0.0, 1.0)
EVIDENCE_RAG_MIN_DENSE_SUPPORT = _optional_float('EVIDENCE_RAG_MIN_DENSE_SUPPORT', 0.35, 0.0, 1.0)
EVIDENCE_RAG_RERANK_BACKEND = os.getenv('EVIDENCE_RAG_RERANK_BACKEND', 'deterministic').strip().lower()
if EVIDENCE_RAG_RERANK_BACKEND not in ('deterministic', 'cross_encoder'):
    EVIDENCE_RAG_RERANK_BACKEND = 'deterministic'
EVIDENCE_RAG_CROSS_ENCODER_MODEL = os.getenv('EVIDENCE_RAG_CROSS_ENCODER_MODEL', 'BAAI/bge-reranker-base')
EVIDENCE_RAG_QUERY_REWRITE_LLM = _optional_bool('EVIDENCE_RAG_QUERY_REWRITE_LLM', False)
EVIDENCE_RAG_CONFLICT_SIMILARITY = _optional_float('EVIDENCE_RAG_CONFLICT_SIMILARITY', 0.55, 0.1, 1.0)
EVIDENCE_RAG_CONFLICT_SCORE_GAP = _optional_float('EVIDENCE_RAG_CONFLICT_SCORE_GAP', 0.12, 0.0, 1.0)
EVIDENCE_RAG_MAX_UPLOAD_BYTES = _optional_int('EVIDENCE_RAG_MAX_UPLOAD_BYTES', 20 * 1024 * 1024, 1024, 200 * 1024 * 1024)
EVIDENCE_RAG_UPLOAD_DIR = BASE_DIR / 'data/evidence_uploads'
EVIDENCE_RAG_OCR_ENABLED = _optional_bool('EVIDENCE_RAG_OCR_ENABLED', False)
EVIDENCE_RAG_ASR_ENABLED = _optional_bool('EVIDENCE_RAG_ASR_ENABLED', False)
EVIDENCE_RAG_MAX_CLAIMS_PER_CHUNK = _optional_int('EVIDENCE_RAG_MAX_CLAIMS_PER_CHUNK', 6, 1, 30)
EVIDENCE_RAG_TREE_PAGE_SIZE = _optional_int('EVIDENCE_RAG_TREE_PAGE_SIZE', 50, 1, 500)

# Evidence-grounded platform (additive; legacy endpoints remain unchanged).
PLATFORM_AGENT_ENABLED = _optional_bool('PLATFORM_AGENT_ENABLED', True)
PLATFORM_GATE_MIN_COVERAGE = _optional_float('PLATFORM_GATE_MIN_COVERAGE', 0.15, 0.0, 1.0)
PLATFORM_GATE_MIN_SUPPORT = _optional_float('PLATFORM_GATE_MIN_SUPPORT', 0.30, 0.0, 1.0)
PLATFORM_AGENT_MAX_STEPS = _optional_int('PLATFORM_AGENT_MAX_STEPS', 20, 5, 60)
PLATFORM_AGENT_MAX_TOKENS = _optional_int('PLATFORM_AGENT_MAX_TOKENS', 6000, 500, 50000)
PLATFORM_AGENT_MAX_TOOL_CALLS = _optional_int('PLATFORM_AGENT_MAX_TOOL_CALLS', 8, 1, 30)
PLATFORM_AGENT_MAX_LATENCY_MS = _optional_int('PLATFORM_AGENT_MAX_LATENCY_MS', 30000, 1000, 120000)
PLATFORM_AGENT_MAX_RETRIEVE_MORE = _optional_int('PLATFORM_AGENT_MAX_RETRIEVE_MORE', 2, 0, 3)
PLATFORM_EVAL_MAX_CASES = _optional_int('PLATFORM_EVAL_MAX_CASES', 50, 1, 200)
