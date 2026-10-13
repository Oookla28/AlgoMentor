"""Offline failures are injected; these tests never spend AI tokens or call providers."""
from datetime import timedelta
from unittest.mock import Mock, patch
import pytest
import requests
from cryptography.fernet import Fernet
from django.contrib.auth.models import User
from django.utils import timezone
from apps.accounts.models import APIUsageRecord, DailyAPIBudget
from apps.accounts.services.credential_service import save_config
from apps.agents.models import ServiceAvailability
from apps.reports.models import ReportTask, LearningReport
from apps.reports.services.report_service import enqueue_report
from core.exceptions import BusinessError, CodeExecutionError
from core.execution.piston_client import PistonClient
from core.llm.deepseek_client import DeepSeekClient
from core.services.availability import ServiceAvailabilityManager, get_service_statuses

pytestmark = pytest.mark.django_db


@pytest.fixture
def users(settings):
    settings.APP_ENCRYPTION_KEY = Fernet.generate_key().decode()
    alice = User.objects.create_user('availability_alice')
    bob = User.objects.create_user('availability_bob')
    save_config(alice, 'sk-test-only-alice-123456')
    save_config(bob, 'sk-test-only-bob-123456')
    return alice, bob


def ready_response(status=200):
    response = Mock(status_code=status)
    response.json.return_value = {'model': 'deepseek-flash', 'choices': [{'message': {'content': 'OK'}}],
                                 'usage': {'prompt_tokens': 2, 'completion_tokens': 1, 'total_tokens': 3}}
    return response


def expire_cooldown(service, scope='global'):
    ServiceAvailability.objects.filter(service=service, scope=scope).update(next_retry_at=timezone.now() - timedelta(seconds=1))


def test_snapshot_is_pure_and_unknown_is_not_a_claim_of_online(users):
    with patch('requests.Session.post', side_effect=AssertionError('No health inference')):
        snapshots = get_service_statuses(users[0])
    assert len(snapshots) == 3 and all(row['status'] == 'UNKNOWN' for row in snapshots)
    assert all(row['updated_at'] is None and row['can_attempt'] for row in snapshots)
    assert not ServiceAvailability.objects.exists()


def test_services_are_independent_and_half_open_recovery_needs_no_restart():
    wiki = ServiceAvailabilityManager('wikipedia')
    wiki.record_failure('WIKIPEDIA_TIMEOUT', 'sk-secret-upstream-123456')
    state = wiki.snapshot()
    assert state['status'] == 'DEGRADED' and not state['can_attempt']
    assert 'sk-secret' not in str(state)
    assert ServiceAvailabilityManager('deepseek').snapshot()['status'] == 'UNKNOWN'
    assert ServiceAvailabilityManager('code_execution').can_attempt()
    assert not wiki.begin_attempt()
    expire_cooldown('wikipedia')
    assert wiki.can_attempt() and wiki.begin_attempt()
    assert not wiki.begin_attempt()  # Only one retry during the next cooldown window.
    wiki.record_success()
    assert wiki.snapshot()['status'] == 'AVAILABLE' and wiki.can_attempt()
    assert wiki.snapshot()['consecutive_failures'] == 0


def test_repeated_actual_failures_and_configuration_change(settings):
    manager = ServiceAvailabilityManager('code_execution')
    manager.record_failure('EXECUTION_UNAVAILABLE')
    expire_cooldown('code_execution'); assert manager.begin_attempt()
    manager.record_failure('EXECUTION_SERVICE_TIMEOUT')
    assert manager.snapshot()['status'] == 'UNAVAILABLE'
    settings.PISTON_BASE_URL = 'http://127.0.0.1:2001/api/v2'
    changed = ServiceAvailabilityManager('code_execution')
    assert changed.snapshot()['status'] == 'UNKNOWN' and changed.can_attempt()
    changed.record_success()
    assert changed.snapshot()['status'] == 'AVAILABLE'


@pytest.mark.parametrize('status,code', [(401, 'INVALID_API_KEY'), (402, 'INSUFFICIENT_BALANCE'),
                                      (429, 'PROVIDER_RATE_LIMITED'), (404, 'MODEL_UNAVAILABLE')])
