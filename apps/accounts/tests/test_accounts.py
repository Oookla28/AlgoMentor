from cryptography.fernet import Fernet
from unittest.mock import Mock
import pytest,requests
from django.contrib.auth.models import User
from django.contrib.auth.models import AnonymousUser
from django.test import override_settings
from apps.accounts.models import UserAPIConfig,APIUsageRecord,DailyAPIBudget
from apps.accounts.services.credential_service import save_config,get_api_key,delete_key,public_config,rotate_key
from core.exceptions import BusinessError
from core.llm.deepseek_client import DeepSeekClient
from core.llm.model_registry import MODEL_TIERS

pytestmark=pytest.mark.django_db

@pytest.fixture
def user(): return User.objects.create_user('alice',password='ExamplePassword-123')

@pytest.fixture(autouse=True)
def encryption(settings): settings.APP_ENCRYPTION_KEY=Fernet.generate_key().decode();settings.APP_ENCRYPTION_PREVIOUS_KEYS=''

@pytest.fixture
def keyed_user(user): save_config(user,'sk-test-key-1234567890');return user


def response(status=200):
    mock=Mock(status_code=status)
    mock.json.return_value={'model':'deepseek-flash','choices':[{'message':{'content':'OK'},'finish_reason':'stop'}],'usage':{'prompt_tokens':8,'completion_tokens':2,'total_tokens':10}}
    return mock


def test_encrypted_current_user_storage_and_mask(user):
    key='sk-test-key-1234567890';save_config(user,key)
    config=UserAPIConfig.objects.get(user=user)
    assert key not in config.encrypted_api_key
    assert get_api_key(user)==key
    assert key not in str(public_config(user))
    assert public_config(user)['key_hint']=='••••7890'
    other=User.objects.create_user('bob')
    with pytest.raises(BusinessError,match='配置'): get_api_key(other)
    with pytest.raises(BusinessError): get_api_key(AnonymousUser())


def test_delete_key_and_blank_update(keyed_user):
    save_config(keyed_user,'',default_tier='expert',reasoning_effort='max')
    assert get_api_key(keyed_user)=='sk-test-key-1234567890'
    delete_key(keyed_user)
    assert not public_config(keyed_user)['configured']
    with pytest.raises(BusinessError): get_api_key(keyed_user)


def test_main_key_rotation(user,settings):
    original=settings.APP_ENCRYPTION_KEY;save_config(user,'sk-test-key-1234567890')
    settings.APP_ENCRYPTION_KEY=Fernet.generate_key().decode();settings.APP_ENCRYPTION_PREVIOUS_KEYS=original
    rotate_key(user)
    settings.APP_ENCRYPTION_PREVIOUS_KEYS=''
    assert get_api_key(user)=='sk-test-key-1234567890'


@pytest.mark.parametrize('tier,model,thinking,effort',[('fast','deepseek-flash','disabled','none'),('deep','deepseek-flash','enabled','high'),('expert','deepseek-v4-pro','enabled','high')])
def test_three_exact_tiers(keyed_user,tier,model,thinking,effort):
    transport=Mock();transport.post.return_value=response();transport.post.return_value.json.return_value['model']=model
    result=DeepSeekClient(keyed_user,transport=transport).complete([{'role':'user','content':'hi'}],tier=tier)
    payload=transport.post.call_args.kwargs['json']
    assert payload['model']==model
    assert payload['thinking']['type']==thinking
    assert payload['reasoning_effort']==effort
    assert result.text=='OK'
    assert result.usage.total_tokens==10
    record=APIUsageRecord.objects.get(user=keyed_user)
    assert record.input_tokens==8 and record.output_tokens==2 and record.status=='SUCCESS'
    assert DailyAPIBudget.objects.get(user=keyed_user).charged_tokens==10


