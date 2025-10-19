from django.core.management.base import BaseCommand
from django.db import transaction
from rawdocs.models import AnnotationType, Annotation


class Command(BaseCommand):
    help = 'Supprime tous les types d\'annotation personnalisés (non prédéfinis)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force la suppression sans demander de confirmation',
        )

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.WARNING('🚨 ATTENTION: Cette opération va supprimer tous les types d\'annotation personnalisés !')
        )
        self.stdout.write('   - Tous les types NON prédéfinis')
        self.stdout.write('   - Toutes les annotations associées')
        self.stdout.write('')

        # Compter les éléments avant suppression
        predefined_names = AnnotationType.get_predefined_type_names()
        custom_types = AnnotationType.objects.exclude(name__in=predefined_names)
        custom_count = custom_types.count()
        annotations_count = Annotation.objects.filter(annotation_type__in=custom_types).count()

        self.stdout.write(f"📊 Éléments à supprimer:")
        self.stdout.write(f"   - Types personnalisés: {custom_count}")
        self.stdout.write(f"   - Annotations associées: {annotations_count}")
        self.stdout.write('')

        if custom_count == 0:
            self.stdout.write(
                self.style.SUCCESS('✅ Aucun type personnalisé à supprimer !')
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

                # Supprimer les types personnalisés (les annotations seront supprimées en cascade)
                deleted_count = AnnotationType.delete_custom_types()

                self.stdout.write(
                    self.style.SUCCESS(f'✅ Supprimé {deleted_count} types d\'annotation personnalisés')
                )
                self.stdout.write(
                    self.style.SUCCESS(f'✅ Supprimé {annotations_count} annotations associées')
                )

                self.stdout.write('')
                self.stdout.write(
                    self.style.SUCCESS('🎉 Nettoyage des types personnalisés terminé !')
                )
                self.stdout.write('   Seuls les types prédéfinis restent disponibles.')

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'❌ Erreur lors du nettoyage: {e}')
            )
            raise