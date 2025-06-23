# # ===== apps/documents/views.py =====
# from django.shortcuts import render, redirect, get_object_or_404
# from django.contrib.auth.decorators import login_required
# from django.contrib import messages
# from django.http import JsonResponse
# from .models import Document
# from .forms import DocumentUploadForm
# from .services import DocumentProcessingService
#
#
# @login_required
# def upload_document(request):
#     """Upload d'un nouveau document"""
#     if request.method == 'POST':
#         form = DocumentUploadForm(request.POST, request.FILES)
#         if form.is_valid():
#             document = form.save(commit=False)
#             document.created_by = request.user
#             document.save()
#
#             # Traitement asynchrone du document
#             try:
#                 processor = DocumentProcessingService()
#                 processor.process_document(document)
#                 messages.success(request, f"Document '{document.title}' uploadé et traité avec succès.")
#             except Exception as e:
#                 messages.warning(request, f"Document uploadé mais erreur de traitement: {e}")
#
#             return redirect('dashboard:document_detail', document_id=document.id)
#         else:
#             messages.error(request, "Erreur dans le formulaire. Veuillez corriger les erreurs.")
#     else:
#         form = DocumentUploadForm()
#
#     return render(request, 'documents/upload.html', {'form': form})
#
#
# @login_required
# def document_analytics(request, document_id):
#     """Analytics détaillées d'un document"""
#     document = get_object_or_404(Document, id=document_id)
#
#     # Statistiques par entité
#     entity_stats = {}
#     for sentence in document.sentences.all():
#         for annotation in sentence.annotations.all():
#             entity_name = annotation.entity_type.name
#             if entity_name not in entity_stats:
#                 entity_stats[entity_name] = {
#                     'count': 0,
#                     'validated': 0,
#                     'pending': 0,
#                     'rejected': 0,
#                     'avg_confidence': 0
#                 }
#
#             entity_stats[entity_name]['count'] += 1
#             entity_stats[entity_name][annotation.validation_status] += 1
#             entity_stats[entity_name]['avg_confidence'] += annotation.confidence_score
#
#     # Calcul des moyennes
#     for entity in entity_stats.values():
#         if entity['count'] > 0:
#             entity['avg_confidence'] = entity['avg_confidence'] / entity['count']
#
#     context = {
#         'document': document,
#         'entity_stats': entity_stats,
#     }
#
#     return render(request, 'documents/analytics.html', context)


# ===== apps/documents/views.py (MIS À JOUR) =====
import logging
import requests
import tempfile
import os
from urllib.parse import urlparse

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction

from .models import Document, DocumentExtractionLog
from .forms import DocumentUploadForm, DocumentMetadataForm, BulkDocumentUploadForm
from .services import DocumentProcessingService, DocumentAnalyticsService

logger = logging.getLogger(__name__)


