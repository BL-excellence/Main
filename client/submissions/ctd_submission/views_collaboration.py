# ctd_submission/views_collaboration.py
# Vues pour la collaboration et les fonctionnalités avancées

from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, HttpResponse, StreamingHttpResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from django.db import transaction, models
from django.db.models import Q, Count, Avg
from django.core.paginator import Paginator
from django.contrib import messages
import json
import logging
from datetime import timedelta
from typing import Dict, List, Optional

from .models_enhanced import EnhancedDocument, SmartSuggestion, DocumentMetrics, DocumentStructure

DocumentMetrics
from .models import (
    Document, DocumentAnnotation, CollaborationSession,
     UserPreferences
)
from .utils import IntelligentCopilot

logger = logging.getLogger(__name__)


@login_required
@csrf_exempt
def start_collaboration(request, document_id):
    """
    Démarre une session de collaboration sur un document
    """
    document = get_object_or_404(Document, id=document_id, submission__created_by=request.user)

    if request.method == 'POST':
        try:
            # Créer ou mettre à jour la session de collaboration
            session, created = CollaborationSession.objects.update_or_create(
                document=document,
                user=request.user,
                defaults={
                    'is_active': True,
                    'last_activity': timezone.now()
                }
            )

            # Désactiver les anciennes sessions de l'utilisateur
            CollaborationSession.objects.filter(
                user=request.user,
                is_active=True
            ).exclude(id=session.id).update(is_active=False)

            # Obtenir les autres collaborateurs actifs
            active_collaborators = document.get_active_collaborators().exclude(user=request.user)

            collaborators_data = []
            for collab in active_collaborators:
                collaborators_data.append({
                    'user_id': collab.user.id,
                    'username': collab.user.username,
                    'full_name': collab.user.get_full_name() or collab.user.username,
                    'last_activity': collab.last_activity.isoformat(),
                    'active_element': collab.active_element
                })

            return JsonResponse({
                'success': True,
                'session_id': str(session.session_id),
                'active_collaborators': collaborators_data,
                'collaboration_enabled': document.collaboration_enabled
            })

        except Exception as e:
            logger.error(f"Erreur démarrage collaboration: {e}")
            return JsonResponse({
                'success': False,
                'message': str(e)
            })

    return JsonResponse({'success': False, 'message': 'Méthode non autorisée'})


@login_required
def get_document_annotations(request, document_id):
    """
    Récupère les annotations d'un document
    """
    document = get_object_or_404(Document, id=document_id, submission__created_by=request.user)

    annotations = DocumentAnnotation.objects.filter(document=document).select_related('created_by', 'resolved_by')

    # Filtrer selon les paramètres
    annotation_type = request.GET.get('type')
    if annotation_type:
        annotations = annotations.filter(annotation_type=annotation_type)

    show_resolved = request.GET.get('show_resolved', 'false').lower() == 'true'
    if not show_resolved:
        annotations = annotations.filter(is_resolved=False)

    annotations_data = []
    for annotation in annotations:
        annotations_data.append({
            'id': annotation.id,
            'type': annotation.annotation_type,
            'content': annotation.content,
            'position_data': annotation.position_data,
            'selected_text': annotation.selected_text,
            'created_by': {
                'id': annotation.created_by.id,
                'username': annotation.created_by.username,
                'full_name': annotation.created_by.get_full_name() or annotation.created_by.username
            },
            'created_at': annotation.created_at.isoformat(),
            'is_resolved': annotation.is_resolved,
            'resolved_by': {
                'id': annotation.resolved_by.id,
                'username': annotation.resolved_by.username,
                'full_name': annotation.resolved_by.get_full_name() or annotation.resolved_by.username
            } if annotation.resolved_by else None,
            'resolved_at': annotation.resolved_at.isoformat() if annotation.resolved_at else None
        })

    return JsonResponse({
        'success': True,
        'annotations': annotations_data,
        'total_count': len(annotations_data)
    })


