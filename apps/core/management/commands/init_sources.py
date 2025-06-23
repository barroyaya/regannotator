# apps/core/management/commands/init_sources.py
from django.core.management.base import BaseCommand
from apps.documents.models import DocumentSource


class Command(BaseCommand):
    help = 'Initialise les sources de documents'

    def handle(self, *args, **options):
        sources = [
            ('European Medicines Agency', 'EMA', 'Union Européenne', 'https://www.ema.europa.eu'),
            ('Food and Drug Administration', 'FDA', 'États-Unis', 'https://www.fda.gov'),
            ('Agence Nationale de Sécurité du Médicament', 'ANSM', 'France', 'https://www.ansm.sante.fr'),
            ('Health Canada', 'HC', 'Canada', 'https://www.canada.ca/en/health-canada'),
            ('Swissmedic', 'SMC', 'Suisse', 'https://www.swissmedic.ch'),
            ('Medicines and Healthcare products Regulatory Agency', 'MHRA', 'Royaume-Uni', 'https://www.gov.uk/mhra'),
        ]

        for name, acronym, country, website in sources:
            source, created = DocumentSource.objects.get_or_create(
                acronym=acronym,
                defaults={'name': name, 'country': country, 'website': website}
            )
            if created:
                self.stdout.write(f'Source créée: {acronym}')
            else:
                self.stdout.write(f'Source existe: {acronym}')