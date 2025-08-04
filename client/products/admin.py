from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from .models import Product, ProductSpecification, ManufacturingSite, ProductVariation

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'active_ingredient', 'dosage', 'form',
        'therapeutic_area', 'status_badge', 'specifications_count',
        'variations_count', 'created_at'
    ]
    list_filter = ['status', 'therapeutic_area', 'form', 'created_at']
    search_fields = ['name', 'active_ingredient', 'therapeutic_area']
    readonly_fields = ['created_at', 'updated_at']
    list_per_page = 25
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Informations produit', {
            'fields': ('name', 'active_ingredient', 'dosage', 'form')
        }),
        ('Classification', {
            'fields': ('therapeutic_area', 'status')
        }),
        ('Source', {
            'fields': ('source_document',)
        }),
        ('Annotations', {
            'fields': ('additional_annotations',),
            'classes': ('collapse',)
        }),
        ('Métadonnées', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def status_badge(self, obj):
        colors = {
            'commercialise': '#28a745',
            'developpement': '#ffc107',
            'arrete': '#dc3545'
        }
        color = colors.get(obj.status, '#6c757d')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; border-radius: 3px; font-size: 11px;">{}</span>',
            color, obj.get_status_display()
        )
    status_badge.short_description = "Statut"
    
    def specifications_count(self, obj):
        count = obj.specifications.count()
        return format_html('<strong>{}</strong>', count)
    specifications_count.short_description = "Spécifications"
    
    def variations_count(self, obj):
        count = obj.variations.count()
        return format_html('<strong>{}</strong>', count)
    variations_count.short_description = "Variations"

@admin.register(ProductSpecification)
class ProductSpecificationAdmin(admin.ModelAdmin):
    list_display = [
        'product', 'country_code', 'amm_number', 'approval_date',
        'renewal_date', 'documents_status', 'is_active'
    ]
    list_filter = [
        'country_code', 'is_active', 'ctd_dossier_complete',
        'gmp_certificate', 'approval_date'
    ]
    search_fields = ['product__name', 'amm_number', 'country_code']
    list_editable = ['is_active']
    date_hierarchy = 'approval_date'
    
    fieldsets = (
        ('Produit et localisation', {
            'fields': ('product', 'country_code')
        }),
        ('Autorisation', {
            'fields': ('amm_number', 'approval_date', 'renewal_date')
        }),
        ('Statut des documents', {
            'fields': (
                'ctd_dossier_complete', 'gmp_certificate',
                'inspection_report', 'rcp_etiquetage'
            )
        }),
        ('Statut', {
            'fields': ('is_active',)
        })
    )
    
    def documents_status(self, obj):
        statuses = []
        if obj.ctd_dossier_complete:
            statuses.append('<span style="color: green;">✓ CTD</span>')
        if obj.gmp_certificate:
            statuses.append('<span style="color: green;">✓ GMP</span>')
        if obj.inspection_report:
            statuses.append('<span style="color: green;">✓ Inspection</span>')
        if obj.rcp_etiquetage:
            statuses.append('<span style="color: green;">✓ RCP</span>')
        
        if not statuses:
            return '<span style="color: red;">Aucun document</span>'
        
        return mark_safe(' | '.join(statuses))
    documents_status.short_description = "Documents"
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('product')

@admin.register(ManufacturingSite)
class ManufacturingSiteAdmin(admin.ModelAdmin):
    list_display = [
        'site_name', 'product', 'country', 'city',
        'gmp_status', 'last_audit', 'audit_status'
    ]
    list_filter = ['country', 'gmp_certified', 'last_audit']
    search_fields = ['site_name', 'city', 'country', 'product__name']
    date_hierarchy = 'last_audit'
    
    fieldsets = (
        ('Site', {
            'fields': ('product', 'site_name', 'country', 'city')
        }),
        ('Certification GMP', {
            'fields': ('gmp_certified', 'gmp_expiry')
        }),
        ('Audit', {
            'fields': ('last_audit',)
        })
    )
    
    def gmp_status(self, obj):
        if obj.gmp_certified:
            if obj.gmp_expiry and obj.gmp_expiry < timezone.now().date():
                return format_html(
                    '<span style="color: orange;">⚠️ Expiré</span>'
                )
            return format_html('<span style="color: green;">✓ Certifié</span>')
        return format_html('<span style="color: red;">✗ Non certifié</span>')
    gmp_status.short_description = "GMP"
    
    def audit_status(self, obj):
        if obj.last_audit:
            from django.utils import timezone
            days_ago = (timezone.now().date() - obj.last_audit).days
            if days_ago > 365:
                return format_html(
                    '<span style="color: red;">Il y a {} jours</span>', days_ago
                )
            elif days_ago > 180:
                return format_html(
                    '<span style="color: orange;">Il y a {} jours</span>', days_ago
                )
            else:
                return format_html(
                    '<span style="color: green;">Il y a {} jours</span>', days_ago
                )
        return "Jamais audité"
    audit_status.short_description = "Dernier audit"
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('product')

@admin.register(ProductVariation)
class ProductVariationAdmin(admin.ModelAdmin):
    list_display = [
        'title', 'product', 'variation_type', 'status_badge',
        'submission_date', 'approval_date', 'processing_time'
    ]
    list_filter = ['variation_type', 'status', 'submission_date']
    search_fields = ['title', 'product__name', 'description']
    date_hierarchy = 'submission_date'
    
    fieldsets = (
        ('Variation', {
            'fields': ('product', 'variation_type', 'title', 'description')
        }),
        ('Dates', {
            'fields': ('submission_date', 'approval_date')
        }),
        ('Statut', {
            'fields': ('status',)
        }),
        ('Annotations', {
            'fields': ('additional_annotations',),
            'classes': ('collapse',)
        })
    )
    
    def status_badge(self, obj):
        colors = {
            'soumis': '#17a2b8',
            'en_cours': '#ffc107',
            'approuve': '#28a745',
            'rejete': '#dc3545'
        }
        color = colors.get(obj.status, '#6c757d')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; border-radius: 3px; font-size: 11px;">{}</span>',
            color, obj.get_status_display()
        )
    status_badge.short_description = "Statut"
    
    def processing_time(self, obj):
        if obj.approval_date and obj.submission_date:
            days = (obj.approval_date - obj.submission_date).days
            return f"{days} jours"
        elif obj.submission_date:
            from django.utils import timezone
            days = (timezone.now().date() - obj.submission_date).days
            return f"{days} jours (en cours)"
        return "N/A"
    processing_time.short_description = "Temps de traitement"
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('product')

# Import timezone for date calculations
from django.utils import timezone