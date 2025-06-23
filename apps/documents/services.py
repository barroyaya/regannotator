# ===== apps/documents/services.py =====
import PyPDF2
import re
from typing import List
from django.core.files.uploadedfile import UploadedFile
from apps.documents.models import Document, DocumentSentence


class DocumentProcessingService:
    """Service de traitement des documents PDF"""

    def extract_text_from_pdf(self, pdf_file: UploadedFile) -> str:
        """Extraire le texte d'un fichier PDF"""
        try:
            pdf_reader = PyPDF2.PdfReader(pdf_file)
            text_content = ""

            for page in pdf_reader.pages:
                text_content += page.extract_text() + "\n"

            return text_content
        except Exception as e:
            raise Exception(f"Erreur lors de l'extraction du PDF: {e}")

    def split_into_sentences(self, text: str) -> List[str]:
        """Découper le texte en phrases"""
        # Expressions régulières pour la segmentation
        sentence_endings = r'[.!?]+(?:\s+|$)'
        sentences = re.split(sentence_endings, text)

        # Nettoyer et filtrer les phrases
        cleaned_sentences = []
        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) > 10:  # Filtrer les phrases trop courtes
                cleaned_sentences.append(sentence)

        return cleaned_sentences

    def process_document(self, document: Document) -> None:
        """Traiter un document complet"""
        try:
            document.status = 'processing'
            document.save()

            # Extraire le texte
            text_content = self.extract_text_from_pdf(document.file)
            document.text_content = text_content

            # Métadonnées du fichier
            document.file_size = document.file.size

            # Découper en phrases
            sentences = self.split_into_sentences(text_content)

            # Créer les objets DocumentSentence
            for i, sentence_text in enumerate(sentences, 1):
                DocumentSentence.objects.create(
                    document=document,
                    sentence_number=i,
                    text=sentence_text
                )

            document.status = 'annotated'
            document.save()

        except Exception as e:
            document.status = 'error'
            document.save()
            raise e

