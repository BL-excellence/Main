# expert/models.py
from django.conf import settings
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import uuid


class ExpertLog(models.Model):
    """Logs des actions de l'expert"""

    ACTION_CHOICES = [
        ('annotation_validated', 'Annotation validée'),
        ('annotation_rejected', 'Annotation rejetée'),
        ('annotation_modified', 'Annotation modifiée'),
        ('annotation_deleted', 'Annotation supprimée'),
        ('annotation_created', 'Annotation créée'),
        ('validation_undone', 'Validation annulée'),
        ('document_reviewed', 'Document révisé'),
        ('sentence_reviewed', 'Phrase révisée'),
        ('annotation_type_created', 'Type d\'annotation créé'),
        ('annotation_type_deleted', 'Type d\'annotation supprimé'),
        ('document_validated_product_created', 'Document validé et produit créé'),
    ]

    # Info utilisateur et timing
    expert = models.ForeignKey(User, on_delete=models.CASCADE, related_name='expert_logs')
    timestamp = models.DateTimeField(auto_now_add=True)
    session_id = models.CharField(max_length=100, blank=True)

    # Info document/phrase
    document_id = models.IntegerField()
    document_title = models.CharField(max_length=500)
    page_id = models.IntegerField(null=True, blank=True)
    page_number = models.IntegerField(null=True, blank=True)
    page_text = models.TextField(blank=True)

    # Détails de l'action
    action = models.CharField(max_length=60, choices=ACTION_CHOICES)
    annotation_id = models.IntegerField(null=True, blank=True, help_text="ID de l'annotation concernée")

    # Détails de l'annotation
    annotation_text = models.TextField(blank=True, help_text="Texte de l'annotation")
    annotation_entity_type = models.CharField(max_length=100, blank=True)
    annotation_start_position = models.IntegerField(null=True, blank=True)
    annotation_end_position = models.IntegerField(null=True, blank=True)

    # Pour les modifications : avant/après
    old_text = models.TextField(blank=True, help_text="Ancien texte (pour modifications)")
    new_text = models.TextField(blank=True, help_text="Nouveau texte (pour modifications)")
    old_entity_type = models.CharField(max_length=100, blank=True)
    new_entity_type = models.CharField(max_length=100, blank=True)

    # Métadonnées
    original_annotator = models.CharField(max_length=150, blank=True, help_text="Qui a créé l'annotation originale")
    validation_status_before = models.CharField(max_length=50, blank=True)
    validation_status_after = models.CharField(max_length=50, blank=True)
    reason = models.TextField(blank=True, help_text="Raison de l'action")
    time_spent_seconds = models.IntegerField(null=True, blank=True)

    class Meta:
        verbose_name = "Log Expert"
        verbose_name_plural = "Logs Expert"
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.expert.username} - {self.get_action_display()} - {self.timestamp.strftime('%d/%m/%Y %H:%M')}"

    @property
    def detailed_description(self):
        """Description détaillée de l'action"""
        descriptions = {
            'annotation_validated': f"A validé l'annotation '{self.annotation_text}' ({self.annotation_entity_type}) créée par {self.original_annotator}",
            'annotation_rejected': f"A rejeté l'annotation '{self.annotation_text}' ({self.annotation_entity_type}) créée par {self.original_annotator}",
            'annotation_modified': f"A modifié l'annotation de '{self.old_text}' ({self.old_entity_type}) vers '{self.new_text}' ({self.new_entity_type})",
            'annotation_deleted': f"A supprimé l'annotation '{self.annotation_text}' ({self.annotation_entity_type})",
            'annotation_created': f"A créé une nouvelle annotation '{self.annotation_text}' ({self.annotation_entity_type})",
            'validation_undone': f"A annulé la validation de l'annotation '{self.annotation_text}' ({self.annotation_entity_type})",
        }

        base = descriptions.get(self.action, f"{self.get_action_display()}: {self.annotation_text}")
        context = f" dans la page {self.page_number} du document '{self.document_title}'"

        return base + context

    @property
    def change_summary(self):
        """Résumé des changements pour les modifications"""
        if self.action == 'annotation_modified':
            changes = []
            if self.old_text != self.new_text:
                changes.append(f"Texte: '{self.old_text}' → '{self.new_text}'")
            if self.old_entity_type != self.new_entity_type:
                changes.append(f"Type: {self.old_entity_type} → {self.new_entity_type}")
            return " | ".join(changes)
        return ""

from django.db import models
from django.contrib.auth import get_user_model


# app/expert/models.py