@login_required
@csrf_exempt
def add_document_annotation(request, document_id):
    """
    Ajoute une annotation à un document
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Méthode non autorisée'})

    document = get_object_or_404(Document, id=document_id, submission__created_by=request.user)

    try:
        data = json.loads(request.body)

        annotation = DocumentAnnotation.objects.create(
            document=document,
            annotation_type=data.get('type', 'comment'),
            content=data.get('content', ''),
            position_data=data.get('position_data', {}),
            selected_text=data.get('selected_text', ''),
            created_by=request.user
        )

        return JsonResponse({
            'success': True,
            'annotation': {
                'id': annotation.id,
                'type': annotation.annotation_type,
                'content': annotation.content,
                'position_data': annotation.position_data,
                'selected_text': annotation.selected_text,
                'created_by': {
                    'id': request.user.id,
                    'username': request.user.username,
                    'full_name': request.user.get_full_name() or request.user.username
                },
                'created_at': annotation.created_at.isoformat(),
                'is_resolved': False
            }
        })

    except Exception as e:
        logger.error(f"Erreur ajout annotation: {e}")
        return JsonResponse({
            'success': False,
            'message': str(e)
        })


@login_required
@csrf_exempt
def resolve_annotation(request, annotation_id):
    """
    Marque une annotation comme résolue
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Méthode non autorisée'})

    annotation = get_object_or_404(
        DocumentAnnotation,
        id=annotation_id,
        document__submission__created_by=request.user
    )

    try:
        annotation.mark_resolved(request.user)

        return JsonResponse({
            'success': True,
            'message': 'Annotation marquée comme résolue',
            'resolved_at': annotation.resolved_at.isoformat(),
            'resolved_by': {
                'id': request.user.id,
                'username': request.user.username,
                'full_name': request.user.get_full_name() or request.user.username
            }
        })

    except Exception as e:
        logger.error(f"Erreur résolution annotation: {e}")
        return JsonResponse({
            'success': False,
            'message': str(e)
        })


@login_required
def user_preferences(request):
    """
    Affiche et gère les préférences utilisateur
    """
    preferences, created = UserPreferences.objects.get_or_create(user=request.user)

    if request.method == 'POST':
        # Mettre à jour les préférences
        preferences.default_edit_mode = request.POST.get('default_edit_mode', 'text')
        preferences.auto_save_enabled = request.POST.get('auto_save_enabled') == 'on'
        preferences.auto_save_interval = int(request.POST.get('auto_save_interval', 120))
        preferences.copilot_enabled = request.POST.get('copilot_enabled') == 'on'
        preferences.copilot_sensitivity = request.POST.get('copilot_sensitivity', 'medium')
        preferences.collaboration_enabled = request.POST.get('collaboration_enabled') == 'on'
        preferences.theme = request.POST.get('theme', 'light')

        preferences.save()
        messages.success(request, 'Préférences mises à jour avec succès')
        return redirect('ctd_submission:user_preferences')

    context = {
        'preferences': preferences,
        'edit_modes': [
            ('text', 'Mode Texte'),
            ('visual', 'Mode Visuel'),
            ('structure', 'Mode Structure')
        ],
        'sensitivities': [
            ('low', 'Faible'),
            ('medium', 'Moyenne'),
            ('high', 'Élevée')
        ],
        'themes': [
            ('light', 'Clair'),
            ('dark', 'Sombre'),
            ('auto', 'Automatique')
        ]
    }

    return render(request, 'ctd_submission/user_preferences.html', context)


