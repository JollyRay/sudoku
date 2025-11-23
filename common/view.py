from typing import Any
from django.http import HttpRequest
from common.stubs import CreateLobbyFormView

class CreateLobby(CreateLobbyFormView):

    def get_context_data(self, **kwargs: Any):
        context = super().get_context_data()
        context['title'] = 'Lobby'
        return context
    
    def post(self, request: HttpRequest, *args: Any, **kwargs: Any):

        response = super().post(request, *args, **kwargs)
        form = self.form_class(request.POST) # pyright: ignore[reportOptionalCall]

        if form.is_valid():

            request.session.update({'room_code': form.cleaned_data['code']})
            response.set_cookie('nick', request.POST['nick'], max_age = 3600)

        return response
