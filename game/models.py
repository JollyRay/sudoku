from typing import Any
from django.db.models import *
from random import randint, sample
from sys import maxsize

# Create your models here.

def genereate_seed() -> int:
    return randint(1, maxsize) 

class LobbySetting(Model):

    code = CharField(max_length = 32, blank = False, null = False, unique = True)
    seed = BigIntegerField(default = genereate_seed)
    time_create = DateTimeField(auto_now = True)

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
    board = ManyToManyField('SudokuBoard')      # type: ignore
                                                # No idea how to annotate. ManyToManyDescriptor? ManyToManyField? ManyToManyManager? BaseManager?
    time_from = DateTimeField(auto_now = False, auto_now_add = False, null = True, default = None)
    time_to = DateTimeField(auto_now = False, auto_now_add = False, null = True, default = None)

    class Meta:
        unique_together = ('nick', 'lobby')
        verbose_name = 'Канал'
        verbose_name_plural = 'Каналы'

        indexes = [
            Index(fields=['nick', 'lobby']),
        ]

    def __str__(self):
        return f'Lobby: {self.lobby.code} - {self.nick}'

from game.stubs import BorderIdDict

class SudokuBoardManager(Manager['SudokuBoard']):
    def random(self, filter: dict[str, Any] = {}, exclude: dict[str, Any] = {}) -> QuerySet['SudokuCell'] | None:
        query = self.filter(**filter).exclude(**exclude).values('id')
        
        return self._collect_cell_by_id(query)
    
    def random_for_user(self, room_code: str, nick: str, difficulty_name: str) -> QuerySet['SudokuCell'] | None: 
        """
        Get 81 (or other by the number of cells on the board) cells

        :param room_code: lobby name
        :param nick: nick of lobby user
        :param difficulty_name: difficulty of board. On defualt 'easy', 'medium', 'hard'.
        :return: QuerySet[SudokuCell] for one board 

        P.S.
        random_for_user equivalent to random with arguments:
            filter = {'difficulty__name' = difficulty_name},
            exclude = {'usersetting__nick': nick, 'usersetting__lobby__code' = room_code)}
        """
        query = self.filter(difficulty__name = difficulty_name).exclude(usersetting__nick = nick, usersetting__lobby__code = room_code).values('id')

        return self._collect_cell_by_id(query)

    def _collect_cell_by_id(self, query: QuerySet['SudokuBoard', BorderIdDict]) -> QuerySet['SudokuCell'] | None:
        count = query.aggregate(count=Count('id'))['count']
        if count == 0:
            return None
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

class SudokuCellManager(Manager['SudokuCell']):

    def get_random_empty_cell_id(self, board_id, quantity) -> list[int]:
        empty_cell = self.filter(board_id = board_id, is_empty = True).values('id')
        empty_cells_id: list[int] = list(map(lambda cell: cell['id'], empty_cell))
        try: 
            return sample(empty_cells_id, k = quantity)
        except ValueError:
            return empty_cells_id

class SudokuCell(Model):
    objects = SudokuCellManager()

    board = ForeignKey('SudokuBoard', on_delete = CASCADE, blank = False, null = False)
    number = IntegerField(blank = False, null = False)
    value = IntegerField(blank = False, null = False)
    is_empty = BooleanField(blank = False, null = False, default = False)

    class Meta:
        unique_together = ('board', 'number')
        verbose_name = 'Ячейка'
        verbose_name_plural = 'Ячейки'

        indexes = [
            Index(fields=['board', 'number']),
        ]

class UserCell(Model):
    user = ForeignKey('UserSetting', on_delete = CASCADE, blank = False, null = False)
    cell = ForeignKey('SudokuCell', on_delete = CASCADE, blank = False, null = False)
    value = IntegerField(blank = False, null = False, default = 0)
    bonus_name = CharField(max_length = 32, blank = False, null = True)
    was_equal = BooleanField(blank = False, null = False, default = False)

    class Meta:
        unique_together = ('user', 'cell')
        verbose_name = 'Пользовательская ячейка'
        verbose_name_plural = 'Пользовательские ячейки'