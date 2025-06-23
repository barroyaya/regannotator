# apps/annotations/tasks.py
from celery import shared_task
from .models import AnnotationSession
from .services import LLMAnnotationService
from apps.documents.models import Document


@shared_task
def process_document_annotations(document_id):
    '''Tâche asynchrone pour annoter un document'''
    try:
        document = Document.objects.get(id=document_id)

        # Créer une session d'annotation
        session = AnnotationSession.objects.create(
            document=document,
            status='running'
        )

        # Service d'annotation
        annotator = LLMAnnotationService()

        # Annoter toutes les phrases
        for sentence in document.sentences.filter(is_processed=False):
            annotator.annotate_sentence(sentence)

        session.status = 'completed'
        session.save()

        document.status = 'annotated'
        document.save()

        return f'Document {document.title} annoté avec succès'

    except Exception as e:
        if 'session' in locals():
            session.status = 'failed'
            session.save()

        document.status = 'error'
        document.save()

        raise e


@shared_task
def generate_document_report(document_id):
    '''Générer un rapport d'analyse pour un document'''
    document = Document.objects.get(id=document_id)

    # Logique de génération de rapport
    # ...

    return f'Rapport généré pour {document.title}'