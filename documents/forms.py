# # documents/forms.py
# from django import forms
# from .models import Document, DocumentType, DocumentContext
#
#
# class DocumentUploadForm(forms.ModelForm):
#     """Formulaire d'upload de document"""
#
#     class Meta:
#         model = Document
#         fields = ['title', 'file', 'document_type', 'context']
#
#     def __init__(self, *args, **kwargs):
#         super().__init__(*args, **kwargs)
#
#         self.fields['title'].widget.attrs.update({
#             'class': 'form-control',
#             'placeholder': 'Titre du document'
#         })
#         self.fields['file'].widget.attrs.update({
#             'class': 'form-control',
#             'accept': '.pdf,.docx,.doc,.png,.jpg,.jpeg'
#         })
#         self.fields['document_type'].widget.attrs.update({
#             'class': 'form-select'
#         })
#         self.fields['context'].widget.attrs.update({
#             'class': 'form-select'
#         })
#
#     def save(self, commit=True):
#         document = super().save(commit=False)
#
#         # Déterminer le type de fichier
#         if document.file:
#             file_extension = document.file.name.split('.')[-1].lower()
#             document.file_type = file_extension
#
#         if commit:
#             document.save()
#
#         return document


# documents/forms.py - Formulaire d'upload avec URLs
from django import forms
from .models import Document, DocumentType, DocumentContext


class DocumentUploadForm(forms.ModelForm):
    """Formulaire d'upload de document avec support des URLs"""

    # Choix du mode d'ajout
    upload_mode = forms.ChoiceField(
        choices=[
            ('file', 'Upload d\'un fichier local'),
            ('url', 'URLs du document (PDF + page EMA)')
        ],
        widget=forms.RadioSelect,
        initial='file',
        label="Mode d'ajout"
    )

    class Meta:
        model = Document
        fields = ['title', 'upload_mode', 'file', 'direct_pdf_url', 'ema_page_url', 'document_type', 'context']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Styles des champs
        self.fields['title'].widget.attrs.update({
            'class': 'form-control',
            'placeholder': 'Titre du document'
        })

        self.fields['file'].widget.attrs.update({
            'class': 'form-control',
            'accept': '.pdf,.docx,.doc,.png,.jpg,.jpeg'
        })

        self.fields['direct_pdf_url'].widget.attrs.update({
            'class': 'form-control',
            'placeholder': 'https://www.ema.europa.eu/documents/scientific-guideline/example.pdf'
        })

        self.fields['ema_page_url'].widget.attrs.update({
            'class': 'form-control',
            'placeholder': 'https://www.ema.europa.eu/en/example-guideline-page'
        })

        self.fields['document_type'].widget.attrs.update({
            'class': 'form-select'
        })

        self.fields['context'].widget.attrs.update({
            'class': 'form-select'
        })

        # Labels et help text
        self.fields['direct_pdf_url'].label = "URL directe du PDF"
        self.fields[
            'direct_pdf_url'].help_text = "URL directe vers le fichier PDF (pour extraire le contenu et le titre)"

        self.fields['ema_page_url'].label = "URL de la page EMA"
        self.fields['ema_page_url'].help_text = "URL de la page web EMA contenant les métadonnées du document"

    def clean(self):
        cleaned_data = super().clean()
        upload_mode = cleaned_data.get('upload_mode')
        file = cleaned_data.get('file')
        direct_pdf_url = cleaned_data.get('direct_pdf_url')
        ema_page_url = cleaned_data.get('ema_page_url')

        if upload_mode == 'file':
            # Mode fichier : le fichier est obligatoire
            if not file:
                raise forms.ValidationError('Un fichier est requis en mode upload local.')
            # Nettoyer les URLs si elles ne sont pas utilisées
            cleaned_data['direct_pdf_url'] = ''
            cleaned_data['ema_page_url'] = ''

        elif upload_mode == 'url':
            # Mode URL : les deux URLs sont obligatoires
            if not direct_pdf_url:
                raise forms.ValidationError('L\'URL directe du PDF est requise en mode URL.')
            if not ema_page_url:
                raise forms.ValidationError('L\'URL de la page EMA est requise en mode URL.')

            # Validation basique des URLs
            if not direct_pdf_url.lower().endswith('.pdf'):
                raise forms.ValidationError('L\'URL directe doit pointer vers un fichier PDF (.pdf).')

            if 'ema.europa.eu' not in ema_page_url.lower():
                raise forms.ValidationError('L\'URL de la page doit être du site EMA (ema.europa.eu).')

            # Nettoyer le fichier si il n'est pas utilisé
            cleaned_data['file'] = None

        return cleaned_data

    def save(self, commit=True):
        document = super().save(commit=False)

        # Déterminer le type de fichier
        if document.file:
            file_extension = document.file.name.split('.')[-1].lower()
            document.file_type = file_extension
        elif document.direct_pdf_url:
            document.file_type = 'pdf'  # Les URLs directes sont toujours des PDF

        if commit:
            document.save()

        return document


class DocumentMetadataForm(forms.ModelForm):
    """Formulaire pour éditer les métadonnées extraites"""

    class Meta:
        model = Document
        fields = [
            'extracted_title', 'language', 'source', 'version', 'source_url',
            'publication_date', 'original_publication_date', 'ema_publication_date',
            'ema_title', 'ema_reference', 'ema_source_url'
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Ajouter des classes CSS
        for field in self.fields:
            if isinstance(self.fields[field].widget, forms.DateInput):
                self.fields[field].widget.attrs.update({
                    'class': 'form-control',
                    'type': 'date'
                })
            else:
                self.fields[field].widget.attrs.update({
                    'class': 'form-control'
                })


class DocumentSearchForm(forms.Form):
    """Formulaire de recherche de documents"""

    search = forms.CharField(
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Rechercher par titre, source, référence...'
        })
    )

    status = forms.ChoiceField(
        choices=[('all', 'Tous les statuts')] + Document.STATUS_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    document_type = forms.ModelChoiceField(
        queryset=DocumentType.objects.all(),
        required=False,
        empty_label="Tous les types",
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    context = forms.ModelChoiceField(
        queryset=DocumentContext.objects.all(),
        required=False,
        empty_label="Tous les contextes",
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    has_ema_data = forms.ChoiceField(
        choices=[
            ('all', 'Tous'),
            ('yes', 'Avec données EMA'),
            ('no', 'Sans données EMA')
        ],
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
        label="Données EMA"
    )