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

class SudokuBoardManager(Manager):
    def random(self, **kwargs):
        query = self.filter(**kwargs).values('id')
        count = query.aggregate(count=Count('id'))['count']
        random_index = randint(0, count - 1)
        id = query[random_index]['id']
        return SudokuCell.objects.filter(board__id = id)

class SudokuBoard(Model):
    objects = SudokuBoardManager()
    difficulty = ForeignKey('Difficulty', on_delete = CASCADE, blank = False, null = False)

    class Meta:
        verbose_name = 'Доска'
        verbose_name_plural = 'Доски'

    def __str__(self) -> str:
        return f'Доска: {self.difficulty.name}'

class Difficulty(Model):

    class DifficultyName(TextChoices):
        EASY = 'easy'
        MEDIUM = 'medium'
        HARD = 'hard'

    name = CharField(
        max_length = 32,
        blank = False,
        null = False,
        choices = DifficultyName,
    )
    top_limit = IntegerField(blank = False, null = False)

    class Meta:
        unique_together = ('name',)
        verbose_name = 'Сложность'
        verbose_name_plural = 'Сложности'

    def __str__(self) -> str:
        return f'{self.name} limit - {self.top_limit}'

class SudokuCell(Model):
    board = ForeignKey('SudokuBoard', on_delete = CASCADE, blank = False, null = False)
    number = IntegerField(blank = False, null = False)
    value = IntegerField(blank = False, null = False)
    is_empty = BooleanField(blank = False, null = False, default = False)

    class Meta:
        unique_together = ('board', 'number')
        verbose_name = 'Ячейка'
        verbose_name_plural = 'Ячейки'