# documents/urls.py
from django.urls import path
from . import views

app_name = 'documents'

urlpatterns = [
    # Liste des documents
    path('', views.document_list, name='list'),

    # Upload de documents
    path('upload/', views.document_upload, name='upload'),

    # Annotation des documents
    path('annotate/', views.document_list, name='annotate_list'),  # Liste pour annotation
    path('annotate/<int:document_id>/', views.document_annotate, name='annotate'),  # Interface d'annotation

    # Actions sur les documents
    path('<int:document_id>/validate/', views.validate_annotations, name='validate'),
    path('<int:document_id>/refuse/', views.refuse_annotation, name='refuse'),
    path('<int:document_id>/view/', views.document_view, name='view'),

    # Stats des documents (ajout pour le debug)
    path('<int:document_id>/stats/', views.document_stats, name='stats'),
]