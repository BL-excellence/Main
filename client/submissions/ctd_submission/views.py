# ctd_submission/views.py - VERSION CORRIGÉE
# Corrections pour la communication avec utils.py
# Ajoutez ces imports en haut du fichier views.py
import logging
from audioop import reverse

from django.contrib import messages

from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, HttpResponse
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.views.decorators.csrf import csrf_exempt
from django.core.files.storage import default_storage
from django.conf import settings
from django.db.models import Q, Count, Max
from django.core.paginator import Paginator
from django.utils import timezone
from django.middleware.csrf import get_token  # AJOUT pour le token CSRF
import json
import os
import re
import logging

from django.views.decorators.http import require_http_methods

# Imports des modèles
from .models import (
    Submission, Document, CTDModule, CTDSection,
    TemplateField, AIAnalysisResult, DocumentVersion
)
from .forms import SubmissionForm, DocumentUploadForm, TemplateForm

# CORRECTION 1: Import correct des classes utils avec gestion d'erreurs
try:
    from .utils import (
        CTDAnalyzer,
        DocumentProcessor,
        IntelligentCopilot,
        DocumentExporter,
        CTDStructureGenerator,
        AdvancedCTDAnalyzer, DJANGO_AVAILABLE, MODELS_AVAILABLE, FaithfulPDFProcessor
)

    UTILS_AVAILABLE = True
except ImportError as e:
    print(f"Erreur import utils: {e}")
    UTILS_AVAILABLE = False


    # Classes de fallback
    class CTDAnalyzer:
        def analyze_document(self, document):
            return None


    class DocumentProcessor:
        def extract_content(self, document):
            return {'text': f'Document: {document.name}', 'extracted': False}

        def update_document_from_template(self, document):
            return False


    class IntelligentCopilot:
        def analyze_global_changes(self, document, changes):
            return []

        def get_smart_suggestions(self, document, change_type, content, context):
            return []

        def suggest_template_positions(self, document, template_data):
            return []


    class DocumentExporter:
        def export_modified_document(self, document):
            return None


    class CTDStructureGenerator:
        def initialize_default_structure(self):
            return []

import zipfile
import csv

logger = logging.getLogger(__name__)

# CORRECTION 1: Corriger la fonction template_add_column


# CORRECTION 2: Corriger la fonction template_add_row
@csrf_exempt
@login_required
def template_add_row(request, document_id):
    """
    Ajouter une ligne au template
    """
    if request.method == 'POST':
        document = get_object_or_404(Document, id=document_id, submission__created_by=request.user)

        # CORRECTION: Utiliser Max au lieu de models.Max
        max_row = TemplateField.objects.filter(document=document).aggregate(
            max_row=Max('row_number')
        )['max_row'] or 0

        # Récupérer la structure de la première ligne pour reproduction
        first_row_fields = TemplateField.objects.filter(
            document=document,
            row_number=0
        ).order_by('column_number')

        # Créer les nouveaux champs pour la nouvelle ligne
        new_fields = []
        for i, template_field in enumerate(first_row_fields):
            new_field = TemplateField.objects.create(
                document=document,
                field_name=f'row_{max_row + 1}_col_{i}',
                field_label=template_field.field_label,
                field_type=template_field.field_type,
                row_number=max_row + 1,
                column_number=i
            )
            new_fields.append(new_field)

        return JsonResponse({
            'success': True,
            'message': 'Ligne ajoutée avec succès',
            'new_row_number': max_row + 1
        })

    return JsonResponse({'success': False, 'message': 'Méthode non autorisée'})

# Fonctions existantes conservées mais améliorées
import json
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from .models import Submission

@login_required
def dashboard(request):
    """Page d'accueil avec la liste des soumissions récentes"""
    recent_submissions = Submission.objects.filter(created_by=request.user).order_by('-created_at')[:10]

    PDF_EDITOR = {
        'MAX_FILE_SIZE': 52428800,  # 50MB en octets
        'ALLOWED_EXTENSIONS': json.dumps(['.pdf'])
    }

    context = {
        'recent_submissions': recent_submissions,
        'total_submissions': Submission.objects.filter(created_by=request.user).count(),
        'draft_submissions': Submission.objects.filter(created_by=request.user, status='draft').count(),
        'in_progress_submissions': Submission.objects.filter(created_by=request.user, status='in_progress').count(),
        'utils_available': UTILS_AVAILABLE,
        'extraction_capabilities': {
            'structured_pdf': UTILS_AVAILABLE,
            'image_extraction': UTILS_AVAILABLE,
            'table_detection': UTILS_AVAILABLE
        },
        'PDF_EDITOR': PDF_EDITOR,
    }
    return render(request, 'client/ctd_submission/dashboard.html', context)


@login_required
def submission_create(request):
    """Création d'une nouvelle soumission CTD"""
    if request.method == 'POST':
        form = SubmissionForm(request.POST)
        if form.is_valid():
            submission = form.save(commit=False)
            submission.created_by = request.user
            submission.save()
            messages.success(request, f'Soumission {submission.name} créée avec succès!')
            return redirect('ctd_submission:submission_detail', submission_id=submission.id)
    else:
        form = SubmissionForm()

    return render(request, 'client/ctd_submission/submission_create.html', {'form': form})



@login_required
def submission_detail(request, submission_id):
    """Détail d'une soumission avec sa structure CTD générée"""
    submission = get_object_or_404(Submission, id=submission_id, created_by=request.user)

    # Récupérer les modules CTD avec leurs sections et documents
    ctd_structure = []
    modules = CTDModule.objects.all().prefetch_related('sections__documents')

    for module in modules:
        sections = []
        for section in module.sections.all():
            documents = section.documents.filter(submission=submission)
            if documents.exists():
                sections.append({
                    'section': section,
                    'documents': documents
                })

        if sections:
            ctd_structure.append({
                'module': module,
                'sections': sections
            })

    context = {
        'submission': submission,
        'ctd_structure': ctd_structure,
        'upload_form': DocumentUploadForm(),
    }
    return render(request, 'client/ctd_submission/submission_detail.html', context)


@csrf_exempt
@login_required
def generate_ctd_structure(request):
    """
    Analyse intelligente pour générer automatiquement la structure CTD
    """
    if request.method == 'POST':
        submission_id = request.POST.get('submission_id')
        submission = get_object_or_404(Submission, id=submission_id, created_by=request.user)

        if not UTILS_AVAILABLE:
            return JsonResponse({
                'success': False,
                'message': 'Analyse CTD non disponible - vérifiez la configuration'
            })

        try:
            # Initialiser l'analyseur CTD
            analyzer = CTDAnalyzer()

            # Analyser tous les documents uploadés mais pas encore classifiés
            unclassified_documents = submission.documents.filter(section__isnull=True)

            results = []
            for document in unclassified_documents:
                try:
                    # Analyser le document
                    analysis_result = analyzer.analyze_document(document)

                    if analysis_result:
                        # Sauvegarder le résultat de l'analyse
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

                        # Assigner automatiquement le document à la section suggérée
                        document.section = analysis_result['section']
                        document.save()

                        results.append({
                            'document_name': document.name,
                            'module': analysis_result['module'].name,
                            'section': analysis_result['section'].name,
                            'confidence': analysis_result['confidence']
                        })

                except Exception as doc_error:
                    logger.warning(f"Erreur analyse document {document.name}: {doc_error}")
                    continue

            # Mettre à jour le statut de la soumission
            submission.status = 'in_progress'
            submission.save()

            return JsonResponse({
                'success': True,
                'message': f'{len(results)} documents analysés et classifiés automatiquement',
                'results': results
            })

        except Exception as e:
            logger.error(f"Erreur génération structure CTD: {e}")
            return JsonResponse({
                'success': False,
                'message': f'Erreur lors de l\'analyse: {str(e)}'
            })

    return JsonResponse({'success': False, 'message': 'Méthode non autorisée'})



# Remplacez la fonction document_upload dans views.py par cette version corrigée :

