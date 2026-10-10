from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render

from .forms import JoinLobbyForm


def join_lobby(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = JoinLobbyForm(request.POST)
        if form.is_valid():
            request.session["room_code"] = form.cleaned_data["room_name"]
            response = redirect("sudoku_vibe:lobby")
            response.set_cookie(
                "nick",
                form.cleaned_data["username"],
                max_age=3600,
                samesite="Lax",
            )
            return response
    else:
        form = JoinLobbyForm(
            initial={"username": request.COOKIES.get("nick", "")},
        )

    return render(
        request,
        "sudoku_vibe/join.html",
        context={"form": form},
    )


def lobby(request: HttpRequest) -> HttpResponse:
    board_name = request.COOKIES.get("nick", "undefined")
    return render(
        request,
        "sudoku_vibe/index.html",
        context={"board_name": board_name},
    )
