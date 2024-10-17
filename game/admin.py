from django.contrib import admin
from .models import *

# Register your models here.

admin.site.register(LobbySetting)
admin.site.register(UserSetting)
admin.site.register(SudokuBoard)
admin.site.register(SudokuCell)
admin.site.register(Difficulty)