from django.urls import path
from . import views

app_name = 'annotations'

urlpatterns = [
    # Statistiques et analytics
    path('statistics/', views.annotation_statistics, name='statistics'),

    # Validation des annotations
    path('validate/<int:annotation_id>/', views.validate_annotation, name='validate_annotation'),
    path('batch-validate/', views.batch_validate_annotations, name='batch_validate'),

    # Éditeur d'annotations
    path('editor/<int:sentence_id>/', views.annotation_editor, name='annotation_editor'),
    path('create/', views.create_annotation, name='create_annotation'),
    path('edit/<int:annotation_id>/', views.edit_annotation, name='edit_annotation'),
    path('delete/<int:annotation_id>/', views.delete_annotation, name='delete_annotation'),

    # Feedback d'experts
    path('feedback/<int:annotation_id>/', views.add_feedback, name='add_feedback'),
    path('feedback/list/', views.feedback_list, name='feedback_list'),

    # Sessions d'annotation
    path('sessions/', views.annotation_sessions, name='sessions'),
    path('sessions/<int:session_id>/', views.session_detail, name='session_detail'),
    path('sessions/create/', views.create_annotation_session, name='create_session'),

    # Export/Import annotations
    path('export/', views.export_annotations, name='export'),
    path('import/', views.import_annotations, name='import'),

    # API endpoints (si utilisées via annotations/)
    path('api/entities/', views.get_entity_types, name='api_entities'),
    path('api/validate/', views.api_validate_annotation, name='api_validate'),


############################
    path('api/batch-create/', views.batch_create_annotations, name='batch_create'),
    path('api/update/<int:annotation_id>/', views.update_annotation, name='update_annotation'),
    path('api/delete/<int:annotation_id>/', views.delete_annotation, name='delete_annotation'),
    path('api/stats/<int:document_id>/', views.get_annotation_statistics, name='annotation_stats'),

]
