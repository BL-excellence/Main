# annotation/forms.py
from django import forms
from .models import Annotation, EntityType


class AnnotationForm(forms.ModelForm):
    """Formulaire pour les annotations"""

    class Meta:
        model = Annotation
        fields = ['text', 'entity_type', 'start_position', 'end_position']
        widgets = {
            'text': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Texte de l\'entité'
            }),
            'entity_type': forms.Select(attrs={
                'class': 'form-select'
            }),
            'start_position': forms.NumberInput(attrs={
                'class': 'form-control'
            }),
            'end_position': forms.NumberInput(attrs={
                'class': 'form-control'
            })
        }


class EntityTypeForm(forms.ModelForm):
    """Formulaire pour les types d'entités"""

    class Meta:
        model = EntityType
        fields = ['name', 'color', 'description']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Nom du type d\'entité'
            }),
            'color': forms.TextInput(attrs={
                'class': 'form-control',
                'type': 'color'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Description du type d\'entité'
            })
        }