def test_personal_errors_never_disable_other_students(users, status, code):
    alice, bob = users
    transport = Mock(); transport.post.return_value = ready_response(status)
    with pytest.raises(BusinessError) as error:
        DeepSeekClient(alice, transport=transport).complete([{'role': 'user', 'content': 'hi'}])
    assert error.value.code == code
    affected = ServiceAvailabilityManager('deepseek', user=alice, model='deepseek-flash' if status == 404 else None)
    assert not affected.can_attempt()
    assert ServiceAvailabilityManager('deepseek', user=bob).can_attempt()
    assert ServiceAvailabilityManager('deepseek').snapshot()['status'] == 'UNKNOWN'
    good = Mock(); good.post.return_value = ready_response()
    DeepSeekClient(bob, transport=good).complete([{'role': 'user', 'content': 'hi'}])
    assert ServiceAvailabilityManager('deepseek', user=bob).snapshot()['status'] == 'AVAILABLE'
    assert affected.snapshot()['error_code'] == code


def test_defensive_shared_state_does_not_accept_personal_key_failure():
    manager = ServiceAvailabilityManager('deepseek')
    manager.record_failure('INVALID_API_KEY')
    assert manager.snapshot()['status'] == 'UNKNOWN'
    assert not ServiceAvailability.objects.exists()


def test_new_key_resets_only_its_personal_error(users):
    alice, bob = users
    ServiceAvailabilityManager('deepseek', user=alice).record_failure('INVALID_API_KEY')
    ServiceAvailabilityManager('deepseek', user=bob).record_failure('INSUFFICIENT_BALANCE')
    save_config(alice, 'sk-test-replacement-123456')
    assert ServiceAvailabilityManager('deepseek', user=alice).can_attempt()
    assert not ServiceAvailabilityManager('deepseek', user=bob).can_attempt()


def test_network_failure_suppresses_repeated_calls_without_fake_usage_then_recovers(users):
    alice, bob = users
    bad = Mock(); bad.post.side_effect = requests.ConnectionError('sk-secret-upstream-123456')
    with pytest.raises(BusinessError) as error:
        DeepSeekClient(alice, transport=bad).complete([{'role': 'user', 'content': 'hi'}])
    assert error.value.code == 'PROVIDER_NETWORK_ERROR'
    budget = DailyAPIBudget.objects.get(user=alice)
    before = (budget.requests, budget.charged_tokens)
    with pytest.raises(BusinessError) as error:
        DeepSeekClient(alice, transport=bad).complete([{'role': 'user', 'content': 'retry'}])
    assert error.value.code == 'DEEPSEEK_TEMPORARILY_UNAVAILABLE'
    budget.refresh_from_db()
    assert (budget.requests, budget.charged_tokens) == before
    assert APIUsageRecord.objects.count() == 1 and bad.post.call_count == 1
    assert not ServiceAvailabilityManager('deepseek', user=bob).can_attempt()
    expire_cooldown('deepseek')
    good = Mock(); good.post.return_value = ready_response()
    DeepSeekClient(bob, transport=good).complete([{'role': 'user', 'content': 'recovered'}])
    assert ServiceAvailabilityManager('deepseek').snapshot()['status'] == 'AVAILABLE'
    assert ServiceAvailabilityManager('deepseek', user=alice).can_attempt()


def test_real_student_runtime_failure_is_available_service():
    with patch('core.execution.piston_client.request_json', return_value={'run': {'code': 1, 'stderr': 'ZeroDivisionError'}}):
        result = PistonClient().run('print(1/0)')
    assert result.status == 'RUNTIME_ERROR'
    assert ServiceAvailabilityManager('code_execution').snapshot()['status'] == 'AVAILABLE'


