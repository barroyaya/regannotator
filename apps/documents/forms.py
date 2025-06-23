# # ===== apps/documents/forms.py =====
# from django import forms
# from .models import Document, DocumentSource
#
#
# class DocumentUploadForm(forms.ModelForm):
#     """Formulaire d'upload de document"""
#
#     class Meta:
#         model = Document
#         fields = ['title', 'file', 'document_type', 'language', 'version', 'url_source']  # ✅ source supprimé
#         widgets = {
#             'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Titre du document'}),
#             'document_type': forms.Select(attrs={'class': 'form-select'}),
#             'language': forms.Select(attrs={'class': 'form-select'}),
#             'version': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'ex: 1.0, Rev 2'}),
#             'url_source': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://...'}),
#             'file': forms.FileInput(attrs={'class': 'form-control', 'accept': '.pdf'}),
#         }
#
#     def __init__(self, *args, **kwargs):
#         super().__init__(*args, **kwargs)
#         self.fields['title'].required = True
#         self.fields['file'].required = True

# ===== apps/documents/forms.py (MIS À JOUR) =====
from django import forms
from django.core.exceptions import ValidationError
from django.forms import ClearableFileInput

from .models import Document, DocumentSource


class DocumentUploadForm(forms.ModelForm):
    """Formulaire d'upload de document avec extraction automatique"""

    # Champ pour URL optionnelle (alternative au fichier)
    url_document = forms.URLField(
        required=False,
        widget=forms.URLInput(attrs={
            'class': 'form-control',
            'placeholder': 'https://exemple.com/document.pdf'
        }),
        help_text="Vous pouvez fournir une URL au lieu d'un fichier"
    )

    # Option pour forcer l'extraction manuelle
    force_manual_metadata = forms.BooleanField(
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        help_text="Cocher pour désactiver l'extraction automatique des métadonnées"
    )

    class Meta:
        model = Document
        fields = [
            'title', 'file', 'url_document', 'document_type',
            'language', 'version', 'url_source', 'force_manual_metadata'
        ]
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Laissez vide pour extraction automatique'
            }),
            'document_type': forms.Select(attrs={'class': 'form-select'}),
            'language': forms.Select(attrs={'class': 'form-select'}),
            'version': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'ex: 1.0, Rev 2 (optionnel)'
            }),
            'url_source': forms.URLInput(attrs={
                'class': 'form-control',
                'placeholder': 'URL source officielle (optionnel)'
            }),
            'file': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': '.pdf,.doc,.docx,.txt,.html,.htm,.rtf,.odt'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Rendre le titre et le fichier optionnels pour l'extraction automatique
        self.fields['title'].required = False
        self.fields['file'].required = False
        self.fields['document_type'].required = False

        # Mettre à jour les help texts
        self.fields['title'].help_text = "Sera extrait automatiquement si laissé vide"
        self.fields['document_type'].help_text = "Sera détecté automatiquement si pas spécifié"
        self.fields['language'].help_text = "Sera détecté automatiquement si 'Détection automatique' est sélectionné"

        # Ajouter des options de contexte
        self.fields['context'] = forms.ChoiceField(
            choices=[
                ('pharma', 'Pharmaceutique'),
                ('juridique', 'Juridique'),
                ('gouvernement', 'Gouvernement'),
                ('medical', 'Médical'),
                ('research', 'Recherche'),
                ('autre', 'Autre'),
            ],
            initial='pharma',
            widget=forms.Select(attrs={'class': 'form-select'}),
            help_text="Contexte du document pour améliorer l'extraction"
        )

    def clean(self):
        cleaned_data = super().clean()
        file = cleaned_data.get('file')
        url_document = cleaned_data.get('url_document')

        # Vérifier qu'au moins un fichier ou une URL est fourni
        if not file and not url_document:
            raise ValidationError(
                "Vous devez fournir soit un fichier, soit une URL de document."
            )

        # Si les deux sont fournis, prioriser le fichier
        if file and url_document:
            cleaned_data['url_document'] = ''  # Ignorer l'URL si fichier fourni

        return cleaned_data

    def clean_file(self):
        file = self.cleaned_data.get('file')

        if file:
            # Vérifier la taille du fichier (100 MB max)
            if file.size > 100 * 1024 * 1024:
                raise ValidationError(
                    "Le fichier est trop volumineux. Taille maximale: 100 MB."
                )

            # Vérifier l'extension du fichier
            allowed_extensions = [
                '.pdf', '.doc', '.docx', '.txt', '.html', '.htm',
                '.rtf', '.odt', '.zip', '.rar'
            ]

            file_extension = file.name.lower().split('.')[-1] if '.' in file.name else ''

            if file_extension and f'.{file_extension}' not in allowed_extensions:
                raise ValidationError(
                    f"Type de fichier non supporté. Extensions autorisées: "
                    f"{', '.join(allowed_extensions)}"
                )

        return file


