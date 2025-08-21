# Chemin d'intégration : ctd_submission/additional_views.py
# Ce fichier contient les vues additionnelles pour compléter l'application CTD submission
from django.db import models
from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, HttpResponse
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.decorators.csrf import csrf_exempt
from django.core.paginator import Paginator
from django.db.models import Q, Count
from django.utils import timezone
from django.conf import settings
import json
import os
from .models import Submission, Document, CTDModule, CTDSection, TemplateField, AIAnalysisResult
from .utils import CTDStructureGenerator, DocumentProcessor


@login_required
def submission_edit(request, submission_id):
    """
    Modification d'une soumission existante
    """
    # Chemin d'intégration : URL 'submission_edit' -> ctd_submission/additional_views.py
    submission = get_object_or_404(Submission, id=submission_id, created_by=request.user)

    if request.method == 'POST':
        # Traitement du formulaire de modification
        submission.name = request.POST.get('name', submission.name)
        submission.region = request.POST.get('region', submission.region)
        submission.submission_type = request.POST.get('submission_type', submission.submission_type)
        submission.variation_type = request.POST.get('variation_type', submission.variation_type)
        submission.change_description = request.POST.get('change_description', submission.change_description)
        submission.save()

        messages.success(request, 'Soumission mise à jour avec succès!')
        return redirect('submission_detail', submission_id=submission.id)

    context = {
        'submission': submission,
        'is_edit_mode': True
    }
    return render(request, 'ctd_submission/submission_create.html', context)


@login_required
def submission_delete(request, submission_id):
    """
    Suppression d'une soumission
    """
    # Chemin d'intégration : URL 'submission_delete' -> ctd_submission/additional_views.py
    submission = get_object_or_404(Submission, id=submission_id, created_by=request.user)

    if request.method == 'POST':
        submission_name = submission.name
        submission.delete()
        messages.success(request, f'Soumission "{submission_name}" supprimée avec succès!')
        return redirect('dashboard')

    context = {'submission': submission}
    return render(request, 'ctd_submission/submission_confirm_delete.html', context)


@login_required
def document_download(request, document_id):
    """
    Téléchargement d'un document
    """
    # Chemin d'intégration : URL 'document_download' -> ctd_submission/additional_views.py
    document = get_object_or_404(Document, id=document_id, submission__created_by=request.user)

    if document.file:
        response = HttpResponse(document.file.read(), content_type='application/octet-stream')
        response['Content-Disposition'] = f'attachment; filename="{document.name}"'
        return response
    else:
        messages.error(request, 'Fichier non disponible pour le téléchargement')
        return redirect('document_view', document_id=document.id)


@login_required
def document_delete(request, document_id):
    """
    Suppression d'un document
    """
    # Chemin d'intégration : URL 'document_delete' -> ctd_submission/additional_views.py
    document = get_object_or_404(Document, id=document_id, submission__created_by=request.user)

    if request.method == 'DELETE':
        document_name = document.name
        submission_id = document.submission.id

        # Supprimer le fichier physique
        if document.file:
            try:
                os.remove(document.file.path)
            except OSError:
                pass

        document.delete()

        return JsonResponse({
            'success': True,
            'message': f'Document "{document_name}" supprimé avec succès'
        })

    return JsonResponse({'success': False, 'message': 'Méthode non autorisée'})


@login_required
def initialize_ctd_modules(request):
    """
    Initialisation des modules CTD de base
    """
    # Chemin d'intégration : URL 'initialize_ctd_modules' -> ctd_submission/additional_views.py
    if request.method == 'POST':
        generator = CTDStructureGenerator()
        modules = generator.initialize_default_structure()

        return JsonResponse({
            'success': True,
            'message': f'{len(modules)} modules CTD initialisés',
            'modules': [{'code': m.code, 'name': m.name} for m in modules]
        })

    return JsonResponse({'success': False, 'message': 'Méthode non autorisée'})


@csrf_exempt
@login_required
def template_edit_field(request, field_id):
    """
    Modification d'un champ de template
    """
    # Chemin d'intégration : URL 'template_edit_field' -> ctd_submission/additional_views.py
    field = get_object_or_404(TemplateField, id=field_id, document__submission__created_by=request.user)

    if request.method == 'POST':
        field.field_label = request.POST.get('field_label', field.field_label)
        field.field_type = request.POST.get('field_type', field.field_type)
        field.field_value = request.POST.get('field_value', field.field_value)
        field.is_required = request.POST.get('is_required') == 'true'

        # Traitement des options pour select/checkbox
        if field.field_type in ['select', 'checkbox']:
            options_text = request.POST.get('field_options', '')
            field.field_options = [opt.strip() for opt in options_text.split('\n') if opt.strip()]

        field.save()

        return JsonResponse({
            'success': True,
            'message': 'Champ mis à jour avec succès'
        })

    return JsonResponse({'success': False, 'message': 'Méthode non autorisée'})


