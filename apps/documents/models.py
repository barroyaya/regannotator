# # ===== apps/documents/models.py =====
# import os
# from django.db import models
# from django.core.validators import FileExtensionValidator
# from django.utils import timezone
#
# from apps.core.models import BaseModel
#
#
# def document_upload_path(instance, filename):
#     """Chemin de stockage des documents avec horodatage"""
#     timestamp = timezone.now().strftime('%Y/%m/%d')
#     return f'documents/{timestamp}/{filename}'
#
#
# class DocumentSource(models.Model):
#     """Sources des documents (EMA, FDA, ANSM, etc.)"""
#     name = models.CharField(max_length=100)
#     acronym = models.CharField(max_length=10)
#     country = models.CharField(max_length=100)
#     website = models.URLField(blank=True)
#
#     def __str__(self):
#         return f"{self.acronym} - {self.name}"
#
#
# class Document(BaseModel):
#     """Document réglementaire à analyser"""
#
#     DOCUMENT_TYPES = [
#         ('guideline', 'Guideline'),
#         ('procedure', 'Procédure'),
#         ('variation', 'Variation'),
#         ('regulation', 'Règlement'),
#         ('directive', 'Directive'),
#     ]
#
#     LANGUAGES = [
#         ('fr', 'Français'),
#         ('en', 'Anglais'),
#         ('de', 'Allemand'),
#         ('es', 'Espagnol'),
#         ('it', 'Italien'),
#     ]
#
#     STATUS_CHOICES = [
#         ('uploaded', 'Téléchargé'),
#         ('processing', 'En cours de traitement'),
#         ('annotated', 'Annoté'),
#         ('validated', 'Validé'),
#         ('error', 'Erreur'),
#     ]
#
#     title = models.CharField(max_length=500)
#     file = models.FileField(
#         upload_to=document_upload_path,
#         validators=[FileExtensionValidator(allowed_extensions=['pdf'])]
#     )
#     document_type = models.CharField(max_length=20, choices=DOCUMENT_TYPES)
#     source = models.ForeignKey(
#         DocumentSource,
#         on_delete=models.SET_NULL,
#         null=True,
#         blank=True,
#         related_name="documents"
#     )
#
#     language = models.CharField(max_length=5, choices=LANGUAGES, default='fr')
#     version = models.CharField(max_length=50, blank=True)
#     publication_date = models.DateField(null=True, blank=True)
#     url_source = models.URLField(blank=True)
#     status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='uploaded')
#
#     # Métadonnées extraites
#     page_count = models.IntegerField(null=True, blank=True)
#     file_size = models.IntegerField(null=True, blank=True)  # en bytes
#     text_content = models.TextField(blank=True)  # Texte extrait du PDF
#
#     class Meta:
#         verbose_name = "Document"
#         verbose_name_plural = "Documents"
#         ordering = ['-created_at']
#
#     def __str__(self):
#         return self.title
#
#     @property
#     def file_size_mb(self):
#         if self.file_size:
#             return round(self.file_size / (1024 * 1024), 2)
#         return None
#
#
# class DocumentSentence(BaseModel):
#     """Phrases extraites des documents"""
#     document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='sentences')
#     sentence_number = models.IntegerField()
#     text = models.TextField()
#     page_number = models.IntegerField(null=True, blank=True)
#     is_processed = models.BooleanField(default=False)
#
#     class Meta:
#         verbose_name = "Phrase"
#         verbose_name_plural = "Phrases"
#         ordering = ['document', 'sentence_number']
#         unique_together = ['document', 'sentence_number']
#
#     def __str__(self):
#         return f"{self.document.title} - Phrase {self.sentence_number}"


# ===== apps/documents/models.py (ÉTENDU) =====
import os
import re
from django.db import models
from django.core.validators import FileExtensionValidator
from django.utils import timezone
from django.contrib.auth.models import User

from apps.core.models import BaseModel


def document_upload_path(instance, filename):
    """Chemin de stockage des documents avec horodatage"""
    timestamp = timezone.now().strftime('%Y/%m/%d')
    return f'documents/{timestamp}/{filename}'


