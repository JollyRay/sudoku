from django.urls import path

from .views import breach_protocol


app_name = "breach_protocol"

urlpatterns = [
    path("", breach_protocol, name="game"),
]