def test_execution_infrastructure_failure_is_cooldown_and_recovers():
    with patch('core.execution.piston_client.request_json', side_effect=CodeExecutionError('Unavailable', code='EXECUTION_UNAVAILABLE')) as http:
        with pytest.raises(CodeExecutionError): PistonClient().run('print(1)')
        with pytest.raises(CodeExecutionError) as error: PistonClient().run('print(1)')
    assert error.value.code == 'EXECUTION_TEMPORARILY_UNAVAILABLE' and http.call_count == 1
    assert ServiceAvailabilityManager('deepseek').can_attempt()
    expire_cooldown('code_execution')
    with patch('core.execution.piston_client.request_json', return_value={'run': {'code': 0, 'stdout': '1\n'}}):
        assert PistonClient().run('print(1)').status == 'ACCEPTED'
    assert ServiceAvailabilityManager('code_execution').snapshot()['status'] == 'AVAILABLE'


def test_report_does_not_queue_fake_ai_work_when_known_unavailable(users):
    user = users[0]
    ServiceAvailabilityManager('deepseek').record_failure('PROVIDER_NETWORK_ERROR')
    with pytest.raises(BusinessError) as error: enqueue_report(user)
    assert error.value.code == 'DEEPSEEK_TEMPORARILY_UNAVAILABLE'
    assert not ReportTask.objects.exists() and not LearningReport.objects.exists()
    expire_cooldown('deepseek')
    assert enqueue_report(user).status == 'PENDING'


def test_persisted_state_survives_a_new_manager_instance():
    ServiceAvailabilityManager('wikipedia').record_failure('WIKIPEDIA_TIMEOUT')
    state = ServiceAvailabilityManager('wikipedia').snapshot()
    assert state['last_failure_at'] and not state['can_attempt']


@pytest.mark.parametrize('returned_model,status,expected', [('deepseek-flash', 404, 'MODEL_UNAVAILABLE'),
                                                          ('deepseek-flash', 200, 'MODEL_MISMATCH')])
def test_model_failure_does_not_block_another_selected_model(users, returned_model, status, expected):
    alice = users[0]
    unavailable = Mock(); unavailable.post.return_value = ready_response(status)
    with pytest.raises(BusinessError) as error:
        DeepSeekClient(alice, transport=unavailable).complete([{'role': 'user', 'content': 'hi'}], tier='expert')
    assert error.value.code == expected
    assert not ServiceAvailabilityManager('deepseek', user=alice, model='deepseek-v4-pro').can_attempt()
    assert ServiceAvailabilityManager('deepseek', user=alice, model='deepseek-flash').can_attempt()
    assert ServiceAvailabilityManager('deepseek', user=alice).can_attempt()
    good = Mock(); good.post.return_value = ready_response()
    assert DeepSeekClient(alice, transport=good).complete([{'role': 'user', 'content': 'hi'}], tier='deep').model == 'deepseek-flash'
    assert not ServiceAvailabilityManager('deepseek', user=alice, model='deepseek-v4-pro').can_attempt()
    assert get_service_statuses(alice, model='deepseek-v4-pro')[0]['selected_model'] == 'deepseek-v4-pro'
    save_config(alice, 'sk-test-new-key-123456')
    assert ServiceAvailabilityManager('deepseek', user=alice, model='deepseek-v4-pro').can_attempt()


def test_report_worker_known_network_failure_publishes_no_ai_narrative(users):
    from django.core.management import call_command
    from apps.reports.services.report_service import claim_next_task
    alice = users[0]
    task = enqueue_report(alice)
    snapshot = task.statistics
    claim_next_task()
    ServiceAvailabilityManager('deepseek').record_failure('PROVIDER_NETWORK_ERROR')
    with patch('apps.reports.services.crew_service.Crew', side_effect=AssertionError('No paid AI work')):
        call_command('run_report_task', task=str(task.pk))
    task.refresh_from_db()
    assert task.status == 'FAILED' and task.error_code == 'DEEPSEEK_TEMPORARILY_UNAVAILABLE'
    assert task.statistics == snapshot and not LearningReport.objects.exists()


def test_admin_disabled_wikipedia_is_labelled_without_fake_failure(settings):
    settings.WIKIPEDIA_ENABLED = False
    manager = ServiceAvailabilityManager('wikipedia')
    state = manager.snapshot()
    assert state['status'] == 'UNAVAILABLE' and state['error_code'] == 'WIKIPEDIA_DISABLED'
    assert state['status_source'] == 'configuration' and state['last_failure_at'] is None
    assert not manager.begin_attempt() and not ServiceAvailability.objects.exists()
