# ===== apps/annotations/admin.py =====
from django.contrib import admin
from .models import Annotation, AnnotationSession, ExpertFeedback


@admin.register(AnnotationSession)
class AnnotationSessionAdmin(admin.ModelAdmin):
    list_display = ['document', 'llm_model', 'status', 'created_at']
    list_filter = ['status', 'llm_model']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(Annotation)
class AnnotationAdmin(admin.ModelAdmin):
    list_display = ['entity_type', 'text_value', 'confidence_score', 'validation_status', 'source']
    list_filter = ['entity_type', 'validation_status', 'source', 'confidence_score']
    search_fields = ['text_value', 'sentence__text']
    readonly_fields = ['created_at', 'updated_at']

    fieldsets = (
        ('Annotation', {
            'fields': ('sentence', 'entity_type', 'text_value', 'start_position', 'end_position')
        }),
        ('Qualité', {
            'fields': ('confidence_score', 'source', 'metadata')
        }),
        ('Validation', {
            'fields': ('validation_status', 'validated_by', 'validated_at')
        })
    )


@admin.register(ExpertFeedback)
class ExpertFeedbackAdmin(admin.ModelAdmin):
    list_display = ['annotation', 'expert', 'feedback_type', 'created_at']
    list_filter = ['feedback_type', 'expert']
    search_fields = ['comment', 'suggested_value']
