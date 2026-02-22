import json
import logging
from random import choices, randint, random
from typing import Any, Dict, Optional, Tuple
from django.db.models import (
    CharField,
    ManyToManyField,
    Manager,
    Model,
    IntegerField,
    TextChoices,
    JSONField,
)

from bunker.stub import ExtraParam

# Create your models here.

logger = logging.getLogger(__name__)


class Tag(Model):
    name = CharField(
        max_length=100,
        unique=True,
    )
    
    def __str__(self) -> str:
        return self.name
    
    class Meta:
        ordering = ['name']


class ColumnType(TextChoices):
    LIVING_CREATURE = 'l', 'living_creature'
    PHYSIQUE = 'y', 'physique'
    TRAIT = 't', 'trait'
    PROFESSION = 'p', 'profession'
    HEALTH = 'h', 'health'
    ENTHUSIASM = 'e', 'enthusiasm'
    FEAR = 'f', 'fear'
    INVENTORY = 'i', 'inventory'
    BACKPACK = 'b', 'backpack'
    ADDITIONAL_INFORMATION = 'a', 'additional_information'


class ParameterManager(Manager['Parameter']):
    def random(self, column_type: ColumnType) -> Tuple[str, Optional[str]]:
        query = self.filter(column_type=column_type).values('id', 'weight')
        prama_weight = [row['weight'] for row in query]
        ids = [row['id'] for row in query]

        random_id = choices(ids, weights=prama_weight, k=1)[0]
        select_param = self.get(id=random_id)
        return select_param.title, select_param.extra_param

    def get_character_set(self) -> list[str]:
        """
        Генерирует набор характеристик на основе доступных типов колонок.
        Метод проходит по всем типам колонок (ColumnType), получает параметры для каждого типа,
        обрабатывает дополнительные параметры (минимальные/максимальные значения или варианты выбора)
        и форматирует строки заголовков с использованием сгенерированных значений.
        Returns:
            list[str]: Список отформатированных строк характеристик, по одной для каждого типа колонки.
            В случае ошибки автоматически повторяет попытку получения набора.
        Raises:
            Исключения логируются, после чего метод вызывает себя рекурсивно.
        Note:
            Если в extra_param присутствуют 'min_value' и 'max_value', генерируется
            случайное целое число в этом диапазоне. Если присутствуют 'choices',
            выбирается один случайный элемент из предложенных вариантов.
        """

        try: 
            character_set: list[str] = []
            for column_type in ColumnType:          
                params = self.random(column_type=column_type)
                title: str = params[0]
                extra_param: Dict[str, ExtraParam] = {} if params[1] is None else json.loads(params[1])
                format_dict: Dict[str, Any] = {}
                for key, extra in extra_param.items():
                    if 'min_value' in extra and 'max_value' in extra:
                        format_dict[key] = randint(extra['min_value'], extra['max_value'])
                    elif 'choices' in extra:
                        format_dict[key] = choices(extra['choices'], k=1)[0]
                character_set.append(title.format(**format_dict))
        except Exception as e:
            logger.error(f"Error generating character set: {e}")
            return self.get_character_set()
        return character_set


class Parameter(Model):
    objects = ParameterManager()
    title = CharField(
        max_length=100,
        blank=False,
        null=False,
        unique=True,
    )
    column_type = CharField(
        max_length=1,
        choices=ColumnType.choices,
        null=False,
    )
    tags = ManyToManyField(
        Tag,
        related_name='parameter',
        blank=True,
    )
    weight = IntegerField(
        blank=False,
        null=False,
    )
    extra_param = JSONField(
        null=True,
    )

    def __str__(self) -> str:
        return f'{self.title} - {self.get_column_type_display()} - Wight({self.weight})' # pyright: ignore[reportAttributeAccessIssue]

