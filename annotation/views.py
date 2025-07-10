# annotation/views.py - VERSION FINALE CORRIGÉE
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth import get_user_model
from django.contrib import messages
import json
import logging

from documents.models import Document
from .models import Annotation, EntityType
from audit.models import AuditLog
from extraction.tasks import auto_annotate_document
from extraction.services import DocumentTextExtractor

User = get_user_model()
logger = logging.getLogger(__name__)


@login_required
def annotate_document(request, document_id):
    """Vue pour afficher l'interface d'annotation d'un document - CORRIGÉE"""
    document = get_object_or_404(Document, id=document_id)

    # Vérifier les permissions - VERSION PERMISSIVE POUR LE DÉVELOPPEMENT
    has_permission = any([
        request.user.role in ['admin', 'expert', 'annotateur', 'metadonneur'],
        document.assigned_to == request.user,
        request.user.is_staff,  # Pour les tests en développement
    ])

    if not has_permission:
        messages.error(request, 'Vous n\'avez pas les permissions pour accéder à ce document.')
        return redirect('dashboard:home')

    # Marquer le document comme en cours d'annotation
    if document.status == 'extracted':
        document.status = 'annotating'
        document.save()

    # ===== EXTRACTION DU CONTENU DU DOCUMENT =====
    document_content = ""
    try:
        if document.file and hasattr(document.file, 'path'):
            logger.info(f"Extraction du contenu pour le document {document_id}")

            text_extractor = DocumentTextExtractor()
            document_content = text_extractor.extract_text_from_file(
                document.file.path,
                document.file_type
            )

            logger.info(f"Contenu extrait: {len(document_content)} caractères")

            if not document_content or len(document_content.strip()) < 10:
                document_content = "Le contenu du document est vide ou n'a pas pu être extrait."
                logger.warning(f"Contenu vide pour le document {document_id}")
        else:
            document_content = "Fichier du document introuvable."
            logger.error(f"Fichier introuvable pour le document {document_id}")

    except Exception as e:
        logger.error(f"Erreur extraction texte document {document_id}: {e}")
        document_content = f"Erreur lors de l'extraction du contenu: {str(e)}"

    # ===== RÉCUPÉRER LES TYPES D'ENTITÉS =====
    entity_types = EntityType.objects.all()

    # Si aucun type d'entité n'existe, en créer quelques-uns par défaut
    if not entity_types.exists():
        default_entity_types = [
            {'name': 'CONDITION', 'color': '#dc3545', 'description': 'Conditions médicales'},
            {'name': 'FACTEUR', 'color': '#fd7e14', 'description': 'Facteurs de risque'},
            {'name': 'METHODE', 'color': '#20c997', 'description': 'Méthodes et analyses'},
            {'name': 'EFFET', 'color': '#6f42c1', 'description': 'Effets et résultats'},
            {'name': 'AUTEUR', 'color': '#0dcaf0', 'description': 'Auteurs et personnes'},
            {'name': 'ORGANISATION', 'color': '#198754', 'description': 'Organisations'},
            {'name': 'DATE', 'color': '#ffc107', 'description': 'Dates'},
            {'name': 'LIEU', 'color': '#6c757d', 'description': 'Lieux'},
        ]

        for et_data in default_entity_types:
            EntityType.objects.get_or_create(
                name=et_data['name'],
                defaults={
                    'color': et_data['color'],
                    'description': et_data['description']
                }
            )

        # Recharger les types d'entités
        entity_types = EntityType.objects.all()
        messages.info(request, "Types d'entités par défaut créés.")

    # ===== RÉCUPÉRER LES ANNOTATIONS EXISTANTES =====
    annotations = document.annotations.select_related(
        'entity_type', 'created_by'
    ).all()

    # ===== LANCER L'ANNOTATION AUTOMATIQUE SI NÉCESSAIRE =====
    # Vérifier s'il y a déjà des annotations automatiques
    auto_annotations_exist = annotations.filter(is_automatic=True).exists()

    # Si pas d'annotations automatiques ET contenu valide, lancer l'IA
    if not auto_annotations_exist and document_content and len(document_content.strip()) > 50:
        try:
            logger.info(f"Lancement de l'annotation automatique pour le document {document_id}")

            # Appeler directement la fonction d'annotation automatique
            result = auto_annotate_document(document_id)

            if result and result.get('success'):
                annotations_count = result.get('annotations_count', 0)
                logger.info(f"Annotation automatique réussie: {annotations_count} annotations")
                messages.success(request, f"Annotation automatique terminée : {annotations_count} entités détectées")

                # Recharger les annotations après l'annotation automatique
                annotations = document.annotations.select_related(
                    'entity_type', 'created_by'
                ).all()
            else:
                error_msg = result.get('error', 'Erreur inconnue') if result else 'Aucun résultat'
                logger.warning(f"Annotation automatique échouée: {error_msg}")
                messages.warning(request, "L'annotation automatique n'a pas pu être effectuée.")

        except Exception as e:
            logger.error(f"Erreur lors du lancement de l'annotation automatique: {e}")
            messages.warning(request, f"Erreur lors de l'annotation automatique: {str(e)}")

    context = {
        'document': document,
        'document_content': document_content,
        'entity_types': entity_types,
        'annotations': annotations,
    }

    return render(request, 'documents/annotate.html', context)


