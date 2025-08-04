#!/usr/bin/env python
"""
Script de test pour vérifier les fonctionnalités d'upload client
"""
import os
import sys
import django
from django.conf import settings

# Configuration Django
if __name__ == "__main__":
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'MyProject.settings')
    django.setup()

from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from rawdocs.models import RawDocument
from django.core.files.uploadedfile import SimpleUploadedFile

def test_client_upload_functionality():
    """Test des fonctionnalités d'upload client"""
    print("Test des fonctionnalites d'upload client...")
    
    # Test 1: Vérification des URLs
    print("\n1. Test des URLs...")
    try:
        from django.urls import resolve
        
        # Test URL upload client
        url = '/client/library/client/upload/'
        resolver = resolve(url)
        print(f"OK URL {url} -> {resolver.view_name}")
        
        # Test URL liste documents client
        url = '/client/library/client/documents/'
        resolver = resolve(url)
        print(f"OK URL {url} -> {resolver.view_name}")
        
        # Test URL détail document client
        url = '/client/library/client/documents/1/'
        resolver = resolve(url)
        print(f"OK URL {url} -> {resolver.view_name}")
        
    except Exception as e:
        print(f"ERREUR URLs: {e}")
    
    # Test 2: Vérification des vues
    print("\n2. Test des vues...")
    try:
        from client.library.client_upload_views import (
            client_upload_document,
            client_document_detail,
            client_documents_list
        )
        print("OK Toutes les vues client sont importables")
    except Exception as e:
        print(f"ERREUR import vues: {e}")
    
    # Test 3: Vérification des templates
    print("\n3. Test des templates...")
    templates = [
        'templates/client/library/client_upload.html',
        'templates/client/library/client_document_detail.html',
        'templates/client/library/client_documents_list.html',
        'templates/client/library/confirm_delete.html'
    ]
    
    for template in templates:
        if os.path.exists(template):
            print(f"OK Template {template} existe")
        else:
            print(f"ERREUR Template {template} manquant")
    
    # Test 4: Vérification du modèle RawDocument
    print("\n4. Test du modèle RawDocument...")
    try:
        # Test création d'un document client
        user = User.objects.first()
        if user:
            doc = RawDocument(
                owner=user,
                source='Client',
                title='Test Document Client'
            )
            print("OK Modele RawDocument compatible avec source 'Client'")
        else:
            print("WARNING Aucun utilisateur trouve pour le test")
    except Exception as e:
        print(f"ERREUR modele: {e}")
    
    # Test 5: Vérification de la fonction d'upload
    print("\n5. Test de la fonction d'upload...")
    try:
        from rawdocs.models import pdf_upload_to
        from datetime import datetime
        
        # Simuler un document client
        class MockInstance:
            source = 'Client'
        
        instance = MockInstance()
        path = pdf_upload_to(instance, 'test.pdf')
        
        if path.startswith('Client/') or path.startswith('Client\\'):
            print(f"OK Chemin d'upload client correct: {path}")
        else:
            print(f"ERREUR Chemin d'upload incorrect: {path}")
            
    except Exception as e:
        print(f"ERREUR fonction upload: {e}")
    
    # Test 6: Vérification de l'intégration dashboard
    print("\n6. Test de l'intégration dashboard...")
    try:
        from client.library.views import library_dashboard
        print("OK Vue dashboard importable")
        
        # Vérifier que les documents clients sont inclus dans les statistiques
        docs_with_client_source = RawDocument.objects.filter(source='Client').count()
        print(f"OK {docs_with_client_source} document(s) client(s) trouve(s) en base")
        
    except Exception as e:
        print(f"ERREUR dashboard: {e}")
    
    print("\nTests termines!")
    return True

if __name__ == "__main__":
    test_client_upload_functionality()