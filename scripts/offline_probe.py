"""Fresh-process offline verification, with a disposable copy of the local DB.

External DNS and socket connections are blocked before Django/model imports.
Only this process's loopback HTTP server and local Piston are allowed; the host
download proxy is deliberately blocked. No student record is written to the
real database, and no API key is used for an AI request.
"""
import ipaddress
import json
import os
from pathlib import Path
import socket
import sqlite3
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
blocked = []
allowed_ports = {2000}
original_connect = socket.socket.connect
original_connect_ex = socket.socket.connect_ex
original_getaddrinfo = socket.getaddrinfo


def permitted(host, port):
    try:
        return ipaddress.ip_address(host).is_loopback and port in allowed_ports
    except ValueError:
        return host == 'localhost' and port in allowed_ports


def deny(host, port):
    if len(blocked) < 30:
        blocked.append({'host': str(host), 'port': port})
    raise OSError('External network blocked by the offline verification harness')


def connect(self, address):
    if isinstance(address, tuple) and not permitted(address[0], address[1]):
        deny(address[0], address[1])
    return original_connect(self, address)


def connect_ex(self, address):
    if isinstance(address, tuple) and not permitted(address[0], address[1]):
        deny(address[0], address[1])
    return original_connect_ex(self, address)


def getaddrinfo(host, port, *args, **kwargs):
    # Passive server binds are local setup, not an outbound DNS lookup.
    if host not in (None, '') and not permitted(host, int(port or 0)):
        deny(host, port)
    return original_getaddrinfo(host, port, *args, **kwargs)


socket.socket.connect = connect
socket.socket.connect_ex = connect_ex
socket.getaddrinfo = getaddrinfo
os.environ.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1',
                  HF_HUB_DISABLE_TELEMETRY='1', ANONYMIZED_TELEMETRY='False',
                  DJANGO_SETTINGS_MODULE='config.settings.development')


