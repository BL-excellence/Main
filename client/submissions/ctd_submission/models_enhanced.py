# ctd_submission/models_enhanced.py
# Modèles améliorés avec nouvelles fonctionnalités

from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator
import json
import uuid

from ctd_submission.models import CollaborationSession


class EnhancedDocument(models.Model):
    """
    Extension du modèle Document avec fonctionnalités avancées
    """
    # Champs de base (hérités du modèle original)
    submission = models.ForeignKey('Submission', on_delete=models.CASCADE, related_name='enhanced_documents')
    section = models.ForeignKey('CTDSection', on_delete=models.CASCADE, related_name='enhanced_documents', null=True,
                                blank=True)
    name = models.CharField(max_length=200)
    file = models.FileField(upload_to='documents/', null=True, blank=True)
    document_type = models.CharField(max_length=10, choices=[
        ('pdf', 'PDF Document'),
        ('docx', 'Word Document'),
        ('xlsx', 'Excel Spreadsheet'),
        ('form', 'Formulaire Web'),
    ])
    content_extracted = models.JSONField(default=dict, blank=True)
    template_data = models.JSONField(default=dict, blank=True)
    is_template_generated = models.BooleanField(default=False)

    # Nouveaux champs pour l'éditeur avancé
    document_structure = models.JSONField(default=dict, blank=True)  # Structure détectée automatiquement
    user_modifications = models.JSONField(default=list, blank=True)  # Modifications utilisateur
    collaboration_enabled = models.BooleanField(default=True)
    last_editor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    editing_session_id = models.UUIDField(default=uuid.uuid4, unique=True)

    # Métadonnées avancées
    word_count = models.PositiveIntegerField(default=0)
    character_count = models.PositiveIntegerField(default=0)
    reading_time_minutes = models.PositiveIntegerField(default=0)
    complexity_score = models.FloatField(default=0.0, validators=[MinValueValidator(0.0), MaxValueValidator(10.0)])

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_accessed = models.DateTimeField(null=True, blank=True)
    content_last_modified = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['submission', 'document_type']),
            models.Index(fields=['last_editor', 'updated_at']),
            models.Index(fields=['editing_session_id']),
        ]

    def __str__(self):
        section_name = f"{self.section}" if self.section else "Non assigné"
        return f"{self.name} - {section_name}"

    def update_statistics(self):
        """Met à jour les statistiques du document"""
        if self.content_extracted and 'text' in self.content_extracted:
            text = self.content_extracted['text']
            self.word_count = len(text.split())
            self.character_count = len(text)
            self.reading_time_minutes = max(1, self.word_count // 200)  # ~200 mots/minute
            self.complexity_score = self.calculate_complexity_score(text)
            self.save(update_fields=['word_count', 'character_count', 'reading_time_minutes', 'complexity_score'])

    def calculate_complexity_score(self, text):
        """Calcule un score de complexité basé sur la structure du texte"""
        if not text:
            return 0.0

        words = text.split()
        sentences = text.split('.')

        if len(sentences) == 0:
            return 0.0

        avg_words_per_sentence = len(words) / len(sentences)
        long_words = len([w for w in words if len(w) > 6])
        long_word_ratio = long_words / len(words) if words else 0

        # Score simple basé sur la longueur des phrases et la complexité des mots
        complexity = min(10.0, (avg_words_per_sentence / 3.0) + (long_word_ratio * 5.0))
        return round(complexity, 2)

    def get_table_of_contents(self):
        """Génère la table des matières pour le document"""
        if 'document_structure' in self.content_extracted:
            return self.content_extracted['document_structure'].get('toc', [])
        return []

    def get_active_collaborators(self):
        """Retourne les collaborateurs actifs sur ce document"""
        from datetime import timedelta
        recent_time = timezone.now() - timedelta(minutes=5)

        return CollaborationSession.objects.filter(
            document=self,
            is_active=True,
            last_activity__gte=recent_time
        ).select_related('user')

    def can_user_edit(self, user):
        """Vérifie si un utilisateur peut éditer ce document"""
        # Le propriétaire peut toujours éditer
        if self.submission.created_by == user:
            return True

        # Vérifier les permissions de collaboration
        if not self.collaboration_enabled:
            return False

        # Ajouter d'autres règles de permission ici
        return True


class DocumentStructure(models.Model):
    """
    Stocke la structure analysée d'un document
    """
    ELEMENT_TYPES = [
        ('heading', 'Titre'),
        ('paragraph', 'Paragraphe'),
        ('table', 'Tableau'),
        ('list', 'Liste'),
        ('image', 'Image'),
        ('section', 'Section'),
    ]

    document = models.ForeignKey(EnhancedDocument, on_delete=models.CASCADE, related_name='structure_elements')
    element_type = models.CharField(max_length=20, choices=ELEMENT_TYPES)
    element_id = models.CharField(max_length=100)  # ID unique dans le document
    parent_element = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True)

    # Position et structure
    order_index = models.PositiveIntegerField(default=0)
    hierarchy_level = models.PositiveIntegerField(default=0)

    # Contenu
    title = models.CharField(max_length=500, blank=True)
    content_preview = models.TextField(blank=True)  # Aperçu du contenu
    metadata = models.JSONField(default=dict, blank=True)

    # Navigation
    anchor_id = models.CharField(max_length=100, blank=True)  # Pour la navigation
    is_toc_visible = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['document', 'order_index']
        unique_together = ['document', 'element_id']
        indexes = [
            models.Index(fields=['document', 'element_type']),
            models.Index(fields=['document', 'order_index']),
        ]

    def __str__(self):
        return f"{self.document.name} - {self.get_element_type_display()}: {self.title}"

    def get_children(self):
        """Retourne les éléments enfants"""
        return DocumentStructure.objects.filter(parent_element=self).order_by('order_index')

    def get_breadcrumb(self):
        """Retourne le chemin de navigation vers cet élément"""
        breadcrumb = []
        current = self

        while current:
            breadcrumb.insert(0, {
                'id': current.element_id,
                'title': current.title,
                'type': current.element_type
            })
            current = current.parent_element

        return breadcrumb


