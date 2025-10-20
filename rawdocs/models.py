# rawdocs/models.py
from os.path import join
from datetime import datetime
from django.db import models
from django.conf import settings
from django.contrib.auth.models import User
from django.db.models import SET_NULL


def pdf_upload_to(instance, filename):
    """
    Place chaque PDF téléchargé dans un sous-dossier organisé par source.
    Ex. "Client/20250626_143502/mon_document.pdf" pour les clients
    Ex. "20250626_143502/mon_document.pdf" pour les métadonneurs
    """
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')

    # Si c'est un document client, le placer dans le dossier Client
    if hasattr(instance, 'source') and instance.source == 'Client':
        return join('Client', ts, filename)

    # Pour les métadonneurs, garder l'ancien système
    return join(ts, filename)


class RawDocument(models.Model):
    # Source & stockage
    url = models.URLField(help_text="URL d'origine du PDF", blank=True)
    file = models.FileField(upload_to=pdf_upload_to, help_text="Fichier PDF téléchargé")
    created_at = models.DateTimeField(auto_now_add=True)
    # Ownership
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='raw_documents',
        null=True, blank=True,
        help_text="Utilisateur qui a téléchargé ce document"
    )

    # Statut de validation
    is_validated = models.BooleanField(default=False, help_text="Document validé par un métadonneur")
    validated_at = models.DateTimeField(null=True, blank=True)
    # Expert review status
    is_ready_for_expert = models.BooleanField(default=False, help_text="Document prêt pour révision expert")
    expert_ready_at = models.DateTimeField(null=True, blank=True,
                                           help_text="Date à laquelle le document est devenu prêt pour l'expert")

    # Extraction de pages
    total_pages = models.IntegerField(default=0, help_text="Nombre total de pages")
    pages_extracted = models.BooleanField(default=False, help_text="Pages extraites individuellement")

    def is_accessible_by(self, user):
        """
        Vérifie si un utilisateur a accès à ce document.
        Pour l'instant, l'accès est accordé au propriétaire du document et aux superutilisateurs.
        """
        if user.is_superuser:
            return True
        if self.owner and self.owner == user:
            return True
        # Si l'utilisateur n'est pas authentifié, refuser l'accès
        if not user.is_authenticated:
            return False
        # Par défaut, autoriser l'accès (pour maintenir la compatibilité avec le code existant)
        # Dans un environnement de production, vous pourriez vouloir être plus restrictif
        return True

    # Métadonnées extraites
    title = models.TextField(blank=True, help_text="Titre du document")
    doc_type = models.CharField("Type", max_length=100, blank=True, help_text="Type du document (guide, rapport…)")
    publication_date = models.CharField(max_length=100, blank=True, help_text="Date de publication")
    version = models.CharField(max_length=50, blank=True, help_text="Version extraite")
    source = models.CharField(max_length=255, blank=True, help_text="Organisation émettrice (EMA, FDA…)")
    context = models.TextField(blank=True, help_text="Contexte extrait (2 phrases max)")
    country = models.CharField(max_length=100, blank=True, help_text="Pays détecté (GPE ou TLD)")
    language = models.CharField(max_length=10, blank=True, help_text="Langue détectée (fr, en…)")
    url_source = models.URLField(blank=True, help_text="URL d'origine pour référence")
    original_ai_metadata = models.JSONField(null=True, blank=True,
                                            help_text="Original AI extracted metadata for RLHF comparison")
    # JSON global de toutes les annotations du document
    global_annotations_json = models.JSONField(
        null=True, blank=True,
        help_text="JSON global consolidé de toutes les annotations du document"
    )

    # Résumé global en langage naturel des annotations du document
    global_annotations_summary = models.TextField(
        blank=True,
        help_text="Résumé global en langage naturel des annotations du document"
    )

    # Date de génération du résumé global
    global_annotations_summary_generated_at = models.DateTimeField(
        null=True, blank=True,
        help_text="Date de génération du résumé global d'annotations"
    )

    # Nouveaux champs pour l'enrichissement (ajoutés depuis le second modèle)
    enriched_annotations_json = models.JSONField(null=True, blank=True)
    enriched_at = models.DateTimeField(null=True, blank=True)
    enriched_by = models.ForeignKey(User, on_delete=SET_NULL, null=True, blank=True, related_name='enriched_documents')

    # Contenu structuré (cache HTML fidèle au PDF)
    structured_html = models.TextField(blank=True,
                                       help_text="HTML structuré fidèle au PDF (mise en page, tableaux, images)")
    structured_html_generated_at = models.DateTimeField(null=True, blank=True,
                                                        help_text="Date de génération du HTML structuré")
    structured_html_method = models.CharField(max_length=100, blank=True, help_text="Méthode d'extraction utilisée")
    structured_html_confidence = models.FloatField(null=True, blank=True, help_text="Confiance globale de l'extraction")

    # Validation par expert
    is_expert_validated = models.BooleanField(default=False, help_text="Document validé par un expert")
    expert_validated_at = models.DateTimeField(null=True, blank=True, help_text="Date de validation par un expert")

    def __str__(self):
        owner_name = self.owner.username if self.owner else "–"
        status = "✅ Validé" if self.is_validated else "⏳ En attente"
        return f"PDF #{self.pk} ({status}) – par {owner_name}"

    def get_total_annotations_count(self):
        """Retourne le nombre total d'annotations dans le document"""
        return sum(page.annotations.count() for page in self.pages.all())

    def get_annotations_by_type(self):
        """Retourne un dictionnaire des annotations groupées par type"""
        annotations_by_type = {}
        for page in self.pages.all():
            for annotation in page.annotations.all():
                ann_type = annotation.annotation_type.display_name
                if ann_type not in annotations_by_type:
                    annotations_by_type[ann_type] = 0
                annotations_by_type[ann_type] += 1
        return annotations_by_type

    def has_annotations(self):
        """Vérifie si le document contient des annotations"""
        return self.get_total_annotations_count() > 0

    def get_page_relations(self):
        """Récupère toutes les relations trouvées dans les pages du document"""
        all_relations = []
        for page in self.pages.all():
            if page.regulatory_analysis and 'relations' in page.regulatory_analysis:
                for relation in page.regulatory_analysis['relations']:
                    relation['page_number'] = page.page_number
                    all_relations.append(relation)
        return all_relations

    def get_semantic_entities(self):
        """Récupère toutes les entités sémantiques du document"""
        entities = {}
        for page in self.pages.all():
            if page.regulatory_analysis and 'entities' in page.regulatory_analysis:
                for entity_type, entity_list in page.regulatory_analysis['entities'].items():
                    if entity_type not in entities:
                        entities[entity_type] = set()
                    if isinstance(entity_list, list):
                        entities[entity_type].update(entity_list)

        # Convertir les sets en listes pour la sérialisation
        return {k: list(v) for k, v in entities.items()}

    def find_relations_between_pages(self, source_page_number, target_page_number):
        """Trouve les relations potentielles entre deux pages"""
        source_page = self.pages.filter(page_number=source_page_number).first()
        target_page = self.pages.filter(page_number=target_page_number).first()

        if not source_page or not target_page:
            return []

        cross_page_relations = []

        # Récupérer les entités de chaque page
        source_entities = source_page.get_all_entities()
        target_entities = target_page.get_all_entities()

        # Chercher les relations possibles entre les entités des deux pages
        for source_type, source_values in source_entities.items():
            for target_type, target_values in target_entities.items():
                for source_value in source_values:
                    for target_value in target_values:
                        # Détecter les relations potentielles basées sur les types d'entités
                        potential_relation = self._detect_potential_relation(
                            source_type, source_value, target_type, target_value
                        )
                        if potential_relation:
                            potential_relation['source_page'] = source_page_number
                            potential_relation['target_page'] = target_page_number
                            cross_page_relations.append(potential_relation)

        return cross_page_relations

    def _detect_potential_relation(self, source_type, source_value, target_type, target_value):
        """Détecte une relation potentielle entre deux entités basée sur leurs types"""
        relation_patterns = {
            ('product', 'ingredient'): 'contains',
            ('product', 'organization'): 'manufactured_by',
            ('product', 'indication'): 'used_for',
            ('product', 'contraindication'): 'contraindicated_with',
            ('procedure', 'authority'): 'submitted_to',
            ('procedure', 'date'): 'due_by',
            ('regulation', 'authority'): 'issued_by',
            ('product', 'dosage'): 'has_dosage',
        }

        key = (source_type.lower(), target_type.lower())
        if key in relation_patterns:
            return {
                'source': {'type': source_type, 'value': source_value},
                'target': {'type': target_type, 'value': target_value},
                'type': relation_patterns[key],
                'confidence': 0.7,  # Confiance modérée car c'est une détection automatique
                'detected_by': 'pattern_matching'
            }

        return None

    def get_regulatory_summary(self):
        """Retourne un résumé consolidé de tous les aspects réglementaires du document"""
        summary = {
            'total_pages': self.total_pages,
            'analyzed_pages': 0,
            'total_obligations': [],
            'critical_deadlines': [],
            'authorities_mentioned': set(),
            'regulations_referenced': set(),
            'importance_score': 0
        }

        for page in self.pages.all():
            if page.is_regulatory_analyzed:
                summary['analyzed_pages'] += 1

                # Obligations
                if page.regulatory_obligations:
                    summary['total_obligations'].extend(page.regulatory_obligations)

                # Délais critiques
                if page.critical_deadlines:
                    summary['critical_deadlines'].extend(page.critical_deadlines)

                # Autorités et régulations
                if page.regulatory_analysis:
                    entities = page.regulatory_analysis.get('entities', {})
                    if 'authorities' in entities:
                        summary['authorities_mentioned'].update(entities['authorities'])
                    if 'regulations' in entities:
                        summary['regulations_referenced'].update(entities['regulations'])

                # Score d'importance
                summary['importance_score'] += page.regulatory_importance_score

        # Convertir les sets en listes et calculer le score moyen
        summary['authorities_mentioned'] = list(summary['authorities_mentioned'])
        summary['regulations_referenced'] = list(summary['regulations_referenced'])
        if summary['analyzed_pages'] > 0:
            summary['importance_score'] = summary['importance_score'] // summary['analyzed_pages']

        return summary


