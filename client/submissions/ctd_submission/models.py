# # Chemin d'intégration : ctd_submission/models.py
# # Ce fichier définit les modèles de données pour l'application CTD submission
#
# from django.db import models
# from django.contrib.auth.models import User
# from django.utils import timezone
# import json
#
#
# class CTDModule(models.Model):
#     """
#     Représente un module CTD (Module 1, 2, 3, etc.)
#     """
#     MODULE_CHOICES = [
#         ('M1', 'Module 1 - Administrative Information'),
#         ('M2', 'Module 2 - Summaries'),
#         ('M3', 'Module 3 - Quality'),
#         ('M4', 'Module 4 - Non-clinical Study Reports'),
#         ('M5', 'Module 5 - Clinical Study Reports'),
#     ]
#
#     code = models.CharField(max_length=10, choices=MODULE_CHOICES, unique=True)
#     name = models.CharField(max_length=200)
#     description = models.TextField(blank=True)
#     created_at = models.DateTimeField(auto_now_add=True)
#
#     def __str__(self):
#         return f"{self.code} - {self.name}"
#
#
# class CTDSection(models.Model):
#     """
#     Représente une section dans un module CTD (ex: 1.1 Cover Letter)
#     """
#     module = models.ForeignKey(CTDModule, on_delete=models.CASCADE, related_name='sections')
#     code = models.CharField(max_length=20)  # ex: "1.1", "2.1"
#     name = models.CharField(max_length=200)  # ex: "Cover Letter"
#     description = models.TextField(blank=True)
#     parent_section = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True)
#     created_at = models.DateTimeField(auto_now_add=True)
#     updated_at = models.DateTimeField(auto_now=True)
#     order = models.PositiveIntegerField(default=0)
#
#     class Meta:
#         ordering = ['module', 'order', 'code']
#         unique_together = ['module', 'code']
#
#     def __str__(self):
#         return f"{self.module.code}.{self.code} - {self.name}"
#
#
# class Submission(models.Model):
#     """
#     Représente une soumission CTD complète
#     """
#     STATUS_CHOICES = [
#         ('draft', 'Draft'),
#         ('in_progress', 'En cours'),
#         ('completed', 'Completed'),
#         ('submitted', 'Submitted'),
#     ]
#
#     REGION_CHOICES = [
#         ('EU', 'Union Européenne (EMA)'),
#         ('US', 'États-Unis (FDA)'),
#         ('CA', 'Canada (Health Canada)'),
#         ('UK', 'Royaume-Uni (MHRA)'),
#     ]
#
#     name = models.CharField(max_length=200)  # ex: EU-MAA-001
#     region = models.CharField(max_length=10, choices=REGION_CHOICES)
#     submission_type = models.CharField(max_length=100)  # ex: MAA - Marketing Authorisation Application
#     variation_type = models.CharField(max_length=100, blank=True)
#     change_description = models.TextField(blank=True)
#     status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
#     created_by = models.ForeignKey(User, on_delete=models.CASCADE)
#     created_at = models.DateTimeField(auto_now_add=True)
#     updated_at = models.DateTimeField(auto_now=True)
#
#     def __str__(self):
#         return f"{self.name} - {self.region} - {self.status}"
#
#
# class Document(models.Model):
#     """
#     Représente un document uploadé dans une soumission
#     """
#     DOCUMENT_TYPES = [
#         ('pdf', 'PDF Document'),
#         ('docx', 'Word Document'),
#         ('xlsx', 'Excel Spreadsheet'),
#         ('form', 'Formulaire Web'),
#     ]
#
#     submission = models.ForeignKey(Submission, on_delete=models.CASCADE, related_name='documents')
#     section = models.ForeignKey(CTDSection, on_delete=models.CASCADE, related_name='documents',null=True, blank=True)
#     name = models.CharField(max_length=200)
#     file = models.FileField(upload_to='documents/', null=True, blank=True)
#     document_type = models.CharField(max_length=10, choices=DOCUMENT_TYPES)
#     content_extracted = models.JSONField(default=dict, blank=True)  # Contenu extrait automatiquement
#     template_data = models.JSONField(default=dict, blank=True)  # Données du template modifiable
#
#     is_template_generated = models.BooleanField(default=False)
#     created_at = models.DateTimeField(auto_now_add=True)
#     updated_at = models.DateTimeField(auto_now=True)
#
#     def __str__(self):
#         return f"{self.name} - {self.section}"
#
#
# class TemplateField(models.Model):
#     """
#     Représente un champ dans un template de document
#     """
#     FIELD_TYPES = [
#         ('text', 'Text Field'),
#         ('textarea', 'Text Area'),
#         ('select', 'Select Dropdown'),
#         ('checkbox', 'Checkbox'),
#         ('number', 'Number Field'),
#         ('date', 'Date Field'),
#     ]
#
#     document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='template_fields')
#     field_name = models.CharField(max_length=100)
#     field_label = models.CharField(max_length=200)
#     field_type = models.CharField(max_length=20, choices=FIELD_TYPES, default='text')
#     field_value = models.TextField(blank=True)
#     field_options = models.JSONField(default=list, blank=True)  # Pour les select, checkbox
#     is_required = models.BooleanField(default=False)
#     row_number = models.PositiveIntegerField(default=0)
#     column_number = models.PositiveIntegerField(default=0)
#     created_at = models.DateTimeField(auto_now_add=True)
#
#     class Meta:
#         ordering = ['row_number', 'column_number']
#
#     def __str__(self):
#         return f"{self.document.name} - {self.field_label}"
#
#
# class AIAnalysisResult(models.Model):
#     """
#     Stocke les résultats de l'analyse IA pour la classification automatique des documents
#     """
#     document = models.OneToOneField(Document, on_delete=models.CASCADE, related_name='ai_analysis')
#     suggested_module = models.ForeignKey(
#         CTDModule,
#         on_delete=models.CASCADE,
#         null=False,
#         default=1  # Assure-toi que l'ID 1 existe dans CTDModule
#     )
#     suggested_section = models.ForeignKey(CTDSection, on_delete=models.CASCADE)
#     confidence_score = models.FloatField(default=0.0)  # Score de confiance 0-1
#     analysis_details = models.JSONField(default=dict)  # Détails de l'analyse
#     keywords_found = models.JSONField(default=list)  # Mots-clés identifiés
#     created_at = models.DateTimeField(auto_now_add=True)
#
#     def __str__(self):
#         # Version simplifiée et sécurisée
#         try:
#             confidence = float(self.confidence_score) if self.confidence_score is not None else 0.0
#             # Échapper les caractères % dans le nom du document
#             safe_name = str(self.document.name).replace('%', '%%')
#             return f"Analysis for {safe_name} (Confidence: {confidence:.2f})"
#         except (ValueError, TypeError):
#             safe_name = str(self.document.name).replace('%', '%%')
#             return f"Analysis for {safe_name}"
#
# #################ajout
#
# # Ajout à ctd_submission/models.py - Modèle pour les versions de documents
#
# class DocumentVersion(models.Model):
#     """
#     Stocke les différentes versions d'un document modifié
#     """
#     document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='versions')
#     version_number = models.PositiveIntegerField()
#     content_data = models.JSONField(default=dict, blank=True)  # Contenu complet à cette version
#     template_data = models.JSONField(default=dict, blank=True)  # Données template à cette version
#     changes_summary = models.JSONField(default=list, blank=True)  # Résumé des changements
#     description = models.TextField(blank=True)  # Description de la version
#     created_by = models.ForeignKey(User, on_delete=models.CASCADE)
#     created_at = models.DateTimeField(auto_now_add=True)
#     is_current = models.BooleanField(default=False)  # Version actuelle active
#
#     class Meta:
#         ordering = ['-version_number']
#         unique_together = ['document', 'version_number']
#
#     def __str__(self):
#         return f"{self.document.name} - Version {self.version_number}"
#
#     def get_changes_count(self):
#         """Retourne le nombre de changements dans cette version"""
#         return len(self.changes_summary) if self.changes_summary else 0
#
#     def get_summary(self):
#         """Retourne un résumé des changements"""
#         if not self.changes_summary:
#             return "Aucun changement enregistré"
#
#         change_types = {}
#         for change in self.changes_summary:
#             change_type = change.get('type', 'unknown')
#             change_types[change_type] = change_types.get(change_type, 0) + 1
#
#         summary_parts = []
#         for change_type, count in change_types.items():
#             if change_type == 'text_change':
#                 summary_parts.append(f"{count} modification(s) de texte")
#             elif change_type == 'element_resize':
#                 summary_parts.append(f"{count} redimensionnement(s)")
#             elif change_type == 'element_move':
#                 summary_parts.append(f"{count} déplacement(s)")
#             else:
#                 summary_parts.append(f"{count} {change_type}")
#
#         return "; ".join(summary_parts)
#
#
# class EditingSession(models.Model):
#     """
#     Stocke les sessions d'édition pour le suivi collaboratif
#     """
#     document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='editing_sessions')
#     user = models.ForeignKey(User, on_delete=models.CASCADE)
#     started_at = models.DateTimeField(auto_now_add=True)
#     last_activity = models.DateTimeField(auto_now=True)
#     is_active = models.BooleanField(default=True)
#     changes_count = models.PositiveIntegerField(default=0)
#
#     class Meta:
#         ordering = ['-started_at']
#
#     def __str__(self):
#         return f"{self.user.username} - {self.document.name} ({self.started_at})"
#
#     def duration(self):
#         """Calcule la durée de la session"""
#         if self.is_active:
#             return timezone.now() - self.started_at
#         return self.last_activity - self.started_at
#
#
# # Signal pour créer automatiquement des versions
# from django.db.models.signals import post_save
# from django.dispatch import receiver
#
#
# @receiver(post_save, sender=Document)
# def create_initial_version(sender, instance, created, **kwargs):
#     """
#     Crée une version initiale lorsqu'un document est créé
#     """
#     if created:
#         DocumentVersion.objects.create(
#             document=instance,
#             version_number=1,
#             content_data=instance.content_extracted or {},
#             template_data=instance.template_data or {},
#             description="Version initiale",
#             created_by=instance.submission.created_by,
#             is_current=True
#         )
#
#
# # Fonction utilitaire pour la migration
# def create_versions_for_existing_documents():
#     """
#     Fonction pour créer des versions pour les documents existants
#     À exécuter dans une migration de données
#     """
#     from .models import Document, DocumentVersion
#
#     for document in Document.objects.all():
#         if not document.versions.exists():
#             DocumentVersion.objects.create(
#                 document=document,
#                 version_number=1,
#                 content_data=document.content_extracted or {},
#                 template_data=document.template_data or {},
#                 description="Version initiale (migration)",
#                 created_by=document.submission.created_by,
#                 is_current=True
#             )


