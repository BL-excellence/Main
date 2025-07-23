from django.urls import path
from . import views

app_name = 'client_reports'

urlpatterns = [
    # Main dashboard
    path('', views.reports_dashboard, name='dashboard'),
    
    # Export functionality
    path('export/', views.export_data, name='export'),
    
    # Individual submission detail
    path('submission/<int:pk>/', views.submission_detail, name='submission_detail'),
    
    # Settings and create pages
    path('settings/', views.reports_settings, name='settings'),
    path('create/', views.reports_create, name='create'),
]