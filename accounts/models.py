# accounts/models.py
from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    ROLE_CHOICES = [
        ('admin', 'Administrateur'),
        ('metadonneur', 'Métadonneur'),
        ('annotateur', 'Annotateur'),
        ('expert', 'Expert Métier'),
    ]

    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='annotateur')
    phone = models.CharField(max_length=20, blank=True)
    speciality = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active_user = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Utilisateur"
        verbose_name_plural = "Utilisateurs"