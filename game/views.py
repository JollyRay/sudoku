from django.http import HttpRequest, HttpResponse
from django.urls import reverse_lazy
from django.views.generic.edit import FormView
from django.shortcuts import redirect, render

from .models import Difficulty, LobbySetting, UserSetting

from .forms import ConncetLobbyForm

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

            request.session.update({'room_code': form.cleaned_data['code']})
            response.set_cookie('nick', request.POST['nick'], max_age = 3600)

        return response