@csrf_exempt
@login_required
def document_upload(request):
    """
    Upload et traitement automatique des documents avec extraction PDF structurée
    """
    if request.method == 'POST':
        try:
            # Récupérer la soumission
            submission_id = request.POST.get('submission_id')
            if not submission_id:
                return JsonResponse({
                    'success': False,
                    'message': 'ID de soumission manquant'
                })

            submission = get_object_or_404(Submission, id=submission_id, created_by=request.user)

            # Vérifier qu'un fichier a été uploadé
            if 'file' not in request.FILES:
                return JsonResponse({
                    'success': False,
                    'message': 'Aucun fichier sélectionné'
                })

            file = request.FILES['file']
            document_name = request.POST.get('name', file.name)

            # Créer le document
            document = Document(
                submission=submission,
                name=document_name,
                file=file
            )

            # Déterminer le type de document
            file_extension = os.path.splitext(file.name)[1].lower()
            if file_extension == '.pdf':
                document.document_type = 'pdf'
            elif file_extension in ['.docx', '.doc']:
                document.document_type = 'docx'
            elif file_extension in ['.xlsx', '.xls']:
                document.document_type = 'xlsx'
            else:
                document.document_type = 'pdf'  # Par défaut

            # Sauvegarder le document
            document.save()

            # EXTRACTION AVEC NOUVEAU PROCESSEUR STRUCTURÉ
            analysis_message = ""
            extraction_details = {}

            try:
                if UTILS_AVAILABLE:
                    logger.info(f"🚀 Début traitement structuré: {document.name}")

                    # 1. Extraction du contenu avec processeur structuré
                    processor = DocumentProcessor()
                    extracted_content = processor.extract_content(document)

                    if extracted_content and extracted_content.get('extracted', False):
                        document.content_extracted = extracted_content
                        document.save()

                        # Préparer les détails d'extraction
                        structure = extracted_content.get('structure', {})
                        extraction_details = {
                            'method': extracted_content.get('extraction_method', 'unknown'),
                            'pages': len(extracted_content.get('pages', [])),
                            'elements': len(structure.get('elements', [])),
                            'tables': len(structure.get('tables', [])),
                            'images': len(structure.get('images', [])),
                            'text_blocks': len(structure.get('text_blocks', [])),
                            'text_length': len(extracted_content.get('text', '')),
                            'has_structure': bool(structure.get('elements'))
                        }

                        analysis_message += f" | ✅ Extraction structurée ({extraction_details['method']})"
                        analysis_message += f" | 📄 {extraction_details['pages']} page(s)"
                        analysis_message += f" | 🧩 {extraction_details['elements']} élément(s)"

                        if extraction_details['tables'] > 0:
                            analysis_message += f" | 📊 {extraction_details['tables']} tableau(x)"
                        if extraction_details['images'] > 0:
                            analysis_message += f" | 🖼️ {extraction_details['images']} image(s)"

                    else:
                        analysis_message += " | ⚠️ Extraction échouée ou partielle"
                        extraction_details = {
                            'method': 'failed',
                            'error': extracted_content.get('error', 'Unknown') if extracted_content else 'No content'
                        }

                    # 2. Analyse IA automatique (si extraction réussie)
                    if extracted_content and extracted_content.get('extracted', False):
                        try:
                            analyzer = CTDAnalyzer()
                            analysis_result = analyzer.analyze_document(document)

                            if analysis_result and analysis_result.get('confidence', 0) > 0.6:
                                # Assigner automatiquement la section
                                document.section = analysis_result['section']
                                document.save()

                                # Sauvegarder le résultat de l'analyse IA
                                AIAnalysisResult.objects.update_or_create(
                                    document=document,
                                    defaults={
                                        'suggested_module': analysis_result['module'],
                                        'suggested_section': analysis_result['section'],
                                        'confidence_score': analysis_result['confidence'],
                                        'analysis_details': analysis_result.get('details', {}),
                                        'keywords_found': analysis_result.get('keywords', [])
                                    }
                                )

                                analysis_message += f" | 🎯 Section: {analysis_result['module'].code}.{analysis_result['section'].code} ({analysis_result['confidence']*100:.1f}%)"

                                # 3. Génération automatique du template si confiance élevée
                                if analysis_result.get('confidence', 0) > 0.8:
                                    try:
                                        generate_document_template(document)
                                        analysis_message += " | 📝 Template généré"
                                    except Exception as template_error:
                                        logger.warning(f"Template non généré: {template_error}")

                            elif analysis_result:
                                confidence_pct = analysis_result.get('confidence', 0) * 100
                                analysis_message += f" | ⚠️ IA: confiance insuffisante ({confidence_pct:.1f}%)"
                            else:
                                analysis_message += " | ❌ Analyse IA échouée"
                        except Exception as ai_error:
                            logger.warning(f"Erreur analyse IA: {ai_error}")
                            analysis_message += f" | ⚠️ IA: {str(ai_error)}"

                else:
                    analysis_message += " | ⚠️ Processeur non disponible"

            except Exception as e:
                logger.error(f"❌ Erreur lors du traitement automatique: {e}")
                analysis_message += f" | ❌ Erreur: {str(e)}"

            # Réponse détaillée améliorée
            response_data = {
                'success': True,
                'message': f'Document {document.name} uploadé avec succès{analysis_message}',
                'document_id': document.id,
                'extraction_details': extraction_details,
                'actions': {
                    'view': f'/document/{document.id}/view/',
                    'template': f'/document/{document.id}/template/',
                    'advanced_editor': f'/document/{document.id}/advanced-editor/',
                    'download': f'/document/{document.id}/download/',
                },
                'analysis': {
                    'has_section': bool(document.section),
                    'section_name': f"{document.section.module.code}.{document.section.code} - {document.section.name}" if document.section else None,
                    'has_content': bool(document.content_extracted and document.content_extracted.get('extracted', False)),
                    'auto_template_generated': document.is_template_generated,
                    'extraction_method': extraction_details.get('method', 'unknown'),
                    'structure_detected': extraction_details.get('has_structure', False)
                },
                'capabilities': {
                    'can_edit_advanced': True,
                    'has_structure': extraction_details.get('has_structure', False),
                    'copilot_enabled': UTILS_AVAILABLE,
                    'supports_images': extraction_details.get('images', 0) > 0,
                    'supports_tables': extraction_details.get('tables', 0) > 0
                }
            }

            return JsonResponse(response_data)

        except Exception as e:
            logger.error(f"❌ Erreur critique lors de l'upload: {e}")
            return JsonResponse({
                'success': False,
                'message': f'Erreur lors de l\'upload: {str(e)}'
            })

    return JsonResponse({'success': False, 'message': 'Méthode non autorisée'})



# BONUS : Ajoutez aussi cette fonction pour forcer l'analyse sur des documents existants
@csrf_exempt
@login_required
def force_document_analysis(request, document_id):
    """
    Force l'analyse IA d'un document spécifique
    """
    if request.method == 'POST':
        try:
            document = get_object_or_404(Document, id=document_id, submission__created_by=request.user)

            # Extraire le contenu si nécessaire
            processor = DocumentProcessor()
            if not document.content_extracted or not document.content_extracted.get('extracted', False):
                extracted_content = processor.extract_content(document)
                if extracted_content:
                    document.content_extracted = extracted_content
                    document.save()

            # Effectuer l'analyse
            analyzer = CTDAnalyzer()
            analysis_result = analyzer.analyze_document(document)

            if analysis_result and analysis_result.get('confidence', 0) > 0.6:
                # Assigner la section
                document.section = analysis_result['section']
                document.save()

                # Sauvegarder l'analyse
                from .models import AIAnalysisResult
                AIAnalysisResult.objects.update_or_create(
                    document=document,
                    defaults={
                        'suggested_module': analysis_result['module'],
                        'suggested_section': analysis_result['section'],
                        'confidence_score': analysis_result['confidence'],
                        'analysis_details': analysis_result.get('details', {}),
                        'keywords_found': analysis_result.get('keywords', [])
                    }
                )

                return JsonResponse({
                    'success': True,
                    'message': f'Section assignée: {analysis_result["module"].code}.{analysis_result["section"].code}',
                    'analysis': {
                        'module': analysis_result['module'].name,
                        'section': analysis_result['section'].name,
                        'confidence': analysis_result['confidence']
                    }
                })
            else:
                return JsonResponse({
                    'success': False,
                    'message': 'Confiance insuffisante pour assigner automatiquement une section'
                })

        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Erreur lors de l\'analyse: {str(e)}'
            })

    return JsonResponse({'success': False, 'message': 'Méthode non autorisée'})


@login_required
def document_view(request, document_id):
    """
    Vue 'Voir' - Affichage du document avec extraction PDF structurée et Word paginé
    """
    document = get_object_or_404(Document, id=document_id, submission__created_by=request.user)

    if not document.content_extracted and UTILS_AVAILABLE:
        try:
            logger.info(f"🔄 Extraction à la demande pour: {document.name}")
            processor = DocumentProcessor()
            extracted_content = processor.extract_content(document)

            if extracted_content:
                document.content_extracted = extracted_content
                document.save()

                if extracted_content.get('extracted', False):
                    method = extracted_content.get('extraction_method', 'méthode inconnue')
                    messages.success(request, f'Contenu extrait avec succès via {method}')

                    stats = []
                    # Adaptation des stats selon structure
                    structure = extracted_content.get('structure', {})
                    if 'images' in extracted_content:
                        stats.append(f"{len(extracted_content['images'])} image(s)")
                    if 'tables' in extracted_content:
                        stats.append(f"{len(extracted_content['tables'])} tableau(x)")
                    if stats:
                        messages.info(request, f'Éléments détectés: {", ".join(stats)}')
                else:
                    messages.warning(request,
                                     'Extraction partielle du contenu - certaines fonctionnalités peuvent être limitées')

        except Exception as e:
            logger.error(f"❌ Erreur extraction à la demande: {e}")
            messages.error(request, f'Erreur lors de l\'extraction du contenu: {str(e)}')

    context = {
        'document': document,
        'content': document.content_extracted,
        'is_raw_view': True,
        'extraction_info': {
            'has_content': bool(document.content_extracted),
            'is_extracted': document.content_extracted.get('extracted', False) if document.content_extracted else False,
            'method': document.content_extracted.get('extraction_method',
                                                     'unknown') if document.content_extracted else None,
            'has_structure': bool(
                document.content_extracted and
                (
                    document.content_extracted.get('structure', {}).get('tables') or
                    document.content_extracted.get('structure', {}).get('images') or
                    document.content_extracted.get('structure', {}).get('elements') or
                    document.content_extracted.get('pages')  # Ajout pour Word paginé
                )
            ) if document.content_extracted else False
        }
    }

    if document.document_type == 'pdf':
        return render(request, 'ctd_submission/document_pdf_view.html', context)
    elif document.document_type in ['docx', 'xlsx']:
        # Ici, dans ton template document_office_view.html,
        # tu pourras parcourir content.pages pour afficher page par page
        return render(request, 'ctd_submission/document_office_view.html', context)
    else:
        return render(request, 'ctd_submission/document_generic_view.html', context)

