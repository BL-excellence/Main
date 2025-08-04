from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from .models import (
    RawDocument, MetadataLog, DocumentPage, AnnotationType, 
    Annotation, AnnotationSession, AnnotationFeedback, 
    AILearningMetrics, PromptOptimization, UserProfile
)

@admin.register(RawDocument)
class RawDocumentAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'title_display', 'source', 'doc_type', 'owner', 
        'is_validated', 'created_at', 'file_link', 'pages_count'
    ]
    list_filter = [
        'source', 'doc_type', 'is_validated', 'is_ready_for_expert', 
        'pages_extracted', 'created_at', 'country', 'language'
    ]
    search_fields = ['title', 'source', 'doc_type', 'owner__username', 'context']
    readonly_fields = [
        'created_at', 'validated_at', 'expert_ready_at', 'total_pages'
    ]
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Informations principales', {
            'fields': ('title', 'doc_type', 'source', 'owner')
        }),
        ('Fichier', {
            'fields': ('url', 'file')
        }),
        ('Métadonnées extraites', {
            'fields': (
                'publication_date', 'version', 'context', 
                'country', 'language', 'url_source'
            )
        }),
        ('Statut', {
            'fields': (
                'is_validated', 'validated_at', 
                'is_ready_for_expert', 'expert_ready_at'
            )
        }),
        ('Pages', {
            'fields': ('total_pages', 'pages_extracted'),
            'classes': ('collapse',)
        }),
        ('Dates', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )
    
    def title_display(self, obj):
        """Affiche le titre avec une longueur limitée"""
        if obj.title:
            return obj.title[:50] + "..." if len(obj.title) > 50 else obj.title
        return "Sans titre"
    title_display.short_description = "Titre"
    
    def file_link(self, obj):
        """Lien vers le fichier"""
        if obj.file:
            return format_html(
                '<a href="{}" target="_blank">📄 Voir fichier</a>',
                obj.file.url
            )
        elif obj.url:
            return format_html(
                '<a href="{}" target="_blank">🔗 URL source</a>',
                obj.url
            )
        return "Aucun fichier"
    file_link.short_description = "Fichier"
    
    def pages_count(self, obj):
        """Nombre de pages extraites"""
        if obj.pages_extracted:
            return f"{obj.total_pages} pages"
        return "Non extrait"
    pages_count.short_description = "Pages"
    
    actions = ['mark_as_validated', 'mark_as_ready_for_expert']
    
    def mark_as_validated(self, request, queryset):
        """Action pour marquer comme validé"""
        from django.utils import timezone
        updated = queryset.update(
            is_validated=True, 
            validated_at=timezone.now()
        )
        self.message_user(request, f"{updated} document(s) marqué(s) comme validé(s).")
    mark_as_validated.short_description = "Marquer comme validé"
    
    def mark_as_ready_for_expert(self, request, queryset):
        """Action pour marquer comme prêt pour expert"""
        from django.utils import timezone
        updated = queryset.update(
            is_ready_for_expert=True, 
            expert_ready_at=timezone.now()
        )
        self.message_user(request, f"{updated} document(s) marqué(s) comme prêt pour expert.")
    mark_as_ready_for_expert.short_description = "Marquer comme prêt pour expert"

@admin.register(MetadataLog)
class MetadataLogAdmin(admin.ModelAdmin):
    list_display = ['document', 'field_name', 'old_value_short', 'new_value_short', 'modified_by', 'modified_at']
    list_filter = ['field_name', 'modified_at', 'modified_by']
    search_fields = ['document__title', 'field_name', 'old_value', 'new_value']
    readonly_fields = ['modified_at']
    
    def old_value_short(self, obj):
        if obj.old_value:
            return obj.old_value[:30] + "..." if len(obj.old_value) > 30 else obj.old_value
        return "Vide"
    old_value_short.short_description = "Ancienne valeur"
    
    def new_value_short(self, obj):
        if obj.new_value:
            return obj.new_value[:30] + "..." if len(obj.new_value) > 30 else obj.new_value
        return "Vide"
    new_value_short.short_description = "Nouvelle valeur"

