from django import forms


class JoinLobbyForm(forms.Form):
    username = forms.CharField(
        label="Имя",
        max_length=32,
    )
    room_name = forms.CharField(
        label="Название комнаты",
        max_length=32,
    )
