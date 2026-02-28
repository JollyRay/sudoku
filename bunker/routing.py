from django.urls import re_path

from . import consumers

websocket_urlpatterns = [
    re_path(
        route=r"ws/bunker/(?P<room_name>\w+)/$",
        view=consumers.ClientEventService.as_asgi(),
        name="bunker",
    ),
]