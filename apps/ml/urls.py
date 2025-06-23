# apps/ml/urls.py
from django.urls import path
from . import views

app_name = 'ml'

urlpatterns = [
    # Dashboard et vues principales
    path('', views.training_dashboard, name='training_dashboard'),
    path('dashboard/', views.training_dashboard, name='dashboard'),

    # Gestion des entraînements
    path('training/create/', views.create_training, name='create_training'),
    path('training/<int:training_id>/', views.training_detail, name='training_detail'),
    path('training/<int:training_id>/metrics/', views.training_metrics, name='training_metrics'),

    # Gestion des modèles
    path('models/', views.model_list, name='model_list'),
    path('models/<int:model_id>/', views.model_detail, name='model_detail'),
    path('models/<int:model_id>/deploy/', views.deploy_model, name='deploy_model'),

    # Règles expertes
    path('rules/', views.expert_rules_list, name='expert_rules'),
    path('rules/create/', views.create_expert_rule, name='create_rule'),
    path('rules/<int:rule_id>/', views.rule_detail, name='rule_detail'),
    path('rules/<int:rule_id>/edit/', views.edit_rule, name='edit_rule'),
    path('rules/<int:rule_id>/delete/', views.delete_rule, name='delete_rule'),

    # API endpoints
    path('api/training/<int:training_id>/status/', views.api_training_status, name='api_training_status'),
    path('api/model/<int:model_id>/predict/', views.api_model_predict, name='api_model_predict'),
    path('api/rules/test/', views.api_test_rule, name='api_test_rule'),

    # Analytics et monitoring
    path('analytics/', views.ml_analytics, name='analytics'),
    path('performance/', views.model_performance, name='performance'),
    path('benchmarks/', views.model_benchmarks, name='benchmarks'),

    # Export/Import
    path('export/model/<int:model_id>/', views.export_model, name='export_model'),
    path('import/model/', views.import_model, name='import_model'),
]