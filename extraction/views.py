# extraction/views.py
import logging

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.core.paginator import Paginator
from django.db.models import Q, Count, Avg
from django.utils import timezone
from django.urls import reverse
import json
from datetime import datetime

from documents.models import Document, DocumentType, DocumentContext
from .models import ExtractionResult
from .tasks import extract_document_metadata  # Import direct de la fonction
from audit.models import AuditLog

logger = logging.getLogger(__name__)
def normalize_extracted_data(extracted_data):
    """Normalise les données extraites SANS écraser un titre valide"""

    # SAUVEGARDER le titre original avant normalisation
    original_title = extracted_data.get('title', '').strip()

    # Normalisation des types de documents
    type_map = {
        'procedure': 'procedure',  # Garder tel quel
        'report': 'rapport',
        'guideline': 'guideline',  # Garder tel quel
        'image': 'image',
        'article': 'article',
        'manual': 'manuel',
        'regulation': 'regulation',
        'directive': 'directive',
        'standard': 'standard',
        'other': 'other',
    }

    context_map = {
        'pharmaceutical': 'pharmaceutique',
        'pharmaceuticals': 'pharmaceutique',
        'technical': 'technique',
        'biology': 'biologie',
        'medical': 'medical',
        'legal': 'legal',
        'regulatory': 'regulatory',
    }

    lang_map = {
        'fr': 'fr',
        'français': 'fr',
        'french': 'fr',
        'en': 'en',
        'english': 'en',
        'es': 'es',
        'spanish': 'es',
        'de': 'de',
        'german': 'de',
        'it': 'it',
        'italian': 'it',
    }

    # Normaliser le type de document
    dt = extracted_data.get('document_type', '').lower()
    extracted_data['document_type'] = type_map.get(dt, dt)

    # Normaliser le contexte
    ctx = extracted_data.get('context', '').lower()
    extracted_data['context'] = context_map.get(ctx, ctx)

    # Normaliser la langue
    lang = extracted_data.get('language', '').lower()
    extracted_data['language'] = lang_map.get(lang, 'fr')

    # Traiter la date de publication
    pub_date = extracted_data.get('publication_date')
    if pub_date:
        try:
            # Essayer le format "6 June 2006" d'abord (format LLM)
            dt_obj = datetime.strptime(pub_date, '%d %B %Y')
            extracted_data['publication_date'] = dt_obj.strftime('%Y-%m-%d')
        except ValueError:
            try:
                # Essayer le format "June 6, 2006"
                dt_obj = datetime.strptime(pub_date, '%B %d, %Y')
                extracted_data['publication_date'] = dt_obj.strftime('%Y-%m-%d')
            except ValueError:
                try:
                    # Essayer le format ISO déjà correct
                    dt_obj = datetime.strptime(pub_date, '%Y-%m-%d')
                    extracted_data['publication_date'] = pub_date  # Garder tel quel
                except ValueError:
                    pass  # Garde la valeur brute si échec

    # CORRECTION CRITIQUE : PRÉSERVER le titre original s'il est valide
    if original_title and original_title.lower() not in ['document sans titre', 'untitled', '', 'none']:
        extracted_data['title'] = original_title
        logger.info(f"✅ Titre préservé après normalisation: '{original_title}'")
    else:
        # Si le titre n'est pas valide, le laisser tel quel pour traitement ultérieur
        logger.warning(f"⚠️ Titre non valide préservé pour traitement: '{original_title}'")

    return extracted_data


