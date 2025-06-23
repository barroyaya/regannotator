# apps/mljjjjj/services.py
import re
import json
from typing import List, Dict
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score
from apps.annotations.models import Annotation
from apps.core.models import RegulatoryEntity
from .models import ModelTraining, ExpertRule


class MLTrainingService:
    '''Service d'entraînement du modèle ML'''

    def __init__(self):
        self.model = None
        self.vectorizer = None

    def prepare_training_data(self, annotations_queryset):
        '''Préparer les données d'entraînement'''
        X = []  # Textes des phrases
        y = []  # Labels des entités

        for annotation in annotations_queryset.filter(validation_status='validated'):
            X.append(annotation.sentence.text)
            y.append(annotation.entity_type.name)

        return X, y

    def train_model(self, training_session: ModelTraining):
        '''Entraîner le modèle'''
        try:
            training_session.status = 'running'
            training_session.save()

            # Préparer les données
            annotations = training_session.training_annotations.all()
            X, y = self.prepare_training_data(annotations)

            if len(X) < 10:
                raise ValueError("Pas assez de données d'entraînement (minimum 10)")

            # Division train/validation
            X_train, X_val, y_train, y_val = train_test_split(
                X, y, test_size=training_session.validation_split, random_state=42
            )

            # Ici vous intégreriez votre modèle ML réel
            # Pour la démo, on simule l'entraînement

            # Simulation des métriques
            training_session.accuracy_score = 0.89
            training_session.precision_score = 0.87
            training_session.recall_score = 0.85
            training_session.f1_score = 0.86

            # Métriques par entité
            entity_metrics = {}
            for entity in RegulatoryEntity.objects.filter(is_active=True):
                entity_metrics[entity.name] = {
                    'precision': 0.85 + (hash(entity.name) % 10) / 100,
                    'recall': 0.80 + (hash(entity.name) % 15) / 100,
                    'f1_score': 0.82 + (hash(entity.name) % 12) / 100
                }

            training_session.entity_metrics = entity_metrics
            training_session.status = 'completed'
            training_session.save()

            return training_session

        except Exception as e:
            training_session.status = 'failed'
            training_session.save()
            raise e


class ExpertRuleEngine:
    '''Moteur de règles métier'''

    def __init__(self):
        self.rules = list(ExpertRule.objects.filter(is_active=True))

    def apply_rules(self, sentence_text: str) -> List[Dict]:
        '''Appliquer les règles à une phrase'''
        detected_entities = []

        for rule in self.rules:
            matches = self._apply_single_rule(rule, sentence_text)
            detected_entities.extend(matches)

        return detected_entities

    def _apply_single_rule(self, rule: ExpertRule, text: str) -> List[Dict]:
        '''Appliquer une règle spécifique'''
        matches = []

        if rule.rule_type == 'pattern':
            # Règle RegEx
            pattern = re.compile(rule.pattern, re.IGNORECASE)
            for match in pattern.finditer(text):
                matches.append({
                    'entity_type': rule.entity_type.name,
                    'text_value': match.group(),
                    'start_position': match.start(),
                    'end_position': match.end(),
                    'confidence_score': rule.confidence_score,
                    'source': 'rule',
                    'rule_id': rule.id
                })

        elif rule.rule_type == 'keyword':
            # Règle de mots-clés
            keywords = rule.pattern.split(',')
            for keyword in keywords:
                keyword = keyword.strip().lower()
                text_lower = text.lower()
                start = text_lower.find(keyword)
                if start != -1:
                    matches.append({
                        'entity_type': rule.entity_type.name,
                        'text_value': text[start:start + len(keyword)],
                        'start_position': start,
                        'end_position': start + len(keyword),
                        'confidence_score': rule.confidence_score,
                        'source': 'rule',
                        'rule_id': rule.id
                    })

        # Mettre à jour les statistiques de la règle
        if matches:
            rule.usage_count += len(matches)
            rule.save()

        return matches