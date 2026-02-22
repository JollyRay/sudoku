from django.urls import re_path

from . import consumers

websocket_urlpatterns = [
    re_path(
        route=r"ws/bunker/(?P<room_name>\w+)/$",
        view=consumers.BunkerConsumer.as_asgi(),
        name="bunker",
    ),
]