# documents/admin.py
from django.contrib import admin
from .models import Document, DocumentType, DocumentContext


@admin.register(DocumentType)
class DocumentTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'description', 'color')
    search_fields = ('name',)
    list_per_page = 25


@admin.register(DocumentContext)
class DocumentContextAdmin(admin.ModelAdmin):
    list_display = ('name', 'description', 'color')
    search_fields = ('name',)
    list_per_page = 25


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ('title', 'document_type', 'context', 'status', 'assigned_to', 'created_at')
    list_filter = ('status', 'document_type', 'context', 'created_at', 'language')
    search_fields = ('title', 'extracted_title', 'source')
    readonly_fields = ('created_at', 'updated_at', 'extraction_started_at', 'extraction_completed_at')
    list_per_page = 25
    date_hierarchy = 'created_at'

    fieldsets = (
        ('Informations principales', {
            'fields': ('title', 'file', 'file_type', 'document_type', 'context', 'status')
        }),
        ('Métadonnées extraites', {
            'fields': ('extracted_title', 'language', 'source', 'version', 'source_url'),
            'classes': ('collapse',)
        }),
        ('Dates EMA', {
            'fields': ('original_publication_date', 'ema_publication_date'),
            'classes': ('collapse',)
        }),
        ('Données EMA', {
            'fields': ('ema_title', 'ema_reference', 'ema_source_url'),
            'classes': ('collapse',)
        }),
        ('Assignations', {
            'fields': ('assigned_to', 'validated_by')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at', 'extraction_started_at', 'extraction_completed_at'),
            'classes': ('collapse',)
        })
    )

    def get_queryset(self, request):
        """Optimiser les requêtes avec select_related"""
        return super().get_queryset(request).select_related(
            'document_type', 'context', 'assigned_to', 'validated_by'
        )

    def save_model(self, request, obj, form, change):
        """Assigner automatiquement le créateur si pas déjà assigné"""
        if not change and not obj.assigned_to:
            obj.assigned_to = request.user
        super().save_model(request, obj, form, change)

    actions = ['mark_as_uploaded', 'mark_as_extracted', 'mark_as_validated']

    def mark_as_uploaded(self, request, queryset):
        """Action pour marquer comme uploadé"""
        updated = queryset.update(status='uploaded')
        self.message_user(request, f'{updated} document(s) marqué(s) comme uploadé(s).')
    mark_as_uploaded.short_description = "Marquer comme uploadé"

    def mark_as_extracted(self, request, queryset):
        """Action pour marquer comme extrait"""
        updated = queryset.update(status='extracted')
        self.message_user(request, f'{updated} document(s) marqué(s) comme extrait(s).')
    mark_as_extracted.short_description = "Marquer comme extrait"

    def mark_as_validated(self, request, queryset):
        """Action pour marquer comme validé"""
        updated = queryset.update(status='validated')
        self.message_user(request, f'{updated} document(s) marqué(s) comme validé(s).')
    mark_as_validated.short_description = "Marquer comme validé"