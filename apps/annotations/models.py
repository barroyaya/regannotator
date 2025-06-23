# ===== apps/annotations/models.py =====
from django.contrib.auth.models import User
from django.db import models
from django.contrib.postgres.fields import JSONField
from apps.core.models import BaseModel, RegulatoryEntity
from apps.documents.models import DocumentSentence


class AnnotationSession(BaseModel):
    """Session d'annotation pour un document"""
    document = models.ForeignKey('documents.Document', on_delete=models.CASCADE)
    llm_model = models.CharField(max_length=100, default='mistral-7b-instruct')
    parameters = models.JSONField(default=dict)  # Paramètres du LLM utilisés
    status = models.CharField(max_length=20, choices=[
        ('running', 'En cours'),
        ('completed', 'Terminé'),
        ('failed', 'Échoué'),
    ], default='running')

    class Meta:
        verbose_name = "Session d'annotation"
        verbose_name_plural = "Sessions d'annotation"


class Annotation(BaseModel):
    """Annotation d'une entité réglementaire dans une phrase"""

    ANNOTATION_SOURCES = [
        ('llm', 'LLM Automatique'),
        ('expert', 'Expert Humain'),
        ('rule', 'Règle Métier'),
    ]

    VALIDATION_STATUS = [
        ('pending', 'En attente'),
        ('validated', 'Validé'),
        ('rejected', 'Rejeté'),
        ('modified', 'Modifié'),
    ]

    sentence = models.ForeignKey(DocumentSentence, on_delete=models.CASCADE, related_name='annotations')
    entity_type = models.ForeignKey(RegulatoryEntity, on_delete=models.CASCADE)
    text_value = models.CharField(max_length=500)  # Texte de l'entité extraite
    start_position = models.IntegerField()  # Position de début dans la phrase
    end_position = models.IntegerField()  # Position de fin dans la phrase
    confidence_score = models.FloatField(default=0.0)  # Score de confiance du LLM

    source = models.CharField(max_length=10, choices=ANNOTATION_SOURCES, default='llm')
    validation_status = models.CharField(max_length=20, choices=VALIDATION_STATUS, default='pending')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='created_annotations')
    validated_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True,
                                     related_name='validated_annotations')
    validated_at = models.DateTimeField(null=True, blank=True)

    # Métadonnées supplémentaires
    metadata = models.JSONField(default=dict)

    class Meta:
        verbose_name = "Annotation"
        verbose_name_plural = "Annotations"
        ordering = ['sentence', 'start_position']

    def __str__(self):
        return f"{self.entity_type.name}: {self.text_value}"


class ExpertFeedback(BaseModel):
    """Feedback d'expert sur les annotations"""
    annotation = models.ForeignKey(Annotation, on_delete=models.CASCADE, related_name='feedbacks')
    expert = models.ForeignKey('auth.User', on_delete=models.CASCADE)
    feedback_type = models.CharField(max_length=20, choices=[
        ('correction', 'Correction'),
        ('suggestion', 'Suggestion'),
        ('validation', 'Validation'),
    ])
    comment = models.TextField()
    suggested_value = models.CharField(max_length=500, blank=True)

    class Meta:
        verbose_name = "Feedback Expert"
        verbose_name_plural = "Feedbacks Experts"
