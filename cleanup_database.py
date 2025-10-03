#!/usr/bin/env python
"""
Script pour supprimer TOUS les documents et annotations de la base de données
ATTENTION: Cette opération est IRRÉVERSIBLE !

Usage:
    python cleanup_database.py

Ce script supprime:
- Tous les documents (RawDocument)
- Toutes les pages de documents (DocumentPage)
- Toutes les annotations (Annotation)
- Tous les produits (Product)
- Toutes les spécifications produits (ProductSpecification)
- Tous les sites de fabrication (ManufacturingSite)
- Toutes les variations produits (ProductVariation)
"""

import os
import sys
import django

# Configuration Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'MyProject.settings')
django.setup()

from rawdocs.models import RawDocument, DocumentPage, Annotation
from client.products.models import Product, ProductSpecification, ManufacturingSite, ProductVariation


def cleanup_all_data():
    """Supprime toutes les données de la base de données"""

    print("🚨 ATTENTION: Cette opération va supprimer TOUTES les données !")
    print("   - Tous les documents")
    print("   - Toutes les pages")
    print("   - Toutes les annotations")
    print("   - Tous les produits")
    print("   - Toutes les spécifications produits")
    print("   - Tous les sites de fabrication")
    print("   - Toutes les variations produits")
    print()

    # Demander confirmation
    confirmation = input("Êtes-vous sûr de vouloir continuer ? (tapez 'OUI' pour confirmer): ")

    if confirmation != 'OUI':
        print("❌ Opération annulée.")
        return

    try:
        # Compter les éléments avant suppression
        documents_count = RawDocument.objects.count()
        pages_count = DocumentPage.objects.count()
        annotations_count = Annotation.objects.count()
        products_count = Product.objects.count()
        specifications_count = ProductSpecification.objects.count()
        sites_count = ManufacturingSite.objects.count()
        variations_count = ProductVariation.objects.count()

        print(f"\n📊 Éléments à supprimer:")
        print(f"   - Documents: {documents_count}")
        print(f"   - Pages: {pages_count}")
        print(f"   - Annotations: {annotations_count}")
        print(f"   - Produits: {products_count}")
        print(f"   - Spécifications produits: {specifications_count}")
        print(f"   - Sites de fabrication: {sites_count}")
        print(f"   - Variations produits: {variations_count}")
        print()

        # Dernière confirmation
        final_confirmation = input("Dernière chance ! Tapez 'SUPPRIMER' pour confirmer: ")

        if final_confirmation != 'SUPPRIMER':
            print("❌ Opération annulée.")
            return

        print("\n🔄 Suppression en cours...")

        # Supprimer toutes les variations produits (dépendances)
        if variations_count > 0:
            ProductVariation.objects.all().delete()
            print(f"✅ Supprimé {variations_count} variations produits")

        # Supprimer tous les sites de fabrication (dépendances)
        if sites_count > 0:
            ManufacturingSite.objects.all().delete()
            print(f"✅ Supprimé {sites_count} sites de fabrication")

        # Supprimer toutes les spécifications produits (dépendances)
        if specifications_count > 0:
            ProductSpecification.objects.all().delete()
            print(f"✅ Supprimé {specifications_count} spécifications produits")

        # Supprimer tous les produits
        if products_count > 0:
            Product.objects.all().delete()
            print(f"✅ Supprimé {products_count} produits")

        # Supprimer toutes les annotations
        if annotations_count > 0:
            Annotation.objects.all().delete()
            print(f"✅ Supprimé {annotations_count} annotations")

        # Supprimer toutes les pages de documents
        if pages_count > 0:
            DocumentPage.objects.all().delete()
            print(f"✅ Supprimé {pages_count} pages de documents")

        # Supprimer tous les documents
        if documents_count > 0:
            RawDocument.objects.all().delete()
            print(f"✅ Supprimé {documents_count} documents")

        print("\n🎉 Base de données nettoyée avec succès !")
        print("   La base de données est maintenant vide.")

    except Exception as e:
        print(f"\n❌ Erreur lors du nettoyage: {e}")
        return False

    return True


if __name__ == "__main__":
    print("=" * 60)
    print("🧹 NETTOYAGE COMPLET DE LA BASE DE DONNÉES")
    print("=" * 60)

    cleanup_all_data()