@login_required
@csrf_exempt
def update_user_preferences(request):
    """
    API pour mettre à jour les préférences utilisateur
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Méthode non autorisée'})

    try:
        data = json.loads(request.body)
        preferences, created = UserPreferences.objects.get_or_create(user=request.user)

        # Mettre à jour les champs fournis
        for field, value in data.items():
            if hasattr(preferences, field):
                setattr(preferences, field, value)

        preferences.save()

        return JsonResponse({
            'success': True,
            'message': 'Préférences mises à jour',
            'preferences': {
                'default_edit_mode': preferences.default_edit_mode,
                'auto_save_enabled': preferences.auto_save_enabled,
                'auto_save_interval': preferences.auto_save_interval,
                'copilot_enabled': preferences.copilot_enabled,
                'copilot_sensitivity': preferences.copilot_sensitivity,
                'collaboration_enabled': preferences.collaboration_enabled,
                'theme': preferences.theme
            }
        })

    except Exception as e:
        logger.error(f"Erreur mise à jour préférences: {e}")
        return JsonResponse({
            'success': False,
            'message': str(e)
        })


@login_required
def document_analytics(request, document_id):
    """
    Affiche les analytics détaillées d'un document
    """
    document = get_object_or_404(Document, id=document_id, submission__created_by=request.user)

    # Récupérer ou créer les métriques
    metrics, created = DocumentMetrics.objects.get_or_create(document=document)

    # Statistiques de collaboration
    collaboration_stats = {
        'total_sessions': CollaborationSession.objects.filter(document=document).count(),
        'unique_collaborators': CollaborationSession.objects.filter(
            document=document
        ).values('user').distinct().count(),
        'total_annotations': DocumentAnnotation.objects.filter(document=document).count(),
        'resolved_annotations': DocumentAnnotation.objects.filter(
            document=document, is_resolved=True
        ).count()
    }

    # Suggestions par type
    suggestions_by_type = SmartSuggestion.objects.filter(document=document).values(
        'suggestion_type'
    ).annotate(count=Count('id')).order_by('-count')

    # Activité récente
    recent_activity = CollaborationSession.objects.filter(
        document=document,
        last_activity__gte=timezone.now() - timedelta(days=7)
    ).select_related('user').order_by('-last_activity')[:10]

    context = {
        'document': document,
        'metrics': metrics,
        'collaboration_stats': collaboration_stats,
        'suggestions_by_type': suggestions_by_type,
        'recent_activity': recent_activity,
        'quality_score': metrics.get_quality_score(),
        'readability_score': metrics.calculate_readability_score()
    }

    return render(request, 'ctd_submission/document_analytics.html', context)


@login_required
@csrf_exempt
def get_smart_suggestions(request, document_id):
    """
    Récupère les suggestions intelligentes pour un document
    """
    document = get_object_or_404(Document, id=document_id, submission__created_by=request.user)

    # Filtres
    suggestion_type = request.GET.get('type')
    priority = request.GET.get('priority')
    status = request.GET.get('status', 'pending')

    suggestions = SmartSuggestion.objects.filter(
        document=document,
        status=status
    ).select_related('applied_by')

    if suggestion_type:
        suggestions = suggestions.filter(suggestion_type=suggestion_type)

    if priority:
        suggestions = suggestions.filter(priority=priority)

    # Pagination
    paginator = Paginator(suggestions, 20)
    page = request.GET.get('page', 1)
    suggestions_page = paginator.get_page(page)

    suggestions_data = []
    for suggestion in suggestions_page:
        suggestions_data.append({
            'id': suggestion.id,
            'type': suggestion.suggestion_type,
            'priority': suggestion.priority,
            'title': suggestion.title,
            'message': suggestion.message,
            'suggested_replacement': suggestion.suggested_replacement,
            'confidence_score': suggestion.confidence_score,
            'reasoning': suggestion.reasoning,
            'element_id': suggestion.element_id,
            'text_selection': suggestion.text_selection,
            'position_data': suggestion.position_data,
            'status': suggestion.status,
            'created_at': suggestion.created_at.isoformat(),
            'priority_color': suggestion.get_priority_color()
        })

    return JsonResponse({
        'success': True,
        'suggestions': suggestions_data,
        'pagination': {
            'current_page': suggestions_page.number,
            'total_pages': paginator.num_pages,
            'has_next': suggestions_page.has_next(),
            'has_previous': suggestions_page.has_previous(),
            'total_count': paginator.count
        }
    })


@login_required
@csrf_exempt
def apply_smart_suggestion(request, suggestion_id):
    """
    Applique une suggestion intelligente
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Méthode non autorisée'})

    suggestion = get_object_or_404(
        SmartSuggestion,
        id=suggestion_id,
        document__submission__created_by=request.user
    )

    try:
        suggestion.apply_suggestion(request.user)

        return JsonResponse({
            'success': True,
            'message': 'Suggestion appliquée avec succès',
            'applied_at': suggestion.applied_at.isoformat()
        })

    except Exception as e:
        logger.error(f"Erreur application suggestion: {e}")
        return JsonResponse({
            'success': False,
            'message': str(e)
        })


