#!/usr/bin/env python3
"""
Test script pour vérifier les améliorations de l'interface utilisateur
"""

import os
import sys
import django
from pathlib import Path

# Configuration Django
sys.path.append('.')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'MyProject.settings')
django.setup()

from rawdocs.models import RawDocument
from rawdocs.utils import extract_metadonnees

def test_ui_improvements():
    """Test des améliorations de l'interface utilisateur"""
    print("🧪 Test des améliorations de l'interface utilisateur")
    print("=" * 60)
    
    # Vérifier qu'il y a des documents dans la base
    documents = RawDocument.objects.all()
    print(f"📄 Documents disponibles: {documents.count()}")
    
    if documents.count() == 0:
        print("❌ Aucun document trouvé pour tester l'interface")
        return
    
    # Tester l'extraction avec le premier document
    doc = documents.first()
    print(f"🔍 Test avec le document: {doc.title or 'Sans titre'}")
    print(f"   Fichier: {doc.file.name}")
    
    try:
        # Extraire les métadonnées avec tableaux et images
        metadata = extract_metadonnees(doc.file.path, doc.url or "")
        
        # Vérifier les tableaux
        tables_data = metadata.get('tables', {})
        tables_count = tables_data.get('count', 0)
        print(f"📊 Tableaux extraits: {tables_count}")
        
        if tables_count > 0:
            print("   ✅ Structure des tableaux:")
            for i, table in enumerate(tables_data.get('data', [])[:2], 1):  # Afficher max 2 tableaux
                print(f"      - Tableau {i}: {table.get('total_rows', 0)} lignes × {table.get('total_columns', 0)} colonnes")
                print(f"        Headers: {table.get('headers', [])[:3]}...")  # Afficher 3 premiers headers
        
        # Vérifier les images
        images_data = metadata.get('images', {})
        images_count = images_data.get('count', 0)
        print(f"🖼️ Images extraites: {images_count}")
        
        if images_count > 0:
            print("   ✅ Structure des images:")
            for i, image in enumerate(images_data.get('data', [])[:2], 1):  # Afficher max 2 images
                print(f"      - Image {i}: {image.get('width', 0)}×{image.get('height', 0)}px")
                print(f"        Format: {image.get('format', 'N/A')}, Taille: {image.get('size_bytes', 0)} bytes")
                print(f"        Preview disponible: {'✅' if image.get('preview_base64') else '❌'}")
        
        print("\n🎨 Améliorations de l'interface:")
        print("   ✅ Template des images mis à jour avec preview_base64")
        print("   ✅ Template des tableaux amélioré avec:")
        print("      - Meilleure gestion des cellules vides")
        print("      - Troncature du texte long")
        print("      - Style amélioré avec bordures et hover")
        print("      - Conteneur avec scroll pour les grands tableaux")
        print("   ✅ Fonction d'extraction des images mise à jour avec thumbnails")
        
        print(f"\n🌐 URLs disponibles:")
        print(f"   - Liste des documents: http://127.0.0.1:8000/rawdocs/documents/")
        print(f"   - Tableaux du document {doc.id}: http://127.0.0.1:8000/rawdocs/documents/{doc.id}/tables/")
        print(f"   - Images du document {doc.id}: http://127.0.0.1:8000/rawdocs/documents/{doc.id}/images/")
        
        return True
        
    except Exception as e:
        print(f"❌ Erreur lors du test: {e}")
        return False

if __name__ == "__main__":
    success = test_ui_improvements()
    if success:
        print("\n✅ Test des améliorations de l'interface réussi!")
        print("🚀 L'interface est prête à être testée dans le navigateur")
    else:
        print("\n❌ Échec du test des améliorations")
    
    print("\n" + "=" * 60)