@login_required
def metadata_validation_list(request):
    """Liste des documents nécessitant une validation des métadonnées"""

    if request.user.role not in ['metadonneur', 'admin']:
        messages.error(request, 'Vous n\'avez pas les permissions pour accéder à cette page.')
        return redirect('dashboard:home')

    status_filter = request.GET.get('status', 'all')
    search = request.GET.get('search', '')
    confidence_filter = request.GET.get('confidence', 'all')

    documents = Document.objects.filter(
        status__in=['extracted', 'extracting', 'refused']
    ).select_related('document_type', 'context', 'assigned_to').prefetch_related('extraction_results')

    if status_filter != 'all':
        documents = documents.filter(status=status_filter)

    if search:
        documents = documents.filter(
            Q(title__icontains=search) |
            Q(extracted_title__icontains=search) |
            Q(source__icontains=search) |
            Q(assigned_to__username__icontains=search)
        )

    if confidence_filter == 'high':
        documents = documents.filter(extraction_results__confidence_score__gte=0.8)
    elif confidence_filter == 'medium':
        documents = documents.filter(
            extraction_results__confidence_score__gte=0.5,
            extraction_results__confidence_score__lt=0.8
        )
    elif confidence_filter == 'low':
        documents = documents.filter(extraction_results__confidence_score__lt=0.5)

    paginator = Paginator(documents.distinct().order_by('-created_at'), 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    for document in page_obj:
        document.extraction_result = document.extraction_results.first()

    context = {
        'page_obj': page_obj,
        'current_filters': {
            'status': status_filter,
            'search': search,
            'confidence': confidence_filter
        },
        'status_choices': [
            ('all', 'Tous'),
            ('extracted', 'Extraits'),
            ('extracting', 'En extraction'),
            ('refused', 'Refusés')
        ],
        'confidence_choices': [
            ('all', 'Toutes'),
            ('high', 'Élevée (>80%)'),
            ('medium', 'Moyenne (50-80%)'),
            ('low', 'Faible (<50%)')
        ],
        'total_documents': paginator.count
    }

    return render(request, 'extraction/validation_list.html', context)


@login_required
def metadata_validation_detail(request, document_id):
    """Interface de validation des métadonnées - LECTURE EMA CORRIGÉE"""

    if request.user.role not in ['metadonneur', 'admin']:
        messages.error(request, 'Vous n\'avez pas les permissions pour accéder à cette page.')
        return redirect('dashboard:home')

    document = get_object_or_404(Document, id=document_id)
    extraction_result = document.extraction_results.first()
    print("ExtractionResult pour le document:", extraction_result)

    default_data = {
        'title': None,
        'document_type': 'rapport',
        'context': 'technique',
        'language': 'fr',
        'publication_date': None,
        'source': '',
        'version': None,
        'source_url': None
    }

    default_scores = {
        'title': 0.0,
        'document_type': 0.0,
        'context': 0.0,
        'language': 0.0,
        'publication_date': 0.0,
        'source': 0.0,
        'version': 0.0,
        'source_url': 0.0
    }

    if extraction_result:
        try:
            raw_data = extraction_result.extracted_data
            print("Raw data from extraction_result:", raw_data)

            # CORRECTION CRITIQUE : Lecture de la structure plate
            if isinstance(raw_data, str):
                parsed_data = json.loads(raw_data)
            else:
                parsed_data = raw_data

            # Vérifier si les données sont dans une structure imbriquée ou plate
            if 'metadata' in parsed_data:
                # Structure imbriquée (ancienne)
                extracted_data = parsed_data['metadata'].copy()
                logger.info("📖 Lecture structure imbriquée (ancienne)")
            else:
                # Structure plate (nouvelle)
                extracted_data = parsed_data.copy()
                logger.info("📖 Lecture structure plate (nouvelle)")

            # SUPPRIMER explicitement les clés parasites
            unwanted_keys = [
                'confidence_scores', 'extraction_reasoning', 'ema_data',
                'extraction_stats', 'quality_score', 'country', 'url_source'
            ]
            for key in unwanted_keys:
                extracted_data.pop(key, None)

            # VÉRIFICATION SPÉCIALE du titre AVANT normalisation
            original_title = extracted_data.get('title', '').strip()
            logger.info(f"🔍 Titre lu depuis ExtractionResult: '{original_title}'")

        except (json.JSONDecodeError, TypeError, AttributeError) as e:
            print("Error parsing extracted_data:", e)
            extracted_data = {}
            original_title = ''

        # Application valeurs par défaut SEULEMENT si les champs sont vides
        for key, default_value in default_data.items():
            if key == 'title':
                continue
            value = extracted_data.get(key)
            if value in [None, '', []] or (isinstance(value, str) and not value.strip()):
                extracted_data[key] = default_value

        # Normaliser les données (sans écraser le titre)
        extracted_data = normalize_extracted_data(extracted_data)

        # CORRECTION CRITIQUE : Traitement intelligent du titre
        llm_title = original_title
        document_title = document.extracted_title or document.title or ''
        filename_title = (document.file.name.split('/')[-1].replace('.pdf', '')
                          if document.file else 'Document sans titre')

        # Priorité : 1) Titre LLM valide, 2) Titre document, 3) Nom fichier
        final_title = ''

        if llm_title and llm_title.lower() not in ['document sans titre', 'untitled', '']:
            final_title = llm_title
            logger.info(f"✅ Utilisation titre LLM: '{final_title}'")
        elif document_title and document_title.lower() not in ['document sans titre', 'untitled', '']:
            final_title = document_title
            logger.info(f"⚠️ Fallback titre document: '{final_title}'")
        else:
            final_title = filename_title
            logger.info(f"❌ Fallback nom fichier: '{final_title}'")

        extracted_data['title'] = final_title

        # Traiter les scores de confiance
        try:
            confidence_scores = extraction_result.confidence_scores
            confidence_scores = json.loads(confidence_scores) if isinstance(confidence_scores,
                                                                            str) else confidence_scores
        except (json.JSONDecodeError, TypeError, AttributeError):
            confidence_scores = default_scores

        # Convertir les scores en pourcentages arrondis et les valider
        computed_scores = {}
        for k in default_scores:
            score = confidence_scores.get(k, 0)
            try:
                if isinstance(score, (int, float)):
                    if 0 <= score <= 1:
                        computed_scores[k] = round(float(score) * 100)
                    elif 0 <= score <= 100:
                        computed_scores[k] = round(float(score))
                    else:
                        computed_scores[k] = 0
                else:
                    computed_scores[k] = 0
            except (ValueError, TypeError):
                computed_scores[k] = 0

        confidence_score_global = round(float(extraction_result.confidence_score or 0) * 100)

    else:
        # Pas de résultat d'extraction - utiliser les valeurs par défaut
        extracted_data = default_data.copy()

        # Titre par défaut intelligent
        document_title = document.extracted_title or document.title or ''
        if document_title and document_title.lower() not in ['document sans titre', 'untitled', '']:
            extracted_data['title'] = document_title
        else:
            extracted_data['title'] = (document.file.name.split('/')[-1].replace('.pdf', '')
                                       if document.file else 'Document sans titre')

        computed_scores = {k: 0 for k in default_scores}
        confidence_score_global = 0

    # === CORRECTION CRITIQUE: Lecture EMA UNIQUEMENT depuis l'extraction récente ===
    ema_data_from_extraction = {}

    if extraction_result and isinstance(raw_data, dict):
        print("🔍 ExtractionResult trouvé, lecture des données EMA...", raw_data)
        logger.info(f"🔍 Recherche données EMA dans extraction_result {extraction_result.id}")

        # Chercher les données EMA dans le résultat d'extraction
        if 'ema_data' in raw_data:
            ema_data_from_extraction = raw_data['ema_data']
            logger.info(f"📊 EMA data trouvées dans 'ema_data': {ema_data_from_extraction}")
        elif any(k.startswith('ema_') or k == 'original_publication_date' for k in raw_data.keys()):
            ema_data_from_extraction = {
                'original_publication_date': raw_data.get('original_publication_date'),
                'ema_publication_date': raw_data.get('ema_publication_date'),
                'ema_source_url': raw_data.get('ema_source_url', ''),
                'ema_title': raw_data.get('ema_title', ''),
                'ema_reference': raw_data.get('ema_reference', ''),
            }
            logger.info(f"📊 EMA data extraites des champs individuels: {ema_data_from_extraction}")
        else:
            logger.info(f"📊 Aucune donnée EMA dans l'extraction récente")

    # === CORRECTION: Utiliser UNIQUEMENT les données de l'extraction ===
    # Ne PAS faire de fallback vers les données obsolètes du document
    ema_data = {
        'original_publication_date': ema_data_from_extraction.get('original_publication_date'),
        'ema_publication_date': ema_data_from_extraction.get('ema_publication_date'),
        'ema_source_url': ema_data_from_extraction.get('ema_source_url', ''),
        'ema_title': ema_data_from_extraction.get('ema_title', ''),
        'ema_reference': ema_data_from_extraction.get('ema_reference', ''),
    }
    print("📊 EMA Data finale:", ema_data)

    logger.info(f"📊 EMA Data finale (extraction uniquement): {ema_data}")

    context = {
        'ema_data': ema_data,
        'document': document,
        'extraction_result': extraction_result,
        'extracted_data': extracted_data,
        'confidence_scores': computed_scores,
        'confidence_score_global': confidence_score_global,
        'document_types': DocumentType.objects.all().order_by('name'),
        'document_contexts': DocumentContext.objects.all().order_by('name'),
        'language_choices': [
            ('fr', 'Français'), ('en', 'Anglais'), ('es', 'Espagnol'), ('de', 'Allemand'), ('it', 'Italien')
        ]
    }

    return render(request, 'extraction/validation_detail.html', context)


@login_required
@require_http_methods(["POST"])
def save_metadata(request, document_id):
    """Sauvegarder les métadonnées validées - CORRIGÉE"""

    if request.user.role not in ['metadonneur', 'admin']:
        return JsonResponse({'success': False, 'error': 'Permission refusée'}, status=403)

    document = get_object_or_404(Document, id=document_id)

    try:
        data = json.loads(request.body)

        if not data.get('title', '').strip():
            return JsonResponse({'success': False, 'error': 'Le titre est obligatoire'}, status=400)

        document.extracted_title = data.get('title', document.extracted_title)
        document.language = data.get('language', document.language)
        document.source = data.get('source', document.source)
        document.version = data.get('version', '')
        document.source_url = data.get('source_url', '')

        original_publication_date = data.get('original_publication_date')
        if original_publication_date:
            try:
                document.original_publication_date = datetime.strptime(original_publication_date, '%Y-%m-%d').date()
            except ValueError:
                pass

        ema_publication_date = data.get('ema_publication_date')
        if ema_publication_date:
            try:
                document.ema_publication_date = datetime.strptime(ema_publication_date, '%Y-%m-%d').date()
            except ValueError:
                pass

        document.ema_title = data.get('ema_title', '')
        document.ema_reference = data.get('ema_reference', '')
        document.ema_source_url = data.get('ema_source_url', '')

        publication_date = data.get('publication_date')
        if publication_date:
            try:
                document.publication_date = datetime.strptime(publication_date, '%Y-%m-%d').date()
            except ValueError:
                pass

        document_type = data.get('document_type')
        if document_type:
            try:
                doc_type = DocumentType.objects.get(name__icontains=document_type)
                document.document_type = doc_type
            except DocumentType.DoesNotExist:
                doc_type = DocumentType.objects.create(name=document_type.title(), color='#007bff')
                document.document_type = doc_type

        context = data.get('context')
        if context:
            try:
                doc_context = DocumentContext.objects.get(name__icontains=context)
                document.context = doc_context
            except DocumentContext.DoesNotExist:
                doc_context = DocumentContext.objects.create(name=context.title(), color='#28a745')
                document.context = doc_context

        document.status = 'validated'
        document.save()

        extraction_result = document.extraction_results.first()
        if extraction_result:
            if isinstance(extraction_result.extracted_data, dict):
                updated_data = extraction_result.extracted_data.copy()
            else:
                updated_data = {}

            updated_data.update({
                'title': data.get('title'),
                'document_type': document_type,
                'context': context,
                'language': data.get('language'),
                'publication_date': publication_date,
                'source': data.get('source'),
                'version': data.get('version'),
                'source_url': data.get('source_url'),
                'ema_title': data.get('ema_title'),
                'ema_reference': data.get('ema_reference'),
                'ema_source_url': data.get('ema_source_url'),
                'original_publication_date': original_publication_date,
                'ema_publication_date': ema_publication_date
            })

            extraction_result.extracted_data = updated_data
            extraction_result.status = 'validated'
            extraction_result.validated_by = request.user
            extraction_result.validated_at = timezone.now()
            extraction_result.save()

        AuditLog.objects.create(
            user=request.user,
            document=document,
            action='validate',
            description=f'Métadonnées validées et sauvegardées pour {document.title}',
            ip_address=request.META.get('REMOTE_ADDR')
        )

        return JsonResponse({
            'success': True,
            'message': 'Métadonnées sauvegardées et validées avec succès',
            'redirect_url': reverse('extraction:validation_list')
        })

    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Données JSON invalides'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': f'Erreur lors de la sauvegarde: {str(e)}'}, status=500)


