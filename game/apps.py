from django.apps import AppConfig
from django.db.utils import OperationalError

class GameConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'game'

    def ready(self) -> None:

        try: 
            LobbySetting = self.get_model('LobbySetting')
            LobbySetting.objects.all().delete()
        except OperationalError: ...

