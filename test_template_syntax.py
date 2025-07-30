#!/usr/bin/env python
"""
Script de test pour valider la syntaxe du template Django
"""
import os
import sys
import django
from django.conf import settings

# Configuration Django minimale
if not settings.configured:
    settings.configure(
        DEBUG=True,
        TEMPLATES=[{
            'BACKEND': 'django.template.backends.django.DjangoTemplates',
            'DIRS': ['templates'],
            'APP_DIRS': True,
            'OPTIONS': {
                'context_processors': [
                    'django.template.context_processors.debug',
                    'django.template.context_processors.request',
                    'django.contrib.auth.context_processors.auth',
                    'django.contrib.messages.context_processors.messages',
                ],
            },
        }],
        INSTALLED_APPS=[
            'django.contrib.auth',
            'django.contrib.contenttypes',
            'rawdocs',
        ],
    )

django.setup()

def test_template_syntax():
    """Test la syntaxe du template view_images.html"""
    try:
        from django.template.loader import get_template
        
        # Tester le template
        template = get_template('rawdocs/view_images.html')
        print("✅ Template 'rawdocs/view_images.html' - Syntaxe correcte")
        
        # Test avec un contexte minimal
        context = {
            'document': {'title': 'Test Document', 'id': 1},
            'images_count': 2,
            'images': [
                {
                    'image_id': 'img1',
                    'page': 1,
                    'width': 800,
                    'height': 600,
                    'format': 'PNG',
                    'size_bytes': 1024,
                    'preview_base64': 'test_base64_data'
                },
                {
                    'image_id': 'img2', 
                    'page': 2,
                    'width': 1024,
                    'height': 768,
                    'format': 'JPEG',
                    'size_bytes': 2048,
                    'preview_base64': 'test_base64_data2'
                }
            ]
        }
        
        # Rendu du template
        rendered = template.render(context)
        print("✅ Template rendu avec succès")
        print(f"📊 Taille du HTML généré: {len(rendered)} caractères")
        
        return True
        
    except Exception as e:
        print(f"❌ Erreur dans le template: {e}")
        return False

if __name__ == '__main__':
    print("🔍 Test de syntaxe du template Django...")
    success = test_template_syntax()
    
    if success:
        print("\n🎉 Tous les tests sont passés avec succès!")
        sys.exit(0)
    else:
        print("\n💥 Des erreurs ont été détectées!")
        sys.exit(1)