@login_required
def upload_document(request):
    """Upload d'un nouveau document avec extraction automatique"""
    if request.method == 'POST':
        form = DocumentUploadForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                with transaction.atomic():
                    # Créer le document
                    document = form.save(commit=False)
                    document.created_by = request.user

                    # Gérer le cas d'une URL
                    url_document = form.cleaned_data.get('url_document')
                    if url_document and not document.file:
                        downloaded_file = _download_file_from_url(url_document)
                        if downloaded_file:
                            document.file = downloaded_file
                            document.url_source = url_document
                        else:
                            messages.error(request, "Impossible de télécharger le fichier depuis l'URL fournie.")
                            return render(request, 'documents/upload.html', {'form': form})

                    # Sauvegarder d'abord pour avoir un ID
                    document.save()

                    # Traitement avec extraction automatique
                    force_manual = form.cleaned_data.get('force_manual_metadata', False)

                    if not force_manual:
                        try:
                            processor = DocumentProcessingService()
                            processing_result = processor.process_document(document)

                            if processing_result['success']:
                                messages.success(
                                    request,
                                    f"Document '{document.effective_title}' uploadé et traité avec succès. "
                                    f"{processing_result['sentences_count']} phrases extraites."
                                )

                                # Afficher les métadonnées extraites
                                extraction_summary = processing_result['metadata_extracted']
                                if extraction_summary['extraction_rate'] > 0:
                                    messages.info(
                                        request,
                                        f"Métadonnées extraites automatiquement "
                                        f"({extraction_summary['extraction_rate']:.0f}% de réussite). "
                                        f"Vous pouvez les modifier si nécessaire."
                                    )
                            else:
                                messages.warning(
                                    request,
                                    f"Document uploadé mais erreur de traitement: {processing_result.get('error', 'Erreur inconnue')}"
                                )
                        except Exception as e:
                            logger.error(f"Erreur lors du traitement automatique: {e}")
                            messages.warning(
                                request,
                                f"Document uploadé mais erreur de traitement automatique. "
                                f"Vous pouvez traiter manuellement depuis la liste des documents."
                            )
                    else:
                        messages.info(
                            request,
                            f"Document '{document.title}' uploadé. Traitement automatique désactivé."
                        )

                    return redirect('dashboard:document_detail', document_id=document.id)

            except Exception as e:
                logger.error(f"Erreur lors de l'upload: {e}")
                messages.error(request, f"Erreur lors de l'upload du document: {e}")
        else:
            messages.error(request, "Erreur dans le formulaire. Veuillez corriger les erreurs.")
    else:
        form = DocumentUploadForm()

    return render(request, 'documents/upload.html', {'form': form})


@login_required
def bulk_upload_documents(request):
    """Upload en lot de documents"""
    if request.method == 'POST':
        form = BulkDocumentUploadForm(request.POST, request.FILES)

        # Récupérer les fichiers manuellement
        files = request.FILES.getlist('files')

        # Validation des fichiers
        if not files:
            messages.error(request, "Aucun fichier sélectionné.")
            return render(request, 'documents/bulk_upload.html', {'form': form})

        if len(files) > 20:
            messages.error(request, "Maximum 20 fichiers autorisés par lot.")
            return render(request, 'documents/bulk_upload.html', {'form': form})

        total_size = sum(f.size for f in files)
        if total_size > 500 * 1024 * 1024:  # 500 MB total
            messages.error(request, "Taille totale des fichiers trop importante (max 500 MB).")
            return render(request, 'documents/bulk_upload.html', {'form': form})

        if form.is_valid():
            default_context = form.cleaned_data['default_context']
            auto_process = form.cleaned_data['auto_process']

            successful_uploads = 0
            failed_uploads = 0

            for file in files:
                try:
                    with transaction.atomic():
                        # Créer le document
                        document = Document.objects.create(
                            title=file.name,  # Sera remplacé par l'extraction automatique
                            file=file,
                            created_by=request.user,
                            document_type='autres',  # Sera détecté automatiquement
                            language='auto'
                        )

                        if auto_process:
                            # Traitement automatique
                            processor = DocumentProcessingService()
                            result = processor.process_document(document)

                            if result['success']:
                                successful_uploads += 1
                            else:
                                failed_uploads += 1
                                logger.error(f"Échec du traitement pour {file.name}: {result.get('error')}")
                        else:
                            successful_uploads += 1

                except Exception as e:
                    failed_uploads += 1
                    logger.error(f"Erreur lors de l'upload de {file.name}: {e}")

            if successful_uploads > 0:
                messages.success(
                    request,
                    f"{successful_uploads} document(s) uploadé(s) avec succès."
                )

            if failed_uploads > 0:
                messages.warning(
                    request,
                    f"{failed_uploads} document(s) ont échoué lors de l'upload."
                )

            return redirect('dashboard:document_list')
    else:
        form = BulkDocumentUploadForm()

    return render(request, 'documents/bulk_upload.html', {'form': form})


