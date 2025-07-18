# rawdocs/urls.py
from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

app_name = 'rawdocs'

urlpatterns = [
    # ============ Authentification ============
    path(
        '',
        views.CustomLoginView.as_view(),
        name='login'
    ),
    path(
        'logout/',
        auth_views.LogoutView.as_view(next_page='rawdocs:login'),
        name='logout'
    ),
    path(
        'register/',
        views.register,
        name='register'
    ),

    # ============ Métadonneur ============
    path(
        'upload/',
        views.upload_pdf,
        name='upload'
    ),
    path(
        'documents/',
        views.document_list,
        name='document_list'
    ),
    path(
        'documents/<int:doc_id>/metadata/',
        views.document_metadata,
        name='document_metadata'
    ),
    path(
        'document/<int:doc_id>/delete/',
        views.delete_document,
        name='document_delete'
    ),
    path(
        'edit/<int:doc_id>/',
        views.edit_metadata,
        name='edit_metadata'
    ),
    path(
        'document/<int:doc_id>/validate/',
        views.validate_document,
        name='validate_document'
    ),
    path(
        'dashboard/',
        views.dashboard_view,
        name='dashboard'
    ),

    # ============ Annotation ============
    path(
        'annotation/',
        views.annotation_dashboard,
        name='annotation_dashboard'
    ),
    path(
        'annotation/document/<int:doc_id>/',
        views.annotate_document,
        name='annotate_document'
    ),
    path(
        'annotation/manual/',
        views.save_manual_annotation,
        name='save_manual_annotation'
    ),
    path(
        'annotation/page/<int:page_id>/',
        views.get_page_annotations,
        name='get_page_annotations'
    ),
    path(
        'annotation/<int:annotation_id>/delete/',
        views.delete_annotation,
        name='delete_annotation'
    ),

    # ============ IA & RLHF ============
    path(
        'annotation/groq/<int:page_id>/', 
        views.ai_annotate_page_groq, 
        name='ai_annotate_page_groq'
    ),
    path(
        'annotation/validate-page/<int:page_id>/', 
        views.validate_page_annotations, 
        name='validate_page_annotations'
    ),
    path(
        'learning/dashboard/', 
        views.get_learning_dashboard, 
        name='learning_dashboard'
    ),
]