@login_required
@require_http_methods(["POST"])
def create_annotation(request):
    """Créer une nouvelle annotation - CORRIGÉE"""
    try:
        data = json.loads(request.body)

        document_id = data.get('document_id')
        entity_type_id = data.get('entity_type_id')
        text = data.get('text')
        start_position = data.get('start_position')
        end_position = data.get('end_position')

        # Validation des données
        if not all([document_id, entity_type_id, text, start_position is not None, end_position is not None]):
            return JsonResponse({
                'success': False,
                'error': 'Données manquantes'
            }, status=400)

        # Vérifier que l'utilisateur peut annoter ce document
        document = get_object_or_404(Document, id=document_id)
        has_permission = any([
            request.user.role in ['admin', 'expert', 'annotateur', 'metadonneur'],
            document.assigned_to == request.user,
            request.user.is_staff,
        ])

        if not has_permission:
            return JsonResponse({
                'success': False,
                'error': 'Permission refusée'
            }, status=403)

        # Vérifier que le type d'entité existe
        entity_type = get_object_or_404(EntityType, id=entity_type_id)

        # Créer l'annotation
        annotation = Annotation.objects.create(
            document=document,
            entity_type=entity_type,
            text=text,
            start_position=int(start_position),
            end_position=int(end_position),
            created_by=request.user,
            is_automatic=False,
            confidence_score=1.0  # Score maximum pour annotation manuelle
        )

        # Log d'audit
        try:
            AuditLog.objects.create(
                user=request.user,
                document=document,
                action='annotate',
                description=f'Annotation manuelle créée: "{text}" -> {entity_type.name}',
                ip_address=request.META.get('REMOTE_ADDR')
            )
        except Exception as e:
            logger.warning(f"Erreur création log audit: {e}")

        return JsonResponse({
            'success': True,
            'annotation': {
                'id': annotation.id,
                'text': annotation.text,
                'entity_type': annotation.entity_type.name,
                'entity_type_color': annotation.entity_type.color,
                'start_position': annotation.start_position,
                'end_position': annotation.end_position,
                'status': annotation.status,
                'created_by': annotation.created_by.get_full_name() or annotation.created_by.username
            }
        })

    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'JSON invalide'
        }, status=400)
    except Exception as e:
        logger.error(f"Erreur création annotation: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["POST"])
def update_annotation(request, annotation_id):
    """Modifier une annotation existante - CORRIGÉE"""
    try:
        annotation = get_object_or_404(Annotation, id=annotation_id)

        # Vérifier les permissions
        has_permission = any([
            request.user.role in ['admin', 'expert'],
            annotation.document.assigned_to == request.user,
            annotation.created_by == request.user,
            request.user.is_staff,
        ])

        if not has_permission:
            return JsonResponse({
                'success': False,
                'error': 'Permission refusée'
            }, status=403)

        data = json.loads(request.body)

        # Mettre à jour les champs si fournis
        if 'entity_type_id' in data:
            entity_type = get_object_or_404(EntityType, id=data['entity_type_id'])
            annotation.entity_type = entity_type

        if 'text' in data:
            annotation.text = data['text']

        if 'start_position' in data:
            annotation.start_position = int(data['start_position'])

        if 'end_position' in data:
            annotation.end_position = int(data['end_position'])

        if 'status' in data and data['status'] in ['detected', 'validated', 'rejected', 'modified']:
            annotation.status = data['status']
            if data['status'] == 'validated':
                annotation.validated_by = request.user

        annotation.save()

        # Log d'audit
        try:
            AuditLog.objects.create(
                user=request.user,
                document=annotation.document,
                action='modify',
                description=f'Annotation modifiée: "{annotation.text}" -> {annotation.entity_type.name}',
                ip_address=request.META.get('REMOTE_ADDR')
            )
        except Exception as e:
            logger.warning(f"Erreur création log audit: {e}")

        return JsonResponse({
            'success': True,
            'annotation': {
                'id': annotation.id,
                'text': annotation.text,
                'entity_type': annotation.entity_type.name,
                'start_position': annotation.start_position,
                'end_position': annotation.end_position,
                'status': annotation.status
            }
        })

    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'JSON invalide'
        }, status=400)
    except Exception as e:
        logger.error(f"Erreur modification annotation: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["DELETE", "POST"])
def delete_annotation(request, annotation_id):
    """Supprimer une annotation - CORRIGÉE"""
    try:
        annotation = get_object_or_404(Annotation, id=annotation_id)

        # Vérifier les permissions
        has_permission = any([
            request.user.role in ['admin', 'expert'],
            annotation.document.assigned_to == request.user,
            annotation.created_by == request.user,
            request.user.is_staff,
        ])

        if not has_permission:
            return JsonResponse({
                'success': False,
                'error': 'Permission refusée'
            }, status=403)

        # Sauvegarder les infos pour le log
        annotation_text = annotation.text
        document = annotation.document

        # Supprimer l'annotation
        annotation.delete()

        # Log d'audit
        try:
            AuditLog.objects.create(
                user=request.user,
                document=document,
                action='delete',
                description=f'Annotation supprimée: "{annotation_text}"',
                ip_address=request.META.get('REMOTE_ADDR')
            )
        except Exception as e:
            logger.warning(f"Erreur création log audit: {e}")

        return JsonResponse({
            'success': True,
            'message': 'Annotation supprimée'
        })

    except Exception as e:
        logger.error(f"Erreur suppression annotation: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["POST"])
def auto_annotate(request, document_id):
    """Lancer l'annotation automatique d'un document - CORRIGÉE"""
    try:
        document = get_object_or_404(Document, id=document_id)

        # Vérifier les permissions
        has_permission = any([
            request.user.role in ['admin', 'expert', 'annotateur', 'metadonneur'],
            document.assigned_to == request.user,
            request.user.is_staff,
        ])

        if not has_permission:
            return JsonResponse({
                'success': False,
                'error': 'Permission refusée'
            }, status=403)

        # Vérifier que le document est dans un état approprié
        if document.status not in ['extracted', 'annotating', 'annotated', 'validated']:
            return JsonResponse({
                'success': False,
                'error': 'Document pas prêt pour l\'annotation'
            }, status=400)

        # Lancer la tâche d'annotation automatique
        result = auto_annotate_document(document_id)

        # Mettre à jour le statut du document si nécessaire
        if document.status == 'extracted':
            document.status = 'annotating'
            document.save()

        # Log d'audit
        try:
            AuditLog.objects.create(
                user=request.user,
                document=document,
                action='annotate',
                description='Annotation automatique lancée',
                ip_address=request.META.get('REMOTE_ADDR')
            )
        except Exception as e:
            logger.warning(f"Erreur création log audit: {e}")

        if result and result.get('success'):
            return JsonResponse({
                'success': True,
                'message': 'Annotation automatique terminée',
                'annotations_count': result.get('annotations_count', 0)
            })
        else:
            error_msg = result.get('error', 'Erreur inconnue') if result else 'Aucun résultat'
            return JsonResponse({
                'success': False,
                'error': error_msg
            }, status=500)

    except Exception as e:
        logger.error(f"Erreur lancement annotation auto: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
def annotation_list(request, document_id):
    """Lister les annotations d'un document - CORRIGÉE"""
    document = get_object_or_404(Document, id=document_id)

    # Vérifier les permissions
    has_permission = any([
        request.user.role in ['admin', 'expert', 'annotateur', 'metadonneur'],
        document.assigned_to == request.user,
        request.user.is_staff,
    ])

    if not has_permission:
        return JsonResponse({
            'success': False,
            'error': 'Permission refusée'
        }, status=403)

    annotations = document.annotations.select_related('entity_type', 'created_by').all()

    annotations_data = []
    for annotation in annotations:
        annotations_data.append({
            'id': annotation.id,
            'text': annotation.text,
            'start_position': annotation.start_position,
            'end_position': annotation.end_position,
            'entity_type': {
                'id': annotation.entity_type.id,
                'name': annotation.entity_type.name,
                'color': annotation.entity_type.color
            },
            'status': annotation.status,
            'confidence_score': annotation.confidence_score,
            'is_automatic': annotation.is_automatic,
            'created_by': annotation.created_by.get_full_name() or annotation.created_by.username,
            'created_at': annotation.created_at.isoformat()
        })

    return JsonResponse({
        'success': True,
        'annotations': annotations_data
    })


@login_required
def entity_types_list(request):
    """Lister tous les types d'entités disponibles"""
    entity_types = EntityType.objects.all()

    entity_types_data = []
    for entity_type in entity_types:
        entity_types_data.append({
            'id': entity_type.id,
            'name': entity_type.name,
            'color': entity_type.color,
            'description': entity_type.description
        })

    return JsonResponse({
        'success': True,
        'entity_types': entity_types_data
    })


@login_required
@require_http_methods(["POST"])
def validate_all_annotations(request, document_id):
    """Valider toutes les annotations d'un document - CORRIGÉE"""
    try:
        document = get_object_or_404(Document, id=document_id)

        # Vérifier les permissions
        has_permission = any([
            request.user.role in ['admin', 'expert'],
            document.assigned_to == request.user,
            request.user.is_staff,
        ])

        if not has_permission:
            return JsonResponse({
                'success': False,
                'error': 'Permission refusée'
            }, status=403)

        # Valider toutes les annotations
        updated = document.annotations.filter(
            status__in=['detected', 'modified']
        ).update(
            status='validated',
            validated_by=request.user
        )

        # Mettre à jour le statut du document
        if document.status == 'annotating':
            document.status = 'annotated'
            document.save()

        # Log d'audit
        try:
            AuditLog.objects.create(
                user=request.user,
                document=document,
                action='validate',
                description=f'{updated} annotations validées',
                ip_address=request.META.get('REMOTE_ADDR')
            )
        except Exception as e:
            logger.warning(f"Erreur création log audit: {e}")

        return JsonResponse({
            'success': True,
            'message': f'{updated} annotations validées',
            'validated_count': updated
        })

    except Exception as e:
        logger.error(f"Erreur validation annotations: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


# ===== Ajout des vues expertes existantes (gardées inchangées) =====
# ... (toutes les autres fonctions expertes restent identiques)

# annotation/views.py - Version corrigée pour les experts
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.core.paginator import Paginator
from django.db.models import Q, Count, Avg
from django.contrib.auth import get_user_model
import json
import logging

from documents.models import Document
from .models import Annotation, EntityType
from audit.models import AuditLog
from extraction.tasks import auto_annotate_document

User = get_user_model()
logger = logging.getLogger(__name__)


@login_required
def expert_validation_list(request):
    """Liste des documents prêts pour la validation finale par les experts"""

    # Vérifier les permissions
    if request.user.role not in ['admin', 'expert']:
        messages.error(request, 'Vous n\'avez pas les permissions pour accéder à cette page.')
        return redirect('dashboard:home')

    # Filtres
    status_filter = request.GET.get('status', 'all')
    search = request.GET.get('search', '')
    quality_filter = request.GET.get('quality', 'all')

    # Base queryset - Documents annotés prêts pour validation finale
    documents = Document.objects.filter(
        status__in=['annotated', 'validating']
    ).select_related('document_type', 'context', 'assigned_to', 'validated_by').prefetch_related('annotations')

    # Filtres
    if status_filter != 'all':
        documents = documents.filter(status=status_filter)

    if search:
        documents = documents.filter(
            Q(title__icontains=search) |
            Q(extracted_title__icontains=search) |
            Q(source__icontains=search)
        )

    # Pour le filtre de qualité, on doit convertir en liste pour évaluer
    documents_list = list(documents)

    if quality_filter == 'high':
        documents_list = [doc for doc in documents_list if calculate_annotation_quality(doc) >= 0.8]
    elif quality_filter == 'medium':
        documents_list = [doc for doc in documents_list if 0.5 <= calculate_annotation_quality(doc) < 0.8]
    elif quality_filter == 'low':
        documents_list = [doc for doc in documents_list if calculate_annotation_quality(doc) < 0.5]

    # Pagination
    paginator = Paginator(documents_list, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Ajouter les statistiques d'annotation pour chaque document
    for document in page_obj:
        document.annotation_stats = get_document_annotation_stats(document)

    context = {
        'page_obj': page_obj,
        'current_filters': {
            'status': status_filter,
            'search': search,
            'quality': quality_filter
        },
        'status_choices': [
            ('all', 'Tous'),
            ('annotated', 'Annotés'),
            ('validating', 'En validation'),
        ],
        'quality_choices': [
            ('all', 'Toutes qualités'),
            ('high', 'Haute qualité (>80%)'),
            ('medium', 'Qualité moyenne (50-80%)'),
            ('low', 'Qualité faible (<50%)'),
        ],
        'total_documents': len(documents_list)
    }

    return render(request, 'annotation/expert_validation_list.html', context)


@login_required
def expert_validation_detail(request, document_id):
    """Interface détaillée de validation experte d'un document"""

    # Vérifier les permissions
    if request.user.role not in ['admin', 'expert']:
        messages.error(request, 'Vous n\'avez pas les permissions pour accéder à cette page.')
        return redirect('dashboard:home')

    document = get_object_or_404(Document, id=document_id)

    # Marquer le document comme en cours de validation si nécessaire
    if document.status == 'annotated':
        document.status = 'validating'
        document.save()

    # Pour le contenu du document, on utilise un contenu d'exemple pour l'instant
    # Dans un vrai projet, il faudrait extraire le contenu du fichier
    document_content = f"""
    Document: {document.title}

    [Contenu du document serait extrait ici...]

    Ce document contient des informations importantes qui ont été annotées 
    automatiquement et manuellement. L'expert doit maintenant valider 
    la qualité de ces annotations avant la mise en production.

    Exemple de texte annoté : Les médicaments cardiovasculaires comme 
    l'aspirine sont utilisés pour prévenir les crises cardiaques.
    """

    # Récupérer toutes les annotations avec leurs détails
    annotations = document.annotations.select_related(
        'entity_type', 'created_by', 'validated_by'
    ).order_by('start_position')

    # Types d'entités disponibles
    entity_types = EntityType.objects.all()

    # Statistiques détaillées des annotations
    annotation_stats = get_detailed_annotation_stats(document)

    # Historique d'audit pour ce document - CORRIGÉ
    audit_logs = AuditLog.objects.filter(
        document=document
    ).select_related('user').order_by('-timestamp')[:10]

    # Sérialiser les annotations pour le template avec calculs de pourcentage
    annotations_data = []
    for annotation in annotations:
        confidence_percentage = round(
            float(annotation.confidence_score or 0) * 100) if annotation.confidence_score else None
        annotations_data.append({
            'id': annotation.id,
            'text': annotation.text,
            'start_position': annotation.start_position,
            'end_position': annotation.end_position,
            'entity_type': annotation.entity_type.name,
            'status': annotation.status,
            'confidence_percentage': confidence_percentage
        })

    # Enrichir les annotations avec les pourcentages calculés
    annotations_with_percentage = []
    for annotation in annotations:
        annotation.confidence_percentage = round(
            float(annotation.confidence_score or 0) * 100) if annotation.confidence_score else None
        annotations_with_percentage.append(annotation)

    context = {
        'document': document,
        'document_content': document_content,
        'annotations': annotations_with_percentage,
        'annotations_json': json.dumps(annotations_data),
        'entity_types': entity_types,
        'annotation_stats': annotation_stats,
        'audit_logs': audit_logs,
    }

    return render(request, 'annotation/expert_validation_detail.html', context)


@login_required
@require_http_methods(["POST"])
def expert_final_validation(request, document_id):
    """Validation finale d'un document par un expert"""

    # Vérifier les permissions
    if request.user.role not in ['admin', 'expert']:
        return JsonResponse({'success': False, 'error': 'Permission refusée'}, status=403)

    document = get_object_or_404(Document, id=document_id)

    try:
        data = json.loads(request.body)
        action = data.get('action')  # 'validate' ou 'reject'
        comments = data.get('comments', '')

        if action == 'validate':
            # Valider définitivement le document
            document.status = 'validated'
            document.validated_by = request.user
            document.save()

            # Marquer toutes les annotations comme définitivement validées
            document.annotations.update(
                status='validated',
                validated_by=request.user
            )

            # Log d'audit - CORRIGÉ pour utiliser les bons champs
            AuditLog.objects.create(
                user=request.user,
                document=document,
                action='expert_validate',
                description=f'Validation finale experte du document: {document.title}. Commentaires: {comments}',
                ip_address=request.META.get('REMOTE_ADDR', ''),
                metadata={'comments': comments}
            )

            return JsonResponse({
                'success': True,
                'message': 'Document validé définitivement par l\'expert',
                'status': 'validated'
            })

        elif action == 'reject':
            # Rejeter le document et remettre en annotation
            document.status = 'annotating'
            document.save()

            # Marquer les annotations comme à revoir
            document.annotations.filter(status='validated').update(
                status='modified'
            )

            # Log d'audit
            AuditLog.objects.create(
                user=request.user,
                document=document,
                action='expert_reject',
                description=f'Rejet expert du document: {document.title}. Raison: {comments}',
                ip_address=request.META.get('REMOTE_ADDR', ''),
                metadata={'reason': comments}
            )

            return JsonResponse({
                'success': True,
                'message': 'Document rejeté et remis en annotation',
                'status': 'annotating'
            })

        else:
            return JsonResponse({
                'success': False,
                'error': 'Action non valide'
            }, status=400)

    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'JSON invalide'}, status=400)
    except Exception as e:
        logger.error(f"Erreur validation experte: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["POST"])
def expert_annotation_feedback(request, annotation_id):
    """Feedback d'un expert sur une annotation spécifique"""

    # Vérifier les permissions
    if request.user.role not in ['admin', 'expert']:
        return JsonResponse({'success': False, 'error': 'Permission refusée'}, status=403)

    annotation = get_object_or_404(Annotation, id=annotation_id)

    try:
        data = json.loads(request.body)
        action = data.get('action')  # 'approve', 'modify', 'reject'
        feedback = data.get('feedback', '')

        if action == 'approve':
            annotation.status = 'validated'
            annotation.validated_by = request.user

        elif action == 'reject':
            annotation.status = 'rejected'
            annotation.validated_by = request.user

        elif action == 'modify':
            # L'expert peut suggérer des modifications
            annotation.status = 'modified'
            annotation.validated_by = request.user

            # Mettre à jour les champs si fournis
            if 'entity_type_id' in data:
                entity_type = get_object_or_404(EntityType, id=data['entity_type_id'])
                annotation.entity_type = entity_type

            if 'text' in data:
                annotation.text = data['text']

        annotation.save()

        # Log d'audit
        AuditLog.objects.create(
            user=request.user,
            document=annotation.document,
            action='expert_annotation_feedback',
            description=f'Feedback expert sur annotation "{annotation.text}": {action}. {feedback}',
            ip_address=request.META.get('REMOTE_ADDR', ''),
            metadata={'annotation_id': annotation.id, 'action': action, 'feedback': feedback}
        )

        return JsonResponse({
            'success': True,
            'message': f'Annotation {action}',
            'annotation': {
                'id': annotation.id,
                'status': annotation.status,
                'feedback': feedback
            }
        })

    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'JSON invalide'}, status=400)
    except Exception as e:
        logger.error(f"Erreur feedback annotation: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
def expert_dashboard_stats(request):
    """Statistiques spécialisées pour le dashboard des experts"""

    if request.user.role not in ['admin', 'expert']:
        return JsonResponse({'error': 'Permission refusée'}, status=403)

    # Documents en attente de validation experte
    documents_pending = Document.objects.filter(status='annotated').count()

    # Documents en cours de validation par cet expert
    documents_validating = Document.objects.filter(
        status='validating',
        validated_by=request.user
    ).count()

    # Documents validés par cet expert
    documents_validated = Document.objects.filter(
        status='validated',
        validated_by=request.user
    ).count()

    # Qualité moyenne des annotations
    total_annotations = Annotation.objects.count()
    validated_annotations = Annotation.objects.filter(status='validated').count()
    annotation_quality = (validated_annotations / total_annotations * 100) if total_annotations > 0 else 0

    # Statistiques par type d'entité
    entity_stats = []
    for entity_type in EntityType.objects.all():
        total = Annotation.objects.filter(entity_type=entity_type).count()
        validated = Annotation.objects.filter(
            entity_type=entity_type,
            status='validated'
        ).count()

        entity_stats.append({
            'name': entity_type.name,
            'total': total,
            'validated': validated,
            'quality': (validated / total * 100) if total > 0 else 0
        })

    return JsonResponse({
        'documents_pending': documents_pending,
        'documents_validating': documents_validating,
        'documents_validated': documents_validated,
        'annotation_quality': round(annotation_quality, 1),
        'entity_stats': entity_stats,
        'total_annotations': total_annotations,
        'validated_annotations': validated_annotations
    })


# Fonctions utilitaires

def calculate_annotation_quality(document):
    """Calculer la qualité des annotations d'un document"""
    total_annotations = document.annotations.count()
    if total_annotations == 0:
        return 0.0

    validated_annotations = document.annotations.filter(status='validated').count()
    return validated_annotations / total_annotations


def get_document_annotation_stats(document):
    """Obtenir les statistiques d'annotation d'un document"""
    annotations = document.annotations.all()
    total = annotations.count()

    if total == 0:
        return {
            'total': 0,
            'validated': 0,
            'pending': 0,
            'rejected': 0,
            'quality_score': 0.0
        }

    validated = annotations.filter(status='validated').count()
    pending = annotations.filter(status__in=['detected', 'modified']).count()
    rejected = annotations.filter(status='rejected').count()

    return {
        'total': total,
        'validated': validated,
        'pending': pending,
        'rejected': rejected,
        'quality_score': round(validated / total * 100, 1)
    }


def get_detailed_annotation_stats(document):
    """Obtenir des statistiques détaillées d'un document"""
    annotations = document.annotations.all()

    # Statistiques par type d'entité
    entity_stats = {}
    for annotation in annotations:
        entity_name = annotation.entity_type.name
        if entity_name not in entity_stats:
            entity_stats[entity_name] = {
                'total': 0,
                'validated': 0,
                'pending': 0,
                'rejected': 0
            }

        entity_stats[entity_name]['total'] += 1
        if annotation.status == 'validated':
            entity_stats[entity_name]['validated'] += 1
        elif annotation.status in ['detected', 'modified']:
            entity_stats[entity_name]['pending'] += 1
        elif annotation.status == 'rejected':
            entity_stats[entity_name]['rejected'] += 1

    # Statistiques par annotateur
    annotator_stats = {}
    for annotation in annotations:
        annotator = annotation.created_by.get_full_name() or annotation.created_by.username
        if annotator not in annotator_stats:
            annotator_stats[annotator] = {
                'total': 0,
                'validated': 0,
                'accuracy': 0.0
            }

        annotator_stats[annotator]['total'] += 1
        if annotation.status == 'validated':
            annotator_stats[annotator]['validated'] += 1

    # Calculer la précision de chaque annotateur
    for annotator in annotator_stats:
        total = annotator_stats[annotator]['total']
        validated = annotator_stats[annotator]['validated']
        annotator_stats[annotator]['accuracy'] = round(validated / total * 100, 1) if total > 0 else 0

    return {
        'entity_stats': entity_stats,
        'annotator_stats': annotator_stats,
        'overall_quality': calculate_annotation_quality(document) * 100
    }