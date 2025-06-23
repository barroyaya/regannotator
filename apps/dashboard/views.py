# # ===== apps/dashboard/views.py =====
# from django.shortcuts import render, get_object_or_404, redirect
# from django.contrib.auth.decorators import login_required
# from django.http import JsonResponse
# from django.core.paginator import Paginator
# from django.db.models import Count, Q
# from django.contrib import messages
# from django.utils import timezone
#
# from apps.documents.models import Document, DocumentSentence
# from apps.annotations.models import Annotation
# from apps.core.models import RegulatoryEntity
# from apps.documents.services import DocumentProcessingService
# from apps.annotations.services import LLMAnnotationService
#
#
# @login_required
# def dashboard_home(request):
#     """Dashboard principal"""
#     # Statistiques générales
#     stats = {
#         'total_documents': Document.objects.count(),
#         'total_sentences': DocumentSentence.objects.count(),
#         'total_annotations': Annotation.objects.count(),
#         'pending_validations': Annotation.objects.filter(validation_status='pending').count(),
#     }
#
#     # Documents récents
#     recent_documents = Document.objects.order_by('-created_at')[:5]
#
#     # Annotations par entité
#     annotations_by_entity = (
#         Annotation.objects
#         .values('entity_type__name')
#         .annotate(count=Count('id'))
#         .order_by('-count')
#     )
#
#     context = {
#         'stats': stats,
#         'recent_documents': recent_documents,
#         'annotations_by_entity': annotations_by_entity,
#     }
#
#     return render(request, 'dashboard/home.html', context)
#
#
# @login_required
# def document_list(request):
#     """Liste des documents avec annotations comptées proprement"""
#
#     # Filtrage par statut
#     status_filter = request.GET.get('status')
#     documents = Document.objects.all()
#
#     if status_filter:
#         documents = documents.filter(status=status_filter)
#
#     # Annoter les statistiques par document
#     documents = documents.annotate(
#         total_sentences=Count('sentences', distinct=True),
#         total_annotations=Count('sentences__annotations', distinct=True),
#         validated_annotations=Count(
#             'sentences__annotations',
#             filter=Q(sentences__annotations__validation_status='validated'),
#             distinct=True
#         )
#     ).order_by('-created_at')
#
#     # Pagination
#     paginator = Paginator(documents, 10)
#     page_number = request.GET.get('page')
#     page_obj = paginator.get_page(page_number)
#
#     # Contexte pour le template
#     context = {
#         'page_obj': page_obj,
#         'status_choices': Document.STATUS_CHOICES,
#         'current_status': status_filter,
#     }
#
#     return render(request, 'dashboard/document_list.html', context)
#
#
# @login_required
# def document_detail(request, document_id):
#     """Détail d'un document avec annotations"""
#     document = get_object_or_404(Document, id=document_id)
#     sentences = document.sentences.prefetch_related('annotations__entity_type').all()
#
#     # Pagination des phrases
#     paginator = Paginator(sentences, 20)
#     page_number = request.GET.get('page')
#     page_obj = paginator.get_page(page_number)
#
#     context = {
#         'document': document,
#         'page_obj': page_obj,
#         'entity_types': RegulatoryEntity.objects.filter(is_active=True),
#     }
#
#     return render(request, 'dashboard/document_detail.html', context)
#
#
# @login_required
# def process_document(request, document_id):
#     """Traiter un document (extraction + annotation)"""
#     document = get_object_or_404(Document, id=document_id)
#
#     try:
#         # Service de traitement
#         processor = DocumentProcessingService()
#         processor.process_document(document)
#
#         # Service d'annotation
#         annotator = LLMAnnotationService()
#         for sentence in document.sentences.all():
#             annotator.annotate_sentence(sentence)
#
#         messages.success(request, f"Document '{document.title}' traité avec succès.")
#
#     except Exception as e:
#         messages.error(request, f"Erreur lors du traitement: {e}")
#
#     return redirect('dashboard:document_detail', document_id=document.id)
#
#
# @login_required
# def annotation_editor(request, sentence_id):
#     """Éditeur d'annotations pour une phrase"""
#     sentence = get_object_or_404(DocumentSentence, id=sentence_id)
#     annotations = sentence.annotations.all()
#
#     if request.method == 'POST':
#         # Gestion des modifications d'annotations
#         annotation_id = request.POST.get('annotation_id')
#         action = request.POST.get('action')
#
#         if action == 'validate':
#             annotation = get_object_or_404(Annotation, id=annotation_id)
#             annotation.validation_status = 'validated'
#             annotation.validated_by = request.user
#             annotation.validated_at = timezone.now()
#             annotation.save()
#
#         elif action == 'reject':
#             annotation = get_object_or_404(Annotation, id=annotation_id)
#             annotation.validation_status = 'rejected'
#             annotation.validated_by = request.user
#             annotation.validated_at = timezone.now()
#             annotation.save()
#
#         return JsonResponse({'status': 'success'})
#
#     context = {
#         'sentence': sentence,
#         'annotations': annotations,
#         'entity_types': RegulatoryEntity.objects.filter(is_active=True),
#     }
#
#     return render(request, 'dashboard/annotation_editor.html', context)

