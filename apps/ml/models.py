# apps/ml/models.py
from django.db import models
from apps.core.models import BaseModel
from apps.annotations.models import Annotation


class ModelTraining(BaseModel):
    '''Session d'entraînement du modèle'''

    STATUS_CHOICES = [
        ('pending', 'En attente'),
        ('running', 'En cours'),
        ('completed', 'Terminé'),
        ('failed', 'Échoué'),
    ]

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    # Données d'entraînement
    training_annotations = models.ManyToManyField(Annotation, related_name='training_sessions')
    validation_split = models.FloatField(default=0.2)

    # Paramètres du modèle
    model_parameters = models.JSONField(default=dict)

    # Résultats
    accuracy_score = models.FloatField(null=True, blank=True)
    precision_score = models.FloatField(null=True, blank=True)
    recall_score = models.FloatField(null=True, blank=True)
    f1_score = models.FloatField(null=True, blank=True)

    # Métriques détaillées par entité
    entity_metrics = models.JSONField(default=dict)

    class Meta:
        verbose_name = "Entraînement de Modèle"
        verbose_name_plural = "Entraînements de Modèles"


class ModelVersion(BaseModel):
    '''Version d'un modèle entraîné'''
    training = models.ForeignKey(ModelTraining, on_delete=models.CASCADE)
    version = models.CharField(max_length=50)
    model_path = models.CharField(max_length=500)  # Chemin vers le modèle sauvegardé
    is_active = models.BooleanField(default=False)

    # Performance
    benchmark_score = models.FloatField(null=True, blank=True)
    inference_time_ms = models.FloatField(null=True, blank=True)

    class Meta:
        verbose_name = "Version de Modèle"
        verbose_name_plural = "Versions de Modèles"
        unique_together = ['training', 'version']


class ExpertRule(BaseModel):
    '''Règles métier définies par les experts'''

    RULE_TYPES = [
        ('pattern', 'Pattern RegEx'),
        ('keyword', 'Mots-clés'),
        ('context', 'Contexte'),
        ('position', 'Position'),
    ]

    name = models.CharField(max_length=200)
    entity_type = models.ForeignKey('core.RegulatoryEntity', on_delete=models.CASCADE)
    rule_type = models.CharField(max_length=20, choices=RULE_TYPES)
    pattern = models.TextField()  # Pattern RegEx ou condition
    confidence_score = models.FloatField(default=1.0)
    is_active = models.BooleanField(default=True)

    # Statistiques d'utilisation
    usage_count = models.IntegerField(default=0)
    success_rate = models.FloatField(default=0.0)

    class Meta:
        verbose_name = "Règle Expert"
        verbose_name_plural = "Règles Experts"
