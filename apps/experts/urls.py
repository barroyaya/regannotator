from django.urls import path
from . import views

app_name = 'experts'

urlpatterns = [
    # Dashboard experts
    path('', views.experts_dashboard, name='dashboard'),

    # Gestion des experts
    path('list/', views.expert_list, name='expert_list'),
    path('<int:expert_id>/', views.expert_detail, name='expert_detail'),
    path('create/', views.create_expert_profile, name='create_profile'),

    # Tâches
    path('<int:expert_id>/tasks/', views.expert_tasks, name='expert_tasks'),
    path('assign-task/', views.assign_task, name='assign_task'),

    # Analytics
    path('<int:expert_id>/analytics/', views.expert_analytics, name='expert_analytics'),

    # API
    path('api/<int:expert_id>/stats/', views.api_expert_stats, name='api_expert_stats'),
]