from django.db.models import *
from random import randint
from sys import maxsize

# Create your models here.

def genereate_seed():
    return randint(1, maxsize) 

class LobbySetting(Model):

    code = CharField(max_length = 32, blank = False, null = False, unique = True)
    seed = BigIntegerField(default = genereate_seed)
    time_create = DateField(auto_now = True)

    class Meta:
        verbose_name = 'Лобби'
        verbose_name_plural = 'Лобби'

        indexes = [
            Index(fields=['code', ]),
        ]

    def __str__(self):
        return f'Lobby: {self.code} Seed: {self.seed} | {self.time_create}'
    
class UserSetting(Model):
    nick = CharField(max_length = 32, blank = False, null = False)
    lobby = ForeignKey('LobbySetting', on_delete = CASCADE, blank = False, null = False)
    user_seed = BigIntegerField(blank = True, null = True)

    class Meta:
        unique_together = ('nick', 'lobby',)
        verbose_name = 'Канал'
        verbose_name_plural = 'Каналы'

    def __str__(self):
        return f'Lobby: {self.lobby.code} - {self.nick}'