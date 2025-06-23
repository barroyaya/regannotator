# apps/api/views.py
from django.utils import timezone
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from apps.documents.models import Document, DocumentSentence
from apps.annotations.models import Annotation
from apps.core.models import RegulatoryEntity
from .serializers import *


class RegulatoryEntityViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = RegulatoryEntity.objects.filter(is_active=True)
    serializer_class = RegulatoryEntitySerializer
    permission_classes = [permissions.IsAuthenticated]


class DocumentViewSet(viewsets.ModelViewSet):
    queryset = Document.objects.all()
    serializer_class = DocumentSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['status', 'document_type', 'source']
    search_fields = ['title', 'text_content']
    ordering_fields = ['created_at', 'title']
    ordering = ['-created_at']

    @action(detail=True, methods=['get'])
    def sentences(self, request, pk=None):
        '''Récupérer les phrases d'un document'''
        document = self.get_object()
        sentences = document.sentences.prefetch_related('annotations__entity_type')
        serializer = DocumentSentenceSerializer(sentences, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def annotate(self, request, pk=None):
        '''Démarrer l'annotation automatique d'un document'''
        document = self.get_object()

        # Créer une tâche d'annotation asynchrone
        from apps.annotations.tasks import process_document_annotations
        task = process_document_annotations.delay(document.id)

        return Response({
            'message': 'Annotation démarrée',
            'task_id': task.id,
            'document_id': document.id
        })


class AnnotationViewSet(viewsets.ModelViewSet):
    queryset = Annotation.objects.all()
    serializer_class = AnnotationSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ['entity_type', 'validation_status', 'source']
    ordering_fields = ['created_at', 'confidence_score']

    def get_serializer_class(self):
        if self.action == 'create':
            return AnnotationCreateSerializer
        return AnnotationSerializer

    @action(detail=True, methods=['post'])
    def validate_annotation(self, request, pk=None):
        '''Valider ou rejeter une annotation'''
        annotation = self.get_object()
        action_type = request.data.get('action')

        if action_type == 'validate':
            annotation.validation_status = 'validated'
        elif action_type == 'reject':
            annotation.validation_status = 'rejected'
        else:
            return Response({'error': 'Action invalide'}, status=status.HTTP_400_BAD_REQUEST)

        annotation.validated_by = request.user
        annotation.validated_at = timezone.now()
        annotation.save()

        return Response({'status': 'success', 'action': action_type})

    @action(detail=False, methods=['get'])
    def statistics(self, request):
        '''Statistiques des annotations'''
        from django.db.models import Count, Avg

        stats = {
            'total': self.get_queryset().count(),
            'by_status': dict(
                self.get_queryset()
                .values('validation_status')
                .annotate(count=Count('id'))
                .values_list('validation_status', 'count')
            ),
            'by_entity': list(
                self.get_queryset()
                .values('entity_type__name')
                .annotate(count=Count('id'), avg_confidence=Avg('confidence_score'))
                .order_by('-count')
            ),
            'avg_confidence': self.get_queryset().aggregate(Avg('confidence_score'))['confidence_score__avg']
        }

        return Response(stats)