from django.urls import path

from .views import *


urlpatterns = [
    path('room/<slug:name>', voice_lobby, name = 'voice_lobby'),
    path('hub', LobbyListView.as_view(), name = 'voice_hub')
]