@csrf_exempt
@login_required
def api_test_pdf_extraction(request, document_id):
    """
    API pour tester et diagnostiquer l'extraction PDF avec le nouveau processeur
    """
    if request.method == 'POST':
        try:
            document = get_object_or_404(Document, id=document_id, submission__created_by=request.user)

            if document.document_type != 'pdf':
                return JsonResponse({
                    'success': False,
                    'message': 'Ce document n\'est pas un PDF'
                })

            if not UTILS_AVAILABLE:
                return JsonResponse({
                    'success': False,
                    'message': 'Processeur PDF non disponible'
                })

            # Diagnostic du processeur structuré
            processor = DocumentProcessor()
            pdf_processor = processor.pdf_processor

            diagnostic = {
                'available_processors': pdf_processor.available_processors,
                'libraries_loaded': list(pdf_processor.pdf_libraries.keys()),
                'file_exists': os.path.exists(document.file.path) if document.file else False,
                'file_size': os.path.getsize(document.file.path) if document.file and os.path.exists(
                    document.file.path) else 0,
                'document_type': document.document_type,
                'processor_type': type(pdf_processor).__name__
            }

            # Test d'extraction structurée
            if diagnostic['file_exists']:
                try:
                    logger.info(f"🧪 Test extraction structurée pour: {document.name}")
                    start_time = timezone.now()

                    result = pdf_processor.extract_pdf_content_structured(document.file.path)

                    end_time = timezone.now()
                    extraction_time = (end_time - start_time).total_seconds()

                    if result:
                        structure = result.get('structure', {})
                        extraction_result = {
                            'success': result.get('extracted', False),
                            'method': result.get('extraction_method', 'unknown'),
                            'extraction_time': f"{extraction_time:.2f}s",
                            'pages_found': len(result.get('pages', [])),
                            'elements_found': len(structure.get('elements', [])),
                            'tables_found': len(structure.get('tables', [])),
                            'images_found': len(structure.get('images', [])),
                            'text_blocks_found': len(structure.get('text_blocks', [])),
                            'text_length': len(result.get('text', '')),
                            'has_html': bool(result.get('html')),
                            'has_structure': bool(structure.get('elements')),
                            'errors': result.get('errors', [])
                        }

                        # Test de qualité de l'extraction
                        quality_score = 0
                        if extraction_result['success']:
                            quality_score += 30
                        if extraction_result['pages_found'] > 0:
                            quality_score += 20
                        if extraction_result['elements_found'] > 0:
                            quality_score += 25
                        if extraction_result['tables_found'] > 0:
                            quality_score += 15
                        if extraction_result['images_found'] > 0:
                            quality_score += 10

                        extraction_result['quality_score'] = quality_score
                        extraction_result['quality_level'] = (
                            'excellent' if quality_score >= 80 else
                            'good' if quality_score >= 60 else
                            'fair' if quality_score >= 40 else
                            'poor'
                        )

                    else:
                        extraction_result = {
                            'success': False,
                            'error': 'Aucun résultat retourné',
                            'method': 'none'
                        }

                except Exception as extraction_error:
                    extraction_result = {
                        'success': False,
                        'error': str(extraction_error),
                        'method': 'error'
                    }
            else:
                extraction_result = {
                    'success': False,
                    'error': 'Fichier non accessible'
                }

            # Recommandations d'amélioration
            recommendations = []
            if not diagnostic['available_processors']:
                recommendations.append({
                    'type': 'critical',
                    'message': 'Installer au moins une bibliothèque PDF',
                    'commands': [
                        'pip install PyMuPDF',
                        'pip install pdfplumber',
                        'pip install pdfminer.six'
                    ]
                })
            elif 'pymupdf_structured' not in diagnostic['available_processors']:
                recommendations.append({
                    'type': 'improvement',
                    'message': 'Installer PyMuPDF pour une extraction optimale',
                    'commands': ['pip install PyMuPDF']
                })

            if extraction_result.get('quality_score', 0) < 60:
                recommendations.append({
                    'type': 'quality',
                    'message': 'Qualité d\'extraction faible - vérifier le format du PDF',
                    'suggestions': [
                        'Le PDF pourrait être scanné (images)',
                        'Le PDF pourrait être protégé',
                        'La structure du PDF pourrait être complexe'
                    ]
                })

            return JsonResponse({
                'success': True,
                'diagnostic': diagnostic,
                'extraction_test': extraction_result,
                'recommendations': recommendations,
                'installation_guide': {
                    'pymupdf': 'pip install PyMuPDF',
                    'pdfplumber': 'pip install pdfplumber',
                    'pdfminer': 'pip install pdfminer.six',
                    'pypdf2': 'pip install PyPDF2'
                }
            })

        except Exception as e:
            logger.error(f"❌ Erreur test extraction: {e}")
            return JsonResponse({
                'success': False,
                'message': f'Erreur lors du test: {str(e)}'
            })

    return JsonResponse({'success': False, 'message': 'Méthode non autorisée'})


@login_required
def document_template(request, document_id):
    """Vue 'Template' - Formulaire dynamique modifiable extrait du document"""
    document = get_object_or_404(Document, id=document_id, submission__created_by=request.user)

    # Générer le template si pas encore fait
    if not document.is_template_generated:
        try:
            generate_document_template(document)
        except Exception as e:
            messages.error(request, f'Erreur lors de la génération du template: {str(e)}')

    template_fields = TemplateField.objects.filter(document=document).order_by('row_number', 'column_number')

    if request.method == 'POST':
        # Sauvegarder les modifications du template
        for field in template_fields:
            field_value = request.POST.get(f'field_{field.id}', '')
            field.field_value = field_value
            field.save()

        # Mettre à jour le template_data du document
        template_data = {}
        for field in template_fields:
            template_data[field.field_name] = field.field_value

        document.template_data = template_data
        document.save()

        # Régénérer le document original avec les nouvelles données si possible
        if UTILS_AVAILABLE:
            try:
                processor = DocumentProcessor()
                processor.update_document_from_template(document)
            except Exception as e:
                logger.warning(f"Erreur mise à jour document: {e}")

        messages.success(request, 'Template mis à jour avec succès!')
        return redirect('ctd_submission:document_template', document_id=document.id)

    # Organiser les champs par lignes pour l'affichage
    rows = {}
    for field in template_fields:
        if field.row_number not in rows:
            rows[field.row_number] = []
        rows[field.row_number].append(field)

    context = {
        'document': document,
        'template_fields': template_fields,
        'rows': rows,
        'is_template_view': True
    }

    return render(request, 'ctd_submission/document_template.html', context)


@csrf_exempt
@login_required
def template_add_column(request, document_id):
    """Ajouter une colonne au template"""
    if request.method == 'POST':
        document = get_object_or_404(Document, id=document_id, submission__created_by=request.user)

        row_number = int(request.POST.get('row_number', 0))
        column_name = request.POST.get('column_name', 'Nouvelle colonne')

        max_column = TemplateField.objects.filter(
            document=document,
            row_number=row_number
        ).aggregate(max_col=Max('column_number'))['max_col'] or 0

        new_field = TemplateField.objects.create(
            document=document,
            field_name=f'col_{max_column + 1}',
            field_label=column_name,
            field_type='text',
            row_number=row_number,
            column_number=max_column + 1
        )

        return JsonResponse({
            'success': True,
            'message': 'Colonne ajoutée avec succès',
            'field_id': new_field.id
        })

    return JsonResponse({'success': False, 'message': 'Méthode non autorisée'})


@csrf_exempt
@login_required
def template_add_row(request, document_id):
    """Ajouter une ligne au template"""
    if request.method == 'POST':
        document = get_object_or_404(Document, id=document_id, submission__created_by=request.user)

        max_row = TemplateField.objects.filter(document=document).aggregate(
            max_row=Max('row_number')
        )['max_row'] or 0

        first_row_fields = TemplateField.objects.filter(
            document=document,
            row_number=0
        ).order_by('column_number')

        new_fields = []
        for i, template_field in enumerate(first_row_fields):
            new_field = TemplateField.objects.create(
                document=document,
                field_name=f'row_{max_row + 1}_col_{i}',
                field_label=template_field.field_label,
                field_type=template_field.field_type,
                row_number=max_row + 1,
                column_number=i
            )
            new_fields.append(new_field)

        return JsonResponse({
            'success': True,
            'message': 'Ligne ajoutée avec succès',
            'new_row_number': max_row + 1
        })

    return JsonResponse({'success': False, 'message': 'Méthode non autorisée'})

@csrf_exempt
@login_required
def template_delete_field(request, field_id):
    """
    Supprimer un champ du template
    """
    # Chemin d'intégration : AJAX DELETE -> ctd_submission/views.py
    if request.method == 'DELETE':
        field = get_object_or_404(TemplateField, id=field_id, document__submission__created_by=request.user)
        field.delete()

        return JsonResponse({
            'success': True,
            'message': 'Champ supprimé avec succès'
        })

    return JsonResponse({'success': False, 'message': 'Méthode non autorisée'})


def generate_document_template(document):
    """
    Génère automatiquement un template de formulaire à partir du contenu extrait - VERSION AMÉLIORÉE
    """
    try:
        # Supprimer les anciens champs
        TemplateField.objects.filter(document=document).delete()

        # Déterminer le type de template selon le nom et contenu du document
        template_structure = []

        document_name_lower = document.name.lower()
        content = document.content_extracted or {}
        content_text = content.get('text', '').lower()

        # Templates spécialisés selon le type de document
        if any(keyword in document_name_lower for keyword in ['ema', 'cover letter', 'lettre']):
            template_structure = _get_ema_cover_letter_template()
        elif any(keyword in document_name_lower for keyword in ['application form', 'formulaire']):
            template_structure = _get_application_form_template()
        elif any(keyword in content_text for keyword in ['quality', 'qos', 'qualité']):
            template_structure = _get_quality_summary_template()
        elif any(keyword in content_text for keyword in ['clinical', 'clinique', 'trial']):
            template_structure = _get_clinical_template()
        else:
            # Template générique basé sur le contenu détecté
            template_structure = _get_generic_template(content)

        # Créer les champs de template
        for i, field_config in enumerate(template_structure):
            TemplateField.objects.create(
                document=document,
                field_name=field_config['name'],
                field_label=field_config['label'],
                field_type=field_config.get('type', 'text'),
                field_value=field_config.get('value', ''),
                field_options=field_config.get('options', []),
                is_required=field_config.get('required', False),
                row_number=i,
                column_number=field_config.get('column', 0)
            )

        document.is_template_generated = True
        document.save()

        logger.info(f"Template généré pour {document.name}: {len(template_structure)} champs")

    except Exception as e:
        logger.error(f"Erreur génération template: {e}")
        raise



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


