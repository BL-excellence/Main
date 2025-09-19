from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.urls import path, include
from . import ai_views  
from django.views.generic import RedirectView

urlpatterns = [
    path('admin/ai-performance/', ai_views.ai_performance_hub, name='ai_performance_hub'),
    path('admin/ai-performance/metadata/', ai_views.metadata_learning_dashboard, name='metadata_learning_dashboard'),
    path('admin/', admin.site.urls),
    path('', include('rawdocs.urls')),
    path('expert/', include('expert.urls')),
    path('client/', include('client.urls', namespace='client')),
    path('client/submissions/', include(('client.submissions.ctd_submission.urls', 'ctd_submission'), namespace='ctd_submission')),
    path('chatbot/', include('chatbot.urls')),
    path('documents/', include(('documents.urls', 'documents'), namespace='documents')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)