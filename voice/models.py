from django.db import models

# Create your models here.

class VoiceGroupSize(models.Model):
    name = models.CharField(max_length = 100, unique=True)
    size = models.IntegerField(default = 1)