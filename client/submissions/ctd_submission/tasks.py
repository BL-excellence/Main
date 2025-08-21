# Chemin d'intégration : ctd_submission/tasks.py
# Tâches Celery pour l'application CTD submission

from celery import shared_task, current_task
from celery.exceptions import Retry
from django.core.mail import send_mail, EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.utils import timezone
from django.conf import settings
from django.db import transaction, models
from django.core.files.storage import default_storage
import os
import logging
import time
from datetime import datetime, timedelta
import json

from .models import Document, Submission, AIAnalysisResult, TemplateField
from .utils import CTDAnalyzer, DocumentProcessor

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def analyze_document(self, document_id):
    """
    Tâche asynchrone pour analyser un document avec l'IA
    """
    try:
        logger.info(f'Début de l\'analyse IA du document {document_id}')

        # Récupérer le document
        document = Document.objects.get(id=document_id)

        # Mettre à jour le statut de progression
        current_task.update_state(
            state='PROGRESS',
            meta={
                'current': 10,
                'total': 100,
                'status': 'Initialisation de l\'analyse...'
            }
        )

        # Initialiser l'analyseur
        analyzer = CTDAnalyzer()

        # Mise à jour du statut
        current_task.update_state(
            state='PROGRESS',
            meta={
                'current': 30,
                'total': 100,
                'status': 'Extraction des caractéristiques...'
            }
        )

        # Effectuer l'analyse
        analysis_result = analyzer.analyze_document(document)

        # Mise à jour du statut
        current_task.update_state(
            state='PROGRESS',
            meta={
                'current': 70,
                'total': 100,
                'status': 'Classification en cours...'
            }
        )

        if analysis_result:
            # Sauvegarder les résultats
            with transaction.atomic():
                ai_analysis, created = AIAnalysisResult.objects.update_or_create(
                    document=document,
                    defaults={
                        'suggested_module': analysis_result['module'],
                        'suggested_section': analysis_result['section'],
                        'confidence_score': analysis_result['confidence'],
                        'analysis_details': analysis_result['details'],
                        'keywords_found': analysis_result['keywords']
                    }
                )

                # Si la confiance est élevée, assigner automatiquement
                if analysis_result['confidence'] >= 0.8 and not document.section:
                    document.section = analysis_result['section']
                    document.save()

                    logger.info(f'Document {document.name} automatiquement assigné à {analysis_result["section"]}')

        # Mise à jour finale
        current_task.update_state(
            state='PROGRESS',
            meta={
                'current': 100,
                'total': 100,
                'status': 'Analyse terminée'
            }
        )

        logger.info(f'Analyse IA terminée pour le document {document_id}')

        return {
            'document_id': document_id,
            'confidence': analysis_result['confidence'] if analysis_result else 0,
            'module': analysis_result['module'].name if analysis_result else None,
            'section': analysis_result['section'].name if analysis_result else None,
        }

    except Document.DoesNotExist:
        logger.error(f'Document {document_id} non trouvé')
        raise

    except Exception as exc:
        logger.error(f'Erreur lors de l\'analyse du document {document_id}: {exc}')

        # Retry avec backoff exponentiel
        retry_count = self.request.retries
        countdown = 60 * (2 ** retry_count)  # 60s, 120s, 240s

        raise self.retry(exc=exc, countdown=countdown)


@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def extract_document_content(self, document_id):
    """
    Tâche asynchrone pour extraire le contenu d'un document
    """
    try:
        logger.info(f'Début de l\'extraction de contenu pour le document {document_id}')

        document = Document.objects.get(id=document_id)

        # Vérifier que le fichier existe
        if not document.file or not document.file.name:
            raise ValueError('Aucun fichier associé au document')

        # Mise à jour du statut
        current_task.update_state(
            state='PROGRESS',
            meta={
                'current': 20,
                'total': 100,
                'status': 'Lecture du fichier...'
            }
        )

        # Initialiser le processeur
        processor = DocumentProcessor()

        # Mise à jour du statut
        current_task.update_state(
            state='PROGRESS',
            meta={
                'current': 50,
                'total': 100,
                'status': 'Extraction en cours...'
            }
        )

        # Extraire le contenu
        extracted_content = processor.extract_content(document)

        # Mise à jour du statut
        current_task.update_state(
            state='PROGRESS',
            meta={
                'current': 80,
                'total': 100,
                'status': 'Sauvegarde...'
            }
        )

        # Sauvegarder le contenu extrait
        document.content_extracted = extracted_content
        document.save()

        # Lancer l'analyse IA si l'extraction a réussi
        if extracted_content.get('extracted', False):
            analyze_document.delay(document_id)

        current_task.update_state(
            state='SUCCESS',
            meta={
                'current': 100,
                'total': 100,
                'status': 'Extraction terminée'
            }
        )

        logger.info(f'Extraction terminée pour le document {document_id}')

        return {
            'document_id': document_id,
            'extracted': extracted_content.get('extracted', False),
            'content_length': len(extracted_content.get('text', '')),
            'document_type': document.document_type
        }

    except Document.DoesNotExist:
        logger.error(f'Document {document_id} non trouvé')
        raise

    except Exception as exc:
        logger.error(f'Erreur lors de l\'extraction du document {document_id}: {exc}')
        raise self.retry(exc=exc)


