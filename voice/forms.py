from django.forms import ModelForm, Textarea
from .models import VoiceGroup


class CreateRoomForm(ModelForm): # type: ignore
     
    class Meta:
        model = VoiceGroup
        fields = "__all__"
        widgets = {
            'description': Textarea(attrs={'cols': 80, 'rows': 8}),
        }