@login_required
def submission_export(request, submission_id):
    """
    Export d'une soumission complète
    """
    submission = get_object_or_404(Submission, id=submission_id, created_by=request.user)

    # Créer un fichier ZIP avec tous les documents
    response = HttpResponse(content_type='application/zip')
    response['Content-Disposition'] = f'attachment; filename="{submission.name}_export.zip"'

    with zipfile.ZipFile(response, 'w') as zip_file:
        # Ajouter les métadonnées de la soumission
        submission_info = {
            'name': submission.name,
            'region': submission.region,
            'submission_type': submission.submission_type,
            'status': submission.status,
            'created_at': submission.created_at.isoformat(),
            'documents_count': submission.documents.count()
        }

        zip_file.writestr(
            'submission_info.json',
            json.dumps(submission_info, indent=2, ensure_ascii=False)
        )

        # Ajouter tous les documents
        for document in submission.documents.all():
            if document.file:
                try:
                    file_content = document.file.read()
                    zip_file.writestr(f'documents/{document.name}', file_content)
                except:
                    pass

        # Ajouter la structure CTD
        ctd_structure = []
        for module in CTDModule.objects.all():
            module_data = {
                'code': module.code,
                'name': module.name,
                'sections': []
            }

            for section in module.sections.all():
                if section.documents.filter(submission=submission).exists():
                    section_data = {
                        'code': section.code,
                        'name': section.name,
                        'documents': [doc.name for doc in section.documents.filter(submission=submission)]
                    }
                    module_data['sections'].append(section_data)

            if module_data['sections']:
                ctd_structure.append(module_data)

        zip_file.writestr(
            'ctd_structure.json',
            json.dumps(ctd_structure, indent=2, ensure_ascii=False)
        )

    return response


@csrf_exempt
@login_required
def api_analyze_document(request, document_id):
    """
    API pour analyser un document avec l'IA
    """
    if request.method == 'POST':
        try:
            document = get_object_or_404(Document, id=document_id, submission__created_by=request.user)

            analyzer = CTDAnalyzer()
            analysis_result = analyzer.analyze_document(document)

            if analysis_result:
                # Sauvegarder le résultat
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

                return JsonResponse({
                    'success': True,
                    'analysis': {
                        'module': analysis_result['module'].name,
                        'section': analysis_result['section'].name,
                        'confidence': analysis_result['confidence'],
                        'keywords': analysis_result['keywords']
                    }
                })
            else:
                return JsonResponse({
                    'success': False,
                    'message': 'Impossible d\'analyser le document'
                })

        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Erreur lors de l\'analyse: {str(e)}'
            })

    return JsonResponse({'success': False, 'message': 'Méthode non autorisée'})




@login_required
def export_submission_report(request, submission_id):
    """
    Export du rapport de soumission en CSV
    """
    submission = get_object_or_404(Submission, id=submission_id, created_by=request.user)

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{submission.name}_report.csv"'

    writer = csv.writer(response)
    writer.writerow([
        'Document', 'Type', 'Section CTD', 'Template Généré',
        'Analyse IA', 'Confiance IA', 'Date Création'
    ])

    for document in submission.documents.all():
        ai_analysis = getattr(document, 'ai_analysis', None)
        writer.writerow([
            document.name,
            document.get_document_type_display(),
            f"{document.section.code} {document.section.name}" if document.section else 'Non assigné',
            'Oui' if document.is_template_generated else 'Non',
            'Oui' if ai_analysis else 'Non',
            f"{ai_analysis.confidence_score:.2f}" if ai_analysis else '',
            document.created_at.strftime('%d/%m/%Y %H:%M')
        ])

    return response


@login_required
@user_passes_test(lambda u: u.is_staff)
def admin_modules(request):
    """
    Administration des modules CTD
    """
    modules = CTDModule.objects.all().prefetch_related('sections')

    context = {'modules': modules}
    return render(request, 'ctd_submission/admin_modules.html', context)


@login_required
@user_passes_test(lambda u: u.is_staff)
def admin_sections(request, module_id):
    """
    Administration des sections d'un module CTD
    """
    module = get_object_or_404(CTDModule, id=module_id)
    sections = module.sections.all().order_by('order', 'code')

    context = {
        'module': module,
        'sections': sections
    }
    return render(request, 'ctd_submission/admin_sections.html', context)


@login_required
@user_passes_test(lambda u: u.is_staff)
def admin_section_create(request):
    """
    Création d'une nouvelle section CTD
    """
    if request.method == 'POST':
        module_id = request.POST.get('module')
        module = get_object_or_404(CTDModule, id=module_id)

        section = CTDSection.objects.create(
            module=module,
            code=request.POST.get('code'),
            name=request.POST.get('name'),
            description=request.POST.get('description', ''),
            order=int(request.POST.get('order', 0))
        )

        messages.success(request, f'Section {section.code} créée avec succès!')
        return redirect('ctd_submission:admin_sections', module_id=module.id)

    modules = CTDModule.objects.all()
    context = {'modules': modules}
    return render(request, 'ctd_submission/admin_section_create.html', context)


@login_required
@user_passes_test(lambda u: u.is_staff)
def admin_section_edit(request, section_id):
    """
    Modification d'une section CTD
    """
    section = get_object_or_404(CTDSection, id=section_id)

    if request.method == 'POST':
        section.code = request.POST.get('code', section.code)
        section.name = request.POST.get('name', section.name)
        section.description = request.POST.get('description', section.description)
        section.order = int(request.POST.get('order', section.order))
        section.save()

        messages.success(request, f'Section {section.code} mise à jour!')
        return redirect('ctd_submission:admin_sections', module_id=section.module.id)

    context = {'section': section}
    return render(request, 'ctd_submission/admin_section_edit.html', context)


@login_required
def help_templates(request):
    """
    Aide spécifique aux templates
    """
    return render(request, 'ctd_submission/help_templates.html')


# =============================================================================
# VUES D'IMPORT/EXPORT
# =============================================================================

@login_required
def import_submission(request):
    """
    Import d'une soumission depuis un fichier
    """
    if request.method == 'POST':
        if 'file' not in request.FILES:
            messages.error(request, 'Aucun fichier sélectionné')
            return redirect('ctd_submission:import_submission')

        uploaded_file = request.FILES['file']

        try:
            # Lire le fichier JSON
            content = uploaded_file.read().decode('utf-8')
            data = json.loads(content)

            # Créer la soumission
            submission = Submission.objects.create(
                name=data['name'] + '_imported',
                region=data['region'],
                submission_type=data['submission_type'],
                status='draft',
                created_by=request.user
            )

            messages.success(request, f'Soumission "{submission.name}" importée avec succès!')
            return redirect('ctd_submission:submission_detail', submission_id=submission.id)

        except Exception as e:
            messages.error(request, f'Erreur lors de l\'import: {str(e)}')

    return render(request, 'ctd_submission/import_submission.html')


@login_required
def export_template(request, document_id):
    """
    Export d'un template en JSON
    """
    document = get_object_or_404(Document, id=document_id, submission__created_by=request.user)

    template_data = {
        'document_name': document.name,
        'template_fields': []
    }

    for field in document.template_fields.all():
        template_data['template_fields'].append({
            'name': field.field_name,
            'label': field.field_label,
            'type': field.field_type,
            'value': field.field_value,
            'options': field.field_options,
            'required': field.is_required,
            'row': field.row_number,
            'column': field.column_number
        })

    response = HttpResponse(
        json.dumps(template_data, indent=2, ensure_ascii=False),
        content_type='application/json'
    )
    response['Content-Disposition'] = f'attachment; filename="{document.name}_template.json"'

    return response


@login_required
def import_template(request, document_id):
    """
    Import d'un template depuis un fichier JSON
    """
    document = get_object_or_404(Document, id=document_id, submission__created_by=request.user)

    if request.method == 'POST':
        if 'file' not in request.FILES:
            messages.error(request, 'Aucun fichier sélectionné')
            return redirect('ctd_submission:document_template', document_id=document.id)

        uploaded_file = request.FILES['file']

        try:
            content = uploaded_file.read().decode('utf-8')
            data = json.loads(content)

            # Supprimer les anciens champs
            document.template_fields.all().delete()

            # Créer les nouveaux champs
            for field_data in data['template_fields']:
                TemplateField.objects.create(
                    document=document,
                    field_name=field_data['name'],
                    field_label=field_data['label'],
                    field_type=field_data['type'],
                    field_value=field_data.get('value', ''),
                    field_options=field_data.get('options', []),
                    is_required=field_data.get('required', False),
                    row_number=field_data.get('row', 0),
                    column_number=field_data.get('column', 0)
                )

            document.is_template_generated = True
            document.save()

            messages.success(request, 'Template importé avec succès!')

        except Exception as e:
            messages.error(request, f'Erreur lors de l\'import: {str(e)}')

    return redirect('ctd_submission:document_template', document_id=document.id)

def error_404(request, exception):
    """
    Page d'erreur 404 personnalisée
    """
    return render(request, 'ctd_submission/errors/404.html', status=404)

def error_500(request):
    """
    Page d'erreur 500 personnalisée
    """
    return render(request, 'ctd_submission/errors/500.html', status=500)

def error_403(request, exception):
    """
    Page d'erreur 403 personnalisée
    """
    return render(request, 'ctd_submission/errors/403.html', status=403)


