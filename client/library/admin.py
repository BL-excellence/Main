from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from .models import DocumentCategory, RegulatoryAuthority, Document, DocumentVersion, DocumentTranslation

@admin.register(DocumentCategory)
class DocumentCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'color', 'color_preview', 'documents_count']
    list_editable = ['color']
    search_fields = ['name', 'code']
    
    def color_preview(self, obj):
        return format_html(
            '<div style="width: 20px; height: 20px; background-color: {}; border-radius: 3px; border: 1px solid #ccc;"></div>',
            obj.color
        )
    color_preview.short_description = "Couleur"
    
    def documents_count(self, obj):
        return obj.document_set.count()
    documents_count.short_description = "Nb documents"

@admin.register(RegulatoryAuthority)
class RegulatoryAuthorityAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'country', 'website_link', 'documents_count']
    list_filter = ['country']
    search_fields = ['name', 'code', 'country']
    
    def website_link(self, obj):
        if obj.website:
            return format_html('<a href="{}" target="_blank">🔗 Site web</a>', obj.website)
        return "Aucun"
    website_link.short_description = "Site web"
    
    def documents_count(self, obj):
        return obj.document_set.count()
    documents_count.short_description = "Nb documents"

@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = [
        'title_short', 'document_type', 'authority', 'language',
        'validation_status', 'publication_date', 'view_count', 'file_link'
    ]
    list_filter = [
        'document_type', 'authority', 'language', 'validation_status',
        'publication_date', 'created_at', 'category'
    ]
    search_fields = ['title', 'description', 'reference_number', 'tags']
    readonly_fields = ['view_count', 'download_count', 'created_at', 'updated_at', 'file_size']
    filter_horizontal = []
    date_hierarchy = 'publication_date'
    
    def title_short(self, obj):
        return obj.title[:50] + "..." if len(obj.title) > 50 else obj.title
    title_short.short_description = "Titre"
    
    def file_link(self, obj):
        if obj.file:
            return format_html('<a href="{}" target="_blank">📄 Fichier</a>', obj.file.url)
        return "Aucun fichier"
    file_link.short_description = "Fichier"
    
    fieldsets = (
        ('Informations principales', {
            'fields': ('title', 'description', 'document_type', 'category')
        }),
        ('Source et autorité', {
            'fields': ('authority', 'source_url', 'reference_number')
        }),
        ('Fichier et langue', {
            'fields': ('file', 'file_size', 'language')
        }),
        ('Dates', {
            'fields': ('publication_date', 'effective_date', 'expiry_date')
        }),
        ('Validation', {
            'fields': ('validation_status', 'validated_by', 'validation_date', 'validation_notes')
        }),
        ('Classification', {
            'fields': ('tags', 'ctd_section', 'therapeutic_area')
        }),
        ('Métadonnées système', {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
        ('Statistiques', {
            'fields': ('view_count', 'download_count'),
            'classes': ('collapse',)
        }),
    )
    
    def save_model(self, request, obj, form, change):
        if not change:  # Si c'est un nouveau document
            obj.created_by = request.user.username
        
        # Calculer la taille du fichier si elle n'est pas définie
        if obj.file and not obj.file_size:
            try:
                obj.file_size = obj.file.size
            except:
                pass
                
        super().save_model(request, obj, form, change)

@admin.register(DocumentVersion)
class DocumentVersionAdmin(admin.ModelAdmin):
    list_display = ['document', 'version', 'created_at', 'created_by']
    list_filter = ['created_at']
    search_fields = ['document__title', 'version', 'release_notes']

@admin.register(DocumentTranslation)
class DocumentTranslationAdmin(admin.ModelAdmin):
    list_display = ['original_document', 'language', 'translation_method', 'validated', 'created_at']
    list_filter = ['language', 'translation_method', 'validated']
    search_fields = ['original_document__title', 'title']
