#!/usr/bin/env python3
"""
Script de test pour l'extraction avancée de métadonnées (tableaux et images)
"""

import os
import sys
import django
from pathlib import Path

# Configuration Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'MyProject.settings')
django.setup()

from rawdocs.utils import extract_tables_from_pdf, extract_images_from_pdf, extract_metadonnees

def test_extraction_functions():
    """Test des fonctions d'extraction"""
    print("🧪 Test des fonctions d'extraction avancée")
    print("=" * 50)
    
    # Chercher un fichier PDF de test dans le dossier media
    media_path = Path("media")
    pdf_files = []
    
    if media_path.exists():
        for pdf_file in media_path.rglob("*.pdf"):
            pdf_files.append(pdf_file)
            if len(pdf_files) >= 3:  # Limiter à 3 fichiers pour le test
                break
    
    if not pdf_files:
        print("❌ Aucun fichier PDF trouvé dans le dossier media pour les tests")
        print("💡 Veuillez uploader un document PDF via l'interface pour tester")
        return
    
    for i, pdf_file in enumerate(pdf_files, 1):
        print(f"\n📄 Test {i}: {pdf_file.name}")
        print("-" * 40)
        
        try:
            # Test extraction des tableaux
            print("📊 Extraction des tableaux...")
            tables = extract_tables_from_pdf(str(pdf_file))
            print(f"   ✅ {len(tables)} tableau(x) trouvé(s)")
            
            for j, table in enumerate(tables[:2], 1):  # Afficher max 2 tableaux
                print(f"   📋 Tableau {j}: {table['total_rows']} lignes × {table['total_columns']} colonnes (page {table['page']})")
            
            # Test extraction des images
            print("🖼️ Extraction des images...")
            images = extract_images_from_pdf(str(pdf_file))
            print(f"   ✅ {len(images)} image(s) trouvée(s)")
            
            for j, image in enumerate(images[:2], 1):  # Afficher max 2 images
                print(f"   🖼️ Image {j}: {image['width']}×{image['height']}px, {image['size_bytes']} bytes (page {image['page']})")
            
            # Test extraction complète des métadonnées
            print("🔍 Extraction complète des métadonnées...")
            metadata = extract_metadonnees(str(pdf_file), "")
            
            if metadata:
                print(f"   ✅ Métadonnées extraites:")
                print(f"   📝 Titre: {metadata.get('title', 'N/A')}")
                print(f"   📂 Type: {metadata.get('type', 'N/A')}")
                print(f"   🏢 Source: {metadata.get('source', 'N/A')}")
                
                # Informations sur les tableaux et images
                tables_info = metadata.get('tables', {})
                images_info = metadata.get('images', {})
                print(f"   📊 Tableaux: {tables_info.get('count', 0)}")
                print(f"   🖼️ Images: {images_info.get('count', 0)}")
                
                # Qualité de l'extraction
                quality = metadata.get('quality', {})
                if quality:
                    print(f"   📈 Qualité: {quality.get('extraction_rate', 0)}%")
                    enhanced = quality.get('enhanced_features', {})
                    if enhanced:
                        print(f"   🚀 Fonctionnalités avancées activées:")
                        print(f"      - Tableaux: {'✅' if enhanced.get('tables_extracted') else '❌'}")
                        print(f"      - Images: {'✅' if enhanced.get('images_extracted') else '❌'}")
            else:
                print("   ❌ Échec de l'extraction des métadonnées")
                
        except Exception as e:
            print(f"   ❌ Erreur lors du test: {str(e)}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "=" * 50)
    print("🎉 Tests terminés!")

def test_django_integration():
    """Test de l'intégration Django"""
    print("\n🔧 Test de l'intégration Django")
    print("=" * 50)
    
    try:
        from rawdocs.models import RawDocument
        from django.contrib.auth.models import User
        
        # Compter les documents existants
        doc_count = RawDocument.objects.count()
        user_count = User.objects.count()
        
        print(f"📊 Documents dans la base: {doc_count}")
        print(f"👥 Utilisateurs dans la base: {user_count}")
        
        # Tester les nouvelles URLs
        from django.urls import reverse
        
        if doc_count > 0:
            first_doc = RawDocument.objects.first()
            try:
                tables_url = reverse('rawdocs:view_extracted_tables', args=[first_doc.id])
                images_url = reverse('rawdocs:view_extracted_images', args=[first_doc.id])
                print(f"✅ URL tableaux: {tables_url}")
                print(f"✅ URL images: {images_url}")
            except Exception as e:
                print(f"❌ Erreur URLs: {e}")
        else:
            print("💡 Aucun document pour tester les URLs")
            
    except Exception as e:
        print(f"❌ Erreur intégration Django: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("🚀 Démarrage des tests d'extraction avancée")
    print("=" * 60)
    
    test_extraction_functions()
    test_django_integration()
    
    print("\n✨ Tests terminés avec succès!")