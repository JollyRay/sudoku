from django.urls import re_path

from .consumers import SudokuV2Consumer


websocket_urlpatterns = [
    re_path(r"ws/sudoku-v2/$", SudokuV2Consumer.as_asgi()),
]
