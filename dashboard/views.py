# dashboard/views.py
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from documents.models import Document
from annotation.models import Annotation
from extraction.models import ExtractionResult
# Ajouter cet import en haut du fichier après les autres imports
from django.contrib.auth import get_user_model
from django.http import JsonResponse

User = get_user_model()


@login_required
def dashboard_home(request):
    user = request.user

    # Redirection selon le rôle
    if user.role == 'metadonneur':
        return render(request, 'dashboard/metadonneur.html', get_metadonneur_context(user))
    elif user.role == 'annotateur':
        return render(request, 'dashboard/annotateur.html', get_annotateur_context(user))
    elif user.role == 'expert':
        return render(request, 'dashboard/expert.html', get_expert_context(user))
    else:
        return render(request, 'dashboard/admin.html', get_admin_context(user))


def get_annotateur_context(user):
    # Statistiques pour annotateur
    total_planned = 150
    documents_to_annotate = Document.objects.filter(
        status__in=['extracted', 'annotating'],
        assigned_to=user
    ).count()

    documents_in_progress = Document.objects.filter(
        status='annotating',
        assigned_to=user
    ).count()

    documents_completed = Document.objects.filter(
        status__in=['annotated', 'validated'],
        assigned_to=user
    ).count()

    documents_refused = Document.objects.filter(
        status='refused',
        assigned_to=user
    ).count()

    # Documents pour annotation
    documents_list = Document.objects.filter(
        status__in=['extracted', 'annotating'],
        assigned_to=user
    ).select_related('document_type', 'context')[:10]

    # Statistiques des tâches
    total_annotations = Annotation.objects.filter(created_by=user).count()
    extraction_tasks = 15  # Exemple
    validation_tasks = 8  # Exemple
    finalization_tasks = 3  # Exemple

    return {
        'total_planned': total_planned,
        'documents_to_annotate': documents_to_annotate,
        'documents_in_progress': documents_in_progress,
        'documents_completed': documents_completed,
        'documents_refused': documents_refused,
        'completion_rate': round((documents_to_annotate / total_planned) * 100, 1) if total_planned > 0 else 0,
        'progress_rate': round((documents_in_progress / 25) * 100, 1),
        'documents_list': documents_list,
        'task_stats': {
            'extraction': {'count': extraction_tasks, 'percentage': 35},
            'validation': {'count': validation_tasks, 'percentage': 19},
            'finalization': {'count': finalization_tasks, 'percentage': 7},
        }
    }


def get_metadonneur_context(user):
    # Statistiques pour métadonneur
    total_planned = 150
    documents_scraped = Document.objects.filter(status='uploaded').count()
    documents_in_extraction = Document.objects.filter(status='extracting').count()
    documents_completed = Document.objects.filter(status__in=['extracted', 'annotated']).count()
    documents_refused = Document.objects.filter(status='refused').count()
    documents_re_scraping = Document.objects.filter(status='re_extracting').count()

    return {
        'total_planned': total_planned,
        'documents_scraped': documents_scraped,
        'documents_in_extraction': documents_in_extraction,
        'documents_completed': documents_completed,
        'documents_refused': documents_refused,
        'documents_re_scraping': documents_re_scraping,
        'completion_rate': round((documents_scraped / total_planned) * 100, 1) if total_planned > 0 else 0,
        'progress_rate': round((documents_in_extraction / 25) * 100, 1),
        'task_stats': {
            'extraction': {'count': 15, 'percentage': 35},
            'validation': {'count': 8, 'percentage': 19},
            'finalization': {'count': 3, 'percentage': 7},
        }
    }


def get_expert_context(user):
    # Statistiques pour expert
    total_planned = 150
    documents_scraped = Document.objects.filter(status__in=['annotated', 'validating']).count()
    documents_in_extraction = Document.objects.filter(status='validating').count()
    documents_completed = Document.objects.filter(status='validated').count()
    documents_refused = Document.objects.filter(status='refused').count()
    documents_re_scraping = Document.objects.filter(status='re_validating').count()

    return {
        'total_planned': total_planned,
        'documents_scraped': documents_scraped,
        'documents_in_extraction': documents_in_extraction,
        'documents_completed': documents_completed,
        'documents_refused': documents_refused,
        'documents_re_scraping': documents_re_scraping,
        'completion_rate': round((documents_scraped / total_planned) * 100, 1) if total_planned > 0 else 0,
        'progress_rate': round((documents_in_extraction / 25) * 100, 1),
        'task_stats': {
            'extraction': {'count': 15, 'percentage': 35},
            'validation': {'count': 8, 'percentage': 19},
            'finalization': {'count': 3, 'percentage': 7},
        }
    }


def get_admin_context(user):
    # Statistiques globales pour admin
    total_users = User.objects.count()
    total_documents = Document.objects.count()
    documents_processed = Document.objects.filter(status__in=['validated', 'completed']).count()

    return {
        'total_users': total_users,
        'total_documents': total_documents,
        'documents_processed': documents_processed,
        'processing_rate': round((documents_processed / total_documents) * 100, 1) if total_documents > 0 else 0,
    }


@login_required
def dashboard_stats(request):
    """API pour les statistiques du dashboard (JSON)"""
    user = request.user

    # Filtrer selon le rôle
    if user.role == 'admin':
        documents = Document.objects.all()
    elif user.role in ['annotateur', 'expert']:
        documents = Document.objects.filter(assigned_to=user)
    elif user.role == 'metadonneur':
        documents = Document.objects.all()
    else:
        documents = Document.objects.none()

    # Statistiques de base
    stats = {
        'total_documents': documents.count(),
        'documents_by_status': dict(
            documents.values('status')
            .annotate(count=Count('id'))
            .values_list('status', 'count')
        ),
    }

    # Statistiques spécifiques selon le rôle
    if user.role == 'annotateur':
        stats.update({
            'annotations_created': Annotation.objects.filter(created_by=user).count(),
            'documents_annotated': documents.filter(status='annotated').count(),
        })
    elif user.role == 'metadonneur':
        stats.update({
            'documents_extracted': documents.filter(status='extracted').count(),
        })
    elif user.role == 'expert':
        stats.update({
            'documents_validated': documents.filter(status='validated').count(),
        })
    elif user.role == 'admin':
        stats.update({
            'total_users': User.objects.count(),
            'total_annotations': Annotation.objects.count(),
        })

    return JsonResponse(stats)