class DocumentMetadataForm(forms.ModelForm):
    """Formulaire pour éditer manuellement les métadonnées extraites"""

    class Meta:
        model = Document
        fields = [
            'title', 'document_type', 'language', 'version',
            'publication_date', 'source', 'url_source'
        ]
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'document_type': forms.Select(attrs={'class': 'form-select'}),
            'language': forms.Select(attrs={'class': 'form-select'}),
            'version': forms.TextInput(attrs={'class': 'form-control'}),
            'publication_date': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date'
            }),
            'source': forms.Select(attrs={'class': 'form-select'}),
            'url_source': forms.URLInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Ajouter les sources disponibles
        self.fields['source'].queryset = DocumentSource.objects.all()
        self.fields['source'].empty_label = "Sélectionner une source"

        # Si c'est une mise à jour, montrer les valeurs extraites automatiquement
        if self.instance and self.instance.pk:
            instance = self.instance

            # Ajouter des help texts avec les valeurs extraites
            if instance.auto_extracted_title:
                self.fields['title'].help_text = f"Extrait automatiquement: {instance.auto_extracted_title}"

            if instance.auto_extracted_date:
                self.fields['publication_date'].help_text = f"Extrait automatiquement: {instance.auto_extracted_date}"

            if instance.auto_extracted_language:
                self.fields['language'].help_text = f"Détecté automatiquement: {instance.auto_extracted_language}"

            if instance.auto_extracted_source:
                self.fields['source'].help_text = f"Extrait automatiquement: {instance.auto_extracted_source}"

    def save(self, commit=True):
        instance = super().save(commit=False)

        # Marquer les champs comme modifiés manuellement
        if 'title' in self.changed_data:
            instance.title_manually_edited = True

        if 'publication_date' in self.changed_data:
            instance.date_manually_edited = True

        if 'language' in self.changed_data:
            instance.language_manually_edited = True

        if 'source' in self.changed_data:
            instance.source_manually_edited = True

        if commit:
            instance.save()

        return instance


class BulkDocumentUploadForm(forms.Form):
    """Formulaire pour upload en lot de documents"""

    files = forms.FileField(
        widget=forms.ClearableFileInput(attrs={
            'class': 'form-control',
            'accept': '.pdf,.doc,.docx,.txt,.html,.htm,.rtf,.odt,.zip'
        }),
        help_text="Sélectionnez plusieurs fichiers",
    )

    default_context = forms.ChoiceField(
        choices=[
            ('pharma', 'Pharmaceutique'),
            ('juridique', 'Juridique'),
            ('gouvernement', 'Gouvernement'),
            ('medical', 'Médical'),
            ('research', 'Recherche'),
            ('autre', 'Autre'),
        ],
        initial='pharma',
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text="Contexte par défaut pour tous les documents"
    )

    auto_process = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        help_text="Traiter automatiquement tous les documents après upload"
    )

    def __init__(self, *args, **kwargs):
        self.files_data = kwargs.pop('files', None)
        super().__init__(*args, **kwargs)

    def is_valid(self):
        # Validation de base du formulaire
        if not super().is_valid():
            return False

        # Validation personnalisée des fichiers (sera faite dans la vue)
        return True