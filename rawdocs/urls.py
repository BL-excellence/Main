from django.urls import path
from django.contrib.auth import views as auth_views
from . import views
from .views import dashboard_view

app_name = 'rawdocs'

urlpatterns = [
    # 1) Page d’accueil → login
    path(
        '',
        auth_views.LoginView.as_view(
            template_name='registration/login.html'
        ),
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

    # 4) Après authentification → upload
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

    # 7) Suppression d’un document
    path(
        'document/<int:doc_id>/delete/',
        views.delete_document,
        name='document_delete'
    ),

    # 8) Édition manuelle des métadonnées
    path(
        'edit/<int:doc_id>/',
        views.edit_metadata,
        name='edit_metadata'
    ),

    # 9) Tableau de bord
    path(
        'dashboard/',
        dashboard_view,
        name='dashboard'
    ),
]