@shared_task(bind=True)
def generate_template(self, document_id):
    """
    Tâche asynchrone pour générer un template de formulaire
    """
    try:
        logger.info(f'Génération de template pour le document {document_id}')

        document = Document.objects.get(id=document_id)

        # Mise à jour du statut
        current_task.update_state(
            state='PROGRESS',
            meta={
                'current': 25,
                'total': 100,
                'status': 'Analyse du contenu...'
            }
        )

        # Générer les champs de template basés sur le type de document
        template_fields = []

        if 'ema' in document.name.lower() or 'cover letter' in document.name.lower():
            # Template EMA Cover Letter
            template_structure = [
                {'name': 'applicant_name', 'label': 'Applicant/MAH Name', 'type': 'text', 'required': True},
                {'name': 'customer_account', 'label': 'Customer Account Number', 'type': 'text', 'required': True},
                {'name': 'customer_reference', 'label': 'Customer Reference', 'type': 'text'},
                {'name': 'inn_code', 'label': 'INN / Active substance/ATC Code', 'type': 'text'},
                {'name': 'product_name', 'label': 'Product Name', 'type': 'text'},
                {'name': 'submission_type', 'label': 'Submission Type', 'type': 'select',
                 'options': ['New procedure', 'Response to ongoing procedure']},
                {'name': 'procedure_type', 'label': 'Procedure Type', 'type': 'text',
                 'value': 'MAA - Marketing Authorisation Application'},
            ]
        else:
            # Template générique
            template_structure = [
                {'name': 'document_title', 'label': 'Document Title', 'type': 'text', 'required': True},
                {'name': 'document_description', 'label': 'Description', 'type': 'textarea'},
                {'name': 'document_date', 'label': 'Date', 'type': 'date'},
            ]

        # Mise à jour du statut
        current_task.update_state(
            state='PROGRESS',
            meta={
                'current': 60,
                'total': 100,
                'status': 'Création des champs...'
            }
        )

        # Créer les champs de template
        with transaction.atomic():
            # Supprimer les anciens champs
            TemplateField.objects.filter(document=document).delete()

            # Créer les nouveaux champs
            for i, field_config in enumerate(template_structure):
                TemplateField.objects.create(
                    document=document,
                    field_name=field_config['name'],
                    field_label=field_config['label'],
                    field_type=field_config['type'],
                    field_value=field_config.get('value', ''),
                    field_options=field_config.get('options', []),
                    is_required=field_config.get('required', False),
                    row_number=i,
                    column_number=0
                )

                template_fields.append(field_config['name'])

            # Marquer le template comme généré
            document.is_template_generated = True
            document.save()

        current_task.update_state(
            state='SUCCESS',
            meta={
                'current': 100,
                'total': 100,
                'status': 'Template généré'
            }
        )

        logger.info(f'Template généré pour le document {document_id}')

        return {
            'document_id': document_id,
            'fields_created': len(template_fields),
            'field_names': template_fields
        }

    except Document.DoesNotExist:
        logger.error(f'Document {document_id} non trouvé')
        raise

    except Exception as exc:
        logger.error(f'Erreur lors de la génération du template {document_id}: {exc}')
        raise


