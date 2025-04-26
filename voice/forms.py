from django.forms import Textarea
from .models import VoiceGroup
from .stubs import VoiceGroupForm

class CreateRoomForm(VoiceGroupForm):
     
    class Meta:
        model = VoiceGroup
        fields = "__all__"
        widgets = {
            'description': Textarea(attrs={'cols': 80, 'rows': 8}),
        }