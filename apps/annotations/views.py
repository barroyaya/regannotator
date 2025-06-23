import json

from django.contrib.auth.models import User
from django.db.models.functions import Round
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Avg, Q, FloatField, F
from django.http import Http404

from .models import Annotation, ExpertFeedback, AnnotationSession
from apps.documents.models import DocumentSentence
from apps.core.models import RegulatoryEntity


@login_required
@csrf_exempt
def validate_annotation(request, annotation_id):
    """Validation/rejet d'une annotation par un expert"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    annotation = get_object_or_404(Annotation, id=annotation_id)

    try:
        data = json.loads(request.body)
        action = data.get('action')

        if action == 'validate':
            annotation.validation_status = 'validated'
            annotation.validated_by = request.user
            annotation.validated_at = timezone.now()
            annotation.save()
            return JsonResponse({'status': 'success', 'message': 'Annotation validée'})

        elif action == 'reject':
            annotation.validation_status = 'rejected'
            annotation.validated_by = request.user
            annotation.validated_at = timezone.now()
            annotation.save()
            return JsonResponse({'status': 'success', 'message': 'Annotation rejetée'})

        elif action == 'modify':
            new_value = data.get('new_value')
            if new_value:
                # Créer un feedback avec la correction
                feedback = ExpertFeedback.objects.create(
                    annotation=annotation,
                    expert=request.user,
                    feedback_type='correction',
                    suggested_value=new_value,
                    comment=data.get('comment', '')
                )

                annotation.validation_status = 'modified'
                annotation.validated_by = request.user
                annotation.validated_at = timezone.now()
                annotation.text_value = new_value
                annotation.save()
                return JsonResponse({'status': 'success', 'message': 'Annotation modifiée'})

        return JsonResponse({'error': 'Action invalide'}, status=400)

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Données JSON invalides'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Avg, Q
from .models import Annotation

# views.py - Version corrigée
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Avg, Q
from django.http import JsonResponse
import json
from .models import Annotation

import json
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Count, Avg, Q, F, FloatField
from django.db.models.functions import Round
from .models import Annotation


@login_required
def annotation_statistics(request):
    """Statistiques globales des annotations optimisées pour de gros volumes"""

    # Calculs globaux d'abord
    total_annotations = Annotation.objects.count()
   

    # Stats de validation en une seule requête
    validation_stats = Annotation.objects.aggregate(
        validated=Count('id', filter=Q(validation_status='validated')),
        pending=Count('id', filter=Q(validation_status='pending')),
        rejected=Count('id', filter=Q(validation_status='rejected'))
    )

    # Stats par entité (limitées au top 15 + autres pour éviter la surcharge)
    entity_stats_full = (
        Annotation.objects
        .values('entity_type__name')
        .annotate(
            count=Count('id'),
            avg_confidence=Round(Avg('confidence_score'), 2),
            validated_count=Count('id', filter=Q(validation_status='validated')),
            rejected_count=Count('id', filter=Q(validation_status='rejected'))
        )
        .order_by('-count')
    )

    # Calculs globaux d'abord pour avoir total_annotations
    total_annotations = Annotation.objects.count()

    # Prendre les 15 premières entités pour éviter la surcharge du graphique
    top_entities = list(entity_stats_full[:15])


    # Ajouter les pourcentages aux entités principales
    for entity in top_entities:
        entity['percentage'] = round((entity['count'] / total_annotations * 100), 1) if total_annotations > 0 else 0

    # Calculer le reste des entités pour la catégorie "Autres"
    remaining_entities = entity_stats_full[15:]
    if remaining_entities:
        others_total = sum(e['count'] for e in remaining_entities)
        if others_total > 0:
            # Calculer la moyenne pondérée pour la confiance
            weighted_confidence_sum = sum(
                (e['avg_confidence'] or 0) * e['count']
                for e in remaining_entities
            )
            others_avg_confidence = round(weighted_confidence_sum / others_total, 2)

            others_validated = sum(e['validated_count'] for e in remaining_entities)
            others_rejected = sum(e['rejected_count'] for e in remaining_entities)

            # Ajouter la catégorie "Autres"
            top_entities.append({
                'entity_type__name': 'Autres',
                'count': others_total,
                'avg_confidence': others_avg_confidence,
                'validated_count': others_validated,
                'rejected_count': others_rejected,
                'percentage': round((others_total / total_annotations * 100), 1) if total_annotations > 0 else 0
            })


    # Stats par expert (top 10 avec gestion des erreurs)
    expert_stats = []
    try:
        expert_stats = (
            Annotation.objects
            .filter(validated_by__isnull=False)
            .values('validated_by__username')
            .annotate(
                total_validated=Count('id'),
                validated_count=Count('id', filter=Q(validation_status='validated')),
                rejected_count=Count('id', filter=Q(validation_status='rejected'))
            )
            .annotate(
                validation_rate=Round(
                    (100.0 * F('validated_count')) / F('total_validated'),
                    output_field=FloatField()
                )
            )
            .order_by('-total_validated')[:10]
        )
    except Exception as e:
        print(f"Erreur lors du calcul des stats experts: {e}")
        expert_stats = []

    # Compter les experts uniques de manière plus efficace
    total_experts = User.objects.filter(
        id__in=Annotation.objects.filter(
            validated_by__isnull=False
        ).values_list('validated_by', flat=True).distinct()
    ).count()

    # Confiance moyenne
    avg_confidence_result = Annotation.objects.aggregate(
        avg=Avg('confidence_score')
    )
    avg_confidence = round(avg_confidence_result['avg'] or 0, 2)

    # Taux de validation global
    validation_rate = round(
        (validation_stats['validated'] / total_annotations * 100),
        2
    ) if total_annotations > 0 else 0

    # Préparation des données pour les graphiques (limitées pour performance)
    entity_labels = [e['entity_type__name'] for e in top_entities]
    entity_counts = [e['count'] for e in top_entities]

    # Données de validation pour le graphique en secteurs avec pourcentages
    validation_data = [
        validation_stats['validated'],
        validation_stats['pending'],
        validation_stats['rejected']
    ]

    # Calculer les pourcentages pour les métriques de validation
    validation_percentages = {
        'validated_percentage': round((validation_stats['validated'] / total_annotations * 100),
                                      1) if total_annotations > 0 else 0,
        'pending_percentage': round((validation_stats['pending'] / total_annotations * 100),
                                    1) if total_annotations > 0 else 0,
        'rejected_percentage': round((validation_stats['rejected'] / total_annotations * 100),
                                     1) if total_annotations > 0 else 0,
    }

    context = {
        'entity_stats': top_entities,  # Limitées pour l'affichage
        'expert_stats': expert_stats,
        'total_annotations': total_annotations,
        'total_experts': total_experts,
        'avg_confidence': avg_confidence,
        'validation_rate': validation_rate,
        'validation_stats': validation_stats,
        'validation_percentages': validation_percentages,  # Ajout des pourcentages

        # Données JSON pour les graphiques
        'entity_labels_json': json.dumps(entity_labels),
        'entity_counts_json': json.dumps(entity_counts),
        'validation_data_json': json.dumps(validation_data),

        # Informations additionnelles
        'entities_total_count': entity_stats_full.count(),  # Nombre total d'entités
        'entities_shown_count': len(top_entities),  # Nombre d'entités affichées
    }

    return render(request, 'annotations/statistics.html', context)
@login_required
def batch_validate_annotations(request):
    """Validation en lot des annotations"""
    if request.method == 'POST':
        annotation_ids = request.POST.getlist('annotation_ids')
        action = request.POST.get('action')  # 'validate' ou 'reject'

        if not annotation_ids:
            messages.error(request, 'Aucune annotation sélectionnée.')
            return redirect('dashboard:home')

        count = 0
        for annotation_id in annotation_ids:
            try:
                annotation = Annotation.objects.get(id=annotation_id)
                if action == 'validate':
                    annotation.validation_status = 'validated'
                elif action == 'reject':
                    annotation.validation_status = 'rejected'
                else:
                    continue

                annotation.validated_by = request.user
                annotation.validated_at = timezone.now()
                annotation.save()
                count += 1
            except Annotation.DoesNotExist:
                continue

        action_text = 'validées' if action == 'validate' else 'rejetées'
        messages.success(request, f'{count} annotations {action_text} avec succès.')

    return redirect('dashboard:home')


@login_required
def annotation_editor(request, sentence_id):
    """Éditeur d'annotations pour une phrase"""
    sentence = get_object_or_404(DocumentSentence, id=sentence_id)
    annotations = sentence.annotations.select_related('entity_type').all()
    entity_types = RegulatoryEntity.objects.filter(is_active=True)

    if request.method == 'POST':
        # Gestion des modifications d'annotations
        annotation_id = request.POST.get('annotation_id')
        action = request.POST.get('action')

        if action == 'validate' and annotation_id:
            annotation = get_object_or_404(Annotation, id=annotation_id)
            annotation.validation_status = 'validated'
            annotation.validated_by = request.user
            annotation.validated_at = timezone.now()
            annotation.save()
            messages.success(request, 'Annotation validée.')

        elif action == 'reject' and annotation_id:
            annotation = get_object_or_404(Annotation, id=annotation_id)
            annotation.validation_status = 'rejected'
            annotation.validated_by = request.user
            annotation.validated_at = timezone.now()
            annotation.save()
            messages.success(request, 'Annotation rejetée.')

        return redirect('annotations:annotation_editor', sentence_id=sentence.id)

    context = {
        'sentence': sentence,
        'annotations': annotations,
        'entity_types': entity_types,
    }
    return render(request, 'annotations/editor.html', context)


