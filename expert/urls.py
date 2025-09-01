# expert/urls.py

from django.urls import path
from . import views, views_enrichment, views_learning

app_name = 'expert'

urlpatterns = [
    path('', views.ExpertDashboardView.as_view(), name='dashboard'),
    path('documents/', views.DocumentReviewListView.as_view(), name='document_list'),
    path('review/<int:document_id>/', views.DocumentReviewView.as_view(), name='review_document'),
    path('validate-document/<int:document_id>/', views.validate_document, name='validate_document'),
    path('api/validate/<int:annotation_id>/', views.validate_annotation_ajax, name='validate_annotation'),
    path('api/create-annotation/', views.create_annotation_ajax, name='create_annotation'),
    path('api/modify/<int:annotation_id>/', views.modify_annotation_ajax, name='modify_annotation'),
    path('api/delete/<int:annotation_id>/', views.delete_annotation_ajax, name='delete_annotation'),
    path('api/undo/<int:annotation_id>/', views.undo_validation_ajax, name='undo_validation'),
    path('api/create-annotation-type/', views.create_annotation_type_ajax, name='create_annotation_type'),
    path('api/delete-annotation-type/', views.delete_annotation_type_ajax, name='delete_annotation_type'),
    path('documents/<int:document_id>/view-original/', views.view_original_document, name='view_original_document'),

    # ——— URLs Annotation Expert (copiées de rawdocs) —————————————————————————————————
    
    # Dashboard annotation expert (liste des documents validés)
    path('annotation/', views.expert_annotation_dashboard, name='annotation_dashboard'),
    
    # Interface d'annotation d'un document spécifique pour expert
    path('annotation/document/<int:doc_id>/', views.expert_annotate_document, name='annotate_document'),
    
    # Annotation automatique avec Groq pour expert
    path('annotation/groq/<int:page_id>/', views.expert_ai_annotate_page_groq, name='ai_annotate_page_groq'),
    
    # Sauvegarde d'une annotation manuelle pour expert
    path('annotation/manual/', views.expert_save_manual_annotation, name='save_manual_annotation'),
    
    # Récupération des annotations d'une page pour expert
    path('annotation/page/<int:page_id>/', views.expert_get_page_annotations, name='get_page_annotations'),
    
    # Suppression d'une annotation pour expert
    path('annotation/<int:annotation_id>/delete/', views.expert_delete_annotation, name='delete_annotation_expert'),
    
    # Validation des annotations d'une page (RLHF) pour expert
    path('annotation/validate-page/<int:page_id>/', views.expert_validate_page_annotations, name='validate_page_annotations'),
    
    # Génération du JSON et résumé pour une page (expert)
    path('annotation/page/<int:page_id>/generate-summary/', views.expert_generate_page_annotation_summary, name='generate_page_annotation_summary'),
    
    # Génération du JSON et résumé global pour un document (expert)
    path('annotation/document/<int:doc_id>/generate-summary/', views.expert_generate_document_annotation_summary, name='generate_document_annotation_summary'),
    
    # Visualisation du JSON et résumé d'une page (expert)
    path('annotation/page/<int:page_id>/view-json/', views.expert_view_page_annotation_json, name='view_page_annotation_json'),
    
    # Visualisation du JSON et résumé global d'un document (expert)
    # ✅ Vue "JSON simple"
    path(
        'annotation/document/<int:doc_id>/view-json/',
        views.expert_view_document_annotation_json,
        name='view_document_annotation_json'
    ),
    
    # ✅ Vue "JSON sémantique/enrichi"
    path(
        'annotation/document/<int:doc_id>/view-json-enriched/',
        views.expert_view_document_annotation_json_enriched,
        name='view_document_annotation_json_enriched'
    ),
    
    # Sauvegarde du JSON global modifié d'un document
    path('annotation/document/<int:doc_id>/save-json/', views.save_document_json, name='save_document_json'),
    
    # Sauvegarde du JSON modifié d'une page
    path('annotation/page/<int:page_id>/save-json/', views.save_page_json, name='save_page_json'),

    # Sauvegarde du résumé modifié
    path('annotation/document/<int:doc_id>/save-summary/', views.save_summary_changes, name='save_summary_changes'),
    
    # Sauvegarde et validation du résumé de page
    path('annotation/page/<int:page_id>/save-summary/', views.save_page_summary, name='save_page_summary'),
    path('annotation/page/<int:page_id>/validate-summary/', views.validate_page_summary, name='validate_page_summary'),

    # Regulatory analysis endpoints for expert
    path('regulatory/save-summary/<int:doc_id>/', views.save_regulatory_summary, name='save_regulatory_summary'),
    path('regulatory/validate/<int:doc_id>/', views.validate_regulatory_analysis, name='validate_regulatory_analysis'),
    # Expert regulatory analysis generation
    path('regulatory/generate/<int:doc_id>/', views.generate_regulatory_analysis, name='generate_regulatory_analysis'),
    # Expert annotation interface
    path('annotate/<int:doc_id>/', views.expert_annotate_document, name='annotate_document'),
    path('api/groq/<int:page_id>/', views.expert_ai_annotate_page_groq, name='ai_annotate_page_groq'),
    path('api/save-annotation/', views.expert_save_manual_annotation, name='save_manual_annotation'),
    path('api/get-annotations/<int:page_id>/', views.expert_get_page_annotations, name='get_page_annotations'),
    path('api/delete-annotation/<int:annotation_id>/', views.expert_delete_annotation, name='delete_annotation'),

    # JSON Enrichi - URLs
    path('annotation/document/<int:doc_id>/enrich-json/', views_enrichment.enrich_document_json,
         name='enrich_document_json'),
    path('annotation/document/<int:doc_id>/test-qa/', views_enrichment.test_qa, name='test_qa_system'),
    path('annotation/document/<int:doc_id>/add-relation/', views_enrichment.add_relation, name='add_custom_relation'),
    path('annotation/document/<int:doc_id>/add-qa/', views_enrichment.add_qa, name='add_qa_pair'),
    path('annotation/document/<int:doc_id>/save-enriched-edits/', views_enrichment.save_enriched_edits,
         name='save_enriched_json_manual_edits'),
    path(
        'annotation/document/<int:doc_id>/qa-feedback/',
        views_enrichment.qa_feedback,
        name='qa_feedback'
    ),
    path('annotation/document/<int:doc_id>/from-paragraph/',
         views_enrichment.paragraph_to_relations, name='paragraph_to_relations'),

    # URLs pour l'apprentissage expert
    path('document/<int:doc_id>/compare-and-learn/',
         views_learning.compare_with_ai_and_learn,
         name='compare_with_ai_and_learn'),
    path('document/<int:doc_id>/learning-history/',
         views_learning.get_learning_history,
         name='get_learning_history'),
    path('document/<int:doc_id>/enhance-with-patterns/',
         views_learning.enhance_with_learned_patterns,
         name='enhance_with_learned_patterns'),
    path('document/<int:doc_id>/view-expert-deltas/',
         views_learning.view_expert_deltas,
         name='view_expert_deltas'),
    path('document/<int:doc_id>/regenerate-with-learning/',
         views_learning.regenerate_with_learning,
         name='regenerate_with_learning'),
    path('delta/<int:delta_id>/rate/',
         views_learning.rate_correction_quality,
         name='rate_correction_quality'),
    path('learning-stats/',
         views_learning.get_learning_stats,
         name='get_learning_stats'),
]