class MetadataLog(models.Model):
    document = models.ForeignKey('RawDocument', on_delete=models.CASCADE, related_name='logs')
    field_name = models.CharField(max_length=100)
    old_value = models.TextField(null=True, blank=True)
    new_value = models.TextField(null=True, blank=True)
    modified_at = models.DateTimeField(auto_now_add=True)
    modified_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)

    def __str__(self):
        return f"{self.field_name}: {self.old_value} → {self.new_value}"


class DocumentPage(models.Model):
    """Pages individuelles extraites du PDF."""
    document = models.ForeignKey(RawDocument, on_delete=models.CASCADE, related_name='pages')
    page_number = models.IntegerField(help_text="Numéro de page (1-indexé)")
    raw_text = models.TextField(help_text="Texte brut extrait de la page")
    cleaned_text = models.TextField(help_text="Texte nettoyé pour annotation")

    # Statut d'annotation (existant)
    is_annotated = models.BooleanField(default=False)
    annotated_at = models.DateTimeField(null=True, blank=True)
    annotated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='annotated_pages'
    )

    # =================== NOUVEAUX CHAMPS POUR L'ANALYSE RÉGLEMENTAIRE ===================

    # Analyse réglementaire par IA
    regulatory_analysis = models.JSONField(
        null=True, blank=True,
        help_text="Analyse réglementaire complète de la page par IA"
    )

    # Résumé de la page
    page_summary = models.TextField(
        blank=True,
        help_text="Résumé concis du contenu de la page"
    )

    # Obligations réglementaires identifiées
    regulatory_obligations = models.JSONField(
        default=list,
        help_text="Liste des obligations réglementaires trouvées sur cette page"
    )

    # Délais critiques
    critical_deadlines = models.JSONField(
        default=list,
        help_text="Délais critiques identifiés sur cette page"
    )

    # Score d'importance réglementaire (0-100)
    regulatory_importance_score = models.IntegerField(
        default=0,
        help_text="Score d'importance réglementaire de cette page (0-100)"
    )

    # Statut d'analyse réglementaire
    is_regulatory_analyzed = models.BooleanField(
        default=False,
        help_text="Page analysée par l'IA pour les aspects réglementaires"
    )

    regulatory_analyzed_at = models.DateTimeField(
        null=True, blank=True,
        help_text="Date d'analyse réglementaire"
    )

    regulatory_analyzed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='regulatory_analyzed_pages',
        help_text="Utilisateur qui a lancé l'analyse réglementaire"
    )

    # Validation humaine (existant)
    is_validated_by_human = models.BooleanField(default=False)
    human_validated_at = models.DateTimeField(null=True, blank=True)
    validated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='validated_pages'
    )

    # Nouveaux champs pour validation du résumé (ajoutés depuis le second modèle)
    summary_validated = models.BooleanField(default=False)
    summary_validated_at = models.DateTimeField(null=True, blank=True)
    summary_validated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=SET_NULL,
        null=True, blank=True,
        related_name='validated_page_summaries'
    )

    # JSON des annotations de la page
    annotations_json = models.JSONField(
        null=True, blank=True,
        help_text="JSON structuré de toutes les annotations de cette page"
    )

    # Résumé en langage naturel des annotations de la page
    annotations_summary = models.TextField(
        blank=True,
        help_text="Résumé en langage naturel des annotations de cette page"
    )

    # Date de génération du résumé
    annotations_summary_generated_at = models.DateTimeField(
        null=True, blank=True,
        help_text="Date de génération du résumé d'annotations"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['document', 'page_number']
        ordering = ['page_number']

    def __str__(self):
        return f"Page {self.page_number} – Doc #{self.document.pk}"

    def get_regulatory_summary(self):
        """Retourne un résumé des points réglementaires de la page"""
        if not self.regulatory_analysis:
            return "Aucune analyse réglementaire disponible"

        analysis = self.regulatory_analysis
        summary_parts = []

        if analysis.get('obligations'):
            summary_parts.append(f"📋 {len(analysis['obligations'])} obligation(s)")

        if analysis.get('deadlines'):
            summary_parts.append(f"⏰ {len(analysis['deadlines'])} délai(s)")

        if analysis.get('authorities'):
            summary_parts.append(f"🏛️ {len(analysis['authorities'])} autorité(s)")

        return " • ".join(summary_parts) if summary_parts else "Aucun élément réglementaire majeur"

    def get_all_entities(self):
        """Récupère toutes les entités de la page depuis l'analyse réglementaire"""
        if not self.regulatory_analysis:
            return {}

        entities = self.regulatory_analysis.get('entities', {})
        # Nettoyer et standardiser les entités
        cleaned_entities = {}
        for entity_type, entity_list in entities.items():
            if isinstance(entity_list, list) and entity_list:
                cleaned_entities[entity_type] = entity_list

        return cleaned_entities

    def get_page_relations(self):
        """Récupère toutes les relations de cette page"""
        if not self.regulatory_analysis:
            return []

        return self.regulatory_analysis.get('relations', [])

    def find_entities_by_type(self, entity_type):
        """Trouve toutes les entités d'un type spécifique sur cette page"""
        entities = self.get_all_entities()
        return entities.get(entity_type, [])

    def has_regulatory_content(self):
        """Vérifie si la page contient du contenu réglementaire significatif"""
        if not self.regulatory_analysis:
            return False

        analysis = self.regulatory_analysis
        has_content = (
                len(analysis.get('obligations', [])) > 0 or
                len(analysis.get('relations', [])) > 0 or
                any(len(v) > 0 for v in analysis.get('entities', {}).values() if isinstance(v, list))
        )

        return has_content

    def get_linked_pages(self, document):
        """Trouve les pages liées à cette page via des relations"""
        linked_pages = set()

        if not self.regulatory_analysis:
            return []

        # Récupérer toutes les entités de cette page
        my_entities = self.get_all_entities()
        my_entity_values = set()
        for entity_list in my_entities.values():
            if isinstance(entity_list, list):
                my_entity_values.update(entity_list)

        # Parcourir toutes les autres pages du document
        for other_page in document.pages.exclude(id=self.id):
            if other_page.regulatory_analysis:
                other_entities = other_page.get_all_entities()
                other_entity_values = set()
                for entity_list in other_entities.values():
                    if isinstance(entity_list, list):
                        other_entity_values.update(entity_list)

                # Si il y a des entités communes, les pages sont liées
                if my_entity_values & other_entity_values:
                    linked_pages.add(other_page.page_number)

        return sorted(list(linked_pages))


class DocumentRegulatoryAnalysis(models.Model):
    """Analyse réglementaire globale d'un document"""
    document = models.OneToOneField(
        RawDocument,
        on_delete=models.CASCADE,
        related_name='regulatory_analysis'
    )

    # Résumé global du document
    global_summary = models.TextField(
        blank=True,
        help_text="Résumé global du document complet"
    )

    # Analyse réglementaire consolidée
    consolidated_analysis = models.JSONField(
        default=dict,
        help_text="Analyse réglementaire consolidée de tout le document"
    )

    # Obligations principales du document
    main_obligations = models.JSONField(
        default=list,
        help_text="Principales obligations réglementaires du document"
    )

    # Délais critiques consolidés
    critical_deadlines_summary = models.JSONField(
        default=list,
        help_text="Résumé des délais critiques du document"
    )

    # Autorités concernées
    relevant_authorities = models.JSONField(
        default=list,
        help_text="Autorités réglementaires mentionnées dans le document"
    )

    # Score global d'importance réglementaire
    global_regulatory_score = models.IntegerField(
        default=0,
        help_text="Score global d'importance réglementaire (0-100)"
    )

    # Métadonnées d'analyse
    analyzed_at = models.DateTimeField(auto_now_add=True)
    analyzed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True
    )

    # Pages analysées
    total_pages_analyzed = models.IntegerField(default=0)
    pages_with_regulatory_content = models.IntegerField(default=0)

    def __str__(self):
        return f"Analyse réglementaire - Doc #{self.document.pk}"

    def get_completion_percentage(self):
        """Pourcentage de pages analysées"""
        if self.document.total_pages == 0:
            return 0
        return int((self.total_pages_analyzed / self.document.total_pages) * 100)

    def get_regulatory_density(self):
        """Densité du contenu réglementaire"""
        if self.total_pages_analyzed == 0:
            return 0
        return int((self.pages_with_regulatory_content / self.total_pages_analyzed) * 100)


