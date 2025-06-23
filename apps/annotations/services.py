# ===== apps/annotations/services.py =====
import json
import requests
from typing import List, Dict
from django.conf import settings
from apps.documents.models import DocumentSentence
from apps.annotations.models import Annotation, AnnotationSession
from apps.core.models import RegulatoryEntity


class LLMAnnotationService:
    """Service d'annotation automatique avec LLM"""

    def __init__(self):
        self.model_name = settings.LLM_CONFIG['MODEL_NAME']
        self.api_key = settings.LLM_CONFIG['API_KEY']
        self.entities = list(RegulatoryEntity.objects.filter(is_active=True))

    def create_annotation_prompt(self, sentence_text: str) -> str:
        """Créer le prompt pour l'annotation LLM"""
        entities_list = [entity.name for entity in self.entities]

        prompt = f"""
        Tu es un expert en réglementation pharmaceutique. Analyse la phrase suivante et extrait toutes les entités réglementaires pertinentes.

        Phrase à analyser: "{sentence_text}"

        Entités à rechercher: {', '.join(entities_list)}

        Pour chaque entité trouvée, retourne un JSON avec:
        - entity_type: le type d'entité
        - text_value: le texte exact de l'entité
        - start_position: position de début dans la phrase
        - end_position: position de fin dans la phrase
        - confidence_score: score de confiance (0.0 à 1.0)

        Format de réponse JSON:
        {{
            "annotations": [
                {{
                    "entity_type": "VARIATION_CODE",
                    "text_value": "Type IB",
                    "start_position": 25,
                    "end_position": 32,
                    "confidence_score": 0.95
                }}
            ]
        }}

        Si aucune entité n'est trouvée, retourne: {{"annotations": []}}
        """
        return prompt

    def annotate_sentence(self, sentence: DocumentSentence) -> List[Dict]:
        """Annoter une phrase avec le LLM"""
        prompt = self.create_annotation_prompt(sentence.text)

        # Simulation d'appel API Mistral (remplacer par vraie API)
        try:
            # Ici vous intégreriez l'API Mistral réelle
            response = self._call_mistral_api(prompt)
            annotations_data = json.loads(response)

            # Créer les annotations en base
            annotations = []
            for ann_data in annotations_data.get('annotations', []):
                entity_type = RegulatoryEntity.objects.get(name=ann_data['entity_type'])

                annotation = Annotation.objects.create(
                    sentence=sentence,
                    entity_type=entity_type,
                    text_value=ann_data['text_value'],
                    start_position=ann_data['start_position'],
                    end_position=ann_data['end_position'],
                    confidence_score=ann_data['confidence_score'],
                    source='llm'
                )
                annotations.append(annotation)

            sentence.is_processed = True
            sentence.save()

            return annotations

        except Exception as e:
            print(f"Erreur lors de l'annotation: {e}")
            return []

    def _call_mistral_api(self, prompt: str) -> str:
        """Appel à l'API Mistral (à implémenter)"""
        # Simulation pour la démo
        return '''
        {
            "annotations": [
                {
                    "entity_type": "PROCEDURE_TYPE",
                    "text_value": "Type IB",
                    "start_position": 15,
                    "end_position": 22,
                    "confidence_score": 0.92
                },
                {
                    "entity_type": "AUTHORITY",
                    "text_value": "EMA",
                    "start_position": 45,
                    "end_position": 48,
                    "confidence_score": 0.98
                }
            ]
        }
        '''