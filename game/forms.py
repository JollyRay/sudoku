from django.forms import *
from .models import UserSetting

class ConncetLobbyForm(Form):
    nick = CharField(
        max_length = 32,
        widget = TextInput(
            attrs = {
                'onkeydown': "return /[a-z0-9]/i.test(event.key)"
            }
        )
    )
    code = CharField(widget = PasswordInput(), max_length = 32)

    def clean(self):

        try:
            nick = self.cleaned_data['nick']
            lobby_code = self.cleaned_data['code']

            if not nick.isascii() or not lobby_code.isascii():
                raise ValidationError('Fields must contain only Latin letters or numbers', code = 'not ascii')

            UserSetting.objects.get(nick = nick, lobby__code = lobby_code)
            raise ValidationError('This user is in the room', code = 'not unique')

        except UserSetting.DoesNotExist:
            return self.cleaned_data