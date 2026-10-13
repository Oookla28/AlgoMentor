from django.utils import timezone


def current_time() -> dict:
    now=timezone.localtime()
    return {'iso8601':now.isoformat(),'timezone':str(now.tzinfo),'date':now.date().isoformat(),'weekday':now.strftime('%A')}