class SmartSuggestion(models.Model):
    """
    Suggestions intelligentes générées par l'IA
    """
    SUGGESTION_TYPES = [
        ('grammar', 'Grammaire'),
        ('spelling', 'Orthographe'),
        ('style', 'Style'),
        ('consistency', 'Cohérence'),
        ('structure', 'Structure'),
        ('content', 'Contenu'),
        ('formatting', 'Mise en forme'),
    ]

    PRIORITY_LEVELS = [
        ('low', 'Faible'),
        ('medium', 'Moyenne'),
        ('high', 'Élevée'),
        ('critical', 'Critique'),
    ]

    STATUS_CHOICES = [
        ('pending', 'En attente'),
        ('accepted', 'Acceptée'),
        ('rejected', 'Rejetée'),
        ('ignored', 'Ignorée'),
    ]

    document = models.ForeignKey(EnhancedDocument, on_delete=models.CASCADE, related_name='smart_suggestions')
    user = models.ForeignKey(User, on_delete=models.CASCADE)

    # Localisation dans le document
    element_id = models.CharField(max_length=100, blank=True)
    text_selection = models.TextField(blank=True)  # Texte sélectionné
    position_data = models.JSONField(default=dict, blank=True)  # Position précise

    # Suggestion
    suggestion_type = models.CharField(max_length=20, choices=SUGGESTION_TYPES)
    priority = models.CharField(max_length=10, choices=PRIORITY_LEVELS, default='medium')
    title = models.CharField(max_length=200)
    message = models.TextField()
    suggested_replacement = models.TextField(blank=True)

    # Métadonnées IA
    confidence_score = models.FloatField(default=0.0, validators=[MinValueValidator(0.0), MaxValueValidator(1.0)])
    ai_model_used = models.CharField(max_length=50, blank=True)
    reasoning = models.TextField(blank=True)  # Explication de la suggestion

    # État
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    applied_at = models.DateTimeField(null=True, blank=True)
    applied_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='applied_suggestions')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-priority', '-confidence_score', '-created_at']
        indexes = [
            models.Index(fields=['document', 'status']),
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['priority', 'confidence_score']),
        ]

    def __str__(self):
        return f"{self.get_suggestion_type_display()} - {self.title}"

    def apply_suggestion(self, user):
        """Applique la suggestion"""
        self.status = 'accepted'
        self.applied_at = timezone.now()
        self.applied_by = user
        self.save()

    def reject_suggestion(self, user):
        """Rejette la suggestion"""
        self.status = 'rejected'
        self.applied_by = user
        self.save()

    def get_priority_color(self):
        """Retourne la couleur associée à la priorité"""
        colors = {
            'low': '#28a745',
            'medium': '#ffc107',
            'high': '#fd7e14',
            'critical': '#dc3545'
        }
        return colors.get(self.priority, '#6c757d')


