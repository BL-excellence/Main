from django.urls import path, include
from . import views
from .client_upload_views import (
    client_upload_document,
    client_document_detail,
    client_documents_list,
    delete_client_document,
    download_client_document
)

app_name = 'library'

urlpatterns = [
    # Vues HTML - Documents des métadonneurs
    path('', views.library_dashboard, name='dashboard'),
    path('documents/', views.document_list, name='document_list'),
    path('documents/horizontal/', views.document_list_horizontal, name='document_list_horizontal'),
    path('category/<str:category>/', views.documents_by_category, name='documents_by_category'),
    path('type/<str:doc_type>/', views.documents_by_type, name='documents_by_type'),
    path('country/<str:country>/', views.documents_by_country, name='documents_by_country'),
    path('documents/<int:pk>/', views.document_detail, name='document_detail'),
    path('documents/<int:pk>/download/', views.download_document, name='download_document'),
    path('upload/', views.upload_document, name='upload_document'),
    
    # Vues Client - Documents uploadés par les clients
    path('client/upload/', client_upload_document, name='client_upload'),
    path('client/documents/', client_documents_list, name='client_documents_list'),
    path('client/documents/<int:pk>/', client_document_detail, name='client_document_detail'),
    path('client/documents/<int:pk>/download/', download_client_document, name='download_client_document'),
    path('client/documents/<int:pk>/delete/', delete_client_document, name='delete_client_document'),
    
    # API endpoints
    path('api/search/', views.search_documents, name='api_search'),
    path('api/documents/<int:pk>/metadata/', views.document_metadata, name='api_metadata'),
]
