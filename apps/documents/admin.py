# ===== apps/documents/admin.py =====
from django.contrib import admin
from .models import Document, DocumentSource, DocumentSentence


@admin.register(DocumentSource)
class DocumentSourceAdmin(admin.ModelAdmin):
    list_display = ['acronym', 'name', 'country']
    search_fields = ['name', 'acronym', 'country']


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ['title', 'source', 'document_type', 'status', 'created_at']
    list_filter = ['status', 'document_type', 'source', 'language']
    search_fields = ['title', 'text_content']
    readonly_fields = ['created_at', 'updated_at', 'file_size', 'page_count']

    fieldsets = (
        ('Informations générales', {
            'fields': ('title', 'file', 'document_type', 'source', 'language')
        }),
        ('Métadonnées', {
            'fields': ('version', 'publication_date', 'url_source', 'status')
        }),
        ('Traitement', {
            'fields': ('text_content', 'file_size', 'page_count'),
            'classes': ('collapse',)
        }),
        ('Audit', {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )


@admin.register(DocumentSentence)
class DocumentSentenceAdmin(admin.ModelAdmin):
    list_display = ['document', 'sentence_number', 'is_processed', 'text_preview']
    list_filter = ['is_processed', 'document__source']
    search_fields = ['text', 'document__title']

    def text_preview(self, obj):
        return obj.text[:100] + "..." if len(obj.text) > 100 else obj.text

    text_preview.short_description = "Aperçu du texte"
