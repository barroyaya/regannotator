# apps/api/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register('documents', views.DocumentViewSet)
router.register('annotations', views.AnnotationViewSet)
router.register('entity-types', views.RegulatoryEntityViewSet)

urlpatterns = [
    path('api/', include(router.urls)),
    path('api-auth/', include('rest_framework.urls')),
]