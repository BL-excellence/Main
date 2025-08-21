# # # # Chemin d'intégration : ctd_submission/urls.py
# # # # Ce fichier définit toutes les URLs de l'application CTD submission
# # #
# # # from django.urls import path
# # # from . import views
# # #
# # # app_name = 'ctd_submission'
# # #
# # # urlpatterns = [
# # #     # Dashboard principal
# # #     path('', views.dashboard, name='dashboard'),
# # #
# # #     # Gestion des soumissions
# # #     path('submission/create/', views.submission_create, name='submission_create'),
# # #     path('submission/<int:submission_id>/', views.submission_detail, name='submission_detail'),
# # #     path('submission/<int:submission_id>/edit/', views.submission_edit, name='submission_edit'),
# # #     path('submission/<int:submission_id>/delete/', views.submission_delete, name='submission_delete'),
# # #     path('submission/<int:submission_id>/export/', views.submission_export, name='submission_export'),
# # #
# # #     # Upload et gestion des documents
# # #     path('document/upload/', views.document_upload, name='document_upload'),
# # #     path('document/<int:document_id>/view/', views.document_view, name='document_view'),
# # #     path('document/<int:document_id>/template/', views.document_template, name='document_template'),
# # #     path('document/<int:document_id>/download/', views.document_download, name='document_download'),
# # #     path('document/<int:document_id>/delete/', views.document_delete, name='document_delete'),
# # #
# # #     # Génération de structure CTD intelligente
# # #     path('generate-ctd-structure/', views.generate_ctd_structure, name='generate_ctd_structure'),
# # #     path('initialize-ctd-modules/', views.initialize_ctd_modules, name='initialize_ctd_modules'),
# # #
# # #     # Gestion des templates
# # #     path('template/<int:document_id>/add-column/', views.template_add_column, name='template_add_column'),
# # #     path('template/<int:document_id>/add-row/', views.template_add_row, name='template_add_row'),
# # #     path('template/field/<int:field_id>/delete/', views.template_delete_field, name='template_delete_field'),
# # #     path('template/field/<int:field_id>/edit/', views.template_edit_field, name='template_edit_field'),
# # #
# # #     # API pour l'analyse IA
# # #     path('api/analyze-document/<int:document_id>/', views.api_analyze_document, name='api_analyze_document'),
# # #     path('api/extract-content/<int:document_id>/', views.api_extract_content, name='api_extract_content'),
# # #     path('api/update-template/<int:document_id>/', views.api_update_template, name='api_update_template'),
# # #
# # #     # Rapports et statistiques
# # #     path('reports/', views.reports_dashboard, name='reports_dashboard'),
# # #     path('reports/submission/<int:submission_id>/', views.submission_report, name='submission_report'),
# # #     path('reports/export/<int:submission_id>/', views.export_submission_report, name='export_submission_report'),
# # #
# # #     # Administration des modules CTD
# # #     path('admin/modules/', views.admin_modules, name='admin_modules'),
# # #     path('admin/modules/<int:module_id>/sections/', views.admin_sections, name='admin_sections'),
# # #     path('admin/sections/create/', views.admin_section_create, name='admin_section_create'),
# # #     path('admin/sections/<int:section_id>/edit/', views.admin_section_edit, name='admin_section_edit'),
# # #
# # #     # Assistant IA et aide
# # #     path('assistant/', views.ai_assistant, name='ai_assistant'),
# # #     path('help/', views.help_center, name='help_center'),
# # #     path('help/templates/', views.help_templates, name='help_templates'),
# # #
# # #     # Import/Export
# # #     path('import/submission/', views.import_submission, name='import_submission'),
# # #     path('export/template/<int:document_id>/', views.export_template, name='export_template'),
# # #     path('import/template/<int:document_id>/', views.import_template, name='import_template'),
# # # ]
# # #
# # # # URLs pour les API AJAX (préfixées par 'ajax/')
# # # ajax_urlpatterns = [
# # #     path('ajax/search-documents/', views.ajax_search_documents, name='ajax_search_documents'),
# # #     path('ajax/validate-template/', views.ajax_validate_template, name='ajax_validate_template'),
# # #     path('ajax/auto-save-template/', views.ajax_auto_save_template, name='ajax_auto_save_template'),
# # #     path('ajax/suggest-classification/', views.ajax_suggest_classification, name='ajax_suggest_classification'),
# # #     path('ajax/get-submission-status/', views.ajax_get_submission_status, name='ajax_get_submission_status'),
# # # ]
# # #
# # # # Ajouter les URLs AJAX au pattern principal
# # # urlpatterns += ajax_urlpatterns
# # #
# # # # Ajout à ctd_submission/urls.py - URLs pour l'éditeur avancé
# # #
# # # # Ajouter ces URLs au fichier existant
# # #
# # # urlpatterns += [
# # #     # Éditeur avancé avec Copilot
# # #     path('document/<int:document_id>/advanced-editor/', views.document_advanced_editor,
# # #          name='document_advanced_editor'),
# # #     path('document/<int:document_id>/save-changes/', views.document_save_changes, name='document_save_changes'),
# # #     path('document/<int:document_id>/export-modified/', views.document_export_modified,
# # #          name='document_export_modified'),
# # #
# # #     # API Copilot intelligent
# # #     path('copilot-suggestions/<int:document_id>/', views.copilot_suggestions, name='copilot_suggestions'),
# # #     path('apply-template-to-editor/<int:document_id>/', views.apply_template_to_editor,
# # #          name='apply_template_to_editor'),
# # #
# # #     # Fonctionnalités avancées d'édition
# # #     path('document/<int:document_id>/validate-content/', views.validate_document_content,
# # #          name='validate_document_content'),
# # #     path('document/<int:document_id>/version-history/', views.document_version_history,
# # #          name='document_version_history'),
# # #     path('document/<int:document_id>/restore-version/<int:version_id>/', views.restore_document_version,
# # #          name='restore_document_version'),
# # # ]
# #
# # # Ajouts au fichier ctd_submission/urls.py
# #
# # from django.urls import path
# # from . import views
# #
# # app_name = 'ctd_submission'
# #
# # urlpatterns = [
# #     # URLs existantes
# #     path('', views.dashboard, name='dashboard'),
# #     path('submission/create/', views.submission_create, name='submission_create'),
# #     path('submission/<int:submission_id>/', views.submission_detail, name='submission_detail'),
# #     path('submission/<int:submission_id>/edit/', views.submission_edit, name='submission_edit'),
# #     path('submission/<int:submission_id>/delete/', views.submission_delete, name='submission_delete'),
# #     path('submission/<int:submission_id>/export/', views.submission_export, name='submission_export'),
# #
# #     # Documents - vues existantes
# #     path('document/upload/', views.document_upload_enhanced, name='document_upload'),
# #     path('document/<int:document_id>/view/', views.document_view, name='document_view'),
# #     path('document/<int:document_id>/template/', views.document_template, name='document_template'),
# #     path('document/<int:document_id>/download/', views.document_download, name='document_download'),
# #     path('document/<int:document_id>/delete/', views.document_delete, name='document_delete'),
# #
# #     # NOUVELLES URLS POUR L'ÉDITEUR AVANCÉ
# #     path('document/<int:document_id>/advanced-editor/', views.document_advanced_editor,
# #          name='document_advanced_editor'),
# #     path('document/<int:document_id>/save-changes/', views.document_save_changes, name='document_save_changes'),
# #     path('document/<int:document_id>/copilot-suggestions/', views.copilot_suggestions, name='copilot_suggestions'),
# #     path('document/<int:document_id>/apply-template-to-editor/', views.apply_template_to_editor,
# #          name='apply_template_to_editor'),
# #     path('document/<int:document_id>/export-modified/', views.document_export_modified,
# #          name='document_export_modified'),
# #     path('document/<int:document_id>/versions/', views.document_version_history, name='document_version_history'),
# #     path('document/<int:document_id>/restore-version/<int:version_id>/', views.restore_document_version,
# #          name='restore_document_version'),
# #
# #     # APIs pour l'éditeur avancé
# #     path('api/document/<int:document_id>/extract-content/', views.api_extract_content, name='api_extract_content'),
# #     path('api/document/<int:document_id>/validate/', views.validate_document_content, name='validate_document_content'),
# #     path('api/document/<int:document_id>/analyze/', views.api_analyze_document, name='api_analyze_document'),
# #     path('api/document/<int:document_id>/force-analysis/', views.force_document_analysis,
# #          name='force_document_analysis'),
# #     path('api/document/<int:document_id>/update-template/', views.api_update_template, name='api_update_template'),
# #
# #     # Templates
# #     path('template/<int:document_id>/add-column/', views.template_add_column, name='template_add_column'),
# #     path('template/<int:document_id>/add-row/', views.template_add_row, name='template_add_row'),
# #     path('template/field/<int:field_id>/edit/', views.template_edit_field, name='template_edit_field'),
# #     path('template/field/<int:field_id>/delete/', views.template_delete_field, name='template_delete_field'),
# #     path('template/<int:document_id>/export/', views.export_template, name='export_template'),
# #     path('template/<int:document_id>/import/', views.import_template, name='import_template'),
# #
# #     # Structure CTD
# #     path('generate-ctd-structure/', views.generate_ctd_structure, name='generate_ctd_structure'),
# #     path('initialize-ctd-modules/', views.initialize_ctd_modules, name='initialize_ctd_modules'),
# #
# #     # AJAX et recherche
# #     path('ajax/search-documents/', views.ajax_search_documents, name='ajax_search_documents'),
# #     path('ajax/validate-template/', views.ajax_validate_template, name='ajax_validate_template'),
# #     path('ajax/auto-save-template/', views.ajax_auto_save_template, name='ajax_auto_save_template'),
# #     path('ajax/suggest-classification/', views.ajax_suggest_classification, name='ajax_suggest_classification'),
# #     path('ajax/get-submission-status/', views.ajax_get_submission_status, name='ajax_get_submission_status'),
# #
# #     # Rapports
# #     path('reports/', views.reports_dashboard, name='reports_dashboard'),
# #     path('reports/submission/<int:submission_id>/', views.submission_report, name='submission_report'),
# #     path('reports/submission/<int:submission_id>/export/', views.export_submission_report,
# #          name='export_submission_report'),
# #
# #     # Assistant IA et aide
# #     path('ai-assistant/', views.ai_assistant, name='ai_assistant'),
# #     path('help/', views.help_center, name='help_center'),
# #     path('help/templates/', views.help_templates, name='help_templates'),
# #
# #     # Import/Export
# #     path('import/submission/', views.import_submission, name='import_submission'),
# #
# #     # Administration (pour les superutilisateurs)
# #     path('admin/modules/', views.admin_modules, name='admin_modules'),
# #     path('admin/modules/<int:module_id>/sections/', views.admin_sections, name='admin_sections'),
# #     path('admin/sections/create/', views.admin_section_create, name='admin_section_create'),
# #     path('admin/sections/<int:section_id>/edit/', views.admin_section_edit, name='admin_section_edit'),
# #
# #     # URL SPÉCIALE POUR SERVIR LES FICHIERS STATIQUES JAVASCRIPT
# #     path('static/<path:path>', views.serve_static_file, name='static'),
# # ]
#
# # ctd_submission/urls.py - URLs corrigées pour l'application
#
# from django.urls import path
# from . import views
#
# app_name = 'ctd_submission'
#
# urlpatterns = [
#     # Dashboard principal
#     path('', views.dashboard, name='dashboard'),
#
#     # Gestion des soumissions
#     path('submission/create/', views.submission_create, name='submission_create'),
#     path('submission/<int:submission_id>/', views.submission_detail, name='submission_detail'),
#     path('submission/<int:submission_id>/edit/', views.submission_edit, name='submission_edit'),
#     path('submission/<int:submission_id>/delete/', views.submission_delete, name='submission_delete'),
#     path('submission/<int:submission_id>/export/', views.submission_export, name='submission_export'),
#
#     # Upload et gestion des documents
#     path('document/upload/', views.document_upload_enhanced, name='document_upload'),
#     path('document/<int:document_id>/view/', views.document_view, name='document_view'),
#     path('document/<int:document_id>/template/', views.document_template, name='document_template'),
#     path('document/<int:document_id>/download/', views.document_download, name='document_download'),
#     path('document/<int:document_id>/delete/', views.document_delete, name='document_delete'),
#
#     # ÉDITEUR AVANCÉ - Nouvelles URLs principales
#     path('document/<int:document_id>/advanced-editor/', views.document_advanced_editor,
#          name='document_advanced_editor'),
#     path('document/<int:document_id>/save-changes/', views.document_save_changes,
#          name='document_save_changes'),
#     path('document/<int:document_id>/copilot-suggestions/', views.copilot_suggestions,
#          name='copilot_suggestions'),
#     path('document/<int:document_id>/apply-template-to-editor/', views.apply_template_to_editor,
#          name='apply_template_to_editor'),
#     path('document/<int:document_id>/export-modified/', views.document_export_modified,
#          name='document_export_modified'),
#
#     # Versioning et historique
#     path('document/<int:document_id>/versions/', views.document_version_history,
#          name='document_version_history'),
#     path('document/<int:document_id>/restore-version/<int:version_id>/', views.restore_document_version,
#          name='restore_document_version'),
#
#     # APIs pour l'éditeur avancé
#     path('api/document/<int:document_id>/extract-content/', views.api_extract_content,
#          name='api_extract_content'),
#     path('api/document/<int:document_id>/validate/', views.validate_document_content,
#          name='validate_document_content'),
#     path('api/document/<int:document_id>/analyze/', views.api_analyze_document,
#          name='api_analyze_document'),
#     path('api/document/<int:document_id>/force-analysis/', views.force_document_analysis,
#          name='force_document_analysis'),
#     path('api/document/<int:document_id>/update-template/', views.api_update_template,
#          name='api_update_template'),
#
#     # Templates
#     path('template/<int:document_id>/add-column/', views.template_add_column,
#          name='template_add_column'),
#     path('template/<int:document_id>/add-row/', views.template_add_row,
#          name='template_add_row'),
#     path('template/field/<int:field_id>/edit/', views.template_edit_field,
#          name='template_edit_field'),
#     path('template/field/<int:field_id>/delete/', views.template_delete_field,
#          name='template_delete_field'),
#     path('template/<int:document_id>/export/', views.export_template,
#          name='export_template'),
#     path('template/<int:document_id>/import/', views.import_template,
#          name='import_template'),
#
#     # Structure CTD
#     path('generate-ctd-structure/', views.generate_ctd_structure,
#          name='generate_ctd_structure'),
#     path('initialize-ctd-modules/', views.initialize_ctd_modules,
#          name='initialize_ctd_modules'),
#
#     # AJAX et recherche
#     path('ajax/search-documents/', views.ajax_search_documents,
#          name='ajax_search_documents'),
#     path('ajax/validate-template/', views.ajax_validate_template,
#          name='ajax_validate_template'),
#     path('ajax/auto-save-template/', views.ajax_auto_save_template,
#          name='ajax_auto_save_template'),
#     path('ajax/suggest-classification/', views.ajax_suggest_classification,
#          name='ajax_suggest_classification'),
#     path('ajax/get-submission-status/', views.ajax_get_submission_status,
#          name='ajax_get_submission_status'),
#
#     # Rapports
#     path('reports/', views.reports_dashboard, name='reports_dashboard'),
#     path('reports/submission/<int:submission_id>/', views.submission_report,
#          name='submission_report'),
#     path('reports/submission/<int:submission_id>/export/', views.export_submission_report,
#          name='export_submission_report'),
#
#     # Assistant IA et aide
#     path('ai-assistant/', views.ai_assistant, name='ai_assistant'),
#     path('help/', views.help_center, name='help_center'),
#     path('help/templates/', views.help_templates, name='help_templates'),
#
#     # Import/Export
#     path('import/submission/', views.import_submission, name='import_submission'),
#
#     # Administration (pour les superutilisateurs)
#     path('admin/modules/', views.admin_modules, name='admin_modules'),
#     path('admin/modules/<int:module_id>/sections/', views.admin_sections,
#          name='admin_sections'),
#     path('admin/sections/create/', views.admin_section_create,
#          name='admin_section_create'),
#     path('admin/sections/<int:section_id>/edit/', views.admin_section_edit,
#          name='admin_section_edit'),
#
#     # URL pour servir les fichiers statiques (développement uniquement)
#     path('static/<path:path>', views.serve_static_file, name='static'),
# ]
#
# # URLs d'erreur personnalisées (à ajouter dans le urls.py principal du projet)
# handler404 = 'ctd_submission.views.error_404'
# handler500 = 'ctd_submission.views.error_500'
# handler403 = 'ctd_submission.views.error_403'
#
#

