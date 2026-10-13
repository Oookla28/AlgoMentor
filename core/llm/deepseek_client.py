"""DeepSeek Chat Completions adapter using requests; never emits upstream bodies or keys."""
import json
import time
from urllib.parse import urlparse
import requests
from django.conf import settings
from apps.accounts.models import APIUsageRecord
from apps.accounts.services.credential_service import get_api_key, get_config, record_connection_status
from apps.accounts.services.usage_service import reserve_request, settle_request
from core.exceptions import LLMProviderError, ValidationError
from core.llm.model_registry import get_tier
from core.llm.provider import LLMResult, TokenUsage


class DeepSeekClient:
    def __init__(self, user, transport=None, purpose='chat', deadline: float | None = None):
        self.user = user
        self.transport = transport or requests.Session()
        self.purpose = purpose
        self.deadline = deadline

    def complete(self, messages: list[dict], tier: str | None = None, tools: list[dict] | None = None, max_tokens: int | None = None, **kwargs) -> LLMResult:
        config = get_config(self.user)
        selected = get_tier(tier or config.default_tier)
        key = get_api_key(self.user)
        if not messages or len(messages) > 80:
            raise ValidationError('对话内容为空或超出上下文条数限制。')
        payload = selected.payload(config.reasoning_effort if selected.thinking else None)
        output_limit = min(max_tokens or getattr(settings,'LLM_MAX_TOKENS',2048),getattr(settings,'LLM_MAX_TOKENS',2048))
        if output_limit < 1:
            raise ValidationError('输出长度必须为正数。')
        payload.update(messages=messages,max_tokens=output_limit,stream=False)
        if tools:
            payload['tools'] = tools
        encoded = json.dumps(payload,ensure_ascii=False)
        if len(encoded.encode()) > getattr(settings,'LLM_MAX_INPUT_BYTES',120000):
            raise ValidationError('对话内容过长，请创建新会话。')
        # Byte length is a conservative token upper bound, including tool schemas.
        budget_id,reserved = reserve_request(self.user,len(encoded.encode())+output_limit)
        record = APIUsageRecord.objects.create(user=self.user,model=selected.model,tier=selected.key,purpose=self.purpose)
        start = time.monotonic()
        actual = None
        try:
            url = getattr(settings,'DEEPSEEK_BASE_URL','https://api.deepseek.com').rstrip('/')
            parsed = urlparse(url)
            if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
                raise LLMProviderError('服务器 AI 接口地址配置无效。',code='PROVIDER_CONFIGURATION_ERROR',status_code=503)
            timeout = float(getattr(settings,'LLM_TIMEOUT',45))
            if self.deadline is not None:
                timeout = min(timeout,max(0.1,self.deadline-time.monotonic()))
                if self.deadline <= time.monotonic():
                    raise LLMProviderError('AI 任务已超时。',code='LLM_TIMEOUT',status_code=504)
            response = self.transport.post(url+'/chat/completions',headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'},json=payload,timeout=(min(10,timeout/2),max(0.1,timeout-min(10,timeout/2))),allow_redirects=False)
            errors = {401:('密钥无效，请重新配置。','INVALID_API_KEY',401),402:('DeepSeek 余额不足，请在服务商账户充值。','INSUFFICIENT_BALANCE',402),429:('DeepSeek 请求限流，请稍后再试。','PROVIDER_RATE_LIMITED',429),404:('所选模型或接口暂不可用。','MODEL_UNAVAILABLE',502)}
            if response.status_code in errors:
                message,code,status = errors[response.status_code]
                raise LLMProviderError(message,code=code,status_code=status)
            if response.status_code >= 300:
                raise LLMProviderError('DeepSeek 服务暂不可用，请稍后重试。',code='PROVIDER_UNAVAILABLE',status_code=502)
            body = response.json()
            message = body['choices'][0]['message']
            returned_model = body.get('model',selected.model)
            usage_data = body.get('usage') or {}
            def token(name):
                value = usage_data.get(name)
                return value if isinstance(value,int) and not isinstance(value,bool) and value >= 0 else None
            usage = TokenUsage(token('prompt_tokens'),token('completion_tokens'),token('total_tokens'))
            actual = usage.total_tokens if usage.total_tokens is not None else ((usage.input_tokens+usage.output_tokens) if usage.input_tokens is not None and usage.output_tokens is not None else None)
            record.input_tokens = usage.input_tokens
            record.output_tokens = usage.output_tokens
            record.model = returned_model
            allowed_models = {'deepseek-flash': {'deepseek-flash','deepseek-v4.1-flash'}, 'deepseek-v4-pro': {'deepseek-v4-pro','deepseek-v4-pro-0813'}}
            if returned_model not in allowed_models.get(selected.model,{selected.model}):
                raise LLMProviderError('上游返回的模型与所选档位不一致；系统已停止回答，请检查接口配置。',code='MODEL_MISMATCH',status_code=502)
            record.status = 'SUCCESS'
            return LLMResult(text=message.get('content') or '',usage=usage,model=returned_model,tool_calls=tuple(message.get('tool_calls') or []),reasoning_content=message.get('reasoning_content') or '',finish_reason=body['choices'][0].get('finish_reason',''))
        except requests.Timeout:
            record.status = 'FAILED'; record.error_code = 'LLM_TIMEOUT'
            raise LLMProviderError('DeepSeek 请求超时，请稍后重试。',code='LLM_TIMEOUT',status_code=504) from None
        except requests.RequestException:
            record.status = 'FAILED'; record.error_code = 'PROVIDER_NETWORK_ERROR'
            raise LLMProviderError('无法连接 DeepSeek，请检查网络或稍后重试。',code=record.error_code,status_code=503) from None
        except (ValueError,KeyError,IndexError,TypeError):
            record.status = 'FAILED'; record.error_code = 'INVALID_PROVIDER_RESPONSE'
            raise LLMProviderError('DeepSeek 返回了无效响应。',code=record.error_code) from None
        except LLMProviderError as exc:
            record.status = 'FAILED'; record.error_code = exc.code
            raise
        finally:
            record.duration_ms = int((time.monotonic()-start)*1000)
            record.save(update_fields=['model','input_tokens','output_tokens','status','error_code','duration_ms'])
            # Failures retain their conservative reservation: usage may exist upstream.
            settle_request(budget_id,reserved,actual)
            record_connection_status(self.user,record.error_code if record.status=='FAILED' else record.status)
