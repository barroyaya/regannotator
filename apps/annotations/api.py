# ===== apps/annotations/api.py =====
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from .models import Annotation, AnnotationSession
from .services import LLMAnnotationService


class AnnotationViewSet(viewsets.ModelViewSet):
    """API ViewSet pour les annotations"""
    queryset = Annotation.objects.all()
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['post'])
    def batch_annotate(self, request):
        """Annotation en lot d'un document"""
        document_id = request.data.get('document_id')
        if not document_id:
            return Response({'error': 'document_id requis'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Créer une session d'annotation
            session = AnnotationSession.objects.create(
                document_id=document_id,
                created_by=request.user
            )

            # Service d'annotation
            annotator = LLMAnnotationService()

            # Annoter toutes les phrases du document
            from apps.documents.models import Document
            document = Document.objects.get(id=document_id)

            for sentence in document.sentences.filter(is_processed=False):
                annotator.annotate_sentence(sentence)

            session.status = 'completed'
            session.save()

            return Response({
                'status': 'success',
                'session_id': session.id,
                'message': f'Document {document.title} annoté avec succès'
            })

        except Exception as e:
            if 'session' in locals():
                session.status = 'failed'
                session.save()

            return Response({
                'error': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