@login_required
@require_http_methods(["POST"])
def re_extract_metadata(request, document_id):
    """Relancer l'extraction des métadonnées avec IA"""

    if request.user.role not in ['metadonneur', 'admin']:
        return JsonResponse({'success': False, 'error': 'Permission refusée'}, status=403)

    document = get_object_or_404(Document, id=document_id)

    try:
        document.extraction_results.all().delete()
        document.status = 'extracting'
        document.extraction_started_at = timezone.now()
        document.save()

        result = extract_document_metadata(document_id)
        print("Résultat de la ré-extraction:", result)

        AuditLog.objects.create(
            user=request.user,
            document=document,
            action='extract',
            description=f'Ré-extraction IA des métadonnées lancée pour {document.title}',
            ip_address=request.META.get('REMOTE_ADDR')
        )

        if result and result.get('success'):
            messages.success(request, 'Ré-extraction IA terminée avec succès')
            return JsonResponse({
                'success': True,
                'message': 'Ré-extraction IA terminée avec succès',
                'confidence_score': result.get('metadata', {}).get('confidence_scores', {}),
                'redirect_url': reverse('extraction:validation_detail', kwargs={'document_id': document_id})
            })
        else:
            error_message = result.get('error', 'Erreur inconnue') if result else 'Aucun résultat retourné'
            messages.error(request, f'Ré-extraction échouée: {error_message}')
            return JsonResponse({
                'success': False,
                'message': f'Ré-extraction échouée: {error_message}'
            })

    except Exception as e:
        try:
            document.status = 'refused'
            document.extraction_completed_at = timezone.now()
            document.save()
        except Exception:
            pass

        messages.error(request, f'Erreur lors de la ré-extraction: {str(e)}')
        return JsonResponse({
            'success': False,
            'error': f'Erreur lors de la ré-extraction: {str(e)}'
        }, status=500)


