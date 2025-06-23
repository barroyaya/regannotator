# apps/core/management/commands/init_entities.py
from django.core.management.base import BaseCommand
from apps.core.models import RegulatoryEntity


class Command(BaseCommand):
    help = 'Initialise les entités réglementaires'

    def handle(self, *args, **options):
        entities = [
            ('VARIATION_CODE', 'Code de variation réglementaire', '#007bff'),
            ('PROCEDURE_TYPE', 'Type de procédure', '#28a745'),
            ('AUTHORITY', 'Autorité réglementaire', '#ffc107'),
            ('LEGAL_REFERENCE', 'Référence légale', '#dc3545'),
            ('DOCUMENT_REQUIRED', 'Document requis', '#6f42c1'),
            ('CONDITION_REQUIRED', 'Condition requise', '#fd7e14'),
            ('TIMELINE', 'Délai/Calendrier', '#20c997'),
            ('DOSSIER_TYPE', 'Type de dossier', '#e83e8c'),
            ('COUNTRY', 'Pays', '#6c757d'),
        ]

        for name, description, color in entities:
            entity, created = RegulatoryEntity.objects.get_or_create(
                name=name,
                defaults={'description': description, 'color': color}
            )
            if created:
                self.stdout.write(f'Entité créée: {name}')
            else:
                self.stdout.write(f'Entité existe: {name}')