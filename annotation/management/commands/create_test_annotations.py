# annotation/management/commands/create_test_annotations.py
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from annotation.models import Annotation, EntityType
from documents.models import Document
import random

User = get_user_model()


class Command(BaseCommand):
    help = 'Créer des annotations de test pour un document'

    def add_arguments(self, parser):
        parser.add_argument(
            '--document-id',
            type=int,
            help='ID du document à annoter'
        )
        parser.add_argument(
            '--count',
            type=int,
            default=10,
            help='Nombre d\'annotations à créer'
        )

    def handle(self, *args, **options):
        document_id = options.get('document_id')
        count = options.get('count', 10)

        # Si pas de document spécifié, prendre le premier
        if document_id:
            try:
                document = Document.objects.get(id=document_id)
            except Document.DoesNotExist:
                self.stdout.write(self.style.ERROR(f'Document {document_id} introuvable'))
                return
        else:
            document = Document.objects.first()
            if not document:
                self.stdout.write(self.style.ERROR('Aucun document trouvé'))
                return

        # Récupérer les types d'entités
        entity_types = list(EntityType.objects.all())
        if not entity_types:
            self.stdout.write(
                self.style.ERROR('Aucun type d\'entité trouvé. Lancez d\'abord: python manage.py create_entity_types'))
            return

        # Récupérer un utilisateur
        user = User.objects.filter(is_superuser=True).first()
        if not user:
            user = User.objects.first()
            if not user:
                self.stdout.write(self.style.ERROR('Aucun utilisateur trouvé'))
                return

        # Exemples de textes à annoter
        sample_annotations = [
            # Médicaments
            {'text': 'paracétamol 500mg', 'type': 'MÉDICAMENT'},
            {'text': 'amoxicilline', 'type': 'MÉDICAMENT'},
            {'text': 'insuline glargine', 'type': 'MÉDICAMENT'},
            {'text': 'metformine 850mg', 'type': 'MÉDICAMENT'},

            # Maladies
            {'text': 'diabète de type 2', 'type': 'MALADIE'},
            {'text': 'hypertension artérielle', 'type': 'MALADIE'},
            {'text': 'pneumonie', 'type': 'MALADIE'},
            {'text': 'syndrome métabolique', 'type': 'MALADIE'},

            # Symptômes
            {'text': 'céphalées', 'type': 'SYMPTÔME'},
            {'text': 'nausées', 'type': 'SYMPTÔME'},
            {'text': 'fatigue chronique', 'type': 'SYMPTÔME'},

            # Dosages
            {'text': '2 comprimés par jour', 'type': 'DOSAGE'},
            {'text': '10mg/kg', 'type': 'DOSAGE'},
            {'text': 'trois fois par jour', 'type': 'DOSAGE'},

            # Organisations
            {'text': 'Laboratoire Pfizer', 'type': 'ORGANISATION'},
            {'text': 'CHU de Toulouse', 'type': 'ORGANISATION'},
            {'text': 'ANSM', 'type': 'ORGANISATION'},

            # Dates
            {'text': '15 janvier 2024', 'type': 'DATE'},
            {'text': '2023-2024', 'type': 'DATE'},
            {'text': 'mars 2024', 'type': 'DATE'},

            # Pourcentages
            {'text': '85%', 'type': 'POURCENTAGE'},
            {'text': '15,5%', 'type': 'POURCENTAGE'},
            {'text': '90 pour cent', 'type': 'POURCENTAGE'},
        ]

        created_count = 0
        position = 0

        for i in range(count):
            # Sélectionner une annotation aléatoire
            sample = random.choice(sample_annotations)

            # Trouver le type d'entité
            entity_type = None
            for et in entity_types:
                if et.name == sample['type']:
                    entity_type = et
                    break

            if not entity_type:
                continue

            # Créer l'annotation avec des positions fictives
            text = sample['text']
            start_pos = position
            end_pos = position + len(text)
            position = end_pos + random.randint(10, 50)  # Espacement aléatoire

            try:
                annotation = Annotation.objects.create(
                    document=document,
                    entity_type=entity_type,
                    text=text,
                    start_position=start_pos,
                    end_position=end_pos,
                    created_by=user,
                    is_automatic=random.choice([True, False]),
                    confidence_score=random.uniform(0.6, 1.0),
                    status=random.choice(['detected', 'validated', 'modified'])
                )
                created_count += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f'✓ Créé: "{text}" ({entity_type.name}) à la position {start_pos}-{end_pos}'
                    )
                )
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'✗ Erreur: {e}')
                )

        self.stdout.write(
            self.style.SUCCESS(
                f'\nTerminé! {created_count} annotations créées pour le document "{document.title}"'
            )
        )