@csrf_exempt
@login_required
def apply_template_to_editor(request, document_id):
    """
    Applique un template généré automatiquement à l'éditeur - VERSION CORRIGÉE
    """
    if request.method == 'POST':
        try:
            document = get_object_or_404(Document, id=document_id, submission__created_by=request.user)

            # Générer ou récupérer le template
            if not document.is_template_generated:
                generate_document_template(document)

            # Récupérer les champs du template
            template_fields = TemplateField.objects.filter(document=document)

            # Préparer les données de préremplissage
            prefill_data = {}
            for field in template_fields:
                prefill_data[field.field_name] = {
                    'label': field.field_label,
                    'value': field.field_value,
                    'type': field.field_type,
                    'required': field.is_required,
                    'position': {
                        'row': field.row_number,
                        'column': field.column_number
                    }
                }

            # Analyser le contenu pour suggérer des positions d'insertion
            insertion_suggestions = []
            try:
                copilot = IntelligentCopilot()
                insertion_suggestions = copilot.suggest_template_positions(document, prefill_data)
            except:
                # Suggestions basiques si le copilot n'est pas disponible
                insertion_suggestions = [
                    {
                        'field_name': 'general',
                        'field_label': 'Champs généraux',
                        'suggested_position': {'line': 0, 'confidence': 0.5},
                        'reasoning': 'Position par défaut en début de document'
                    }
                ]

            return JsonResponse({
                'success': True,
                'template_data': prefill_data,
                'insertion_suggestions': insertion_suggestions,
                'fields_count': len(prefill_data),
                'message': 'Template prêt à être appliqué'
            })

        except Exception as e:
            logger.error(f"Erreur application template: {e}")
            return JsonResponse({
                'success': False,
                'message': f'Erreur lors de l\'application du template: {str(e)}'
            })

    return JsonResponse({'success': False, 'message': 'Méthode non autorisée'})


# Ajout d'une fonction pour servir le token CSRF
def get_token(request):
    """Récupère le token CSRF pour les requêtes AJAX"""
    from django.middleware.csrf import get_token
    return get_token(request)


@csrf_exempt
@login_required
def apply_template_to_editor(request, document_id):
    """
    Applique un template généré automatiquement à l'éditeur
    """
    if request.method == 'POST':
        try:
            document = get_object_or_404(Document, id=document_id, submission__created_by=request.user)

            # Générer ou récupérer le template
            if not document.is_template_generated:
                generate_document_template(document)

            # Récupérer les champs du template
            template_fields = TemplateField.objects.filter(document=document)

            # Préparer les données de préremplissage
            prefill_data = {}
            for field in template_fields:
                prefill_data[field.field_name] = {
                    'label': field.field_label,
                    'value': field.field_value,
                    'type': field.field_type,
                    'position': {
                        'row': field.row_number,
                        'column': field.column_number
                    }
                }

            # Analyser le contenu pour suggérer des positions d'insertion
            copilot = IntelligentCopilot()
            insertion_suggestions = copilot.suggest_template_positions(document, prefill_data)

            return JsonResponse({
                'success': True,
                'template_data': prefill_data,
                'insertion_suggestions': insertion_suggestions,
                'message': 'Template appliqué avec succès'
            })

        except Exception as e:
            logger.error(f"Erreur application template: {e}")
            return JsonResponse({
                'success': False,
                'message': f'Erreur lors de l\'application du template: {str(e)}'
            })

    return JsonResponse({'success': False, 'message': 'Méthode non autorisée'})


@csrf_exempt
@login_required
def document_export_modified(request, document_id):
    """
    Exporte le document modifié dans son format original
    """
    document = get_object_or_404(Document, id=document_id, submission__created_by=request.user)

    try:
        exporter = DocumentExporter()
        exported_file = exporter.export_modified_document(document)

        if exported_file:
            response = HttpResponse(
                exported_file.read(),
                content_type='application/octet-stream'
            )
            response['Content-Disposition'] = f'attachment; filename="{document.name}_modifie.{document.document_type}"'
            return response
        else:
            messages.error(request, 'Erreur lors de l\'export du document modifié')
            return redirect('ctd_submission:document_advanced_editor', document_id=document.id)

    except Exception as e:
        logger.error(f"Erreur export document: {e}")
        messages.error(request, f'Erreur lors de l\'export: {str(e)}')
        return redirect('ctd_submission:document_advanced_editor', document_id=document.id)


# Ajout à ctd_submission/views.py - Fonctionnalités additionnelles

@csrf_exempt
@login_required
def validate_document_content(request, document_id):
    """
    Valide le contenu du document modifié
    """
    if request.method == 'POST':
        try:
            document = get_object_or_404(Document, id=document_id, submission__created_by=request.user)

            # Initialiser le validateur intelligent
            validator = DocumentValidator()
            validation_results = validator.validate_document(document)

            return JsonResponse({
                'success': True,
                'validation_results': validation_results,
                'is_valid': validation_results.get('is_valid', False),
                'errors': validation_results.get('errors', []),
                'warnings': validation_results.get('warnings', []),
                'suggestions': validation_results.get('suggestions', [])
            })

        except Exception as e:
            logger.error(f"Erreur validation document: {e}")
            return JsonResponse({
                'success': False,
                'message': f'Erreur lors de la validation: {str(e)}'
            })

    return JsonResponse({'success': False, 'message': 'Méthode non autorisée'})


@login_required
def document_version_history(request, document_id):
    """
    Affiche l'historique des versions d'un document
    """
    document = get_object_or_404(Document, id=document_id, submission__created_by=request.user)

    # Récupérer l'historique des versions
    versions = DocumentVersion.objects.filter(document=document).order_by('-created_at')

    context = {
        'document': document,
        'versions': versions
    }

    return render(request, 'ctd_submission/document_version_history.html', context)


@csrf_exempt
@login_required
def restore_document_version(request, document_id, version_id):
    """
    Restaure une version précédente du document
    """
    if request.method == 'POST':
        try:
            document = get_object_or_404(Document, id=document_id, submission__created_by=request.user)
            version = get_object_or_404(DocumentVersion, id=version_id, document=document)

            # Créer une nouvelle version avec le contenu actuel avant de restaurer
            DocumentVersion.objects.create(
                document=document,
                content_data=document.content_extracted,
                template_data=document.template_data,
                version_number=DocumentVersion.objects.filter(document=document).count() + 1,
                created_by=request.user,
                description=f"Sauvegarde avant restauration de la version {version.version_number}"
            )

            # Restaurer le contenu de la version sélectionnée
            document.content_extracted = version.content_data
            document.template_data = version.template_data
            document.save()

            return JsonResponse({
                'success': True,
                'message': f'Version {version.version_number} restaurée avec succès'
            })

        except Exception as e:
            logger.error(f"Erreur restauration version: {e}")
            return JsonResponse({
                'success': False,
                'message': f'Erreur lors de la restauration: {str(e)}'
            })

    return JsonResponse({'success': False, 'message': 'Méthode non autorisée'})


@csrf_exempt
@login_required
def document_upload_enhanced(request):
    """
    Version améliorée de l'upload avec analyse IA automatique
    """
    if request.method == 'POST':
        try:
            # Récupérer la soumission
            submission_id = request.POST.get('submission_id')
            if not submission_id:
                return JsonResponse({
                    'success': False,
                    'message': 'ID de soumission manquant'
                })

            submission = get_object_or_404(Submission, id=submission_id, created_by=request.user)

            # Vérifier qu'un fichier a été uploadé
            if 'file' not in request.FILES:
                return JsonResponse({
                    'success': False,
                    'message': 'Aucun fichier sélectionné'
                })

            file = request.FILES['file']
            document_name = request.POST.get('name', file.name)

            # Créer le document
            document = Document(
                submission=submission,
                name=document_name,
                file=file
            )

            # Déterminer le type de document
            file_extension = os.path.splitext(file.name)[1].lower()
            if file_extension == '.pdf':
                document.document_type = 'pdf'
            elif file_extension in ['.docx', '.doc']:
                document.document_type = 'docx'
            elif file_extension in ['.xlsx', '.xls']:
                document.document_type = 'xlsx'
            else:
                document.document_type = 'pdf'  # Par défaut

            # Sauvegarder le document
            document.save()

            # Analyse IA automatique améliorée
            analysis_message = ""
            auto_template_generated = False

            try:
                # 1. Extraction du contenu
                processor = DocumentProcessor()
                extracted_content = processor.extract_content(document)

                if extracted_content and extracted_content.get('extracted', False):
                    document.content_extracted = extracted_content
                    document.save()
                    analysis_message += " | ✅ Contenu extrait"

                # 2. Analyse IA automatique
                analyzer = CTDAnalyzer()
                analysis_result = analyzer.analyze_document(document)

                if analysis_result and analysis_result.get('confidence', 0) > 0.6:
                    # Assigner automatiquement la section
                    document.section = analysis_result['section']
                    document.save()

                    # Sauvegarder le résultat de l'analyse IA
                    AIAnalysisResult.objects.update_or_create(
                        document=document,
                        defaults={
                            'suggested_module': analysis_result['module'],
                            'suggested_section': analysis_result['section'],
                            'confidence_score': analysis_result['confidence'],
                            'analysis_details': analysis_result.get('details', {}),
                            'keywords_found': analysis_result.get('keywords', []),
                            'analysis_method': analysis_result.get('details', {}).get('analysis_method', 'advanced')
                        }
                    )

                    analysis_message += f" | ✅ Section assignée: {analysis_result['module'].code}.{analysis_result['section'].code} (Confiance: {analysis_result['confidence'] * 100:.1f}%)"

                    # 3. Génération automatique du template si confiance élevée
                    if analysis_result.get('confidence', 0) > 0.8:
                        try:
                            generate_document_template(document)
                            auto_template_generated = True
                            analysis_message += " | 📝 Template généré"
                        except Exception as template_error:
                            logger.warning(f"Impossible de générer le template: {template_error}")

                elif analysis_result:
                    confidence_pct = analysis_result.get('confidence', 0) * 100
                    analysis_message += f" | ⚠️ Confiance insuffisante ({confidence_pct:.1f}%)"
                else:
                    analysis_message += " | ❌ Analyse échouée"

            except Exception as e:
                logger.error(f"Erreur lors de l'analyse automatique: {e}")
                analysis_message += f" | ⚠️ Erreur: {str(e)}"

            # Réponse améliorée
            response_data = {
                'success': True,
                'message': f'Document {document.name} uploadé avec succès{analysis_message}',
                'document_id': document.id,
                'actions': {
                    'view': f'/document/{document.id}/view/',
                    'template': f'/document/{document.id}/template/',
                    'advanced_editor': f'/document/{document.id}/advanced-editor/',
                    'download': f'/document/{document.id}/download/',
                },
                'analysis': {
                    'has_section': bool(document.section),
                    'section_name': f"{document.section.module.code}.{document.section.code} - {document.section.name}" if document.section else None,
                    'confidence': analysis_result.get('confidence', 0) if 'analysis_result' in locals() and analysis_result else 0,
                    'auto_template_generated': auto_template_generated,
                },
                'features': {
                    'can_edit_advanced': True,
                    'has_template': auto_template_generated or document.is_template_generated,
                    'copilot_enabled': True
                }
            }

            return JsonResponse(response_data)

        except Exception as e:
            logger.error(f"Erreur lors de l'upload: {e}")
            return JsonResponse({
                'success': False,
                'message': f'Erreur lors de l\'upload: {str(e)}'
            })

    return JsonResponse({'success': False, 'message': 'Méthode non autorisée'})