@login_required
@require_http_methods(["POST"])
def extract_metadata(request, document_id):
    """Lancer l'extraction des métadonnées avec IA"""

    if request.user.role not in ['metadonneur', 'admin']:
        return JsonResponse({'success': False, 'error': 'Permission refusée'}, status=403)

    document = get_object_or_404(Document, id=document_id)

    if document.status not in ['uploaded', 'refused']:
        return JsonResponse({'success': False, 'error': 'Document déjà en cours de traitement'}, status=400)

    try:
        document.status = 'extracting'
        document.extraction_started_at = timezone.now()
        document.save()

        result = extract_document_metadata(document_id)

        AuditLog.objects.create(
            user=request.user,
            document=document,
            action='extract',
            description=f'Extraction IA des métadonnées lancée pour {document.title}',
            ip_address=request.META.get('REMOTE_ADDR')
        )

        if result and result.get('success'):
            messages.success(request, 'Extraction IA terminée avec succès')
            return JsonResponse({
                'success': True,
                'message': 'Extraction IA terminée avec succès',
                'confidence_score': result.get('metadata', {}).get('confidence_scores', {}),
                'redirect_url': reverse('extraction:validation_detail', kwargs={'document_id': document_id})
            })
        else:
            error_message = result.get('error', 'Erreur inconnue') if result else 'Aucun résultat retourné'
            messages.error(request, f'Extraction échouée: {error_message}')
            return JsonResponse({
                'success': False,
                'message': f'Extraction échouée: {error_message}'
            })

    except Exception as e:
        try:
            document.status = 'refused'
            document.extraction_completed_at = timezone.now()
            document.save()
        except Exception:
            pass

        messages.error(request, f'Erreur lors de l\'extraction: {str(e)}')
        return JsonResponse({
            'success': False,
            'error': f'Erreur lors de l\'extraction: {str(e)}'
        }, status=500)


