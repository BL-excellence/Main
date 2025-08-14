from django.urls import path
from . import views

app_name = 'client_products'

urlpatterns = [
    # Vues HTML
    path('', views.products_list_view, name='list'),
    path('<int:pk>/', views.product_detail_view, name='detail'),
    
    # API endpoints
    path('api/products/', views.ProductListAPIView.as_view(), name='api_list'),
    path('api/products/<int:pk>/', views.ProductDetailAPIView.as_view(), name='api_detail'),
    path('api/products/search/', views.search_products, name='api_search'),
    path('api/products/<int:pk>/overview/', views.product_overview, name='api_overview'),
    path('api/products/<int:pk>/sites/', views.product_sites, name='api_sites'),
    path('api/products/<int:pk>/variations/', views.product_variations, name='api_variations'),
    path('api/products/<int:pk>/source-document/', views.product_source_document_view, name='source_document'),
    path('api/products/<int:pk>/variations/add/', views.add_product_variation, name='api_add_variation'),
    path('api/cloud/setup/', views.setup_cloud_connection, name='api_cloud_setup'),
    path('api/cloud/oauth/initiate/', views.initiate_cloud_oauth, name='api_cloud_oauth_initiate'),
    path('api/products/<int:pk>/ectd/sync/', views.sync_ectd_files, name='api_sync_ectd'),
    path('api/products/<int:pk>/ectd/files/', views.product_ectd_files, name='api_ectd_files'),
    path('api/oauth/callback/', views.oauth_callback, name='oauth_callback'),
    path('api/products/<int:pk>/zip/<int:file_id>/structure/', views.get_zip_structure, name='api_zip_structure'),
    path('api/products/<int:pk>/ectd/delete/', views.delete_ectd_files, name='api_delete_ectd_files'),
    path('api/products/<int:pk>/pdf/<int:file_id>/view/', views.view_pdf_file, name='view_pdf_file'),

]