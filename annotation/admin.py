# annotation/admin.py
from django.contrib import admin
from .models import Annotation, EntityType


@admin.register(EntityType)
class EntityTypeAdmin(admin.ModelAdmin):
    """Administration des types d'entités"""

    list_display = ('name', 'color', 'description')
    search_fields = ('name', 'description')
    list_filter = ('name',)

    fieldsets = (
        ('Informations générales', {
            'fields': ('name', 'description')
        }),
        ('Apparence', {
            'fields': ('color',)
        })
    )


@admin.register(Annotation)
class AnnotationAdmin(admin.ModelAdmin):
    """Administration des annotations"""

    list_display = ('text', 'entity_type', 'document', 'status', 'created_by', 'created_at')
    list_filter = ('entity_type', 'status', 'is_automatic', 'created_at')
    search_fields = ('text', 'document__title', 'created_by__username')
    readonly_fields = ('created_at', 'updated_at')

    fieldsets = (
        ('Annotation', {
            'fields': ('document', 'text', 'entity_type', 'start_position', 'end_position')
        }),
        ('Statut', {
            'fields': ('status', 'confidence_score', 'is_automatic')
        }),
        ('Utilisateurs', {
            'fields': ('created_by', 'validated_by')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )

    def get_readonly_fields(self, request, obj=None):
        readonly_fields = list(super().get_readonly_fields(request, obj))
        if obj:  # En mode édition
            readonly_fields.extend(['document', 'created_by'])
        return readonly_fields
