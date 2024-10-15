from django.forms import *
from .models import UserSetting

class ConncetLobbyForm(Form):
    nick = CharField()
    code = CharField(widget = PasswordInput(), max_length = 32)

    def clean(self):

        try:
            nick = self.cleaned_data['nick']
            lobby_code = self.cleaned_data['code']
            UserSetting.objects.get(nick = nick, lobby__code = lobby_code)
            raise ValidationError('This user is in the room', code = 'not unique')

        except UserSetting.DoesNotExist:
            return self.cleaned_data