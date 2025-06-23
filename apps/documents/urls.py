# # apps/documents/urls.py
# from django.urls import path
# from . import views
#
# app_name = 'documents'
#
# urlpatterns = [
#     path('upload/', views.upload_document, name='upload'),
#     path('<int:document_id>/analytics/', views.document_analytics, name='analytics'),
#     path('<int:document_id>/analytics/', views.document_analytics, name='analytics'),
#     # autres URLs...
# ]

# ===== apps/documents/urls.py (MIS À JOUR) =====
from django.urls import path
from . import views

app_name = 'documents'

urlpatterns = [
    # Upload et gestion des documents
    path('upload/', views.upload_document, name='upload'),
    path('bulk-upload/', views.bulk_upload_documents, name='bulk_upload'),
    path('<int:document_id>/analytics/', views.document_analytics, name='analytics'),

    # Gestion des métadonnées
    path('<int:document_id>/edit-metadata/', views.edit_document_metadata, name='edit_metadata'),
    path('<int:document_id>/reprocess/', views.reprocess_document, name='reprocess'),

    # Logs d'extraction
    path('extraction-logs/', views.extraction_logs, name='extraction_logs'),
    # path('extraction-logs/export/', views.export_extraction_logs, name='export_extraction_logs'),  # décommente si utilisé

    # API endpoints pour les documents
    path('api/<int:document_id>/metadata/', views.api_document_metadata, name='api_document_metadata'),
    path('api/<int:document_id>/reextract/', views.api_reextract_metadata, name='api_reextract_metadata'),

    # API endpoints pour les logs
    path('api/extraction-logs/<int:log_id>/details/', views.extraction_log_details, name='extraction_log_details'),
    # path('api/documents/<int:document_id>/reextract/', views.reextract_document, name='reextract_document'),  # désactivé car doublon
]
