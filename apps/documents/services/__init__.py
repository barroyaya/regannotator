# ===== apps/documents/services/__init__.py =====
import logging
import re
from typing import List, Dict
from django.utils import timezone

from ..models import Document, DocumentSentence
from .metadata_extraction import MetadataExtractionService

logger = logging.getLogger(__name__)


class DocumentProcessingService:
    """Service de traitement complet des documents"""

    def __init__(self):
        self.metadata_extractor = MetadataExtractionService()

    def process_document(self, document: Document) -> Dict:
        """
        Traitement complet d'un document:
        1. Extraction des métadonnées
        2. Extraction et segmentation du texte
        3. Création des phrases
        """
        logger.info(f"Début du traitement du document: {document.title}")

        try:
            # Marquer le document comme en cours de traitement
            document.status = 'processing'
            document.save()

            # 1. Extraction des métadonnées
            extraction_log = self.metadata_extractor.extract_metadata(document)
            logger.info(f"Métadonnées extraites pour {document.title}")

            # 2. Segmentation en phrases
            if document.text_content:
                sentences = self._segment_into_sentences(document.text_content)
                self._create_sentence_objects(document, sentences)
                logger.info(f"{len(sentences)} phrases créées pour {document.title}")

            # 3. Mise à jour du statut
            document.status = 'annotated' if document.sentences.count() > 0 else 'error'
            document.save()

            processing_summary = {
                'success': True,
                'extraction_log': extraction_log,
                'sentences_count': document.sentences.count(),
                'metadata_extracted': document.extraction_summary,
                'processing_time': extraction_log.processing_time,
            }

            logger.info(f"Traitement terminé avec succès pour {document.title}")
            return processing_summary

        except Exception as e:
            logger.error(f"Erreur lors du traitement de {document.title}: {e}")
            document.status = 'error'
            document.save()

            return {
                'success': False,
                'error': str(e),
                'sentences_count': 0,
            }

    def _segment_into_sentences(self, text: str) -> List[str]:
        """
        Segmenter le texte en phrases intelligemment
        """
        # Nettoyer le texte
        text = self._clean_text(text)

        # Patterns pour la segmentation
        # On évite de couper sur les abréviations courantes
        sentence_endings = r'(?<!\w\.\w.)(?<![A-Z][a-z]\.)(?<=\.|\!|\?)\s+'

        # Segmentation initiale
        sentences = re.split(sentence_endings, text)

        # Nettoyer et filtrer les phrases
        cleaned_sentences = []
        for sentence in sentences:
            sentence = sentence.strip()

            # Filtrer les phrases trop courtes ou vides
            if len(sentence) > 10 and sentence:
                # Nettoyer la phrase
                sentence = re.sub(r'\s+', ' ', sentence)  # Normaliser les espaces
                sentence = sentence.strip()

                if sentence:
                    cleaned_sentences.append(sentence)

        return cleaned_sentences

    def _clean_text(self, text: str) -> str:
        """Nettoyer le texte extrait"""
        # Supprimer les caractères de contrôle
        text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', text)

        # Normaliser les espaces et sauts de ligne
        text = re.sub(r'\n\s*\n', '\n\n', text)  # Normaliser les paragraphes
        text = re.sub(r'[ \t]+', ' ', text)  # Normaliser les espaces

        # Supprimer les numéros de page isolés
        text = re.sub(r'\n\s*\d+\s*\n', '\n', text)

        # Supprimer les headers/footers répétitifs
        lines = text.split('\n')
        if len(lines) > 10:
            # Identifier les lignes qui se répètent (headers/footers)
            line_counts = {}
            for line in lines:
                line_clean = line.strip()
                if len(line_clean) > 5:  # Ignorer les lignes très courtes
                    line_counts[line_clean] = line_counts.get(line_clean, 0) + 1

            # Supprimer les lignes qui apparaissent plus de 3 fois
            filtered_lines = []
            for line in lines:
                line_clean = line.strip()
                if line_counts.get(line_clean, 0) <= 3:
                    filtered_lines.append(line)

            text = '\n'.join(filtered_lines)

        return text.strip()

    def _create_sentence_objects(self, document: Document, sentences: List[str]):
        """Créer les objets DocumentSentence"""
        # Supprimer les anciennes phrases si elles existent
        document.sentences.all().delete()

        sentence_objects = []
        current_position = 0

        for i, sentence_text in enumerate(sentences, 1):
            # Calculer la position dans le texte
            start_pos = document.text_content.find(sentence_text, current_position)
            end_pos = start_pos + len(sentence_text) if start_pos != -1 else current_position + len(sentence_text)

            # Estimer le numéro de page (approximatif)
            page_number = self._estimate_page_number(start_pos, len(document.text_content))

            # Classifier le type de phrase
            sentence_type = self._classify_sentence_type(sentence_text)

            sentence_obj = DocumentSentence(
                document=document,
                sentence_number=i,
                text=sentence_text,
                page_number=page_number,
                start_position=start_pos if start_pos != -1 else current_position,
                end_position=end_pos,
                sentence_type=sentence_type['type'],
                confidence_score=sentence_type['confidence']
            )

            sentence_objects.append(sentence_obj)
            current_position = end_pos

        # Créer toutes les phrases en une fois
        DocumentSentence.objects.bulk_create(sentence_objects)

    def _estimate_page_number(self, position: int, total_length: int) -> int:
        """Estimer le numéro de page basé sur la position dans le texte"""
        # Estimation approximative: ~2000 caractères par page
        chars_per_page = 2000
        return max(1, (position // chars_per_page) + 1)

    def _classify_sentence_type(self, sentence: str) -> Dict:
        """Classifier le type de phrase"""
        sentence_lower = sentence.lower()

        # Patterns pour différents types de phrases
        patterns = {
            'definition': {
                'patterns': [r'means?', r'defined? as', r'refers? to', r'signifie', r'désigne'],
                'confidence': 0.8
            },
            'requirement': {
                'patterns': [r'shall', r'must', r'required', r'mandatory', r'doit', r'obligatoire'],
                'confidence': 0.7
            },
            'procedure': {
                'patterns': [r'procedure', r'process', r'step', r'procédure', r'étape'],
                'confidence': 0.6
            },
            'reference': {
                'patterns': [r'article', r'section', r'annex', r'appendix', r'annexe'],
                'confidence': 0.7
            },
            'timeline': {
                'patterns': [r'within', r'days?', r'months?', r'years?', r'dans les', r'jours?', r'mois'],
                'confidence': 0.8
            }
        }

        for sentence_type, config in patterns.items():
            for pattern in config['patterns']:
                if re.search(pattern, sentence_lower):
                    return {
                        'type': sentence_type,
                        'confidence': config['confidence']
                    }

        return {
            'type': 'general',
            'confidence': 0.5
        }


class DocumentAnalyticsService:
    """Service d'analyse et de statistiques des documents"""

    @staticmethod
    def get_document_statistics(document: Document) -> Dict:
        """Obtenir les statistiques détaillées d'un document"""
        from apps.annotations.models import Annotation

        sentences = document.sentences.all()
        annotations = Annotation.objects.filter(sentence__document=document)

        # Statistiques de base
        stats = {
            'basic': {
                'total_sentences': sentences.count(),
                'total_annotations': annotations.count(),
                'total_characters': len(document.text_content) if document.text_content else 0,
                'estimated_pages': document.page_count or 0,
                'file_size_mb': document.file_size_mb or 0,
            },

            # Statistiques par type de phrase
            'sentence_types': {},

            # Statistiques par entité
            'entity_distribution': {},

            # Extraction des métadonnées
            'extraction_quality': document.extraction_summary,

            # Validation
            'validation_status': {
                'validated': annotations.filter(validation_status='validated').count(),
                'pending': annotations.filter(validation_status='pending').count(),
                'rejected': annotations.filter(validation_status='rejected').count(),
            }
        }

        # Analyser les types de phrases
        for sentence in sentences:
            sentence_type = sentence.sentence_type or 'general'
            stats['sentence_types'][sentence_type] = stats['sentence_types'].get(sentence_type, 0) + 1

        # Analyser la distribution des entités
        for annotation in annotations:
            entity_name = annotation.entity_type.name
            if entity_name not in stats['entity_distribution']:
                stats['entity_distribution'][entity_name] = {
                    'count': 0,
                    'validated': 0,
                    'avg_confidence': 0,
                    'confidences': []
                }

            stats['entity_distribution'][entity_name]['count'] += 1
            stats['entity_distribution'][entity_name]['confidences'].append(annotation.confidence_score)

            if annotation.validation_status == 'validated':
                stats['entity_distribution'][entity_name]['validated'] += 1

        # Calculer les moyennes de confiance
        for entity_data in stats['entity_distribution'].values():
            if entity_data['confidences']:
                entity_data['avg_confidence'] = sum(entity_data['confidences']) / len(entity_data['confidences'])
            del entity_data['confidences']  # Supprimer la liste temporaire

        return stats