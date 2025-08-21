# # Chemin d'intégration : ctd_submission/admin.py
# # Ce fichier configure l'interface d'administration Django pour l'application CTD submission
# from .utils import CTDAnalyzer, DocumentProcessor
# from .models import AIAnalysisResult
# import logging
#
# logger = logging.getLogger(__name__)
# from django.contrib import admin
# from django.utils.html import format_html
# from django.urls import reverse
# from django.utils.safestring import mark_safe
# from .models import (
#     CTDModule, CTDSection, Submission, Document,
#     TemplateField, AIAnalysisResult
# )
# from .utils import CTDAnalyzer, DocumentProcessor
#
#
# @admin.register(CTDModule)
# class CTDModuleAdmin(admin.ModelAdmin):
#     """
#     Administration des modules CTD
#     """
#     list_display = ['code', 'name', 'sections_count', 'created_at']
#     list_filter = ['created_at']
#     search_fields = ['code', 'name', 'description']
#     ordering = ['code']
#
#     def sections_count(self, obj):
#         """Compte le nombre de sections dans le module"""
#         count = obj.sections.count()
#         if count > 0:
#             url = reverse('admin:ctd_submission_ctdsection_changelist') + f'?module__id__exact={obj.id}'
#             return format_html('<a href="{}">{} sections</a>', url, count)
#         return '0 sections'
#
#     sections_count.short_description = 'Sections'
#
#     def get_readonly_fields(self, request, obj=None):
#         """Rendre le code en lecture seule après création"""
#         if obj:  # Si l'objet existe déjà
#             return ['code']
#         return []
#
#
# @admin.register(CTDSection)
# class CTDSectionAdmin(admin.ModelAdmin):
#     """
#     Administration des sections CTD
#     """
#     list_display = ['full_code', 'name', 'module', 'documents_count', 'order']
#     list_filter = ['module', 'created_at']
#     search_fields = ['code', 'name', 'description']
#     ordering = ['module', 'order', 'code']
#     list_editable = ['order']
#
#     def full_code(self, obj):
#         """Affiche le code complet de la section"""
#         return f"{obj.module.code}.{obj.code}"
#
#     full_code.short_description = 'Code complet'
#     full_code.admin_order_field = 'code'
#
#     def documents_count(self, obj):
#         """Compte le nombre de documents dans la section"""
#         count = obj.documents.count()
#         if count > 0:
#             url = reverse('admin:ctd_submission_document_changelist') + f'?section__id__exact={obj.id}'
#             return format_html('<a href="{}">{} documents</a>', url, count)
#         return '0 documents'
#
#     documents_count.short_description = 'Documents'
#
#     fieldsets = (
#         ('Informations de base', {
#             'fields': ('module', 'code', 'name', 'order')
#         }),
#         ('Description', {
#             'fields': ('description',),
#             'classes': ('collapse',)
#         }),
#         ('Hiérarchie', {
#             'fields': ('parent_section',),
#             'classes': ('collapse',)
#         })
#     )
#
#
# @admin.register(Submission)
# class SubmissionAdmin(admin.ModelAdmin):
#     """
#     Administration des soumissions CTD
#     """
#     list_display = ['name', 'region_flag', 'submission_type', 'status_badge', 'created_by', 'created_at',
#                     'documents_count']
#     list_filter = ['region', 'status', 'created_at', 'submission_type']
#     search_fields = ['name', 'submission_type', 'created_by__username']
#     ordering = ['-created_at']
#     readonly_fields = ['created_at', 'updated_at']
#
#     def region_flag(self, obj):
#         """Affiche un drapeau selon la région"""
#         flags = {
#             'EU': '🇪🇺',
#             'US': '🇺🇸',
#             'CA': '🇨🇦',
#             'UK': '🇬🇧'
#         }
#         flag = flags.get(obj.region, '🏳️')
#         return format_html('<span title="{}">{} {}</span>',
#                            obj.get_region_display(), flag, obj.region)
#
#     region_flag.short_description = 'Région'
#
#     def status_badge(self, obj):
#         """Affiche un badge coloré pour le statut"""
#         colors = {
#             'draft': '#ffc107',
#             'in_progress': '#17a2b8',
#             'completed': '#28a745',
#             'submitted': '#6f42c1'
#         }
#         color = colors.get(obj.status, '#6c757d')
#         return format_html(
#             '<span style="background-color: {}; color: white; padding: 3px 8px; border-radius: 10px; font-size: 0.8em;">{}</span>',
#             color, obj.get_status_display()
#         )
#
#     status_badge.short_description = 'Statut'
#
#     def documents_count(self, obj):
#         """Compte le nombre de documents dans la soumission"""
#         count = obj.documents.count()
#         if count > 0:
#             url = reverse('admin:ctd_submission_document_changelist') + f'?submission__id__exact={obj.id}'
#             return format_html('<a href="{}">{} documents</a>', url, count)
#         return '0 documents'
#
#     documents_count.short_description = 'Documents'
#
#     fieldsets = (
#         ('Informations de base', {
#             'fields': ('name', 'region', 'status')
#         }),
#         ('Type de soumission', {
#             'fields': ('submission_type', 'variation_type', 'change_description')
#         }),
#         ('Métadonnées', {
#             'fields': ('created_by', 'created_at', 'updated_at'),
#             'classes': ('collapse',)
#         })
#     )
#
#     def get_readonly_fields(self, request, obj=None):
#         readonly = ['created_at', 'updated_at']
#         if obj and not request.user.is_superuser:
#             readonly.append('created_by')
#         return readonly
#
#     def save_model(self, request, obj, form, change):
#         """Définir l'utilisateur créateur automatiquement"""
#         if not change:  # Si c'est une création
#             obj.created_by = request.user
#         super().save_model(request, obj, form, change)
#
#
# @admin.register(Document)
# class DocumentAdmin(admin.ModelAdmin):
#     """
#     Administration des documents
#     """
#     list_display = ['name', 'document_type_icon', 'submission_link', 'section_link','section','display_section_debug', 'ai_confidence', 'created_at']
#     list_filter = ['document_type', 'submission__region', 'section__module', 'is_template_generated', 'created_at']
#     search_fields = ['name', 'submission__name', 'section__name']
#     ordering = ['-created_at']
#     readonly_fields = ['created_at', 'updated_at', 'ai_analysis_summary']
#
#     def __init__(self, *args, **kwargs):
#         super().__init__(*args, **kwargs)
#         self.ctd_analyzer = CTDAnalyzer()
#         self.document_processor = DocumentProcessor()
#
#     # Correction dans admin.py - Méthode save_model mise à jour
#
#     def save_model(self, request, obj, form, change):
#         """
#         Déclenche l'analyse IA automatiquement lors de la sauvegarde
#         et met à jour la section suggérée
#         """
#         # Sauvegarder d'abord le document
#         super().save_model(request, obj, form, change)
#
#         # Vérifier s'il faut faire l'analyse automatique
#         should_analyze = (
#                 not obj.section and  # Pas encore de section assignée
#                 obj.file and  # A un fichier
#                 not change  # C'est une création (pas une modification)
#         )
#
#         if should_analyze:
#             try:
#                 # Extraire le contenu du document d'abord
#                 self._extract_document_content(obj)
#
#                 # Effectuer l'analyse IA avec votre analyseur avancé
#                 analysis_result = self.ctd_analyzer.analyze_document(obj)
#
#                 if analysis_result and analysis_result.get('confidence', 0) > 0.6:
#                     # CORRECTION : Récupérer la section correctement
#                     suggested_section = analysis_result.get('section')
#
#                     if suggested_section:
#                         # Assigner la section suggérée
#                         obj.section = suggested_section
#                         obj.save(update_fields=['section'])
#
#                         # Créer ou mettre à jour le résultat d'analyse IA
#                         self._save_analysis_result(obj, analysis_result)
#
#                         # Message de succès pour l'admin
#                         confidence_pct = analysis_result['confidence'] * 100
#                         self.message_user(
#                             request,
#                             f"✅ Section automatiquement assignée: {analysis_result['module'].code}.{suggested_section.code} - {suggested_section.name} "
#                             f"(Confiance: {confidence_pct:.1f}%)",
#                             level='SUCCESS'
#                         )
#                     else:
#                         logger.error(f"Section suggérée introuvable dans le résultat d'analyse pour {obj.name}")
#                         self.message_user(
#                             request,
#                             "❌ Erreur: Section suggérée introuvable dans le résultat d'analyse",
#                             level='ERROR'
#                         )
#                 else:
#                     confidence_pct = analysis_result.get('confidence', 0) * 100 if analysis_result else 0
#                     self.message_user(
#                         request,
#                         f"⚠️ Analyse IA effectuée mais confiance insuffisante ({confidence_pct:.1f}%). "
#                         "Veuillez vérifier et assigner manuellement.",
#                         level='WARNING'
#                     )
#
#             except Exception as e:
#                 # En cas d'erreur, juste log et continuer
#                 logger.error(f"Erreur lors de l'analyse automatique du document {obj.name}: {e}")
#                 self.message_user(
#                     request,
#                     f"❌ Erreur lors de l'analyse automatique: {str(e)}",
#                     level='ERROR'
#                 )
#
#     def force_ai_analysis(self, request, queryset):
#         """
#         Action admin pour forcer l'analyse IA sur des documents sélectionnés
#         """
#         success_count = 0
#         error_count = 0
#
#         for document in queryset:
#             try:
#                 # Extraire le contenu si nécessaire
#                 self._extract_document_content(document)
#
#                 # Effectuer l'analyse
#                 analysis_result = self.ctd_analyzer.analyze_document(document)
#
#                 if analysis_result and analysis_result.get('confidence', 0) > 0.6:
#                     suggested_section = analysis_result.get('section')
#                     if suggested_section:
#                         # Assigner la section (même si elle existe déjà)
#                         document.section = suggested_section
#                         document.save(update_fields=['section'])
#
#                         # Sauvegarder le résultat d'analyse
#                         self._save_analysis_result(document, analysis_result)
#
#                         success_count += 1
#                     else:
#                         error_count += 1
#                 else:
#                     error_count += 1
#
#             except Exception as e:
#                 logger.error(f"Erreur lors de l'analyse forcée pour {document.name}: {e}")
#                 error_count += 1
#
#         if success_count > 0:
#             self.message_user(
#                 request,
#                 f"✅ {success_count} document(s) analysé(s) et section(s) assignée(s) avec succès.",
#                 level='SUCCESS'
#             )
#
#         if error_count > 0:
#             self.message_user(
#                 request,
#                 f"⚠️ {error_count} document(s) n'ont pas pu être analysés correctement.",
#                 level='WARNING'
#             )
#
#     force_ai_analysis.short_description = "🤖 Forcer l'analyse IA et assigner les sections"
#
#     # Ajoutez cette action à la classe DocumentAdmin
#     actions = ['force_ai_analysis']
#     def _extract_document_content(self, document):
#         """
#         Extrait le contenu du document si ce n'est pas déjà fait
#         """
#         try:
#             if not document.content_extracted or not document.content_extracted.get('extracted', False):
#                 logger.info(f"Extraction du contenu pour: {document.name}")
#                 extracted_content = self.document_processor.extract_content(document)
#
#                 if extracted_content and extracted_content.get('extracted', False):
#                     document.content_extracted = extracted_content
#                     document.save(update_fields=['content_extracted'])
#                     logger.info(f"Contenu extrait avec succès pour: {document.name}")
#                 else:
#                     logger.warning(f"Échec de l'extraction pour: {document.name}")
#                     # Utiliser au moins le nom du fichier
#                     document.content_extracted = {
#                         'text': document.name,
#                         'extracted': False,
#                         'fallback': True
#                     }
#                     document.save(update_fields=['content_extracted'])
#
#         except Exception as e:
#             logger.error(f"Erreur lors de l'extraction du contenu pour {document.name}: {e}")
#             # Fallback : utiliser le nom du fichier
#             document.content_extracted = {
#                 'text': document.name,
#                 'extracted': False,
#                 'error': str(e)
#             }
#             document.save(update_fields=['content_extracted'])
#
#     def _save_analysis_result(self, document, analysis_result):
#         """
#         Sauvegarde le résultat de l'analyse IA dans la base de données
#         """
#         try:
#             # Créer ou mettre à jour le résultat d'analyse
#             ai_analysis, created = AIAnalysisResult.objects.get_or_create(
#                 document=document,
#                 defaults={
#                     'suggested_module': analysis_result['module'],
#                     'suggested_section': analysis_result['section'],
#                     'confidence_score': analysis_result['confidence'],
#                     'analysis_details': analysis_result.get('details', {}),
#                     'keywords_found': analysis_result.get('keywords', [])
#                 }
#             )
#
#             if not created:
#                 # Mettre à jour si existe déjà
#                 ai_analysis.suggested_module = analysis_result['module']
#                 ai_analysis.suggested_section = analysis_result['section']
#                 ai_analysis.confidence_score = analysis_result['confidence']
#                 ai_analysis.analysis_details = analysis_result.get('details', {})
#                 ai_analysis.keywords_found = analysis_result.get('keywords', [])
#                 ai_analysis.save()
#
#             logger.info(f"Résultat d'analyse sauvegardé pour: {document.name}")
#
#         except Exception as e:
#             logger.error(f"Erreur lors de la sauvegarde du résultat d'analyse pour {document.name}: {e}")
#
#     def document_type_icon(self, obj):
#         """Affiche une icône selon le type de document"""
#         icons = {
#             'pdf': ('📄', '#dc3545'),
#             'docx': ('📘', '#0d6efd'),
#             'xlsx': ('📊', '#198754'),
#             'form': ('📝', '#6f42c1')
#         }
#         icon, color = icons.get(obj.document_type, ('📎', '#6c757d'))
#         return format_html('<span style="color: {}; font-size: 1.2em;" title="{}">{}</span>',
#                            color, obj.get_document_type_display(), icon)
#
#     document_type_icon.short_description = 'Type'
#
#     def submission_link(self, obj):
#         """Lien vers la soumission"""
#         url = reverse('admin:ctd_submission_submission_change', args=[obj.submission.id])
#         return format_html('<a href="{}">{}</a>', url, obj.submission.name)
#
#     submission_link.short_description = 'Soumission'
#
#     def section_link(self, obj):
#         """Lien vers la section CTD"""
#         if obj.section:
#             url = reverse('admin:ctd_submission_ctdsection_change', args=[obj.section.id])
#             return format_html('<a href="{}">{}.{} {}</a>',
#                                url, obj.section.module.code, obj.section.code, obj.section.name)
#         return '-'
#
#     section_link.short_description = 'Section CTD'
#
#     def ai_confidence(self, obj):
#         """Affiche la confiance de l'analyse IA"""
#         if hasattr(obj, 'ai_analysis') and obj.ai_analysis:
#             confidence = obj.ai_analysis.confidence_score
#             if confidence >= 0.8:
#                 color = '#28a745'  # Vert
#             elif confidence >= 0.6:
#                 color = '#ffc107'  # Jaune
#             else:
#                 color = '#dc3545'  # Rouge
#
#             # Convertir manuellement en pourcentage
#             confidence_str = f"{confidence * 100:.1f}%"
#             return format_html(
#                 '<span style="color: {}; font-weight: bold;">{}</span>',
#                 color, confidence_str
#             )
#         return '-'
#
#     ai_confidence.short_description = 'IA Confiance'
#
#     def ai_analysis_summary(self, obj):
#         """Résumé de l'analyse IA"""
#         if hasattr(obj, 'ai_analysis') and obj.ai_analysis:
#             analysis = obj.ai_analysis
#             html = f"""
#             <div style="background: #f8f9fa; padding: 10px; border-radius: 5px;">
#                 <strong>Module suggéré:</strong> {analysis.suggested_module.name}<br>
#                 <strong>Section suggérée:</strong> {analysis.suggested_section.name}<br>
#                 <strong>Confiance:</strong> {analysis.confidence_score:.1%}<br>
#                 <strong>Mots-clés trouvés:</strong> {', '.join(analysis.keywords_found[:5])}
#             </div>
#             """
#             return mark_safe(html)
#         return "Aucune analyse IA disponible"
#
#     ai_analysis_summary.short_description = 'Analyse IA'
#
#     fieldsets = (
#         ('Informations de base', {
#             'fields': ('name', 'file', 'document_type')
#         }),
#         ('Classification', {
#             'fields': ('submission', 'section')
#         }),
#         ('Traitement', {
#             'fields': ('is_template_generated', 'content_extracted', 'template_data'),
#             'classes': ('collapse',)
#         }),
#         ('Analyse IA', {
#             'fields': ('ai_analysis_summary',),
#             'classes': ('collapse',)
#         }),
#         ('Métadonnées', {
#             'fields': ('created_at', 'updated_at'),
#             'classes': ('collapse',)
#         })
#     )
#
#     def display_section_debug(self, obj):
#         if obj.section:
#             return f"{obj.section.id} - {obj.section.module.code}.{obj.section.code}"
#         return "❌ None"
#
#     display_section_debug.short_description = "Section (Debug)"
#
#
#
#
# @admin.register(TemplateField)
# class TemplateFieldAdmin(admin.ModelAdmin):
#     """
#     Administration des champs de template
#     """
#     list_display = ['field_label', 'document_link', 'field_type', 'is_required', 'position']
#     list_filter = ['field_type', 'is_required', 'document__document_type']
#     search_fields = ['field_name', 'field_label', 'document__name']
#     ordering = ['document', 'row_number', 'column_number']
#
#     def document_link(self, obj):
#         """Lien vers le document"""
#         url = reverse('admin:ctd_submission_document_change', args=[obj.document.id])
#         return format_html('<a href="{}">{}</a>', url, obj.document.name)
#
#     document_link.short_description = 'Document'
#
#     def position(self, obj):
#         """Position du champ dans le template"""
#         return f"Ligne {obj.row_number}, Col {obj.column_number}"
#
#     position.short_description = 'Position'
#
#     fieldsets = (
#         ('Informations de base', {
#             'fields': ('document', 'field_name', 'field_label', 'field_type')
#         }),
#         ('Configuration', {
#             'fields': ('field_value', 'field_options', 'is_required')
#         }),
#         ('Position', {
#             'fields': ('row_number', 'column_number'),
#             'classes': ('collapse',)
#         })
#     )
#
#
# @admin.register(AIAnalysisResult)
# class AIAnalysisResultAdmin(admin.ModelAdmin):
#     """
#     Administration des résultats d'analyse IA
#     """
#     list_display = ['document_name', 'suggested_classification', 'confidence_badge', 'created_at']
#     list_filter = ['suggested_module', 'confidence_score', 'created_at']
#     search_fields = ['document__name', 'suggested_module__name', 'suggested_section__name']
#     ordering = ['-created_at']
#     readonly_fields = ['created_at', 'analysis_details_formatted', 'keywords_display']
#
#     def document_name(self, obj):
#         """Nom du document analysé"""
#         url = reverse('admin:ctd_submission_document_change', args=[obj.document.id])
#         return format_html('<a href="{}">{}</a>', url, obj.document.name)
#
#     document_name.short_description = 'Document'
#
#     def suggested_classification(self, obj):
#         """Classification suggérée"""
#         return f"{obj.suggested_module.code} → {obj.suggested_section.code} {obj.suggested_section.name}"
#
#     suggested_classification.short_description = 'Classification suggérée'
#
#     def confidence_badge(self, obj):
#         """Badge de confiance coloré"""
#         confidence = obj.confidence_score
#         if confidence >= 0.8:
#             color = '#28a745'
#             label = 'Élevée'
#         elif confidence >= 0.6:
#             color = '#ffc107'
#             label = 'Moyenne'
#         else:
#             color = '#dc3545'
#             label = 'Faible'
#
#         confidence_str = f"{confidence * 100:.1f}%"  # transforme le float en string sécurisée
#         return format_html(
#             '<span style="background-color: {}; color: white; padding: 3px 8px; border-radius: 10px; font-size: 0.8em;">{} ({})</span>',
#             color, label, confidence_str
#         )
#
#     confidence_badge.short_description = 'Confiance'
#
#     def analysis_details_formatted(self, obj):
#         """Détails de l'analyse formatés"""
#         if obj.analysis_details:
#             html = "<ul>"
#             for key, value in obj.analysis_details.items():
#                 html += f"<li><strong>{key}:</strong> {value}</li>"
#             html += "</ul>"
#             return mark_safe(html)
#         return "Aucun détail disponible"
#
#     analysis_details_formatted.short_description = 'Détails de l\'analyse'
#
#     def keywords_display(self, obj):
#         """Affichage des mots-clés"""
#         if obj.keywords_found:
#             keywords_html = ""
#             for keyword in obj.keywords_found[:10]:  # Limiter à 10 mots-clés
#                 keywords_html += f'<span style="background: #e9ecef; padding: 2px 6px; margin: 2px; border-radius: 3px; font-size: 0.8em;">{keyword}</span> '
#             return mark_safe(keywords_html)
#         return "Aucun mot-clé identifié"
#
#     keywords_display.short_description = 'Mots-clés identifiés'
#
#     fieldsets = (
#         ('Document analysé', {
#             'fields': ('document',)
#         }),
#         ('Résultats de l\'analyse', {
#             'fields': ('suggested_module', 'suggested_section', 'confidence_score')
#         }),
#         ('Détails', {
#             'fields': ('analysis_details_formatted', 'keywords_display'),
#             'classes': ('collapse',)
#         }),
#         ('Métadonnées', {
#             'fields': ('created_at',),
#             'classes': ('collapse',)
#         })
#     )
#
#     def has_add_permission(self, request):
#         """Empêcher la création manuelle d'analyses IA"""
#         return False
#
#
# # Configuration globale de l'administration
# admin.site.site_header = "CTD Submission System - Administration"
# admin.site.site_title = "CTD Admin"
# admin.site.index_title = "Gestion des Soumissions CTD"