class AnnotationType(models.Model):
    """Types d'annotations possibles."""
    name = models.CharField(max_length=100, unique=True)
    display_name = models.CharField(max_length=100, help_text="Libellé affiché")
    color = models.CharField(max_length=7, default="#3b82f6", help_text="Couleur hexadécimale")
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
    """Annotation sur une page de document."""
    page = models.ForeignKey(DocumentPage, on_delete=models.CASCADE, related_name='annotations')
    annotation_type = models.ForeignKey(AnnotationType, on_delete=models.CASCADE)

    # Text selection
    start_pos = models.IntegerField(help_text="Position de début dans le texte")
    end_pos = models.IntegerField(help_text="Position de fin dans le texte")
    selected_text = models.CharField(max_length=500, help_text="Texte sélectionné")

    # Selection mode & structured selection anchors
    MODE_CHOICES = [
        ('raw', 'Raw Text'),
        ('structured', 'Structured HTML'),
    ]
    mode = models.CharField(
        max_length=20,
        choices=MODE_CHOICES,
        default='raw',
        help_text='Annotation mode: raw text or structured HTML'
    )
    start_xpath = models.TextField(
        blank=True, null=True,
        help_text='XPath to start node for structured annotations'
    )
    end_xpath = models.TextField(
        blank=True, null=True,
        help_text='XPath to end node for structured annotations'
    )
    start_offset = models.IntegerField(
        blank=True, null=True,
        help_text='Character offset within start node'
    )
    end_offset = models.IntegerField(
        blank=True, null=True,
        help_text='Character offset within end node'
    )

    # AI confidence and context
    confidence_score = models.FloatField(default=0.0, help_text="Score IA (0.0–1.0)")
    ai_reasoning = models.TextField(blank=True, help_text="Raisonnement IA pour cette annotation")

    # Expert validation status
    VALIDATION_CHOICES = [
        ('pending', 'En attente'),
        ('validated', 'Validé'),
        ('rejected', 'Rejeté'),
        ('expert_created', 'Créé par expert'),
    ]

    validation_status = models.CharField(
        max_length=20,
        choices=VALIDATION_CHOICES,
        default='pending',
        help_text="Statut de validation par l'expert"
    )

    # Source tracking
    SOURCE_CHOICES = [
        ('ai', 'Intelligence Artificielle'),
        ('manual', 'Manuel'),
        ('expert', 'Expert'),
    ]
    source = models.CharField(max_length=10, choices=SOURCE_CHOICES, default='ai')

    # Manual validation
    is_validated = models.BooleanField(default=False)
    validated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='validated_annotations'
    )
    validated_at = models.DateTimeField(null=True, blank=True)

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
        sel = (self.selected_text[:47] + '...') if len(self.selected_text) > 50 else self.selected_text
        return f"{self.annotation_type.display_name}: '{sel}'"