@shared_task
def send_notification_email(user_email, subject, template_name, context=None):
    """
    Tâche asynchrone pour envoyer des emails de notification
    """
    try:
        logger.info(f'Envoi d\'email à {user_email}: {subject}')

        if context is None:
            context = {}

        # Rendu du template HTML
        html_content = render_to_string(f'emails/{template_name}.html', context)
        text_content = strip_tags(html_content)

        # Créer l'email
        email = EmailMultiAlternatives(
            subject=f'[CTD Submission] {subject}',
            body=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[user_email]
        )
        email.attach_alternative(html_content, "text/html")

        # Envoyer l'email
        email.send()

        logger.info(f'Email envoyé avec succès à {user_email}')

        return {
            'recipient': user_email,
            'subject': subject,
            'sent_at': timezone.now().isoformat()
        }

    except Exception as exc:
        logger.error(f'Erreur lors de l\'envoi d\'email à {user_email}: {exc}')
        raise


@shared_task
def cleanup_temp_files():
    """
    Tâche périodique pour nettoyer les fichiers temporaires
    """
    try:
        logger.info('Début du nettoyage des fichiers temporaires')

        # Nettoyer les fichiers temporaires de plus de 24h
        temp_dir = os.path.join(settings.MEDIA_ROOT, 'temp')
        if not os.path.exists(temp_dir):
            return {'cleaned_files': 0}

        cutoff_time = time.time() - (24 * 3600)  # 24 heures
        cleaned_count = 0

        for filename in os.listdir(temp_dir):
            file_path = os.path.join(temp_dir, filename)
            if os.path.isfile(file_path):
                file_time = os.path.getmtime(file_path)
                if file_time < cutoff_time:
                    try:
                        os.remove(file_path)
                        cleaned_count += 1
                        logger.debug(f'Fichier temporaire supprimé: {filename}')
                    except OSError as e:
                        logger.warning(f'Impossible de supprimer {filename}: {e}')

        logger.info(f'Nettoyage terminé: {cleaned_count} fichiers supprimés')

        return {
            'cleaned_files': cleaned_count,
            'cleanup_time': timezone.now().isoformat()
        }

    except Exception as exc:
        logger.error(f'Erreur lors du nettoyage des fichiers temporaires: {exc}')
        raise


@shared_task
def cleanup_old_ai_analysis(days_old=30):
    """
    Tâche périodique pour nettoyer les anciennes analyses IA
    """
    try:
        logger.info(f'Nettoyage des analyses IA de plus de {days_old} jours')

        cutoff_date = timezone.now() - timedelta(days=days_old)

        # Supprimer les analyses anciennes
        deleted_count, _ = AIAnalysisResult.objects.filter(
            created_at__lt=cutoff_date
        ).delete()

        logger.info(f'Nettoyage terminé: {deleted_count} analyses supprimées')

        return {
            'deleted_analyses': deleted_count,
            'cutoff_date': cutoff_date.isoformat(),
            'cleanup_time': timezone.now().isoformat()
        }

    except Exception as exc:
        logger.error(f'Erreur lors du nettoyage des analyses IA: {exc}')
        raise


@shared_task
def save_system_metrics():
    """
    Tâche périodique pour sauvegarder les métriques système
    """
    try:
        logger.info('Sauvegarde des métriques système')

        # Calculer les métriques
        metrics = {
            'timestamp': timezone.now().isoformat(),
            'submissions': {
                'total': Submission.objects.count(),
                'by_status': {},
                'by_region': {}
            },
            'documents': {
                'total': Document.objects.count(),
                'with_templates': Document.objects.filter(is_template_generated=True).count(),
                'by_type': {}
            },
            'ai_analysis': {
                'total': AIAnalysisResult.objects.count(),
                'avg_confidence': 0
            }
        }

        # Statistiques par statut
        for status_choice in Submission.STATUS_CHOICES:
            status = status_choice[0]
            count = Submission.objects.filter(status=status).count()
            metrics['submissions']['by_status'][status] = count

        # Statistiques par région
        for region_choice in Submission.REGION_CHOICES:
            region = region_choice[0]
            count = Submission.objects.filter(region=region).count()
            metrics['submissions']['by_region'][region] = count

        # Statistiques par type de document
        for doc_type_choice in Document.DOCUMENT_TYPES:
            doc_type = doc_type_choice[0]
            count = Document.objects.filter(document_type=doc_type).count()
            metrics['documents']['by_type'][doc_type] = count

        # Confiance moyenne des analyses IA
        avg_confidence = AIAnalysisResult.objects.aggregate(
            avg=models.Avg('confidence_score')
        )['avg']
        metrics['ai_analysis']['avg_confidence'] = float(avg_confidence or 0)

        # Sauvegarder les métriques (ici on les log, mais on pourrait les sauvegarder en base)
        logger.info(f'Métriques système: {json.dumps(metrics, indent=2)}')

        return metrics

    except Exception as exc:
        logger.error(f'Erreur lors de la sauvegarde des métriques: {exc}')
        raise


