# ===== apps/core/admin.py =====
from django.contrib import admin
from .models import RegulatoryEntity

@admin.register(RegulatoryEntity)
class RegulatoryEntityAdmin(admin.ModelAdmin):
    list_display = ['name', 'description', 'color', 'is_active']
    list_filter = ['is_active']
    search_fields = ['name', 'description']