# ===== apps/dashboard/views.py (CORRIGÉ FINAL) =====
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.contrib import messages
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.core.serializers.json import DjangoJSONEncoder
import json

from apps.documents.models import Document, DocumentSentence
from apps.annotations.models import Annotation
from apps.core.models import RegulatoryEntity
from apps.documents.services import DocumentProcessingService
from apps.annotations.services import LLMAnnotationService


# @login_required
# def dashboard_home(request):
#     """Dashboard principal"""
#     stats = {
#         'total_documents': Document.objects.count(),
#         'total_sentences': DocumentSentence.objects.count(),
#         'total_annotations': Annotation.objects.count(),
#         'pending_validations': Annotation.objects.filter(validation_status='pending').count(),
#     }
#
#     recent_documents = Document.objects.order_by('-created_at')[:5]
#     annotations_by_entity = (
#         Annotation.objects
#         .values('entity_type__name')
#         .annotate(count=Count('id'))
#         .order_by('-count')
#     )
#
#     context = {
#         'stats': stats,
#         'recent_documents': recent_documents,
#         'annotations_by_entity': annotations_by_entity,
#     }
#
#     return render(request, 'dashboard/home.html', context)
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.core.cache import cache
from django.utils import timezone
from django.http import JsonResponse
import logging

logger = logging.getLogger(__name__)

from django.core.cache import cache
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)


@login_required
def dashboard_home(request):
    """Dashboard principal avec protection contre les boucles"""

    try:
        # Cache pour éviter les recalculs
        cache_key = f"dashboard_{request.user.id}_{timezone.now().strftime('%H%M')}"
        cached_data = cache.get(cache_key)

        if cached_data:
            return render(request, 'dashboard/home.html', cached_data)

        # Requêtes optimisées
        stats = {
            'total_documents': Document.objects.count(),
            'total_sentences': DocumentSentence.objects.count(),
            'total_annotations': Annotation.objects.count(),
            'pending_validations': Annotation.objects.filter(validation_status='pending').count(),
        }

        recent_documents = list(
            Document.objects.select_related('source').order_by('-created_at')[:5]
        )

        # Protection contre les données nulles
        annotations_raw = (
            Annotation.objects
            .values('entity_type__name')
            .annotate(count=Count('id'))
            .order_by('-count')[:10]
        )

        annotations_by_entity = []
        for item in annotations_raw:
            if item.get('entity_type__name') and item.get('count', 0) > 0:
                annotations_by_entity.append(item)

        # Fallback si pas de données
        if not annotations_by_entity:
            annotations_by_entity = [{'entity_type__name': 'Aucune donnée', 'count': 0}]

        context = {
            'stats': stats,
            'recent_documents': recent_documents,
            'annotations_by_entity': annotations_by_entity,
            'debug_info': {
                'has_valid_data': len(annotations_by_entity) > 0 and annotations_by_entity[0]['count'] > 0
            }
        }

        # Cache 2 minutes
        cache.set(cache_key, context, 120)

        return render(request, 'dashboard/home.html', context)

    except Exception as e:
        logger.error(f"Dashboard error: {str(e)}")

        # Contexte de fallback
        context = {
            'stats': {'total_documents': 0, 'total_sentences': 0, 'total_annotations': 0, 'pending_validations': 0},
            'recent_documents': [],
            'annotations_by_entity': [{'entity_type__name': 'Erreur de chargement', 'count': 0}],
            'debug_info': {'has_valid_data': False},
            'error_occurred': True,
            'error_message': "Erreur lors du chargement. Veuillez rafraîchir."
        }

        return render(request, 'dashboard/home.html', context)