@shared_task
def check_submission_health():
    """
    Tâche périodique pour vérifier la santé des soumissions en cours
    """
    try:
        logger.info('Vérification de la santé des soumissions')

        issues = []

        # Vérifier les soumissions en cours depuis plus de 30 jours
        stale_cutoff = timezone.now() - timedelta(days=30)
        stale_submissions = Submission.objects.filter(
            status='in_progress',
            updated_at__lt=stale_cutoff
        )

        for submission in stale_submissions:
            issues.append({
                'type': 'stale_submission',
                'submission_id': submission.id,
                'name': submission.name,
                'days_stale': (timezone.now() - submission.updated_at).days
            })

        # Vérifier les documents sans section assignée
        unassigned_docs = Document.objects.filter(section__isnull=True)
        for doc in unassigned_docs:
            issues.append({
                'type': 'unassigned_document',
                'document_id': doc.id,
                'name': doc.name,
                'submission': doc.submission.name
            })

        # Vérifier les analyses IA avec faible confiance
        low_confidence_analyses = AIAnalysisResult.objects.filter(
            confidence_score__lt=0.3
        )
        for analysis in low_confidence_analyses:
            issues.append({
                'type': 'low_confidence_analysis',
                'document': analysis.document.name,
                'confidence': analysis.confidence_score
            })

        if issues:
            logger.warning(f'{len(issues)} problèmes détectés dans les soumissions')

            # Envoyer une notification aux administrateurs
            admin_emails = ['admin@ctd-submission.com']  # À configurer
            for email in admin_emails:
                send_notification_email.delay(
                    email,
                    f'{len(issues)} problèmes détectés',
                    'health_check_issues',
                    {'issues': issues}
                )
        else:
            logger.info('Aucun problème détecté')

        return {
            'issues_found': len(issues),
            'issues': issues,
            'check_time': timezone.now().isoformat()
        }

    except Exception as exc:
        logger.error(f'Erreur lors de la vérification de santé: {exc}')
        raise


@shared_task
def generate_daily_stats():
    """
    Tâche quotidienne pour générer les statistiques
    """
    try:
        logger.info('Génération des statistiques quotidiennes')

        today = timezone.now().date()
        yesterday = today - timedelta(days=1)

        # Statistiques du jour précédent
        stats = {
            'date': yesterday.isoformat(),
            'new_submissions': Submission.objects.filter(
                created_at__date=yesterday
            ).count(),
            'new_documents': Document.objects.filter(
                created_at__date=yesterday
            ).count(),
            'ai_analyses': AIAnalysisResult.objects.filter(
                created_at__date=yesterday
            ).count(),
            'templates_generated': Document.objects.filter(
                updated_at__date=yesterday,
                is_template_generated=True
            ).count()
        }

        # Envoyer les statistiques aux administrateurs
        admin_emails = ['admin@ctd-submission.com']  # À configurer
        for email in admin_emails:
            send_notification_email.delay(
                email,
                f'Statistiques quotidiennes - {yesterday}',
                'daily_stats',
                {'stats': stats}
            )

        logger.info(f'Statistiques quotidiennes générées: {stats}')

        return stats

    except Exception as exc:
        logger.error(f'Erreur lors de la génération des statistiques: {exc}')
        raise


# Tâche de test pour vérifier que Celery fonctionne
@shared_task
def test_celery():
    """
    Tâche de test pour vérifier le bon fonctionnement de Celery
    """
    logger.info('Test Celery - Début')
    time.sleep(2)  # Simuler un traitement
    logger.info('Test Celery - Fin')
    return {
        'status': 'success',
        'message': 'Celery fonctionne correctement',
        'timestamp': timezone.now().isoformat()
    }

#######################################################
# ctd_submission/tasks.py
# Tâches asynchrones pour l'éditeur avancé avec Celery

from celery import shared_task, current_task
from celery.exceptions import Retry
from django.core.mail import send_mail
from django.contrib.auth.models import User
from django.utils import timezone
from django.db import transaction
import logging
import time
import asyncio
from typing import Dict, List, Optional