@login_required
def reports_dashboard(request):
    """
    Dashboard des rapports et statistiques
    """
    # Chemin d'intégration : URL 'reports_dashboard' -> ctd_submission/additional_views.py
    user_submissions = Submission.objects.filter(created_by=request.user)

    # Statistiques globales
    stats = {
        'total_submissions': user_submissions.count(),
        'by_status': user_submissions.values('status').annotate(count=Count('id')),
        'by_region': user_submissions.values('region').annotate(count=Count('id')),
        'total_documents': Document.objects.filter(submission__created_by=request.user).count(),
        'documents_with_templates': Document.objects.filter(
            submission__created_by=request.user,
            is_template_generated=True
        ).count(),
        'ai_analyzed_documents': AIAnalysisResult.objects.filter(
            document__submission__created_by=request.user
        ).count()
    }

    # Soumissions récentes avec progression
    recent_submissions = user_submissions.order_by('-created_at')[:10]

    context = {
        'stats': stats,
        'recent_submissions': recent_submissions
    }
    return render(request, 'ctd_submission/reports_dashboard.html', context)


@login_required
def submission_report(request, submission_id):
    """
    Rapport détaillé d'une soumission
    """
    # Chemin d'intégration : URL 'submission_report' -> ctd_submission/additional_views.py
    submission = get_object_or_404(Submission, id=submission_id, created_by=request.user)

    # Récupérer toutes les données pour le rapport
    documents = submission.documents.all().prefetch_related('section', 'ai_analysis', 'template_fields')

    # Statistiques de la soumission
    submission_stats = {
        'total_documents': documents.count(),
        'documents_by_type': documents.values('document_type').annotate(count=Count('id')),
        'documents_by_module': documents.values('section__module__name').annotate(count=Count('id')),
        'templates_generated': documents.filter(is_template_generated=True).count(),
        'ai_confidence_avg': documents.filter(ai_analysis__isnull=False).aggregate(
            avg_confidence=models.Avg('ai_analysis__confidence_score')
        )['avg_confidence'] or 0
    }

    context = {
        'submission': submission,
        'documents': documents,
        'stats': submission_stats
    }
    return render(request, 'ctd_submission/submission_report.html', context)


@login_required
def ai_assistant(request):
    """
    Interface de l'assistant IA pour les questions réglementaires
    """
    # Chemin d'intégration : URL 'ai_assistant' -> ctd_submission/additional_views.py
    if request.method == 'POST':
        user_question = request.POST.get('question', '')

        # Simulation d'une réponse de l'assistant IA
        # Dans un vrai système, cela ferait appel à un modèle IA
        ai_responses = {
            'ema': 'Pour les soumissions EMA, vous devez suivre le format CTD avec les modules 1-5...',
            'fda': 'Pour les soumissions FDA, le format eCTD est requis avec...',
            'variation': 'Les variations de type IA nécessitent...',
            'cover letter': 'La lettre de couverture doit contenir les informations suivantes...'
        }

        # Recherche de mots-clés dans la question
        response = "Je peux vous aider avec vos questions réglementaires. Pouvez-vous être plus spécifique ?"
        for keyword, ai_response in ai_responses.items():
            if keyword in user_question.lower():
                response = ai_response
                break

        return JsonResponse({
            'success': True,
            'response': response,
            'suggestions': [
                'Comment structurer un dossier EMA ?',
                'Quels documents sont requis pour une variation Type IA ?',
                'Comment remplir une cover letter ?'
            ]
        })

    return render(request, 'ctd_submission/ai_assistant.html')


@login_required
def help_center(request):
    """
    Centre d'aide et documentation
    """
    # Chemin d'intégration : URL 'help_center' -> ctd_submission/additional_views.py
    context = {
        'help_sections': [
            {
                'title': 'Getting Started',
                'topics': [
                    'Créer votre première soumission',
                    'Upload de documents',
                    'Génération de structure CTD'
                ]
            },
            {
                'title': 'Templates',
                'topics': [
                    'Utilisation des templates',
                    'Modification des formulaires',
                    'Export des données'
                ]
            },
            {
                'title': 'IA et Analyse',
                'topics': [
                    'Comment fonctionne l\'analyse IA',
                    'Améliorer la précision',
                    'Résoudre les erreurs de classification'
                ]
            }
        ]
    }
    return render(request, 'ctd_submission/help_center.html', context)


# Vues AJAX pour les appels asynchrones

