from django.urls import path, include
from . import views

app_name = 'client'

urlpatterns = [
    path('', views.client_dashboard, name='dashboard'),
    path('library/', include('client.library.urls', namespace='library')),
    path('products/', include('client.products.urls', namespace='products')),
    path('reports/', include('client.reports.urls', namespace='reports')),
    # Nested namespace so templates can reverse 'client:ctd_submission:...'
    path('submissions/', include(('client.submissions.ctd_submission.urls', 'ctd_submission'), namespace='ctd_submission')),
]