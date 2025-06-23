# apps/ml/admin.py
from django.contrib import admin
from .models import ModelTraining, ModelVersion, ExpertRule


@admin.register(ModelTraining)
class ModelTrainingAdmin(admin.ModelAdmin):
    list_display = ('name', 'status', 'accuracy_score', 'created_at', 'created_by')
    list_filter = ('status', 'created_at')
    search_fields = ('name', 'description')
    readonly_fields = ('accuracy_score', 'precision_score', 'recall_score', 'f1_score', 'entity_metrics')

    fieldsets = (
        ('Informations générales', {
            'fields': ('name', 'description', 'status', 'created_by')
        }),
        ('Paramètres d\'entraînement', {
            'fields': ('validation_split', 'model_parameters')
        }),
        ('Résultats', {
            'fields': ('accuracy_score', 'precision_score', 'recall_score', 'f1_score'),
            'classes': ('collapse',)
        }),
        ('Métriques détaillées', {
            'fields': ('entity_metrics',),
            'classes': ('collapse',)
        }),
    )


@admin.register(ModelVersion)
class ModelVersionAdmin(admin.ModelAdmin):
    list_display = ('training', 'version', 'is_active', 'benchmark_score', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('training__name', 'version')
    list_editable = ('is_active',)


@admin.register(ExpertRule)
class ExpertRuleAdmin(admin.ModelAdmin):
    list_display = ('name', 'entity_type', 'rule_type', 'confidence_score', 'is_active', 'usage_count')
    list_filter = ('rule_type', 'is_active', 'entity_type')
    search_fields = ('name', 'pattern')
    list_editable = ('is_active', 'confidence_score')

    fieldsets = (
        ('Informations générales', {
            'fields': ('name', 'entity_type', 'rule_type', 'is_active')
        }),
        ('Configuration de la règle', {
            'fields': ('pattern', 'confidence_score')
        }),
        ('Statistiques', {
            'fields': ('usage_count', 'success_rate'),
            'classes': ('collapse',)
        }),
    )