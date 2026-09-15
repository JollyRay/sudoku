from django.urls import path

from .views import *


urlpatterns = [
    path('hub', BunkerCreateLobby.as_view(), name = 'bunber_hub'),
    path('lobby', lobby, name = 'bunker_lobby')
]