# Chemin d'intégration : ctd_submission/models.py
# Ce fichier définit les modèles de données pour l'application CTD submission

# Chemin d'intégration : ctd_submission/models.py
# Ce fichier définit les modèles de données pour l'application CTD submission - VERSION CORRIGÉE

from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import json


class CTDModule(models.Model):
    """
    Représente un module CTD (Module 1, 2, 3, etc.)
    """
    MODULE_CHOICES = [
        ('M1', 'Module 1 - Administrative Information'),
        ('M2', 'Module 2 - Summaries'),
        ('M3', 'Module 3 - Quality'),
        ('M4', 'Module 4 - Non-clinical Study Reports'),
        ('M5', 'Module 5 - Clinical Study Reports'),
    ]

    code = models.CharField(max_length=10, choices=MODULE_CHOICES, unique=True)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.code} - {self.name}"

    class Meta:
        ordering = ['code']


class CTDSection(models.Model):
    """
    Représente une section dans un module CTD (ex: 1.1 Cover Letter)
    """
    module = models.ForeignKey(CTDModule, on_delete=models.CASCADE, related_name='sections')
    code = models.CharField(max_length=20)  # ex: "1.1", "2.1"
    name = models.CharField(max_length=200)  # ex: "Cover Letter"
    description = models.TextField(blank=True)
    parent_section = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['module', 'order', 'code']
        unique_together = ['module', 'code']

    def __str__(self):
        return f"{self.module.code}.{self.code} - {self.name}"