@login_required
def edit_document_metadata(request, document_id):
    """Éditer manuellement les métadonnées d'un document"""
    document = get_object_or_404(Document, id=document_id)

    if request.method == 'POST':
        form = DocumentMetadataForm(request.POST, instance=document)
        if form.is_valid():
            form.save()
            messages.success(request, "Métadonnées mises à jour avec succès.")
            return redirect('dashboard:document_detail', document_id=document.id)
    else:
        form = DocumentMetadataForm(instance=document)

    # Obtenir les logs d'extraction
    extraction_logs = document.extraction_logs.all()[:5]  # Les 5 derniers

    context = {
        'document': document,
        'form': form,
        'extraction_logs': extraction_logs,
    }

    return render(request, 'documents/edit_metadata.html', context)


@login_required
def reprocess_document(request, document_id):
    """Retraiter un document (nouvelle extraction)"""
    document = get_object_or_404(Document, id=document_id)

    if request.method == 'POST':
        try:
            processor = DocumentProcessingService()
            result = processor.process_document(document)

            if result['success']:
                messages.success(
                    request,
                    f"Document retraité avec succès. {result['sentences_count']} phrases extraites."
                )
            else:
                messages.error(
                    request,
                    f"Erreur lors du retraitement: {result.get('error', 'Erreur inconnue')}"
                )
        except Exception as e:
            messages.error(request, f"Erreur lors du retraitement: {e}")

        return redirect('dashboard:document_detail', document_id=document.id)

    return render(request, 'documents/reprocess_confirm.html', {'document': document})


@login_required
def document_analytics(request, document_id):
    """Analytics détaillées d'un document"""
    document = get_object_or_404(Document, id=document_id)

    # Obtenir les statistiques
    stats = DocumentAnalyticsService.get_document_statistics(document)

    # Obtenir les logs d'extraction
    extraction_logs = document.extraction_logs.all()

    context = {
        'document': document,
        'stats': stats,
        'extraction_logs': extraction_logs,
    }

    return render(request, 'documents/analytics.html', context)


# @login_required
# def extraction_logs(request):
#     """Vue pour consulter tous les logs d'extraction"""
#     logs = DocumentExtractionLog.objects.select_related('document').all()
#
#     # Filtrage
#     status_filter = request.GET.get('status')
#     context_filter = request.GET.get('context')
#
#     if status_filter:
#         logs = logs.filter(extraction_status=status_filter)
#
#     if context_filter:
#         logs = logs.filter(context=context_filter)
#
#     # Pagination
#     from django.core.paginator import Paginator
#     paginator = Paginator(logs, 25)
#     page_number = request.GET.get('page')
#     page_obj = paginator.get_page(page_number)
#
#     context = {
#         'page_obj': page_obj,
#         'status_choices': DocumentExtractionLog.STATUS_CHOICES,
#         'context_choices': DocumentExtractionLog.CONTEXT_CHOICES,
#         'current_status': status_filter,
#         'current_context': context_filter,
#     }
#
#     return render(request, 'documents/extraction_logs.html', context)

