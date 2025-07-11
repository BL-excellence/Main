# rawdocs/urls.py

from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

app_name = 'rawdocs'

urlpatterns = [
    # 1) Custom login (redirects by role)
    path(
        '',
        views.CustomLoginView.as_view(),
        name='login'
    ),

    # 2) Logout
    path(
        'logout/',
        auth_views.LogoutView.as_view(next_page='rawdocs:login'),
        name='logout'
    ),

    # 3) Register
    path(
        'register/',
        views.register,
        name='register'
    ),

    # 4) Upload (Métadonneur) — URL or local file
    path(
        'upload/',
        views.upload_pdf,
        name='upload'
    ),

    # 5) List imported documents
    path(
        'documents/',
        views.document_list,
        name='document_list'
    ),

    # 6) JSON metadata for a document
    path(
        'documents/<int:doc_id>/metadata/',
        views.document_metadata,
        name='document_metadata'
    ),

    # 7) Delete a document
    path(
        'document/<int:doc_id>/delete/',
        views.delete_document,
        name='document_delete'
    ),

    # 8) Edit metadata manually
    path(
        'edit/<int:doc_id>/',
        views.edit_metadata,
        name='edit_metadata'
    ),

    # 9) Validate a document (extract pages & ready for annotation)
    path(
        'document/<int:doc_id>/validate/',
        views.validate_document,
        name='validate_document'
    ),

    # 10) Metadonneur dashboard
    path(
        'dashboard/',
        views.dashboard_view,
        name='dashboard'
    ),

    # ——— Annotateur URLs —————————————————————————————————

    # 11) Annotation dashboard (list validated docs)
    path(
        'annotation/',
        views.annotation_dashboard,
        name='annotation_dashboard'
    ),

    # 12) Annotate a specific document
    path(
        'annotation/document/<int:doc_id>/',
        views.annotate_document,
        name='annotate_document'
    ),
    
    # AI annotation using Groq
    path('annotation/groq/<int:page_id>/', 
        views.ai_annotate_page_groq, 
        name='ai_annotate_page_groq'
    ),

    # 14) Save a manual annotation
    path(
        'annotation/manual/',
        views.save_manual_annotation,
        name='save_manual_annotation'
    ),

    # 15) Retrieve all annotations for a page
    path(
        'annotation/page/<int:page_id>/',
        views.get_page_annotations,
        name='get_page_annotations'
    ),

    # 16) Delete an annotation
    path(
        'annotation/<int:annotation_id>/delete/',
        views.delete_annotation,
        name='delete_annotation'
    ),
]
