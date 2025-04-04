from django.urls import path

from .views import *


urlpatterns = [
    path('<slug:name>', voice_lobby, name = 'voice_lobby')
]