@login_required
def extraction_logs(request):
    """Vue pour consulter tous les logs d'extraction"""
    logs = DocumentExtractionLog.objects.select_related('document').all()
    print("logs:", logs)

    # Filtrage par document spécifique
    document_filter = request.GET.get('document')
    if document_filter:
        logs = logs.filter(document_id=document_filter)

    # Filtrage par statut
    status_filter = request.GET.get('status')
    if status_filter:
        logs = logs.filter(extraction_status=status_filter)

    # Filtrage par contexte
    context_filter = request.GET.get('context')
    if context_filter:
        logs = logs.filter(context=context_filter)

    # Ordonner par date décroissante
    logs = logs.order_by('-scraping_date')

    # Calculer les statistiques
    total_logs = logs.count()
    success_logs = logs.filter(extraction_status='success').count()
    failed_logs = logs.filter(extraction_status='failed').count()
    partial_logs = logs.filter(extraction_status='partial').count()

    # Pagination
    from django.core.paginator import Paginator
    paginator = Paginator(logs, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Récupérer le document pour l'affichage si filtré
    current_document = None
    if document_filter:
        try:
            from .models import Document  # Ajustez l'import selon votre structure
            current_document = Document.objects.get(id=document_filter)
        except Document.DoesNotExist:
            pass

    context = {
        'page_obj': page_obj,
        'status_choices': DocumentExtractionLog.STATUS_CHOICES,
        'context_choices': DocumentExtractionLog.CONTEXT_CHOICES,
        'current_status': status_filter,
        'current_context': context_filter,
        'current_document': current_document,
        'document_filter': document_filter,
        # Statistiques
        'total_logs': total_logs,
        'success_logs': success_logs,
        'failed_logs': failed_logs,
        'partial_logs': partial_logs,
    }

    return render(request, 'documents/extraction_logs.html', context)

def _download_file_from_url(url: str) -> ContentFile:
    """Télécharger un fichier depuis une URL"""
    try:
        # Valider l'URL
        parsed_url = urlparse(url)
        if not parsed_url.scheme or not parsed_url.netloc:
            return None

        # Headers pour simuler un navigateur
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }

        # Télécharger le fichier
        response = requests.get(url, headers=headers, timeout=30, stream=True)
        response.raise_for_status()

        # Vérifier la taille
        content_length = response.headers.get('content-length')
        if content_length and int(content_length) > 100 * 1024 * 1024:  # 100 MB
            return None

        # Déterminer le nom de fichier
        content_disposition = response.headers.get('content-disposition')
        if content_disposition:
            filename = content_disposition.split('filename=')[-1].strip('"')
        else:
            filename = os.path.basename(parsed_url.path) or 'document'

        # Lire le contenu
        content = b''
        for chunk in response.iter_content(chunk_size=8192):
            content += chunk
            if len(content) > 100 * 1024 * 1024:  # 100 MB max
                return None

        return ContentFile(content, name=filename)

    except Exception as e:
        logger.error(f"Erreur lors du téléchargement depuis {url}: {e}")
        return None


# API Views
@login_required
def api_document_metadata(request, document_id):
    """API pour obtenir les métadonnées d'un document"""
    document = get_object_or_404(Document, id=document_id)

    data = {
        'id': document.id,
        'title': document.effective_title,
        'auto_extracted_title': document.auto_extracted_title,
        'title_manually_edited': document.title_manually_edited,

        'publication_date': document.effective_date.isoformat() if document.effective_date else None,
        'auto_extracted_date': document.auto_extracted_date.isoformat() if document.auto_extracted_date else None,
        'date_manually_edited': document.date_manually_edited,

        'language': document.effective_language,
        'auto_extracted_language': document.auto_extracted_language,
        'language_manually_edited': document.language_manually_edited,

        'source': document.source.name if document.source else None,
        'auto_extracted_source': document.auto_extracted_source,
        'source_manually_edited': document.source_manually_edited,

        'version': document.version,
        'auto_extracted_version': document.auto_extracted_version,

        'country': document.auto_extracted_country,
        'document_type': document.document_type,

        'extraction_confidence': document.extraction_confidence,
        'extraction_summary': document.extraction_summary,

        'status': document.status,
        'file_type': document.file_type,
        'file_size_mb': document.file_size_mb,
    }

    return JsonResponse(data)


