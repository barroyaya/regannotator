from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('apps.dashboard.urls', namespace='dashboard')),
    path('documents/', include('apps.documents.urls', namespace='documents')),
    path('annotations/', include('apps.annotations.urls', namespace='annotations')),
    path('experts/', include('apps.experts.urls', namespace='experts')),
    path('ml/', include('apps.ml.urls', namespace='ml')),
    # path('core/', include('apps.core.urls')),  # Fonctionnalités de base
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)