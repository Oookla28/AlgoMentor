from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from core.llm.model_registry import MODEL_TIERS


class RegisterForm(UserCreationForm):
    email = forms.EmailField(required=False,label='邮箱')
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('username','email')


class APIConfigForm(forms.Form):
    learning_goal = forms.CharField(label='个人学习目标',required=False,max_length=200,widget=forms.TextInput(attrs={'placeholder':'例如：掌握链表与 KMP，完成课程考核'}))
    api_key = forms.CharField(label='DeepSeek API Key',required=False,max_length=256,widget=forms.PasswordInput(render_value=False,attrs={'autocomplete':'new-password','placeholder':'输入新密钥；留空保留当前配置'}))
    default_tier = forms.ChoiceField(label='默认模型档位',choices=[(key,tier.label) for key,tier in MODEL_TIERS.items()])
    reasoning_effort = forms.ChoiceField(label='思考强度',choices=[('low','低 · low'),('high','高 · high'),('max','最大 · max')],initial='high')
