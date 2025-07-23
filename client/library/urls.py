from django.urls import path, include
from . import views

app_name = 'client_library'

urlpatterns = [
    # Vues HTML
    path('', views.library_dashboard, name='dashboard'),
    path('documents/', views.document_list, name='document_list'),
    path('documents/<int:pk>/', views.document_detail, name='document_detail'),
    path('documents/<int:pk>/download/', views.download_document, name='download_document'),
    path('upload/', views.upload_document, name='upload_document'),
    
    # API endpoints
    path('api/search/', views.search_documents, name='api_search'),
    path('api/documents/<int:pk>/metadata/', views.document_metadata, name='api_metadata'),
]
