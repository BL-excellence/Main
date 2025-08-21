# Chemin d'intégration : ctd_submission/signals.py (CORRIGÉ)
# Correction de l'erreur 'function' object has no attribute 'delay'

from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
import logging
import os

from .models import Submission, Document, TemplateField, AIAnalysisResult
from .utils import CTDAnalyzer, DocumentProcessor

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Document)
def document_post_save_handler(sender, instance, created, **kwargs):
    """
    Signal déclenché après la sauvegarde d'un document
    Lance automatiquement l'extraction de contenu et l'analyse IA
    CORRECTION: Appel direct de la fonction au lieu de .delay()
    """
    if created and instance.file:
        logger.info(f"Nouveau document créé: {instance.name}")

        # Lancer l'extraction de contenu
        try:
            processor = DocumentProcessor()
            extracted_content = processor.extract_content(instance)

            if extracted_content:
                instance.content_extracted = extracted_content
                instance.save(update_fields=['content_extracted'])
                logger.info(f"Contenu extrait pour le document: {instance.name}")

                # ✅ CORRECTION: Appel direct au lieu de .delay()
                trigger_ai_analysis_sync(instance.id)

        except Exception as e:
            logger.error(f"Erreur lors de l'extraction du contenu pour {instance.name}: {e}")


def trigger_ai_analysis_sync(document_id):
    """
    Fonction pour déclencher l'analyse IA d'un document (version synchrone)
    CORRECTION: Version sans Celery pour éviter l'erreur .delay()
    """
    try:
        document = Document.objects.get(id=document_id)
        analyzer = CTDAnalyzer()

        # Effectuer l'analyse
        analysis_result = analyzer.analyze_document(document)

        if analysis_result:
            # Sauvegarder les résultats
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
                document.save(update_fields=['section'])
                logger.info(
                    f"Document {document.name} automatiquement assigné à la section {analysis_result['section']}")

            logger.info(
                f"Analyse IA terminée pour {document.name} avec {analysis_result['confidence']:.2f} de confiance")

        else:
            logger.warning(f"Impossible d'analyser le document {document.name}")

    except Document.DoesNotExist:
        logger.error(f"Document avec ID {document_id} non trouvé pour l'analyse IA")
    except Exception:
        logger.exception(f"Erreur lors de l'analyse IA du document {document_id}")


# Version Celery optionnelle (si vous voulez utiliser Celery plus tard)
def trigger_ai_analysis_async(document_id):
    """
    Version asynchrone avec Celery (optionnelle)
    À utiliser seulement si Celery est configuré
    """
    try:
        # Importer la tâche Celery si elle existe
        from .tasks import analyze_document
        analyze_document.delay(document_id)
        logger.info(f"Tâche d'analyse IA lancée en arrière-plan pour le document {document_id}")
    except ImportError:
        # Fallback vers la version synchrone si Celery n'est pas disponible
        logger.warning("Celery non disponible, utilisation de l'analyse synchrone")
        trigger_ai_analysis_sync(document_id)
    except Exception as e:
        logger.error(f"Erreur lors du lancement de la tâche Celery: {e}")
        # Fallback vers la version synchrone
        trigger_ai_analysis_sync(document_id)


@receiver(post_save, sender=Submission)
def submission_post_save_handler(sender, instance, created, **kwargs):
    """
    Signal déclenché après la sauvegarde d'une soumission
    """
    if created:
        logger.info(f"Nouvelle soumission créée: {instance.name} par {instance.created_by.username}")

        # Envoyer une notification par email (si configuré)
        if hasattr(settings, 'EMAIL_NOTIFICATIONS') and settings.EMAIL_NOTIFICATIONS:
            try:
                send_notification_email(instance, 'created')
            except Exception as e:
                logger.error(f"Erreur lors de l'envoi de notification email: {e}")

        # Créer l'historique de la soumission
        create_submission_history(instance, 'created')

    # Vérifier si le statut a changé
    if not created and hasattr(instance, '_original_status'):
        if instance._original_status != instance.status:
            logger.info(
                f"Statut de la soumission {instance.name} changé: {instance._original_status} -> {instance.status}")
            create_submission_history(instance, 'status_changed', {
                'from_status': instance._original_status,
                'to_status': instance.status
            })