from .models import Document, Submission, DocumentVersion, AIAnalysisResult
from .utils import CTDAnalyzer, DocumentProcessor
from .services.mistral_service import MistralEnhancedCopilot, run_async_analysis

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def analyze_document_async(self, document_id: int, analysis_type: str = 'full'):
    """
    Tâche asynchrone pour analyser un document avec l'IA
    """
    try:
        logger.info(f'Début de l\'analyse IA du document {document_id}')

        # Récupérer le document
        document = Document.objects.select_related(
            'submission', 'section', 'section__module'
        ).get(id=document_id)

        # Mettre à jour le statut de progression
        self.update_state(
            state='PROGRESS',
            meta={
                'current': 10,
                'total': 100,
                'status': 'Initialisation de l\'analyse...',
                'document_name': document.name
            }
        )

        # Étape 1: Extraction du contenu si nécessaire
        if not document.content_extracted or not document.content_extracted.get('extracted', False):
            self.update_state(
                state='PROGRESS',
                meta={
                    'current': 20,
                    'total': 100,
                    'status': 'Extraction du contenu...'
                }
            )

            processor = DocumentProcessor()
            extracted_content = processor.extract_content(document)

            if extracted_content:
                document.content_extracted = extracted_content
                document.save(update_fields=['content_extracted'])

        # Étape 2: Analyse avec Copilot amélioré
        self.update_state(
            state='PROGRESS',
            meta={
                'current': 40,
                'total': 100,
                'status': 'Analyse IA en cours...'
            }
        )

        if analysis_type == 'enhanced':
            # Utiliser Mistral AI pour une analyse avancée
            copilot = MistralEnhancedCopilot()
            analysis_result = run_async_analysis(
                copilot.enhanced_document_analysis(document)
            )
        else:
            # Analyse standard
            analyzer = CTDAnalyzer()
            analysis_result = analyzer.analyze_document(document)

        self.update_state(
            state='PROGRESS',
            meta={
                'current': 70,
                'total': 100,
                'status': 'Traitement des résultats...'
            }
        )

        # Étape 3: Sauvegarder les résultats
        if analysis_result:
            with transaction.atomic():
                if analysis_type == 'enhanced' and 'suggested_classification' in analysis_result:
                    # Résultats Mistral
                    classification = analysis_result['suggested_classification']
                    if classification['confidence'] > 0.6:
                        # Trouver le module et la section correspondants
                        try:
                            from .models import CTDModule, CTDSection
                            module = CTDModule.objects.get(code=classification['module'])
                            section = CTDSection.objects.get(
                                module=module,
                                code=classification['section']
                            )

                            AIAnalysisResult.objects.update_or_create(
                                document=document,
                                defaults={
                                    'suggested_module': module,
                                    'suggested_section': section,
                                    'confidence_score': classification['confidence'],
                                    'analysis_details': analysis_result,
                                    'keywords_found': analysis_result.get('analyses', {}).get('classification', {}).get(
                                        'keywords_identified', [])
                                }
                            )
                        except Exception as e:
                            logger.error(f"Erreur lors de la récupération des objets CTD: {e}")

                else:
                    # Résultats analyse standard
                    ai_analysis, created = AIAnalysisResult.objects.update_or_create(
                        document=document,
                        defaults={
                            'suggested_module': analysis_result['module'],
                            'suggested_section': analysis_result['section'],
                            'confidence_score': analysis_result['confidence'],
                            'analysis_details': analysis_result['details'],
                            'keywords_found': analysis_result['keywords']
                        }
                    )

                # Assigner automatiquement si confiance élevée
                confidence = (analysis_result.get('suggested_classification', {}).get('confidence', 0)
                              if analysis_type == 'enhanced'
                              else analysis_result.get('confidence', 0))

                if confidence >= 0.8 and not document.section:
                    if analysis_type == 'enhanced':
                        classification = analysis_result['suggested_classification']
                        try:
                            module = CTDModule.objects.get(code=classification['module'])
                            section = CTDSection.objects.get(
                                module=module,
                                code=classification['section']
                            )
                            document.section = section
                            document.save(update_fields=['section'])
                        except:
                            pass
                    else:
                        document.section = analysis_result['section']
                        document.save(update_fields=['section'])

        # Étape 4: Finalisation
        self.update_state(
            state='PROGRESS',
            meta={
                'current': 100,
                'total': 100,
                'status': 'Analyse terminée'
            }
        )

        logger.info(f'Analyse IA terminée pour le document {document_id}')

        # Notifier l'utilisateur si configuré
        if getattr(document.submission, 'notify_on_analysis', False):
            notify_analysis_complete.delay(document_id, analysis_result)

        return {
            'document_id': document_id,
            'success': True,
            'analysis_type': analysis_type,
            'confidence': confidence if 'confidence' in locals() else 0,
            'assigned_section': document.section.name if document.section else None
        }

    except Document.DoesNotExist:
        logger.error(f'Document {document_id} non trouvé')
        raise

    except Exception as exc:
        logger.error(f'Erreur lors de l\'analyse du document {document_id}: {exc}')

        # Retry avec backoff exponentiel
        retry_count = self.request.retries
        countdown = 60 * (2 ** retry_count)  # 60s, 120s, 240s

        raise self.retry(exc=exc, countdown=countdown)