# === VUE AJAX POUR REFRESH SANS RECHARGEMENT ===
@login_required
def dashboard_refresh(request):
    """
    Vue AJAX pour rafraîchir les stats sans recharger la page
    Utile pour éviter les boucles de rechargement
    """
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        # Stats rapides seulement
        stats = {
            'total_documents': Document.objects.count(),
            'total_annotations': Annotation.objects.count(),
            'pending_validations': Annotation.objects.filter(validation_status='pending').count(),
        }

        return JsonResponse({
            'success': True,
            'stats': stats,
            'timestamp': timezone.now().isoformat()
        })

    except Exception as e:
        logger.error(f"Dashboard refresh error: {str(e)}")
        return JsonResponse({'error': 'Refresh failed'}, status=500)


# === VUE DE DEBUG (TEMPORAIRE) ===
@login_required
def dashboard_debug(request):
    """Vue de debug avec interface stylée"""
    if not request.user.is_staff:
        return render(request, '403.html', status=403)

    try:
        # Collecte des données de debug
        debug_data = {
            'metadata': {
                'timestamp': timezone.now(),
                'user': request.user.username,
                'user_groups': list(request.user.groups.values_list('name', flat=True)),
                'is_superuser': request.user.is_superuser,
                'request_method': request.method,
                'request_path': request.path,
            },

            'database_stats': {
                'total_documents': Document.objects.count(),
                'total_sentences': DocumentSentence.objects.count(),
                'total_annotations': Annotation.objects.count(),
                'documents_without_source': Document.objects.filter(source__isnull=True).count(),
                'annotations_without_entity_type': Annotation.objects.filter(entity_type__isnull=True).count(),
                'entity_types_with_null_names': Annotation.objects.filter(entity_type__name__isnull=True).count(),
            },

            'validation_stats': {
                'pending': Annotation.objects.filter(validation_status='pending').count(),
                'validated': Annotation.objects.filter(validation_status='validated').count(),
                'rejected': Annotation.objects.filter(validation_status='rejected').count(),
                'in_review': Annotation.objects.filter(validation_status='review').count(),
            },

            'top_entity_types': list(
                Annotation.objects
                .values('entity_type__name')
                .annotate(count=Count('id'))
                .order_by('-count')[:10]
            ),

            'recent_documents': list(
                Document.objects
                .select_related('source')
                .values('id', 'title', 'source__name', 'status', 'created_at')
                .order_by('-created_at')[:10]
            ),

            'recent_annotations': list(
                Annotation.objects
                .select_related('entity_type')
                .values('id', 'entity_type__name', 'validation_status', 'created_at')
                .order_by('-created_at')[:10]
            ),

            'sources_stats': list(
                Document.objects
                .values('source__name', 'source__acronym')
                .annotate(count=Count('id'))
                .order_by('-count')[:5]
            ),

            'cache_info': {
                'cache_key_pattern': f"dashboard_{request.user.id}_HHMM",
                'current_cache_key': f"dashboard_{request.user.id}_{timezone.now().strftime('%H%M')}",
                'cache_duration': '120 seconds',
                'cache_backend': 'django.core.cache.backends.locmem.LocMemCache',
            },

            'performance_info': {
                'total_db_objects': (
                        Document.objects.count() +
                        DocumentSentence.objects.count() +
                        Annotation.objects.count()
                ),
                'last_week_documents': Document.objects.filter(
                    created_at__gte=timezone.now() - timezone.timedelta(days=7)
                ).count(),
                'last_week_annotations': Annotation.objects.filter(
                    created_at__gte=timezone.now() - timezone.timedelta(days=7)
                ).count(),
            }
        }

        # Calculs additionnels
        total_annotations = debug_data['database_stats']['total_annotations']
        validation_stats = debug_data['validation_stats']

        if total_annotations > 0:
            debug_data['validation_percentages'] = {
                'validated_pct': round((validation_stats['validated'] / total_annotations) * 100, 1),
                'pending_pct': round((validation_stats['pending'] / total_annotations) * 100, 1),
                'rejected_pct': round((validation_stats['rejected'] / total_annotations) * 100, 1),
            }
        else:
            debug_data['validation_percentages'] = {'validated_pct': 0, 'pending_pct': 0, 'rejected_pct': 0}

        context = {
            'debug_data': debug_data,
            'page_title': 'Debug Dashboard',
        }

        return render(request, 'dashboard/debug.html', context)

    except Exception as e:
        logger.error(f"Dashboard debug error: {str(e)}")

        error_context = {
            'error_message': str(e),
            'error_timestamp': timezone.now(),
            'page_title': 'Debug Error',
        }

        return render(request, 'dashboard/debug.html', error_context)