@receiver(pre_save, sender=Submission)
def submission_pre_save_handler(sender, instance, **kwargs):
    """
    Signal déclenché avant la sauvegarde d'une soumission
    Stocke l'état original pour comparaison
    """
    if instance.pk:
        try:
            original = Submission.objects.get(pk=instance.pk)
            instance._original_status = original.status
        except Submission.DoesNotExist:
            pass


@receiver(post_save, sender=TemplateField)
def template_field_post_save_handler(sender, instance, created, **kwargs):
    """
    Signal déclenché après la sauvegarde d'un champ de template
    Met à jour automatiquement le document associé
    """
    if not created:  # Seulement lors de modifications
        logger.info(f"Champ de template modifié: {instance.field_label} pour {instance.document.name}")

        # Mettre à jour le template_data du document
        try:
            update_document_template_data(instance.document)
        except Exception as e:
            logger.error(f"Erreur lors de la mise à jour du template: {e}")


@receiver(post_delete, sender=Document)
def document_post_delete_handler(sender, instance, **kwargs):
    """
    Signal déclenché après la suppression d'un document
    Nettoie les fichiers associés
    """
    logger.info(f"Document supprimé: {instance.name}")

    # Supprimer le fichier physique
    if instance.file:
        try:
            if os.path.isfile(instance.file.path):
                os.remove(instance.file.path)
                logger.info(f"Fichier physique supprimé: {instance.file.path}")
        except Exception as e:
            logger.error(f"Erreur lors de la suppression du fichier: {e}")

    # Nettoyer les analyses IA associées
    try:
        AIAnalysisResult.objects.filter(document=instance).delete()
        logger.info(f"Analyses IA supprimées pour le document: {instance.name}")
    except Exception as e:
        logger.error(f"Erreur lors du nettoyage des analyses IA: {e}")


@receiver(user_logged_in)
def user_logged_in_handler(sender, request, user, **kwargs):
    """
    Signal déclenché lors de la connexion d'un utilisateur
    """
    logger.info(f"Utilisateur connecté: {user.username}")

    # Mettre à jour la dernière connexion
    user.last_login = timezone.now()
    user.save(update_fields=['last_login'])

    # Ajouter un message de bienvenue dans la session
    if hasattr(request, 'session'):
        request.session['welcome_message'] = f"Bienvenue, {user.get_full_name() or user.username}!"


@receiver(user_logged_out)
def user_logged_out_handler(sender, request, user, **kwargs):
    """
    Signal déclenché lors de la déconnexion d'un utilisateur
    """
    if user:
        logger.info(f"Utilisateur déconnecté: {user.username}")


def send_notification_email(submission, action):
    """
    Envoie une notification par email pour les événements de soumission
    """
    subject_templates = {
        'created': f'Nouvelle soumission CTD créée: {submission.name}',
        'completed': f'Soumission CTD terminée: {submission.name}',
        'submitted': f'Soumission CTD envoyée: {submission.name}'
    }

    message_templates = {
        'created': f'''
        Une nouvelle soumission CTD a été créée:

        Nom: {submission.name}
        Région: {submission.get_region_display()}
        Type: {submission.submission_type}
        Créée par: {submission.created_by.get_full_name() or submission.created_by.username}
        Date: {submission.created_at.strftime("%d/%m/%Y à %H:%M")}
        ''',
        'completed': f'''
        La soumission CTD {submission.name} a été marquée comme terminée.
        ''',
        'submitted': f'''
        La soumission CTD {submission.name} a été soumise avec succès.
        '''
    }

    subject = subject_templates.get(action, f'Notification CTD: {submission.name}')
    message = message_templates.get(action, f'Événement {action} pour la soumission {submission.name}')

    # Liste des destinataires (à personnaliser selon les besoins)
    recipient_list = [submission.created_by.email] if submission.created_by.email else []

    # Ajouter les administrateurs
    from django.contrib.auth.models import User
    admin_emails = User.objects.filter(is_staff=True, email__isnull=False).values_list('email', flat=True)
    recipient_list.extend(admin_emails)

    if recipient_list and hasattr(settings, 'EMAIL_HOST'):
        try:
            send_mail(
                subject=subject,
                message=message,
                from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@ctd-submission.com'),
                recipient_list=list(set(recipient_list)),  # Éviter les doublons
                fail_silently=True
            )
        except Exception as e:
            logger.error(f"Erreur lors de l'envoi d'email: {e}")


