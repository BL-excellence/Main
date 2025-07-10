# ===================================
# annotation/urls.py - COMPLET
# ===================================
from django.urls import path
from . import views

app_name = 'annotation'

urlpatterns = [
    # === INTERFACE D'ANNOTATION STANDARD ===
    path('document/<int:document_id>/', views.annotate_document, name='annotate_document'),

    # === API POUR ANNOTATIONS ===
    path('create/', views.create_annotation, name='create'),
    path('<int:annotation_id>/update/', views.update_annotation, name='update'),
    path('<int:annotation_id>/delete/', views.delete_annotation, name='delete'),

    # === ANNOTATION AUTOMATIQUE ===
    path('auto-annotate/<int:document_id>/', views.auto_annotate, name='auto_annotate'),

    # === API POUR LISTER ET GÉRER ===
    path('document/<int:document_id>/annotations/', views.annotation_list, name='list'),
    path('entity-types/', views.entity_types_list, name='entity_types'),
    path('document/<int:document_id>/validate-all/', views.validate_all_annotations, name='validate_all'),

    # === INTERFACE DE VALIDATION EXPERTE ===
    path('expert/validation/', views.expert_validation_list, name='expert_validation_list'),
    path('expert/validation/<int:document_id>/', views.expert_validation_detail, name='expert_validation_detail'),

    # === ACTIONS DE VALIDATION EXPERTE ===
    path('expert/validate/<int:document_id>/', views.expert_final_validation, name='expert_final_validation'),
    path('expert/annotation/<int:annotation_id>/feedback/', views.expert_annotation_feedback,
         name='expert_annotation_feedback'),

    # === STATISTIQUES EXPERTS ===
    path('expert/stats/', views.expert_dashboard_stats, name='expert_dashboard_stats'),
]