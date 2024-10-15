from django.urls import re_path

from . import consumers

websocket_urlpatterns = [
    re_path(r"ws/sudoku/(?P<room_name>\w+)/$", consumers.SudokuConsumer.as_asgi()),
]