@login_required
def create_annotation(request):
    """Créer une nouvelle annotation manuellement"""
    if request.method == 'POST':
        sentence_id = request.POST.get('sentence_id')
        entity_type_id = request.POST.get('entity_type_id')
        text_value = request.POST.get('text_value')
        start_position = request.POST.get('start_position', 0)
        end_position = request.POST.get('end_position', 0)

        try:
            sentence = DocumentSentence.objects.get(id=sentence_id)
            entity_type = RegulatoryEntity.objects.get(id=entity_type_id)

            annotation = Annotation.objects.create(
                sentence=sentence,
                entity_type=entity_type,
                text_value=text_value,
                start_position=int(start_position),
                end_position=int(end_position),
                confidence_score=1.0,  # Score maximal pour annotation manuelle
                source='expert',
                created_by=request.user
            )

            messages.success(request, 'Annotation créée avec succès.')
            return redirect('annotations:annotation_editor', sentence_id=sentence.id)

        except (DocumentSentence.DoesNotExist, RegulatoryEntity.DoesNotExist, ValueError):
            messages.error(request, 'Erreur lors de la création de l\'annotation.')

    # GET request - afficher le formulaire
    sentences = DocumentSentence.objects.select_related('document').all()[:100]  # Limiter pour performance
    entity_types = RegulatoryEntity.objects.filter(is_active=True)

    context = {
        'sentences': sentences,
        'entity_types': entity_types,
    }
    return render(request, 'annotations/create.html', context)