# ===== FONCTIONS D'AIDE POUR document_upload_enhanced =====

def save_document_version(document, changes, description=""):
    """
    Sauvegarde automatique d'une version du document
    (Cette fonction était mentionnée mais pas définie dans le code original)
    """
    try:
        # Calculer le numéro de version
        last_version = DocumentVersion.objects.filter(document=document).order_by('-version_number').first()
        version_number = (last_version.version_number + 1) if last_version else 1

        # Créer la version
        version = DocumentVersion.objects.create(
            document=document,
            content_data=document.content_extracted,
            template_data=document.template_data,
            version_number=version_number,
            created_by=document.submission.created_by,
            description=description or f"Version automatique {version_number}",
            changes_summary=changes
        )

        logger.info(f"Version {version_number} sauvegardée pour le document {document.id}")
        return version

    except Exception as e:
        logger.error(f"Erreur lors de la sauvegarde de version: {e}")
        return None


class DocumentValidator:
    """
    Validateur intelligent pour les documents modifiés
    (Cette classe était référencée mais pas complètement définie)
    """

    def __init__(self):
        self.validation_rules = {
            'required_fields': [
                'applicant_name', 'customer_account', 'procedure_type'
            ],
            'date_formats': [
                r'\d{1,2}[/.-]\d{1,2}[/.-]\d{4}',
                r'\d{4}[/.-]\d{1,2}[/.-]\d{1,2}'
            ],
            'identifier_patterns': {
                'ema_numbers': r'EMEA/H/C/\d+',
                'account_numbers': r'\d{6,}',
                'references': r'[A-Z]{2,}-[A-Z0-9]+-\d+'
            }
        }

    def validate_document(self, document):
        """
        Valide le contenu du document selon les règles métier
        """
        results = {
            'is_valid': True,
            'errors': [],
            'warnings': [],
            'suggestions': []
        }

        try:
            content = self._get_document_content(document)
            template_data = document.template_data or {}

            # Validation des champs obligatoires
            self._validate_required_fields(template_data, results)

            # Validation des formats
            self._validate_formats(content, results)

            # Validation de cohérence
            self._validate_consistency(content, template_data, results)

            # Validation spécifique au type de soumission
            self._validate_submission_type(document, results)

            # Déterminer si le document est globalement valide
            results['is_valid'] = len(results['errors']) == 0

        except Exception as e:
            logger.error(f"Erreur lors de la validation: {e}")
            results['errors'].append(f"Erreur de validation: {str(e)}")
            results['is_valid'] = False

        return results

    def _validate_required_fields(self, template_data, results):
        """Valide la présence des champs obligatoires"""
        for field in self.validation_rules['required_fields']:
            if field not in template_data or not template_data[field].strip():
                results['errors'].append(f"Champ obligatoire manquant: {field}")

    def _validate_formats(self, content, results):
        """Valide les formats des données (dates, identifiants, etc.)"""
        # Validation des dates
        dates_found = re.findall(r'\d{1,2}[/.-]\d{1,2}[/.-]\d{4}', content)
        for date in dates_found:
            if not self._is_valid_date(date):
                results['warnings'].append(f"Format de date suspect: {date}")

    def _validate_consistency(self, content, template_data, results):
        """Valide la cohérence entre le contenu et les données du template"""
        # Vérifier que les données du template apparaissent bien dans le contenu
        for field_name, field_value in template_data.items():
            if field_value and len(field_value) > 3:  # Ignorer les valeurs trop courtes
                if field_value.lower() not in content.lower():
                    results['warnings'].append(
                        f"La valeur '{field_value}' du champ '{field_name}' "
                        f"n'apparaît pas dans le contenu du document"
                    )

    def _validate_submission_type(self, document, results):
        """Validation spécifique au type de soumission"""
        submission = document.submission

        if submission.region == 'EU':
            # Validations spécifiques EMA
            if not document.template_data.get('ectd_sequence'):
                results['warnings'].append("Séquence eCTD recommandée pour les soumissions EMA")

        elif submission.region == 'US':
            # Validations spécifiques FDA
            results['suggestions'].append("Vérifier la conformité avec les guidelines FDA")

    def _get_document_content(self, document):
        """Récupère le contenu textuel du document"""
        if document.content_extracted:
            if isinstance(document.content_extracted, dict):
                return document.content_extracted.get('modified_content') or \
                    document.content_extracted.get('text', '')
            return str(document.content_extracted)
        return ""

    def _is_valid_date(self, date_str):
        """Vérifie si une date est valide"""
        try:
            # Logique de validation de date
            import datetime
            # Parse différents formats de date
            formats = ['%d/%m/%Y', '%d-%m-%Y', '%d.%m.%Y', '%Y/%m/%d', '%Y-%m-%d']
            for fmt in formats:
                try:
                    datetime.datetime.strptime(date_str, fmt)
                    return True
                except ValueError:
                    continue
            return False
        except:
            return False


# ===== FONCTION UTILITAIRE POUR REMPLACER L'ANCIENNE =====

def replace_document_upload_with_enhanced():
    """
    Fonction utilitaire pour remplacer l'ancienne fonction document_upload
    par la version enhanced dans les URLs
    """
    # Cette fonction peut être utilisée pour mettre à jour les références
    # dans urls.py si nécessaire
    pass



@csrf_exempt
@login_required
def api_update_template(request, document_id):
    """
    API pour mettre à jour un template
    """
    if request.method == 'POST':
        try:
            document = get_object_or_404(Document, id=document_id, submission__created_by=request.user)

            template_data = json.loads(request.body)

            # Mettre à jour les champs du template
            for field_data in template_data.get('fields', []):
                field_id = field_data.get('id')
                if field_id:
                    try:
                        field = TemplateField.objects.get(id=field_id, document=document)
                        field.field_value = field_data.get('value', '')
                        field.save()
                    except TemplateField.DoesNotExist:
                        pass

            # Mettre à jour le template_data du document
            document.template_data = template_data
            document.save()

            return JsonResponse({
                'success': True,
                'message': 'Template mis à jour avec succès'
            })

        except Exception as e:
            return JsonResponse({
                'success': False,
                'message': f'Erreur lors de la mise à jour: {str(e)}'
            })

    return JsonResponse({'success': False, 'message': 'Méthode non autorisée'})


# Ajouts aux vues existantes dans ctd_submission/views.py

import os
from django.http import HttpResponse, Http404
from django.conf import settings
from django.views.decorators.cache import cache_control
import mimetypes


# Vue pour servir les fichiers statiques JavaScript
# Vue pour servir les fichiers statiques
@login_required
def serve_static_file(request, path):
    """
    Sert les fichiers statiques de l'application (pour développement)
    """
    try:
        from django.http import Http404
        from django.conf import settings
        import mimetypes

        # En production, utiliser un serveur web approprié
        if settings.DEBUG:
            static_root = os.path.join(settings.BASE_DIR, 'ctd_submission', 'static')
            file_path = os.path.join(static_root, path)

            if os.path.exists(file_path) and file_path.startswith(static_root):
                content_type, _ = mimetypes.guess_type(file_path)
                if not content_type:
                    content_type = 'application/octet-stream'

                with open(file_path, 'rb') as f:
                    response = HttpResponse(f.read(), content_type=content_type)
                    return response

        raise Http404("Fichier non trouvé")

    except Exception as e:
        logger.error(f"Erreur service fichier statique {path}: {e}")
        raise Http404("Erreur lors du chargement du fichier")
# Corrections des vues existantes pour l'éditeur avancé

@login_required
def document_advanced_editor(request, document_id):
    """
    Vue pour l'éditeur avancé avec support de la structure préservée
    """
    document = get_object_or_404(Document, id=document_id, submission__created_by=request.user)

    # Extraire le contenu avec le processeur structuré si nécessaire
    if not document.content_extracted and UTILS_AVAILABLE:
        try:
            processor = DocumentProcessor()
            extracted_content = processor.extract_content(document)
            if extracted_content:
                document.content_extracted = extracted_content
                document.save()
        except Exception as e:
            logger.warning(f"Erreur extraction contenu: {e}")

    # Préparer le contenu pour l'affichage
    content = document.content_extracted or {'text': f'Document: {document.name}', 'extracted': False}

    # Améliorer le HTML pour l'édition si c'est une extraction structurée
    if isinstance(content, dict) and content.get('extracted', False):
        if content.get('extraction_method') == 'pymupdf_structured':
            # Le HTML est déjà optimisé pour l'édition
            pass
        elif not content.get('html') and content.get('text'):
            # Créer du HTML basique pour l'édition
            content['html'] = _create_editable_html_from_text(content['text'], document.document_type)

    # Récupérer les champs de template s'ils existent
    template_fields = TemplateField.objects.filter(document=document).order_by('row_number', 'column_number')

    context = {
        'document': document,
        'content': content,
        'template_fields': template_fields,
        'copilot_enabled': UTILS_AVAILABLE,
        'has_extracted_content': bool(content and content.get('extracted', False)),
        'has_structured_content': bool(content and content.get('structure', {}).get('elements')),
        'extraction_method': content.get('extraction_method', 'unknown') if content else 'none',
        'csrf_token': get_token(request)
    }

    return render(request, 'ctd_submission/document_advanced_editor.html', context)


