from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods
from core.exceptions import BusinessError
from core.http import api_endpoint,json_body
from core.llm.deepseek_client import DeepSeekClient
from core.llm.model_registry import model_options
from apps.accounts.forms import RegisterForm,APIConfigForm
from apps.accounts.services import credential_service
from apps.accounts.services.usage_service import monthly_usage


@require_http_methods(['GET','POST'])
def register(request):
    form = RegisterForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        from apps.accounts.services.profile_service import profile_for
        profile_for(user)
        login(request,user)
        return redirect('dashboard')
    return render(request,'accounts/register.html',{'form':form})


@login_required
@require_http_methods(['GET','POST'])
def settings_page(request):
    config = credential_service.get_config(request.user)
    from apps.accounts.services.profile_service import profile_for
    profile=profile_for(request.user)
    form = APIConfigForm(request.POST or None,initial={'default_tier':config.default_tier,'reasoning_effort':config.reasoning_effort,'learning_goal':profile.learning_goal})
    if request.method == 'POST':
        if request.POST.get('action') == 'delete':
            credential_service.delete_key(request.user)
            messages.success(request,'已删除个人 API Key。')
            return redirect('accounts:settings')
        if form.is_valid():
            try:
                credential_service.save_config(request.user,**form.cleaned_data)
                messages.success(request,'AI 配置已保存。请测试连接。')
                return redirect('accounts:settings')
            except BusinessError as exc:
                form.add_error(None,exc.message)
    public=credential_service.public_config(request.user)
    public['last_checked_at']=config.last_checked_at
    return render(request,'accounts/settings.html',{'form':form,'config':public,'usage':monthly_usage(request.user),'model_options':model_options()})


@api_endpoint(methods=('POST','DELETE','GET'))
def ai_config(request):
    if request.method == 'DELETE':
        credential_service.delete_key(request.user)
    elif request.method == 'POST':
        payload=json_body(request)
        form = APIConfigForm(payload)
        if not form.is_valid():
            from core.exceptions import ValidationError
            raise ValidationError('AI 配置格式无效，请检查密钥、模型和推理强度。')
        values=form.cleaned_data
        if 'learning_goal' not in payload: values.pop('learning_goal',None)
        credential_service.save_config(request.user,**values)
    return credential_service.public_config(request.user)


@api_endpoint(methods=('POST',))
def test_connection(request):
    try:
        result = DeepSeekClient(request.user,purpose='connection_test').complete([{'role':'user','content':'Reply only OK.'}],max_tokens=32)
        credential_service.record_connection_status(request.user,'CONNECTED')
        return {'connected':True,'inference_verified':True,'selected_model':result.model,'usage':{'input_tokens':result.usage.input_tokens,'output_tokens':result.usage.output_tokens},'message':'当前档位已完成真实推理调用。其他档位和后续余额需分别验证。'}
    except BusinessError as exc:
        credential_service.record_connection_status(request.user,exc.code)
        raise


@api_endpoint()
def ai_models(request):
    return {'models':model_options()}