class Submission(models.Model):
    """
    Représente une soumission CTD complète
    """
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('in_progress', 'En cours'),
        ('completed', 'Completed'),
        ('submitted', 'Submitted'),
    ]

    REGION_CHOICES = [
        ('EU', 'Union Européenne (EMA)'),
        ('US', 'États-Unis (FDA)'),
        ('CA', 'Canada (Health Canada)'),
        ('UK', 'Royaume-Uni (MHRA)'),
    ]

    name = models.CharField(max_length=200)  # ex: EU-MAA-001
    region = models.CharField(max_length=10, choices=REGION_CHOICES)
    submission_type = models.CharField(max_length=100)  # ex: MAA - Marketing Authorisation Application
    variation_type = models.CharField(max_length=100, blank=True)
    change_description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} - {self.region} - {self.status}"

    class Meta:
        ordering = ['-created_at']


class Document(models.Model):
    """
    Représente un document uploadé dans une soumission
    """
    DOCUMENT_TYPES = [
        ('pdf', 'PDF Document'),
        ('docx', 'Word Document'),
        ('xlsx', 'Excel Spreadsheet'),
        ('form', 'Formulaire Web'),
    ]

    submission = models.ForeignKey(Submission, on_delete=models.CASCADE, related_name='documents')
    section = models.ForeignKey(CTDSection, on_delete=models.CASCADE, related_name='documents', null=True, blank=True)
    name = models.CharField(max_length=200)
    file = models.FileField(upload_to='documents/', null=True, blank=True)
    document_type = models.CharField(max_length=10, choices=DOCUMENT_TYPES)
    content_extracted = models.JSONField(default=dict, blank=True)  # Contenu extrait automatiquement
    template_data = models.JSONField(default=dict, blank=True)  # Données du template modifiable

    is_template_generated = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        section_name = f"{self.section}" if self.section else "Non assigné"
        return f"{self.name} - {section_name}"

    class Meta:
        ordering = ['-created_at']


