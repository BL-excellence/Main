# audit/views.py
from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.core.paginator import Paginator
from .models import AuditLog, DocumentVersion
from documents.models import Document
import csv
from datetime import datetime


@login_required
def audit_trail(request):
    """Journal d'audit et traçabilité"""

    # Filtrage
    document_id = request.GET.get('document')
    action_filter = request.GET.get('action')
    user_filter = request.GET.get('user')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')

    logs = AuditLog.objects.all().select_related('user', 'document')

    if document_id:
        logs = logs.filter(document_id=document_id)
    if action_filter:
        logs = logs.filter(action=action_filter)
    if user_filter:
        logs = logs.filter(user_id=user_filter)
    if date_from:
        logs = logs.filter(timestamp__date__gte=date_from)
    if date_to:
        logs = logs.filter(timestamp__date__lte=date_to)

    # Pagination
    paginator = Paginator(logs, 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Données pour les filtres
    from accounts.models import User
    documents = Document.objects.all().order_by('title')
    users = User.objects.all().order_by('first_name', 'last_name')
    actions = AuditLog.ACTION_CHOICES

    context = {
        'page_obj': page_obj,
        'documents': documents,
        'users': users,
        'actions': actions,
        'current_filters': {
            'document': document_id,
            'action': action_filter,
            'user': user_filter,
            'date_from': date_from,
            'date_to': date_to,
        }
    }

    return render(request, 'audit/trail.html', context)


@login_required
def document_audit_trail(request, document_id):
    """Trail d'audit pour un document spécifique"""
    document = get_object_or_404(Document, id=document_id)

    # Logs d'audit
    logs = AuditLog.objects.filter(document=document).select_related('user')

    # Versions du document
    versions = DocumentVersion.objects.filter(document=document).select_related('created_by')

    context = {
        'document': document,
        'logs': logs,
        'versions': versions,
    }

    return render(request, 'audit/document_trail.html', context)


@login_required
def export_audit(request):
    """Exporter les logs d'audit en CSV"""

    # Récupération des filtres depuis la session ou les paramètres
    logs = AuditLog.objects.all().select_related('user', 'document')

    # Application des filtres de la requête précédente si nécessaire
    # ... (logique de filtrage similaire à audit_trail)

    response = HttpResponse(content_type='text/csv')
    response[
        'Content-Disposition'] = f'attachment; filename="audit_logs_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv"'

    writer = csv.writer(response)
    writer.writerow([
        'Timestamp', 'Utilisateur', 'Document', 'Action',
        'Description', 'Adresse IP'
    ])

    for log in logs:
        writer.writerow([
            log.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            log.user.get_full_name() or log.user.username,
            log.document.title if log.document else '',
            log.get_action_display(),
            log.description,
            log.ip_address or ''
        ])

    return response