def main():
    from django.conf import settings
    from django.core.wsgi import get_wsgi_application
    from django.test import Client
    from wsgiref.simple_server import make_server, WSGIRequestHandler
    import requests

    with tempfile.TemporaryDirectory(prefix='algomentor-offline-') as temporary:
        database = Path(temporary) / 'offline.sqlite3'
        with sqlite3.connect('file:' + str(ROOT / 'data/db.sqlite3') + '?mode=ro', uri=True) as original:
            with sqlite3.connect(database) as copied:
                original.backup(copied)
        settings.DATABASES['default']['NAME'] = str(database)
        settings.LOCAL_EMBEDDING_OFFLINE_MODE = True
        settings.DEBUG = False
        settings.MIDDLEWARE = [*settings.MIDDLEWARE[:1], 'whitenoise.middleware.WhiteNoiseMiddleware', *settings.MIDDLEWARE[1:]]
        application = get_wsgi_application()
        from django.contrib.auth import get_user_model
        from apps.learning.models import LearningActivity, MasteryState
        from apps.problems.models import Submission
        from apps.knowledge.services.embedding_service import bge_embeddings
        from apps.knowledge.services.wikipedia_service import search_wikipedia
        from core.services.availability import ServiceAvailabilityManager
        from core.execution.provider import get_execution_provider

        assert bge_embeddings.cache_info().currsize == 0, 'This must be a fresh model process'
        learner = get_user_model().objects.order_by('id').first()
        assert learner is not None, 'Use a locally initialized database with an existing account'
        initial = (Submission.objects.count(), LearningActivity.objects.count(),
                   list(MasteryState.objects.order_by('id').values_list('id', 'index', 'bkt_probability', 'evidence_count')))
        client = Client()
        client.force_login(learner)

        class QuietHandler(WSGIRequestHandler):
            def log_message(self, format, *args):
                pass

        server = make_server('127.0.0.1', 0, application, handler_class=QuietHandler)
        allowed_ports.add(server.server_port)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f'http://127.0.0.1:{server.server_port}'
        results = {}
        started = time.monotonic()
        try:
            with requests.Session() as session:
                session.trust_env = False
                session.cookies.set(settings.SESSION_COOKIE_NAME, client.cookies[settings.SESSION_COOKIE_NAME].value)
                for path in ('/', '/accounts/login/', '/accounts/settings/', '/knowledge/',
                             '/knowledge/local/', '/knowledge/wikipedia/', '/graph/',
                             '/visualizations/', '/problems/', '/learning/', '/mistakes/', '/reports/'):
                    response = session.get(base + path, timeout=30)
                    results[path] = response.status_code
                    assert response.status_code == 200, path
                for path in ('/static/css/app.css', '/static/js/app.js', '/static/js/graph.js',
                             '/static/js/visualization.js', '/static/svg/icons.svg'):
                    response = session.get(base + path, timeout=10)
                    results[path] = response.status_code
                    assert response.status_code == 200 and response.content, path
                response = session.get(base + '/api/v1/knowledge/search/', params={'q': '循环队列判满条件'}, timeout=60)
                knowledge = response.json()
                assert response.status_code == 200 and knowledge['data']['evidence_sufficient']
                results['local_rag'] = {'status': 'PASSED', 'citations': len(knowledge['data']['citations']), 'embedding': 'local BGE / Chroma'}
                response = session.get(base + '/api/v1/graph/', timeout=10)
                assert response.status_code == 200 and response.json()['data']['nodes']
                results['graph_api'] = 'PASSED'

                cached = search_wikipedia('红黑树', cache_only=True)
                assert cached['success'] and cached['from_cache']
                results['wikipedia_cache'] = {'status': 'PASSED', 'title': cached['title'], 'language': cached['language'], 'cache_status': cached['cache_status'], 'retrieved_at': cached['retrieved_at']}
                # A force-refresh actually attempts a network request, then falls
                # back to the same real historical cache instead of inventing it.
                fallback = search_wikipedia('红黑树', force_refresh=True)
                assert fallback['success'] and fallback['from_cache'] and fallback.get('error_code')
                results['wikipedia_network_fallback'] = 'PASSED'

                ServiceAvailabilityManager('deepseek').record_failure('PROVIDER_NETWORK_ERROR')
                response = session.get(base + '/api/v1/services/status/', timeout=10)
                assert response.status_code == 200
                statuses = {item['service']: item for item in response.json()['data']['services']}
                assert not statuses['deepseek']['can_attempt']
                results['independent_statuses'] = 'PASSED'

                csrf = session.cookies.get(settings.CSRF_COOKIE_NAME)
                response = session.post(base + '/api/v1/algorithms/steps/', json={'algorithm': 'kmp', 'text': 'ababcabcacbab', 'pattern': 'abcac'}, headers={'X-CSRFToken': csrf}, timeout=10)
                assert response.status_code == 200, 'Algorithm API'
                results['algorithm_api'] = 'PASSED'

                execution = get_execution_provider().run('print("ALGOMENTOR_OFFLINE_PYTHON")')
                assert execution.status == 'ACCEPTED' and execution.stdout.strip() == 'ALGOMENTOR_OFFLINE_PYTHON'
                results['local_isolated_execution'] = 'PASSED'

                response = session.post(base + '/api/v1/code/draft/', json={'code': 'print("draft only")', 'stdin': ''}, headers={'X-CSRFToken': csrf}, timeout=10)
                assert response.status_code == 200 and response.json()['data']['saved']
                results['draft_saved_without_grading'] = 'PASSED'
                after = (Submission.objects.count(), LearningActivity.objects.count(),
                         list(MasteryState.objects.order_by('id').values_list('id', 'index', 'bkt_probability', 'evidence_count')))
                assert initial == after
                assert blocked, 'The network block must have been exercised'
                return {'status': 'PASSED', 'fresh_process': True, 'external_dns_and_sockets_blocked': True,
                        'host_proxy_blocked': True, 'student_db': 'disposable local copy', 'learning_evidence_unchanged': True,
                        'deepseek_inference': 'not called; no key used', 'debug': False,
                        'elapsed_seconds': round(time.monotonic() - started, 3), 'checks': results,
                        'blocked_attempts': blocked}
        finally:
            server.shutdown()
            server.server_close()


if __name__ == '__main__':
    try:
        outcome = main()
    except Exception as error:
        outcome = {'status': 'FAILED', 'error_type': type(error).__name__, 'message': str(error)[:300], 'blocked_attempts': blocked}
    print('ALGOMENTOR_OFFLINE_RESULT=' + json.dumps(outcome, ensure_ascii=False))
    raise SystemExit(0 if outcome['status'] == 'PASSED' else 1)