class DocumentVersion(models.Model):
    """
    Stocke l'historique des versions d'un document modifié
    """
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='versions')
    version_number = models.PositiveIntegerField()
    content_data = models.JSONField(default=dict)  # Contenu du document à cette version
    template_data = models.JSONField(default=dict)  # Données du template à cette version
    changes_summary = models.JSONField(default=list)  # Résumé des changements
    description = models.TextField(blank=True)  # Description de la version
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    is_current = models.BooleanField(default=False)  # Version actuelle

    class Meta:
        ordering = ['-version_number']
        unique_together = ['document', 'version_number']

    def __str__(self):
        return f"{self.document.name} - Version {self.version_number}"


class TemplateField(models.Model):
    """
    Représente un champ dans un template de document
    """
    FIELD_TYPES = [
        ('text', 'Text Field'),
        ('textarea', 'Text Area'),
        ('select', 'Select Dropdown'),
        ('checkbox', 'Checkbox'),
        ('number', 'Number Field'),
        ('date', 'Date Field'),
        ('email', 'Email Field'),
        ('url', 'URL Field'),
    ]

    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='template_fields')
    field_name = models.CharField(max_length=100)
    field_label = models.CharField(max_length=200)
    field_type = models.CharField(max_length=20, choices=FIELD_TYPES, default='text')
    field_value = models.TextField(blank=True)
    field_options = models.JSONField(default=list, blank=True)  # Pour les select, checkbox
    is_required = models.BooleanField(default=False)
    row_number = models.PositiveIntegerField(default=0)
    column_number = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['row_number', 'column_number']

    def __str__(self):
        return f"{self.document.name} - {self.field_label}"


class AIAnalysisResult(models.Model):
    """
    Stocke les résultats de l'analyse IA pour la classification automatique des documents
    """
    document = models.OneToOneField(Document, on_delete=models.CASCADE, related_name='ai_analysis')
    suggested_module = models.ForeignKey(CTDModule, on_delete=models.CASCADE)
    suggested_section = models.ForeignKey(CTDSection, on_delete=models.CASCADE)
    confidence_score = models.FloatField(default=0.0)  # Score de confiance 0-1
    analysis_details = models.JSONField(default=dict)  # Détails de l'analyse
    keywords_found = models.JSONField(default=list)  # Mots-clés identifiés
    analysis_method = models.CharField(max_length=50, default='traditional')  # Méthode d'analyse utilisée
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        try:
            confidence = float(self.confidence_score) if self.confidence_score is not None else 0.0
            safe_name = str(self.document.name).replace('%', '%%')
            return f"Analysis for {safe_name} (Confidence: {confidence:.2f})"
        except (ValueError, TypeError):
            safe_name = str(self.document.name).replace('%', '%%')
            return f"Analysis for {safe_name}"

    class Meta:
        ordering = ['-created_at']