@login_required
def edit_annotation(request, annotation_id):
    """Éditer une annotation existante"""
    annotation = get_object_or_404(Annotation, id=annotation_id)

    if request.method == 'POST':
        new_text_value = request.POST.get('text_value')
        new_entity_type_id = request.POST.get('entity_type_id')
        comment = request.POST.get('comment', '')

        if new_text_value and new_entity_type_id:
            try:
                entity_type = RegulatoryEntity.objects.get(id=new_entity_type_id)

                # Créer un feedback pour tracer la modification
                ExpertFeedback.objects.create(
                    annotation=annotation,
                    expert=request.user,
                    feedback_type='correction',
                    comment=f'Modifié de "{annotation.text_value}" vers "{new_text_value}". {comment}',
                    suggested_value=new_text_value
                )

                # Mettre à jour l'annotation
                annotation.text_value = new_text_value
                annotation.entity_type = entity_type
                annotation.validation_status = 'modified'
                annotation.validated_by = request.user
                annotation.validated_at = timezone.now()
                annotation.save()

                messages.success(request, 'Annotation modifiée avec succès.')
                return redirect('annotations:annotation_editor', sentence_id=annotation.sentence.id)

            except RegulatoryEntity.DoesNotExist:
                messages.error(request, 'Type d\'entité invalide.')

    entity_types = RegulatoryEntity.objects.filter(is_active=True)
    context = {
        'annotation': annotation,
        'entity_types': entity_types,
    }
    return render(request, 'annotations/edit.html', context)


