from django.urls import path

from .views import *


urlpatterns = [
    path('create', CreateLobby.as_view(), name = 'create_lobby'),
    path('lobby', lobby, name = 'lobby')
]