@login_required
def extraction_status(request, document_id):
    """Vérifier le statut de l'extraction"""

    document = get_object_or_404(Document, id=document_id)
    extraction_result = document.extraction_results.first()

    processing_time = None
    if document.extraction_started_at and document.extraction_completed_at:
        processing_time = (document.extraction_completed_at - document.extraction_started_at).total_seconds()

    return JsonResponse({
        'document_status': document.status,
        'extraction_completed': extraction_result is not None,
        'confidence_score': extraction_result.confidence_score if extraction_result else 0,
        'extracted_fields': len(
            extraction_result.extracted_data) if extraction_result and extraction_result.extracted_data else 0,
        'extraction_method': extraction_result.extraction_method if extraction_result else None,
        'model_version': extraction_result.model_version if extraction_result else None,
        'processing_time': processing_time,
        'extraction_started_at': document.extraction_started_at.isoformat() if document.extraction_started_at else None,
        'extraction_completed_at': document.extraction_completed_at.isoformat() if document.extraction_completed_at else None
    })


@login_required
def extraction_dashboard(request):
    """Dashboard des extractions pour les métadonneurs"""

    if request.user.role not in ['metadonneur', 'admin']:
        messages.error(request, 'Vous n\'avez pas les permissions pour accéder à cette page.')
        return redirect('dashboard:home')

    stats_query = Document.objects.aggregate(
        total_documents=Count('id'),
        extracted_documents=Count('id', filter=Q(status='extracted')),
        validated_documents=Count('id', filter=Q(status='validated')),
        failed_extractions=Count('id', filter=Q(status='refused')),
        extracting_documents=Count('id', filter=Q(status='extracting'))
    )

    recent_extractions = Document.objects.filter(
        status='extracted'
    ).select_related('document_type', 'context', 'assigned_to').prefetch_related('extraction_results').order_by(
        '-created_at')[:10]

    for document in recent_extractions:
        document.extraction_result = document.extraction_results.first()

    confidence_stats = ExtractionResult.objects.aggregate(
        high_confidence=Count('id', filter=Q(confidence_score__gte=0.8)),
        medium_confidence=Count('id', filter=Q(confidence_score__gte=0.5, confidence_score__lt=0.8)),
        low_confidence=Count('id', filter=Q(confidence_score__lt=0.5)),
        avg_confidence=Avg('confidence_score')
    )

    total_docs = stats_query['total_documents']
    extracted_docs = stats_query['extracted_documents']

    extraction_rate = round((extracted_docs / total_docs * 100) if total_docs > 0 else 0, 1)
    validation_rate = round((stats_query['validated_documents'] / extracted_docs * 100) if extracted_docs > 0 else 0, 1)

    context = {
        'stats': {
            **stats_query,
            **confidence_stats,
            'extraction_rate': extraction_rate,
            'validation_rate': validation_rate,
            'avg_confidence_percent': round(float(confidence_stats['avg_confidence'] or 0) * 100, 1)
        },
        'recent_extractions': recent_extractions,
        'chart_data': {
            'confidence_distribution': [
                confidence_stats['high_confidence'],
                confidence_stats['medium_confidence'],
                confidence_stats['low_confidence']
            ],
            'status_distribution': [
                stats_query['extracted_documents'],
                stats_query['validated_documents'],
                stats_query['failed_extractions'],
                stats_query['extracting_documents']
            ]
        }
    }

    return render(request, 'extraction/dashboard.html', context)