@shared_task(bind=True, max_retries=2)
def batch_analyze_documents(self, document_ids: List[int], analysis_type: str = 'standard'):
    """
    Analyse en lot de plusieurs documents
    """
    try:
        logger.info(f'Début de l\'analyse en lot de {len(document_ids)} documents')

        total_docs = len(document_ids)
        results = []

        for i, doc_id in enumerate(document_ids):
            # Mettre à jour la progression
            self.update_state(
                state='PROGRESS',
                meta={
                    'current': i + 1,
                    'total': total_docs,
                    'status': f'Analyse du document {i + 1}/{total_docs}',
                    'processing_document_id': doc_id
                }
            )

            # Analyser le document
            try:
                result = analyze_document_async.apply_async(
                    args=[doc_id, analysis_type],
                    countdown=i * 2  # Étalement des requêtes
                )
                results.append({
                    'document_id': doc_id,
                    'task_id': result.id,
                    'status': 'queued'
                })
            except Exception as e:
                logger.error(f'Erreur lors du lancement de l\'analyse pour {doc_id}: {e}')
                results.append({
                    'document_id': doc_id,
                    'status': 'error',
                    'error': str(e)
                })

        return {
            'success': True,
            'total_documents': total_docs,
            'results': results,
            'batch_id': self.request.id
        }

    except Exception as exc:
        logger.error(f'Erreur lors de l\'analyse en lot: {exc}')
        raise self.retry(exc=exc, countdown=120)


@shared_task(bind=True)
def generate_document_template_async(self, document_id: int):
    """
    Génération asynchrone de template pour un document
    """
    try:
        from .views import generate_document_template

        document = Document.objects.get(id=document_id)

        self.update_state(
            state='PROGRESS',
            meta={
                'current': 50,
                'total': 100,
                'status': 'Génération du template...'
            }
        )

        # Générer le template
        generate_document_template(document)

        self.update_state(
            state='PROGRESS',
            meta={
                'current': 100,
                'total': 100,
                'status': 'Template généré avec succès'
            }
        )

        return {
            'success': True,
            'document_id': document_id,
            'template_fields_count': document.template_fields.count()
        }

    except Exception as exc:
        logger.error(f'Erreur lors de la génération de template: {exc}')
        raise


@shared_task
def cleanup_old_versions(days_old: int = 30):
    """
    Nettoyage automatique des anciennes versions de documents
    """
    try:
        cutoff_date = timezone.now() - timezone.timedelta(days=days_old)

        # Supprimer les versions non-actuelles anciennes
        old_versions = DocumentVersion.objects.filter(
            created_at__lt=cutoff_date,
            is_current=False
        ).exclude(
            # Garde toujours la première version
            version_number=1
        )

        deleted_count = 0
        for version in old_versions:
            # Vérifier qu'il y a au moins 2 versions plus récentes
            newer_versions = DocumentVersion.objects.filter(
                document=version.document,
                version_number__gt=version.version_number
            ).count()

            if newer_versions >= 2:
                version.delete()
                deleted_count += 1

        logger.info(f'Nettoyage terminé: {deleted_count} versions supprimées')

        return {
            'success': True,
            'deleted_versions': deleted_count,
            'cutoff_date': cutoff_date.isoformat()
        }

    except Exception as e:
        logger.error(f'Erreur lors du nettoyage: {e}')
        return {'success': False, 'error': str(e)}


