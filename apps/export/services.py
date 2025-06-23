# apps/export/services.py
import json
import csv
import xml.etree.ElementTree as ET
from io import StringIO, BytesIO
from django.http import HttpResponse
from django.utils import timezone

from apps.documents.models import Document
from apps.annotations.models import Annotation


class ExportService:
    '''Service d'export des données'''

    def export_annotations_csv(self, document_id=None):
        '''Exporter les annotations en CSV'''
        queryset = Annotation.objects.select_related('entity_type', 'sentence__document')

        if document_id:
            queryset = queryset.filter(sentence__document_id=document_id)

        output = StringIO()
        writer = csv.writer(output)

        # En-têtes
        writer.writerow([
            'Document', 'Phrase', 'Entité', 'Valeur', 'Position Début',
            'Position Fin', 'Confiance', 'Statut', 'Source', 'Date Création'
        ])

        # Données
        for annotation in queryset:
            writer.writerow([
                annotation.sentence.document.title,
                annotation.sentence.sentence_number,
                annotation.entity_type.name,
                annotation.text_value,
                annotation.start_position,
                annotation.end_position,
                annotation.confidence_score,
                annotation.validation_status,
                annotation.source,
                annotation.created_at.strftime('%Y-%m-%d %H:%M:%S')
            ])

        response = HttpResponse(output.getvalue(), content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="annotations.csv"'
        return response

    def export_annotations_json(self, document_id=None):
        '''Exporter les annotations en JSON'''
        queryset = Annotation.objects.select_related('entity_type', 'sentence__document')

        if document_id:
            queryset = queryset.filter(sentence__document_id=document_id)

        data = {
            'export_date': timezone.now().isoformat(),
            'total_annotations': queryset.count(),
            'annotations': []
        }

        for annotation in queryset:
            data['annotations'].append({
                'id': annotation.id,
                'document': {
                    'id': annotation.sentence.document.id,
                    'title': annotation.sentence.document.title
                },
                'sentence': {
                    'number': annotation.sentence.sentence_number,
                    'text': annotation.sentence.text
                },
                'entity': {
                    'type': annotation.entity_type.name,
                    'value': annotation.text_value,
                    'start_position': annotation.start_position,
                    'end_position': annotation.end_position
                },
                'metadata': {
                    'confidence_score': annotation.confidence_score,
                    'validation_status': annotation.validation_status,
                    'source': annotation.source,
                    'created_at': annotation.created_at.isoformat()
                }
            })

        response = HttpResponse(
            json.dumps(data, indent=2, ensure_ascii=False),
            content_type='application/json'
        )
        response['Content-Disposition'] = 'attachment; filename="annotations.json"'
        return response

    def export_document_report(self, document_id):
        '''Générer un rapport complet pour un document'''
        document = Document.objects.get(id=document_id)
        annotations = Annotation.objects.filter(sentence__document=document)

        # Statistiques
        total_annotations = annotations.count()
        validated_annotations = annotations.filter(validation_status='validated').count()

        # Répartition par entité
        entity_stats = {}
        for annotation in annotations:
            entity_name = annotation.entity_type.name
            if entity_name not in entity_stats:
                entity_stats[entity_name] = {'count': 0, 'validated': 0}
            entity_stats[entity_name]['count'] += 1
            if annotation.validation_status == 'validated':
                entity_stats[entity_name]['validated'] += 1

        report = {
            'document': {
                'title': document.title,
                'source': document.source.name,
                'type': document.get_document_type_display(),
                'created_at': document.created_at.isoformat()
            },
            'statistics': {
                'total_sentences': document.sentences.count(),
                'total_annotations': total_annotations,
                'validated_annotations': validated_annotations,
                'validation_rate': (validated_annotations / total_annotations * 100) if total_annotations > 0 else 0
            },
            'entity_breakdown': entity_stats,
            'annotations': []
        }

        # Détail des annotations
        for annotation in annotations.select_related('entity_type', 'sentence'):
            report['annotations'].append({
                'sentence_number': annotation.sentence.sentence_number,
                'entity_type': annotation.entity_type.name,
                'text_value': annotation.text_value,
                'confidence_score': annotation.confidence_score,
                'validation_status': annotation.validation_status
            })

        response = HttpResponse(
            json.dumps(report, indent=2, ensure_ascii=False),
            content_type='application/json'
        )
        response['Content-Disposition'] = f'attachment; filename="rapport_{document.id}.json"'
        return response


class ImportService:
    '''Service d'import des données'''

    def import_annotations_json(self, file, document_id):
        '''Importer des annotations depuis un fichier JSON'''
        try:
            data = json.load(file)
            document = Document.objects.get(id=document_id)

            imported_count = 0
            for ann_data in data.get('annotations', []):
                # Créer l'annotation
                annotation = Annotation.objects.create(
                    sentence_id=ann_data['sentence_id'],
                    entity_type_id=ann_data['entity_type_id'],
                    text_value=ann_data['text_value'],
                    start_position=ann_data['start_position'],
                    end_position=ann_data['end_position'],
                    confidence_score=ann_data.get('confidence_score', 0.5),
                    source='import'
                )
                imported_count += 1

            return {'success': True, 'imported_count': imported_count}

        except Exception as e:
            return {'success': False, 'error': str(e)}
