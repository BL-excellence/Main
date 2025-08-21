# Chemin d'intégration : ctd_submission/forms.py
# Ce fichier contient tous les formulaires Django pour l'application CTD submission

from django import forms
from django.core.validators import FileExtensionValidator
from .models import Submission, Document, TemplateField


class SubmissionForm(forms.ModelForm):
    """
    Formulaire pour créer/modifier une soumission CTD
    """

    class Meta:
        model = Submission
        fields = ['name', 'region', 'submission_type', 'variation_type', 'change_description']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'ex: EU-MAA-Product-001'
            }),
            'region': forms.Select(attrs={
                'class': 'form-control'
            }),
            'submission_type': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'ex: MAA - Marketing Authorisation Application'
            }),
            'variation_type': forms.Select(attrs={
                'class': 'form-control'
            }, choices=[
                ('', 'Sélectionner le type de variation'),
                ('Type IA', 'Variation Type IA'),
                ('Type IB', 'Variation Type IB'),
                ('Type II', 'Variation Type II'),
            ]),
            'change_description': forms.Select(attrs={
                'class': 'form-control'
            }, choices=[
                ('', 'Sélectionner le changement'),
                ('ajout_site_fabrication', 'Ajout de site de fabrication primaire'),
                ('modification_procede', 'Modification du procédé de fabrication'),
                ('changement_specification', 'Changement de spécification'),
                ('nouveau_dosage', 'Nouveau dosage'),
            ])
        }
        labels = {
            'name': 'Nom de la soumission',
            'region': 'Pays/Région',
            'submission_type': 'Type de soumission',
            'variation_type': 'Type de variation',
            'change_description': 'Description du changement'
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Rendre certains champs obligatoires
        self.fields['name'].required = True
        self.fields['region'].required = True
        self.fields['submission_type'].required = True


class DocumentUploadForm(forms.ModelForm):
    """
    Formulaire pour uploader des documents
    """

    class Meta:
        model = Document
        fields = ['name', 'file']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Nom du document'
            }),
            'file': forms.ClearableFileInput(attrs={
                'class': 'form-control-file',
                'accept': '.pdf,.docx,.doc,.xlsx,.xls'
            })
        }
        labels = {
            'name': 'Nom du document',
            'file': 'Fichier'
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Validation des types de fichiers
        self.fields['file'].validators = [
            FileExtensionValidator(
                allowed_extensions=['pdf', 'docx', 'doc', 'xlsx', 'xls'],
                message='Seuls les fichiers PDF, Word et Excel sont autorisés.'
            )
        ]
        self.fields['file'].help_text = 'Formats acceptés: PDF, Word (.docx, .doc), Excel (.xlsx, .xls)'


class TemplateForm(forms.Form):
    """
    Formulaire dynamique généré à partir des TemplateField
    """

    def __init__(self, document, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Récupérer tous les champs du template pour ce document
        template_fields = TemplateField.objects.filter(document=document).order_by('row_number', 'column_number')

        for field in template_fields:
            field_name = f'field_{field.id}'

            # Configuration commune
            field_kwargs = {
                'label': field.field_label,
                'required': field.is_required,
                'initial': field.field_value,
            }

            # Créer le champ selon son type
            if field.field_type == 'text':
                django_field = forms.CharField(
                    widget=forms.TextInput(attrs={'class': 'form-control'}),
                    **field_kwargs
                )

            elif field.field_type == 'textarea':
                django_field = forms.CharField(
                    widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
                    **field_kwargs
                )

            elif field.field_type == 'select':
                choices = [('', 'Sélectionnez...')] + [(opt, opt) for opt in field.field_options]
                django_field = forms.ChoiceField(
                    choices=choices,
                    widget=forms.Select(attrs={'class': 'form-control'}),
                    **field_kwargs
                )

            elif field.field_type == 'checkbox':
                django_field = forms.BooleanField(
                    widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
                    required=False,  # Les checkboxes ne sont jamais obligatoires par défaut
                    initial=field.field_value.lower() in ['true', '1', 'yes'] if field.field_value else False
                )

            elif field.field_type == 'number':
                django_field = forms.IntegerField(
                    widget=forms.NumberInput(attrs={'class': 'form-control'}),
                    **field_kwargs
                )

            elif field.field_type == 'date':
                django_field = forms.DateField(
                    widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
                    **field_kwargs
                )

            else:
                # Par défaut, créer un champ texte
                django_field = forms.CharField(
                    widget=forms.TextInput(attrs={'class': 'form-control'}),
                    **field_kwargs
                )

            # Ajouter le champ au formulaire
            self.fields[field_name] = django_field


class EMATemplateForm(forms.Form):
    """
    Formulaire spécialisé pour les documents EMA Cover Letter
    Basé sur les captures d'écran fournies
    """
    # Ligne 1
    applicant_name = forms.CharField(
        label='Applicant/MAH Name',
        max_length=200,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter applicant/MAH name'
        })
    )

    # Ligne 2
    customer_account = forms.CharField(
        label='Customer Account Number',
        max_length=50,
        required=True,
        help_text='000060xxxx (only one number for WS and IG)',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': '000060xxxx'
        })
    )

    # Ligne 3
    customer_reference = forms.CharField(
        label='Customer Reference / Purchase Order Number',
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter reference number'
        })
    )

    # Ligne 4
    inn_code = forms.CharField(
        label='INN / Active substance/ATC Code',
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter INN/Active substance/ATC Code'
        })
    )

    # Ligne 5
    product_name = forms.CharField(
        label='Product Name of centrally authorised medicinal product(s)',
        max_length=200,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter product name'
        })
    )

    # Ligne 5.1
    nationally_authorised = forms.BooleanField(
        label='Nationally Authorised Product(s)',
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )

    # Ligne 6
    product_number = forms.CharField(
        label='Product Number or Procedure Number',
        max_length=100,
        required=False,
        help_text='H XXXX or EMEA/H/C/XXXX / type / or PSUSA/000XXXXX/yyyymm',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'EMEA/H/C/XXXX / type /'
        })
    )

    national_marketing_auth = forms.CharField(
        label='National Marketing Authorisation No',
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control'
        })
    )

    # Ligne 6.1
    SUBMISSION_TYPE_CHOICES = [
        ('new', 'A submission of a new procedure'),
        ('response', 'A response/supplementary information to an on-going procedure'),
    ]

    submission_nature = forms.ChoiceField(
        label='Is this:',
        choices=SUBMISSION_TYPE_CHOICES,
        required=True,
        widget=forms.RadioSelect(attrs={'class': 'form-check-input'})
    )

    # Ligne 7
    unit_type = forms.CharField(
        label='Unit Type',
        max_length=50,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Please select'
        })
    )

    # Ligne 7.1
    MODE_CHOICES = [
        ('single', 'Single'),
        ('grouping', 'Grouping'),
    ]

    mode = forms.ChoiceField(
        label='Mode',
        choices=MODE_CHOICES,
        required=True,
        widget=forms.RadioSelect(attrs={'class': 'form-check-input'})
    )

    # Ligne 7.2
    procedure_type = forms.CharField(
        label='Procedure Type',
        max_length=100,
        initial='MAA - Marketing Authorisation Application',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'readonly': True
        })
    )

    # Ligne 7.3
    description_submission = forms.CharField(
        label='Description of submission',
        max_length=200,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Please select'
        })
    )

    # Ligne 8
    centrally_authorised_info = forms.CharField(
        label='Please provide the name(s) of any centrally authorised medicinal product for which the same change(s) are being applied for outside of this procedure',
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Product name and number:'
        }),
        required=False
    )

    # Ligne 9
    RMP_CHOICES = [
        ('yes', 'Yes'),
        ('no', 'No'),
    ]

    rmp_included = forms.ChoiceField(
        label='RMP included in this submission:',
        choices=RMP_CHOICES,
        required=True,
        widget=forms.RadioSelect(attrs={'class': 'form-check-input'})
    )

    rmp_version = forms.CharField(
        label='RMP version N.',
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )

    # Ligne 10
    ectd_sequence = forms.CharField(
        label='eCTD sequence',
        max_length=50,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )

    related_sequence = forms.CharField(
        label='Related sequence',
        max_length=50,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )


class TemplateFieldForm(forms.ModelForm):
    """
    Formulaire pour ajouter/modifier des champs de template
    """

    class Meta:
        model = TemplateField
        fields = ['field_name', 'field_label', 'field_type', 'field_value', 'field_options', 'is_required']
        widgets = {
            'field_name': forms.TextInput(attrs={'class': 'form-control'}),
            'field_label': forms.TextInput(attrs={'class': 'form-control'}),
            'field_type': forms.Select(attrs={'class': 'form-control'}),
            'field_value': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'field_options': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Une option par ligne'
            }),
            'is_required': forms.CheckboxInput(attrs={'class': 'form-check-input'})
        }
        labels = {
            'field_name': 'Nom du champ',
            'field_label': 'Libellé du champ',
            'field_type': 'Type de champ',
            'field_value': 'Valeur par défaut',
            'field_options': 'Options (pour select/checkbox)',
            'is_required': 'Champ obligatoire'
        }

    def clean_field_options(self):
        """
        Convertit les options en liste
        """
        options_text = self.cleaned_data.get('field_options', '')
        if options_text:
            return [option.strip() for option in options_text.split('\n') if option.strip()]
        return []