from django.db import models

# Create your models here.
# ===== apps/core/models.py =====
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class BaseModel(models.Model):
    """Modèle de base avec timestamps"""
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='%(class)s_created')

    class Meta:
        abstract = True


class RegulatoryEntity(models.Model):
    """Types d'entités réglementaires"""
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    color = models.CharField(max_length=7, default='#007bff')  # Couleur hex
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Entité Réglementaire"
        verbose_name_plural = "Entités Réglementaires"

    def __str__(self):
        return self.name