@login_required
def document_list(request):
    """Liste des documents avec annotations comptées proprement"""
    status_filter = request.GET.get('status')
    documents = Document.objects.all()

    if status_filter:
        documents = documents.filter(status=status_filter)

    documents = documents.annotate(
        total_sentences=Count('sentences', distinct=True),
        total_annotations=Count('sentences__annotations', distinct=True),
        validated_annotations=Count(
            'sentences__annotations',
            filter=Q(sentences__annotations__validation_status='validated'),
            distinct=True
        )
    ).order_by('-created_at')

    paginator = Paginator(documents, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'status_choices': Document.STATUS_CHOICES,
        'current_status': status_filter,
    }

    return render(request, 'dashboard/document_list.html', context)


@login_required
def document_detail(request, document_id):
    """Détail d'un document avec interface d'annotation interactive"""
    document = get_object_or_404(Document, id=document_id)
    sentences = document.sentences.prefetch_related('annotations__entity_type').all()

    paginator = Paginator(sentences, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    total_sentences = document.sentences.count()
    total_annotations = Annotation.objects.filter(sentence__document=document).count()
    entity_types = RegulatoryEntity.objects.filter(is_active=True)

    # COULEURS PAR DÉFAUT GARANTIES
    default_colors = {
        'VARIATION_CODE': '#FFD700',
        'PROCEDURE_TYPE': '#87CEEB',
        'AUTHORITY': '#98FB98',
        'LEGAL_REFERENCE': '#DDA0DD',
        'DOCUMENT_REQUIRED': '#F0E68C',
        'CONDITION_REQUIRED': '#FFA07A',
        'TIMELINE': '#D3D3D3',
        'DOSSIER_TYPE': '#E6E6FA',
        'COUNTRY': '#FFB6C1'
    }

    # ASSURER QUE TOUTES LES ENTITÉS ONT DES COULEURS
    for entity_type in entity_types:
        if not getattr(entity_type, 'color', None):
            entity_type.color = default_colors.get(entity_type.name.upper(), '#E6E6FA')
            entity_type.save()  # Sauvegarder la couleur

        # Compter les annotations pour cette entité
        entity_type.annotations_count = Annotation.objects.filter(
            entity_type=entity_type,
            sentence__document=document
        ).count()

    # PRÉPARER LES DONNÉES JSON POUR CHAQUE PHRASE
    for sentence in page_obj:
        annotations_data = []

        sentence_annotations = sentence.annotations.select_related('entity_type').all()

        for annotation in sentence_annotations:
            # S'assurer que l'entité a une couleur
            if not annotation.entity_type.color:
                annotation.entity_type.color = default_colors.get(
                    annotation.entity_type.name.upper(),
                    '#E6E6FA'
                )
                annotation.entity_type.save()

            annotations_data.append({
                "id": annotation.id,
                "text": annotation.text_value,
                "startOffset": annotation.start_position,
                "endOffset": annotation.end_position,
                "entityType": {
                    "id": annotation.entity_type.id,
                    "name": annotation.entity_type.name,
                    "color": annotation.entity_type.color,
                },
                "validationStatus": annotation.validation_status
            })

        # Sérialiser les données d'annotations pour cette phrase
        sentence.annotations_json = json.dumps(annotations_data, cls=DjangoJSONEncoder)

    context = {
        'document': document,
        'page_obj': page_obj,
        'entity_types': entity_types,
        'total_sentences': total_sentences,
        'total_annotations': total_annotations,
    }

    return render(request, 'dashboard/document_detail.html', context)


@login_required
def process_document(request, document_id):
    """Traiter un document (extraction + annotation)"""
    document = get_object_or_404(Document, id=document_id)

    try:
        processor = DocumentProcessingService()
        processor.process_document(document)

        annotator = LLMAnnotationService()
        for sentence in document.sentences.all():
            annotator.annotate_sentence(sentence)

        messages.success(request, f"Document '{document.title}' traité avec succès.")

    except Exception as e:
        messages.error(request, f"Erreur lors du traitement: {e}")

    return redirect('dashboard:document_detail', document_id=document.id)


@login_required
@csrf_exempt
def create_annotation_ajax(request):
    """Créer une annotation via AJAX"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        data = json.loads(request.body)
        annotations_data = data.get('annotations', [])
        document_id = data.get('documentId')

        if not document_id:
            return JsonResponse({'error': 'Document ID requis'}, status=400)

        document = get_object_or_404(Document, id=document_id)
        created_annotations = []

        # COULEURS PAR DÉFAUT
        default_colors = {
            'VARIATION_CODE': '#FFD700',
            'PROCEDURE_TYPE': '#87CEEB',
            'AUTHORITY': '#98FB98',
            'LEGAL_REFERENCE': '#DDA0DD',
            'DOCUMENT_REQUIRED': '#F0E68C',
            'CONDITION_REQUIRED': '#FFA07A',
            'TIMELINE': '#D3D3D3',
            'DOSSIER_TYPE': '#E6E6FA',
            'COUNTRY': '#FFB6C1'
        }

        for annotation_data in annotations_data:
            # Récupérer la phrase
            sentence_id = annotation_data.get('sentenceId')
            if sentence_id:
                try:
                    sentence = DocumentSentence.objects.get(id=sentence_id, document=document)
                except DocumentSentence.DoesNotExist:
                    sentence = document.sentences.first()
            else:
                sentence = document.sentences.first()

            if not sentence:
                continue

            # Récupérer le type d'entité
            entity_type = get_object_or_404(RegulatoryEntity, id=annotation_data['entityTypeId'])

            # S'assurer que l'entité a une couleur
            if not entity_type.color:
                entity_type.color = default_colors.get(entity_type.name.upper(), '#E6E6FA')
                entity_type.save()

            # Créer l'annotation
            annotation = Annotation.objects.create(
                sentence=sentence,
                entity_type=entity_type,
                text_value=annotation_data['text'],
                start_position=annotation_data.get('startOffset', 0),
                end_position=annotation_data.get('endOffset', len(annotation_data['text'])),
                confidence_score=1.0,
                source='expert',
                created_by=request.user,
                validation_status='validated'
            )

            created_annotations.append({
                'id': annotation.id,
                'text': annotation.text_value,
                'entity_type': annotation.entity_type.name,
                'entity_color': annotation.entity_type.color,
                'confidence': annotation.confidence_score
            })

        return JsonResponse({
            'success': True,
            'message': f'{len(created_annotations)} annotations créées',
            'annotations': created_annotations
        })

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Données JSON invalides'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def get_document_annotations(request, document_id):
    """API pour récupérer les annotations d'un document"""
    try:
        document = get_object_or_404(Document, id=document_id)

        annotations = Annotation.objects.filter(
            sentence__document=document
        ).select_related('entity_type', 'sentence')

        default_colors = {
            'VARIATION_CODE': '#FFD700',
            'PROCEDURE_TYPE': '#87CEEB',
            'AUTHORITY': '#98FB98',
            'LEGAL_REFERENCE': '#DDA0DD',
            'DOCUMENT_REQUIRED': '#F0E68C',
            'CONDITION_REQUIRED': '#FFA07A',
            'TIMELINE': '#D3D3D3',
            'DOSSIER_TYPE': '#E6E6FA',
            'COUNTRY': '#FFB6C1'
        }

        annotations_data = []
        for annotation in annotations:
            # S'assurer que l'entité a une couleur
            if not annotation.entity_type.color:
                annotation.entity_type.color = default_colors.get(
                    annotation.entity_type.name.upper(),
                    '#E6E6FA'
                )
                annotation.entity_type.save()

            annotations_data.append({
                'id': annotation.id,
                'text': annotation.text_value,
                'startOffset': annotation.start_position,
                'endOffset': annotation.end_position,
                'entityType': {
                    'id': annotation.entity_type.id,
                    'name': annotation.entity_type.name,
                    'color': annotation.entity_type.color
                },
                'confidence': annotation.confidence_score,
                'validationStatus': annotation.validation_status,
                'sentenceId': annotation.sentence.id
            })

        return JsonResponse({
            'success': True,
            'annotations': annotations_data
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e),
            'annotations': []
        })


@login_required
def annotation_editor(request, sentence_id):
    """Éditeur d'annotations pour une phrase"""
    sentence = get_object_or_404(DocumentSentence, id=sentence_id)
    annotations = sentence.annotations.all()

    if request.method == 'POST':
        annotation_id = request.POST.get('annotation_id')
        action = request.POST.get('action')

        if action == 'validate':
            annotation = get_object_or_404(Annotation, id=annotation_id)
            annotation.validation_status = 'validated'
            annotation.validated_by = request.user
            annotation.validated_at = timezone.now()
            annotation.save()

        elif action == 'reject':
            annotation = get_object_or_404(Annotation, id=annotation_id)
            annotation.validation_status = 'rejected'
            annotation.validated_by = request.user
            annotation.validated_at = timezone.now()
            annotation.save()

        return JsonResponse({'status': 'success'})

    context = {
        'sentence': sentence,
        'annotations': annotations,
        'entity_types': RegulatoryEntity.objects.filter(is_active=True),
    }

    return render(request, 'dashboard/annotation_editor.html', context)