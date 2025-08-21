# management/commands/init_ctd_structure.py
# Commande pour initialiser la structure CTD complète

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from ctd_submission.models import CTDModule, CTDSection
import json

from ctd_submission.views import DocumentValidator


class Command(BaseCommand):
    help = 'Initialise la structure CTD complète avec tous les modules et sections'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force la re-création même si la structure existe déjà'
        )
        parser.add_argument(
            '--region',
            type=str,
            choices=['EU', 'US', 'ICH'],
            default='ICH',
            help='Structure CTD selon la région (par défaut: ICH)'
        )
        parser.add_argument(
            '--import-file',
            type=str,
            help='Importer la structure depuis un fichier JSON'
        )

    def handle(self, *args, **options):
        force = options['force']
        region = options['region']
        import_file = options.get('import_file')

        # Vérifier si la structure existe déjà
        if CTDModule.objects.exists() and not force:
            self.stdout.write(
                self.style.WARNING(
                    'La structure CTD existe déjà. Utilisez --force pour la recréer.'
                )
            )
            return

        try:
            with transaction.atomic():
                if force:
                    self.stdout.write('Suppression de la structure existante...')
                    CTDSection.objects.all().delete()
                    CTDModule.objects.all().delete()

                if import_file:
                    self._import_from_file(import_file)
                else:
                    self._create_default_structure(region)

                self.stdout.write(
                    self.style.SUCCESS(f'Structure CTD {region} créée avec succès!')
                )

        except Exception as e:
            raise CommandError(f'Erreur lors de la création: {e}')

    def _import_from_file(self, filepath):
        """Importe la structure depuis un fichier JSON"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)

            for module_data in data:
                module = CTDModule.objects.create(
                    code=module_data['code'],
                    name=module_data['name'],
                    description=module_data.get('description', '')
                )

                for section_data in module_data.get('sections', []):
                    CTDSection.objects.create(
                        module=module,
                        code=section_data['code'],
                        name=section_data['name'],
                        description=section_data.get('description', ''),
                        order=section_data.get('order', 0)
                    )

                self.stdout.write(f'Module {module.code} créé avec {len(module_data.get("sections", []))} sections')

        except FileNotFoundError:
            raise CommandError(f'Fichier {filepath} non trouvé')
        except json.JSONDecodeError as e:
            raise CommandError(f'Erreur JSON dans {filepath}: {e}')

    def _create_default_structure(self, region):
        """Crée la structure par défaut selon la région"""

        if region == 'ICH':
            structure = self._get_ich_structure()
        elif region == 'EU':
            structure = self._get_eu_structure()
        elif region == 'US':
            structure = self._get_us_structure()

        for module_data in structure:
            module = CTDModule.objects.create(
                code=module_data['code'],
                name=module_data['name'],
                description=module_data['description']
            )

            for section_data in module_data['sections']:
                CTDSection.objects.create(
                    module=module,
                    code=section_data['code'],
                    name=section_data['name'],
                    description=section_data.get('description', ''),
                    order=section_data['order']
                )

            self.stdout.write(f'Module {module.code} créé avec {len(module_data["sections"])} sections')

    def _get_ich_structure(self):
        """Structure CTD standard ICH"""
        return [
            {
                'code': 'M1',
                'name': 'Module 1 - Administrative Information',
                'description': 'Administrative information and product information',
                'sections': [
                    {'code': '1.1', 'name': 'Cover Letter', 'order': 1},
                    {'code': '1.2', 'name': 'Comprehensive Table of Contents', 'order': 2},
                    {'code': '1.3', 'name': 'Application Form', 'order': 3},
                    {'code': '1.4', 'name': 'Product Information', 'order': 4},
                ]
            },
            {
                'code': 'M2',
                'name': 'Module 2 - Summaries',
                'description': 'Quality, nonclinical and clinical summaries',
                'sections': [
                    {'code': '2.1', 'name': 'Table of Contents', 'order': 1},
                    {'code': '2.2', 'name': 'Introduction', 'order': 2},
                    {'code': '2.3', 'name': 'Quality Overall Summary', 'order': 3},
                    {'code': '2.4', 'name': 'Nonclinical Overview', 'order': 4},
                    {'code': '2.5', 'name': 'Clinical Overview', 'order': 5},
                    {'code': '2.6', 'name': 'Nonclinical Summaries', 'order': 6},
                    {'code': '2.7', 'name': 'Clinical Summary', 'order': 7},
                ]
            },
            {
                'code': 'M3',
                'name': 'Module 3 - Quality',
                'description': 'Quality information',
                'sections': [
                    {'code': '3.1', 'name': 'Table of Contents', 'order': 1},
                    {'code': '3.2', 'name': 'Body of Data', 'order': 2},
                ]
            },
            {
                'code': 'M4',
                'name': 'Module 4 - Nonclinical Study Reports',
                'description': 'Nonclinical study reports',
                'sections': [
                    {'code': '4.1', 'name': 'Table of Contents', 'order': 1},
                    {'code': '4.2', 'name': 'Study Reports', 'order': 2},
                ]
            },
            {
                'code': 'M5',
                'name': 'Module 5 - Clinical Study Reports',
                'description': 'Clinical study reports',
                'sections': [
                    {'code': '5.1', 'name': 'Table of Contents', 'order': 1},
                    {'code': '5.2', 'name': 'Tabulated Summaries', 'order': 2},
                    {'code': '5.3', 'name': 'Clinical Study Reports', 'order': 3},
                    {'code': '5.4', 'name': 'Literature References', 'order': 4},
                ]
            }
        ]

    def _get_eu_structure(self):
        """Structure CTD spécifique EMA"""
        # Version étendue avec sections EMA spécifiques
        return self._get_ich_structure()  # Base ICH avec extensions

    def _get_us_structure(self):
        """Structure CTD spécifique FDA"""
        # Version adaptée FDA
        return self._get_ich_structure()  # Base ICH avec adaptations


# management/commands/analyze_documents.py
# Commande pour analyser des documents en lot

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from ctd_submission.models import Document, Submission
from ctd_submission.tasks import analyze_document_async, batch_analyze_documents
import time


class Command(BaseCommand):
    help = 'Analyse des documents avec IA en lot'

    def add_arguments(self, parser):
        parser.add_argument(
            '--submission-id',
            type=int,
            help='Analyser seulement les documents de cette soumission'
        )
        parser.add_argument(
            '--unanalyzed-only',
            action='store_true',
            help='Analyser seulement les documents non encore analysés'
        )
        parser.add_argument(
            '--low-confidence',
            action='store_true',
            help='Re-analyser les documents avec faible confiance (<60%)'
        )
        parser.add_argument(
            '--analysis-type',
            choices=['standard', 'enhanced'],
            default='standard',
            help='Type d\'analyse (standard ou enhanced avec Mistral)'
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=10,
            help='Nombre de documents à traiter par lot'
        )
        parser.add_argument(
            '--async',
            action='store_true',
            help='Lancer l\'analyse en arrière-plan avec Celery'
        )

    def handle(self, *args, **options):
        # Construire la requête
        queryset = Document.objects.all()

        if options['submission_id']:
            queryset = queryset.filter(submission_id=options['submission_id'])

        if options['unanalyzed_only']:
            queryset = queryset.filter(ai_analysis__isnull=True)

        if options['low_confidence']:
            queryset = queryset.filter(ai_analysis__confidence_score__lt=0.6)

        documents = list(queryset.select_related('submission', 'ai_analysis'))

        if not documents:
            self.stdout.write(
                self.style.WARNING('Aucun document à analyser trouvé.')
            )
            return

        self.stdout.write(f'Analyse de {len(documents)} document(s)...')

        if options['async']:
            self._analyze_async(documents, options)
        else:
            self._analyze_sync(documents, options)

    def _analyze_async(self, documents, options):
        """Analyse asynchrone avec Celery"""
        batch_size = options['batch_size']
        analysis_type = options['analysis_type']

        # Diviser en lots
        batches = [documents[i:i + batch_size] for i in range(0, len(documents), batch_size)]

        self.stdout.write(f'Lancement de {len(batches)} lot(s) d\'analyse asynchrone...')

        for i, batch in enumerate(batches):
            document_ids = [doc.id for doc in batch]

            task = batch_analyze_documents.delay(document_ids, analysis_type)

            self.stdout.write(
                f'Lot {i + 1}/{len(batches)} lancé (Task ID: {task.id})'
            )

        self.stdout.write(
            self.style.SUCCESS(
                f'Toutes les tâches d\'analyse ont été lancées. '
                f'Surveillez les logs Celery pour le suivi.'
            )
        )

    def _analyze_sync(self, documents, options):
        """Analyse synchrone"""
        from ctd_submission.utils import CTDAnalyzer

        analyzer = CTDAnalyzer()
        analysis_type = options['analysis_type']

        success_count = 0
        error_count = 0

        for i, document in enumerate(documents, 1):
            self.stdout.write(f'Analyse {i}/{len(documents)}: {document.name}')

            try:
                if analysis_type == 'enhanced':
                    # Lancer l'analyse enhanced de manière synchrone
                    task = analyze_document_async.apply(args=[document.id, 'enhanced'])
                    result = task.get()  # Attendre le résultat
                else:
                    # Analyse standard
                    result = analyzer.analyze_document(document)

                if result:
                    success_count += 1
                    confidence = result.get('confidence', 0)
                    section = result.get('section', {}).get('name', 'Non déterminée') if isinstance(
                        result.get('section'), dict) else 'Non déterminée'
                    self.stdout.write(
                        f'  ✓ Confiance: {confidence:.1%}, Section: {section}'
                    )
                else:
                    error_count += 1
                    self.stdout.write('  ✗ Échec de l\'analyse')

            except Exception as e:
                error_count += 1
                self.stdout.write(f'  ✗ Erreur: {e}')

        self.stdout.write(
            self.style.SUCCESS(
                f'Analyse terminée: {success_count} succès, {error_count} erreurs'
            )
        )


# management/commands/validate_submissions.py
# Commande pour valider les soumissions

from django.core.management.base import BaseCommand
from django.db.models import Count, Q
from ctd_submission.models import Submission, Document

import csv
from datetime import datetime


class Command(BaseCommand):
    help = 'Valide les soumissions et génère un rapport'

    def add_arguments(self, parser):
        parser.add_argument(
            '--submission-id',
            type=int,
            help='Valider une soumission spécifique'
        )
        parser.add_argument(
            '--status',
            choices=['draft', 'in_progress', 'completed', 'submitted'],
            help='Valider seulement les soumissions avec ce statut'
        )
        parser.add_argument(
            '--export-csv',
            type=str,
            help='Exporter le rapport en CSV vers ce fichier'
        )
        parser.add_argument(
            '--detailed',
            action='store_true',
            help='Rapport détaillé avec tous les erreurs et avertissements'
        )

    def handle(self, *args, **options):
        # Construire la requête
        queryset = Submission.objects.all()

        if options['submission_id']:
            queryset = queryset.filter(id=options['submission_id'])

        if options['status']:
            queryset = queryset.filter(status=options['status'])

        submissions = queryset.prefetch_related('documents').annotate(
            documents_count=Count('documents')
        )

        if not submissions.exists():
            self.stdout.write(
                self.style.WARNING('Aucune soumission à valider trouvée.')
            )
            return

        validator = DocumentValidator()
        validation_results = []

        self.stdout.write(f'Validation de {submissions.count()} soumission(s)...')

        for submission in submissions:
            self.stdout.write(f'\n=== {submission.name} ===')

            documents = submission.documents.all()
            document_results = []

            total_errors = 0
            total_warnings = 0
            valid_documents = 0

            for document in documents:
                self.stdout.write(f'  Validation: {document.name}')

                result = validator.validate_document(document)

                if result['is_valid']:
                    valid_documents += 1
                    self.stdout.write('    ✓ Valide')
                else:
                    self.stdout.write(f'    ✗ {len(result["errors"])} erreur(s)')

                total_errors += len(result['errors'])
                total_warnings += len(result['warnings'])

                document_results.append({
                    'document': document,
                    'result': result
                })

                # Affichage détaillé si demandé
                if options['detailed']:
                    for error in result['errors']:
                        self.stdout.write(f'      ERREUR: {error}')
                    for warning in result['warnings']:
                        self.stdout.write(f'      ATTENTION: {warning}')

            # Score global de la soumission
            overall_score = (valid_documents / len(documents)) * 100 if documents else 0

            submission_result = {
                'submission': submission,
                'overall_score': overall_score,
                'total_documents': len(documents),
                'valid_documents': valid_documents,
                'total_errors': total_errors,
                'total_warnings': total_warnings,
                'document_results': document_results
            }

            validation_results.append(submission_result)

            # Résumé pour cette soumission
            status_color = self.style.SUCCESS if overall_score >= 80 else \
                self.style.WARNING if overall_score >= 60 else \
                    self.style.ERROR

            self.stdout.write(
                status_color(
                    f'  Score global: {overall_score:.1f}% ({valid_documents}/{len(documents)} documents valides)')
            )

        # Export CSV si demandé
        if options['export_csv']:
            self._export_to_csv(validation_results, options['export_csv'])

        # Résumé global
        self._print_global_summary(validation_results)

    def _export_to_csv(self, validation_results, filepath):
        """Exporte les résultats en CSV"""
        try:
            with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)

                # En-têtes
                writer.writerow([
                    'Soumission', 'Région', 'Statut', 'Score Global (%)',
                    'Documents Total', 'Documents Valides', 'Erreurs', 'Avertissements',
                    'Date Création', 'Créé Par'
                ])

                # Données
                for result in validation_results:
                    submission = result['submission']
                    writer.writerow([
                        submission.name,
                        submission.region,
                        submission.status,
                        f"{result['overall_score']:.1f}",
                        result['total_documents'],
                        result['valid_documents'],
                        result['total_errors'],
                        result['total_warnings'],
                        submission.created_at.strftime('%Y-%m-%d'),
                        submission.created_by.username
                    ])

            self.stdout.write(
                self.style.SUCCESS(f'Rapport exporté vers {filepath}')
            )

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Erreur lors de l\'export: {e}')
            )

    def _print_global_summary(self, validation_results):
        """Affiche le résumé global"""
        if not validation_results:
            return

        total_submissions = len(validation_results)
        total_documents = sum(r['total_documents'] for r in validation_results)
        total_valid_documents = sum(r['valid_documents'] for r in validation_results)
        total_errors = sum(r['total_errors'] for r in validation_results)
        total_warnings = sum(r['total_warnings'] for r in validation_results)

        excellent_submissions = sum(1 for r in validation_results if r['overall_score'] >= 90)
        good_submissions = sum(1 for r in validation_results if 70 <= r['overall_score'] < 90)
        poor_submissions = sum(1 for r in validation_results if r['overall_score'] < 70)

        self.stdout.write('\n' + '=' * 50)
        self.stdout.write(self.style.SUCCESS('RÉSUMÉ GLOBAL'))
        self.stdout.write('=' * 50)
        self.stdout.write(f'Soumissions analysées: {total_submissions}')
        self.stdout.write(f'Documents total: {total_documents}')
        self.stdout.write(
            f'Documents valides: {total_valid_documents} ({(total_valid_documents / total_documents) * 100:.1f}%)')
        self.stdout.write(f'Erreurs total: {total_errors}')
        self.stdout.write(f'Avertissements total: {total_warnings}')
        self.stdout.write('')
        self.stdout.write('Répartition par qualité:')
        self.stdout.write(f'  Excellentes (≥90%): {excellent_submissions}')
        self.stdout.write(f'  Bonnes (70-89%): {good_submissions}')
        self.stdout.write(f'  À améliorer (<70%): {poor_submissions}')


# management/commands/maintenance.py
# Commande de maintenance générale

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db.models import Count
from ctd_submission.models import Document, DocumentVersion, Submission, AIAnalysisResult
from ctd_submission.tasks import cleanup_old_versions, daily_maintenance
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Effectue la maintenance du système CTD'

    def add_arguments(self, parser):
        parser.add_argument(
            '--cleanup-versions',
            action='store_true',
            help='Nettoie les anciennes versions de documents'
        )
        parser.add_argument(
            '--days-old',
            type=int,
            default=30,
            help='Nombre de jours pour considérer une version comme ancienne'
        )
        parser.add_argument(
            '--stats',
            action='store_true',
            help='Affiche les statistiques du système'
        )
        parser.add_argument(
            '--full-maintenance',
            action='store_true',
            help='Lance la maintenance complète (équivalent à la tâche quotidienne)'
        )
        parser.add_argument(
            '--async',
            action='store_true',
            help='Lance les tâches en arrière-plan'
        )

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS('=== Maintenance CTD Submission System ===')
        )

        if options['stats']:
            self._show_stats()

        if options['cleanup_versions']:
            if options['async']:
                task = cleanup_old_versions.delay(options['days_old'])
                self.stdout.write(f'Nettoyage lancé en arrière-plan (Task ID: {task.id})')
            else:
                self._cleanup_versions_sync(options['days_old'])

        if options['full_maintenance']:
            if options['async']:
                task = daily_maintenance.delay()
                self.stdout.write(f'Maintenance complète lancée (Task ID: {task.id})')
            else:
                self._full_maintenance_sync()

        self.stdout.write(
            self.style.SUCCESS('Maintenance terminée!')
        )

    def _show_stats(self):
        """Affiche les statistiques du système"""
        self.stdout.write('\n--- STATISTIQUES SYSTÈME ---')

        # Statistiques générales
        total_submissions = Submission.objects.count()
        total_documents = Document.objects.count()
        total_versions = DocumentVersion.objects.count()
        total_ai_analyses = AIAnalysisResult.objects.count()

        self.stdout.write(f'Soumissions: {total_submissions}')
        self.stdout.write(f'Documents: {total_documents}')
        self.stdout.write(f'Versions: {total_versions}')
        self.stdout.write(f'Analyses IA: {total_ai_analyses}')

        # Répartition par statut
        self.stdout.write('\n--- RÉPARTITION PAR STATUT ---')
        for status_data in Submission.objects.values('status').annotate(count=Count('id')):
            self.stdout.write(f'{status_data["status"]}: {status_data["count"]}')

        # Répartition par région
        self.stdout.write('\n--- RÉPARTITION PAR RÉGION ---')
        for region_data in Submission.objects.values('region').annotate(count=Count('id')):
            self.stdout.write(f'{region_data["region"]}: {region_data["count"]}')

        # Documents avec template
        template_docs = Document.objects.filter(is_template_generated=True).count()
        self.stdout.write(
            f'\nDocuments avec template: {template_docs}/{total_documents} ({(template_docs / total_documents) * 100:.1f}%)')

        # Analyses IA par confiance
        self.stdout.write('\n--- CONFIANCE ANALYSES IA ---')
        high_confidence = AIAnalysisResult.objects.filter(confidence_score__gte=0.8).count()
        medium_confidence = AIAnalysisResult.objects.filter(confidence_score__gte=0.6, confidence_score__lt=0.8).count()
        low_confidence = AIAnalysisResult.objects.filter(confidence_score__lt=0.6).count()

        self.stdout.write(f'Confiance élevée (≥80%): {high_confidence}')
        self.stdout.write(f'Confiance moyenne (60-79%): {medium_confidence}')
        self.stdout.write(f'Confiance faible (<60%): {low_confidence}')

    def _cleanup_versions_sync(self, days_old):
        """Nettoyage synchrone des versions"""
        cutoff_date = timezone.now() - timezone.timedelta(days=days_old)

        old_versions = DocumentVersion.objects.filter(
            created_at__lt=cutoff_date,
            is_current=False
        ).exclude(version_number=1)

        deleted_count = 0
        for version in old_versions:
            newer_versions = DocumentVersion.objects.filter(
                document=version.document,
                version_number__gt=version.version_number
            ).count()

            if newer_versions >= 2:
                version.delete()
                deleted_count += 1

        self.stdout.write(f'Versions supprimées: {deleted_count}')

    def _full_maintenance_sync(self):
        """Maintenance complète synchrone"""
        self.stdout.write('Lancement de la maintenance complète...')

        # Nettoyage des versions
        self._cleanup_versions_sync(30)

        # Autres tâches de maintenance
        self.stdout.write('Maintenance complète terminée')


# management/commands/export_structure.py
# Commande pour exporter la structure CTD

from django.core.management.base import BaseCommand
from ctd_submission.models import CTDModule, CTDSection
import json


class Command(BaseCommand):
    help = 'Exporte la structure CTD vers un fichier JSON'

    def add_arguments(self, parser):
        parser.add_argument(
            'output_file',
            type=str,
            help='Fichier de sortie JSON'
        )
        parser.add_argument(
            '--pretty',
            action='store_true',
            help='Formatage JSON indenté'
        )

    def handle(self, *args, **options):
        modules = CTDModule.objects.prefetch_related('sections').all()

        structure = []
        for module in modules:
            module_data = {
                'code': module.code,
                'name': module.name,
                'description': module.description,
                'sections': []
            }

            for section in module.sections.all().order_by('order', 'code'):
                section_data = {
                    'code': section.code,
                    'name': section.name,
                    'description': section.description,
                    'order': section.order
                }
                module_data['sections'].append(section_data)

            structure.append(module_data)

        # Écrire le fichier
        try:
            with open(options['output_file'], 'w', encoding='utf-8') as f:
                if options['pretty']:
                    json.dump(structure, f, indent=2, ensure_ascii=False)
                else:
                    json.dump(structure, f, ensure_ascii=False)

            self.stdout.write(
                self.style.SUCCESS(
                    f'Structure CTD exportée vers {options["output_file"]}'
                )
            )

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Erreur lors de l\'export: {e}')
            )