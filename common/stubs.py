from typing import TYPE_CHECKING

from django.views.generic.edit import FormView

from common.forms import ConncetLobbyForm

if TYPE_CHECKING:
    CreateLobbyFormView = FormView[ConncetLobbyForm]
else:
    CreateLobbyFormView = FormView