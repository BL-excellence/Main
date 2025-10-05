from django.urls import path
from .views import chatbot_rag_api, index_document_api  
urlpatterns = [
    path('api/', chatbot_rag_api, name='chatbot_api'),
    path('index_document/', index_document_api, name='index_document_api'),  
]