class UserProfile(models.Model):
    ROLE_CHOICES = [
        ('metadonneur', 'Métadonneur'),
        ('annotateur', 'Annotateur'),
        ('expert', 'Expert'),
        ('client', 'Client'),
        ('dev_metier', 'Dev métier'),  # Gardé depuis le premier modèle
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='client')
    # Nombre de documents planifiés pour le métadonneur (KPI affiché dans le dashboard)
    planned_documents = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.user.username} - {self.role}"


class AnnotationSession(models.Model):
    """Session d'annotation pour analytics."""
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
        return f"Session {self.annotator.username} – Doc #{self.document.pk}"


class AnnotationFeedback(models.Model):
    """Track human feedback for AI annotations"""
    page = models.ForeignKey(DocumentPage, on_delete=models.CASCADE, related_name='feedbacks')
    annotator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    # AI's original predictions
    ai_annotations_before = models.JSONField(help_text="AI annotations before human correction")

    # Human corrections
    human_annotations_after = models.JSONField(help_text="Final annotations after human validation")

    # Feedback analysis
    corrections_made = models.JSONField(help_text="What was corrected: additions, deletions, modifications")
    feedback_score = models.FloatField(default=0.0, help_text="Overall feedback score (0-1)")

    # Timestamps
    validated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['page', 'annotator']