# ctd_submission/urls.py - VERSION CORRIGÉE
# Configuration des URLs pour la communication avec utils.py

from django.urls import path
from . import views


app_name = 'ctd_submission'

urlpatterns = [
    # Dashboard principal
    path('', views.dashboard, name='dashboard'),

    # Gestion des soumissions
    path('submission/create/', views.submission_create, name='submission_create'),
    path('submission/<int:submission_id>/', views.submission_detail, name='submission_detail'),
    path('submission/<int:submission_id>/edit/', views.submission_edit, name='submission_edit'),
    path('submission/<int:submission_id>/delete/', views.submission_delete, name='submission_delete'),
    path('submission/<int:submission_id>/export/', views.submission_export, name='submission_export'),
    path('submission/<int:submission_id>/report/', views.submission_report, name='submission_report'),

    # Upload de documents - VERSION AMÉLIORÉE
    path('document/upload/', views.document_upload, name='document_upload'),
    path('document/upload-enhanced/', views.document_upload_enhanced, name='document_upload_enhanced'),

    # Gestion des documents
    path('document/<int:document_id>/view/', views.document_view, name='document_view'),
    path('document/<int:document_id>/template/', views.document_template, name='document_template'),
    path('document/<int:document_id>/download/', views.document_download, name='document_download'),
    path('document/<int:document_id>/delete/', views.document_delete, name='document_delete'),

    # NOUVEAU: Éditeur avancé avec Copilot
    path('document/<int:document_id>/advanced-editor/', views.document_advanced_editor,
         name='document_advanced_editor'),
    path('document/<int:document_id>/save-changes/', views.document_save_changes, name='document_save_changes'),
    path('document/<int:document_id>/export-modified/', views.document_export_modified,
         name='document_export_modified'),

    # Gestion des templates
    path('template/<int:document_id>/add-column/', views.template_add_column, name='template_add_column'),
    path('template/<int:document_id>/add-row/', views.template_add_row, name='template_add_row'),
    path('template/field/<int:field_id>/edit/', views.template_edit_field, name='template_edit_field'),
    path('template/field/<int:field_id>/delete/', views.template_delete_field, name='template_delete_field'),
    path('template/<int:document_id>/export/', views.export_template, name='export_template'),
    path('template/<int:document_id>/import/', views.import_template, name='import_template'),

    # NOUVEAU: APIs Copilot et IA
    path('api/copilot/<int:document_id>/suggestions/', views.copilot_suggestions, name='copilot_suggestions'),
    path('api/template/<int:document_id>/apply/', views.apply_template_to_editor, name='apply_template_to_editor'),
    path('api/document/<int:document_id>/extract-content/', views.api_extract_content, name='api_extract_content'),
    path('api/document/<int:document_id>/analyze/', views.api_analyze_document, name='api_analyze_document'),
    path('api/template/<int:document_id>/update/', views.api_update_template, name='api_update_template'),

    # Génération CTD automatique
    path('generate-ctd-structure/', views.generate_ctd_structure, name='generate_ctd_structure'),
    path('force-analysis/<int:document_id>/', views.force_document_analysis, name='force_document_analysis'),

    # Initialisation et configuration
    path('initialize-ctd-modules/', views.initialize_ctd_modules, name='initialize_ctd_modules'),

    # Historique des versions
    path('document/<int:document_id>/versions/', views.document_version_history, name='document_version_history'),
    path('document/<int:document_id>/versions/<int:version_id>/restore/', views.restore_document_version,
         name='restore_document_version'),

    # Validation des documents
    path('document/<int:document_id>/validate/', views.validate_document_content, name='validate_document_content'),

    # Rapports et statistiques
    path('reports/', views.reports_dashboard, name='reports_dashboard'),
    path('reports/<int:submission_id>/export/', views.export_submission_report, name='export_submission_report'),

    # Assistant IA
    path('ai-assistant/', views.ai_assistant, name='ai_assistant'),

    # Centre d'aide
    path('help/', views.help_center, name='help_center'),
    path('help/templates/', views.help_templates, name='help_templates'),

    # APIs AJAX
    path('ajax/search-documents/', views.ajax_search_documents, name='ajax_search_documents'),
    path('ajax/validate-template/', views.ajax_validate_template, name='ajax_validate_template'),
    path('ajax/auto-save-template/', views.ajax_auto_save_template, name='ajax_auto_save_template'),
    path('ajax/suggest-classification/', views.ajax_suggest_classification, name='ajax_suggest_classification'),
    path('ajax/submission-status/', views.ajax_get_submission_status, name='ajax_get_submission_status'),

    # Import/Export
    path('import/', views.import_submission, name='import_submission'),

    # Administration (pour staff uniquement)
    path('admin/modules/', views.admin_modules, name='admin_modules'),
    path('admin/modules/<int:module_id>/sections/', views.admin_sections, name='admin_sections'),
    path('admin/sections/create/', views.admin_section_create, name='admin_section_create'),
    path('admin/sections/<int:section_id>/edit/', views.admin_section_edit, name='admin_section_edit'),

    # NOUVEAU: Fichiers statiques pour développement
    path('static/<path:path>', views.serve_static_file, name='serve_static_file'),

# Nouvelle URL pour le retraitement fidèle
    path('document/<int:document_id>/reprocess_faithful/',
         views.reprocess_document_faithful,
         name='reprocess_document_faithful'),



]