@login_required
def delete_annotation(request, annotation_id):
    """Supprimer une annotation"""
    annotation = get_object_or_404(Annotation, id=annotation_id)
    sentence_id = annotation.sentence.id

    if request.method == 'POST':
        annotation.delete()
        messages.success(request, 'Annotation supprimée avec succès.')
        return redirect('annotations:annotation_editor', sentence_id=sentence_id)

    context = {'annotation': annotation}
    return render(request, 'annotations/delete_confirm.html', context)


@login_required
def add_feedback(request, annotation_id):
    """Ajouter un feedback expert"""
    annotation = get_object_or_404(Annotation, id=annotation_id)

    if request.method == 'POST':
        feedback_type = request.POST.get('feedback_type')
        comment = request.POST.get('comment')
        suggested_value = request.POST.get('suggested_value', '')

        if feedback_type and comment:
            ExpertFeedback.objects.create(
                annotation=annotation,
                expert=request.user,
                feedback_type=feedback_type,
                comment=comment,
                suggested_value=suggested_value
            )

            messages.success(request, 'Feedback ajouté avec succès.')
            return redirect('annotations:annotation_editor', sentence_id=annotation.sentence.id)

    context = {'annotation': annotation}
    return render(request, 'annotations/add_feedback.html', context)


@login_required
def feedback_list(request):
    """Liste des feedbacks d'experts"""
    feedbacks = ExpertFeedback.objects.select_related(
        'annotation__entity_type',
        'annotation__sentence__document',
        'expert'
    ).order_by('-created_at')

    # Pagination
    paginator = Paginator(feedbacks, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {'page_obj': page_obj}
    return render(request, 'annotations/feedback_list.html', context)


from django.core.paginator import Paginator
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from apps.annotations.models import AnnotationSession

from datetime import timedelta

@login_required
def annotation_sessions(request):
    sessions = AnnotationSession.objects.select_related('document').order_by('-created_at')

    status_filter = request.GET.get('status')
    if status_filter:
        sessions = sessions.filter(status=status_filter)

    paginator = Paginator(sessions, 15)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    for session in page_obj:
        if session.status == 'completed' and session.updated_at:
            session.duration = session.updated_at - session.created_at
        else:
            session.duration = None

        # Phrases traitées
        if hasattr(session.document, 'sentences'):
            session.total_sentences = session.document.sentences.count()
            session.processed_sentences = session.document.sentences.filter(is_processed=True).count()
        else:
            session.total_sentences = 0
            session.processed_sentences = 0

    context = {
        'page_obj': page_obj,
        'status_choices': AnnotationSession.status.field.choices,
        'current_status': status_filter,
    }
    return render(request, 'annotations/sessions.html', context)



@login_required
def session_detail(request, session_id):
    """Détail d'une session d'annotation"""
    session = get_object_or_404(AnnotationSession, id=session_id)

    # Statistiques de la session
    total_sentences = session.document.sentences.count()
    processed_sentences = session.document.sentences.filter(is_processed=True).count()
    total_annotations = Annotation.objects.filter(sentence__document=session.document).count()

    context = {
        'session': session,
        'total_sentences': total_sentences,
        'processed_sentences': processed_sentences,
        'total_annotations': total_annotations,
    }
    return render(request, 'annotations/session_detail.html', context)


@login_required
def create_annotation_session(request):
    """Créer une nouvelle session d'annotation"""
    if request.method == 'POST':
        document_id = request.POST.get('document_id')
        llm_model = request.POST.get('llm_model', 'mistral-7b-instruct')

        try:
            from apps.documents.models import Document
            document = Document.objects.get(id=document_id)

            session = AnnotationSession.objects.create(
                document=document,
                llm_model=llm_model,
                created_by=request.user,
                status='running'
            )

            # Démarrer l'annotation asynchrone (si Celery est configuré)
            try:
                from apps.annotations.tasks import process_document_annotations
                process_document_annotations.delay(document.id)
            except ImportError:
                # Fallback synchrone si pas de Celery
                from apps.annotations.services import LLMAnnotationService
                annotator = LLMAnnotationService()
                for sentence in document.sentences.filter(is_processed=False):
                    annotator.annotate_sentence(sentence)
                session.status = 'completed'
                session.save()

            messages.success(request, 'Session d\'annotation créée et démarrée.')
            return redirect('annotations:session_detail', session_id=session.id)

        except Document.DoesNotExist:
            messages.error(request, 'Document introuvable.')

    from apps.documents.models import Document
    documents = Document.objects.filter(status='uploaded').order_by('-created_at')

    context = {'documents': documents}
    return render(request, 'annotations/create_session.html', context)


@login_required
def export_annotations(request):
    """Exporter les annotations"""
    format_type = request.GET.get('format', 'csv')
    document_id = request.GET.get('document_id')

    from apps.export.services import ExportService
    service = ExportService()

    if format_type == 'csv':
        return service.export_annotations_csv(document_id)
    elif format_type == 'json':
        return service.export_annotations_json(document_id)
    else:
        messages.error(request, 'Format non supporté.')
        return redirect('export:dashboard')


@login_required
def import_annotations(request):
    """Importer des annotations"""
    if request.method == 'POST':
        file = request.FILES.get('file')
        document_id = request.POST.get('document_id')

        if not file or not document_id:
            messages.error(request, 'Fichier et document requis.')
            return redirect('export:dashboard')

        from apps.export.services import ImportService
        service = ImportService()
        result = service.import_annotations_json(file, document_id)

        if result['success']:
            messages.success(request, f"{result['imported_count']} annotations importées.")
        else:
            messages.error(request, f"Erreur: {result['error']}")

    return redirect('export:dashboard')


# API Views
@login_required
def get_entity_types(request):
    """API pour récupérer les types d'entités"""
    entities = RegulatoryEntity.objects.filter(is_active=True)
    data = [
        {
            'id': entity.id,
            'name': entity.name,
            'description': entity.description,
            'color': entity.color
        }
        for entity in entities
    ]
    return JsonResponse(data, safe=False)


@login_required
@csrf_exempt
def api_validate_annotation(request):
    """API pour valider une annotation"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        data = json.loads(request.body)
        annotation_id = data.get('annotation_id')
        action = data.get('action')

        annotation = get_object_or_404(Annotation, id=annotation_id)

        if action in ['validate', 'reject']:
            annotation.validation_status = 'validated' if action == 'validate' else 'rejected'
            annotation.validated_by = request.user
            annotation.validated_at = timezone.now()
            annotation.save()

            return JsonResponse({
                'status': 'success',
                'annotation_id': annotation.id,
                'new_status': annotation.validation_status
            })
        else:
            return JsonResponse({'error': 'Action invalide'}, status=400)

    except json.JSONDecodeError:
        return JsonResponse({'error': 'JSON invalide'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# ===== apps/annotations/views.py (nouvelles vues pour l'API) =====
import json
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Avg, Q


from apps.documents.models import DocumentSentence, Document
from apps.core.models import RegulatoryEntity


@login_required
@csrf_exempt
def batch_create_annotations(request):
    """Créer plusieurs annotations en une seule requête"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        data = json.loads(request.body)
        document_id = data.get('document_id')
        annotations_data = data.get('annotations', [])

        document = get_object_or_404(Document, id=document_id)
        created_count = 0

        for ann_data in annotations_data:
            # Déterminer la phrase à partir de la position dans le texte
            sentence = find_sentence_by_position(document, ann_data.get('global_start', 0))

            if sentence:
                entity_type = get_object_or_404(RegulatoryEntity, id=ann_data['entity_type_id'])

                Annotation.objects.create(
                    sentence=sentence,
                    entity_type=entity_type,
                    text_value=ann_data['text'],
                    start_position=ann_data.get('start_position', 0),
                    end_position=ann_data.get('end_position', 0),
                    confidence_score=1.0,
                    source='expert',
                    created_by=request.user,
                    validation_status='validated'
                )
                created_count += 1

        return JsonResponse({
            'success': True,
            'created_count': created_count,
            'message': f'{created_count} annotations créées avec succès'
        })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def find_sentence_by_position(document, global_position):
    """Trouver la phrase correspondant à une position globale dans le document"""
    # Logique simplifiée - dans une vraie implémentation,
    # il faudrait calculer les positions exactes
    sentences = document.sentences.order_by('sentence_number')

    # Pour l'instant, on retourne la première phrase
    # À améliorer selon votre logique de calcul de position
    return sentences.first() if sentences.exists() else None


@login_required
def get_annotation_statistics(request, document_id):
    """Statistiques d'annotations pour un document"""
    document = get_object_or_404(Document, id=document_id)

    # Statistiques par type d'entité
    entity_stats = (
        Annotation.objects
        .filter(sentence__document=document)
        .values('entity_type__name', 'entity_type__color')
        .annotate(
            count=Count('id'),
            avg_confidence=Avg('confidence_score')
        )
        .order_by('-count')
    )

    # Statistiques générales
    total_annotations = Annotation.objects.filter(sentence__document=document).count()
    validated_annotations = Annotation.objects.filter(
        sentence__document=document,
        validation_status='validated'
    ).count()

    return JsonResponse({
        'success': True,
        'stats': {
            'total_annotations': total_annotations,
            'validated_annotations': validated_annotations,
            'validation_rate': (validated_annotations / total_annotations * 100) if total_annotations > 0 else 0,
            'entity_stats': list(entity_stats)
        }
    })


@login_required
@csrf_exempt
def update_annotation(request, annotation_id):
    """Mettre à jour une annotation existante"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    annotation = get_object_or_404(Annotation, id=annotation_id)

    try:
        data = json.loads(request.body)

        # Mettre à jour les champs modifiables
        if 'text_value' in data:
            annotation.text_value = data['text_value']

        if 'entity_type_id' in data:
            entity_type = get_object_or_404(RegulatoryEntity, id=data['entity_type_id'])
            annotation.entity_type = entity_type

        if 'validation_status' in data:
            annotation.validation_status = data['validation_status']
            annotation.validated_by = request.user
            annotation.validated_at = timezone.now()

        annotation.save()

        return JsonResponse({
            'success': True,
            'message': 'Annotation mise à jour',
            'annotation': {
                'id': annotation.id,
                'text_value': annotation.text_value,
                'entity_type': annotation.entity_type.name,
                'validation_status': annotation.validation_status
            }
        })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@csrf_exempt
def delete_annotation(request, annotation_id):
    """Supprimer une annotation"""
    if request.method != 'DELETE':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    annotation = get_object_or_404(Annotation, id=annotation_id)
    annotation.delete()

    return JsonResponse({
        'success': True,
        'message': 'Annotation supprimée'
    })


