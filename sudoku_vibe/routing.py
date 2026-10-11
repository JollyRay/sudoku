from django.urls import re_path

from .consumers import SudokuVibeConsumer


websocket_urlpatterns = [
    re_path(r"ws/sudoku-vibe/$", SudokuVibeConsumer.as_asgi()),
]
