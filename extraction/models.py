# extraction/models.py - Version avec migration en 2 étapes
from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
import json

User = get_user_model()


class ExtractionResult(models.Model):
    """Résultat de l'extraction de métadonnées par IA"""

    STATUS_CHOICES = [
        ('pending', 'En attente'),
        ('processing', 'En cours'),
        ('completed', 'Terminé'),
        ('failed', 'Échec'),
        ('validated', 'Validé'),
    ]

    document = models.ForeignKey(
        'documents.Document',
        on_delete=models.CASCADE,
        related_name='extraction_results',
        verbose_name='Document'
    )

    # Données extraites par l'IA (JSON)
    extracted_data = models.JSONField(
        default=dict,
        verbose_name='Données extraites',
        help_text='Métadonnées extraites par l\'IA au format JSON'
    )

    # Scores de confiance pour chaque champ (JSON)
    confidence_scores = models.JSONField(
        default=dict,
        verbose_name='Scores de confiance',
        help_text='Score de confiance pour chaque champ extrait'
    )

    # Score de confiance global
    confidence_score = models.FloatField(
        default=0.0,
        verbose_name='Score de confiance global',
        help_text='Score de confiance moyen de l\'extraction (0.0 à 1.0)'
    )

    # Métadonnées de l'extraction
    extraction_method = models.CharField(
        max_length=50,
        default='mistral_ai',
        verbose_name='Méthode d\'extraction',
        help_text='Méthode utilisée pour l\'extraction (mistral_ai, openai, etc.)'
    )

    model_version = models.CharField(
        max_length=100,
        default='mistral-large-latest',
        verbose_name='Version du modèle',
        help_text='Version du modèle IA utilisé'
    )

    processing_time = models.FloatField(
        null=True,
        blank=True,
        verbose_name='Temps de traitement',
        help_text='Temps de traitement en secondes'
    )

    # Statut et métadonnées
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        verbose_name='Statut'
    )

    error_message = models.TextField(
        blank=True,
        null=True,
        verbose_name='Message d\'erreur',
        help_text='Message d\'erreur si l\'extraction a échoué'
    )

    # Métadonnées temporelles - ÉTAPE 1: Champs nullable d'abord
    created_at = models.DateTimeField(
        default=timezone.now,  # ← Changer ici pour éviter auto_now_add
        verbose_name='Créé le'
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='Mis à jour le'
    )

    validated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='Validé par',
        help_text='Utilisateur qui a validé les métadonnées'
    )

    validated_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Validé le'
    )

    class Meta:
        verbose_name = 'Résultat d\'extraction'
        verbose_name_plural = 'Résultats d\'extraction'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['document', '-created_at']),
            models.Index(fields=['status']),
            models.Index(fields=['confidence_score']),
        ]

    def __str__(self):
        return f"Extraction {self.document.title} - {self.confidence_score:.0%}"

    def get_extracted_field(self, field_name, default=None):
        """Récupérer un champ spécifique des données extraites"""
        if isinstance(self.extracted_data, dict):
            return self.extracted_data.get(field_name, default)
        return default

    def get_confidence_for_field(self, field_name):
        """Récupérer le score de confiance pour un champ"""
        if isinstance(self.confidence_scores, dict):
            return self.confidence_scores.get(field_name, 0.0)
        return 0.0

    def is_high_confidence(self, threshold=0.8):
        """Vérifier si l'extraction a une confiance élevée"""
        return self.confidence_score >= threshold

    def get_extracted_fields_summary(self):
        """Résumé des champs extraits avec succès"""
        if not isinstance(self.extracted_data, dict):
            return {}

        summary = {}
        for field, value in self.extracted_data.items():
            if value:  # Champ non vide
                confidence = self.get_confidence_for_field(field)
                summary[field] = {
                    'value': value,
                    'confidence': confidence,
                    'status': 'high' if confidence >= 0.8 else 'medium' if confidence >= 0.5 else 'low'
                }
        return summary

    @property
    def confidence_scores_dict(self):
        """Renvoie le dict de scores même si c’est stocké en string JSON."""
        if isinstance(self.confidence_scores, dict):
            return self.confidence_scores
        try:
            return json.loads(self.confidence_scores)
        except Exception:
            return {}

    def update_confidence_score(self):
        """Mettre à jour le score de confiance global"""
        if isinstance(self.confidence_scores, dict) and self.confidence_scores:
            # Calculer la moyenne des scores de confiance
            scores = [score for score in self.confidence_scores.values() if isinstance(score, (int, float))]
            if scores:
                self.confidence_score = sum(scores) / len(scores)
            else:
                self.confidence_score = 0.0
        else:
            self.confidence_score = 0.0

    def save(self, *args, **kwargs):
        # Mettre à jour le score de confiance avant la sauvegarde
        self.update_confidence_score()
        super().save(*args, **kwargs)

    @property
    def extraction_quality(self):
        """Qualité de l'extraction basée sur le score de confiance"""
        if self.confidence_score >= 0.8:
            return 'Excellente'
        elif self.confidence_score >= 0.6:
            return 'Bonne'
        elif self.confidence_score >= 0.4:
            return 'Moyenne'
        else:
            return 'Faible'

    @property
    def extracted_fields_count(self):
        """Nombre de champs extraits avec succès"""
        if isinstance(self.extracted_data, dict):
            return len([v for v in self.extracted_data.values() if v])
        return 0


class ExtractionTask(models.Model):
    """Suivi des tâches d'extraction en arrière-plan"""

    document = models.ForeignKey(
        'documents.Document',
        on_delete=models.CASCADE,
        related_name='extraction_tasks',
        verbose_name='Document'
    )

    task_id = models.CharField(
        max_length=255,
        unique=True,
        verbose_name='ID de tâche',
        help_text='ID de la tâche Celery'
    )

    status = models.CharField(
        max_length=20,
        choices=[
            ('pending', 'En attente'),
            ('started', 'Démarré'),
            ('success', 'Succès'),
            ('failure', 'Échec'),
            ('retry', 'Nouvelle tentative'),
        ],
        default='pending',
        verbose_name='Statut'
    )

    started_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Démarré le'
    )

    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Terminé le'
    )

    error_message = models.TextField(
        blank=True,
        null=True,
        verbose_name='Message d\'erreur'
    )

    # ÉTAPE 1: Champ avec default au lieu de auto_now_add
    created_at = models.DateTimeField(
        default=timezone.now,  # ← Utiliser default au lieu de auto_now_add
        verbose_name='Créé le'
    )

    class Meta:
        verbose_name = 'Tâche d\'extraction'
        verbose_name_plural = 'Tâches d\'extraction'
        ordering = ['-created_at']

    def __str__(self):
        return f"Tâche {self.task_id} - {self.document.title}"