class DocumentSource(models.Model):
    """Sources des documents (EMA, FDA, ANSM, etc.)"""
    name = models.CharField(max_length=100)
    acronym = models.CharField(max_length=10)
    country = models.CharField(max_length=100)
    website = models.URLField(blank=True)

    # Patterns pour reconnaissance automatique
    domain_patterns = models.TextField(blank=True, help_text="Domaines séparés par des virgules")
    name_patterns = models.TextField(blank=True, help_text="Patterns de reconnaissance séparés par des virgules")

    def __str__(self):
        return f"{self.acronym} - {self.name}"


class DocumentExtractionLog(BaseModel):
    """Logs d'extraction de métadonnées"""

    CONTEXT_CHOICES = [
        ('pharma', 'Pharmaceutique'),
        ('juridique', 'Juridique'),
        ('gouvernement', 'Gouvernement'),
        ('medical', 'Médical'),
        ('research', 'Recherche'),
        ('autre', 'Autre'),
    ]

    STATUS_CHOICES = [
        ('success', 'Succès'),
        ('partial', 'Partiel'),
        ('failed', 'Échec'),
    ]

    document = models.ForeignKey('Document', on_delete=models.CASCADE, related_name='extraction_logs')
    scraping_date = models.DateTimeField(default=timezone.now)
    url = models.URLField(blank=True, help_text="URL source si applicable")
    file_type = models.CharField(max_length=50)
    context = models.CharField(max_length=20, choices=CONTEXT_CHOICES, default='pharma')

    # Métadonnées extraites automatiquement
    extracted_title = models.CharField(max_length=500, blank=True)
    extracted_date = models.DateField(null=True, blank=True)
    extracted_language = models.CharField(max_length=10, blank=True)
    extracted_country = models.CharField(max_length=100, blank=True)
    extracted_source = models.CharField(max_length=100, blank=True)
    extracted_version = models.CharField(max_length=50, blank=True)

    # Métrique de confiance (0-100)
    confidence_title = models.IntegerField(default=0)
    confidence_date = models.IntegerField(default=0)
    confidence_language = models.IntegerField(default=0)
    confidence_source = models.IntegerField(default=0)

    # Résultats
    extraction_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='success')
    extraction_notes = models.TextField(blank=True)
    processing_time = models.FloatField(null=True, blank=True, help_text="Temps en secondes")

    class Meta:
        verbose_name = "Log d'extraction"
        verbose_name_plural = "Logs d'extraction"
        ordering = ['-scraping_date']

    def __str__(self):
        return f"Extraction {self.document.title} - {self.scraping_date.strftime('%d/%m/%Y %H:%M')}"


