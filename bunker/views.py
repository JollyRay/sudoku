from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse_lazy

from common.forms import ConncetLobbyForm
from common.view import CreateLobby


# Create your views here.

class BunkerCreateLobby(CreateLobby):
    template_name = 'bunker/hub.html'
    success_url = reverse_lazy('bunker_lobby')
    form_class = ConncetLobbyForm


def lobby(request: HttpRequest) -> HttpResponse:
    nick = request.COOKIES.get('nick')
    room_code = request.session.get('room_code', False)
    if nick and room_code:
        return render(request, 'bunker/lobby.html', context = {'room_code': room_code, 'nick': nick})
    return redirect('bunber_hub')