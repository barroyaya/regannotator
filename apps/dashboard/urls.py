# ===== apps/dashboard/urls.py (mis à jour) =====
from django.urls import path
from . import views

app_name = 'dashboard'

urlpatterns = [
    path('', views.dashboard_home, name='home'),
    path('documents/', views.document_list, name='document_list'),
    path('documents/<int:document_id>/', views.document_detail, name='document_detail'),
    path('documents/<int:document_id>/process/', views.process_document, name='process_document'),
    path('annotations/edit/<int:sentence_id>/', views.annotation_editor, name='annotation_editor'),

    # Nouvelles API pour l'interface d'annotation
    path('api/annotations/create/', views.create_annotation_ajax, name='create_annotation_ajax'),
    path('api/annotations/document/<int:document_id>/', views.get_document_annotations,
         name='get_document_annotations'),

    path('refresh/', views.dashboard_refresh, name='dashboard_refresh'),
    path('debug/', views.dashboard_debug, name='dashboard_debug'),
]
