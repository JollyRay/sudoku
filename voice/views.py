from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

def voice_lobby(request: HttpRequest, name: str):
    print(name)
    return render(request, 'voice/voiceLobby.html', context = {'title': f'WebRTC {name}', 'room_code': name})