class DocumentAnnotation(models.Model):
    """
    Stocke les annotations et commentaires sur les documents
    """
    ANNOTATION_TYPES = [
        ('comment', 'Commentaire'),
        ('question', 'Question'),
        ('suggestion', 'Suggestion'),
        ('error', 'Erreur'),
        ('highlight', 'Surlignage'),
    ]

    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='annotations')
    annotation_type = models.CharField(max_length=20, choices=ANNOTATION_TYPES, default='comment')
    content = models.TextField()  # Contenu de l'annotation
    position_data = models.JSONField(default=dict)  # Position dans le document (coordonnées, etc.)
    selected_text = models.TextField(blank=True)  # Texte sélectionné pour l'annotation
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_resolved = models.BooleanField(default=False)
    resolved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='resolved_annotations')
    resolved_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.get_annotation_type_display()} on {self.document.name}"

    class Meta:
        ordering = ['-created_at']

    def mark_resolved(self, user):
        """Marque l'annotation comme résolue"""
        self.is_resolved = True
        self.resolved_by = user
        self.resolved_at = timezone.now()
        self.save()


class DocumentProcessingLog(models.Model):
    """
    Log des traitements effectués sur les documents
    """
    PROCESSING_TYPES = [
        ('extraction', 'Extraction de contenu'),
        ('analysis', 'Analyse IA'),
        ('template_generation', 'Génération de template'),
        ('validation', 'Validation'),
        ('export', 'Export'),
    ]

    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='processing_logs')
    processing_type = models.CharField(max_length=30, choices=PROCESSING_TYPES)
    status = models.CharField(max_length=20, choices=[
        ('started', 'Démarré'),
        ('completed', 'Terminé'),
        ('failed', 'Échoué'),
    ])
    details = models.JSONField(default=dict)  # Détails du traitement
    error_message = models.TextField(blank=True)  # Message d'erreur si échec
    processing_time = models.DurationField(null=True, blank=True)  # Temps de traitement
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.get_processing_type_display()} - {self.document.name} ({self.status})"

    class Meta:
        ordering = ['-created_at']


class UserPreferences(models.Model):
    """
    Préférences utilisateur pour l'éditeur
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='editor_preferences')
    default_edit_mode = models.CharField(max_length=20, choices=[
        ('text', 'Texte'),
        ('visual', 'Visuel'),
        ('structure', 'Structure'),
    ], default='text')
    auto_save_enabled = models.BooleanField(default=True)
    auto_save_interval = models.PositiveIntegerField(default=120)  # En secondes
    copilot_enabled = models.BooleanField(default=True)
    copilot_sensitivity = models.CharField(max_length=20, choices=[
        ('low', 'Faible'),
        ('medium', 'Moyenne'),
        ('high', 'Élevée'),
    ], default='medium')
    collaboration_enabled = models.BooleanField(default=True)
    theme = models.CharField(max_length=20, choices=[
        ('light', 'Clair'),
        ('dark', 'Sombre'),
        ('auto', 'Automatique'),
    ], default='light')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Préférences de {self.user.username}"

    class Meta:
        verbose_name = "Préférences utilisateur"
        verbose_name_plural = "Préférences utilisateur"


class CollaborationSession(models.Model):
    """
    Sessions de collaboration en temps réel
    """
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='collaboration_sessions')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    session_id = models.CharField(max_length=100, unique=True)
    cursor_position = models.JSONField(default=dict)  # Position du curseur
    active_element = models.CharField(max_length=100, blank=True)  # Élément actuellement édité
    last_activity = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.document.name}"

    class Meta:
        ordering = ['-last_activity']

    def is_expired(self):
        """Vérifie si la session a expiré (plus de 5 minutes d'inactivité)"""
        from datetime import timedelta
        return timezone.now() - self.last_activity > timedelta(minutes=5)


# Signaux pour automatiser certaines actions
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

@receiver(post_save, sender=Document)
def create_initial_version(sender, instance, created, **kwargs):
    """Crée une version initiale lors de la création d'un document"""
    if created and not instance.versions.exists():
        DocumentVersion.objects.create(
            document=instance,
            version_number=1,
            content_data=instance.content_extracted,
            template_data=instance.template_data,
            description="Version initiale",
            created_by=instance.submission.created_by,
            is_current=True
        )

@receiver(post_save, sender=User)
def create_user_preferences(sender, instance, created, **kwargs):
    """Crée les préférences utilisateur par défaut"""
    if created:
        UserPreferences.objects.create(user=instance)

@receiver(post_delete, sender=Document)
def cleanup_document_files(sender, instance, **kwargs):
    """Nettoie les fichiers lors de la suppression d'un document"""
    if instance.file:
        try:
            import os
            if os.path.isfile(instance.file.path):
                os.remove(instance.file.path)
        except Exception:
            pass  # Ignorer les erreurs de nettoyage