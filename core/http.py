import functools
import json
import logging
import uuid
from django.http import JsonResponse
from django.http.response import HttpResponseBase
from django.core.exceptions import ObjectDoesNotExist
from core.exceptions import BusinessError, ValidationError

logger = logging.getLogger('algomentor')


def json_body(request) -> dict:
    try:
        value = json.loads(request.body or b'{}')
    except (ValueError, UnicodeDecodeError):
        raise ValidationError('请求必须为有效 JSON。')
    if not isinstance(value, dict):
        raise ValidationError('请求内容必须为 JSON 对象。')
    return value


def api_endpoint(methods=('GET',), authenticated=True):
    def decorate(view):
        @functools.wraps(view)
        def wrapped(request, *args, **kwargs):
            request_id = uuid.uuid4().hex
            error = None
            if request.method not in methods:
                error = ('METHOD_NOT_ALLOWED', '该接口不支持此请求方法。', 405)
            elif authenticated and not request.user.is_authenticated:
                error = ('AUTHENTICATION_REQUIRED', '请先登录。', 401)
            if error is None:
                try:
                    data = view(request, *args, **kwargs)
                    if isinstance(data, HttpResponseBase):
                        return data
                    return JsonResponse({'success': True, 'data': data, 'request_id': request_id}, json_dumps_params={'ensure_ascii': False})
                except BusinessError as exc:
                    error = (exc.code, exc.message, exc.status_code)
                    logger.warning('request=%s code=%s view=%s', request_id, exc.code, view.__name__)
                except ObjectDoesNotExist:
                    error = ('NOT_FOUND', '记录不存在或不属于当前用户。', 404)
                except Exception as exc:
                    # Never log upstream exception text or request body: both may contain credentials.
                    logger.error('request=%s view=%s exception_type=%s', request_id, view.__name__, type(exc).__name__)
                    error = ('INTERNAL_ERROR', '处理失败，请稍后重试，并向管理员提供请求编号。', 500)
            return JsonResponse({'success': False, 'error': {'code': error[0], 'message': error[1]}, 'request_id': request_id}, status=error[2])
        return wrapped
    return decorate