def create_submission_history(submission, action, details=None):
    """
    Crée un enregistrement d'historique pour une soumission
    """
    try:
        history_entry = {
            'submission_id': submission.id,
            'submission_name': submission.name,
            'action': action,
            'timestamp': timezone.now().isoformat(),
            'user': submission.created_by.username,
            'details': details or {}
        }

        logger.info(f"Historique de soumission: {history_entry}")

        # Option: Sauvegarder dans un fichier JSON pour audit
        if hasattr(settings, 'AUDIT_LOG_PATH'):
            import json
            audit_file = os.path.join(settings.AUDIT_LOG_PATH, 'submission_history.json')

            # Lire les entrées existantes
            existing_entries = []
            if os.path.exists(audit_file):
                try:
                    with open(audit_file, 'r') as f:
                        existing_entries = json.load(f)
                except json.JSONDecodeError:
                    existing_entries = []

            # Ajouter la nouvelle entrée
            existing_entries.append(history_entry)

            # Sauvegarder
            os.makedirs(os.path.dirname(audit_file), exist_ok=True)
            with open(audit_file, 'w') as f:
                json.dump(existing_entries, f, indent=2)

    except Exception as e:
        logger.error(f"Erreur lors de la création de l'historique: {e}")


def update_document_template_data(document):
    """
    Met à jour les template_data d'un document basé sur ses TemplateField
    """
    template_fields = TemplateField.objects.filter(document=document)
    template_data = {}

    for field in template_fields:
        field_key = f'field_{field.id}'
        template_data[field_key] = field.field_value
        # Aussi sauvegarder avec le nom du champ pour faciliter l'accès
        template_data[field.field_name] = field.field_value

    document.template_data = template_data
    document.save(update_fields=['template_data'])

    logger.info(f"Template data mis à jour pour le document: {document.name}")


# Signaux personnalisés pour la completion de soumission
from django.dispatch import Signal

submission_completed = Signal()
document_analyzed = Signal()
template_updated = Signal()


@receiver(submission_completed)
def handle_submission_completed(sender, submission, **kwargs):
    """
    Gestionnaire pour le signal de completion de soumission
    """
    logger.info(f"Soumission terminée: {submission.name}")

    # Mettre à jour le statut
    submission.status = 'completed'
    submission.save(update_fields=['status'])

    # Envoyer notification
    send_notification_email(submission, 'completed')


@receiver(document_analyzed)
def handle_document_analyzed(sender, document, analysis_result, **kwargs):
    """
    Gestionnaire pour le signal d'analyse de document terminée
    """
    logger.info(f"Document analysé: {document.name} - Confiance: {analysis_result.get('confidence', 0):.2f}")


@receiver(template_updated)
def handle_template_updated(sender, document, **kwargs):
    """
    Gestionnaire pour le signal de mise à jour de template
    """
    logger.info(f"Template mis à jour: {document.name}")

    # Marquer le document comme modifié
    document.updated_at = timezone.now()
    document.save(update_fields=['updated_at'])