class Document(BaseModel):
    """Document réglementaire à analyser"""

    DOCUMENT_TYPES = [
        ('guideline', 'Guideline'),
        ('procedure', 'Procédure'),
        ('variation', 'Variation'),
        ('regulation', 'Règlement'),
        ('directive', 'Directive'),
        ('circular', 'Circulaire'),
        ('notice', 'Notice'),
        ('report', 'Rapport'),
        ('autres', 'Autres'),
    ]

    LANGUAGES = [
        ('fr', 'Français'),
        ('en', 'Anglais'),
        ('de', 'Allemand'),
        ('es', 'Espagnol'),
        ('it', 'Italien'),
        ('pt', 'Portugais'),
        ('nl', 'Néerlandais'),
        ('auto', 'Détection automatique'),
    ]

    STATUS_CHOICES = [
        ('uploaded', 'Téléchargé'),
        ('processing', 'En cours de traitement'),
        ('metadata_extracted', 'Métadonnées extraites'),
        ('annotated', 'Annoté'),
        ('validated', 'Validé'),
        ('error', 'Erreur'),
    ]

    # Champs de base
    title = models.CharField(max_length=500)
    file = models.FileField(
        upload_to=document_upload_path,
        validators=[FileExtensionValidator(allowed_extensions=[
            'pdf', 'doc', 'docx', 'txt', 'html', 'htm', 'rtf', 'odt'
        ])]
    )
    document_type = models.CharField(max_length=20, choices=DOCUMENT_TYPES)
    source = models.ForeignKey(
        DocumentSource,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="documents"
    )

    language = models.CharField(max_length=10, choices=LANGUAGES, default='auto')
    version = models.CharField(max_length=50, blank=True)
    publication_date = models.DateField(null=True, blank=True)
    url_source = models.URLField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='uploaded')

    # Métadonnées extraites automatiquement
    auto_extracted_title = models.CharField(max_length=500, blank=True, help_text="Titre extrait automatiquement")
    auto_extracted_date = models.DateField(null=True, blank=True, help_text="Date extraite automatiquement")
    auto_extracted_language = models.CharField(max_length=10, blank=True, help_text="Langue détectée automatiquement")
    auto_extracted_country = models.CharField(max_length=100, blank=True, help_text="Pays extrait automatiquement")
    auto_extracted_source = models.CharField(max_length=100, blank=True, help_text="Source extraite automatiquement")
    auto_extracted_version = models.CharField(max_length=50, blank=True, help_text="Version extraite automatiquement")

    # Flags pour indiquer si les métadonnées ont été modifiées manuellement
    title_manually_edited = models.BooleanField(default=False)
    date_manually_edited = models.BooleanField(default=False)
    language_manually_edited = models.BooleanField(default=False)
    source_manually_edited = models.BooleanField(default=False)

    # Métadonnées du fichier
    page_count = models.IntegerField(null=True, blank=True)
    file_size = models.IntegerField(null=True, blank=True)  # en bytes
    file_type = models.CharField(max_length=10, blank=True)
    text_content = models.TextField(blank=True)  # Texte extrait du fichier

    # Métadonnées d'extraction
    extraction_confidence = models.JSONField(default=dict, blank=True,
                                             help_text="Scores de confiance pour chaque métadonnée")
    extraction_patterns_used = models.JSONField(default=list, blank=True,
                                                help_text="Patterns utilisés pour l'extraction")

    class Meta:
        verbose_name = "Document"
        verbose_name_plural = "Documents"
        ordering = ['-created_at']

    def __str__(self):
        return self.title

    @property
    def file_size_mb(self):
        if self.file_size:
            return round(self.file_size / (1024 * 1024), 2)
        return None

    @property
    def effective_title(self):
        """Retourne le titre effectif (manuel ou extrait)"""
        return self.title or self.auto_extracted_title

    @property
    def effective_date(self):
        """Retourne la date effective (manuelle ou extraite)"""
        return self.publication_date or self.auto_extracted_date

    @property
    def effective_language(self):
        """Retourne la langue effective (manuelle ou détectée)"""
        if self.language and self.language != 'auto':
            return self.language
        return self.auto_extracted_language or 'fr'

    @property
    def extraction_summary(self):
        """Résumé de l'extraction automatique"""
        auto_fields = {
            'title': bool(self.auto_extracted_title),
            'date': bool(self.auto_extracted_date),
            'language': bool(self.auto_extracted_language),
            'country': bool(self.auto_extracted_country),
            'source': bool(self.auto_extracted_source),
            'version': bool(self.auto_extracted_version),
        }
        extracted_count = sum(auto_fields.values())
        total_count = len(auto_fields)
        return {
            'extracted_fields': auto_fields,
            'extraction_rate': (extracted_count / total_count) * 100,
            'confidence_avg': sum(self.extraction_confidence.values()) / len(
                self.extraction_confidence) if self.extraction_confidence else 0
        }


class DocumentSentence(BaseModel):
    """Phrases extraites des documents"""
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='sentences')
    sentence_number = models.IntegerField()
    text = models.TextField()
    page_number = models.IntegerField(null=True, blank=True)
    is_processed = models.BooleanField(default=False)

    # Métadonnées de positionnement dans le document
    start_position = models.IntegerField(null=True, blank=True, help_text="Position de début dans le texte")
    end_position = models.IntegerField(null=True, blank=True, help_text="Position de fin dans le texte")

    # Classification automatique de la phrase
    sentence_type = models.CharField(max_length=50, blank=True, help_text="Type de phrase détecté")
    confidence_score = models.FloatField(default=0.0, help_text="Score de confiance pour le type détecté")

    class Meta:
        verbose_name = "Phrase"
        verbose_name_plural = "Phrases"
        ordering = ['document', 'sentence_number']
        unique_together = ['document', 'sentence_number']

    def __str__(self):
        return f"{self.document.title} - Phrase {self.sentence_number}"