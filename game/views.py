from typing import Any
from django.http import HttpRequest
from django.urls import reverse_lazy
from django.shortcuts import redirect, render

from .models import Difficulty, UserSetting


# Create your views here.

def lobby(request: HttpRequest):
    nick = request.COOKIES.get('nick')
    if nick:
        room_code = request.session.get('room_code', False)
        if room_code:
            if not UserSetting.objects.filter(nick = nick, lobby__code = room_code).exists():
                difficulty_names = (difficulty['name'] for difficulty in Difficulty.objects.all().order_by('top_limit').values('name'))

                return render(request, 'game/sudokuLobby.html', context = {'room_code': room_code, 'difficulty_names': difficulty_names, 'nick': nick})
    return redirect('create_lobby')

from common.forms import ConncetLobbyForm
from common.view import CreateLobby

class SudokuCreateLobby(CreateLobby):
    template_name = 'game/createLobby.html'
    success_url = reverse_lazy('lobby')
    form_class = ConncetLobbyForm