@login_required
def extraction_history(request, document_id):
    """Historique des extractions pour un document"""

    if request.user.role not in ['metadonneur', 'admin']:
        return JsonResponse({'success': False, 'error': 'Permission refusée'}, status=403)

    document = get_object_or_404(Document, id=document_id)

    extraction_results = document.extraction_results.all().order_by('-created_at')

    history = []
    for result in extraction_results:
        history.append({
            'id': result.id,
            'status': result.status,
            'confidence_score': result.confidence_score,
            'extraction_method': result.extraction_method,
            'model_version': result.model_version,
            'created_at': result.created_at.isoformat(),
            'validated_by': result.validated_by.username if result.validated_by else None,
            'validated_at': result.validated_at.isoformat() if result.validated_at else None,
            'processing_time': result.processing_time
        })

    return JsonResponse({
        'success': True,
        'history': history,
        'document_title': document.title
    })


@login_required
@require_http_methods(["POST"])
def batch_validate(request):
    """Validation en lot de plusieurs documents"""

    if request.user.role not in ['metadonneur', 'admin']:
        return JsonResponse({'success': False, 'error': 'Permission refusée'}, status=403)

    try:
        data = json.loads(request.body)
        document_ids = data.get('document_ids', [])

        if not document_ids:
            return JsonResponse({'success': False, 'error': 'Aucun document sélectionné'}, status=400)

        validated_count = 0
        errors = []

        for doc_id in document_ids:
            try:
                document = Document.objects.get(id=doc_id, status='extracted')
                document.status = 'validated'
                document.save()

                extraction_result = document.extraction_results.first()
                if extraction_result:
                    extraction_result.status = 'validated'
                    extraction_result.validated_by = request.user
                    extraction_result.validated_at = timezone.now()
                    extraction_result.save()

                validated_count += 1

                AuditLog.objects.create(
                    user=request.user,
                    document=document,
                    action='batch_validate',
                    description=f'Document validé en lot: {document.title}',
                    ip_address=request.META.get('REMOTE_ADDR')
                )

            except Document.DoesNotExist:
                errors.append(f'Document {doc_id} non trouvé ou statut invalide')
            except Exception as e:
                errors.append(f'Erreur document {doc_id}: {str(e)}')

        return JsonResponse({
            'success': True,
            'message': f'{validated_count} documents validés avec succès',
            'validated_count': validated_count,
            'errors': errors
        })

    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Données JSON invalides'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
