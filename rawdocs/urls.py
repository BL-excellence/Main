# rawdocs/urls.py

from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

app_name = 'rawdocs'

urlpatterns = [
    # 1) Page d'accueil → login with custom redirect
    path(
        '',
        views.CustomLoginView.as_view(),
        name='login'
    ),

    # 2) Déconnexion
    path(
        'logout/',
        auth_views.LogoutView.as_view(next_page='rawdocs:login'),
        name='logout'
    ),

    # 3) Inscription
    path(
        'register/',
        views.register,
        name='register'
    ),

    # 4) Upload (Métadonneur)
    path(
        'upload/',
        views.upload_pdf,
        name='upload'
    ),

    # 5) Liste des documents importés
    path(
        'documents/',
        views.document_list,
        name='document_list'
    ),

    # 6) Métadonnées JSON pour un document
    path(
        'documents/<int:doc_id>/metadata/',
        views.document_metadata,
        name='document_metadata'
    ),

    # 7) Suppression d'un document
    path(
        'document/<int:doc_id>/delete/',
        views.delete_document,
        name='document_delete'
    ),

    # 8) Validation d'un document (Métadonneur)
    path(
        'document/<int:doc_id>/validate/',
        views.validate_document,
        name='validate_document'
    ),

    # 9) Dashboard annotation (Annotateur)
    path(
        'annotation/',
        views.annotation_dashboard,
        name='annotation_dashboard'
    ),

    # 10) Interface d'annotation
    path(
        'annotation/document/<int:doc_id>/',
        views.annotate_document,
        name='annotate_document'
    ),

    # 12) Sauvegarde annotation manuelle
    path(
        'annotation/manual/',
        views.save_manual_annotation,
        name='save_manual_annotation'
    ),

    # 13) Récupérer annotations d'une page
    path(
        'annotation/page/<int:page_id>/',
        views.get_page_annotations,
        name='get_page_annotations'
    ),

    # 14) Supprimer une annotation
    path(
        'annotation/<int:annotation_id>/delete/',
        views.delete_annotation,
        name='delete_annotation'
    ),
    path('annotation/groq/<int:page_id>/', 
        views.ai_annotate_page_groq, 
        name='ai_annotate_page_groq'),

]