@admin.register(DocumentPage)
class DocumentPageAdmin(admin.ModelAdmin):
    list_display = ['document', 'page_number', 'is_annotated', 'is_validated_by_human', 'annotated_by', 'created_at']
    list_filter = ['is_annotated', 'is_validated_by_human', 'created_at']
    search_fields = ['document__title', 'raw_text', 'cleaned_text']
    readonly_fields = ['created_at', 'annotated_at', 'human_validated_at']
    
    fieldsets = (
        ('Page', {
            'fields': ('document', 'page_number')
        }),
        ('Contenu', {
            'fields': ('raw_text', 'cleaned_text'),
            'classes': ('collapse',)
        }),
        ('Annotation', {
            'fields': ('is_annotated', 'annotated_at', 'annotated_by')
        }),
        ('Validation', {
            'fields': ('is_validated_by_human', 'human_validated_at', 'validated_by')
        }),
    )

@admin.register(AnnotationType)
class AnnotationTypeAdmin(admin.ModelAdmin):
    list_display = ['name', 'display_name', 'color_preview', 'created_at']
    list_editable = ['display_name']
    search_fields = ['name', 'display_name', 'description']
    
    def color_preview(self, obj):
        return format_html(
            '<div style="width: 20px; height: 20px; background-color: {}; border-radius: 3px;"></div>',
            obj.color
        )
    color_preview.short_description = "Couleur"

@admin.register(Annotation)
class AnnotationAdmin(admin.ModelAdmin):
    list_display = ['page', 'annotation_type', 'selected_text_short', 'confidence_score', 'validation_status', 'source']
    list_filter = ['annotation_type', 'validation_status', 'source', 'is_validated']
    search_fields = ['selected_text', 'ai_reasoning']
    readonly_fields = ['created_at', 'validated_at']
    
    def selected_text_short(self, obj):
        return obj.selected_text[:40] + "..." if len(obj.selected_text) > 40 else obj.selected_text
    selected_text_short.short_description = "Texte sélectionné"

@admin.register(AnnotationSession)
class AnnotationSessionAdmin(admin.ModelAdmin):
    list_display = ['document', 'annotator', 'total_annotations', 'pages_annotated', 'duration_minutes', 'started_at']
    list_filter = ['started_at', 'finished_at']
    search_fields = ['document__title', 'annotator__username']
    readonly_fields = ['started_at', 'finished_at']

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'role']
    list_filter = ['role']
    search_fields = ['user__username', 'user__email']

@admin.register(AnnotationFeedback)
class AnnotationFeedbackAdmin(admin.ModelAdmin):
    list_display = ['page', 'annotator', 'feedback_score', 'validated_at']
    list_filter = ['feedback_score', 'validated_at']
    search_fields = ['page__document__title', 'annotator__username']
    readonly_fields = ['validated_at']

@admin.register(AILearningMetrics)
class AILearningMetricsAdmin(admin.ModelAdmin):
    list_display = ['model_version', 'precision_score', 'recall_score', 'f1_score', 'total_feedbacks', 'created_at']
    list_filter = ['model_version', 'created_at']
    readonly_fields = ['created_at']

@admin.register(PromptOptimization)
class PromptOptimizationAdmin(admin.ModelAdmin):
    list_display = ['entity_type', 'performance_score', 'feedback_count', 'is_active', 'created_at']
    list_filter = ['entity_type', 'is_active', 'created_at']
    search_fields = ['entity_type', 'optimized_prompt']
    readonly_fields = ['created_at']

# Configuration de l'admin site
admin.site.site_header = "Administration RegX Platform"
admin.site.site_title = "RegX Admin"
admin.site.index_title = "Gestion des Documents et Métadonnées"
