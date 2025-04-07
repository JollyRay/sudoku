from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

def voice_lobby(request: HttpRequest, name: str):
    return render(request, 'voice/voiceLobby.html', context = {'title': f'WebRTC {name}', 'room_code': name})