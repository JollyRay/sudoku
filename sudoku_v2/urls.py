from django.urls import path

from .views import join_lobby, lobby


app_name = "sudoku_v2"

urlpatterns = [
    path("", join_lobby, name="join"),
    path("lobby", lobby, name="lobby"),
]
