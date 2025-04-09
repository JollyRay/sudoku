from django.db import models

# Create your models here.

class VoiceGroup(models.Model):
    name = models.CharField(max_length = 100, unique=True, blank = False, null = False)

    class Meta:
        indexes = [
            models.Index(fields=['name', ]),
        ]

class VoiceMember(models.Model):
    nick = models.CharField(max_length = 100, blank = False, null = False)
    voice_group = models.ForeignKey(VoiceGroup, on_delete = models.CASCADE, blank = False, null = False)
    has_screen_sream = models.BooleanField(default = False, blank = False, null = False)

    class Meta:
        unique_together = ('nick', 'voice_group')
        verbose_name = 'Участник войса'
        verbose_name_plural = 'Участники войса'