@login_required
def api_reextract_metadata(request, document_id):
    """API pour relancer l'extraction de métadonnées"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    document = get_object_or_404(Document, id=document_id)

    try:
        from .services.metadata_extraction import MetadataExtractionService
        extractor = MetadataExtractionService()
        extraction_log = extractor.extract_metadata(document)

        return JsonResponse({
            'success': True,
            'message': 'Métadonnées réextraites avec succès',
            'extraction_log_id': extraction_log.id,
            'metadata': {
                'title': document.auto_extracted_title,
                'date': document.auto_extracted_date.isoformat() if document.auto_extracted_date else None,
                'language': document.auto_extracted_language,
                'source': document.auto_extracted_source,
                'version': document.auto_extracted_version,
                'country': document.auto_extracted_country,
            }
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required


# @login_required
# @require_http_methods(["GET"])
# def extraction_log_details(request, log_id):
#     """API pour récupérer les détails d'un log d'extraction"""
#     try:
#         log = DocumentExtractionLog.objects.select_related('document').get(id=log_id)
#
#         # Déterminer la couleur du statut
#         status_colors = {
#             'success': 'success',
#             'partial': 'warning',
#             'failed': 'danger',
#             'processing': 'info'
#         }
#
#         data = {
#             'success': True,
#             'log': {
#                 'id': log.id,
#                 'document_id': log.document.id,
#                 'document_title': log.document.effective_title,
#                 'file_type': log.file_type,
#                 'url': log.url,
#                 'extraction_date': log.scraping_date.strftime('%d/%m/%Y %H:%M'),
#                 'status_label': log.get_extraction_status_display(),
#                 'status_color': status_colors.get(log.extraction_status, 'secondary'),
#                 'context_label': log.get_context_display(),
#                 'processing_time': log.processing_time if log.processing_time else 'N/A',
#
#                 # Métadonnées extraites
#                 'extracted_title': log.extracted_title,
#                 'extracted_date': log.extracted_date.strftime('%d/%m/%Y') if log.extracted_date else None,
#                 'extracted_language': log.extracted_language,
#                 'extracted_source': log.extracted_source,
#                 'extracted_version': log.extracted_version,
#
#                 # Scores de confiance
#                 'confidence_title': log.confidence_title,
#                 'confidence_date': log.confidence_date,
#                 'confidence_language': log.confidence_language,
#                 'confidence_source': log.confidence_source,
#                 'confidence_version': log.confidence_version,
#
#                 # Autres informations
#                 'notes': log.notes if hasattr(log, 'notes') else None,
#                 'error_message': log.error_message if hasattr(log, 'error_message') else None,
#             }
#         }
#
#         return JsonResponse(data)
#
#     except DocumentExtractionLog.DoesNotExist:
#         return JsonResponse({
#             'success': False,
#             'error': 'Log d\'extraction non trouvé'
#         }, status=404)
#     except Exception as e:
#         return JsonResponse({
#             'success': False,
#             'error': str(e)
#         }, status=500)

@login_required
@require_http_methods(["GET"])
def extraction_log_details(request, log_id):
    """API pour récupérer les détails d'un log d'extraction"""
    try:
        # Importer le modèle (ajustez selon votre structure)


        log = DocumentExtractionLog.objects.select_related('document').get(id=log_id)

        # Déterminer la couleur du statut
        status_colors = {
            'success': 'success',
            'partial': 'warning',
            'failed': 'danger',
            'processing': 'info',
            'pending': 'secondary'
        }

        # Préparer les données du document avec fallbacks
        document_title = (
                getattr(log.document, 'effective_title', None) or
                getattr(log.document, 'title', None) or
                f"Document #{log.document.id}"
        )

        data = {
            'success': True,
            'log': {
                'id': log.id,
                'document_id': log.document.id,
                'document_title': document_title,
                'file_type': getattr(log, 'file_type', None),
                'url': getattr(log, 'url', None),
                'extraction_date': log.scraping_date.strftime('%d/%m/%Y %H:%M') if log.scraping_date else 'N/A',
                'status_label': log.get_extraction_status_display() if hasattr(log,
                                                                               'get_extraction_status_display') else log.extraction_status,
                'status_color': status_colors.get(log.extraction_status, 'secondary'),
                'context_label': log.get_context_display() if hasattr(log, 'get_context_display') else getattr(log,
                                                                                                               'context',
                                                                                                               'N/A'),
                'processing_time': f"{log.processing_time:.2f}s" if getattr(log, 'processing_time', None) else 'N/A',

                # Métadonnées extraites avec gestion des champs optionnels
                'extracted_title': getattr(log, 'extracted_title', None),
                'extracted_date': log.extracted_date.strftime('%d/%m/%Y') if getattr(log, 'extracted_date',
                                                                                     None) else None,
                'extracted_language': getattr(log, 'extracted_language', None),
                'extracted_source': getattr(log, 'extracted_source', None),
                'extracted_version': getattr(log, 'extracted_version', None),

                # Scores de confiance avec gestion des valeurs nulles
                'confidence_title': getattr(log, 'confidence_title', None),
                'confidence_date': getattr(log, 'confidence_date', None),
                'confidence_language': getattr(log, 'confidence_language', None),
                'confidence_source': getattr(log, 'confidence_source', None),
                'confidence_version': getattr(log, 'confidence_version', None),

                # Informations additionnelles
                'notes': getattr(log, 'notes', None),
                'error_message': getattr(log, 'error_message', None),
            }
        }

        return JsonResponse(data)

    except DocumentExtractionLog.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Log d\'extraction non trouvé'
        }, status=404)
    except Exception as e:
        # Log l'erreur pour le debugging
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Erreur dans extraction_log_details: {str(e)}")

        return JsonResponse({
            'success': False,
            'error': f'Erreur serveur: {str(e)}'
        }, status=500)


import csv
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from django.utils import timezone


@login_required
def export_extraction_logs(request):
    """Export des logs d'extraction en CSV"""
    try:
        # Importer le modèle

        # Récupérer les logs avec les mêmes filtres que la vue principale
        logs = DocumentExtractionLog.objects.select_related('document').all()

        # Appliquer les filtres
        document_filter = request.GET.get('document')
        status_filter = request.GET.get('status')
        context_filter = request.GET.get('context')

        if document_filter:
            logs = logs.filter(document_id=document_filter)
        if status_filter:
            logs = logs.filter(extraction_status=status_filter)
        if context_filter:
            logs = logs.filter(context=context_filter)

        logs = logs.order_by('-scraping_date')

        # Créer la réponse HTTP avec le type de contenu CSV
        response = HttpResponse(content_type='text/csv')
        response[
            'Content-Disposition'] = f'attachment; filename="extraction_logs_{timezone.now().strftime("%Y%m%d_%H%M%S")}.csv"'

        # Créer le writer CSV
        writer = csv.writer(response)

        # Écrire l'en-tête
        writer.writerow([
            'ID Log',
            'Document ID',
            'Titre Document',
            'Date Extraction',
            'Statut',
            'Contexte',
            'Type Fichier',
            'URL',
            'Titre Extrait',
            'Date Extraite',
            'Langue Extraite',
            'Source Extraite',
            'Version Extraite',
            'Confiance Titre (%)',
            'Confiance Date (%)',
            'Confiance Langue (%)',
            'Confiance Source (%)',
            'Confiance Version (%)',
            'Temps Traitement (s)',
            'Notes',
            'Message Erreur'
        ])

        # Écrire les données
        for log in logs:
            document_title = (
                    getattr(log.document, 'effective_title', None) or
                    getattr(log.document, 'title', None) or
                    f"Document #{log.document.id}"
            )

            writer.writerow([
                log.id,
                log.document.id,
                document_title,
                log.scraping_date.strftime('%d/%m/%Y %H:%M') if log.scraping_date else '',
                log.get_extraction_status_display() if hasattr(log,
                                                               'get_extraction_status_display') else log.extraction_status,
                log.get_context_display() if hasattr(log, 'get_context_display') else getattr(log, 'context', ''),
                getattr(log, 'file_type', ''),
                getattr(log, 'url', ''),
                getattr(log, 'extracted_title', ''),
                log.extracted_date.strftime('%d/%m/%Y') if getattr(log, 'extracted_date', None) else '',
                getattr(log, 'extracted_language', ''),
                getattr(log, 'extracted_source', ''),
                getattr(log, 'extracted_version', ''),
                getattr(log, 'confidence_title', ''),
                getattr(log, 'confidence_date', ''),
                getattr(log, 'confidence_language', ''),
                getattr(log, 'confidence_source', ''),
                getattr(log, 'confidence_version', ''),
                getattr(log, 'processing_time', ''),
                getattr(log, 'notes', ''),
                getattr(log, 'error_message', '')
            ])

        return response

    except Exception as e:
        # En cas d'erreur, retourner une réponse d'erreur
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Erreur dans export_extraction_logs: {str(e)}")

        response = HttpResponse(content_type='text/plain')
        response.status_code = 500
        response.content = f"Erreur lors de l'export: {str(e)}"
        return response