def _create_editable_html_from_text(text: str, document_type: str) -> str:
    """
    Crée du HTML éditable basique à partir du texte
    """
    if not text:
        return '<p class="editable-element" contenteditable="true">Aucun contenu disponible</p>'

    # Diviser en paragraphes
    paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]

    html_parts = ['<div class="editable-content">']

    for i, para in enumerate(paragraphs):
        # Nettoyer le texte
        clean_para = para.replace('<', '&lt;').replace('>', '&gt;')

        # Détecter le type d'élément
        if len(clean_para) < 100 and (clean_para.isupper() or any(
                word in clean_para.lower() for word in ['chapitre', 'section', 'figure', 'tableau'])):
            html_parts.append(
                f'<h3 class="editable-element" contenteditable="true" data-element-id="heading-{i}">{clean_para}</h3>')
        else:
            html_parts.append(
                f'<p class="editable-element" contenteditable="true" data-element-id="para-{i}">{clean_para}</p>')

    html_parts.append('</div>')
    return '\n'.join(html_parts)

@csrf_exempt
@login_required
def document_save_changes(request, document_id):
    """
    Sauvegarde les modifications apportées dans l'éditeur avancé - VERSION CORRIGÉE
    """
    if request.method == 'POST':
        try:
            document = get_object_or_404(Document, id=document_id, submission__created_by=request.user)

            # Parser le JSON de la requête
            try:
                data = json.loads(request.body)
            except json.JSONDecodeError:
                return JsonResponse({
                    'success': False,
                    'message': 'Données JSON invalides'
                })

            # Récupérer le contenu modifié
            modified_content = data.get('content', '')
            changes = data.get('changes', [])

            # Mettre à jour le contenu du document
            if not document.content_extracted:
                document.content_extracted = {}

            document.content_extracted['modified_content'] = modified_content
            document.content_extracted['last_modified'] = timezone.now().isoformat()
            document.content_extracted['modifications_count'] = len(changes)
            document.content_extracted['extracted'] = True

            # Créer une nouvelle version du document si le modèle existe
            try:
                last_version = DocumentVersion.objects.filter(document=document).order_by('-version_number').first()
                next_version = (last_version.version_number + 1) if last_version else 1

                DocumentVersion.objects.create(
                    document=document,
                    version_number=next_version,
                    content_data=document.content_extracted,
                    template_data=document.template_data or {},
                    changes_summary=changes,
                    description=f"Modification via éditeur avancé - {len(changes)} changement(s)",
                    created_by=request.user,
                    is_current=True
                )

                # Marquer les anciennes versions comme non-actuelles
                DocumentVersion.objects.filter(
                    document=document,
                    version_number__lt=next_version
                ).update(is_current=False)

            except Exception as version_error:
                logger.warning(f"Erreur lors de la création de version: {version_error}")

            # Traiter les changements avec l'analyseur intelligent si disponible
            global_suggestions = []
            try:
                if changes and UTILS_AVAILABLE:
                    analyzer = IntelligentCopilot()
                    global_suggestions = analyzer.analyze_global_changes(document, changes)
            except Exception as analyzer_error:
                logger.warning(f"Erreur analyseur: {analyzer_error}")

            # Sauvegarder le document
            document.save()

            return JsonResponse({
                'success': True,
                'message': 'Modifications sauvegardées avec succès',
                'global_suggestions': global_suggestions,
                'version_created': True,
                'timestamp': timezone.now().isoformat()
            })

        except Exception as e:
            logger.error(f"Erreur lors de la sauvegarde: {e}")
            return JsonResponse({
                'success': False,
                'message': f'Erreur lors de la sauvegarde: {str(e)}'
            })

    return JsonResponse({'success': False, 'message': 'Méthode non autorisée'})


@csrf_exempt
@login_required
def copilot_suggestions(request, document_id):
    """
    API pour obtenir des suggestions du Copilot intelligent - VERSION CORRIGÉE
    """
    if request.method == 'POST':
        try:
            document = get_object_or_404(Document, id=document_id, submission__created_by=request.user)

            try:
                data = json.loads(request.body)
            except json.JSONDecodeError:
                return JsonResponse({
                    'success': False,
                    'message': 'Données JSON invalides'
                })

            change_type = data.get('type')
            change_content = data.get('content')
            context = data.get('context', {})

            # Générer des suggestions
            suggestions = []

            try:
                if UTILS_AVAILABLE:
                    copilot = IntelligentCopilot()
                    suggestions = copilot.get_smart_suggestions(document, change_type, change_content, context)
                else:
                    # Suggestions de fallback
                    suggestions = _generate_fallback_suggestions(change_type, change_content, context)
            except Exception as copilot_error:
                logger.warning(f"Erreur Copilot: {copilot_error}")
                suggestions = _generate_fallback_suggestions(change_type, change_content, context)

            return JsonResponse({
                'success': True,
                'suggestions': suggestions,
                'timestamp': timezone.now().isoformat()
            })

        except Exception as e:
            logger.error(f"Erreur Copilot: {e}")
            return JsonResponse({
                'success': False,
                'message': f'Erreur lors de la génération de suggestions: {str(e)}'
            })

    return JsonResponse({'success': False, 'message': 'Méthode non autorisée'})

def _generate_fallback_suggestions(change_type, change_content, context):
    """
    Génère des suggestions de base quand le Copilot avancé n'est pas disponible
    """
    suggestions = []

    if change_type == 'text_change':
        # Vérification orthographique basique
        if change_content and len(change_content.split()) == 1:
            suggestions.append({
                'type': 'spelling_check',
                'message': 'Vérifier l\'orthographe de ce mot',
                'confidence': 0.6,
                'action': 'verify'
            })

        # Détection de dates
        if re.search(r'\d{1,2}[/.-]\d{1,2}[/.-]\d{4}', change_content):
            suggestions.append({
                'type': 'date_format',
                'message': 'Format de date détecté - vérifier la cohérence',
                'confidence': 0.8,
                'action': 'verify'
            })

    return suggestions


@csrf_exempt
@login_required
def apply_template_to_editor(request, document_id):
    """
    Applique un template généré automatiquement à l'éditeur - VERSION CORRIGÉE
    """
    if request.method == 'POST':
        try:
            document = get_object_or_404(Document, id=document_id, submission__created_by=request.user)

            # Générer ou récupérer le template
            if not document.is_template_generated:
                # Utiliser la fonction existante de génération de template
                generate_document_template(document)

            # Récupérer les champs du template
            template_fields = TemplateField.objects.filter(document=document)

            # Préparer les données de préremplissage
            prefill_data = {}
            for field in template_fields:
                prefill_data[field.field_name] = {
                    'label': field.field_label,
                    'value': field.field_value,
                    'type': field.field_type,
                    'required': field.is_required,
                    'position': {
                        'row': field.row_number,
                        'column': field.column_number
                    }
                }

            # Analyser le contenu pour suggérer des positions d'insertion
            insertion_suggestions = []
            try:
                copilot = IntelligentCopilot()
                insertion_suggestions = copilot.suggest_template_positions(document, prefill_data)
            except:
                # Suggestions basiques si le copilot n'est pas disponible
                insertion_suggestions = [
                    {
                        'field_name': 'general',
                        'field_label': 'Champs généraux',
                        'suggested_position': {'line': 0, 'confidence': 0.5},
                        'reasoning': 'Position par défaut en début de document'
                    }
                ]

            return JsonResponse({
                'success': True,
                'template_data': prefill_data,
                'insertion_suggestions': insertion_suggestions,
                'fields_count': len(prefill_data),
                'message': 'Template prêt à être appliqué'
            })

        except Exception as e:
            logger.error(f"Erreur application template: {e}")
            return JsonResponse({
                'success': False,
                'message': f'Erreur lors de l\'application du template: {str(e)}'
            })

    return JsonResponse({'success': False, 'message': 'Méthode non autorisée'})


@csrf_exempt
@login_required
def document_export_modified(request, document_id):
    """
    Exporte le document modifié dans son format original - VERSION CORRIGÉE
    """
    document = get_object_or_404(Document, id=document_id, submission__created_by=request.user)

    try:
        # Utiliser l'exporteur si disponible, sinon export basique
        try:
            exporter = DocumentExporter()
            exported_file = exporter.export_modified_document(document)

            if exported_file:
                # Déterminer l'extension du fichier
                file_extension = document.document_type
                if file_extension == 'docx':
                    content_type = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
                elif file_extension == 'xlsx':
                    content_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                elif file_extension == 'pdf':
                    content_type = 'application/pdf'
                else:
                    content_type = 'application/octet-stream'

                response = HttpResponse(
                    exported_file.read(),
                    content_type=content_type
                )
                response['Content-Disposition'] = f'attachment; filename="{document.name}_modifie.{file_extension}"'
                return response
        except:
            # Export basique - créer un fichier texte avec le contenu modifié
            content = document.content_extracted or {}
            modified_content = content.get('modified_content', content.get('text', ''))

            if not modified_content:
                modified_content = f"Document: {document.name}\nAucune modification disponible."

            # Ajouter les métadonnées
            export_content = f"""Document: {document.name}
Type: {document.get_document_type_display()}
Section: {document.section.name if document.section else 'Non assignée'}
Dernière modification: {content.get('last_modified', 'Inconnue')}
Nombre de modifications: {content.get('modifications_count', 0)}

=== CONTENU MODIFIÉ ===

{modified_content}

=== INFORMATIONS TECHNIQUES ===
Exporté le: {timezone.now().strftime('%d/%m/%Y à %H:%M')}
Utilisateur: {request.user.get_full_name() or request.user.username}
"""

            response = HttpResponse(export_content, content_type='text/plain; charset=utf-8')
            response['Content-Disposition'] = f'attachment; filename="{document.name}_modifie.txt"'
            return response

    except Exception as e:
        logger.error(f"Erreur export document: {e}")
        messages.error(request, f'Erreur lors de l\'export: {str(e)}')
        return redirect('ctd_submission:document_advanced_editor', document_id=document.id)


# Dans ctd_submission/views.py

