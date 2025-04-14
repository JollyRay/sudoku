from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.views.generic import ListView
from collections import namedtuple

from voice.forms import CreateRoomForm
from voice.models import VoiceGroup, VoiceMember

def voice_lobby(request: HttpRequest, name: str) -> HttpResponse:
    return render(request, 'voice/voiceLobby.html', context = {'title': f'WebRTC {name}', 'room_code': name})

        
class LobbyListView(ListView): # type: ignore
    model = VoiceGroup
    paginate_by = 15
    template_name = 'voice/voiceHub.html'
    queryset = VoiceGroup.objects.filter(voicemember__isnull=False).distinct()
    GroupInfo = namedtuple('GroupInfo', ['name', 'description', 'members'])
    form = CreateRoomForm
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        member_info_list = VoiceMember.objects.filter(voice_group__in = context['page_obj'].object_list).values_list('nick', 'voice_group__description', 'voice_group__name')
        member_data: dict[str, list[str]] = dict()
        member_descripton: dict[str, str] = dict()

        for member_nick, description, member_room in member_info_list:

            if member_data.get(member_room, False):
                member_data[member_room].append(member_nick)
            else:
                member_data[member_room] = [member_nick, ]

            if member_room not in member_descripton:
                member_descripton[member_room] = description

        context['group_info'] = [self.GroupInfo(room_name, member_descripton[room_name], ', '.join(members)) for room_name, members in member_data.items()]


        if len(self.request.POST):
            context['create_form'] = self.form(self.request.POST)
        else:
            context['create_form'] = self.form()


        return context
    
    def post(self, request: HttpRequest, *args, **kwargs):
        formset: CreateRoomForm = self.form(request.POST)

        if formset.is_valid():
            instance: VoiceGroup = formset.save()
            return HttpResponseRedirect(instance.get_absolute_url())

        return self.get(request, *args, **kwargs)