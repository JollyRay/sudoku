from django.http import HttpRequest, HttpResponse
from django.shortcuts import render


def index(request: HttpRequest) -> HttpResponse:
    board_name = request.COOKIES.get("nick", "undefined")
    return render(
        request,
        "sudoku_vibe/index.html",
        context={"board_name": board_name},
    )