@shared_task
def validate_submission_documents(submission_id: int):
    """
    Validation automatique de tous les documents d'une soumission
    """
    try:
        from .utils import DocumentValidator

        submission = Submission.objects.get(id=submission_id)
        documents = submission.documents.all()

        validator = DocumentValidator()
        validation_results = []

        for document in documents:
            result = validator.validate_document(document)
            validation_results.append({
                'document_id': document.id,
                'document_name': document.name,
                'is_valid': result['is_valid'],
                'errors_count': len(result['errors']),
                'warnings_count': len(result['warnings'])
            })

        # Calculer le score global de la soumission
        total_documents = len(validation_results)
        valid_documents = sum(1 for r in validation_results if r['is_valid'])
        total_errors = sum(r['errors_count'] for r in validation_results)
        total_warnings = sum(r['warnings_count'] for r in validation_results)

        overall_score = (valid_documents / total_documents) * 100 if total_documents > 0 else 0

        return {
            'success': True,
            'submission_id': submission_id,
            'overall_score': overall_score,
            'total_documents': total_documents,
            'valid_documents': valid_documents,
            'total_errors': total_errors,
            'total_warnings': total_warnings,
            'document_results': validation_results
        }

    except Exception as e:
        logger.error(f'Erreur lors de la validation de soumission: {e}')
        return {'success': False, 'error': str(e)}


@shared_task
def notify_analysis_complete(document_id: int, analysis_result: Dict):
    """
    Notification par email de la completion d'analyse
    """
    try:
        document = Document.objects.select_related('submission', 'submission__created_by').get(id=document_id)
        user = document.submission.created_by

        if not user.email:
            logger.warning(f'Pas d\'email configuré pour l\'utilisateur {user.username}')
            return

        confidence = analysis_result.get('confidence', 0)
        section_name = analysis_result.get('section', {}).get('name', 'Non déterminée') if isinstance(
            analysis_result.get('section'), dict) else 'Non déterminée'

        subject = f'Analyse IA terminée - {document.name}'
        message = f"""
Bonjour {user.get_full_name() or user.username},

L'analyse IA de votre document "{document.name}" est terminée.

Résultats:
- Confiance de l'analyse: {confidence:.1%}
- Section suggérée: {section_name}
- Soumission: {document.submission.name}

Vous pouvez consulter les résultats détaillés dans l'éditeur avancé.

Cordialement,
L'équipe CTD Submission
        """

        send_mail(
            subject=subject,
            message=message,
            from_email='noreply@ctd-submission.com',
            recipient_list=[user.email],
            fail_silently=True
        )

        logger.info(f'Notification envoyée à {user.email} pour le document {document_id}')

    except Exception as e:
        logger.error(f'Erreur lors de l\'envoi de notification: {e}')


@shared_task(bind=True)
def export_submission_package(self, submission_id: int, export_format: str = 'zip'):
    """
    Export complet d'une soumission en arrière-plan
    """
    try:
        import zipfile
        import tempfile
        import os
        from django.core.files.base import ContentFile
        from django.core.files.storage import default_storage

        submission = Submission.objects.prefetch_related('documents').get(id=submission_id)

        self.update_state(
            state='PROGRESS',
            meta={
                'current': 10,
                'total': 100,
                'status': 'Préparation de l\'export...'
            }
        )

        # Créer un fichier temporaire
        with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as temp_file:
            with zipfile.ZipFile(temp_file, 'w', zipfile.ZIP_DEFLATED) as zipf:

                documents = submission.documents.all()
                total_docs = documents.count()

                # Ajouter les métadonnées de la soumission
                submission_info = {
                    'name': submission.name,
                    'region': submission.region,
                    'submission_type': submission.submission_type,
                    'status': submission.status,
                    'created_at': submission.created_at.isoformat(),
                    'documents_count': total_docs,
                    'export_date': timezone.now().isoformat()
                }

                zipf.writestr('submission_metadata.json',
                              json.dumps(submission_info, indent=2, ensure_ascii=False))

                # Ajouter chaque document
                for i, document in enumerate(documents):
                    progress = 20 + (i / total_docs) * 70  # 20% à 90%
                    self.update_state(
                        state='PROGRESS',
                        meta={
                            'current': int(progress),
                            'total': 100,
                            'status': f'Export document {i + 1}/{total_docs}: {document.name}'
                        }
                    )

                    # Ajouter le fichier original
                    if document.file:
                        try:
                            with document.file.open('rb') as f:
                                zipf.writestr(f'documents/{document.name}', f.read())
                        except Exception as e:
                            logger.warning(f'Impossible d\'ajouter le fichier {document.name}: {e}')

                    # Ajouter les données du template si disponibles
                    if document.template_data:
                        template_filename = f'templates/{document.name}_template.json'
                        zipf.writestr(template_filename,
                                      json.dumps(document.template_data, indent=2, ensure_ascii=False))

            # Sauvegarder le fichier zip
            temp_file.seek(0)
            zip_content = temp_file.read()

            # Stocker dans le storage Django
            filename = f'exports/submission_{submission_id}_{timezone.now().strftime("%Y%m%d_%H%M%S")}.zip'
            saved_path = default_storage.save(filename, ContentFile(zip_content))

            # Nettoyer le fichier temporaire
            os.unlink(temp_file.name)

        self.update_state(
            state='PROGRESS',
            meta={
                'current': 100,
                'total': 100,
                'status': 'Export terminé'
            }
        )

        return {
            'success': True,
            'submission_id': submission_id,
            'export_path': saved_path,
            'file_size': len(zip_content),
            'documents_exported': total_docs
        }

    except Exception as exc:
        logger.error(f'Erreur lors de l\'export: {exc}')
        raise


