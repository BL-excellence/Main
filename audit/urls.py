# audit/urls.py
from django.urls import path
from . import views

app_name = 'audit'

urlpatterns = [
    path('trail/', views.audit_trail, name='trail'),
    path('trail/<int:document_id>/', views.document_audit_trail, name='document_trail'),
    path('export/', views.export_audit, name='export'),
]