class DocumentMetrics(models.Model):
    """
    Métriques détaillées d'un document
    """
    document = models.OneToOneField(EnhancedDocument, on_delete=models.CASCADE, related_name='metrics')

    # Métriques de contenu
    total_characters = models.PositiveIntegerField(default=0)
    total_words = models.PositiveIntegerField(default=0)
    total_sentences = models.PositiveIntegerField(default=0)
    total_paragraphs = models.PositiveIntegerField(default=0)
    total_headings = models.PositiveIntegerField(default=0)
    total_tables = models.PositiveIntegerField(default=0)
    total_images = models.PositiveIntegerField(default=0)

    # Métriques de structure
    heading_distribution = models.JSONField(default=dict, blank=True)  # h1: 5, h2: 12, etc.
    average_sentence_length = models.FloatField(default=0.0)
    readability_score = models.FloatField(default=0.0)

    # Métriques d'édition
    total_edits = models.PositiveIntegerField(default=0)
    last_major_edit = models.DateTimeField(null=True, blank=True)
    edit_frequency = models.FloatField(default=0.0)  # éditions par jour

    # Métriques de collaboration
    unique_editors = models.PositiveIntegerField(default=0)
    total_comments = models.PositiveIntegerField(default=0)
    resolved_comments = models.PositiveIntegerField(default=0)

    # Métriques de qualité
    spelling_errors = models.PositiveIntegerField(default=0)
    grammar_issues = models.PositiveIntegerField(default=0)
    style_suggestions = models.PositiveIntegerField(default=0)

    # Horodatage
    calculated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['document', 'calculated_at']),
        ]

    def __str__(self):
        return f"Métriques - {self.document.name}"

    def calculate_readability_score(self):
        """Calcule un score de lisibilité simple"""
        if self.total_sentences == 0 or self.total_words == 0:
            return 0.0

        avg_sentence_length = self.total_words / self.total_sentences
        # Score simple basé sur la longueur moyenne des phrases
        # Plus la phrase est courte, plus c'est lisible
        score = max(0, 10 - (avg_sentence_length / 5))
        return min(10.0, score)

    def get_quality_score(self):
        """Calcule un score de qualité global"""
        if self.total_words == 0:
            return 0.0

        # Pénalités pour les erreurs
        error_penalty = (self.spelling_errors + self.grammar_issues) / self.total_words * 100

        # Bonus pour la structure
        structure_bonus = min(2.0, self.total_headings / max(1, self.total_paragraphs) * 10)

        # Score de base
        base_score = 8.0 - error_penalty + structure_bonus

        return max(0.0, min(10.0, base_score))


# Signaux pour maintenir les métriques à jour
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver


@receiver(post_save, sender=EnhancedDocument)
def update_document_metrics(sender, instance, **kwargs):
    """Met à jour les métriques quand un document est modifié"""
    if hasattr(instance, 'metrics'):
        instance.update_statistics()
    else:
        DocumentMetrics.objects.create(document=instance)


@receiver(post_save, sender=SmartSuggestion)
def update_suggestion_metrics(sender, instance, created, **kwargs):
    """Met à jour les métriques quand une suggestion est créée/modifiée"""
    if hasattr(instance.document, 'metrics'):
        metrics = instance.document.metrics
        if instance.suggestion_type == 'spelling':
            metrics.spelling_errors = SmartSuggestion.objects.filter(
                document=instance.document,
                suggestion_type='spelling',
                status='pending'
            ).count()
        elif instance.suggestion_type == 'grammar':
            metrics.grammar_issues = SmartSuggestion.objects.filter(
                document=instance.document,
                suggestion_type='grammar',
                status='pending'
            ).count()
        elif instance.suggestion_type == 'style':
            metrics.style_suggestions = SmartSuggestion.objects.filter(
                document=instance.document,
                suggestion_type='style',
                status='pending'
            ).count()

        metrics.save()