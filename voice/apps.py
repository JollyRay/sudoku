from django.apps import AppConfig
from django.db.utils import OperationalError


class VoiceConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'voice'

    def ready(self) -> None:

        try: 
            VoiceGroup = self.get_model('VoiceGroup') 
            VoiceGroup.objects.all().delete() # type: ignore
        except OperationalError: ...