# app/expert/models.py
# from django.db import models
# from django.conf import settings  # ✅ pas MyProject.settings !
#
# class ExpertDelta(models.Model):
#     # ⬇︎ utiliser RawDocument (et le bon label d’app)
#     document = models.ForeignKey(
#         'rawdocs.RawDocument',            # <-- PAS 'rawdocs.Document'
#         on_delete=models.CASCADE,
#         related_name='expert_deltas'
#     )
#     payload = models.JSONField(default=dict)      # relations_added, relations_modified, qa_added, qa_modified, …
#     created_by = models.ForeignKey(
#         settings.AUTH_USER_MODEL,                 # supporte un User custom
#         null=True, on_delete=models.SET_NULL
#     )
#     created_at = models.DateTimeField(auto_now_add=True)
#     active = models.BooleanField(default=True)
#
#     class Meta:
#         ordering = ['-created_at']


# expert/models.py - Ajout du modèle ExpertDelta

from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
import json

User = get_user_model()


class ExpertDelta(models.Model):
    """
    Stocke les différences entre les résultats IA et les corrections de l'expert
    pour permettre l'apprentissage incrémental
    """

    # Référence au document
    document = models.ForeignKey(
        'rawdocs.RawDocument',
        on_delete=models.CASCADE,
        related_name='expert_deltas'
    )

    # Métadonnées de la correction
    expert = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    session_id = models.CharField(max_length=100, blank=True)

    # Type de correction
    DELTA_TYPES = [
        ('relation_added', 'Relation ajoutée'),
        ('relation_modified', 'Relation modifiée'),
        ('relation_removed', 'Relation supprimée'),
        ('entity_added', 'Entité ajoutée'),
        ('entity_modified', 'Entité modifiée'),
        ('qa_added', 'Q&A ajoutée'),
        ('qa_corrected', 'Q&A corrigée'),
        ('summary_corrected', 'Résumé corrigé'),
    ]
    delta_type = models.CharField(max_length=50, choices=DELTA_TYPES)

    # Contenu de la correction
    ai_version = models.JSONField(
        help_text="Version générée par l'IA avant correction"
    )
    expert_version = models.JSONField(
        help_text="Version corrigée par l'expert"
    )

    # Contexte de la correction
    context = models.JSONField(
        default=dict,
        help_text="Contexte additionnel (document_summary, entity_context, etc.)"
    )

    # Feedback de qualité
    confidence_before = models.FloatField(
        null=True, blank=True,
        help_text="Confiance de l'IA avant correction (0.0-1.0)"
    )
    expert_rating = models.IntegerField(
        null=True, blank=True,
        choices=[(i, f"{i}/5") for i in range(1, 6)],
        help_text="Qualité de la correction selon l'expert (1-5)"
    )

    # Statut
    is_validated = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)

    # Métadonnées d'apprentissage
    reused_count = models.IntegerField(
        default=0,
        help_text="Nombre de fois que cette correction a été réutilisée"
    )
    last_reused = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['document', 'delta_type']),
            models.Index(fields=['expert', 'created_at']),
            models.Index(fields=['is_active', 'is_validated']),
        ]

    def __str__(self):
        return f"{self.expert.username} - {self.get_delta_type_display()} - {self.created_at.strftime('%d/%m/%Y')}"

    @property
    def correction_summary(self):
        """Résumé lisible de la correction"""
        if self.delta_type == 'relation_added':
            rel = self.expert_version
            return f"Ajout relation: {rel.get('source', {}).get('value')} --{rel.get('type')}--> {rel.get('target', {}).get('value')}"
        elif self.delta_type == 'qa_added':
            qa = self.expert_version
            return f"Ajout Q&A: {qa.get('question', '')[:50]}..."
        elif self.delta_type == 'qa_corrected':
            return f"Correction réponse: {self.ai_version.get('answer', '')[:30]}... → {self.expert_version.get('answer', '')[:30]}..."
        return f"{self.get_delta_type_display()}"

    def mark_reused(self):
        """Marque cette correction comme réutilisée"""
        self.reused_count += 1
        self.last_reused = timezone.now()
        self.save(update_fields=['reused_count', 'last_reused'])


class ExpertLearningStats(models.Model):
    """Statistiques d'apprentissage pour le système IA"""

    expert = models.ForeignKey(User, on_delete=models.CASCADE)
    document_type = models.CharField(max_length=100, blank=True)

    # Métriques d'apprentissage
    total_corrections = models.IntegerField(default=0)
    relations_improved = models.IntegerField(default=0)
    qa_improved = models.IntegerField(default=0)

    # Qualité moyenne des corrections
    avg_expert_rating = models.FloatField(default=0.0)

    # Réutilisation
    corrections_reused = models.IntegerField(default=0)

    # Période
    period_start = models.DateTimeField()
    period_end = models.DateTimeField()
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['expert', 'document_type', 'period_start']