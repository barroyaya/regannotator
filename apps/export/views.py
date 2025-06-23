# apps/export/views.py
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from apps.documents.models import Document
from .services import ExportService, ImportService


@login_required
def export_dashboard(request):
    '''Dashboard d'export/import'''
    documents = Document.objects.all().order_by('-created_at')

    context = {
        'documents': documents,
    }

    return render(request, 'export/dashboard.html', context)


@login_required
def export_annotations(request):
    '''Exporter les annotations'''
    format_type = request.GET.get('format', 'csv')
    document_id = request.GET.get('document_id')

    service = ExportService()

    if format_type == 'csv':
        return service.export_annotations_csv(document_id)
    elif format_type == 'json':
        return service.export_annotations_json(document_id)
    else:
        return JsonResponse({'error': 'Format non supporté'}, status=400)


@login_required
def export_document_report(request, document_id):
    '''Exporter le rapport d'un document'''
    service = ExportService()
    return service.export_document_report(document_id)


@login_required
def import_annotations(request):
    '''Importer des annotations'''
    if request.method == 'POST':
        file = request.FILES.get('file')
        document_id = request.POST.get('document_id')

        if not file or not document_id:
            return JsonResponse({'error': 'Fichier et document requis'}, status=400)

        service = ImportService()
        result = service.import_annotations_json(file, document_id)

        if result['success']:
            messages.success(request, f"{result['imported_count']} annotations importées avec succès")
        else:
            messages.error(request, f"Erreur lors de l'import: {result['error']}")

        return JsonResponse(result)

    return JsonResponse({'error': 'Méthode non autorisée'}, status=405)