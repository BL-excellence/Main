from django.core.management.base import BaseCommand
from django.db import transaction
from rawdocs.models import RawDocument, DocumentPage, Annotation
from client.products.models import Product, ProductSpecification, ManufacturingSite, ProductVariation


class Command(BaseCommand):
    help = 'Supprime TOUS les documents, annotations et produits de la base de données'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force la suppression sans demander de confirmation',
        )

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.WARNING('🚨 ATTENTION: Cette opération va supprimer TOUTES les données !')
        )
        self.stdout.write('   - Tous les documents')
        self.stdout.write('   - Toutes les pages')
        self.stdout.write('   - Toutes les annotations')
        self.stdout.write('   - Tous les produits')
        self.stdout.write('   - Toutes les spécifications produits')
        self.stdout.write('   - Tous les sites de fabrication')
        self.stdout.write('   - Toutes les variations produits')
        self.stdout.write('')

        # Compter les éléments avant suppression
        documents_count = RawDocument.objects.count()
        pages_count = DocumentPage.objects.count()
        annotations_count = Annotation.objects.count()
        products_count = Product.objects.count()
        specifications_count = ProductSpecification.objects.count()
        sites_count = ManufacturingSite.objects.count()
        variations_count = ProductVariation.objects.count()

        self.stdout.write(f"📊 Éléments à supprimer:")
        self.stdout.write(f"   - Documents: {documents_count}")
        self.stdout.write(f"   - Pages: {pages_count}")
        self.stdout.write(f"   - Annotations: {annotations_count}")
        self.stdout.write(f"   - Produits: {products_count}")
        self.stdout.write(f"   - Spécifications produits: {specifications_count}")
        self.stdout.write(f"   - Sites de fabrication: {sites_count}")
        self.stdout.write(f"   - Variations produits: {variations_count}")
        self.stdout.write('')

        if (documents_count == 0 and pages_count == 0 and annotations_count == 0 and 
            products_count == 0 and specifications_count == 0 and sites_count == 0 and variations_count == 0):
            self.stdout.write(
                self.style.SUCCESS('✅ La base de données est déjà vide !')
            )
            return

        # Demander confirmation si --force n'est pas utilisé
        if not options['force']:
            confirm = input("Êtes-vous sûr de vouloir continuer ? (tapez 'oui' pour confirmer): ")
            if confirm.lower() not in ['oui', 'yes', 'y']:
                self.stdout.write(
                    self.style.ERROR('❌ Opération annulée.')
                )
                return

        try:
            with transaction.atomic():
                self.stdout.write('🔄 Suppression en cours...')

                # Supprimer toutes les variations produits (dépendances)
                if variations_count > 0:
                    ProductVariation.objects.all().delete()
                    self.stdout.write(
                        self.style.SUCCESS(f'✅ Supprimé {variations_count} variations produits')
                    )

                # Supprimer tous les sites de fabrication (dépendances)
                if sites_count > 0:
                    ManufacturingSite.objects.all().delete()
                    self.stdout.write(
                        self.style.SUCCESS(f'✅ Supprimé {sites_count} sites de fabrication')
                    )

                # Supprimer toutes les spécifications produits (dépendances)
                if specifications_count > 0:
                    ProductSpecification.objects.all().delete()
                    self.stdout.write(
                        self.style.SUCCESS(f'✅ Supprimé {specifications_count} spécifications produits')
                    )

                # Supprimer tous les produits
                if products_count > 0:
                    Product.objects.all().delete()
                    self.stdout.write(
                        self.style.SUCCESS(f'✅ Supprimé {products_count} produits')
                    )

                # Supprimer toutes les annotations
                if annotations_count > 0:
                    Annotation.objects.all().delete()
                    self.stdout.write(
                        self.style.SUCCESS(f'✅ Supprimé {annotations_count} annotations')
                    )

                # Supprimer toutes les pages de documents
                if pages_count > 0:
                    DocumentPage.objects.all().delete()
                    self.stdout.write(
                        self.style.SUCCESS(f'✅ Supprimé {pages_count} pages de documents')
                    )

                # Supprimer tous les documents
                if documents_count > 0:
                    RawDocument.objects.all().delete()
                    self.stdout.write(
                        self.style.SUCCESS(f'✅ Supprimé {documents_count} documents')
                    )

                self.stdout.write('')
                self.stdout.write(
                    self.style.SUCCESS('🎉 Base de données nettoyée avec succès !')
                )
                self.stdout.write('   La base de données est maintenant vide.')

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ Erreur lors du nettoyage: {e}')
            )
            raise