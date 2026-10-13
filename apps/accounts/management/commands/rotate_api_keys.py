from django.core.management.base import BaseCommand,CommandError
from apps.accounts.models import UserAPIConfig
from core.security.encryption import rotate_secret
from core.exceptions import BusinessError

class Command(BaseCommand):
    help='用 APP_ENCRYPTION_KEY 重加密已配置密钥；旧密钥需暂存 APP_ENCRYPTION_PREVIOUS_KEYS。'
    def handle(self,*args,**options):
        count=0
        try:
            for config in UserAPIConfig.objects.exclude(encrypted_api_key='').iterator():
                config.encrypted_api_key=rotate_secret(config.encrypted_api_key)
                config.save(update_fields=['encrypted_api_key','updated_at']);count+=1
        except BusinessError as exc:
            raise CommandError(exc.message) from None
        self.stdout.write(f'已完成 {count} 个账户的密钥密文轮换。')
