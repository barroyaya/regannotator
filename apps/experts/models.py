from django.db import models
from django.contrib.auth.models import User
from apps.core.models import BaseModel, RegulatoryEntity


class ExpertProfile(BaseModel):
    """Profil d'un expert en réglementation"""

    EXPERTISE_LEVELS = [
        ('junior', 'Junior (< 2 ans)'),
        ('confirmed', 'Confirmé (2-5 ans)'),
        ('senior', 'Senior (5-10 ans)'),
        ('expert', 'Expert (> 10 ans)'),
    ]

    SPECIALIZATIONS = [
        ('regulatory_affairs', 'Affaires Réglementaires'),
        ('clinical_research', 'Recherche Clinique'),
        ('pharmacovigilance', 'Pharmacovigilance'),
        ('quality_assurance', 'Assurance Qualité'),
        ('medical_affairs', 'Affaires Médicales'),
        ('legal_compliance', 'Conformité Légale'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='expert_profile')
    expertise_level = models.CharField(max_length=20, choices=EXPERTISE_LEVELS, default='junior')
    specializations = models.JSONField(default=list)  # Liste des spécialisations

    # Informations professionnelles
    company = models.CharField(max_length=200, blank=True)
    position = models.CharField(max_length=200, blank=True)
    years_experience = models.IntegerField(default=0)
    certifications = models.TextField(blank=True)

    # Préférences d'annotation
    preferred_entities = models.ManyToManyField(RegulatoryEntity, blank=True, related_name='preferred_by_experts')
    annotation_speed = models.CharField(max_length=20, choices=[
        ('slow', 'Minutieux'),
        ('normal', 'Normal'),
        ('fast', 'Rapide'),
    ], default='normal')

    # Statistiques
    total_annotations_validated = models.IntegerField(default=0)
    total_feedbacks_given = models.IntegerField(default=0)
    average_validation_time = models.FloatField(default=0.0)  # en secondes
    accuracy_score = models.FloatField(default=0.0)  # score de précision

    # Disponibilité
    is_active = models.BooleanField(default=True)
    last_activity = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Profil Expert"
        verbose_name_plural = "Profils Experts"

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username} - {self.get_expertise_level_display()}"

    @property
    def validation_rate(self):
        """Taux de validation (validées / total traité)"""
        if self.total_annotations_validated == 0:
            return 0
        from apps.annotations.models import Annotation
        total_processed = Annotation.objects.filter(validated_by=self.user).count()
        if total_processed == 0:
            return 0
        return (self.total_annotations_validated / total_processed) * 100

    def update_statistics(self):
        """Mettre à jour les statistiques de l'expert"""
        from apps.annotations.models import Annotation
        from apps.annotations.models import ExpertFeedback
        from django.utils import timezone

        # Compter les annotations validées
        validated_annotations = Annotation.objects.filter(
            validated_by=self.user,
            validation_status='validated'
        )
        self.total_annotations_validated = validated_annotations.count()

        # Compter les feedbacks donnés
        self.total_feedbacks_given = ExpertFeedback.objects.filter(expert=self.user).count()

        # Calculer le temps moyen de validation (simulation)
        if self.total_annotations_validated > 0:
            self.average_validation_time = 45.0  # Simulation : 45 secondes en moyenne

        # Calculer le score de précision (simulation basée sur les feedbacks positifs)
        if self.total_feedbacks_given > 0:
            self.accuracy_score = min(85 + (self.years_experience * 2), 98)  # Score simulé

        self.last_activity = timezone.now()
        self.save()


class ExpertSpecialty(BaseModel):
    """Spécialités des experts par entité réglementaire"""
    expert = models.ForeignKey(ExpertProfile, on_delete=models.CASCADE, related_name='specialties')
    entity_type = models.ForeignKey(RegulatoryEntity, on_delete=models.CASCADE)
    proficiency_level = models.IntegerField(default=1, choices=[
        (1, 'Débutant'),
        (2, 'Intermédiaire'),
        (3, 'Avancé'),
        (4, 'Expert'),
        (5, 'Référent'),
    ])
    annotations_count = models.IntegerField(default=0)
    success_rate = models.FloatField(default=0.0)

    class Meta:
        verbose_name = "Spécialité Expert"
        verbose_name_plural = "Spécialités Experts"
        unique_together = ['expert', 'entity_type']


class ExpertTask(BaseModel):
    """Tâches assignées aux experts"""

    TASK_TYPES = [
        ('validation', 'Validation d\'annotations'),
        ('review', 'Révision de document'),
        ('training', 'Formation de modèle'),
        ('quality_check', 'Contrôle qualité'),
    ]

    STATUS_CHOICES = [
        ('pending', 'En attente'),
        ('in_progress', 'En cours'),
        ('completed', 'Terminée'),
        ('cancelled', 'Annulée'),
    ]

    PRIORITY_CHOICES = [
        ('low', 'Basse'),
        ('normal', 'Normale'),
        ('high', 'Haute'),
        ('urgent', 'Urgente'),
    ]

    expert = models.ForeignKey(ExpertProfile, on_delete=models.CASCADE, related_name='tasks')
    task_type = models.CharField(max_length=20, choices=TASK_TYPES)
    title = models.CharField(max_length=200)
    description = models.TextField()
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='normal')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    # Références vers les objets concernés
    document = models.ForeignKey('documents.Document', on_delete=models.CASCADE, null=True, blank=True)
    annotations = models.ManyToManyField('annotations.Annotation', blank=True)

    # Dates
    due_date = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    # Résultats
    result_notes = models.TextField(blank=True)
    quality_score = models.FloatField(null=True, blank=True)

    class Meta:
        verbose_name = "Tâche Expert"
        verbose_name_plural = "Tâches Experts"
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} - {self.expert.user.username}"


class ExpertSession(BaseModel):
    """Session de travail d'un expert"""
    expert = models.ForeignKey(ExpertProfile, on_delete=models.CASCADE, related_name='sessions')
    start_time = models.DateTimeField(auto_now_add=True)
    end_time = models.DateTimeField(null=True, blank=True)

    # Activités de la session
    annotations_validated = models.IntegerField(default=0)
    annotations_rejected = models.IntegerField(default=0)
    feedbacks_created = models.IntegerField(default=0)
    documents_reviewed = models.IntegerField(default=0)

    # Métadonnées
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)

    class Meta:
        verbose_name = "Session Expert"
        verbose_name_plural = "Sessions Experts"

    @property
    def duration_minutes(self):
        if self.end_time:
            delta = self.end_time - self.start_time
            return delta.total_seconds() / 60
        return 0

    @property
    def productivity_score(self):
        """Score de productivité de la session"""
        if self.duration_minutes == 0:
            return 0
        total_actions = (self.annotations_validated +
                         self.annotations_rejected +
                         self.feedbacks_created)
        return total_actions / max(self.duration_minutes, 1) * 60  # Actions par heure