# extraction/urls.py
from django.urls import path
from . import views

app_name = 'extraction'

urlpatterns = [
    # Liste de validation des métadonnées
    path('validation/', views.metadata_validation_list, name='validation_list'),

    # Détail de validation d'un document
    path('validation/<int:document_id>/', views.metadata_validation_detail, name='validation_detail'),

    # Actions sur les métadonnées
    path('save-metadata/<int:document_id>/', views.save_metadata, name='save_metadata'),
    path('extract/<int:document_id>/', views.extract_metadata, name='extract_metadata'),
    path('re-extract/<int:document_id>/', views.re_extract_metadata, name='re_extract_metadata'),

    # Statut de l'extraction
    path('status/<int:document_id>/', views.extraction_status, name='extraction_status'),
]