class AILearningMetrics(models.Model):
    """Track AI performance over time"""
    model_version = models.CharField(max_length=50, default="groq_llama3.3_70b")

    # Performance metrics
    precision_score = models.FloatField(default=0.0)
    recall_score = models.FloatField(default=0.0)
    f1_score = models.FloatField(default=0.0)

    # Learning data
    total_feedbacks = models.IntegerField(default=0)
    improvement_rate = models.FloatField(default=0.0)

    # Entity-specific performance
    entity_performance = models.JSONField(default=dict, help_text="Performance per entity type")

    created_at = models.DateTimeField(auto_now_add=True)


class PromptOptimization(models.Model):
    """Store optimized prompts based on learning"""
    entity_type = models.CharField(max_length=100)
    optimized_prompt = models.TextField()
    performance_score = models.FloatField()
    feedback_count = models.IntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)


class CustomField(models.Model):
    name = models.CharField(max_length=100, unique=True)
    field_type = models.CharField(max_length=20, choices=[
        ('text', 'Text'),
        ('textarea', 'Long Text'),
        ('date', 'Date'),
        ('number', 'Number'),
    ], default='text')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class CustomFieldValue(models.Model):
    document = models.ForeignKey(RawDocument, on_delete=models.CASCADE)
    field = models.ForeignKey(CustomField, on_delete=models.CASCADE)
    value = models.TextField(blank=True)

    class Meta:
        unique_together = ['document', 'field']


# Classes présentes uniquement dans le premier modèle
class GlobalSummaryEditHistory(models.Model):
    """Model pour garder l'historique des modifications du résumé global"""
    document = models.ForeignKey(RawDocument, on_delete=models.CASCADE)
    old_summary = models.TextField()
    new_summary = models.TextField()
    modified_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    modified_at = models.DateTimeField(auto_now_add=True)
    reason = models.TextField(blank=True)


class MetadataFeedback(models.Model):
    document = models.ForeignKey(RawDocument, on_delete=models.CASCADE)
    metadonneur = models.ForeignKey(User, on_delete=models.CASCADE)
    ai_metadata_before = models.JSONField()
    human_metadata_after = models.JSONField()
    corrections_made = models.JSONField()
    feedback_score = models.FloatField()
    created_at = models.DateTimeField(auto_now_add=True)


class MetadataLearningMetrics(models.Model):
    field_performance = models.JSONField()
    total_feedbacks = models.IntegerField()
    avg_feedback_score = models.FloatField()
    created_at = models.DateTimeField(auto_now_add=True)