@pytest.mark.parametrize('status,code',[(401,'INVALID_API_KEY'),(402,'INSUFFICIENT_BALANCE'),(429,'PROVIDER_RATE_LIMITED'),(404,'MODEL_UNAVAILABLE'),(503,'PROVIDER_UNAVAILABLE')])
def test_upstream_error_redacted(keyed_user,status,code):
    transport=Mock();transport.post.return_value=response(status)
    transport.post.return_value.json.return_value={'error':{'message':'sk-secret-danger'}}
    with pytest.raises(BusinessError) as error:
        DeepSeekClient(keyed_user,transport=transport).complete([{'role':'user','content':'hi'}])
    assert error.value.code==code
    assert 'sk-secret' not in str(error.value)
    assert APIUsageRecord.objects.get().status=='FAILED'


def test_network_timeout_and_budget(keyed_user,settings):
    transport=Mock();transport.post.side_effect=requests.Timeout('sk-secret-danger')
    with pytest.raises(BusinessError) as error: DeepSeekClient(keyed_user,transport=transport).complete([{'role':'user','content':'hi'}])
    assert error.value.code=='LLM_TIMEOUT' and 'sk-secret' not in str(error.value)
    settings.LLM_DAILY_REQUEST_LIMIT=1
    with pytest.raises(BusinessError) as error: DeepSeekClient(keyed_user,transport=transport).complete([{'role':'user','content':'hi'}])
    assert error.value.code=='DAILY_BUDGET_EXCEEDED'
    assert transport.post.call_count==1


def test_missing_usage_not_invented(keyed_user):
    transport=Mock();reply=response();reply.json.return_value.pop('usage');transport.post.return_value=reply
    result=DeepSeekClient(keyed_user,transport=transport).complete([{'role':'user','content':'hi'}])
    assert result.usage.input_tokens is None
    assert APIUsageRecord.objects.get().input_tokens is None


def test_register_login_logout(client):
    reply=client.post('/accounts/register/',{'username':'newstudent','password1':'UniquePass-45678','password2':'UniquePass-45678'})
    assert reply.status_code==302 and User.objects.filter(username='newstudent').exists()
    assert client.get('/api/v1/ai/config/').status_code==200
    assert client.post('/accounts/logout/').status_code==302
    assert client.get('/api/v1/ai/config/').status_code==401


def test_api_config_never_exposes_keys(client,user):
    client.force_login(user)
    reply=client.post('/api/v1/ai/config/',data={'api_key':'sk-api-key-abcdefgh','default_tier':'deep','reasoning_effort':'high'},content_type='application/json')
    assert reply.status_code==200 and 'sk-api-key' not in reply.content.decode()
    assert client.delete('/api/v1/ai/config/').status_code==200
    assert not UserAPIConfig.objects.get(user=user).configured


def test_csrf_enforced(user):
    from django.test import Client
    client=Client(enforce_csrf_checks=True);client.force_login(user)
    assert client.post('/api/v1/ai/config/',data={},content_type='application/json').status_code==403


def test_upstream_model_mismatch_fails_explicitly(keyed_user):
    transport=Mock();transport.post.return_value=response()
    with pytest.raises(BusinessError) as exc:
        DeepSeekClient(keyed_user,transport=transport).complete([{'role':'user','content':'hi'}],tier='expert')
    assert exc.value.code=='MODEL_MISMATCH'
    assert APIUsageRecord.objects.get().output_tokens==2


def test_persisted_minute_rate_limit(keyed_user,settings):
    settings.LLM_REQUESTS_PER_MINUTE=1
    transport=Mock();transport.post.return_value=response()
    client=DeepSeekClient(keyed_user,transport=transport)
    client.complete([{'role':'user','content':'hi'}])
    with pytest.raises(BusinessError) as exc: client.complete([{'role':'user','content':'hi'}])
    assert exc.value.code=='RATE_LIMITED' and transport.post.call_count==1
    assert DailyAPIBudget.objects.get(user=keyed_user).requests==1


def test_personal_goal_saved_current_user_only(user,client):
    client.force_login(user)
    other=User.objects.create_user('othergoal')
    reply=client.post('/accounts/settings/',{'learning_goal':'掌握链表','api_key':'','default_tier':'fast','reasoning_effort':'high'})
    assert reply.status_code==302
    from apps.accounts.models import UserProfile
    assert UserProfile.objects.get(user=user).learning_goal=='掌握链表'
    assert not UserProfile.objects.filter(user=other).exists()
