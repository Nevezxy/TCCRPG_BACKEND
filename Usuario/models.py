from django.db import models
from django.contrib.auth.models import AbstractUser
from cloudinary.models import CloudinaryField
# Create your models here.

class Usuario(AbstractUser):
    foto = CloudinaryField('Foto', blank=True)
    
    def __str__(self):
        return self.username