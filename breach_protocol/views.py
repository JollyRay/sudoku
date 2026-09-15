from django.http import HttpRequest, HttpResponse
from django.shortcuts import render


def breach_protocol(request: HttpRequest) -> HttpResponse:
    return render(request, "breach_protocol/game.html")
