
from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('rawdocs.urls')),
    path('expert/', include('expert.urls')),
    path('client/', include('client.urls', namespace='client')),
    # Expose ctd_submission at project level so {% url 'ctd_submission:...' %} works
    path('client/submissions/', include(('client.submissions.ctd_submission.urls', 'ctd_submission'), namespace='ctd_submission')),
    path('chatbot/', include('chatbot.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
