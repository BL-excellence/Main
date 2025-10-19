# expert/urls.py
from django.urls import path
from . import views, views_enrichment, views_learning, views_evaluation

app_name = "expert"

urlpatterns = [
    # ============================================
    # 📊 DASHBOARD & LISTE DOCUMENTS
    # ============================================
    path("", views.ExpertDashboardView.as_view(), name="dashboard"),
    path("documents/", views.DocumentReviewListView.as_view(), name="document_list"),

    # ============================================
    # 📊 DASHBOARD ANNOTATION
    # ============================================
    path("annotation-dashboard/", views.expert_annotation_dashboard, name="annotation_dashboard"),

    # ============================================
    # 📝 ANNOTATION (Interface Annotateur pour Expert)
    # ============================================
    path("annotate/<int:doc_id>/", views.expert_annotate_document, name="annotate_document"),
    path("review/<int:doc_id>/", views.expert_annotate_document, name="review_document"),  # Alias for backward compatibility

    # ============================================
    # ✅ RÉVISION EXPERT (Valider annotations des annotateurs)
    # ============================================
    path("review-annotations/<int:doc_id>/", views.expert_review_annotations, name="review_annotations"),
    path("api/bulk-validate/<int:doc_id>/", views.expert_bulk_validate_annotations, name="bulk_validate_annotations"),

    # ============================================
    # 🧠 JSON SÉMANTIQUE (Relations, Q&A, Enrichissement)
    # ============================================
    path("semantic-json/<int:doc_id>/", views.expert_view_document_annotation_json_enriched, name="view_semantic_json"),
    path("annotation/document/<int:doc_id>/view-json-enriched/", views.expert_view_document_annotation_json_enriched, name="view_document_annotation_json_enriched"),

    # ============================================
    # 🔧 API ANNOTATIONS (CRUD)
    # ============================================
    path("api/validate/<int:annotation_id>/", views.validate_annotation_ajax, name="validate_annotation"),
    path("api/create-annotation/", views.create_annotation_ajax, name="create_annotation"),
    path("api/modify/<int:annotation_id>/", views.modify_annotation_ajax, name="modify_annotation"),
    path("api/delete/<int:annotation_id>/", views.delete_annotation_ajax, name="delete_annotation"),
    path("api/undo/<int:annotation_id>/", views.undo_validation_ajax, name="undo_validation"),

    # ============================================
    # 🏷️ TYPES D'ANNOTATIONS
    # ============================================
    path("api/create-annotation-type/", views.create_annotation_type_ajax, name="create_annotation_type"),
    path("api/delete-annotation-type/", views.delete_annotation_type_ajax, name="delete_annotation_type"),

    # ============================================
    # 🤖 IA (Groq)
    # ============================================
    path("api/groq/<int:page_id>/", views.expert_ai_annotate_page_groq, name="ai_annotate_page_groq"),
    path("api/save-annotation/", views.expert_save_manual_annotation, name="save_manual_annotation"),
    path("api/get-annotations/<int:page_id>/", views.expert_get_page_annotations, name="get_page_annotations"),

    # ============================================
    # 📄 PAGE: JSON & RÉSUMÉS
    # ============================================
    path("page/<int:page_id>/generate-summary/", views.expert_generate_page_annotation_summary,
         name="generate_page_annotation_summary"),
    path("page/<int:page_id>/view-json/", views.expert_view_page_annotation_json, name="view_page_annotation_json"),
    path("page/<int:page_id>/save-json/", views.save_page_json, name="save_page_json"),
    path("page/<int:page_id>/save-summary/", views.save_page_summary, name="save_page_summary"),
    path("page/<int:page_id>/update-from-annotations/", views.update_summary_from_annotations,
         name="update_summary_from_annotations"),

    # ============================================
    # 📚 DOCUMENT: JSON & RÉSUMÉS
    # ============================================
    path("document/<int:doc_id>/generate-summary/", views.expert_generate_document_annotation_summary,
         name="generate_document_annotation_summary"),
    path("document/<int:doc_id>/view-json/", views.expert_view_document_annotation_json,
         name="view_document_annotation_json"),
    path("document/<int:doc_id>/save-json/", views.save_document_json, name="save_document_json"),
    path("document/<int:doc_id>/save-summary/", views.save_summary_changes, name="save_summary_changes"),
    path("document/<int:doc_id>/auto-regenerate-summary/", views.auto_regenerate_summary_from_annotations,
         name="auto_regenerate_summary_from_annotations"),

    # ============================================
    # 🔗 ENRICHISSEMENT (Relations, Q&A)
    # ============================================
    path("document/<int:doc_id>/enrich-json/", views_enrichment.enrich_document_json, name="enrich_document_json"),
    path("document/<int:doc_id>/test-qa/", views_enrichment.test_qa, name="test_qa_system"),
    path("document/<int:doc_id>/add-relation/", views_enrichment.add_relation, name="add_custom_relation"),
    path("document/<int:doc_id>/add-qa/", views_enrichment.add_qa, name="add_qa_pair"),
    path("document/<int:doc_id>/save-enriched-edits/", views_enrichment.save_enriched_edits,
         name="save_enriched_json_manual_edits"),
    path("document/<int:doc_id>/qa-feedback/", views_enrichment.qa_feedback, name="qa_feedback"),
    path("document/<int:doc_id>/from-paragraph/", views_enrichment.paragraph_to_relations,
         name="paragraph_to_relations"),
    path("document/<int:doc_id>/describe-relation/", views_enrichment.describe_relation,
         name="describe_single_relation"),
    path("document/<int:doc_id>/add-relations-batch/", views_enrichment.add_relations_batch,
         name="add_relations_batch"),
    path("document/<int:doc_id>/describe-relations-batch/", views_enrichment.describe_relations_batch,
         name="describe_relations_batch"),
    path("document/<int:doc_id>/analyze-paragraph/", views_enrichment.analyze_paragraph, name="analyze_paragraph"),
    path("document/<int:doc_id>/save-paragraph-relations/", views_enrichment.save_paragraph_relations,
         name="save_paragraph_relations"),

    # ============================================
    # 📊 ANALYSE PAGE PAR PAGE (Documents Validés)
    # ============================================
    path("validated-documents/", views_enrichment.get_validated_documents, name="get_validated_documents"),
    path("document/<int:doc_id>/analyze-pages-relations/", views_enrichment.analyze_document_pages_relations,
         name="analyze_pages_relations"),
    path("document/<int:doc_id>/get-page-relations/", views_enrichment.get_document_page_relations,
         name="get_page_relations"),
    path("document/<int:doc_id>/page/<int:page_num>/relations/", views_enrichment.get_single_page_relations,
         name="get_single_page_relations"),
    path("document/<int:doc_id>/page/<int:page_num>/relation/<int:relation_index>/delete/",
         views_enrichment.delete_page_relation, name="delete_page_relation"),

    # ============================================
    # 🎓 APPRENTISSAGE (Comparaison, Stats)
    # ============================================
    path("document/<int:doc_id>/compare-and-learn/", views_learning.compare_with_ai_and_learn,
         name="compare_with_ai_and_learn"),
    path("document/<int:doc_id>/learning-history/", views_learning.get_learning_history, name="get_learning_history"),
    path("document/<int:doc_id>/enhance-with-patterns/", views_learning.enhance_with_learned_patterns,
         name="enhance_with_learned_patterns"),
    path("document/<int:doc_id>/view-expert-deltas/", views_learning.view_expert_deltas, name="view_expert_deltas"),
    path("document/<int:doc_id>/regenerate-with-learning/", views_learning.regenerate_with_learning,
         name="regenerate_with_learning"),
    path("delta/<int:delta_id>/rate/", views_learning.rate_correction_quality, name="rate_correction_quality"),
    path("learning-stats/", views_learning.get_learning_stats, name="get_learning_stats"),

    # ============================================
    # 📊 ÉVALUATION DU MODÈLE (Métriques académiques)
    # ============================================
    path("model-evaluation/", views_evaluation.model_evaluation_view, name="model_evaluation"),

    # ============================================
    # 🏛️ ANALYSE RÉGLEMENTAIRE
    # ============================================
    path("regulatory/save-summary/<int:doc_id>/", views.save_regulatory_summary, name="save_regulatory_summary"),
    path("regulatory/validate/<int:doc_id>/", views.validate_regulatory_analysis, name="validate_regulatory_analysis"),
    path("regulatory/generate/<int:doc_id>/", views.generate_regulatory_analysis, name="generate_regulatory_analysis"),

    # ============================================
    # ✅ VALIDATION FINALE
    # ============================================
    path("validate-document/<int:document_id>/", views.validate_document, name="validate_document"),
    path("documents/<int:document_id>/view-original/", views.view_original_document, name="view_original_document"),

    # ============================================
    # 📄 PROXY PDF (pour affichage dans iframe)
    # ============================================
    path("proxy-pdf/<int:doc_id>/", views.expert_proxy_pdf, name="proxy_pdf"),
    path("page-image/<int:doc_id>/<int:page_num>/", views.get_page_image, name="get_page_image"),

]