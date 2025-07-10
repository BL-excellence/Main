# rawdocs/models.py

from os.path import join
from datetime import datetime
from django.db import models
from django.conf import settings

def pdf_upload_to(instance, filename):
    """
    Place chaque PDF téléchargé dans un sous-dossier horodaté.
    Ex. "20250626_143502/mon_document.pdf"
    """
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    return join(ts, filename)

class RawDocument(models.Model):
    url        = models.URLField(help_text="URL d'origine du PDF")
    file       = models.FileField(upload_to=pdf_upload_to, help_text="Fichier PDF téléchargé")
    created_at = models.DateTimeField(auto_now_add=True)
    
    # Validation status
    is_validated = models.BooleanField(default=False, help_text="Document validé par un métadonneur")
    validated_at = models.DateTimeField(null=True, blank=True)
    
    # Page extraction
    total_pages = models.IntegerField(default=0, help_text="Nombre total de pages")
    pages_extracted = models.BooleanField(default=False, help_text="Pages extraites individuellement")

    # On autorise NULL/blank pour ne pas casser les anciens enregistrements
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='raw_documents',
        null=True,
        blank=True,
        help_text="Utilisateur qui a téléchargé ce document"
    )

    def __str__(self):
        owner_name = self.owner.username if self.owner else "–"
        status = "✅ Validé" if self.is_validated else "⏳ En attente"
        return f"PDF #{self.pk} ({status}) – par {owner_name}"

class DocumentPage(models.Model):
    """Individual pages extracted from PDF"""
    document = models.ForeignKey(RawDocument, on_delete=models.CASCADE, related_name='pages')
    page_number = models.IntegerField(help_text="Numéro de la page (1-indexé)")
    raw_text = models.TextField(help_text="Texte brut extrait de la page")
    cleaned_text = models.TextField(help_text="Texte nettoyé pour annotation")
    
    # Annotation status
    is_annotated = models.BooleanField(default=False)
    annotated_at = models.DateTimeField(null=True, blank=True)
    annotated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='annotated_pages'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['document', 'page_number']
        ordering = ['page_number']
    
    def __str__(self):
        return f"Page {self.page_number} - {self.document}"

class AnnotationType(models.Model):
    """Types d'annotations possibles"""
    name = models.CharField(max_length=100, unique=True)
    display_name = models.CharField(max_length=100, help_text="Nom affiché dans l'interface")
    color = models.CharField(max_length=7, default="#3b82f6", help_text="Couleur hex pour l'annotation")
    description = models.TextField(blank=True)
    
    # Predefined types
    PROCEDURE_TYPE = "procedure_type"
    COUNTRY = "country"
    AUTHORITY = "authority"
    LEGAL_REFERENCE = "legal_reference"
    REQUIRED_DOCUMENT = "required_document"
    REQUIRED_CONDITION = "required_condition"
    DELAY = "delay"
    VARIATION_CODE = "variation_code"
    FILE_TYPE = "file_type"
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return self.display_name

class Annotation(models.Model):
    """Annotations on document pages"""
    page = models.ForeignKey(DocumentPage, on_delete=models.CASCADE, related_name='annotations')
    annotation_type = models.ForeignKey(AnnotationType, on_delete=models.CASCADE)
    
    # Text selection
    start_pos = models.IntegerField(help_text="Position de début dans le texte")
    end_pos = models.IntegerField(help_text="Position de fin dans le texte") 
    selected_text = models.CharField(max_length=500, help_text="Texte sélectionné")
    
    # AI confidence and context
    confidence_score = models.FloatField(default=0.0, help_text="Score de confiance de l'IA (0-1)")
    ai_reasoning = models.TextField(blank=True, help_text="Explication de l'IA pour cette annotation")
    
    # Manual validation
    is_validated = models.BooleanField(default=False)
    validated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='validated_annotations'
    )
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='created_annotations'
    )
    
    class Meta:
        ordering = ['start_pos']
    
    def __str__(self):
        return f"{self.annotation_type.display_name}: '{self.selected_text[:50]}...'"

class AnnotationSession(models.Model):
    """Track annotation sessions for analytics"""
    document = models.ForeignKey(RawDocument, on_delete=models.CASCADE, related_name='annotation_sessions')
    annotator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    
    # Session stats
    total_annotations = models.IntegerField(default=0)
    pages_annotated = models.IntegerField(default=0)
    ai_annotations = models.IntegerField(default=0)
    manual_annotations = models.IntegerField(default=0)
    
    # Timing
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    duration_minutes = models.IntegerField(default=0)
    
    def __str__(self):
        return f"Session {self.annotator.username} - {self.document}"