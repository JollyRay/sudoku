from typing import Any

from django import forms

from .storage import SudokuVibeStorage


class JoinLobbyForm(forms.Form):
    username = forms.CharField(
        label="Имя",
        max_length=32,
    )
    room_name = forms.CharField(
        label="Название комнаты",
        max_length=32,
    )

    def clean(self) -> dict[str, Any]:
        cleaned_data = super().clean() or {}
        username = cleaned_data.get("username")
        room_name = cleaned_data.get("room_name")

        if (
            username
            and room_name
            and SudokuVibeStorage().is_username_active(room_name, username)
        ):
            raise forms.ValidationError(
                "Пользователь с таким именем уже находится в этой комнате.",
                code="duplicate_lobby_username",
            )

        return cleaned_data