@shared_task
def daily_maintenance():
    """
    Tâche de maintenance quotidienne
    """
    try:
        maintenance_results = []

        # 1. Nettoyage des anciennes versions
        cleanup_result = cleanup_old_versions.delay(30)
        maintenance_results.append({
            'task': 'cleanup_old_versions',
            'task_id': cleanup_result.id
        })

        # 2. Validation des soumissions actives
        active_submissions = Submission.objects.filter(
            status__in=['draft', 'in_progress']
        ).values_list('id', flat=True)

        for submission_id in active_submissions[:10]:  # Limiter à 10 par jour
            validation_result = validate_submission_documents.delay(submission_id)
            maintenance_results.append({
                'task': 'validate_submission',
                'submission_id': submission_id,
                'task_id': validation_result.id
            })

        # 3. Statistiques d'utilisation
        from django.db.models import Count
        stats = {
            'total_submissions': Submission.objects.count(),
            'total_documents': Document.objects.count(),
            'analyzed_documents': AIAnalysisResult.objects.count(),
            'template_generated_documents': Document.objects.filter(is_template_generated=True).count(),
            'date': timezone.now().isoformat()
        }

        logger.info(f'Maintenance quotidienne terminée: {stats}')

        return {
            'success': True,
            'maintenance_tasks': maintenance_results,
            'stats': stats
        }

    except Exception as e:
        logger.error(f'Erreur lors de la maintenance quotidienne: {e}')
        return {'success': False, 'error': str(e)}


# Tâches périodiques configurables
@shared_task(bind=True)
def smart_reanalysis(self, confidence_threshold: float = 0.6, days_old: int = 7):
    """
    Réanalyse intelligente des documents avec faible confiance
    """
    try:
        cutoff_date = timezone.now() - timezone.timedelta(days=days_old)

        # Trouver les documents avec faible confiance ou non analysés
        low_confidence_docs = Document.objects.filter(
            models.Q(ai_analysis__confidence_score__lt=confidence_threshold) |
            models.Q(ai_analysis__isnull=True),
            created_at__gte=cutoff_date
        ).select_related('ai_analysis')

        total_docs = low_confidence_docs.count()
        if total_docs == 0:
            return {'success': True, 'message': 'Aucun document à réanalyser'}

        reanalyzed = 0
        for i, document in enumerate(low_confidence_docs[:20]):  # Limiter à 20
            self.update_state(
                state='PROGRESS',
                meta={
                    'current': i + 1,
                    'total': min(total_docs, 20),
                    'status': f'Réanalyse de {document.name}'
                }
            )

            # Lancer l'analyse enhanced
            analyze_document_async.delay(document.id, 'enhanced')
            reanalyzed += 1

        return {
            'success': True,
            'total_candidates': total_docs,
            'reanalyzed': reanalyzed,
            'confidence_threshold': confidence_threshold
        }

    except Exception as e:
        logger.error(f'Erreur lors de la réanalyse intelligente: {e}')
        raise