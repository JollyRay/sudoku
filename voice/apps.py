from django.apps import AppConfig
from django.db.utils import OperationalError


class VoiceConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'voice'

    def ready(self) -> None:

        try: 
            VoiceGroupSize = self.get_model('VoiceGroupSize')
            VoiceGroupSize.objects.all().delete()
        except OperationalError: ...