@login_required
@csrf_exempt
def reject_smart_suggestion(request, suggestion_id):
    """
    Rejette une suggestion intelligente
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Méthode non autorisée'})

    suggestion = get_object_or_404(
        SmartSuggestion,
        id=suggestion_id,
        document__submission__created_by=request.user
    )

    try:
        suggestion.reject_suggestion(request.user)

        return JsonResponse({
            'success': True,
            'message': 'Suggestion rejetée'
        })

    except Exception as e:
        logger.error(f"Erreur rejet suggestion: {e}")
        return JsonResponse({
            'success': False,
            'message': str(e)
        })


@login_required
def document_structure_view(request, document_id):
    """
    Affiche la structure détaillée d'un document
    """
    document = get_object_or_404(Document, id=document_id, submission__created_by=request.user)

    # Récupérer la structure du document
    structure_elements = DocumentStructure.objects.filter(
        document=document
    ).order_by('order_index')

    # Organiser en arbre hiérarchique
    def build_tree(elements, parent=None):
        tree = []
        for element in elements:
            if element.parent_element == parent:
                children = build_tree(elements, element)
                tree.append({
                    'element': element,
                    'children': children
                })
        return tree

    structure_tree = build_tree(structure_elements)

    # Statistiques de structure
    structure_stats = {
        'total_elements': structure_elements.count(),
        'headings': structure_elements.filter(element_type='heading').count(),
        'paragraphs': structure_elements.filter(element_type='paragraph').count(),
        'tables': structure_elements.filter(element_type='table').count(),
        'images': structure_elements.filter(element_type='image').count(),
        'max_depth': structure_elements.aggregate(
            max_depth=models.Max('hierarchy_level')
        )['max_depth'] or 0
    }

    context = {
        'document': document,
        'structure_tree': structure_tree,
        'structure_stats': structure_stats
    }

    return render(request, 'ctd_submission/document_structure.html', context)


@login_required
@csrf_exempt
def update_collaboration_status(request, document_id):
    """
    Met à jour le statut de collaboration d'un utilisateur
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Méthode non autorisée'})

    document = get_object_or_404(Document, id=document_id, submission__created_by=request.user)

    try:
        data = json.loads(request.body)

        session = CollaborationSession.objects.filter(
            document=document,
            user=request.user,
            is_active=True
        ).first()

        if session:
            session.cursor_position = data.get('cursor_position', {})
            session.active_element = data.get('active_element', '')
            session.last_activity = timezone.now()
            session.save()

            return JsonResponse({
                'success': True,
                'session_updated': True
            })
        else:
            return JsonResponse({
                'success': False,
                'message': 'Session de collaboration non trouvée'
            })

    except Exception as e:
        logger.error(f"Erreur mise à jour collaboration: {e}")
        return JsonResponse({
            'success': False,
            'message': str(e)
        })


@login_required
def get_collaboration_status(request, document_id):
    """
    Récupère le statut de collaboration actuel
    """
    document = get_object_or_404(Document, id=document_id, submission__created_by=request.user)

    # Collaborateurs actifs (dernière activité < 5 minutes)
    recent_time = timezone.now() - timedelta(minutes=5)
    active_sessions = CollaborationSession.objects.filter(
        document=document,
        is_active=True,
        last_activity__gte=recent_time
    ).select_related('user')

    collaborators = []
    for session in active_sessions:
        collaborators.append({
            'user_id': session.user.id,
            'username': session.user.username,
            'full_name': session.user.get_full_name() or session.user.username,
            'cursor_position': session.cursor_position,
            'active_element': session.active_element,
            'last_activity': session.last_activity.isoformat(),
            'is_current_user': session.user == request.user
        })

    return JsonResponse({
        'success': True,
        'collaborators': collaborators,
        'total_active': len(collaborators)
    })


@login_required
def export_document_analytics(request, document_id):
    """
    Exporte les analytics d'un document en CSV
    """
    document = get_object_or_404(Document, id=document_id, submission__created_by=request.user)

    import csv
    from django.http import HttpResponse

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{document.name}_analytics.csv"'

    writer = csv.writer(response)

    # En-têtes
    writer.writerow([
        'Métrique', 'Valeur', 'Description'
    ])

    # Métriques de base
    metrics = getattr(document, 'metrics', None)
    if metrics:
        writer.writerow(['Mots totaux', metrics.total_words, 'Nombre total de mots'])
        writer.writerow(['Caractères', metrics.total_characters, 'Nombre total de caractères'])
        writer.writerow(['Phrases', metrics.total_sentences, 'Nombre total de phrases'])
        writer.writerow(['Paragraphes', metrics.total_paragraphs, 'Nombre total de paragraphes'])
        writer.writerow(['Titres', metrics.total_headings, 'Nombre total de titres'])
        writer.writerow(['Tableaux', metrics.total_tables, 'Nombre total de tableaux'])
        writer.writerow(['Longueur moyenne phrase', metrics.average_sentence_length, 'Mots par phrase en moyenne'])
        writer.writerow(['Score lisibilité', metrics.readability_score, 'Score de lisibilité (0-10)'])
        writer.writerow(['Score qualité', metrics.get_quality_score(), 'Score de qualité global (0-10)'])
        writer.writerow(['Éditions totales', metrics.total_edits, 'Nombre total d\'éditions'])
        writer.writerow(['Éditeurs uniques', metrics.unique_editors, 'Nombre d\'éditeurs différents'])
        writer.writerow(['Commentaires', metrics.total_comments, 'Nombre total de commentaires'])
        writer.writerow(['Erreurs orthographe', metrics.spelling_errors, 'Erreurs d\'orthographe détectées'])
        writer.writerow(['Problèmes grammaire', metrics.grammar_issues, 'Problèmes de grammaire détectés'])

    return response