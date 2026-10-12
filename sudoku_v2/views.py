from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render

from .forms import JoinLobbyForm


def join_lobby(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = JoinLobbyForm(request.POST)
        if form.is_valid():
            request.session["sudoku_v2_room"] = form.cleaned_data["room_name"]
            request.session["sudoku_v2_username"] = form.cleaned_data["username"]
            return redirect("sudoku_v2:lobby")
    else:
        form = JoinLobbyForm(
            initial={
                "username": request.session.get("sudoku_v2_username", ""),
            },
        )

    return render(
        request,
        "sudoku_v2/join.html",
        context={"form": form},
    )


def lobby(request: HttpRequest) -> HttpResponse:
    board_name = request.session.get("sudoku_v2_username")
    room = request.session.get("sudoku_v2_room")
    if not isinstance(board_name, str) or not board_name or not isinstance(room, str) or not room:
        return redirect("sudoku_v2:join")
    return render(
        request,
        "sudoku_v2/index.html",
        context={"bootstrap": {
            "username": board_name, "room": room,
        }},
    )
