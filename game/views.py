from django.http import HttpRequest, HttpResponse
from django.urls import reverse_lazy
from django.views.generic.edit import FormView
from django.shortcuts import redirect, render

from .models import LobbySetting, UserSetting

from .forms import ConncetLobbyForm

# Create your views here.

def lobby(request: HttpRequest):
    nick = request.COOKIES.get('nick')
    if nick:
        room_code = request.session.get('room_code', False)
        if room_code:
            if not UserSetting.objects.filter(nick = nick, lobby__code = room_code).exists():
                is_first = request.session.get('is_first', False)

                return render(request, 'game/sudokuLobby.html', context = {'room_code': room_code, 'is_first': is_first})
    return redirect('create_lobby')

class CreateLobby(FormView):
    template_name = 'game/createLobby.html'
    success_url = reverse_lazy('lobby')
    form_class = ConncetLobbyForm

    def get_context_data(self, **kwargs):
        context = super().get_context_data()
        context['title'] = 'Lobby'
        return context
    
    def post(self, request: HttpRequest, *args, **kwargs):

        response = super().post(request, *args, **kwargs)
        form = self.form_class(request.POST)

        if form.is_valid():

            is_first = not LobbySetting.objects.filter(code = form.cleaned_data['code']).exists()

            request.session.update({'room_code': form.cleaned_data['code'], 'is_first': is_first})
            response.set_cookie('nick', request.POST['nick'], max_age = 3600)

        return response