@require_http_methods(["POST"])
@login_required
def api_extract_content(request, document_id):
    """API pour extraire le contenu d'un document avec le processeur fidèle"""
    try:
        document = get_object_or_404(Document, id=document_id)

        # Utiliser le processeur amélioré
        processor = DocumentProcessor()  # Maintenant utilise FaithfulPDFProcessor
        result = processor.extract_content(document)

        if result.get('extracted', False):
            # Sauvegarder le contenu extrait
            document.content_extracted = result
            document.extraction_status = 'completed'
            document.extraction_date = timezone.now()
            document.save()

            # Log des métriques d'extraction
            if 'structure' in result and 'tables' in result['structure']:
                tables_count = len(result['structure']['tables'])
                logger.info(f"✅ Document {document.id}: {tables_count} tableaux extraits avec fidélité")

            return JsonResponse({
                'success': True,
                'message': 'Contenu extrait avec succès',
                'extraction_method': result.get('extraction_method', 'unknown'),
                'tables_count': len(result.get('structure', {}).get('tables', [])),
                'has_structured_content': bool(result.get('structure', {}).get('tables'))
            })
        else:
            return JsonResponse({
                'success': False,
                'message': result.get('error', 'Extraction échouée'),
                'extraction_method': result.get('extraction_method', 'unknown')
            })

    except Exception as e:
        logger.error(f"Erreur API extraction document {document_id}: {e}")
        return JsonResponse({
            'success': False,
            'message': f'Erreur serveur: {str(e)}'
        }, status=500)


# Ajouter une vue pour recalculer l'extraction avec le nouveau processeur
@require_http_methods(["POST"])
@login_required
def reprocess_document_faithful(request, document_id):
    """Force le retraitement d'un document avec le processeur fidèle"""
    try:
        document = get_object_or_404(Document, id=document_id)

        # Réinitialiser les données d'extraction
        document.content_extracted = None
        document.extraction_status = 'pending'
        document.save()

        # Relancer l'extraction avec le nouveau processeur
        processor = DocumentProcessor()
        result = processor.extract_content(document)

        if result.get('extracted', False):
            document.content_extracted = result
            document.extraction_status = 'completed'
            document.extraction_date = timezone.now()
            document.save()

            return JsonResponse({
                'success': True,
                'message': 'Document retraité avec succès',
                'redirect_url': reverse('ctd_submission:document_advanced_editor', args=[document_id])
            })
        else:
            document.extraction_status = 'failed'
            document.save()
            return JsonResponse({
                'success': False,
                'message': f'Erreur de retraitement: {result.get("error", "Erreur inconnue")}'
            })

    except Exception as e:
        logger.error(f"Erreur retraitement document {document_id}: {e}")
        return JsonResponse({
            'success': False,
            'message': f'Erreur serveur: {str(e)}'
        }, status=500)

# NOUVELLE FONCTION: Diagnostic système pour l'extraction PDF
@login_required
def system_pdf_diagnostic(request):
    """
    Page de diagnostic pour vérifier l'état du système d'extraction PDF
    """
    if not request.user.is_staff:
        messages.error(request, "Accès restreint aux administrateurs")
        return redirect('ctd_submission:dashboard')

    diagnostic = {}

    try:
        # Test des imports
        processor = DocumentProcessor()
        pdf_processor = processor.pdf_processor

        diagnostic = {
            'available_processors': pdf_processor.available_processors,
            'libraries_status': {},
            'system_info': {
                'django_available': DJANGO_AVAILABLE,
                'models_available': MODELS_AVAILABLE,
                'utils_available': UTILS_AVAILABLE
            }
        }

        # Test de chaque bibliothèque
        test_libraries = ['pymupdf', 'pdfplumber', 'pdfminer', 'pypdf2']
        for lib in test_libraries:
            try:
                if lib == 'pymupdf':
                    import fitz
                    diagnostic['libraries_status'][lib] = {'available': True,
                                                           'version': fitz.__version__ if hasattr(fitz,
                                                                                                  '__version__') else 'unknown'}
                elif lib == 'pdfplumber':
                    import pdfplumber
                    diagnostic['libraries_status'][lib] = {'available': True,
                                                           'version': pdfplumber.__version__ if hasattr(pdfplumber,
                                                                                                        '__version__') else 'unknown'}
                elif lib == 'pdfminer':
                    import pdfminer
                    diagnostic['libraries_status'][lib] = {'available': True, 'version': 'unknown'}
                elif lib == 'pypdf2':
                    import PyPDF2
                    diagnostic['libraries_status'][lib] = {'available': True,
                                                           'version': PyPDF2.__version__ if hasattr(PyPDF2,
                                                                                                    '__version__') else 'unknown'}
            except ImportError as e:
                diagnostic['libraries_status'][lib] = {'available': False, 'error': str(e)}

        # Statistiques des documents
        total_docs = Document.objects.count()
        pdf_docs = Document.objects.filter(document_type='pdf').count()
        extracted_docs = Document.objects.filter(content_extracted__isnull=False).count()

        diagnostic['document_stats'] = {
            'total_documents': total_docs,
            'pdf_documents': pdf_docs,
            'extracted_documents': extracted_docs,
            'extraction_rate': (extracted_docs / pdf_docs * 100) if pdf_docs > 0 else 0
        }

    except Exception as e:
        diagnostic['error'] = str(e)
        logger.error(f"Erreur diagnostic système: {e}")

    context = {
        'diagnostic': diagnostic,
        'installation_commands': {
            'pymupdf': 'pip install PyMuPDF',
            'pdfplumber': 'pip install pdfplumber',
            'pdfminer': 'pip install pdfminer.six',
            'pypdf2': 'pip install PyPDF2'
        }
    }

    return render(request, 'ctd_submission/system_pdf_diagnostic.html', context)
# Fonction utilitaire pour générer le template (amélioration de l'existante)


def _get_ema_cover_letter_template():
    """Template spécialisé pour les lettres de couverture EMA"""
    return [
        {'name': 'applicant_name', 'label': 'Applicant/MAH Name', 'type': 'text', 'required': True},
        {'name': 'customer_account', 'label': 'Customer Account Number', 'type': 'text', 'required': True},
        {'name': 'customer_reference', 'label': 'Customer Reference / Purchase Order Number', 'type': 'text'},
        {'name': 'inn_code', 'label': 'INN / Active substance/ATC Code', 'type': 'text'},
        {'name': 'product_name', 'label': 'Product Name of centrally authorised medicinal product(s)', 'type': 'text'},
        {'name': 'nationally_authorised', 'label': 'Nationally Authorised Product(s)', 'type': 'checkbox'},
        {'name': 'product_number', 'label': 'Product Number or Procedure Number', 'type': 'text'},
        {'name': 'submission_type', 'label': 'Is this: A submission of a new procedure', 'type': 'select',
         'options': ['A submission of a new procedure',
                     'A response/supplementary information to an on-going procedure']},
        {'name': 'unit_type', 'label': 'Unit Type', 'type': 'select', 'options': ['Please select']},
        {'name': 'mode', 'label': 'Mode', 'type': 'select', 'options': ['Single', 'Grouping']},
        {'name': 'procedure_type', 'label': 'Procedure Type', 'type': 'text',
         'value': 'MAA - Marketing Authorisation Application'},
        {'name': 'description', 'label': 'Description of submission', 'type': 'select', 'options': ['Please select']},
        {'name': 'rmp_included', 'label': 'RMP included in this submission', 'type': 'select',
         'options': ['Yes', 'No']},
        {'name': 'ectd_sequence', 'label': 'eCTD sequence', 'type': 'text'},
    ]


def _get_application_form_template():
    """Template pour les formulaires d'application"""
    return [
        {'name': 'company_name', 'label': 'Company Name', 'type': 'text', 'required': True},
        {'name': 'contact_person', 'label': 'Contact Person', 'type': 'text', 'required': True},
        {'name': 'email', 'label': 'Email Address', 'type': 'text', 'required': True},
        {'name': 'phone', 'label': 'Phone Number', 'type': 'text'},
        {'name': 'application_date', 'label': 'Application Date', 'type': 'date'},
        {'name': 'application_type', 'label': 'Application Type', 'type': 'select',
         'options': ['Initial', 'Variation', 'Extension', 'Renewal']},
    ]


def _get_quality_summary_template():
    """Template pour les résumés qualité"""
    return [
        {'name': 'substance_name', 'label': 'Active Substance Name', 'type': 'text', 'required': True},
        {'name': 'manufacturer', 'label': 'Manufacturer', 'type': 'text'},
        {'name': 'manufacturing_site', 'label': 'Manufacturing Site', 'type': 'text'},
        {'name': 'specification', 'label': 'Specification', 'type': 'textarea'},
        {'name': 'stability_data', 'label': 'Stability Data', 'type': 'textarea'},
    ]


def _get_clinical_template():
    """Template pour les documents cliniques"""
    return [
        {'name': 'study_title', 'label': 'Study Title', 'type': 'text', 'required': True},
        {'name': 'protocol_number', 'label': 'Protocol Number', 'type': 'text'},
        {'name': 'study_phase', 'label': 'Study Phase', 'type': 'select',
         'options': ['Phase I', 'Phase II', 'Phase III', 'Phase IV']},
        {'name': 'primary_endpoint', 'label': 'Primary Endpoint', 'type': 'textarea'},
        {'name': 'patient_population', 'label': 'Patient Population', 'type': 'textarea'},
    ]


def _get_generic_template(content):
    """Template générique basé sur l'analyse du contenu"""
    return [
        {'name': 'document_title', 'label': 'Document Title', 'type': 'text', 'required': True},
        {'name': 'document_date', 'label': 'Document Date', 'type': 'date'},
        {'name': 'author', 'label': 'Author', 'type': 'text'},
        {'name': 'version', 'label': 'Version', 'type': 'text'},
        {'name': 'description', 'label': 'Description', 'type': 'textarea'},
        {'name': 'keywords', 'label': 'Keywords', 'type': 'text'},
    ]


##########################################################
#####################################################