@csrf_exempt
@login_required
def ajax_search_documents(request):
    """
    Recherche AJAX de documents
    """
    # Chemin d'intégration : URL 'ajax_search_documents' -> ctd_submission/additional_views.py
    if request.method == 'GET':
        query = request.GET.get('q', '')
        submission_id = request.GET.get('submission_id')

        documents = Document.objects.filter(submission__created_by=request.user)

        if submission_id:
            documents = documents.filter(submission_id=submission_id)

        if query:
            documents = documents.filter(
                Q(name__icontains=query) |
                Q(section__name__icontains=query)
            )

        results = []
        for doc in documents[:10]:  # Limiter à 10 résultats
            results.append({
                'id': doc.id,
                'name': doc.name,
                'type': doc.document_type,
                'section': f"{doc.section.code} {doc.section.name}" if doc.section else 'Non classifié',
                'url': f'/document/{doc.id}/view/'
            })

        return JsonResponse({'results': results})

    return JsonResponse({'error': 'Méthode non autorisée'})


@csrf_exempt
@login_required
def ajax_validate_template(request):
    """
    Validation AJAX d'un template
    """
    # Chemin d'intégration : URL 'ajax_validate_template' -> ctd_submission/additional_views.py
    if request.method == 'POST':
        document_id = request.POST.get('document_id')
        template_data = json.loads(request.POST.get('template_data', '{}'))

        document = get_object_or_404(Document, id=document_id, submission__created_by=request.user)

        # Validation des champs obligatoires
        required_fields = TemplateField.objects.filter(document=document, is_required=True)
        errors = []

        for field in required_fields:
            field_key = f'field_{field.id}'
            if field_key not in template_data or not template_data[field_key]:
                errors.append(f'Le champ "{field.field_label}" est obligatoire')

        return JsonResponse({
            'valid': len(errors) == 0,
            'errors': errors
        })

    return JsonResponse({'error': 'Méthode non autorisée'})


@csrf_exempt
@login_required
def ajax_auto_save_template(request):
    """
    Sauvegarde automatique AJAX d'un template
    """
    # Chemin d'intégration : URL 'ajax_auto_save_template' -> ctd_submission/additional_views.py
    if request.method == 'POST':
        document_id = request.POST.get('document_id')
        template_data = json.loads(request.POST.get('template_data', '{}'))

        document = get_object_or_404(Document, id=document_id, submission__created_by=request.user)

        # Sauvegarder les données du template
        document.template_data = template_data
        document.save()

        return JsonResponse({
            'success': True,
            'message': 'Template sauvegardé automatiquement',
            'timestamp': timezone.now().isoformat()
        })

    return JsonResponse({'error': 'Méthode non autorisée'})


@csrf_exempt
@login_required
def ajax_suggest_classification(request):
    """
    Suggestion AJAX de classification pour un document
    """
    # Chemin d'intégration : URL 'ajax_suggest_classification' -> ctd_submission/additional_views.py
    if request.method == 'POST':
        document_id = request.POST.get('document_id')
        document = get_object_or_404(Document, id=document_id, submission__created_by=request.user)

        # Utiliser l'analyseur pour suggérer une classification
        from .utils import CTDAnalyzer
        analyzer = CTDAnalyzer()
        analysis_result = analyzer.analyze_document(document)

        if analysis_result:
            return JsonResponse({
                'success': True,
                'suggestion': {
                    'module': {
                        'id': analysis_result['module'].id,
                        'code': analysis_result['module'].code,
                        'name': analysis_result['module'].name
                    },
                    'section': {
                        'id': analysis_result['section'].id,
                        'code': analysis_result['section'].code,
                        'name': analysis_result['section'].name
                    },
                    'confidence': analysis_result['confidence'],
                    'keywords': analysis_result['keywords']
                }
            })
        else:
            return JsonResponse({
                'success': False,
                'message': 'Impossible de déterminer une classification automatique'
            })

    return JsonResponse({'error': 'Méthode non autorisée'})


@csrf_exempt
@login_required
def ajax_get_submission_status(request):
    """
    Récupération AJAX du statut d'une soumission
    """
    # Chemin d'intégration : URL 'ajax_get_submission_status' -> ctd_submission/additional_views.py
    if request.method == 'GET':
        submission_id = request.GET.get('submission_id')
        submission = get_object_or_404(Submission, id=submission_id, created_by=request.user)

        # Calculer la progression
        total_documents = submission.documents.count()
        processed_documents = submission.documents.filter(is_template_generated=True).count()

        progress = (processed_documents / total_documents * 100) if total_documents > 0 else 0

        return JsonResponse({
            'status': submission.status,
            'status_display': submission.get_status_display(),
            'progress': progress,
            'total_documents': total_documents,
            'processed_documents': processed_documents,
            'last_updated': submission.updated_at.isoformat()
        })

    return JsonResponse({'error': 'Méthode non autorisée'})