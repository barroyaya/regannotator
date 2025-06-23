from django.contrib import admin
from .models import ExpertProfile, ExpertSpecialty, ExpertTask, ExpertSession

@admin.register(ExpertProfile)
class ExpertProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'expertise_level', 'company', 'years_experience', 'is_active', 'last_activity']
    list_filter = ['expertise_level', 'is_active', 'specializations']
    search_fields = ['user__username', 'user__first_name', 'user__last_name', 'company']
    readonly_fields = ['total_annotations_validated', 'total_feedbacks_given', 'accuracy_score']

@admin.register(ExpertTask)
class ExpertTaskAdmin(admin.ModelAdmin):
    list_display = ['title', 'expert', 'task_type', 'priority', 'status', 'created_at']
    list_filter = ['task_type', 'priority', 'status']
    search_fields = ['title', 'description', 'expert__user__username']

@admin.register(ExpertSpecialty)
class ExpertSpecialtyAdmin(admin.ModelAdmin):
    list_display = ['expert', 'entity_type', 'proficiency_level', 'success_rate']
    list_filter = ['proficiency_level', 'entity_type']

@admin.register(ExpertSession)
class ExpertSessionAdmin(admin.ModelAdmin):
    list_display = ['expert', 'start_time', 'duration_minutes', 'productivity_score']
    list_filter = ['start_time']
    readonly_fields = ['duration_minutes', 'productivity_score']