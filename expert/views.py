# expert/views.py
import os
import threading

from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.contrib import messages
from django.core.paginator import Paginator
from django.db import models
from django.db.models import Q, Count, Max
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.contrib.auth.decorators import user_passes_test
import uuid
from django.http import JsonResponse, HttpResponse
from client.products.models import Product, ProductSpecification, ManufacturingSite, ProductVariation
import json
import re

from .models import ExpertLog
from rawdocs.models import RawDocument, DocumentPage, Annotation, AnnotationType

from pymongo import MongoClient
from django.conf import settings

# Connexion MongoDB (ajuste ton URI si besoin)
MONGO_URI = getattr(settings, "MONGO_URI", "mongodb://localhost:27017/")
MONGO_DB = getattr(settings, "MONGO_DB", "annotations_db")
MONGO_COLLECTION = getattr(settings, "MONGO_COLLECTION", "documents")

mongo_client = MongoClient(MONGO_URI)
mongo_db = mongo_client[MONGO_DB]
mongo_collection = mongo_db[MONGO_COLLECTION]

# --- Helpers Date FR/EN ---
MONTH_MAP = {
    1: ["january", "jan", "jan.", "janvier", "janv", "janv.", "01"],
    2: ["february", "feb", "feb.", "février", "fevrier", "févr", "fevr", "févr.", "02"],
    3: ["march", "mar", "mar.", "mars", "03"],
    4: ["april", "apr", "apr.", "avril", "avr", "avr.", "04"],
    5: ["may", "mai", "05"],
    6: ["june", "jun", "jun.", "juin", "06"],
    7: ["july", "jul", "jul.", "juillet", "juil", "juil.", "07"],
    8: ["august", "aug", "aug.", "août", "aout", "08"],
    9: ["september", "sep", "sept", "sept.", "septembre", "09"],
    10: ["october", "oct", "oct.", "octobre", "10"],
    11: ["november", "nov", "nov.", "novembre", "11"],
    12: ["december", "dec", "dec.", "décembre", "decembre", "déc", "dec", "12"],
}

def _is_date_like(s: str) -> tuple[bool, int|None, str|None]:
    """Vrai si s contient 'mois + année' (FR/EN/abbr) ou formats 01/2013, 2013-01, 01-2013."""
    if not s: return (False, None, None)
    text = s.strip().lower()
    # mois + année (FR/EN, abbr, ponctuation optionnelle)
    for mnum, variants in MONTH_MAP.items():
        month_alt = "|".join([re.escape(v) for v in variants if not v.isdigit()])
        if re.search(rf"\b(?:{month_alt})\s*[,/-]?\s*\b(20\d{{2}}|19\d{{2}})\b", text, flags=re.IGNORECASE):
            year = re.search(r"(20\d{2}|19\d{2})", text).group(1)
            return (True, mnum, year)
    # numériques (01/2013, 2013/01, 2013-01)
    m = re.search(r"\b(0?[1-9]|1[0-2])\s*[/-]\s*(20\d{2}|19\d{2})\b", text)
    if m: return (True, int(m.group(1)), m.group(2))
    m = re.search(r"\b(20\d{2}|19\d{2})\s*[/-]\s*(0?[1-9]|1[0-2])\b", text)
    if m: return (True, int(m.group(2)), m.group(1))
    return (False, None, None)

def _date_regexes(month_num: int, year: str) -> list[re.Pattern]:
    """Construit des regex robustes pour retrouver 'Month YYYY' dans le texte source."""
    variants = MONTH_MAP.get(month_num, [])
    words = [v for v in variants if not v.isdigit()]
    mm = f"{month_num:02d}"
    pats = []
    # Month YYYY & YYYY Month
    if words:
        month_alt = "|".join([re.escape(w) for w in words])
        pats.append(re.compile(rf"\b(?:{month_alt})\s*[,/-]?\s*{re.escape(year)}\b", re.IGNORECASE))
        pats.append(re.compile(rf"\b{re.escape(year)}\s*[,/-]?\s*(?:{month_alt})\b", re.IGNORECASE))
    # 01/2013, 2013/01, 2013-01
    pats.append(re.compile(rf"\b{mm}\s*[/-]\s*{re.escape(year)}\b"))
    pats.append(re.compile(rf"\b{re.escape(year)}\s*[/-]\s*{mm}\b"))
    return pats

def find_date_span_in_text(text: str, query: str) -> tuple[int,int,str] | tuple[None,None,None]:
    """Retourne (start, end, match_text) pour la date 'query' dans text, sinon (None,None,None)."""
    ok, mnum, year = _is_date_like(query)
    if not ok: return (None, None, None)
    for rx in _date_regexes(mnum, year):
        m = rx.search(text or "")
        if m:
            return (m.start(), m.end(), m.group(0))
    return (None, None, None)

def find_any_month_year_for_year(text: str, year: str) -> tuple[int,int,str] | tuple[None,None,None]:
    """Si on n'a que '2013', essaie 'Jan 2013', 'janvier 2013', etc. dans le texte."""
    for mnum in range(1, 13):
        for rx in _date_regexes(mnum, year):
            m = rx.search(text or "")
            if m: return (m.start(), m.end(), m.group(0))
    return (None, None, None)

def is_expert(user):
    """Check if user is in Expert group"""
    return user.groups.filter(name="Expert").exists()


def expert_required(view_func):
    """Decorator to require expert role"""
    return user_passes_test(is_expert, login_url='rawdocs:login')(view_func)


@method_decorator(expert_required, name='dispatch')
class ExpertDashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'expert/dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        from django.db.models import Count, Q, F

        # Base queryset: documents prêts pour révision expert
        docs_qs = RawDocument.objects.filter(
            is_ready_for_expert=True
        ).select_related('owner').prefetch_related('pages__annotations') \
            .annotate(
            total_ann=Count('pages__annotations'),
            validated_ann=Count('pages__annotations', filter=Q(pages__annotations__validation_status='validated')),
            pending_ann=Count('pages__annotations', filter=Q(pages__annotations__validation_status='pending')),
            rejected_ann=Count('pages__annotations', filter=Q(pages__annotations__validation_status='rejected')),
            latest_annotation=Max('pages__annotations__created_at'),
        ).order_by('-expert_ready_at')

        total_documents = docs_qs.count()

        # Aggregates for annotations (limités aux docs prêts)
        ann_qs = Annotation.objects.filter(
        page__document__in=docs_qs,
        validation_status__in=['pending', 'validated', 'expert_created']
    )
        total_annotations = ann_qs.count()
        validated_annotations = ann_qs.filter(validation_status='validated').count()
        pending_annotations = ann_qs.filter(validation_status='pending').count()
        rejected_annotations = ann_qs.filter(validation_status='rejected').count()

        # Répartition des documents par statut de révision
        completed_reviews = docs_qs.filter(total_ann__gt=0, validated_ann=F('total_ann')).count()
        # Documents avec annotations mais non totalement validés (inclut potentiellement des rejetés)
        in_progress_reviews = docs_qs.filter(total_ann__gt=0).exclude(validated_ann=F('total_ann')).count()
        # Documents ayant au moins une annotation rejetée
        rejected_documents = docs_qs.filter(rejected_ann__gt=0).count()
        # Documents sans aucune annotation encore
        to_review_count = docs_qs.filter(total_ann=0).count()

        # KPI dérivés
        total_reviews = total_documents
        validation_rate = round((validated_annotations / total_annotations) * 100) if total_annotations > 0 else 0
        validated_documents_count = completed_reviews

        # Pagination des documents pour l'onglet "Documents"
        paginator = Paginator(docs_qs, 12)
        page_number = self.request.GET.get('page')
        recent_documents = paginator.get_page(page_number)

        # Completer quelques champs attendus par le template
        for doc in recent_documents:
            doc.annotator = doc.owner
            # updated_at basé sur la dernière annotation sinon fallback
            if getattr(doc, 'latest_annotation', None):
                doc.updated_at = doc.latest_annotation
            elif getattr(doc, 'expert_ready_at', None):
                doc.updated_at = doc.expert_ready_at
            else:
                doc.updated_at = doc.created_at
            # exposer total_annotations attendu par le template
            doc.total_annotations = getattr(doc, 'total_ann', 0)
            doc.pending_annotations = getattr(doc, 'pending_ann', 0)
            doc.validated_annotations = getattr(doc, 'validated_ann', 0)

        context.update({
            'ready_documents_count': total_documents,
            'pending_annotations': pending_annotations,
            'recent_documents': recent_documents,
            'total_documents': total_documents,
            'total_annotations': total_annotations,
            'completed_reviews': completed_reviews,
            'in_progress_reviews': in_progress_reviews,
            'rejected_documents': rejected_documents,
            'total_reviews': total_reviews,
            'validation_rate': validation_rate,
            'validated_documents_count': validated_documents_count,
            'to_review_count': to_review_count,
        })
        return context


@method_decorator(expert_required, name='dispatch')
class DocumentReviewView(LoginRequiredMixin, TemplateView):
    template_name = 'expert/document_review.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        document_id = self.kwargs['document_id']
        document = get_object_or_404(RawDocument, id=document_id)

        # Get current page number (default to 1)
        current_page_num = int(self.request.GET.get('page', 1))
        current_page = document.pages.filter(page_number=current_page_num).first()
        page_annotations = current_page.annotations.all().select_related('annotation_type').order_by('start_pos') if current_page else []


        if not current_page:
            current_page = document.pages.first()
            current_page_num = current_page.page_number if current_page else 1

        # Get page summary (generate if not exists)
        page_summary = ""
        if hasattr(current_page, 'annotations_summary') and current_page.annotations_summary:
            page_summary = current_page.annotations_summary
        else:
            # Get ALL annotations (not just validated ones) for expert review
            page_annotations = current_page.annotations.filter(
                validation_status__in=['pending', 'validated', 'expert_created', 'rejected']
            )
            if page_annotations.exists():
                # Build entities and generate summary
                entities = {}
                for annotation in page_annotations:
                    entity_type = annotation.annotation_type.display_name
                    if entity_type not in entities:
                        entities[entity_type] = []
                    entities[entity_type].append(annotation.selected_text)

                # Generate summary for this page
                from rawdocs.views import generate_entities_based_page_summary
                page_summary = generate_entities_based_page_summary(
                    entities=entities,
                    page_number=current_page.page_number,
                    document_title=document.title
                )

                # Save the generated summary to the page for future use
                current_page.annotations_summary = page_summary
                current_page.save(update_fields=['annotations_summary'])
            else:
                page_summary = f"Page {current_page_num}: Aucune annotation disponible pour générer un résumé."

        # Check if this is the last page
        is_last_page = current_page_num >= document.total_pages

        context.update({
            'document': document,
            'current_page': current_page,
            'current_page_num': current_page_num,
            'page_summary': page_summary,
            'is_last_page': is_last_page,
            'total_pages': document.total_pages,
            'page_annotations': page_annotations,
'total_page_annotations': page_annotations.count() if current_page else 0,
        })
        return context


@method_decorator(expert_required, name='dispatch')
class DocumentReviewListView(LoginRequiredMixin, TemplateView):
    template_name = 'expert/document_list.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        documents = RawDocument.objects.filter(
            is_ready_for_expert=True
        ).select_related('owner').prefetch_related('pages__annotations').annotate(
            annotation_count=Count('pages__annotations'),
        ).order_by('-expert_ready_at')

        # Enrich documents with additional info
        for doc in documents:
            doc.annotator = doc.owner  # Add annotator field for template consistency
            doc.pending_annotations = doc.pages.aggregate(
                total=Count('annotations', filter=models.Q(annotations__validation_status='pending'))
            )['total'] or 0
            doc.validated_annotations = doc.pages.aggregate(
                total=Count('annotations', filter=models.Q(annotations__validation_status='validated'))
            )['total'] or 0

        paginator = Paginator(documents, 12)
        page_number = self.request.GET.get('page')
        page_obj = paginator.get_page(page_number)

        context['page_obj'] = page_obj
        return context


@expert_required
@csrf_exempt
def validate_annotation_ajax(request, annotation_id):
    """
    Valide / rejette une annotation + régénère résumé page + déclenche régénération globale.
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'})

    try:
        data = json.loads(request.body)
        action = data.get('action')
        annotation = get_object_or_404(Annotation, id=annotation_id)

        if action == 'validate':
            annotation.validation_status = 'validated'
        elif action == 'reject':
            annotation.validation_status = 'rejected'
        else:
            return JsonResponse({'success': False, 'error': 'invalid action'})

        annotation.validated_by = request.user
        annotation.validated_at = timezone.now()
        annotation.save()

        # Recalcule résumé de la page
        try:
            new_page_summary, _ = build_page_summary_and_json(annotation.page, request.user)
        except Exception as e:
            print(f"⚠️ Erreur régénération résumé page après {action}: {e}")
            new_page_summary = None

        # Régénération globale (async)
        try:
            thread = threading.Thread(
                target=trigger_summary_regeneration_safe,
                args=(annotation.page.document, request.user, 3)
            )
            thread.daemon = True
            thread.start()
        except Exception as e:
            print(f"⚠️ Erreur déclenchement régénération après {action}: {e}")

        return JsonResponse({
            'success': True,
            'message': 'Annotation validée' if action == 'validate' else 'Annotation rejetée',
            'status': 'validated' if action == 'validate' else 'rejected',
            'auto_summary_triggered': True,
            'page_summary': new_page_summary
        })

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@expert_required
@csrf_exempt
def create_annotation_ajax(request):
    """
    Création d'une annotation (pré-validée) + MAJ JSON + régénération résumé page + retour résumé.
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'})

    try:
        data = json.loads(request.body)
        page_id = data.get('page_id')
        text = (data.get('text') or '').strip()
        entity_type_name = (data.get('entity_type') or '').strip()
        if not entity_type_name:
            return JsonResponse({'success': False, 'error': 'entity_type is required'})

        page = get_object_or_404(DocumentPage, id=page_id)

        annotation_type, _ = AnnotationType.objects.get_or_create(
            name=entity_type_name,
            defaults={
                'display_name': entity_type_name.replace('_', ' ').title(),
                'color': '#3b82f6',
                'description': f"Expert created type: {entity_type_name}"
            }
        )

        annotation = Annotation.objects.create(
            page=page,
            selected_text=text,
            annotation_type=annotation_type,
            start_pos=int(data.get('start_pos', 0) or 0),
            end_pos=int(data.get('end_pos', len(text) or 0) or 0),
            validation_status='expert_created',
            validated_by=request.user,
            validated_at=timezone.now(),
            created_by=request.user,
            source='expert'
        )

        # MAJ JSON + résumé page + doc
        try:
            build_page_summary_and_json(page, request.user)

            all_annotations = Annotation.objects.filter(
                page__document=page.document,
                validation_status__in=['validated', 'expert_created']
            ).select_related('annotation_type', 'page').order_by('page__page_number', 'start_pos')

            from rawdocs.views import _build_entities_map
            document_entities = _build_entities_map(all_annotations, use_display_name=True)

            document_json = {
                'document': {
                    'id': str(page.document.id),
                    'title': page.document.title,
                    'doc_type': getattr(page.document, 'doc_type', None),
                    'source': getattr(page.document, 'source', None),
                    'total_pages': page.document.total_pages,
                    'total_annotations': all_annotations.count(),
                },
                'entities': document_entities,
                'generated_at': datetime.utcnow().isoformat() + 'Z',
            }
            page.document.global_annotations_json = document_json
            page.document.save(update_fields=['global_annotations_json'])

            try:
                trigger_summary_regeneration_safe(page.document, request.user, 3)
            except Exception as e:
                print(f"⚠️ Erreur déclenchement régénération document: {e}")

        except Exception as e:
            print(f"❌ Erreur MAJ JSON/summary (create): {e}")

        return JsonResponse({
            'success': True,
            'annotation_id': annotation.id,
            'message': 'Annotation créée avec succès',
            'page_summary': page.annotations_summary,
            'auto_summary_triggered': True
        })

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})



@expert_required
@csrf_exempt
def modify_annotation_ajax(request, annotation_id):
    """
    Modification d'une annotation (→ validée) + MAJ JSON + régénération résumé page + retour résumé.
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'})

    try:
        data = json.loads(request.body)
        annotation = get_object_or_404(Annotation, id=annotation_id)

        new_text = (data.get('text') or '').strip()
        new_entity_type_name = (data.get('entity_type') or '').strip()

        annotation_type, _ = AnnotationType.objects.get_or_create(
            name=new_entity_type_name,
            defaults={
                'display_name': new_entity_type_name.replace('_', ' ').title(),
                'color': '#3b82f6',
                'description': f"Expert type: {new_entity_type_name}"
            }
        )

        annotation.selected_text = new_text
        annotation.annotation_type = annotation_type
        annotation.validation_status = 'validated'
        annotation.validated_by = request.user
        annotation.validated_at = timezone.now()
        annotation.save()

        page = annotation.page

        # MAJ JSON + résumé page + doc
        try:
            build_page_summary_and_json(page, request.user)

            all_annotations = Annotation.objects.filter(
                page__document=page.document,
                validation_status__in=['validated', 'expert_created']
            ).select_related('annotation_type', 'page').order_by('page__page_number', 'start_pos')

            from rawdocs.views import _build_entities_map
            document_entities = _build_entities_map(all_annotations, use_display_name=True)

            document_json = {
                'document': {
                    'id': str(page.document.id),
                    'title': page.document.title,
                    'doc_type': getattr(page.document, 'doc_type', None),
                    'source': getattr(page.document, 'source', None),
                    'total_pages': page.document.total_pages,
                    'total_annotations': all_annotations.count(),
                },
                'entities': document_entities,
                'generated_at': datetime.utcnow().isoformat() + 'Z',
            }
            page.document.global_annotations_json = document_json
            page.document.save(update_fields=['global_annotations_json'])

            try:
                trigger_summary_regeneration_safe(page.document, request.user, 3)
            except Exception as e:
                print(f"⚠️ Erreur déclenchement régénération document (modify): {e}")

        except Exception as e:
            print(f"❌ Erreur MAJ JSON/summary (modify): {e}")

        return JsonResponse({
            'success': True,
            'message': 'Annotation modifiée, validée et JSON mis à jour',
            'page_summary': page.annotations_summary,
            'auto_summary_triggered': True
        })

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@expert_required
@csrf_exempt
def delete_annotation_ajax(request, annotation_id):
    """Delete an annotation"""
    if request.method == 'POST':
        try:
            annotation = get_object_or_404(Annotation, id=annotation_id)

            # LOG ACTION BEFORE DELETION
            log_expert_action(
                user=request.user,
                action='annotation_deleted',
                annotation=annotation,
                reason=f"Manual deletion by expert. Annotation was: {annotation.validation_status}"
            )

            annotation.delete()

            return JsonResponse({
                'success': True,
                'message': 'Annotation supprimée'
            })

        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})

    return JsonResponse({'success': False, 'error': 'Method not allowed'})


@expert_required
@csrf_exempt
def undo_validation_ajax(request, annotation_id):
    """
    Annuler la validation → met l'annotation en 'pending' et régénère le résumé de la page.
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'})

    try:
        annotation = get_object_or_404(Annotation, id=annotation_id)
        annotation.validation_status = 'pending'
        annotation.validated_by = None
        annotation.validated_at = None
        annotation.save()

        try:
            new_page_summary, _ = build_page_summary_and_json(annotation.page, request.user)
        except Exception as e:
            print(f"⚠️ Erreur régénération résumé page (undo): {e}")
            new_page_summary = None

        try:
            trigger_summary_regeneration_safe(annotation.page.document, request.user, 3)
        except Exception as e:
            print(f"⚠️ Erreur déclenchement régénération (undo): {e}")

        return JsonResponse({'success': True, 'message': 'Validation annulée', 'page_summary': new_page_summary})

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

def log_expert_action(user, action, annotation, document_id=None, document_title=None,
                      old_text=None, new_text=None, old_entity_type=None, new_entity_type=None,
                      reason=None, session_id=None):
    """Helper to log expert actions"""
    if not session_id:
        session_id = str(uuid.uuid4())[:8]

    # Get annotation info
    if annotation:
        annotation_text = getattr(annotation, 'selected_text', '')
        entity_type = getattr(annotation.annotation_type, 'name', '') if hasattr(annotation, 'annotation_type') else ''
        page = getattr(annotation, 'page', None)
        original_annotator = getattr(annotation.created_by, 'username', 'Unknown') if hasattr(annotation,
                                                                                              'created_by') else 'Unknown'

        if page:
            page_id = page.id
            page_number = page.page_number
            page_text = page.cleaned_text
            document_id = page.document.id
            document_title = page.document.file.name
        else:
            page_id = page_number = None
            page_text = ''
    else:
        annotation_text = entity_type = original_annotator = ''
        page_id = page_number = None
        page_text = ''

    ExpertLog.objects.create(
        expert=user,
        session_id=session_id,
        document_id=document_id or 0,
        document_title=document_title or '',
        page_id=page_id,
        page_number=page_number,
        page_text=page_text,
        action=action,
        annotation_id=getattr(annotation, 'id', None),
        annotation_text=annotation_text,
        annotation_entity_type=entity_type,
        annotation_start_position=getattr(annotation, 'start_pos', None),
        annotation_end_position=getattr(annotation, 'end_pos', None),
        old_text=old_text or '',
        new_text=new_text or '',
        old_entity_type=old_entity_type or '',
        new_entity_type=new_entity_type or '',
        original_annotator=original_annotator,
        validation_status_before=getattr(annotation, 'validation_status', '') if annotation else '',
        validation_status_after='',
        reason=reason or '',
    )
    return session_id


@expert_required
@csrf_exempt
def create_annotation_type_ajax(request):
    """AJAX endpoint for experts to create new annotation types"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            display_name = data.get('display_name', '').strip()
            name = data.get('name', '').strip()

            if not display_name:
                return JsonResponse({'success': False, 'error': 'Display name is required'})

            # Auto-generate name if not provided
            if not name:
                name = display_name.lower().replace(' ', '_').replace('-', '_')
                # Remove any non-alphanumeric characters except underscores
                name = re.sub(r'[^\w]', '', name)

            # Check if annotation type already exists
            if AnnotationType.objects.filter(name=name).exists():
                return JsonResponse({'success': False, 'error': f'Annotation type "{name}" already exists'})

            # Create new annotation type
            annotation_type = AnnotationType.objects.create(
                name=name,
                display_name=display_name,
                color='#6f42c1',  # Purple color for expert-created types
                description=f"Expert-created annotation type: {display_name}"
            )

            # LOG ACTION
            log_expert_action(
                user=request.user,
                action='annotation_type_created',
                annotation=None,
                reason=f"Created new annotation type: {display_name} ({name})"
            )

            return JsonResponse({
                'success': True,
                'message': f'Annotation type "{display_name}" created successfully',
                'annotation_type': {
                    'id': annotation_type.id,
                    'name': annotation_type.name,
                    'display_name': annotation_type.display_name,
                    'color': annotation_type.color
                }
            })

        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})

    return JsonResponse({'success': False, 'error': 'Method not allowed'})


@expert_required
@csrf_exempt
def delete_annotation_type_ajax(request):
    """AJAX endpoint for experts to delete annotation types"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            annotation_type_name = data.get('annotation_type_name', '').strip()

            if not annotation_type_name:
                return JsonResponse({'success': False, 'error': 'Annotation type name is required'})

            # Check if annotation type exists
            try:
                annotation_type = AnnotationType.objects.get(name=annotation_type_name)
            except AnnotationType.DoesNotExist:
                return JsonResponse({'success': False, 'error': f'Annotation type "{annotation_type_name}" not found'})

            # Check if this annotation type is being used
            annotations_count = Annotation.objects.filter(
                annotation_type=annotation_type
            ).count()

            if annotations_count > 0:
                return JsonResponse({
                    'success': False,
                    'error': f'Cannot delete annotation type "{annotation_type.display_name}" as it is used by {annotations_count} annotation(s)'
                })

            # Store info before deletion for logging
            display_name = annotation_type.display_name

            # Delete the annotation type
            annotation_type.delete()

            # LOG ACTION
            log_expert_action(
                user=request.user,
                action='annotation_type_deleted',
                annotation=None,
                reason=f"Deleted annotation type: {display_name} ({annotation_type_name})"
            )

            return JsonResponse({
                'success': True,
                'message': f'Annotation type "{display_name}" deleted successfully'
            })

        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})

    return JsonResponse({'success': False, 'error': 'Method not allowed'})


def create_product_from_annotations(document):
    """Create a product with all expert annotations stored"""
    validated_annotations = Annotation.objects.filter(
        page__document=document,
        validation_status__in=['validated', 'expert_created']
    )

    # Group annotations by type
    annotations_by_type = {}
    for annotation in validated_annotations:
        annotation_type = annotation.annotation_type.name.lower()
        if annotation_type not in annotations_by_type:
            annotations_by_type[annotation_type] = []
        annotations_by_type[annotation_type].append(annotation.selected_text.strip())

    # Core product fields (these go into regular product fields)
    core_fields = ['product', 'dosage', 'substance_active', 'site', 'adresse', 'address', 'pays', 'country']

    # Additional annotations (these go into JSON field)
    additional_annotations = {}
    for annotation_type, values in annotations_by_type.items():
        if annotation_type not in core_fields:
            # Store additional annotations like batch_size, shelf_life, etc.
            additional_annotations[annotation_type] = values[0] if len(values) == 1 else values

    # Extract core product information
    product_name = annotations_by_type.get('product', [''])[0] or 'Unknown Product'

    product_data = {
        'name': product_name,
        'dosage': annotations_by_type.get('dosage', [''])[0] or 'N/A',
        'active_ingredient': annotations_by_type.get('substance_active', ['N/A'])[0],
        'form': 'Comprimé',
        'therapeutic_area': 'N/A',
        'status': 'commercialise',
        'additional_annotations': additional_annotations
    }

    # Process sites data - match each site with address and country
    sites = annotations_by_type.get('site', [])
    addresses = annotations_by_type.get('adresse', []) + annotations_by_type.get('address', [])
    countries = annotations_by_type.get('pays', []) + annotations_by_type.get('country', [])

    sites_data = []
    max_sites = max(len(sites), len(addresses), len(countries))

    for i in range(max_sites):
        site_name = sites[i] if i < len(sites) else f'Site {i + 1}'
        address = addresses[i] if i < len(addresses) else 'N/A'
        country = countries[i] if i < len(countries) else 'N/A'

        sites_data.append({
            'site_name': site_name,
            'country': country,
            'city': address,
            'gmp_certified': False
        })

    print(f"DEBUG: Processing product '{product_name}' with {len(sites_data)} sites")
    print(f"DEBUG: Additional annotations stored: {additional_annotations}")

    # Check if product exists
    existing_product = Product.objects.filter(name=product_name).first()

    if existing_product and product_name != 'Unknown Product':
        return update_existing_product_with_variations(existing_product, sites_data, document, additional_annotations)
    else:
        return create_new_product(product_data, sites_data, document)


def debug_product_annotations():
    """Debug function to check if products have additional annotations"""
    from client.products.models import Product

    print("🔍 DEBUGGING PRODUCT ADDITIONAL ANNOTATIONS")
    print("=" * 50)

    for product in Product.objects.all():
        print(f"📦 Product: {product.name}")
        if hasattr(product, 'additional_annotations'):
            print(f"   additional_annotations: {product.additional_annotations}")
        else:
            print(f"   ❌ No additional_annotations field")
        print()


def create_new_product(product_data, sites_data, document):
    """Create a completely new product with additional annotations"""
    if product_data['name'] and product_data['name'] != 'Unknown Product':
        try:
            product = Product.objects.create(
                name=product_data['name'],
                active_ingredient=product_data['active_ingredient'],
                dosage=product_data['dosage'],
                form=product_data['form'],
                therapeutic_area=product_data['therapeutic_area'],
                status=product_data['status'],
                source_document=document
            )

            # Try to save additional annotations after creation
            try:
                if 'additional_annotations' in product_data:
                    product.additional_annotations = product_data['additional_annotations']
                    product.save()
                    print(f"✅ Saved additional annotations: {product_data['additional_annotations']}")
            except Exception as e:
                print(f"⚠️ Additional annotations field not ready yet: {e}")

            # Create manufacturing sites
            for site_data in sites_data:
                ManufacturingSite.objects.create(
                    product=product,
                    site_name=site_data['site_name'],
                    country=site_data['country'],
                    city=site_data['city'],
                    gmp_certified=site_data['gmp_certified']
                )
                print(f"DEBUG: Created site: {site_data['site_name']}")

            print(f"DEBUG: Created product with additional annotations: {product_data['additional_annotations']}")
            return product

        except Exception as e:
            print(f"Error creating product: {e}")
            return None

    return None


def update_existing_product_with_variations(existing_product, new_sites_data, document, additional_annotations=None):
    """Compare existing product with new data and create variations"""
    # Get existing sites
    existing_sites = list(ManufacturingSite.objects.filter(product=existing_product).values(
        'site_name', 'country', 'city'
    ))

    print(f"DEBUG: Existing sites: {existing_sites}")
    print(f"DEBUG: New sites: {new_sites_data}")

    # Compare sites
    added_sites = []
    removed_sites = []

    # Find new sites
    for new_site in new_sites_data:
        site_exists = any(
            existing_site['site_name'].strip().lower() == new_site['site_name'].strip().lower() and
            existing_site['country'].strip().lower() == new_site['country'].strip().lower()
            for existing_site in existing_sites
        )
        if not site_exists:
            added_sites.append(new_site)

    # Find removed sites
    for existing_site in existing_sites:
        site_still_exists = any(
            new_site['site_name'].strip().lower() == existing_site['site_name'].strip().lower() and
            new_site['country'].strip().lower() == existing_site['country'].strip().lower()
            for new_site in new_sites_data
        )
        if not site_still_exists:
            removed_sites.append(existing_site)

    print(f"DEBUG: Sites to add: {added_sites}")
    print(f"DEBUG: Sites to remove: {removed_sites}")

    # Create variations for changes
    variations_created = []

    # Add variations for new sites
    for site in added_sites:
        variation = ProductVariation.objects.create(
            product=existing_product,
            variation_type='type_ib',  # Site addition is usually Type IB
            title=f"Ajout de site - {site['site_name']}",
            description=f"Ajout du site de fabrication: {site['site_name']} ({site['city']}, {site['country']})",
            submission_date=timezone.now().date(),
            status='soumis'
        )
        variations_created.append(variation)

        # Actually add the site to the product
        ManufacturingSite.objects.create(
            product=existing_product,
            site_name=site['site_name'],
            country=site['country'],
            city=site['city'],
            gmp_certified=site.get('gmp_certified', False)
        )
        print(f"DEBUG: Added variation and site: {site['site_name']}")

    # Add variations for removed sites
    for site in removed_sites:
        variation = ProductVariation.objects.create(
            product=existing_product,
            variation_type='type_ib',
            title=f"Suppression de site - {site['site_name']}",
            description=f"Suppression du site de fabrication: {site['site_name']} ({site['city']}, {site['country']})",
            submission_date=timezone.now().date(),
            status='soumis'
        )
        variations_created.append(variation)

        # Actually remove the site from the product
        ManufacturingSite.objects.filter(
            product=existing_product,
            site_name=site['site_name'],
            country=site['country']
        ).delete()
        print(f"DEBUG: Added variation and removed site: {site['site_name']}")

    # Update additional annotations if provided
    if additional_annotations:
        try:
            existing_product.additional_annotations = additional_annotations
            existing_product.save()
            print(f"✅ Updated additional annotations: {additional_annotations}")
        except Exception as e:
            print(f"⚠️ Could not update additional annotations: {e}")

    print(f"🎯 Updated existing product '{existing_product.name}' with {len(variations_created)} variations")

    return existing_product


# expert/views.py - Modifier la fonction validate_document


@expert_required
def validate_document(request, document_id):
    """Validate entire document and create product if it's a manufacturer document"""
    if request.method == 'POST':
        try:
            document = get_object_or_404(RawDocument, id=document_id)

            document.is_expert_validated = True
            document.expert_validated_at = timezone.now()
            document.save(update_fields=['is_expert_validated', 'expert_validated_at'])

            # Debug: Check document type
            print(f"DEBUG: Document type = '{document.doc_type}'")

            # Create or update product from annotations
            product = create_product_from_annotations(document)

            # Fonction helper pour gérer les dates
            def safe_isoformat(date_value):
                if date_value is None:
                    return None
                if isinstance(date_value, str):
                    return date_value
                if hasattr(date_value, 'isoformat'):
                    return date_value.isoformat()
                return str(date_value)

            # Sauvegarder dans MongoDB avec toutes les métadonnées lors de la validation
            from rawdocs.models import CustomFieldValue

            # Construire les métadonnées complètes
            metadata = {
                'title': document.title,
                'doc_type': document.doc_type,
                'publication_date': safe_isoformat(document.publication_date),
                'version': document.version,
                'source': document.source,
                'context': document.context,
                'country': document.country,
                'language': document.language,
                'url_source': document.url_source,
                'url': document.url,
                'created_at': safe_isoformat(document.created_at),
                'validated_at': timezone.now().isoformat(),
                'validated_by': request.user.username,
                'owner': document.owner.username if document.owner else None,
                'total_pages': document.total_pages,
                'file_name': os.path.basename(document.file.name) if document.file else None,
            }

            # Ajouter les champs personnalisés
            custom_fields = {}
            for custom_value in CustomFieldValue.objects.filter(document=document):
                custom_fields[custom_value.field.name] = custom_value.value

            if custom_fields:
                metadata['custom_fields'] = custom_fields

            # Récupérer les entités du JSON global si elles existent
            entities = {}
            if hasattr(document, 'global_annotations_json') and document.global_annotations_json:
                entities = document.global_annotations_json.get('entities', {})

            # Sauvegarder dans MongoDB
            mongo_collection.update_one(
                {"document_id": str(document.id)},
                {
                    "$set": {
                        "document_id": str(document.id),
                        "title": document.title,
                        "metadata": metadata,
                        "entities": entities,
                        "validated": True,
                        "validated_at": timezone.now().isoformat(),
                        "validated_by": request.user.username,
                        "product_created": product.name if product else None,
                        "updated_at": timezone.now().isoformat()
                    }
                },
                upsert=True
            )

            # Préparer le message à renvoyer (et conserver messages Django pour fallback)
            response_message = ''
            if product:
                debug_product_annotations()
                variations_today = ProductVariation.objects.filter(
                    product=product,
                    submission_date=timezone.now().date()
                ).count()

                if variations_today > 0:
                    response_message = (
                        f'🎉 Document validé avec succès! Le produit "{product.name}" a été mis à jour avec {variations_today} nouvelle(s) variation(s). '
                        f'Consultez l\'onglet "Variations" pour voir les changements.'
                    )
                    messages.success(request, response_message)
                else:
                    response_message = (
                        f'🎉 Document validé avec succès! Le produit "{product.name}" a été créé dans le module client.'
                    )
                    messages.success(request, response_message)
            else:
                debug_info = debug_annotations_for_product(document)
                response_message = (
                    f'⚠️ Document validé mais aucun produit créé. Détails: {debug_info}'
                )
                messages.warning(request, response_message)

            # Si appel AJAX, renvoyer JSON au lieu de rediriger
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': True, 'message': response_message})

            return redirect('expert:dashboard')

        except Exception as e:
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'error': str(e)}, status=500)
            messages.error(request, f'❌ Erreur lors de la validation: {str(e)}')
            return redirect('expert:review_document', document_id=document_id)

    return redirect('expert:review_document', document_id=document_id)


def debug_annotations_for_product(document):
    """Debug function to show what annotations are available"""
    validated_annotations = Annotation.objects.filter(
        page__document=document,
        validation_status__in=['validated', 'expert_created']
    )

    debug_info = []
    debug_info.append(f"Doc type: '{document.doc_type}'")
    debug_info.append(f"Total annotations: {validated_annotations.count()}")

    # Check what annotation types we have
    annotation_types = {}
    for annotation in validated_annotations:
        annotation_type = annotation.annotation_type.name.lower()
        if annotation_type not in annotation_types:
            annotation_types[annotation_type] = []
        annotation_types[annotation_type].append(annotation.selected_text)

    debug_info.append(f"Available types: {list(annotation_types.keys())}")

    # Check for required fields
    has_product = 'product' in annotation_types
    has_dosage = 'dosage' in annotation_types
    has_site = 'site' in annotation_types

    debug_info.append(f"Has product: {has_product}")
    debug_info.append(f"Has dosage: {has_dosage}")
    debug_info.append(f"Has site: {has_site}")

    return " | ".join(debug_info)


@expert_required
def view_original_document(request, document_id):
    """View the original document PDF"""
    document = get_object_or_404(RawDocument, id=document_id)

    # Check if document file exists
    if document.file:
        try:
            # Serve the PDF file directly in browser
            response = HttpResponse(document.file.read(), content_type='application/pdf')
            response['Content-Disposition'] = f'inline; filename="{document.file.name}"'
            return response
        except:
            # If file doesn't exist, show error
            return HttpResponse(
                "<html><body><h2>Erreur</h2>"
                "<p>Le fichier PDF n'a pas pu être chargé.</p>"
                "<script>window.close();</script></body></html>"
            )
    else:
        return HttpResponse(
            "<html><body><h2>Aucun fichier disponible</h2>"
            "<p>Ce document n'a pas de fichier PDF associé.</p>"
            "<script>window.close();</script></body></html>"
        )


@expert_required
@csrf_exempt
def save_page_json(request, page_id):
    """Sauvegarde du JSON modifié d'une page"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        page = get_object_or_404(DocumentPage, id=page_id)
        data = json.loads(request.body)
        json_content = data.get('json_content')

        if not json_content:
            return JsonResponse({'error': 'JSON content is required'}, status=400)

        # Valider que le JSON est bien formaté
        try:
            parsed_json = json.loads(json_content)
        except json.JSONDecodeError as e:
            return JsonResponse({'error': f'Invalid JSON format: {str(e)}'}, status=400)

        # Sauvegarder le nouveau JSON
        page.annotations_json = parsed_json
        page.annotations_summary_generated_at = timezone.now()
        page.save(update_fields=['annotations_json', 'annotations_summary_generated_at'])

        # Mise à jour du JSON global du document
        document = page.document
        all_annotations = Annotation.objects.filter(
            page__document=document
        ).select_related('annotation_type', 'page').order_by('page__page_number', 'start_pos')

        from rawdocs.views import _build_entities_map
        document_entities = _build_entities_map(all_annotations, use_display_name=True)

        document_json = {
            'document': {
                'id': str(document.id),
                'title': document.title,
                'doc_type': getattr(document, 'doc_type', None),
                'source': getattr(document, 'source', None),
                'total_pages': document.total_pages,
                'total_annotations': all_annotations.count(),
            },
            'entities': document_entities,
            'generated_at': datetime.utcnow().isoformat() + 'Z',
        }

        document.global_annotations_json = document_json
        document.save(update_fields=['global_annotations_json'])

        # LOG ACTION
        log_expert_action(
            user=request.user,
            action='page_json_edited',
            annotation=None,
            document_id=document.id,
            document_title=document.title,
            reason=f"Page {page.page_number} JSON manually edited by expert"
        )

        return JsonResponse({
            'success': True,
            'message': 'JSON sauvegardé avec succès'
        })

    except Exception as e:
        print(f"❌ Erreur lors de la sauvegarde du JSON de la page: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)


# expert/views.py - Modifier uniquement la fonction save_document_json

# expert/views.py - Corriger la fonction save_document_json

@expert_required
@csrf_exempt
#################
# À ajouter dans expert/views.py

# @expert_required
# @csrf_exempt
# def save_summary_changes(request, doc_id):
#     if request.method != 'POST':
#         return JsonResponse({'error': 'POST required'}, status=405)
#     try:
#         document = get_object_or_404(RawDocument, id=doc_id)
#         payload = json.loads(request.body)
#         new_summary = (payload.get('summary_content') or '').strip()
#         if not new_summary:
#             return JsonResponse({'error': 'Summary cannot be empty'}, status=400)
#
#         old_summary = document.global_annotations_summary or ""
#
#         # 2) Préparer/initialiser le JSON global et les entités si manquants
#         current_json = document.global_annotations_json or {}
#         current_json.setdefault('document', {})
#         current_entities = current_json.get('entities', {}) or {}
#
#         if not current_entities:
#             # Tenter de construire les entités depuis les annotations du document
#             try:
#                 from rawdocs.views import _build_entities_map  # utilitaire existant
#                 all_annotations = Annotation.objects.filter(page__document=document).select_related('annotation_type')
#                 built = _build_entities_map(all_annotations, use_display_name=True) or {}
#                 current_entities = built
#             except Exception:
#                 # Fallback minimal: construire une map simple type -> valeurs depuis les annotations
#                 built = {}
#                 anns = Annotation.objects.filter(page__document=document).select_related('annotation_type')
#                 for ann in anns:
#                     key = getattr(ann.annotation_type, 'display_name', None) or getattr(ann.annotation_type, 'name',
#                                                                                         None) or 'Unknown'
#                     built.setdefault(key, [])
#                     val = (ann.selected_text or '').strip()
#                     if val and val not in built[key]:
#                         built[key].append(val)
#                 current_entities = built
#
#             # Si toujours vide (ex: document sans annotations), initialiser des clés par défaut
#             if not current_entities:
#                 default_keys = [
#                     'Invented Name',
#                     'Strength',
#                     'Pharmaceutical Form',
#                     'Route Of Administration',
#                     'Immediate Packaging',
#                     'Pack Size',
#                     'Ma Number',
#                 ]
#                 current_entities = {k: [] for k in default_keys}
#
#             current_json['entities'] = current_entities
#
#         allowed_keys = list(current_entities.keys())
#
#         # 1) Extraire les entités du nouveau résumé:
#         #    a) via libellés existants (Clé: valeur)
#         extracted_by_keys = extract_by_allowed_keys(new_summary, allowed_keys)
#         #    b) via texte libre (phrases), en détectant entité/valeur
#         free_extracted = extract_entities_from_text(new_summary) or {}
#         #       b2) enrichissement par détections ciblées (route, packaging, pack size, forme)
#         try:
#             # Route of Administration
#             route_vals = set()
#             for m in re.finditer(
#                     r"(?i)(?:par\s+voie\s+|voie\s+)(orale|intraveineuse|intramusculaire|sous\s*cutan[eé]e|subcutan[eé]e|nasale|topique|cutan[eé]e|rectale|inhalation)",
#                     new_summary):
#                 route_vals.add(m.group(1))
#             for m in re.finditer(
#                     r"(?i)\b(oral|intravenous|intramuscular|subcutaneous|topical|nasal|rectal|inhalation|iv|im|sc)\b",
#                     new_summary):
#                 route_vals.add(m.group(1))
#             if route_vals:
#                 free_extracted.setdefault('Route Of Administration', []).extend(sorted(route_vals))
#
#             # Immediate Packaging
#             packaging_vals = set()
#             for m in re.finditer(
#                     r"(?i)\b(blisters?|blister|flacons?|bouteilles?|bottles?|sachets?|ampoules?|seringues?\s*pr[ée]remplies?)\b",
#                     new_summary):
#                 packaging_vals.add(m.group(0))
#             if packaging_vals:
#                 free_extracted.setdefault('Immediate Packaging', []).extend(sorted(packaging_vals))
#
#             # Pack Size (ex: 20 comprimés, 100 ml, 6 sachets)
#             pack_vals = set()
#             for m in re.finditer(
#                     r"(?i)\b([0-9]{1,4}\s*(?:comprim[ée]s?|g[ée]lules?|capsules?|sachets?|ml|ampoules?|unit[eé]s?))\b",
#                     new_summary):
#                 pack_vals.add(m.group(1))
#             if pack_vals:
#                 free_extracted.setdefault('Pack Size', []).extend(sorted(pack_vals))
#
#             # Pharmaceutical Form
#             form_vals = set()
#             for m in re.finditer(
#                     r"(?i)\b(comprim[ée]s?|g[ée]lules?|capsules?|sirop|solution|suspension|poudre|injectable|tablet[s]?)\b",
#                     new_summary):
#                 form_vals.add(m.group(0))
#             if form_vals:
#                 free_extracted.setdefault('Pharmaceutical Form', []).extend(sorted(form_vals))
#         except Exception:
#             pass
#
#         #    c) Fusionner en ne gardant que les clés existantes (mapping canonique)
#         extracted_entities: dict[str, list[str]] = {}
#         for k, vals in (extracted_by_keys or {}).items():
#             extracted_entities.setdefault(k, []).extend(vals or [])
#         for raw_k, vals in (free_extracted or {}).items():
#             canon = _canonical_key(raw_k, allowed_keys)
#             if not canon:
#                 continue
#             extracted_entities.setdefault(canon, []).extend(vals or [])
#         # Déduplication + nettoyage par type
#         for k, vals in list(extracted_entities.items()):
#             extracted_entities[k] = _clean_values_for_type(k, vals or [])
#         print(f"Entités extraites (fusion): {extracted_entities}")
#
#         # 3) Mise à jour fine par valeurs (ajouts/suppressions basées sur le résumé)
#         updated_entities = current_entities.copy()
#         changes_made = []
#         entities_added: dict[str, list[str]] = {}
#         entities_removed: dict[str, list[str]] = {}
#         changed_keys: list[str] = []
#
#         # Normaliser les clés permises (mapping insensible à la casse)
#         key_map = {k.lower(): k for k in allowed_keys}
#
#         # Extraire entités de l'ancien résumé pour détecter suppressions (toutes clés)
#         old_extracted = extract_by_allowed_keys(old_summary or "", allowed_keys)
#
#         def _norm_val(s: str) -> str:
#             return re.sub(r'\s+', ' ', (s or '').strip()).lower()
#
#         for lower_k, canon_k in key_map.items():
#             # valeurs existantes
#             existing_vals = list(updated_entities.get(canon_k, []) or [])
#             existing_norms = {_norm_val(v) for v in existing_vals}
#
#             # valeurs extraites anciennes et nouvelles pour cette clé
#             old_vals_ex = []
#             for etype, vals in (old_extracted or {}).items():
#                 if (etype or '').lower() == lower_k:
#                     old_vals_ex = vals or []
#                     break
#             new_vals_ex = []
#             for etype, vals in (extracted_entities or {}).items():
#                 if (etype or '').lower() == lower_k:
#                     new_vals_ex = vals or []
#                     break
#
#             cleaned_old = _clean_values_for_type(canon_k, old_vals_ex)
#             cleaned_new = _clean_values_for_type(canon_k, new_vals_ex)
#
#             old_norms = {_norm_val(v) for v in cleaned_old}
#             new_norms = {_norm_val(v) for v in cleaned_new}
#
#             # suppressions: présentes avant, absentes maintenant
#             to_remove = old_norms - new_norms
#             # ajouts: présentes dans le nouveau résumé, pas déjà existantes
#             to_add = [v for v in cleaned_new if _norm_val(v) not in existing_norms]
#
#             # appliquer suppressions
#             kept = [v for v in existing_vals if _norm_val(v) not in to_remove]
#             removed_list = [v for v in existing_vals if _norm_val(v) in to_remove]
#             # appliquer ajouts
#             added_list = []
#             for v in to_add:
#                 nv = _norm_val(v)
#                 if nv not in {_norm_val(x) for x in kept}:
#                     kept.append(v)
#                     added_list.append(v)
#
#             if kept != existing_vals:
#                 change_msg = f"{canon_k}:"
#                 if removed_list:
#                     change_msg += f" -{removed_list}"
#                     entities_removed[canon_k] = removed_list
#                 if added_list:
#                     change_msg += f" +{added_list}"
#                     entities_added[canon_k] = added_list
#                 changes_made.append(change_msg)
#                 updated_entities[canon_k] = kept
#                 changed_keys.append(canon_k)
#
#         # 4) Sauvegarder le résumé
#         document.global_annotations_summary = new_summary
#         document.global_annotations_summary_generated_at = timezone.now()
#
#         # 5) Mettre à jour le JSON
#         current_json['entities'] = updated_entities
#
#         # 6) Mettre à jour les métadonnées
#         current_json['last_updated'] = timezone.now().isoformat()
#         current_json['last_updated_by'] = request.user.username
#         current_json['document'].update({
#             'summary': new_summary,
#             'summary_updated_at': timezone.now().isoformat(),
#             'summary_updated_by': request.user.username,
#         })
#
#         # 7) Sauvegarder les modifications
#         document.global_annotations_json = current_json
#         document.save(update_fields=['global_annotations_summary', 'global_annotations_summary_generated_at',
#                                      'global_annotations_json'])
#
#         # Log de l'action
#         reason = "Summary edited and entities synchronized"
#         if changes_made:
#             reason += " | Changes: " + " ; ".join(changes_made[:5])
#         else:
#             reason += " | Aucune entité changée"
#         log_expert_action(
#             user=request.user,
#             action='summary_edited',
#             annotation=None,
#             document_id=document.id,
#             document_title=document.title,
#             old_text=old_summary,
#             new_text=new_summary,
#             reason=reason
#         )
#
#         return JsonResponse({
#             'success': True,
#             'message': 'Résumé sauvegardé et entités synchronisées',
#             'updated_json': current_json,
#             'changes_made': changes_made,
#             'changed_keys': changed_keys,
#             'entities_added': entities_added,
#             'entities_removed': entities_removed,
#             'entities_changes': changes_made,
#         })
#
#         # métadonnées de mise à jour
#         current_json['last_updated'] = timezone.now().isoformat()
#         current_json['last_updated_by'] = request.user.username
#         current_json['document'].update({
#             'summary': new_summary,
#             'summary_updated_at': timezone.now().isoformat(),
#             'summary_updated_by': request.user.username,
#         })
#
#         document.global_annotations_json = current_json
#         document.save(update_fields=['global_annotations_json'])
#
#         # (optionnel) push Mongo ici…
#
#         # Log
#         reason = "Summary edited; IA replace-only"
#         if human_diffs:
#             reason += " | " + " ; ".join(human_diffs[:5])
#         log_expert_action(
#             user=request.user,
#             action='summary_edited',
#             annotation=None,
#             document_id=document.id,
#             document_title=document.title,
#             old_text=old_summary,
#             new_text=new_summary,
#             reason=reason
#         )
#
#         return JsonResponse({
#             'success': True,
#             'message': 'Résumé sauvegardé',
#             'updated_json': current_json,
#             'changed_keys': changed_keys,
#             'entities_changes': human_diffs,
#         })
#     except Exception as e:
#         print(f"❌ save_summary_changes error: {e}")
#         return JsonResponse({'error': str(e)}, status=500)

# Modifier dans expert/views.py - Remplacer la fonction save_summary_changes existante

@expert_required
@csrf_exempt
def save_summary_changes(request, doc_id):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        document = get_object_or_404(RawDocument, id=doc_id)
        payload = json.loads(request.body)
        new_summary = (payload.get('summary_content') or '').strip()
        auto_annotate = payload.get('auto_annotate', True)
        page_id = payload.get('page_id', None)  # NOUVEAU: récupérer l'ID de la page



        if not new_summary:
            return JsonResponse({'error': 'Summary cannot be empty'}, status=400)

        old_summary = document.global_annotations_summary or ""

        # 2) Préparer/initialiser le JSON global et les entités si manquants
        current_json = document.global_annotations_json or {}
        current_json.setdefault('document', {})
        current_entities = current_json.get('entities', {}) or {}

        if not current_entities:
            # Construire les entités depuis les annotations du document
            try:
                from rawdocs.views import _build_entities_map
                all_annotations = Annotation.objects.filter(page__document=document).select_related('annotation_type')
                built = _build_entities_map(all_annotations, use_display_name=True) or {}
                current_entities = built
            except Exception:
                built = {}
                anns = Annotation.objects.filter(page__document=document).select_related('annotation_type')
                for ann in anns:
                    key = getattr(ann.annotation_type, 'display_name', None) or getattr(ann.annotation_type, 'name',
                                                                                        None) or 'Unknown'
                    built.setdefault(key, [])
                    val = (ann.selected_text or '').strip()
                    if val and val not in built[key]:
                        built[key].append(val)
                current_entities = built

            if not current_entities:
                default_keys = [
                    'Invented Name', 'Strength', 'Pharmaceutical Form', 'Route Of Administration',
                    'Immediate Packaging', 'Pack Size', 'Ma Number',
                ]
                current_entities = {k: [] for k in default_keys}

            current_json['entities'] = current_entities

        allowed_keys = list(current_entities.keys())

        # ===== NOUVELLE FONCTIONNALITÉ : ANNOTATION AUTOMATIQUE PAR IA =====
        new_annotations_created = []
        # MODIFICATION: Passer page_id à la fonction
        if auto_annotate and old_summary != new_summary:
            try:
                new_entities = await_ai_extract_and_annotate(
                    document, old_summary, new_summary, allowed_keys,
                    request.user, page_id=page_id  # NOUVEAU: passer page_id
                )
                if new_entities:
                    new_annotations_created = new_entities
                    # Mettre à jour current_entities avec les nouvelles entités trouvées par IA
                    for entity_type, values in new_entities.items():
                        if entity_type in allowed_keys:
                            current_entities[entity_type] = list(set(current_entities.get(entity_type, []) + values))
            except Exception as e:
                print(f"⚠️ Erreur annotation IA automatique: {e}")

        # Extraction des entités du nouveau résumé (méthode existante)
        extracted_by_keys = extract_by_allowed_keys(new_summary, allowed_keys)
        free_extracted = extract_entities_from_text(new_summary) or {}

        # Enrichissement par détections ciblées (route, packaging, pack size, forme)
        try:
            # Route of Administration
            route_vals = set()
            for m in re.finditer(
                    r"(?i)(?:par\s+voie\s+|voie\s+)(orale|intraveineuse|intramusculaire|sous\s*cutan[eé]e|subcutan[eé]e|nasale|topique|cutan[eé]e|rectale|inhalation)",
                    new_summary):
                route_vals.add(m.group(1))
            for m in re.finditer(
                    r"(?i)\b(oral|intravenous|intramuscular|subcutaneous|topical|nasal|rectal|inhalation|iv|im|sc)\b",
                    new_summary):
                route_vals.add(m.group(1))
            if route_vals:
                free_extracted.setdefault('Route Of Administration', []).extend(sorted(route_vals))

            # Immediate Packaging
            packaging_vals = set()
            for m in re.finditer(
                    r"(?i)\b(blisters?|blister|flacons?|bouteilles?|bottles?|sachets?|ampoules?|seringues?\s*pré?remplies?)\b",
                    new_summary):
                packaging_vals.add(m.group(0))
            if packaging_vals:
                free_extracted.setdefault('Immediate Packaging', []).extend(sorted(packaging_vals))

            # Pack Size
            pack_vals = set()
            for m in re.finditer(
                    r"(?i)\b([0-9]{1,4}\s*(?:comprim[ée]s?|gé?lules?|capsules?|sachets?|ml|ampoules?|unit[eé]s?))\b",
                    new_summary):
                pack_vals.add(m.group(1))
            if pack_vals:
                free_extracted.setdefault('Pack Size', []).extend(sorted(pack_vals))

            # Pharmaceutical Form
            form_vals = set()
            for m in re.finditer(
                    r"(?i)\b(comprim[ée]s?|gé?lules?|capsules?|sirop|solution|suspension|poudre|injectable|tablet[s]?)\b",
                    new_summary):
                form_vals.add(m.group(0))
            if form_vals:
                free_extracted.setdefault('Pharmaceutical Form', []).extend(sorted(form_vals))
        except Exception:
            pass

        # Fusionner les entités extraites
        extracted_entities: dict[str, list[str]] = {}
        for k, vals in (extracted_by_keys or {}).items():
            extracted_entities.setdefault(k, []).extend(vals or [])
        for raw_k, vals in (free_extracted or {}).items():
            canon = _canonical_key(raw_k, allowed_keys)
            if not canon:
                continue
            extracted_entities.setdefault(canon, []).extend(vals or [])

        # Déduplication + nettoyage par type
        for k, vals in list(extracted_entities.items()):
            extracted_entities[k] = _clean_values_for_type(k, vals or [])

        # Mise à jour fine par valeurs
        updated_entities = current_entities.copy()
        changes_made = []
        entities_added: dict[str, list[str]] = {}
        entities_removed: dict[str, list[str]] = {}
        changed_keys: list[str] = []

        key_map = {k.lower(): k for k in allowed_keys}
        old_extracted = extract_by_allowed_keys(old_summary or "", allowed_keys)

        def _norm_val(s: str) -> str:
            return re.sub(r'\s+', ' ', (s or '').strip()).lower()

        for lower_k, canon_k in key_map.items():
            existing_vals = list(updated_entities.get(canon_k, []) or [])
            existing_norms = {_norm_val(v) for v in existing_vals}

            old_vals_ex = []
            for etype, vals in (old_extracted or {}).items():
                if (etype or '').lower() == lower_k:
                    old_vals_ex = vals or []
                    break
            new_vals_ex = []
            for etype, vals in (extracted_entities or {}).items():
                if (etype or '').lower() == lower_k:
                    new_vals_ex = vals or []
                    break

            cleaned_old = _clean_values_for_type(canon_k, old_vals_ex)
            cleaned_new = _clean_values_for_type(canon_k, new_vals_ex)

            old_norms = {_norm_val(v) for v in cleaned_old}
            new_norms = {_norm_val(v) for v in cleaned_new}

            to_remove = old_norms - new_norms
            to_add = [v for v in cleaned_new if _norm_val(v) not in existing_norms]

            kept = [v for v in existing_vals if _norm_val(v) not in to_remove]
            removed_list = [v for v in existing_vals if _norm_val(v) in to_remove]

            added_list = []
            for v in to_add:
                nv = _norm_val(v)
                if nv not in {_norm_val(x) for x in kept}:
                    kept.append(v)
                    added_list.append(v)

            if kept != existing_vals:
                change_msg = f"{canon_k}:"
                if removed_list:
                    change_msg += f" -{removed_list}"
                    entities_removed[canon_k] = removed_list
                if added_list:
                    change_msg += f" +{added_list}"
                    entities_added[canon_k] = added_list
                changes_made.append(change_msg)
                updated_entities[canon_k] = kept
                changed_keys.append(canon_k)

        # Sauvegarder le résumé
        document.global_annotations_summary = new_summary
        document.global_annotations_summary_generated_at = timezone.now()

        # Mettre à jour le JSON
        current_json['entities'] = updated_entities
        current_json['last_updated'] = timezone.now().isoformat()
        current_json['last_updated_by'] = request.user.username
        current_json['document'].update({
            'summary': new_summary,
            'summary_updated_at': timezone.now().isoformat(),
            'summary_updated_by': request.user.username,
        })

        # Sauvegarder les modifications
        document.global_annotations_json = current_json
        document.save(update_fields=[
            'global_annotations_summary',
            'global_annotations_summary_generated_at',
            'global_annotations_json'
        ])

        # Log de l'action
        reason = "Summary edited and entities synchronized"
        if changes_made:
            reason += " | Changes: " + " ; ".join(changes_made[:5])
        if new_annotations_created:
            reason += f" | AI created {len(new_annotations_created)} new annotations"
        else:
            reason += " | No entity changes"

        log_expert_action(
            user=request.user,
            action='summary_edited',
            annotation=None,
            document_id=document.id,
            document_title=document.title,
            old_text=old_summary,
            new_text=new_summary,
            reason=reason
        )

        return JsonResponse({
            'success': True,
            'message': 'Résumé sauvegardé et entités synchronisées',
            'updated_json': current_json,
            'changes_made': changes_made,
            'changed_keys': changed_keys,
            'entities_added': entities_added,
            'entities_removed': entities_removed,
            'entities_changes': changes_made,
            'ai_annotations_created': new_annotations_created,  # Nouvelles annotations IA
        })

    except Exception as e:
        print(f"⛔ save_summary_changes error: {e}")
        return JsonResponse({'error': str(e)}, status=500)


# Nouvelle fonction pour l'annotation automatique par IA
# def await_ai_extract_and_annotate(document, old_summary, new_summary, allowed_keys, user):
#     """
#     Utilise l'IA pour identifier les nouvelles informations dans le résumé
#     et créer automatiquement des annotations dans le document
#     """
#     try:
#         from rawdocs.groq_annotation_system import GroqAnnotator
#
#         # Calculer les différences entre ancien et nouveau résumé
#         diff_text = find_summary_differences(old_summary, new_summary)
#         if not diff_text.strip():
#             return {}
#
#         # Utiliser Groq pour identifier les entités dans les nouvelles informations
#         groq_annotator = GroqAnnotator()
#
#         # Contexte pour l'IA
#         context = f"""
# Document: {document.title}
# Ancien résumé: {old_summary[:500]}...
# Nouveau résumé: {new_summary[:500]}...
# Types d'entités autorisés: {', '.join(allowed_keys)}
#
# Nouvelles informations ajoutées:
# {diff_text}
# """
#
#         # Prompt pour extraire et créer des annotations
#         prompt = f"""
# Analyse les nouvelles informations ajoutées au résumé et identifie les entités à annoter automatiquement.
#
# Contexte: {context}
#
# Instructions:
# 1. Identifie UNIQUEMENT les nouvelles informations (qui n'étaient pas dans l'ancien résumé)
# 2. Extrait les entités pharmaceutiques pertinentes selon les types autorisés
# 3. Pour chaque entité trouvée, propose le texte exact à annoter dans le document
#
# Réponds en JSON:
# {{
#     "entities_to_annotate": [
#         {{
#             "type": "entity_type",
#             "value": "texte exact",
#             "confidence": 0.0-1.0,
#             "context": "contexte où ça apparaît"
#         }}
#     ]
# }}
# """
#
#         # Appel à Groq
#         response = groq_annotator.complete_text(prompt, max_tokens=1000)
#
#         if response:
#             try:
#                 ai_result = json.loads(response)
#                 entities_to_annotate = ai_result.get('entities_to_annotate', [])
#
#                 created_annotations = {}
#
#                 # Créer automatiquement les annotations identifiées par l'IA
#                 for entity_data in entities_to_annotate:
#                     entity_type = entity_data.get('type', '').strip()
#                     entity_value = entity_data.get('value', '').strip()
#                     confidence = entity_data.get('confidence', 0.8)
#
#                     if entity_type in allowed_keys and entity_value and confidence > 0.7:
#                         # Trouver la meilleure page pour cette annotation
#                         target_page = find_best_page_for_annotation(document, entity_value)
#
#                         if target_page:
#                             # Créer l'annotation automatiquement
#                             annotation_created = create_ai_annotation(
#                                 target_page, entity_value, entity_type, user, confidence
#                             )
#
#                             if annotation_created:
#                                 created_annotations.setdefault(entity_type, []).append(entity_value)
#
#                 return created_annotations
#
#             except json.JSONDecodeError:
#                 print("⚠️ Erreur parsing réponse IA pour annotation automatique")
#                 return {}
#
#         return {}
#
#     except Exception as e:
#         print(f"⚠️ Erreur annotation IA automatique: {e}")
#         return {}


def find_summary_differences(old_summary, new_summary):
    """Trouve les différences entre deux résumés"""
    import difflib

    old_lines = old_summary.split('\n') if old_summary else []
    new_lines = new_summary.split('\n') if new_summary else []

    differ = difflib.unified_diff(old_lines, new_lines, n=0)

    additions = []
    for line in differ:
        if line.startswith('+') and not line.startswith('+++'):
            additions.append(line[1:].strip())

    return '\n'.join(additions)


def find_best_page_for_annotation(document, entity_value):
    """Trouve la meilleure page pour placer une annotation"""
    # Chercher dans les pages du document celle qui contient le texte
    pages = document.pages.all().order_by('page_number')

    best_page = None
    best_score = 0

    for page in pages:
        if hasattr(page, 'cleaned_text') and page.cleaned_text:
            text = page.cleaned_text.lower()
            entity_lower = entity_value.lower()

            # Score basé sur la présence du texte exact ou similaire
            score = 0
            if entity_lower in text:
                score = 100
            else:
                # Recherche de mots-clés similaires
                words = entity_lower.split()
                for word in words:
                    if len(word) > 3 and word in text:
                        score += 20

            if score > best_score:
                best_score = score
                best_page = page

    return best_page if best_score > 30 else pages.first()


def create_ai_annotation(page, entity_value, entity_type, user, confidence):
    """Crée une annotation automatiquement via IA"""
    try:
        # Chercher le texte dans la page
        if hasattr(page, 'cleaned_text') and page.cleaned_text:
            text_content = page.cleaned_text
            start_pos = text_content.lower().find(entity_value.lower())

            if start_pos == -1:
                # Si pas trouvé exactement, chercher des mots-clés
                words = entity_value.split()
                for word in words:
                    if len(word) > 3:
                        start_pos = text_content.lower().find(word.lower())
                        if start_pos != -1:
                            entity_value = word  # Utiliser le mot trouvé
                            break

            if start_pos != -1:
                end_pos = start_pos + len(entity_value)

                # Créer ou récupérer le type d'annotation
                annotation_type, created = AnnotationType.objects.get_or_create(
                    name=entity_type,
                    defaults={
                        'display_name': entity_type.replace('_', ' ').title(),
                        'color': '#8b5cf6',  # Violet pour les annotations IA automatiques
                        'description': f"Auto-generated by AI from summary: {entity_type}"
                    }
                )

                # Créer l'annotation
                annotation = Annotation.objects.create(
                    page=page,
                    selected_text=entity_value,
                    annotation_type=annotation_type,
                    start_pos=start_pos,
                    end_pos=end_pos,
                    validation_status='expert_created',  # Pré-validée car créée par expert
                    validated_by=user,
                    validated_at=timezone.now(),
                    created_by=user,
                    source='expert_ai_auto',
                    confidence_score=confidence
                )

                print(f"✅ Annotation IA automatique créée: {entity_value} ({entity_type}) dans page {page.page_number}")
                return True

        return False

    except Exception as e:
        print(f"⚠️ Erreur création annotation automatique: {e}")
        return False

# --- helpers backend : extraction stricte + nettoyage ---

import re


# Ajouter à expert/views.py - Nouvelle fonction pour régénération automatique du résumé

@expert_required
@csrf_exempt
def auto_regenerate_summary_from_annotations(request, doc_id):
    """
    Régénère automatiquement le résumé basé sur les annotations actuelles
    Appelé quand les annotations sont modifiées
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        document = get_object_or_404(RawDocument, id=doc_id)

        # Récupérer toutes les annotations validées du document
        all_annotations = Annotation.objects.filter(
            page__document=document,
            validation_status__in=['validated', 'expert_created']
        ).select_related('annotation_type', 'page').order_by('page__page_number', 'start_pos')

        if not all_annotations.exists():
            return JsonResponse({
                'success': False,
                'error': 'No validated annotations found'
            })

        # Construire les entités depuis les annotations
        from rawdocs.views import _build_entities_map, generate_entities_based_document_summary
        entities = _build_entities_map(all_annotations, use_display_name=True)

        # Générer un nouveau résumé basé sur les annotations actuelles
        new_summary = generate_entities_based_document_summary(
            entities=entities,
            doc_title=document.title,
            doc_type=getattr(document, 'doc_type', None),
            total_annotations=all_annotations.count()
        )

        # Enrichir le résumé avec l'IA si possible
        try:
            enhanced_summary = enhance_summary_with_ai(document, entities, new_summary)
            if enhanced_summary and len(enhanced_summary) > len(new_summary):
                new_summary = enhanced_summary
        except Exception as e:
            print(f"⚠️ Erreur enrichissement résumé IA: {e}")

        # Sauvegarder le nouveau résumé
        old_summary = document.global_annotations_summary or ""
        document.global_annotations_summary = new_summary
        document.global_annotations_summary_generated_at = timezone.now()

        # Mettre à jour le JSON global
        current_json = document.global_annotations_json or {}
        current_json.setdefault('document', {})
        current_json['entities'] = entities
        current_json['last_updated'] = timezone.now().isoformat()
        current_json['last_updated_by'] = request.user.username
        current_json['document'].update({
            'summary': new_summary,
            'summary_updated_at': timezone.now().isoformat(),
            'summary_updated_by': request.user.username + ' (auto)',
        })

        document.global_annotations_json = current_json
        document.save(update_fields=[
            'global_annotations_summary',
            'global_annotations_summary_generated_at',
            'global_annotations_json'
        ])

        # Log de l'action
        log_expert_action(
            user=request.user,
            action='summary_auto_regenerated',
            annotation=None,
            document_id=document.id,
            document_title=document.title,
            old_text=old_summary,
            new_text=new_summary,
            reason=f"Summary auto-regenerated from {all_annotations.count()} annotations"
        )

        return JsonResponse({
            'success': True,
            'message': 'Résumé régénéré automatiquement depuis les annotations',
            'new_summary': new_summary,
            'updated_json': current_json,
            'annotations_count': all_annotations.count()
        })

    except Exception as e:
        print(f"⛔ auto_regenerate_summary error: {e}")
        return JsonResponse({'error': str(e)}, status=500)


def enhance_summary_with_ai(document, entities, basic_summary):
    """
    Utilise l'IA pour enrichir le résumé généré automatiquement
    """
    try:
        from rawdocs.groq_annotation_system import GroqAnnotator

        groq_annotator = GroqAnnotator()

        # Construire le contexte pour l'IA
        entities_text = ""
        for entity_type, values in entities.items():
            if values:
                entities_text += f"- {entity_type}: {', '.join(values[:3])}\n"

        prompt = f"""
Améliore ce résumé pharmaceutique en ajoutant du contexte et des détails pertinents basés sur les entités extraites.

Document: {document.title}
Type: {getattr(document, 'doc_type', 'Pharmaceutique')}

Résumé de base:
{basic_summary}

Entités identifiées:
{entities_text}

Instructions:
1. Garde toutes les informations du résumé original
2. Ajoute des connexions logiques entre les entités
3. Enrichis avec du contexte pharmaceutique pertinent
4. Maintiens un ton professionnel et précis
5. Maximum 300 mots

Résumé enrichi:"""

        response = groq_annotator.complete_text(prompt, max_tokens=800)

        if response and len(response.strip()) > len(basic_summary):
            return response.strip()

        return basic_summary

    except Exception as e:
        print(f"⚠️ Erreur enrichissement résumé: {e}")
        return basic_summary


# Modifier aussi les fonctions d'annotation existantes pour déclencher la régénération
# Par exemple, dans expert_save_manual_annotation, expert_delete_annotation, etc.

def trigger_summary_regeneration(document, user):
    """
    Déclenche la régénération automatique du résumé en arrière-plan
    """
    try:
        from django.test import RequestFactory
        factory = RequestFactory()
        fake_request = factory.post(f'/expert/document/{document.id}/auto-regenerate-summary/')
        fake_request.user = user

        # Appeler la fonction de régénération
        result = auto_regenerate_summary_from_annotations(fake_request, document.id)
        return True
    except Exception as e:
        print(f"⚠️ Erreur déclenchement régénération résumé: {e}")
        return False
def extract_entities_from_text(text: str) -> dict:
    """
    Extraction intelligente des entités du texte (FR/EN + abréviations).
    Ajout: détection robuste des Date (mois + année, formats dd Month yyyy, mm/yyyy, yyyy-mm, etc.).
    """
    base_patterns = {
        'Product': [
            r'\b(?:produit|médicament|product)\b\s*:?\s*((?-i:[A-Z])[\wÀ-ÿ\s\-\/]{2,60})',
            r'\b(?:produit|product)\b\s+(?:est|is)\s+((?-i:[A-Z])[\wÀ-ÿ\s\-\/]{2,60})',
            r'^(?:le\s+|the\s+)?([A-Z][\wÀ-ÿ\s\-\/]{3,60})\s+(?:est|sera|contient|is|contains)\b',
            r'(?:nom du produit|product name)\s*:?\s*([A-Z][\wÀ-ÿ\s\-\/]{2,60})'
        ],
        'Dosage': [
            r'\b([0-9]+(?:[.,][0-9]+)?\s*(?:mg|g|ml|l|µg|mcg|%|UI|iu|mg\/ml|g\/l))\b',
            r'(?:dosage|posologie|concentration|strength)\s*:?\s*([0-9]+(?:[.,][0-9]+)?\s*(?:mg|g|ml|l|µg|mcg|%|UI|iu|mg\/ml|g\/l))',
        ],
        'Substance_Active': [
            r'(?:substance active|principe actif|active ingredient)\s*:?\s*([A-Z][\wÀ-ÿ\s\-]{2,60})',
            r'(?:contient|à base de|contains)\s+([A-Z][\wÀ-ÿ\s\-]{2,60})'
        ],
        'Site': [
            r'(?:site|usine|fabricant|manufacturing site|manufacturer)\s*:?\s*([A-Z][\wÀ-ÿ\s\.\-]{2,80})',
            r'(?:fabriqu[ée]|produit|manufactured|made)\s*(?:à|par|by|in)\s*([A-Z][\wÀ-ÿ\s\.\-]{2,80})'
        ],
        'Pays': [
            r'(?:pays|country)\s*:?\s*([A-Z][\wÀ-ÿ\s\-]{2,40})',
            r'(?:en|au|aux|in)\s+([A-Z][\wÀ-ÿ\s\-]{2,40})(?=[\s,\.]|$)'
        ],
        'Strength': [
            r'(?:strength|force|puissance|teneur)\s*(?:de|:)?\s*([0-9]+(?:[.,][0-9]+)?\s*(?:mg|g|ml|l|µg|mcg|%|UI|iu))',
            r'(?:concentration)\s*(?:de|:)?\s*([0-9]+(?:[.,][0-9]+)?\s*(?:mg|g|ml|l|µg|mcg|%|UI|iu))',
            r'(?:est\s+de|is)\s*([0-9]+(?:[.,][0-9]+)?\s*(?:mg|g|ml|l|µg|mcg|%|UI|iu))',
        ],
        'Form': [
            r'(?:forme|form|presentation|pharmaceutical form)\s*:?\s*(\b(?:comprim[ée]s?|g[ée]lules?|capsules?|sirop|solution|suspension|poudre|injectable|gel|cr[èe]me|onguent|suppositoire|tablet[s]?)\b)',
            r'(?:sous\s+forme\s+de|as\s+a)\s*(\b(?:comprim[ée]s?|g[ée]lules?|capsules?|sirop|solution|suspension|poudre|injectable|gel|cr[èe]me|onguent|suppositoire|tablet[s]?)\b)',
        ],
        'Batch_Size': [
            r'(?:taille de lot|batch size|lot)\s*:?\s*([0-9]+(?:[.,][0-9]+)?\s*(?:unités?|comprim[ée]s?|g[ée]lules?|capsules?|batches?))',
        ],
        'Shelf_Life': [
            r'(?:durée de conservation|shelf life|péremption|expiry)\s*:?\s*([0-9]+\s*(?:mois|ans?|months?|years?|m|y))',
        ],
        # --- NOUVEAU : Dates (mois + année, d/m/Y, Y-m, etc.) ---
        'Date': [
            r'\b(?:\d{1,2}\s+)?(?:janvier|février|fevrier|mars|avril|mai|juin|juillet|août|aout|septembre|octobre|novembre|décembre|decembre|jan|janv\.?|févr\.?|fevr\.?|avr\.?|juil\.?|sept\.?|oct\.?|nov\.?|déc\.?|dec\.?|january|february|march|april|may|june|july|august|september|october|november|december|jan\.?|feb\.?|mar\.?|apr\.?|jun\.?|jul\.?|aug\.?|sep\.?|oct\.?|nov\.?|dec\.?)\s*[,/-]?\s*(20\d{2}|19\d{2})\b',
            r'\b(0?[1-9]|[12][0-9]|3[01])\s+(?:janvier|février|fevrier|mars|avril|mai|juin|juillet|août|aout|septembre|octobre|novembre|décembre|decembre|january|february|march|april|may|june|july|august|september|october|november|december)\s*(20\d{2}|19\d{2})\b',
            r'\b(0?[1-9]|1[0-2])[/-](20\d{2}|19\d{2})\b',
            r'\b(20\d{2}|19\d{2})-(0?[1-9]|1[0-2])\b',
            r'\b(0?[1-9]|[12][0-9]|3[01])[/-](0?[1-9]|1[0-2])[/-](20\d{2}|19\d{2})\b',
        ]
    }

    results = {}
    for entity_type, patterns in base_patterns.items():
        vals = set()
        for pattern in patterns:
            for m in re.finditer(pattern, text or "", re.IGNORECASE | re.MULTILINE):
                v = (m.group(0) or '').strip().rstrip('.,;:')
                # anti-bruit Date: refuser année seule
                if entity_type == 'Date' and re.fullmatch(r'\d{4}', v):
                    continue
                if v and len(v) <= 100:
                    vals.add(v)
        if vals:
            results[entity_type] = list(vals)
    return results



def extract_by_allowed_keys(text: str, allowed_keys: list[str]) -> dict:
    """
    Extraction basée sur les libellés des clés existantes (insensible à la casse).
    Pour chaque clé existante, capture des valeurs sous les formes:
    - "<Clé>: <valeur>"
    - "<Clé> est/is/are <valeur>"
    Les valeurs extraites sont ensuite nettoyées par _clean_values_for_type.
    """
    results: dict[str, list[str]] = {}

    def norm_one(s: str) -> str:
        s = re.sub(r"\s+", " ", (s or "").strip())
        # normaliser espace entre nombre et unité
        s = re.sub(r"(?i)\b([0-9]+(?:[.,][0-9]+)?)(mg|g|ml|l|µg|mcg|%|ui)\b", r"\1 \2", s)
        return s

    text = text or ""

    for key in allowed_keys or []:
        if not key:
            continue
        label = re.escape(key)
        patterns = [
            rf"(?i)\b{label}\b\s*[:\-]\s*([^\.;\n]+)",  # Clé: valeur
            rf"(?i)\b{label}\b\s*(?:est|is|are)\s*([^\.;\n]+)",  # Clé est/is/are valeur
        ]
        found = set()
        for pat in patterns:
            for m in re.finditer(pat, text):
                raw_val = norm_one(m.group(1))
                cleaned = _clean_values_for_type(key, [raw_val])
                for cv in cleaned:
                    found.add(cv)
        if found:
            results[key] = list(found)

    return results

    out = {}
    for etype, regs in patterns.items():
        vals = set()
        for rg in regs:
            for m in re.finditer(rg, text, re.IGNORECASE | re.MULTILINE):
                v = (m.group(1) or '').strip().rstrip('.,;:')
                if v and 1 < len(v) <= 80:
                    vals.add(v)
        if vals:
            out[etype] = list(sorted(vals))
    return out


def _clean_values_for_type(key: str, values: list[str]) -> list[str]:
    def norm(s: str) -> str:
        s = re.sub(r'\s+', ' ', (s or '').strip())
        s = re.sub(r'(?i)\b([0-9]+(?:[.,][0-9]+)?)(mg|g|ml|l|µg|mcg|%|ui)\b', r'\1 \2', s)
        return s

    seen, keep = set(), []
    k = (key or '').strip().lower()

    # --- Dates ---
    if k in {'date', 'publication date', 'effective date', 'date de publication', 'deadline'}:
        for v in values or []:
            vv = norm(v).rstrip('.,;:')
            ok, _, _ = _is_date_like(vv)
            if not ok:  # éviter '2013' seule
                continue
            slug = vv.lower()
            if slug not in seen:
                seen.add(slug); keep.append(vv)
        return keep

    if k in {'dosage', 'strength'}:
        strict_rx = re.compile(r'(?i)^[0-9]+(?:[.,][0-9]+)?\s*(?:mg|g|ml|l|µg|mcg|%|ui|iu)(?:\s*/\s*(?:ml|l|g))?$')
        for v in values or []:
            vv = norm(v)
            m = re.search(r'(?i)([0-9]+(?:[.,][0-9]+)?\s*(?:mg|g|ml|l|µg|mcg|%|ui|iu)(?:\s*/\s*(?:ml|l|g))?)', vv)
            if m: vv = norm(m.group(1))
            if strict_rx.match(vv):
                slug = vv.lower()
                if slug not in seen:
                    seen.add(slug); keep.append(vv)
        return keep

    if k in {'product', 'invented name', 'substance active', 'substance_active', 'active ingredient'}:
        cut_rx = re.compile(r'^(.*?)(?:\s+(?:et|and)\b|,|;|\.|$)', re.IGNORECASE)
        for v in values or []:
            vv = norm(v)
            m = cut_rx.match(vv)
            if m: vv = m.group(1).strip()
            vv = re.sub(r'(?i)^(?:le\s+produit\s+est|the\s+product\s+is|est|est de|is|contains)\s+', '', vv).strip()
            if not re.match(r'^(?-i:[A-Z]).*', vv):  # éviter 'produits de dégradation'
                continue
            if 1 < len(vv) <= 80:
                slug = vv.lower()
                if slug not in seen:
                    seen.add(slug); keep.append(vv)
        return keep

    stop = {'de','du','des','et','la','le','les','à','au','aux','pour','sur','dans','par','avec'}
    for v in values or []:
        vv = norm(v)
        vv = re.split(r'[;\.]', vv)[0].strip()
        if 2 < len(vv) <= 80 and vv.lower() not in stop:
            slug = vv.lower()
            if slug not in seen:
                seen.add(slug); keep.append(vv)
    return keep


import unicodedata


def _fold_key(s: str) -> str:
    s = (s or '').strip().lower()
    s = unicodedata.normalize('NFD', s)
    s = ''.join(ch for ch in s if unicodedata.category(ch) != 'Mn')  # remove accents
    s = re.sub(r'[^a-z0-9]+', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def _build_synonym_map(existing_keys: list[str]) -> dict:
    """Construit une map foldée -> clé canonique, avec synonymes courants (FR/EN).
    Note: on ne relie des synonymes qu’aux clés VRAIMENT présentes dans existing_keys.
    """
    syn: dict[str, str] = {}
    existing_keys = existing_keys or []

    # Clés existantes -> elles-mêmes
    for ek in existing_keys:
        syn[_fold_key(ek)] = ek

    # Lier des synonymes SEULEMENT si la clé canonique est déjà présente
    def bind(canon: str, variants: list[str]):
        if canon in existing_keys:
            syn[_fold_key(canon)] = canon
            for v in variants:
                syn[_fold_key(v)] = canon

    bind('Invented Name', ['product', 'product name', 'nom du produit', 'nom commercial', 'invented name'])
    bind('Strength', ['dosage', 'posologie', 'concentration', 'teneur', 'strength'])

    # Forme pharmaceutique
    for variant in ['Pharmaceutical Form', 'Form']:
        bind(variant, ['form', 'forme', 'presentation', 'pharmaceutical form', 'forme pharmaceutique'])

    # Voie d'administration
    for variant in ['Route Of Administration', 'Route', 'Voie']:
        bind(variant, [
            'route', 'voie', 'voie d administration', "voie d’administration",
            'route of administration', 'administration route'
        ])
    # Dates (ne liera ces synonymes que si la clé canonique correspondante existe déjà)
    for variant in ['Date', 'Effective Date', 'Publication Date', 'Update Date', 'Deadline', 'Start Date']:
        bind(variant, [
            'date', 'effective date', 'date effective', 'publication date', 'date de publication',
            'update date', 'date de mise à jour', 'deadline', 'échéance', 'date limite',
            'start date', 'date de début', "date d'entrée en vigueur", 'date d effet', 'date d’effet'
        ])


    # Conditionnement immédiat
    for variant in ['Immediate Packaging', 'Packaging', 'Emballage']:
        bind(variant, ['packaging', 'emballage', 'immediate packaging', 'conditionnement'])

    # Taille de pack
    for variant in ['Pack Size', 'Packsize', 'Pack']:
        bind(variant, ['pack size', 'taille du pack', 'taille de pack', 'taille de boîte', 'boîte'])

    # Numéro d'AMM
    for variant in ['Ma Number', 'AMM Number', 'Authorization Number']:
        bind(variant, [
            'ma number', 'numero amm', 'numéro amm',
            'authorization number', 'marketing authorization number', 'amm'
        ])

    # Sites / Fabricant
    for variant in ['Site', 'Manufacturing Site']:
        bind(variant, ['manufacturing site', 'site', 'usine', 'fabricant'])

    # Pays
    for variant in ['Country', 'Pays']:
        bind(variant, ['pays', 'country'])

    # Substance active
    for variant in ['Substance Active', 'Substance_Active', 'Active Ingredient']:
        bind(variant, ['substance active', 'principe actif', 'active ingredient'])

    # --- NOUVEAU : Dates (points temporels) ---
    # Permet de canoniser vers la clé 'Date' (ou variantes) si elle existe déjà dans le JSON
    for variant in ['Date', 'Publication Date', 'Effective Date', 'Deadline']:
        bind(variant, [
            'date', 'publication date', 'effective date', 'deadline',
            'date de publication', "date d'effet", 'date d’effet',
            "date d'entrée en vigueur", "date d'entree en vigueur",
            'date effective', 'date limite', 'date de validité', 'date de validite'
        ])

    # Délai / Duration (durées, à distinguer des dates)
    bind('Delay', ['délai', 'delai', 'durée', 'duree', 'duration', 'timeframe'])

    return syn



def _canonical_key(key: str, existing_keys: list[str]) -> str | None:
    """Retourne la clé canonique parmi existing_keys en utilisant un matching accent/casse/synonymes."""
    if not key:
        return None
    syn = _build_synonym_map(existing_keys)
    folded = _fold_key(key)
    return syn.get(folded)


def update_document_json_with_entities_replace_only(document, new_entities: dict) -> tuple[dict, list[str]]:
    """
    Remplace les valeurs des entités EXISTANTES uniquement, sans en créer.
    Nettoie et déduplique. Retourne (json_mis_a_jour, liste_cles_modifiees).
    """
    current_json = document.global_annotations_json or {}
    entities = current_json.get('entities', {}) or {}
    changed = []

    existing_keys = list(entities.keys())
    if not existing_keys:
        # Rien à faire si pas d'entités existantes
        return current_json, changed

    for raw_key, values in (new_entities or {}).items():
        canon = _canonical_key(raw_key, existing_keys)
        if not canon:
            continue  # on ignore les types non présents pour éviter d'en créer
        cleaned = _clean_values_for_type(canon, values or [])
        if cleaned and entities.get(canon) != cleaned:
            entities[canon] = cleaned
            changed.append(canon)

    if changed:
        current_json['entities'] = entities
        current_json['last_updated'] = timezone.now().isoformat()
        document.global_annotations_json = current_json
        document.save(update_fields=['global_annotations_json'])

    return current_json, changed


####################
import difflib, json, re
from typing import Dict, List, Tuple
from rawdocs.groq_annotation_system import GroqAnnotator
import os, difflib, json, re
from typing import Dict, List, Tuple

try:
    from groq import Groq  # SDK officiel
except Exception:
    Groq = None

from rawdocs.groq_annotation_system import GroqAnnotator


def _normalize_values(values: List[str]) -> List[str]:
    """trim + dédup (insensible à la casse) + espaces normalisés"""
    seen, out = set(), []
    for v in values or []:
        vv = re.sub(r'\s+', ' ', (v or '').strip())
        key = vv.lower()
        if vv and key not in seen:
            seen.add(key);
            out.append(vv)
    return out


def _replace_only(existing_entities: Dict[str, List[str]],
                  proposed_changes: Dict[str, List[str]]) -> Tuple[Dict[str, List[str]], List[str], List[str]]:
    """
    Applique des changements SEULEMENT sur les clés déjà existantes.
    Retourne (entities_mises_a_jour, keys_modifiées, traces_humaines)
    """
    if not existing_entities:
        return existing_entities, [], []

    allowed = {k: k for k in existing_entities.keys()}  # map canonique
    changed_keys, human_diffs = [], []

    for raw_k, vals in (proposed_changes or {}).items():
        # ne pas créer de nouveaux types : on ne garde que les clés existantes (match insensible casse)
        canon = next((ek for ek in allowed if ek.lower() == (raw_k or '').lower()), None)
        if not canon:
            continue

        new_vals = _normalize_values(vals)
        old_vals = existing_entities.get(canon, [])
        if new_vals != old_vals:
            existing_entities[canon] = new_vals
            changed_keys.append(canon)
            human_diffs.append(f"{canon}: {old_vals} → {new_vals}")

    return existing_entities, changed_keys, human_diffs


def ai_propose_entity_updates(old_summary: str,
                              new_summary: str,
                              current_entities: Dict[str, List[str]],
                              allowed_keys: List[str]) -> Dict[str, List[str]]:
    diff = "\n".join(difflib.unified_diff(
        (old_summary or "").splitlines(),
        (new_summary or "").splitlines(),
        fromfile="before", tofile="after", lineterm=""
    ))

    system = (
        "You are a strict information-extraction assistant. "
        "Update ONLY existing entity types if the new summary clearly changes them. "
        "Do not invent new types. If unsure, omit it. Output JSON only."
    )
    user = f"""
Allowed entity types: {allowed_keys}

Current entities:
{json.dumps(current_entities, ensure_ascii=False)}

Old summary:
\"\"\"{old_summary or ''}\"\"\"

New summary:
\"\"\"{new_summary or ''}\"\"\"

Unified diff:
{diff}

Return EXACTLY:
{{"changes": {{"<Type>": ["new", "values"]}}}}
""".strip()

    content = None

    # A) SDK officiel Groq (recommandé)
    if Groq is not None:
        try:
            client = Groq(api_key=getattr(settings, "GROQ_API_KEY", os.getenv("GROQ_API_KEY")))
            resp = client.chat.completions.create(
                model=getattr(settings, "GROQ_MODEL", "llama3-70b-8192"),
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": user}],
                temperature=0.1,
                max_tokens=400,
                response_format={"type": "json_object"},
            )
            content = resp.choices[0].message.content
        except Exception as e:
            print(f"⚠️ GROQ SDK path failed: {e}")

    # B) Fallback via votre GroqAnnotator s'il expose une méthode utilisable
    if not content:
        try:
            ga = GroqAnnotator()
            # Essayez une méthode JSON si elle existe dans votre classe
            for m in ("chat_json", "complete_json", "ask_json"):
                if hasattr(ga, m):
                    content = getattr(ga, m)(
                        system=system, user=user,
                        model=getattr(settings, "GROQ_MODEL", "llama3-70b-8192"),
                        temperature=0.1, max_tokens=400
                    )
                    break
        except Exception as e:
            print(f"⚠️ GroqAnnotator fallback failed: {e}")

    if not content:
        return {}  # IA indispo → pas de modif

    try:
        data = json.loads(content) if isinstance(content, str) else content
        raw_changes = data.get("changes", {}) if isinstance(data, dict) else {}
    except Exception:
        return {}

    # Filtrer: uniquement les clés existantes
    filtered = {}
    for k, vals in (raw_changes or {}).items():
        if any(k.lower() == ak.lower() for ak in allowed_keys):
            filtered[k] = _normalize_values(vals)
    return filtered


def save_document_json(request, doc_id):
    """Sauvegarde du JSON global modifié d'un document (et stockage MongoDB avec métadonnées complètes)"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        document = get_object_or_404(RawDocument, id=doc_id)
        data = json.loads(request.body)
        json_content = data.get('json_content')

        if not json_content:
            return JsonResponse({'error': 'JSON content is required'}, status=400)

        # Valider que le JSON est bien formaté
        try:
            parsed_json = json.loads(json_content)
        except json.JSONDecodeError as e:
            return JsonResponse({'error': f'Invalid JSON format: {str(e)}'}, status=400)

        # Fonction helper pour gérer les dates
        def safe_isoformat(date_value):
            if date_value is None:
                return None
            if isinstance(date_value, str):
                return date_value
            if hasattr(date_value, 'isoformat'):
                return date_value.isoformat()
            return str(date_value)

        # Enrichir le JSON avec TOUTES les métadonnées du document
        parsed_json['document']['metadata'] = {
            'title': document.title,
            'doc_type': document.doc_type,
            'publication_date': safe_isoformat(document.publication_date),
            'version': document.version,
            'source': document.source,
            'context': document.context,
            'country': document.country,
            'language': document.language,
            'url_source': document.url_source,
            'url': document.url,
            'created_at': safe_isoformat(document.created_at),
            'validated_at': safe_isoformat(document.validated_at),
            'owner': document.owner.username if document.owner else None,
            'total_pages': document.total_pages,
            'file_name': os.path.basename(document.file.name) if document.file else None,
        }

        # Ajouter les champs personnalisés s'ils existent
        from rawdocs.models import CustomFieldValue
        custom_fields = {}
        for custom_value in CustomFieldValue.objects.filter(document=document):
            custom_fields[custom_value.field.name] = custom_value.value

        if custom_fields:
            parsed_json['document']['metadata']['custom_fields'] = custom_fields

        # Sauvegarder en base SQL
        document.global_annotations_json = parsed_json
        document.global_annotations_summary_generated_at = timezone.now()
        document.save(update_fields=['global_annotations_json', 'global_annotations_summary_generated_at'])

        # Sauvegarder dans MongoDB avec toutes les métadonnées
        mongo_collection.update_one(
            {"document_id": str(document.id)},
            {
                "$set": {
                    "document_id": str(document.id),
                    "title": document.title,
                    "metadata": parsed_json['document']['metadata'],  # Toutes les métadonnées
                    "json": parsed_json,
                    "entities": parsed_json.get('entities', {}),
                    "updated_at": timezone.now().isoformat(),
                    "updated_by": request.user.username
                }
            },
            upsert=True
        )

        # LOG ACTION
        log_expert_action(
            user=request.user,
            action='json_edited',
            annotation=None,
            document_id=document.id,
            document_title=document.title,
            reason=f"Global JSON manually edited by expert with full metadata"
        )

        return JsonResponse({
            'success': True,
            'message': 'JSON sauvegardé avec succès (SQL + MongoDB avec métadonnées complètes)'
        })

    except Exception as e:
        print(f"❌ Erreur lors de la sauvegarde du JSON: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)


# ——— NOUVELLES VUES ANNOTATION EXPERT (copiées et adaptées de rawdocs) —————————————————————————————————

from django.contrib.auth.decorators import login_required
from datetime import datetime
from rawdocs.groq_annotation_system import GroqAnnotator


@expert_required
def expert_annotation_dashboard(request):
    """Dashboard annotation pour Expert - copie de rawdocs.views.annotation_dashboard"""
    # Récupérer tous les documents validés (prêts pour annotation)
    documents = RawDocument.objects.filter(is_validated=True).select_related('owner').order_by('-created_at')

    # Statistiques
    total_documents = documents.count()
    total_pages = sum(doc.total_pages for doc in documents)

    # Pages avec au moins une annotation
    annotated_pages = DocumentPage.objects.filter(
        document__in=documents,
        annotations__isnull=False
    ).distinct().count()

    # Documents en cours d'annotation (au moins une page annotée mais pas toutes)
    in_progress_docs = []
    completed_docs = []

    for doc in documents:
        doc_pages = doc.pages.all()
        annotated_doc_pages = doc_pages.filter(annotations__isnull=False).distinct().count()

        if annotated_doc_pages > 0:
            if annotated_doc_pages == doc.total_pages:
                completed_docs.append(doc)
            else:
                in_progress_docs.append(doc)

    context = {
        'documents': documents,
        'total_documents': total_documents,
        'total_pages': total_pages,
        'total_annotated_pages': annotated_pages,
        'in_progress_count': len(in_progress_docs),
        'completed_count': len(completed_docs),
    }

    return render(request, 'expert/annotation_dashboard.html', context)


def expert_annotate_document(request, doc_id):
    document = get_object_or_404(RawDocument, id=doc_id, is_ready_for_expert=True)
    pages = document.pages.all()
    pnum = int(request.GET.get('page', 1))
    current_page = get_object_or_404(DocumentPage, document=document, page_number=pnum)

    # Get existing annotations
    existing_annotations = current_page.annotations.filter(
        validation_status__in=['pending', 'validated', 'expert_created', 'rejected']
    ).order_by('start_pos')

    # Types d'annotations par défaut (mêmes que côté Annotateur) + types déjà utilisés
    used_type_ids = Annotation.objects.filter(page__document=document).values_list('annotation_type_id', flat=True).distinct()

    whitelist = {
        AnnotationType.REQUIRED_DOCUMENT,
        AnnotationType.AUTHORITY,
        AnnotationType.LEGAL_REFERENCE,
        AnnotationType.DELAY,
        AnnotationType.PROCEDURE_TYPE,
        AnnotationType.VARIATION_CODE,
        AnnotationType.REQUIRED_CONDITION,
        AnnotationType.FILE_TYPE,
    }

    base_qs = AnnotationType.objects.filter(name__in=list(whitelist))
    used_qs = AnnotationType.objects.filter(id__in=used_type_ids)
    annotation_types = (base_qs | used_qs).distinct().order_by('display_name')

    # Annotations existantes pour la page courante
    existing_annotations = current_page.annotations.all() if current_page else []

    context = {
        'document': document,
        'pages': pages,
        'current_page': current_page,
        'annotation_types': annotation_types,
        'existing_annotations': existing_annotations,
        'total_pages': document.total_pages
    }

    return render(request, 'expert/annotate_document.html', context)


# Ajouter ces fonctions utilitaires dans expert/views.py - À la fin du fichier

# ===== FONCTIONS UTILITAIRES POUR LA SYNCHRONISATION AUTOMATIQUE =====

# Variables globales pour la gestion des régénérations
REGENERATION_CACHE = {}
CACHE_DURATION = 30  # secondes entre régénérations pour un même document


def should_regenerate_summary(document_id):
    """Vérifie si on doit régénérer le résumé (évite les appels trop fréquents)"""
    import time

    last_regeneration = REGENERATION_CACHE.get(document_id, 0)
    current_time = time.time()

    if current_time - last_regeneration > CACHE_DURATION:
        REGENERATION_CACHE[document_id] = current_time
        return True

    return False


def trigger_summary_regeneration(document, user):
    """Version de base pour régénération du résumé"""
    if not should_regenerate_summary(document.id):
        print(f"⏰ Régénération résumé ignorée (trop récente) pour doc {document.id}")
        return False

    try:
        from django.test import RequestFactory
        factory = RequestFactory()
        fake_request = factory.post(f'/expert/document/{document.id}/auto-regenerate-summary/')
        fake_request.user = user

        # Appeler la fonction de régénération
        result = auto_regenerate_summary_from_annotations(fake_request, document.id)

        if hasattr(result, 'status_code') and result.status_code == 200:
            print(f"✅ Régénération résumé réussie pour doc {document.id}")
            return True
        else:
            print(f"⚠️ Régénération résumé échouée pour doc {document.id}")
            return False

    except Exception as e:
        print(f"⚠️ Erreur déclenchement régénération résumé: {e}")
        return False


def trigger_summary_regeneration_safe(document, user, delay_seconds=5):
    """
    Version sécurisée avec délai pour éviter les régénérations trop fréquentes
    """
    import time
    import threading

    def delayed_regeneration():
        try:
            time.sleep(delay_seconds)  # Attendre un peu pour éviter les appels multiples
            trigger_summary_regeneration(document, user)
        except Exception as e:
            print(f"⚠️ Erreur régénération différée: {e}")

    # Exécuter la régénération dans un thread séparé
    thread = threading.Thread(target=delayed_regeneration)
    thread.daemon = True
    thread.start()

    print(f"🔄 Régénération automatique programmée dans {delay_seconds}s pour doc {document.id}")


# ===== FONCTIONS POUR L'ANNOTATION AUTOMATIQUE PAR IA =====

def find_summary_differences(old_summary, new_summary):
    """Trouve les différences entre deux résumés"""
    import difflib

    old_lines = old_summary.split('\n') if old_summary else []
    new_lines = new_summary.split('\n') if new_summary else []

    differ = difflib.unified_diff(old_lines, new_lines, n=0)

    additions = []
    for line in differ:
        if line.startswith('+') and not line.startswith('+++'):
            additions.append(line[1:].strip())

    return '\n'.join(additions)


def find_best_page_for_annotation(document, entity_value):
    """Trouve la meilleure page pour placer une annotation"""
    # Chercher dans les pages du document celle qui contient le texte
    pages = document.pages.all().order_by('page_number')

    best_page = None
    best_score = 0

    for page in pages:
        text_content = getattr(page, 'cleaned_text', '') or getattr(page, 'text_content', '')
        if text_content:
            text = text_content.lower()
            entity_lower = entity_value.lower()

            # Score basé sur la présence du texte exact ou similaire
            score = 0
            if entity_lower in text:
                score = 100
            else:
                # Recherche de mots-clés similaires
                words = entity_lower.split()
                for word in words:
                    if len(word) > 3 and word in text:
                        score += 20

            if score > best_score:
                best_score = score
                best_page = page

    # Si aucune page pertinente, retourner la première page
    return best_page if best_score > 30 else pages.first()


def create_ai_annotation(page, entity_value, entity_type, user, confidence=0.8):
    """Crée une annotation automatiquement via IA"""
    try:
        # Chercher le texte dans la page
        text_content = getattr(page, 'cleaned_text', '') or getattr(page, 'text_content', '')
        if text_content:
            start_pos = text_content.lower().find(entity_value.lower())

            if start_pos == -1:
                # Si pas trouvé exactement, chercher des mots-clés
                words = entity_value.split()
                for word in words:
                    if len(word) > 3:
                        start_pos = text_content.lower().find(word.lower())
                        if start_pos != -1:
                            entity_value = word  # Utiliser le mot trouvé
                            break

            if start_pos != -1:
                end_pos = start_pos + len(entity_value)

                # Créer ou récupérer le type d'annotation
                annotation_type, created = AnnotationType.objects.get_or_create(
                    name=entity_type,
                    defaults={
                        'display_name': entity_type.replace('_', ' ').title(),
                        'color': '#8b5cf6',  # Violet pour les annotations IA automatiques
                        'description': f"Auto-generated by AI from summary: {entity_type}"
                    }
                )

                # Créer l'annotation
                annotation = Annotation.objects.create(
                    page=page,
                    selected_text=entity_value,
                    annotation_type=annotation_type,
                    start_pos=start_pos,
                    end_pos=end_pos,
                    validation_status='expert_created',  # Pré-validée car créée par expert
                    validated_by=user,
                    validated_at=timezone.now(),
                    created_by=user,
                    source='expert_ai_auto'
                )

                print(f"✅ Annotation IA automatique créée: {entity_value} ({entity_type}) dans page {page.page_number}")
                return annotation

        return None

    except Exception as e:
        print(f"⚠️ Erreur création annotation automatique: {e}")
        return None


def await_ai_extract_and_annotate(document, old_summary, new_summary, allowed_keys, user, page_id=None):
    """
    Version améliorée qui limite les annotations à la page spécifique
    et vérifie que le texte existe vraiment avant de créer l'annotation.
    """
    try:
        from rawdocs.groq_annotation_system import GroqAnnotator
        from django.utils import timezone
        from django.db.models import Q

        # Si page_id est fourni, on travaille uniquement sur cette page
        if page_id:
            target_page = DocumentPage.objects.filter(id=page_id).first()
            if not target_page:
                print(f"⚠️ Page {page_id} non trouvée")
                return {}
        else:
            target_page = None

        # ---------- helpers dates (inchangé) ----------
        MONTHS_EN = {
            "january": "01","jan": "01","february": "02","feb": "02","march": "03","mar": "03",
            "april": "04","apr": "04","may": "05","june": "06","jun": "06","july": "07","jul": "07",
            "august": "08","aug": "08","september": "09","sep": "09","sept":"09",
            "october": "10","oct": "10","november": "11","nov": "11","december": "12","dec": "12"
        }
        MONTHS_FR = {
            "janvier":"01","février":"02","fevrier":"02","mars":"03","avril":"04","mai":"05","juin":"06",
            "juillet":"07","août":"08","aout":"08","septembre":"09","octobre":"10","novembre":"11",
            "décembre":"12","decembre":"12"
        }
        MONTHS_ALL = {**MONTHS_EN, **MONTHS_FR}

        def _norm(s: str) -> str:
            return re.sub(r"\s+", " ", (s or "").strip())

        def _canonical_date_key():
            # choisit une clé Date existante si possible
            for k in ["Date", "Effective Date", "Publication Date", "Update Date", "Deadline", "Start Date"]:
                canon = _canonical_key(k, allowed_keys)
                if canon:
                    return canon
            return None

        DATE_KEY = _canonical_date_key()

        # détecte toute forme de date (jour-mois-année, mois-année, numériques…)
        DAY = r"(0?[1-9]|[12]\d|3[01])"
        YEAR = r"(?:19|20)\d{2}"
        MONTH_TXT = r"[A-Za-zéèêëàâîïôöùûü]{3,}"
        MONTH_NUM = r"(0?[1-9]|1[0-2])"
        # formes texte et numériques
        RX_DATE_TEXT_1 = re.compile(rf"(?i)\b{DAY}\s+({MONTH_TXT})\s*,?\s*({YEAR})\b")
        RX_DATE_TEXT_2 = re.compile(rf"(?i)\b({MONTH_TXT})\s+{DAY}\s*,?\s*({YEAR})\b")
        RX_DATE_MY     = re.compile(rf"(?i)\b({MONTH_TXT})\s*,?\s*({YEAR})\b")
        RX_NUM_DMY     = re.compile(rf"\b{DAY}[/\-\.]{MONTH_NUM}[/\-\.]{YEAR}\b")
        RX_NUM_YMD     = re.compile(rf"\b{YEAR}[/\-\.]{MONTH_NUM}[/\-\.]{DAY}\b")
        RX_NUM_MY      = re.compile(rf"\b{MONTH_NUM}[/\-\.]{YEAR}\b")
        RX_NUM_YM      = re.compile(rf"\b{YEAR}[/\-\.]{MONTH_NUM}\b")

        def _is_date_token(s: str) -> bool:
            x = (s or "").strip()
            return bool(
                RX_DATE_TEXT_1.search(x) or RX_DATE_TEXT_2.search(x) or RX_DATE_MY.search(x) or
                RX_NUM_DMY.search(x) or RX_NUM_YMD.search(x) or RX_NUM_MY.search(x) or RX_NUM_YM.search(x)
            )

        def _expand_date_variants(s: str) -> list[str]:
            """
            À partir d'une forme '5 June 2014' ou '5 Jun 2014' ou '5 juin 2014', génère :
            - '5 Jun 2014' / 'June 5, 2014' / '05/06/2014' / '2014-06-05'
            - si mois-année seulement → 'Jun 2014' / '06/2014' / '2014-06'
            """
            s = _norm(s)
            out = {s}

            def month_num(mtxt: str) -> str | None:
                return MONTHS_ALL.get((mtxt or "").lower())

            # cas: 5 June 2014
            m = RX_DATE_TEXT_1.search(s)
            if m:
                d = int(m.group(1))
                mtxt = m.group(2)
                y = m.group(3)
                mm = month_num(mtxt)
                if mm:
                    out.add(f"{d} {mtxt[:3].title()} {y}")         # 5 Jun 2014
                    out.add(f"{mtxt.title()} {d}, {y}")           # June 5, 2014
                    out.add(f"{d:02d}/{mm}/{y}")                  # 05/06/2014
                    out.add(f"{y}-{mm}-{d:02d}")                  # 2014-06-05
            # cas: June 5, 2014
            m = RX_DATE_TEXT_2.search(s)
            if m:
                mtxt = m.group(1)
                d = int(m.group(2))
                y = m.group(3)
                mm = month_num(mtxt)
                if mm:
                    out.add(f"{d} {mtxt[:3].title()} {y}")
                    out.add(f"{d:02d}/{mm}/{y}")
                    out.add(f"{y}-{mm}-{d:02d}")
            # cas: Month Year (January 2013 / 01/2013 / 2013-01)
            m = RX_DATE_MY.search(s)
            if m:
                mtxt = m.group(1)
                y = m.group(2)
                mm = month_num(mtxt)
                if mm:
                    out.add(f"{mtxt[:3].title()} {y}")            # Jan 2013
                    out.add(f"{mm}/{y}")                          # 01/2013
                    out.add(f"{y}-{mm}")                          # 2013-01
                    out.add(re.sub(r"(?i)\b([A-Za-zéèêëàâîïôöùûü]+)\s+(\d{{4}})\b", r"\1, \2", s))  # January, 2013
            # numériques → générer quelques tournures inverses
            m = RX_NUM_DMY.search(s)
            if m:
                d, mm, y = m.group(1), m.group(2), re.search(YEAR, s).group(0)
                # essayer avec mois texte anglais (si possible)
                inv = {k: v for k, v in MONTHS_EN.items() if v == f"{int(mm):02d}"}
                if inv:
                    mtxt = sorted(inv.keys(), key=len)[-1]  # 'june' > 'jun'
                    out.add(f"{int(d)} {mtxt.title()} {y}")
                    out.add(f"{mtxt.title()} {int(d)}, {y}")
                out.add(f"{y}-{int(mm):02d}-{int(d):02d}")
            m = RX_NUM_YMD.search(s)
            if m:
                y, mm, d = m.group(1), m.group(2), m.group(3)
                inv = {k: v for k, v in MONTHS_EN.items() if v == f"{int(mm):02d}"}
                if inv:
                    mtxt = sorted(inv.keys(), key=len)[-1]
                    out.add(f"{int(d)} {mtxt.title()} {y}")
                    out.add(f"{mtxt.title()} {int(d)}, {y}")
                out.add(f"{int(d):02d}/{int(mm):02d}/{y}")

            return list(out)

        def _coerce_type_for_value(raw_type: str, value: str) -> str:
            # force Date si le token ressemble à une date
            if DATE_KEY and _is_date_token(value):
                return DATE_KEY
            return _canonical_key(raw_type, allowed_keys) or raw_type

        # ---------- extraction locale des entités dans un résumé ----------
        def _extract_entities(summary: str) -> dict[str, list[str]]:
            summary = summary or ""
            by_text = extract_entities_from_text(summary) or {}
            out: dict[str, list[str]] = {}

            # 1) capturer explicitement toutes les dates sous toutes formes
            dates = set()
            for rx in (RX_DATE_TEXT_1, RX_DATE_TEXT_2, RX_DATE_MY, RX_NUM_DMY, RX_NUM_YMD, RX_NUM_MY, RX_NUM_YM):
                for m in rx.finditer(summary):
                    dates.add(_norm(m.group(0)))
            if DATE_KEY and dates:
                out[DATE_KEY] = sorted(dates)

            # 2) fusionner avec heuristique générique et recanoniser
            for raw_k, vals in (by_text or {}).items():
                for v in (vals or []):
                    v = _norm(v)
                    k2 = _coerce_type_for_value(raw_k, v)
                    out.setdefault(k2, [])
                    if v and v not in out[k2]:
                        out[k2].append(v)

            # dédup
            for k, vals in list(out.items()):
                out[k] = list({v.lower(): v for v in vals}.values())
                if not out[k]:
                    del out[k]
            return out

        # ---------- diff entités (ajouts / retraits) ----------
        def _diff_entities(old_sum: str, new_sum: str) -> tuple[dict, dict]:
            old_e = _extract_entities(old_sum)
            new_e = _extract_entities(new_sum)
            added, removed = {}, {}
            key = lambda s: s.lower()

            for t in set(old_e) | set(new_e):
                old_vals = {key(v): v for v in old_e.get(t, [])}
                new_vals = {key(v): v for v in new_e.get(t, [])}
                add_keys = set(new_vals) - set(old_vals)
                rem_keys = set(old_vals) - set(new_vals)
                if add_keys:
                    added[t] = [new_vals[k] for k in add_keys]
                if rem_keys:
                    removed[t] = [old_vals[k] for k in rem_keys]
            return added, removed

        # met en rejected les anciennes valeurs
        def _deselect_existing_annotation(document, entity_type_canon: str, value: str):
            try:
                qs_type = AnnotationType.objects.filter(
                    Q(name__iexact=entity_type_canon) | Q(display_name__iexact=entity_type_canon)
                )
                if not qs_type.exists():
                    return 0
                qs = Annotation.objects.filter(
                    page__document=document,
                    annotation_type__in=list(qs_type),
                    selected_text__iexact=value,
                    validation_status__in=['pending', 'validated', 'expert_created']
                )
                n = 0
                for ann in qs:
                    ann.validation_status = 'rejected'
                    ann.validated_by = user
                    ann.validated_at = timezone.now()
                    ann.save(update_fields=['validation_status','validated_by','validated_at'])
                    n += 1
                return n
            except Exception as e:
                print(f"⚠️ Deselect error {entity_type_canon}='{value}': {e}")
                return 0

        # ---------- pipeline principal ----------
                # ---------- extraction des changements ----------
                added_local, removed_local = _diff_entities(old_summary or "", new_summary or "")

                # Option IA : enrichissement (optionnel)
                ai_added, ai_removed = {}, {}
                if not added_local and not removed_local:
                    # Si pas de changements détectés localement, demander à l'IA
                    try:
                        diff_text = find_summary_differences(old_summary or "", new_summary or "")
                        if diff_text.strip():
                            ga = GroqAnnotator()
                            prompt = f"""
        Analyse les changements dans ce résumé et identifie les entités à annoter.
        IMPORTANT: Ne retourne QUE les entités qui sont NOUVELLES ou MODIFIÉES.

        Types autorisés: {', '.join(allowed_keys)}

        Ancien résumé:
        {old_summary[:500]}

        Nouveau résumé:
        {new_summary[:500]}

        Changements détectés:
        {diff_text}

        Réponds en JSON strict:
        {{
          "added": {{ "<Type>": ["valeur exacte dans le texte"] }},
          "removed": {{ "<Type>": ["valeur supprimée"] }}
        }}
        """
                            raw = ga.complete_text(prompt, max_tokens=700, temperature=0.0)
                            if raw:
                                try:
                                    data = json.loads(raw) if isinstance(raw, str) else raw
                                    ai_added = data.get("added", {}) or {}
                                    ai_removed = data.get("removed", {}) or {}
                                except Exception:
                                    pass
                    except Exception as e:
                        print(f"⚠️ IA assist skipped: {e}")

                # Fusionner les résultats
                added_all = _merge(added_local, ai_added)
                removed_all = _merge(removed_local, ai_removed)

                # 1) Désélection des valeurs retirées (inchangé)
                for etype, values in (removed_all or {}).items():
                    for val in values:
                        if target_page:
                            # Désélectionner uniquement sur la page cible
                            _deselect_annotation_on_page(target_page, etype, val, user)
                        else:
                            _deselect_existing_annotation(document, etype, val, user)

                # 2) Création des annotations UNIQUEMENT sur la page spécifiée
                created_map: dict[str, list[str]] = {}

                for etype, values in (added_all or {}).items():
                    for val in values:
                        if target_page:
                            # Créer l'annotation UNIQUEMENT si le texte existe dans la page
                            success = create_annotation_if_text_exists(
                                target_page, val, etype, user, confidence=0.9
                            )
                            if success:
                                created_map.setdefault(etype, []).append(val)
                        else:
                            # Comportement original pour le document complet
                            page = find_best_page_for_annotation(document, val)
                            if page:
                                ann = create_ai_annotation(page, val, etype, user, confidence=0.9)
                                if ann:
                                    created_map.setdefault(etype, []).append(val)

                return created_map

            except Exception as e:
                print(f"⚠️ Erreur annotation IA automatique: {e}")
                return {}

    except Exception as e:
        print(f"⚠️ Erreur annotation IA automatique: {e}")
        return {}


def create_annotation_if_text_exists(page, entity_value, entity_type, user, confidence=0.9):
    """
    Crée une annotation SEULEMENT si le texte existe vraiment dans la page.
    Utilise plusieurs stratégies de recherche pour être plus robuste.
    """
    try:
        # Obtenir le texte de la page
        page_text = _get_page_text(page)
        if not page_text:
            print(f"⚠️ Page {page.page_number} sans texte")
            return False

        # Stratégies de recherche dans l'ordre de préférence
        search_results = []

        # 1. Recherche exacte
        exact_pos = page_text.lower().find(entity_value.lower())
        if exact_pos >= 0:
            search_results.append({
                'start': exact_pos,
                'end': exact_pos + len(entity_value),
                'text': page_text[exact_pos:exact_pos + len(entity_value)],
                'confidence': 1.0
            })

        # 2. Recherche avec normalisation des espaces
        normalized_entity = re.sub(r'\s+', ' ', entity_value.strip())
        normalized_text = re.sub(r'\s+', ' ', page_text)
        norm_pos = normalized_text.lower().find(normalized_entity.lower())
        if norm_pos >= 0 and not search_results:
            # Ajuster la position pour le texte original
            real_pos = find_real_position(page_text, normalized_text, norm_pos)
            if real_pos >= 0:
                search_results.append({
                    'start': real_pos,
                    'end': real_pos + len(normalized_entity),
                    'text': page_text[real_pos:real_pos + len(normalized_entity)],
                    'confidence': 0.95
                })

        # 3. Recherche flexible pour les dates
        if 'date' in entity_type.lower() or 'deadline' in entity_type.lower():
            date_result = find_date_in_page_text(entity_value, page_text)
            if date_result and not search_results:
                search_results.append(date_result)

        # 4. Recherche par mots-clés significatifs
        if not search_results:
            keywords = extract_significant_keywords(entity_value)
            if keywords:
                keyword_result = find_by_keywords_in_page(keywords, page_text, entity_value)
                if keyword_result:
                    search_results.append(keyword_result)

        # Si aucun résultat, on n'annote pas
        if not search_results:
            print(f"⚠️ Texte '{entity_value}' non trouvé dans page {page.page_number}")
            return False

        # Utiliser le meilleur résultat
        best_result = max(search_results, key=lambda x: x['confidence'])

        # Créer l'annotation uniquement si la confiance est suffisante
        if best_result['confidence'] < 0.5:
            print(f"⚠️ Confiance trop faible ({best_result['confidence']}) pour '{entity_value}'")
            return False

        # Créer ou récupérer le type d'annotation
        annotation_type, _ = AnnotationType.objects.get_or_create(
            name=entity_type,
            defaults={
                'display_name': entity_type.replace('_', ' ').title(),
                'color': '#8b5cf6',
                'description': f"Auto-generated by AI from summary: {entity_type}"
            }
        )

        # Vérifier qu'une annotation similaire n'existe pas déjà
        existing = Annotation.objects.filter(
            page=page,
            annotation_type=annotation_type,
            start_pos__lte=best_result['start'] + 5,
            start_pos__gte=best_result['start'] - 5,
            validation_status__in=['validated', 'expert_created', 'pending']
        ).first()

        if existing:
            print(f"ℹ️ Annotation similaire déjà existante pour '{entity_value}'")
            return False

        # Créer l'annotation
        annotation = Annotation.objects.create(
            page=page,
            selected_text=best_result['text'],
            annotation_type=annotation_type,
            start_pos=best_result['start'],
            end_pos=best_result['end'],
            validation_status='expert_created',
            validated_by=user,
            validated_at=timezone.now(),
            created_by=user,
            source='expert_ai_auto',
            confidence_score=confidence * best_result['confidence']
        )

        print(f"✅ Annotation créée: '{best_result['text']}' ({entity_type}) "
              f"page {page.page_number} pos [{best_result['start']}:{best_result['end']}]")
        return True

    except Exception as e:
        print(f"❌ Erreur création annotation: {e}")
        return False


def find_real_position(original_text, normalized_text, norm_pos):
    """Trouve la position réelle dans le texte original à partir de la position normalisée."""
    if norm_pos < 0:
        return -1

    # Compter les caractères jusqu'à norm_pos dans le texte normalisé
    norm_count = 0
    real_pos = 0

    for i, char in enumerate(original_text):
        if norm_count >= norm_pos:
            return i

        # Si ce n'est pas un espace multiple, compter
        if not (char.isspace() and i > 0 and original_text[i - 1].isspace()):
            norm_count += 1

    return -1


def extract_significant_keywords(text, min_length=4):
    """Extrait les mots-clés significatifs d'un texte."""
    # Mots vides à ignorer
    stopwords = {'le', 'la', 'les', 'de', 'du', 'des', 'un', 'une', 'et', 'ou',
                 'à', 'au', 'aux', 'pour', 'par', 'sur', 'dans', 'avec', 'sans',
                 'the', 'a', 'an', 'and', 'or', 'for', 'by', 'on', 'in', 'with'}

    words = re.findall(r'\b\w+\b', text.lower())
    keywords = [w for w in words if len(w) >= min_length and w not in stopwords]

    # Prioriser les mots commençant par une majuscule (noms propres)
    capitalized = re.findall(r'\b[A-Z]\w+\b', text)

    return capitalized + keywords


def find_by_keywords_in_page(keywords, page_text, original_value):
    """Cherche une séquence de mots-clés dans le texte."""
    if not keywords:
        return None

    page_lower = page_text.lower()
    best_match = None
    best_score = 0

    # Chercher chaque mot-clé
    for keyword in keywords[:3]:  # Limiter aux 3 premiers mots-clés
        keyword_lower = keyword.lower()
        pos = page_lower.find(keyword_lower)

        if pos >= 0:
            # Étendre la recherche autour du mot-clé
            context_start = max(0, pos - 50)
            context_end = min(len(page_text), pos + len(keyword) + 50)
            context = page_text[context_start:context_end]

            # Calculer un score basé sur le nombre de mots-clés trouvés
            score = sum(1 for kw in keywords if kw.lower() in context.lower())

            if score > best_score:
                best_score = score
                best_match = {
                    'start': pos,
                    'end': pos + len(keyword),
                    'text': page_text[pos:pos + len(keyword)],
                    'confidence': min(0.7, score * 0.2)
                }

    return best_match


def find_date_in_page_text(date_value, page_text):
    """Recherche spécialisée pour les dates avec formats multiples."""
    # Utiliser la fonction existante mais adaptée pour retourner le bon format
    start, end, text = find_date_span_in_text(page_text, date_value)

    if start is not None:
        return {
            'start': start,
            'end': end,
            'text': text,
            'confidence': 0.9
        }

    # Essayer d'autres formats de date
    # ... (logique additionnelle si nécessaire)

    return None


def _deselect_annotation_on_page(page, entity_type_canon, value, user):
    """Désélectionne les annotations uniquement sur une page spécifique."""
    try:
        from django.db.models import Q

        qs_type = AnnotationType.objects.filter(
            Q(name__iexact=entity_type_canon) | Q(display_name__iexact=entity_type_canon)
        )

        if not qs_type.exists():
            return 0

        qs = Annotation.objects.filter(
            page=page,  # Limiter à la page spécifique
            annotation_type__in=list(qs_type),
            selected_text__iexact=value,
            validation_status__in=['pending', 'validated', 'expert_created']
        )

        count = 0
        for ann in qs:
            ann.validation_status = 'rejected'
            ann.validated_by = user
            ann.validated_at = timezone.now()
            ann.save(update_fields=['validation_status', 'validated_by', 'validated_at'])
            count += 1

        if count > 0:
            print(f"ℹ️ {count} annotation(s) désélectionnée(s) pour '{value}' sur page {page.page_number}")

        return count

    except Exception as e:
        print(f"⚠️ Erreur désélection: {e}")
        return 0
def enhance_summary_with_ai(document, entities, basic_summary):
    """
    Utilise l'IA pour enrichir le résumé généré automatiquement
    """
    try:
        from rawdocs.groq_annotation_system import GroqAnnotator

        groq_annotator = GroqAnnotator()

        # Construire le contexte pour l'IA
        entities_text = ""
        for entity_type, values in entities.items():
            if values:
                entities_text += f"- {entity_type}: {', '.join(values[:3])}\n"

        prompt = f"""
Améliore ce résumé pharmaceutique en ajoutant du contexte et des détails pertinents basés sur les entités extraites.

Document: {document.title}
Type: {getattr(document, 'doc_type', 'Pharmaceutique')}

Résumé de base:
{basic_summary}

Entités identifiées:
{entities_text}

Instructions:
1. Garde toutes les informations du résumé original
2. Ajoute des connexions logiques entre les entités
3. Enrichis avec du contexte pharmaceutique pertinent
4. Maintiens un ton professionnel et précis
5. Maximum 300 mots

Résumé enrichi:"""

        response = groq_annotator.complete_text(prompt, max_tokens=800)

        if response and len(response.strip()) > len(basic_summary):
            return response.strip()

        return basic_summary

    except Exception as e:
        print(f"⚠️ Erreur enrichissement résumé: {e}")
        return basic_summary


# ===== FONCTION DE NETTOYAGE POUR LA MAINTENANCE =====

def cleanup_regeneration_cache():
    """Nettoie le cache des régénérations (à appeler périodiquement)"""
    import time
    current_time = time.time()

    # Supprimer les entrées anciennes
    expired_keys = [
        doc_id for doc_id, timestamp in REGENERATION_CACHE.items()
        if current_time - timestamp > CACHE_DURATION * 2
    ]

    for key in expired_keys:
        del REGENERATION_CACHE[key]

    if expired_keys:
        print(f"🧹 Cache régénération nettoyé: {len(expired_keys)} entrées supprimées")


# ===== DÉCORATEUR POUR EVITER LES APPELS TROP FREQUENTS =====

def with_regeneration_throttle(delay_seconds=5):
    """Décorateur pour limiter la fréquence des régénérations"""

    def decorator(func):
        def wrapper(document, user, *args, **kwargs):
            if should_regenerate_summary(document.id):
                import threading
                import time

                def delayed_execution():
                    time.sleep(delay_seconds)
                    func(document, user, *args, **kwargs)

                thread = threading.Thread(target=delayed_execution)
                thread.daemon = True
                thread.start()

                return True
            else:
                print(f"⏰ Fonction {func.__name__} throttlée pour doc {document.id}")
                return False

        return wrapper

    return decorator


# Usage avec le décorateur:
# @with_regeneration_throttle(delay_seconds=3)
# def my_regeneration_function(document, user):
#     # votre code ici
# expert/views.py

@expert_required
@csrf_exempt
def expert_ai_annotate_page_groq(request, page_id):
    """
    Version corrigée qui gère les erreurs API et le nouveau format de retour GROQ
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        page = get_object_or_404(DocumentPage, id=page_id)
        page_text = _get_page_text(page)

        if not page_text.strip():
            return JsonResponse({
                'success': False,
                'error': "Aucun texte exploitable sur la page."
            }, status=400)

        # Vérification de l'API GROQ
        try:
            from rawdocs.groq_annotation_system import GroqAnnotator
            groq_annotator = GroqAnnotator()

            # Vérifier si GROQ est disponible
            if not groq_annotator.enabled:
                return JsonResponse({
                    'success': False,
                    'error': "API GROQ non configurée ou clé invalide (erreur 401)",
                    'message': "Veuillez vérifier votre clé API GROQ dans les paramètres.",
                    'fallback_available': True
                })

        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': f"Erreur initialisation GROQ: {str(e)}",
                'fallback_available': True
            })

        # Appel GROQ avec gestion du nouveau format de retour
        try:
            page_data = {
                'page_num': page.page_number,
                'text': page_text,
                'char_count': len(page_text)
            }

            # CORRECTION : La nouvelle version retourne seulement une liste
            raw_annotations = groq_annotator.annotate_page_with_groq(page_data)

            # Récupérer le schéma depuis l'attribut last_schema
            annotation_schema = getattr(groq_annotator, 'last_schema', [])

            if not isinstance(raw_annotations, list):
                raise Exception(f"Format de retour GROQ inattendu: {type(raw_annotations)}")

            print(f"✅ GROQ retour: {len(raw_annotations)} annotations, {len(annotation_schema)} types")

        except Exception as e:
            error_msg = str(e)
            print(f"❌ Erreur appel GROQ: {error_msg}")

            if "401" in error_msg or "invalide" in error_msg:
                return JsonResponse({
                    'success': False,
                    'error': "Clé API GROQ invalide ou expirée",
                    'message': "Veuillez renouveler votre clé API GROQ.",
                    'groq_status': 'unauthorized'
                })
            else:
                return JsonResponse({
                    'success': False,
                    'error': f"Erreur technique GROQ: {error_msg}",
                    'fallback_available': True
                })

        # Normaliser les annotations (nouveau format)
        entities = []
        for item in raw_annotations:
            if isinstance(item, dict):
                entities.append({
                    "type": item.get('type', ''),
                    "text": item.get('text', ''),
                    "start_pos": item.get('start_pos', 0),
                    "end_pos": item.get('end_pos', 0)
                })

        if not entities:
            return JsonResponse({
                'success': True,
                'annotations': [],
                'message': "GROQ connecté mais aucune entité détectée.",
                'page_summary': getattr(page, 'annotations_summary', None)
            })

        # Création des annotations
        saved = []
        for item in entities:
            try:
                etype = (item.get('type') or '').strip()
                etext = (item.get('text') or '').strip()

                if not etype or not etext:
                    continue

                # Créer le type d'annotation
                annotation_type, created = AnnotationType.objects.get_or_create(
                    name=etype,
                    defaults={
                        'display_name': etype.replace('_', ' ').title(),
                        'color': '#3b82f6',
                        'description': f"GROQ AI type: {etype}"
                    }
                )

                # Positions sécurisées
                sp = max(0, int(item.get('start_pos', 0)))
                ep = max(sp + 1, min(int(item.get('end_pos', sp + len(etext))), len(page_text)))

                # Créer l'annotation
                annotation = Annotation.objects.create(
                    page=page,
                    selected_text=etext,
                    annotation_type=annotation_type,
                    start_pos=sp,
                    end_pos=ep,
                    validation_status='expert_created',
                    validated_by=request.user,
                    validated_at=timezone.now(),
                    created_by=request.user,
                    source='expert_groq_ai'
                )

                saved.append({
                    'id': annotation.id,
                    'text': annotation.selected_text,
                    'type': annotation.annotation_type.display_name,
                    'start_pos': annotation.start_pos,
                    'end_pos': annotation.end_pos
                })

            except Exception as e:
                print(f"⚠️ Erreur création annotation '{etext}': {e}")
                continue

        # Mise à jour JSON
        try:
            new_page_summary, _ = build_page_summary_and_json(page, request.user)

            # JSON document
            all_annotations = Annotation.objects.filter(
                page__document=page.document,
                validation_status__in=['validated', 'expert_created']
            ).select_related('annotation_type', 'page').order_by('page__page_number', 'start_pos')

            from rawdocs.views import _build_entities_map
            document_entities = _build_entities_map(all_annotations, use_display_name=True)

            document_json = {
                'document': {
                    'id': str(page.document.id),
                    'title': page.document.title,
                    'total_pages': page.document.total_pages,
                    'total_annotations': all_annotations.count(),
                },
                'entities': document_entities,
                'generated_at': timezone.now().isoformat(),
            }

            page.document.global_annotations_json = document_json
            page.document.save(update_fields=['global_annotations_json'])

        except Exception as e:
            print(f"⚠️ Erreur mise à jour JSON: {e}")

        return JsonResponse({
            'success': True,
            'annotations': saved,
            'message': f"{len(saved)} annotation(s) créée(s) par GROQ",
            'page_summary': getattr(page, 'annotations_summary', ''),
            'groq_status': 'success'
        })

    except Exception as e:
        print(f"❌ Erreur critique: {e}")
        return JsonResponse({
            'success': False,
            'error': f"Erreur système: {str(e)}",
            'fallback_available': True
        }, status=500)

@expert_required
@csrf_exempt
def expert_save_manual_annotation(request):
    """
    Création d'une annotation manuelle (pré-validée) + MAJ JSON page/doc + régénération automatique
    du résumé de la page + retour du nouveau résumé.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        data = json.loads(request.body)
        page_id = data.get('page_id')
        selected_text = data.get('selected_text', '').strip()
        entity_type = (data.get('entity_type') or '').strip()
        if not entity_type:
            return JsonResponse({'success': False, 'error': 'entity_type is required'})

        start_pos = int(data.get('start_pos', 0) or 0)
        end_pos = int(data.get('end_pos', 0) or 0)

        page = get_object_or_404(DocumentPage, id=page_id)

        annotation_type, _ = AnnotationType.objects.get_or_create(
            name=entity_type,
            defaults={
                'display_name': entity_type.replace('_', ' ').title(),
                'color': '#3b82f6',
                'description': f"Expert manual type: {entity_type}"
            }
        )

        annotation = Annotation.objects.create(
            page=page,
            selected_text=selected_text,
            annotation_type=annotation_type,
            start_pos=start_pos,
            end_pos=end_pos if end_pos > start_pos else start_pos + len(selected_text),
            validation_status='expert_created',
            validated_by=request.user,
            validated_at=timezone.now(),
            created_by=request.user,
            source='expert_manual'
        )

        # LOG (facultatif) ...
        # log_expert_action(...)

        # ===== MAJ JSON PAGE & DOC =====
        try:
            # page
            build_page_summary_and_json(page, request.user)

            # doc
            all_annotations = Annotation.objects.filter(
                page__document=page.document,
                validation_status__in=['validated', 'expert_created']
            ).select_related('annotation_type', 'page').order_by('page__page_number', 'start_pos')

            from rawdocs.views import _build_entities_map
            document_entities = _build_entities_map(all_annotations, use_display_name=True)

            document_json = {
                'document': {
                    'id': str(page.document.id),
                    'title': page.document.title,
                    'doc_type': getattr(page.document, 'doc_type', None),
                    'source': getattr(page.document, 'source', None),
                    'total_pages': page.document.total_pages,
                    'total_annotations': all_annotations.count(),
                },
                'entities': document_entities,
                'generated_at': datetime.utcnow().isoformat() + 'Z',
            }
            page.document.global_annotations_json = document_json
            page.document.save(update_fields=['global_annotations_json'])

            # résumé global (asynchrone / throttlé)
            try:
                trigger_summary_regeneration_safe(page.document, request.user, 3)
            except Exception as e:
                print(f"⚠️ Erreur déclenchement régénération document (manual): {e}")

        except Exception as e:
            print(f"❌ Erreur MAJ JSON/summary (manual): {e}")

        return JsonResponse({
            'success': True,
            'annotation_id': annotation.id,
            'message': 'Annotation sauvegardée avec succès et JSON mis à jour',
            'page_summary': page.annotations_summary,
            'auto_summary_triggered': True
        })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@expert_required
def expert_get_page_annotations(request, page_id):
    """Récupération des annotations d'une page pour Expert - copie de rawdocs.views.get_page_annotations"""
    try:
        page = get_object_or_404(DocumentPage, id=page_id)
        annotations = page.annotations.filter(
            validation_status__in=['pending', 'validated', 'expert_created', 'rejected']
        ).select_related('annotation_type').order_by('start_pos')

        annotations_data = []
        for annotation in annotations:
            annotations_data.append({
                'id': annotation.id,
                'selected_text': annotation.selected_text,  # Match the JavaScript expectation
                'type_display': annotation.annotation_type.display_name,  # Match the JavaScript expectation
                'type': annotation.annotation_type.name,
                'color': annotation.annotation_type.color,  # Add the color
                'start_pos': annotation.start_pos,
                'end_pos': annotation.end_pos,
                'validation_status': annotation.validation_status,
                'created_at': annotation.created_at.isoformat() if annotation.created_at else None,
                'validated_at': annotation.validated_at.isoformat() if annotation.validated_at else None,
                'validated_by': annotation.validated_by.username if annotation.validated_by else None,
            })

        return JsonResponse({
            'success': True,
            'annotations': annotations_data
        })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@expert_required
@csrf_exempt
def expert_delete_annotation(request, annotation_id):
    """
    Suppression d'annotation + MAJ JSON page/doc + régénération résumé page + retour résumé.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        ann = get_object_or_404(Annotation, id=annotation_id)
        page = ann.page
        document = page.document

        ann.delete()

        try:
            # MAJ page (entities + summary + json)
            new_page_summary, _ = build_page_summary_and_json(page, request.user)

            # MAJ doc
            all_annotations = Annotation.objects.filter(
                page__document=document,
                validation_status__in=['validated', 'expert_created']
            ).select_related('annotation_type', 'page').order_by('page__page_number', 'start_pos')

            from rawdocs.views import _build_entities_map
            document_entities = _build_entities_map(all_annotations, use_display_name=True)
            document_json = {
                'document': {
                    'id': str(document.id),
                    'title': document.title,
                    'doc_type': getattr(document, 'doc_type', None),
                    'source': getattr(document, 'source', None),
                    'total_pages': document.total_pages,
                    'total_annotations': all_annotations.count(),
                },
                'entities': document_entities,
                'generated_at': datetime.utcnow().isoformat() + 'Z',
            }
            document.global_annotations_json = document_json
            document.save(update_fields=['global_annotations_json'])

            try:
                trigger_summary_regeneration_safe(document, request.user, 3)
            except Exception as e:
                print(f"⚠️ Erreur déclenchement régénération après suppression: {e}")

        except Exception as e:
            print(f"❌ Erreur MAJ JSON/summary (delete): {e}")
            new_page_summary = None

        return JsonResponse({'success': True, 'message': 'Annotation supprimée', 'page_summary': new_page_summary})

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@expert_required
@csrf_exempt
def expert_validate_page_annotations(request, page_id):
    """Validation des annotations d'une page pour Expert - copie de rawdocs.views.validate_page_annotations"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        page = get_object_or_404(DocumentPage, id=page_id)

        # Valider toutes les annotations de la page
        annotations = page.annotations.filter(validation_status='pending')
        validated_count = 0

        for annotation in annotations:
            annotation.validation_status = 'validated'
            annotation.validated_by = request.user
            annotation.validated_at = timezone.now()
            annotation.save()
            validated_count += 1

            # LOG ACTION
            log_expert_action(
                user=request.user,
                action='annotation_validated',
                annotation=annotation,
                reason=f"Bulk validation by expert for page {page.page_number}"
            )

        return JsonResponse({
            'success': True,
            'validated_count': validated_count,
            'message': f'{validated_count} annotations validées'
        })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@expert_required
@csrf_exempt
def expert_generate_page_annotation_summary(request, page_id):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        page = get_object_or_404(DocumentPage, id=page_id)
        summary, entities_map = build_page_summary_and_json(page, request.user)

        # (optionnel) mettre aussi à jour le JSON global du document pour rester cohérent
        from rawdocs.views import _build_entities_map
        all_doc_anns = (
            Annotation.objects
            .filter(page__document=page.document, validation_status__in=['validated', 'expert_created'])
            .select_related('annotation_type', 'page')
            .order_by('page__page_number', 'start_pos')
        )
        doc_entities = _build_entities_map(all_doc_anns, use_display_name=True)
        from datetime import datetime as _dt
        page.document.global_annotations_json = {
            'document': {
                'id': str(page.document.id),
                'title': page.document.title,
                'doc_type': getattr(page.document, 'doc_type', None),
                'source': getattr(page.document, 'source', None),
                'total_pages': page.document.total_pages,
                'total_annotations': all_doc_anns.count(),
            },
            'entities': doc_entities,
            'generated_at': _dt.utcnow().isoformat() + 'Z',
        }
        page.document.save(update_fields=['global_annotations_json'])

        return JsonResponse({
            'success': True,
            'summary': summary,
            'entities': entities_map,
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@expert_required
@csrf_exempt
def expert_generate_document_annotation_summary(request, doc_id):
    """Génération du JSON et résumé global pour un document - Expert - copie de rawdocs.views.generate_document_annotation_summary"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        document = get_object_or_404(RawDocument, id=doc_id, is_validated=True)

        # Récupérer toutes les annotations du document
        all_annotations = Annotation.objects.filter(
            page__document=document
        ).select_related('annotation_type', 'page').order_by('page__page_number', 'start_pos')

        # Construire entities -> [valeurs] (utiliser la fonction de rawdocs)
        from rawdocs.views import _build_entities_map, generate_entities_based_document_summary
        entities = _build_entities_map(all_annotations, use_display_name=True)

        # JSON global minimaliste
        document_json = {
            'document': {
                'id': str(document.id),
                'title': document.title,
                'doc_type': getattr(document, 'doc_type', None),
                'source': getattr(document, 'source', None),
                'total_pages': document.total_pages,
                'total_annotations': all_annotations.count(),
            },
            'entities': entities,
            'generated_at': datetime.utcnow().isoformat() + 'Z',
        }

        # Résumé à partir des seules entités/valeurs
        summary = generate_entities_based_document_summary(
            entities=entities,
            doc_title=document.title,
            doc_type=getattr(document, 'doc_type', None),
            total_annotations=all_annotations.count()
        )

        # Sauvegarde
        document.global_annotations_json = document_json
        document.global_annotations_summary = summary
        document.global_annotations_summary_generated_at = timezone.now()
        document.save(update_fields=['global_annotations_json', 'global_annotations_summary',
                                     'global_annotations_summary_generated_at'])

        return JsonResponse({
            'success': True,
            'document_json': document_json,
            'summary': summary,
            'message': f'JSON et résumé globaux générés pour le document'
        })
    except Exception as e:
        print(f"❌ Erreur génération résumé document {doc_id}: {e}")
        return JsonResponse({'error': f'Erreur lors de la génération: {str(e)}'}, status=500)


@expert_required
def expert_view_page_annotation_json(request, page_id):
    """Visualisation du JSON et résumé d'une page - Expert avec navigation"""
    try:
        page = get_object_or_404(DocumentPage, id=page_id)
        document = page.document

        # Si pas encore généré, le générer
        if not hasattr(page, 'annotations_json') or not page.annotations_json:
            from django.test import RequestFactory
            factory = RequestFactory()
            fake_request = factory.post(f'/expert/annotation/page/{page_id}/generate-summary/')
            fake_request.user = request.user
            expert_generate_page_annotation_summary(fake_request, page_id)
            page.refresh_from_db()

        # Calculate navigation info
        current_page_num = page.page_number
        next_page_num = current_page_num + 1 if current_page_num < document.total_pages else None
        is_last_page = current_page_num >= document.total_pages

        context = {
            'page': page,
            'document': document,
            'annotations_json': page.annotations_json if hasattr(page, 'annotations_json') else None,
            'annotations_summary': page.annotations_summary if hasattr(page, 'annotations_summary') else None,
            'total_annotations': page.annotations.count(),
            'current_page_num': current_page_num,
            'next_page_num': next_page_num,
            'is_last_page': is_last_page,
            'total_pages': document.total_pages,
        }

        return render(request, 'expert/view_page_annotation_json.html', context)

    except Exception as e:
        messages.error(request, f"Erreur: {str(e)}")
        return redirect('expert:annotation_dashboard')

@expert_required
def expert_view_document_annotation_json(request, doc_id):
    """Visualisation et édition du JSON et résumé global d'un document - Expert avec analyse réglementaire"""
    try:
        document = get_object_or_404(RawDocument, id=doc_id, is_validated=True)

        if request.method == 'POST' and request.headers.get('x-requested-with') == 'XMLHttpRequest':
            # Mode édition AJAX
            try:
                data = json.loads(request.body)
                action = data.get('action', '')

                if action == 'save_summary':
                    # Déléguer à la fonction existante
                    return save_summary_changes(request, doc_id)
                elif action == 'save_json':
                    # Déléguer à la fonction existante
                    return save_document_json(request, doc_id)
                else:
                    return JsonResponse({'error': 'Action non reconnue'}, status=400)
            except Exception as e:
                return JsonResponse({'error': str(e)}, status=500)

        # Mode affichage GET
        # Si pas encore généré, le générer
        if not hasattr(document, 'global_annotations_json') or not document.global_annotations_json:
            # Déclencher la génération
            from django.test import RequestFactory
            factory = RequestFactory()
            fake_request = factory.post(f'/expert/annotation/document/{doc_id}/generate-summary/')
            fake_request.user = request.user
            expert_generate_document_annotation_summary(fake_request, doc_id)
            document.refresh_from_db()

        # Enrichir le contexte pour l'édition
        document_json = document.global_annotations_json if hasattr(document, 'global_annotations_json') else {}
        allowed_entity_types = list(document_json.get('entities', {}).keys())
        document_summary = document.global_annotations_summary if hasattr(document, 'global_annotations_summary') else ""

        # Statistiques des annotations
        total_annotations = sum(page.annotations.count() for page in document.pages.all())
        annotated_pages = document.pages.filter(annotations__isnull=False).distinct().count()

        # Get regulatory analysis data
        try:
            from rawdocs.models import DocumentRegulatoryAnalysis
            regulatory_analysis = document.regulatory_analysis
            has_regulatory_analysis = True
        except DocumentRegulatoryAnalysis.DoesNotExist:
            regulatory_analysis = None
            has_regulatory_analysis = False

        # Calculate regulatory stats
        regulatory_stats = {
            'total_pages': document.total_pages,
            'analyzed_pages': document.pages.filter(is_regulatory_analyzed=True).count(),
            'high_importance_pages': document.pages.filter(regulatory_importance_score__gte=70).count(),
        }
        if regulatory_stats['total_pages'] > 0:
            regulatory_stats['completion_percentage'] = int(
                (regulatory_stats['analyzed_pages'] / regulatory_stats['total_pages']) * 100
            )
        else:
            regulatory_stats['completion_percentage'] = 0

        context = {
            'document': document,
            'global_annotations_json': document_json,
            'global_annotations_summary': document_summary,
            'total_annotations': total_annotations,
            'annotated_pages': annotated_pages,
            'total_pages': document.total_pages,
            'allowed_entity_types': allowed_entity_types,
            'can_edit': True,  # Activer l'interface d'édition
            'last_updated': document_json.get('last_updated'),
            'last_updated_by': document_json.get('last_updated_by'),
            # Regulatory analysis data
            'regulatory_analysis': regulatory_analysis,
            'has_regulatory_analysis': has_regulatory_analysis,
            'regulatory_stats': regulatory_stats,
        }

        return render(request, 'expert/view_document_annotation_json.html', context)

    except Exception as e:
        messages.error(request, f"Erreur: {str(e)}")
        return redirect('expert:annotation_dashboard')


@expert_required
@csrf_exempt
def save_regulatory_summary(request, doc_id):
    """Save regulatory summary edited by expert"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        document = get_object_or_404(RawDocument, id=doc_id)
        data = json.loads(request.body)
        regulatory_summary = data.get('regulatory_summary', '').strip()

        if not regulatory_summary:
            return JsonResponse({'error': 'Regulatory summary cannot be empty'}, status=400)

        # Get or create regulatory analysis
        from rawdocs.models import DocumentRegulatoryAnalysis
        regulatory_analysis, created = DocumentRegulatoryAnalysis.objects.get_or_create(
            document=document,
            defaults={
                'global_summary': regulatory_summary,
                'analyzed_by': request.user,
            }
        )

        if not created:
            regulatory_analysis.global_summary = regulatory_summary
            regulatory_analysis.analyzed_by = request.user
            regulatory_analysis.save()

        # Log expert action
        log_expert_action(
            user=request.user,
            annotation=None,
            action='regulatory_summary_saved',
            document_id=document.id,
            document_title=document.title,
            reason='Expert edited regulatory summary'
        )

        return JsonResponse({'success': True, 'message': 'Regulatory summary saved successfully'})

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@expert_required
@csrf_exempt
def validate_regulatory_analysis(request, doc_id):
    """Validate regulatory analysis by expert"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        document = get_object_or_404(RawDocument, id=doc_id)

        # Get regulatory analysis
        from rawdocs.models import DocumentRegulatoryAnalysis
        try:
            regulatory_analysis = document.regulatory_analysis
        except DocumentRegulatoryAnalysis.DoesNotExist:
            return JsonResponse({'error': 'No regulatory analysis found for this document'}, status=404)

        # Mark as expert validated
        regulatory_analysis.is_expert_validated = True
        regulatory_analysis.expert_validated_by = request.user
        regulatory_analysis.expert_validated_at = timezone.now()
        regulatory_analysis.save()

        # Log expert action
        log_expert_action(
            user=request.user,
            annotation=None,
            action='regulatory_analysis_validated',
            document_id=document.id,
            document_title=document.title,
            reason='Expert validated regulatory analysis'
        )

        return JsonResponse({'success': True, 'message': 'Regulatory analysis validated successfully'})

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@expert_required
@csrf_exempt
def generate_regulatory_analysis(request, doc_id):
    """Generate complete regulatory analysis for a document in expert module"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        document = get_object_or_404(RawDocument, id=doc_id, is_validated=True)

        print(f"Starting expert regulatory analysis for document {doc_id}")

        # Initialize expert regulatory analyzer
        from .regulatory_analyzer import ExpertRegulatoryAnalyzer
        analyzer = ExpertRegulatoryAnalyzer()
        document_context = f"{document.title} - {document.doc_type} - {document.source}"

        # Analyze all pages
        pages = document.pages.all().order_by('page_number')
        analyses = []
        analyzed_count = 0

        for page in pages:
            try:
                print(f"Analyzing page {page.page_number}/{document.total_pages}")

                analysis = analyzer.analyze_page_regulatory_content(
                    page_text=page.cleaned_text,
                    page_num=page.page_number,
                    document_context=document_context
                )

                # Save page-level analysis
                page.regulatory_analysis = analysis
                page.page_summary = analysis.get('page_summary', '')
                page.regulatory_obligations = analysis.get('regulatory_obligations', [])
                page.critical_deadlines = analysis.get('critical_deadlines', [])
                page.regulatory_importance_score = analysis.get('regulatory_importance_score', 0)
                page.is_regulatory_analyzed = True
                page.regulatory_analyzed_at = timezone.now()
                page.regulatory_analyzed_by = request.user
                page.save()

                analyses.append(analysis)
                analyzed_count += 1

                # Pause to avoid API limits
                import time
                time.sleep(2)

            except Exception as e:
                print(f"Error analyzing page {page.page_number}: {e}")
                continue

        # Generate global summary
        print(f"Generating global summary with {len(analyses)} analyses...")
        global_analysis = analyzer.generate_document_global_summary(document, analyses)

        # Save document-level regulatory analysis
        from rawdocs.models import DocumentRegulatoryAnalysis
        doc_analysis, created = DocumentRegulatoryAnalysis.objects.update_or_create(
            document=document,
            defaults={
                'global_summary': global_analysis.get('global_summary', ''),
                'consolidated_analysis': global_analysis,
                'main_obligations': global_analysis.get('critical_compliance_requirements', []),
                'critical_deadlines_summary': global_analysis.get('key_deadlines_summary', []),
                'relevant_authorities': global_analysis.get('regulatory_authorities_involved', []),
                'global_regulatory_score': global_analysis.get('global_regulatory_score', 0),
                'analyzed_by': request.user,
                'total_pages_analyzed': analyzed_count,
                'pages_with_regulatory_content': sum(
                    1 for a in analyses if a.get('regulatory_importance_score', 0) > 30
                )
            }
        )

        # Log expert action
        log_expert_action(
            user=request.user,
            annotation=None,
            action='regulatory_analysis_generated',
            document_id=document.id,
            document_title=document.title,
            reason=f'Expert generated regulatory analysis for {analyzed_count} pages'
        )

        print(f"Expert regulatory analysis completed: {analyzed_count} pages analyzed")

        return JsonResponse({
            'success': True,
            'message': f'Regulatory analysis generated successfully! {analyzed_count} pages analyzed.',
            'analyzed_pages': analyzed_count,
            'global_score': global_analysis.get('global_regulatory_score', 0)
        })

    except Exception as e:
        return JsonResponse({
            'error': f'Error generating regulatory analysis: {str(e)}'
        }, status=500)


# Fonctions pour la gestion des résumés de page
# @expert_required
# @csrf_exempt
# def save_page_summary(request, page_id):
#     """Sauvegarde du résumé d'une page"""
#     if request.method != 'POST':
#         return JsonResponse({'error': 'POST required'}, status=405)
#     try:
#         page = get_object_or_404(DocumentPage, id=page_id)
#         data = json.loads(request.body)
#         summary_text = data.get('summary_text', '').strip()
#
#         page.page_summary = summary_text
#         page.summary_validated = False  # Réinitialiser la validation
#         page.summary_validated_at = None
#         page.summary_validated_by = None
#         page.save(update_fields=['page_summary', 'summary_validated', 'summary_validated_at', 'summary_validated_by'])
#
#         return JsonResponse({'success': True, 'message': 'Résumé sauvegardé'})
#     except Exception as e:
#         return JsonResponse({'error': str(e)}, status=500)

# Ajouter ces vues dans expert/views.py

# Ajouter ces vues dans expert/views.py

@login_required
@user_passes_test(is_expert)
@csrf_exempt
def save_page_summary(request, page_id):
    """
    Version améliorée qui utilise le JSON de page existant pour une synchronisation intelligente.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        page = get_object_or_404(DocumentPage, id=page_id)
        data = json.loads(request.body)

        new_summary = data.get('summary_text', '').strip()
        auto_annotate = data.get('auto_annotate', True)
        auto_delete = data.get('auto_delete', True)

        if not new_summary:
            return JsonResponse({'error': 'Résumé vide'}, status=400)

        # Sauvegarder l'ancien résumé pour comparaison
        old_summary = page.annotations_summary or ""

        # UTILISER LA NOUVELLE FONCTION DE SYNCHRONISATION INTELLIGENTE
        if auto_annotate and old_summary != new_summary:
            sync_result = synchronize_page_annotations_with_summary(
                page=page,
                old_summary=old_summary,
                new_summary=new_summary,
                user=request.user,
                auto_delete=auto_delete
            )
        else:
            sync_result = {
                'annotations_created': 0,
                'annotations_deleted': 0,
                'annotations_rejected': 0,
                'details': {}
            }

        # Sauvegarder le nouveau résumé
        page.annotations_summary = new_summary
        page.annotations_summary_generated_at = timezone.now()
        page.save(update_fields=['annotations_summary', 'annotations_summary_generated_at'])

        # Reconstruire le JSON de la page
        build_page_summary_and_json(page, request.user)

        response_data = {
            'success': True,
            'message': f'Synchronisation intelligente réussie : {sync_result["annotations_created"]} créées, {sync_result["annotations_deleted"] + sync_result["annotations_rejected"]} supprimées',
            'summary': new_summary,
            'sync_result': sync_result
        }

        return JsonResponse(response_data)

    except Exception as e:
        print(f"Erreur synchronisation intelligente page {page_id}: {e}")
        return JsonResponse({'error': f'Erreur: {str(e)}'}, status=500)

# helpers -------------------------------------------------------------

from typing import Dict, List, Iterable

def _normalize(s: str) -> str:
    return (s or "").strip().strip('.,;:·').lower()

def _normalize_entities(entities: Dict[str, Iterable[str]]) -> Dict[str, List[str]]:
    """Nettoie, déduplique et retire les valeurs vides."""
    cleaned: Dict[str, List[str]] = {}
    for etype, vals in (entities or {}).items():
        seen = set()
        out: List[str] = []
        for v in vals or []:
            if not v:
                continue
            key = _normalize(v)
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(v.strip())
        if out:
            cleaned[etype] = out
    return cleaned

# 1) Enrichissement IA -----------------------------------------------

def enhance_entities_with_ai(
    page_text: str,
    entities: Dict[str, Iterable[str]],
    groq_annotator=None,
) -> Dict[str, List[str]]:
    """
    Enrichit/valide les entités détectées.
    - Si un GroqAnnotator est fourni et expose une méthode utile, on l’utilise.
    - Sinon, fallback : normalisation + dédoublonnage + filtrage trivial par présence dans le texte.
    Retourne le même schéma {entity_type: [values...]}.
    """
    # Fallback immédiat si rien à faire
    if not entities:
        return {}

    # Tentatives d’utilisation de l’annotateur si présent
    try:
        if groq_annotator:
            # On accepte plusieurs conventions possibles pour rester robuste
            if hasattr(groq_annotator, "enhance"):
                result = groq_annotator.enhance(page_text=page_text, entities=entities)
                if isinstance(result, dict):
                    return _normalize_entities(result)
            elif hasattr(groq_annotator, "annotate_entities"):
                result = groq_annotator.annotate_entities(page_text=page_text, seed=entities)
                if isinstance(result, dict):
                    return _normalize_entities(result)
            elif callable(groq_annotator):
                result = groq_annotator(page_text=page_text, entities=entities)
                if isinstance(result, dict):
                    return _normalize_entities(result)
        # Si on arrive ici, on passe en fallback
    except Exception:
        # On ignore proprement et on passe au fallback
        pass

    # Fallback simple : on garde les valeurs présentes dans le texte (quand possible)
    text_lc = (page_text or "").lower()
    filtered: Dict[str, List[str]] = {}
    for etype, vals in _normalize_entities(entities).items():
        keep: List[str] = []
        for v in vals:
            # très permissif : gardé si valeur ou version normalisée est dans le texte
            vn = _normalize(v)
            if not text_lc or (vn and vn in text_lc) or (v and v.lower() in text_lc):
                keep.append(v)
        if keep:
            filtered[etype] = keep
    return filtered


# 2) Création d’annotation -------------------------------------------

def create_page_annotation_from_entity(
    page,
    entity_type: str,
    entity_value: str,
    user,
):
    """
    Crée l’annotation (si elle n’existe pas déjà, insensible à la casse).
    Retourne l’instance créée, ou None si un doublon existait déjà.

    Hypothèses Django courantes :
    - Modèle PageAnnotation avec champs : page, entity_type, entity_value, created_by
    - Adapte les noms de champs au besoin.
    """
    # Normalisation pour éviter les doublons
    norm_value = _normalize(entity_value)

    # --- Variante modèle Django (recommandée) ---
    try:
        from rawdocs.models import PageAnnotation  # adapte le chemin si besoin

        # Existence (insensible à la casse)
        exists = PageAnnotation.objects.filter(
            page=page,
            entity_type=entity_type,
            entity_value__iexact=entity_value.strip(),
        ).exists()
        if exists:
            return None

        ann = PageAnnotation.objects.create(
            page=page,
            entity_type=entity_type,
            entity_value=entity_value.strip(),
            created_by=user,
        )
        return ann
    except Exception:
        # --- Fallback très simple si tu n’utilises pas Django ---
        # On essaie d'utiliser un conteneur en mémoire sur l'objet page.
        # Remplace ceci par ta logique de persistance maison.
        if not hasattr(page, "_tmp_annotations"):
            page._tmp_annotations = []  # type: ignore[attr-defined]
        # doublon ?
        for a in page._tmp_annotations:  # type: ignore[attr-defined]
            if a.get("entity_type") == entity_type and _normalize(a.get("entity_value", "")) == norm_value:
                return None
        ann = {
            "page": getattr(page, "id", None),
            "entity_type": entity_type,
            "entity_value": entity_value.strip(),
            "created_by": getattr(user, "id", None),
        }
        page._tmp_annotations.append(ann)  # type: ignore[attr-defined]
        return ann


def validate_ai_analysis(analysis, existing_entities, page_text):
    """
    Valide et filtre les résultats de l'analyse IA pour éviter les erreurs.
    """
    validated = {
        'entities_to_add': {},
        'entities_to_remove': {},
        'entities_to_modify': {},
        'removal_confidence': analysis.get('removal_confidence', 0.8),
        'analysis_summary': analysis.get('analysis_summary', '')
    }

    page_text_lower = page_text.lower() if page_text else ''

    # Valider les ajouts
    for entity_type, values in analysis.get('entities_to_add', {}).items():
        validated_values = []
        for value_data in values:
            if isinstance(value_data, dict):
                value = value_data.get('value', '')
                confidence = value_data.get('confidence', 0.7)
            else:
                value = str(value_data)
                confidence = 0.7

            # Vérifier que l'entité n'existe pas déjà
            existing_values = existing_entities.get(entity_type, [])
            if value.lower() not in [v.lower() for v in existing_values]:
                # Vérifier présence dans le texte (pour les entités non-date)
                if 'date' not in entity_type.lower() or value.lower() in page_text_lower or confidence > 0.9:
                    validated_values.append(value_data)

        if validated_values:
            validated['entities_to_add'][entity_type] = validated_values

    # Valider les suppressions
    for entity_type, values in analysis.get('entities_to_remove', {}).items():
        if entity_type in existing_entities:
            # Ne supprimer que les entités qui existent réellement
            validated_values = []
            existing_values = [v.lower() for v in existing_entities[entity_type]]
            for value in values:
                if value.lower() in existing_values:
                    validated_values.append(value)

            if validated_values:
                validated['entities_to_remove'][entity_type] = validated_values

    # Valider les modifications
    for entity_type, modifications in analysis.get('entities_to_modify', {}).items():
        validated_mods = []
        for mod in modifications:
            old_value = mod.get('old_value', '')
            new_value = mod.get('new_value', '')

            # Vérifier que l'ancienne valeur existe
            if entity_type in existing_entities:
                existing_values = [v.lower() for v in existing_entities[entity_type]]
                if old_value.lower() in existing_values and old_value != new_value:
                    validated_mods.append(mod)

        if validated_mods:
            validated['entities_to_modify'][entity_type] = validated_mods

    return validated


def _fallback_analysis(old_summary, new_summary, existing_entities):
    """
    Analyse de fallback simple si l'IA n'est pas disponible.
    """
    try:
        old_entities = extract_entities_from_summary(old_summary) if old_summary else {}
        new_entities = extract_entities_from_summary(new_summary) if new_summary else {}

        entities_to_add = {}
        entities_to_remove = {}

        all_types = set(old_entities.keys()) | set(new_entities.keys())

        for entity_type in all_types:
            old_values = set([v.lower() for v in old_entities.get(entity_type, [])])
            new_values = set([v.lower() for v in new_entities.get(entity_type, [])])

            # Ajouts
            added = new_values - old_values
            if added:
                entities_to_add[entity_type] = [
                    {'value': v, 'confidence': 0.7, 'context': '', 'reasoning': 'Detected in new summary'}
                    for v in new_entities[entity_type] if v.lower() in added
                ]

            # Suppressions
            removed = old_values - new_values
            if removed:
                entities_to_remove[entity_type] = [
                    v for v in old_entities[entity_type] if v.lower() in removed
                ]

        return {
            'entities_to_add': entities_to_add,
            'entities_to_remove': entities_to_remove,
            'entities_to_modify': {},
            'removal_confidence': 0.7,
            'analysis_summary': 'Fallback analysis - IA non disponible'
        }

    except Exception as e:
        print(f"⚠️ Erreur analyse fallback: {e}")
        return {
            'entities_to_add': {},
            'entities_to_remove': {},
            'entities_to_modify': {},
            'removal_confidence': 0.5,
            'analysis_summary': f'Erreur analyse: {str(e)}'
        }


def analyze_summary_changes_with_ai(page, old_summary, new_summary, existing_entities, page_text):
    """
    Utilise l'IA pour analyser intelligemment les changements dans le résumé
    en prenant en compte le contexte du JSON existant et du texte de la page.
    """
    try:
        from rawdocs.groq_annotation_system import GroqAnnotator
        import json

        groq_annotator = GroqAnnotator()

        # Construire le contexte pour l'IA
        context_data = {
            'page_number': page.page_number,
            'document_title': page.document.title,
            'existing_entities': existing_entities,
            'old_summary': old_summary or '',
            'new_summary': new_summary or '',
            'page_text_preview': page_text[:1000] if page_text else ''  # Limiter pour le prompt
        }

        prompt = f"""Tu es un expert en analyse documentaire pharmaceutique. Analyse les changements dans le résumé d'une page en tenant compte du contexte existant.

CONTEXTE:
- Document: {context_data['document_title']}
- Page: {context_data['page_number']}

ENTITÉS EXISTANTES (JSON actuel):
{json.dumps(existing_entities, ensure_ascii=False, indent=2)}

ANCIEN RÉSUMÉ:
{context_data['old_summary']}

NOUVEAU RÉSUMÉ:
{context_data['new_summary']}

EXTRAIT DU TEXTE DE PAGE (pour référence):
{context_data['page_text_preview']}

INSTRUCTIONS:
1. Identifie les entités qui doivent être AJOUTÉES (nouvelles dans le résumé)
2. Identifie les entités qui doivent être SUPPRIMÉES (retirées du résumé)
3. Identifie les entités MODIFIÉES (changement de valeur)
4. Pour chaque entité, évalue si elle existe réellement dans le texte de la page
5. Donne un niveau de confiance (0.0-1.0) pour chaque action

TYPES D'ENTITÉS PHARMACEUTIQUES À CONSIDÉRER:
- Product/Invented Name
- Strength/Dosage  
- Pharmaceutical Form
- Route Of Administration
- Date/Deadline
- Ma Number/Authorization
- Manufacturing Site
- Active Ingredient

Réponds UNIQUEMENT en JSON strict:
{{
  "entities_to_add": {{
    "<EntityType>": [
      {{
        "value": "texte exact à annoter",
        "confidence": 0.9,
        "context": "contexte où apparaît l'entité",
        "reasoning": "pourquoi cette entité doit être ajoutée"
      }}
    ]
  }},
  "entities_to_remove": {{
    "<EntityType>": ["valeur1", "valeur2"]
  }},
  "entities_to_modify": {{
    "<EntityType>": [
      {{
        "old_value": "ancienne valeur",
        "new_value": "nouvelle valeur", 
        "confidence": 0.8,
        "reasoning": "pourquoi cette modification"
      }}
    ]
  }},
  "removal_confidence": 0.8,
  "analysis_summary": "Résumé de l'analyse des changements"
}}"""

        # Appel à l'IA
        raw_response = groq_annotator.complete_text(
            prompt=prompt,
            max_tokens=1500,
            temperature=0.1
        )

        if raw_response:
            try:
                # Nettoyer la réponse
                clean_response = raw_response.strip()
                if clean_response.startswith('```'):
                    clean_response = clean_response.split('\n', 1)[1]
                if clean_response.endswith('```'):
                    clean_response = clean_response.rsplit('\n', 1)[0]

                analysis = json.loads(clean_response)

                # Validation et nettoyage des résultats
                validated_analysis = validate_ai_analysis(analysis, existing_entities, page_text)

                return validated_analysis

            except json.JSONDecodeError as e:
                print(f"⚠️ Erreur parsing réponse IA: {e}")
                return _fallback_analysis(old_summary, new_summary, existing_entities)
        else:
            return _fallback_analysis(old_summary, new_summary, existing_entities)

    except Exception as e:
        print(f"⚠️ Erreur analyse IA: {e}")
        return _fallback_analysis(old_summary, new_summary, existing_entities)


def create_page_annotation_with_smart_positioning(page, entity_type, entity_value, user, confidence=0.8, context='',
                                                  existing_json=None):
    """
    Crée une annotation avec positionnement intelligent basé sur le contexte existant
    et recherche optimisée dans le texte.
    """
    try:
        page_text = _get_page_text(page)
        if not page_text:
            print(f"⚠️ Pas de texte disponible pour la page {page.page_number}")
            return False

        # Recherche intelligente de position
        start_pos, end_pos, actual_text = find_entity_in_text_enhanced(
            entity_text=entity_value,
            page_text=page_text,
            entity_type=entity_type,
            existing_annotations=existing_json,
            context_hint=context
        )

        if start_pos == -1:
            print(f"⚠️ Entité '{entity_value}' non trouvée dans le texte de la page {page.page_number}")
            return False

        # Créer le type d'annotation
        annotation_type, _ = AnnotationType.objects.get_or_create(
            name=entity_type,
            defaults={
                'display_name': entity_type.replace('_', ' ').title(),
                'color': '#8b5cf6',
                'description': f"Smart annotation: {entity_type}"
            }
        )

        # Vérifier les doublons
        existing = Annotation.objects.filter(
            page=page,
            annotation_type=annotation_type,
            start_pos__lte=start_pos + 10,
            start_pos__gte=start_pos - 10,
            validation_status__in=['validated', 'expert_created', 'pending']
        ).first()

        if existing:
            print(f"ℹ️ Annotation similaire déjà existante: {existing.selected_text}")
            return False

        # Créer l'annotation
        annotation = Annotation.objects.create(
            page=page,
            selected_text=actual_text,
            annotation_type=annotation_type,
            start_pos=start_pos,
            end_pos=end_pos,
            validation_status='expert_created',
            validated_by=user,
            validated_at=timezone.now(),
            created_by=user,
            source='expert_smart_sync',
            confidence_score=confidence
        )

        print(f"✅ Annotation intelligente créée: '{actual_text}' ({entity_type}) page {page.page_number}")
        return True

    except Exception as e:
        print(f"⚠️ Erreur création annotation intelligente: {e}")
        return False


def find_entity_in_text_enhanced(entity_text, page_text, entity_type='', existing_annotations=None, context_hint=''):
    """
    Version améliorée de la recherche d'entité qui utilise le contexte du JSON existant.
    """
    if not entity_text or not page_text:
        return -1, -1, entity_text

    # 1. Recherche exacte d'abord
    result = find_entity_in_text(entity_text, page_text, entity_type)
    if result[0] != -1:
        return result

    # 2. Utiliser le contexte des annotations existantes
    if existing_annotations:
        result = _find_entity_using_annotation_context(entity_text, page_text, existing_annotations)
        if result[0] != -1:
            return result

    # 3. Utiliser l'indice de contexte fourni par l'IA
    if context_hint:
        result = _find_entity_using_context_hint(entity_text, page_text, context_hint)
        if result[0] != -1:
            return result

    return -1, -1, entity_text


def _find_entity_using_annotation_context(entity_text, page_text, existing_annotations):
    """
    Utilise le contexte des annotations existantes pour améliorer la recherche.
    """
    try:
        existing_entities = existing_annotations.get('entities', {})
        page_text_lower = page_text.lower()
        entity_lower = entity_text.lower()

        # Chercher des entités similaires ou liées
        for entity_type, values in existing_entities.items():
            for value in values:
                value_pos = page_text_lower.find(value.lower())
                if value_pos != -1:
                    # Chercher l'entité cible dans un rayon autour de cette annotation
                    search_start = max(0, value_pos - 200)
                    search_end = min(len(page_text), value_pos + len(value) + 200)
                    context_text = page_text[search_start:search_end]

                    entity_pos_in_context = context_text.lower().find(entity_lower)
                    if entity_pos_in_context != -1:
                        actual_start = search_start + entity_pos_in_context
                        actual_end = actual_start + len(entity_text)
                        actual_text = page_text[actual_start:actual_end]
                        return actual_start, actual_end, actual_text

        return -1, -1, entity_text

    except Exception as e:
        print(f"⚠️ Erreur recherche avec contexte annotations: {e}")
        return -1, -1, entity_text


def _find_entity_using_context_hint(entity_text, page_text, context_hint):
    """
    Utilise l'indice de contexte fourni par l'IA pour localiser l'entité.
    """
    try:
        page_text_lower = page_text.lower()
        context_lower = context_hint.lower()
        entity_lower = entity_text.lower()

        # Chercher le contexte d'abord
        context_pos = page_text_lower.find(context_lower)
        if context_pos != -1:
            # Chercher l'entité près du contexte
            search_start = max(0, context_pos - 100)
            search_end = min(len(page_text), context_pos + len(context_hint) + 100)
            search_area = page_text[search_start:search_end]

            entity_pos_in_area = search_area.lower().find(entity_lower)
            if entity_pos_in_area != -1:
                actual_start = search_start + entity_pos_in_area
                actual_end = actual_start + len(entity_text)
                actual_text = page_text[actual_start:actual_end]
                return actual_start, actual_end, actual_text

        return -1, -1, entity_text

    except Exception as e:
        print(f"⚠️ Erreur recherche avec contexte hint: {e}")
        return -1, -1, entity_text


def remove_page_annotations_for_entity_enhanced(page, entity_type, entity_value, user, existing_json=None,
                                                confidence_threshold=0.8, hard_delete=False):
    """
    Version améliorée de suppression qui prend en compte le contexte du JSON existant.
    """
    try:
        # Utiliser la fonction existante mais avec une validation supplémentaire
        result = remove_page_annotations_for_entity(
            page=page,
            entity_type=entity_type,
            entity_value=entity_value,
            user=user,
            hard_delete=hard_delete
        )

        # Validation supplémentaire basée sur le JSON existant
        if existing_json and confidence_threshold > 0.7:
            existing_entities = existing_json.get('entities', {})
            if entity_type in existing_entities:
                existing_values = [v.lower() for v in existing_entities[entity_type]]
                if entity_value.lower() not in existing_values:
                    print(f"ℹ️ Entité '{entity_value}' pas dans le JSON existant, suppression annulée")
                    return {'count': 0, 'message': 'Entité non trouvée dans le JSON existant'}

        return result

    except Exception as e:
        print(f"⚠️ Erreur suppression annotations améliorée: {e}")
        return {'count': 0, 'error': str(e)}


def synchronize_page_annotations_with_summary(page, old_summary, new_summary, user, auto_delete=True):
    """
    Synchronisation intelligente qui prend en compte le JSON de page existant
    pour une analyse précise des modifications et une annotation automatique optimisée.
    """
    try:
        from rawdocs.groq_annotation_system import GroqAnnotator
        from django.utils import timezone

        # 1. RÉCUPÉRER LE CONTEXTE EXISTANT
        existing_json = getattr(page, 'annotations_json', {}) or {}
        existing_entities = existing_json.get('entities', {})
        page_text = _get_page_text(page)

        # 2. ANALYSER LES CHANGEMENTS AVEC IA
        ai_analysis = analyze_summary_changes_with_ai(
            page=page,
            old_summary=old_summary,
            new_summary=new_summary,
            existing_entities=existing_entities,
            page_text=page_text
        )

        sync_result = {
            'annotations_created': 0,
            'annotations_deleted': 0,
            'annotations_rejected': 0,
            'details': {
                'added': {},
                'removed': {},
                'modified': {},
                'ai_analysis': ai_analysis
            }
        }

        # 3. TRAITEMENT DES SUPPRESSIONS (basé sur l'analyse IA)
        entities_to_remove = ai_analysis.get('entities_to_remove', {})
        if entities_to_remove and auto_delete:
            for entity_type, values in entities_to_remove.items():
                for value in values:
                    result = remove_page_annotations_for_entity_enhanced(
                        page=page,
                        entity_type=entity_type,
                        entity_value=value,
                        user=user,
                        existing_json=existing_json,
                        confidence_threshold=ai_analysis.get('removal_confidence', 0.8)
                    )
                    sync_result['annotations_rejected'] += result['count']

        # 4. TRAITEMENT DES AJOUTS (basé sur l'analyse IA + recherche dans le texte)
        entities_to_add = ai_analysis.get('entities_to_add', {})
        if entities_to_add:
            for entity_type, values in entities_to_add.items():
                for value_data in values:
                    if isinstance(value_data, dict):
                        value = value_data.get('value', '')
                        confidence = value_data.get('confidence', 0.7)
                        context = value_data.get('context', '')
                    else:
                        value = str(value_data)
                        confidence = 0.7
                        context = ''

                    # Créer l'annotation avec recherche intelligente dans le texte
                    annotation_created = create_page_annotation_with_smart_positioning(
                        page=page,
                        entity_type=entity_type,
                        entity_value=value,
                        user=user,
                        confidence=confidence,
                        context=context,
                        existing_json=existing_json
                    )

                    if annotation_created:
                        sync_result['annotations_created'] += 1
                        sync_result['details']['added'].setdefault(entity_type, []).append(value)

        # 5. TRAITEMENT DES MODIFICATIONS
        entities_to_modify = ai_analysis.get('entities_to_modify', {})
        if entities_to_modify:
            for entity_type, modifications in entities_to_modify.items():
                for mod in modifications:
                    old_value = mod.get('old_value', '')
                    new_value = mod.get('new_value', '')

                    # Supprimer l'ancienne valeur
                    remove_result = remove_page_annotations_for_entity_enhanced(
                        page=page,
                        entity_type=entity_type,
                        entity_value=old_value,
                        user=user,
                        existing_json=existing_json
                    )

                    # Ajouter la nouvelle valeur
                    annotation_created = create_page_annotation_with_smart_positioning(
                        page=page,
                        entity_type=entity_type,
                        entity_value=new_value,
                        user=user,
                        confidence=mod.get('confidence', 0.8),
                        existing_json=existing_json
                    )

                    if remove_result['count'] > 0 and annotation_created:
                        sync_result['details']['modified'].setdefault(entity_type, []).append({
                            'from': old_value,
                            'to': new_value
                        })

        return sync_result

    except Exception as e:
        print(f"⚠️ Erreur synchronisation intelligente: {e}")
        # Fallback vers la méthode originale
        return synchronize_page_annotations_with_summary(page, old_summary, new_summary, user, auto_delete)



def remove_page_annotations_for_entity(page, entity_type, entity_value, user, hard_delete=False):
    """
    Supprime ou rejette les annotations d'une page qui correspondent à une entité

    Args:
        page: La page concernée
        entity_type: Type d'entité (ex: "Product", "Date")
        entity_value: Valeur de l'entité à rechercher
        user: Utilisateur effectuant l'action
        hard_delete: Si True, supprime définitivement. Si False, met en status 'rejected'

    Returns:
        dict avec le nombre d'annotations affectées
    """
    try:
        from django.db.models import Q

        # Rechercher les types d'annotation correspondants
        annotation_types = AnnotationType.objects.filter(
            Q(name__iexact=entity_type) |
            Q(display_name__iexact=entity_type) |
            Q(name__icontains=entity_type.replace(' ', '_'))
        )

        if not annotation_types.exists():
            return {'count': 0, 'message': f'Type {entity_type} non trouvé'}

        # Rechercher les annotations sur cette page uniquement
        annotations = Annotation.objects.filter(
            page=page,
            annotation_type__in=annotation_types,
            validation_status__in=['pending', 'validated', 'expert_created']
        )

        # Filtrer par valeur (recherche flexible)
        matching_annotations = []
        entity_lower = entity_value.lower().strip()

        for ann in annotations:
            ann_text_lower = ann.selected_text.lower().strip()

            # Correspondance exacte ou partielle
            if (ann_text_lower == entity_lower or
                    entity_lower in ann_text_lower or
                    ann_text_lower in entity_lower):
                matching_annotations.append(ann)
                continue

            # Pour les dates, vérifier les variantes
            if 'date' in entity_type.lower():
                if are_dates_equivalent(ann.selected_text, entity_value):
                    matching_annotations.append(ann)

        count = 0
        for ann in matching_annotations:
            if hard_delete:
                # Suppression définitive
                ann_id = ann.id
                ann.delete()
                print(f"❌ Annotation {ann_id} supprimée (page {page.page_number})")
            else:
                # Marquer comme rejetée
                ann.validation_status = 'rejected'
                ann.validated_by = user
                ann.validated_at = timezone.now()
                ann.save(update_fields=['validation_status', 'validated_by', 'validated_at'])
                print(f"⛔ Annotation {ann.id} rejetée (page {page.page_number})")

            count += 1

        return {
            'count': count,
            'message': f'{count} annotation(s) {"supprimée(s)" if hard_delete else "rejetée(s)"} pour "{entity_value}"'
        }

    except Exception as e:
        print(f"❌ Erreur suppression annotations: {e}")
        return {'count': 0, 'error': str(e)}


def extract_entities_from_summary(summary_text):
    """
    Extrait toutes les entités d'un résumé
    Utilise les patterns existants + détection intelligente
    """
    if not summary_text:
        return {}

    # Utiliser la fonction existante
    entities = extract_entities_from_text(summary_text)

    # Ajouter une détection par structure "Type: valeur"
    import re
    pattern = r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s*:\s*([^,\n]+)'
    for match in re.finditer(pattern, summary_text):
        entity_type = match.group(1)
        entity_value = match.group(2).strip()

        if entity_type not in entities:
            entities[entity_type] = []
        if entity_value not in entities[entity_type]:
            entities[entity_type].append(entity_value)

    return entities


def are_dates_equivalent(date1, date2):
    """
    Vérifie si deux dates sont équivalentes malgré des formats différents
    Ex: "January 2013" == "Jan 2013" == "01/2013"
    """
    # Normaliser les dates
    date1_normalized = normalize_date_format(date1)
    date2_normalized = normalize_date_format(date2)

    return date1_normalized == date2_normalized


def normalize_date_format(date_str):
    """
    Normalise une date dans un format standard pour comparaison
    """
    import re

    # Dictionnaire mois
    months = {
        'january': '01', 'jan': '01', 'février': '02', 'february': '02',
        'march': '03', 'mar': '03', 'april': '04', 'apr': '04',
        'may': '05', 'june': '06', 'jun': '06', 'july': '07', 'jul': '07',
        'august': '08', 'aug': '08', 'september': '09', 'sep': '09',
        'october': '10', 'oct': '10', 'november': '11', 'nov': '11',
        'december': '12', 'dec': '12'
    }

    date_lower = date_str.lower().strip()

    # Extraire mois et année
    for month_name, month_num in months.items():
        if month_name in date_lower:
            year_match = re.search(r'(\d{4})', date_lower)
            if year_match:
                return f"{month_num}/{year_match.group(1)}"

    # Format numérique
    numeric_match = re.search(r'(\d{1,2})[/-](\d{4})', date_lower)
    if numeric_match:
        month = numeric_match.group(1).zfill(2)
        year = numeric_match.group(2)
        return f"{month}/{year}"

    return date_str

@login_required
@user_passes_test(is_expert)
@csrf_exempt
def update_summary_from_annotations(request, page_id):
    """
    Régénère automatiquement le résumé de page basé sur les annotations actuelles
    Appelé quand l'expert modifie/ajoute/supprime des annotations
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        page = get_object_or_404(DocumentPage, id=page_id)

        # Récupérer toutes les annotations de la page
        annotations = page.annotations.all().select_related('annotation_type').order_by('start_pos')

        if not annotations.exists():
            # Pas d'annotations = résumé vide ou générique
            new_summary = f"Page {page.page_number}: Aucune annotation disponible."
            page.annotations_summary = new_summary
            page.annotations_summary_generated_at = timezone.now()
            page.save(update_fields=['annotations_summary', 'annotations_summary_generated_at'])

            return JsonResponse({
                'success': True,
                'summary': new_summary,
                'message': 'Résumé mis à jour (aucune annotation)'
            })

        # Construire les entités depuis les annotations
        from collections import OrderedDict
        entities = OrderedDict()
        seen_per_key = {}

        for ann in annotations:
            key = ann.annotation_type.display_name
            val = (ann.selected_text or "").strip()
            if not val:
                continue

            if key not in entities:
                entities[key] = []
                seen_per_key[key] = set()

            if val not in seen_per_key[key]:
                entities[key].append(val)
                seen_per_key[key].add(val)

        # Générer le résumé avec IA si possible
        try:
            from rawdocs.groq_annotation_system import GroqAnnotator
            groq_annotator = GroqAnnotator()

            if groq_annotator.enabled and entities:
                # Préparer les données structurées pour le prompt
                lines = []
                total_pairs = 0
                for ent, vals in entities.items():
                    total_pairs += len(vals)
                    preview = "; ".join(vals[:4]) + ("…" if len(vals) > 4 else "")
                    lines.append(f"- {ent}: {preview}")

                structured_view = "\n".join(lines)

                prompt = f"""Tu es un expert en analyse documentaire réglementaire.
Génère un résumé court (3-4 phrases) et fluide basé UNIQUEMENT sur les entités annotées.

DOCUMENT: {page.document.title}
PAGE: {page.page_number}

ENTITÉS ANNOTÉES:
{structured_view}

Contraintes:
- Ne liste pas tout; synthétise les thèmes/infos clés
- Utilise un ton professionnel et clair
- Termine par le nombre total de paires entité-valeur entre parenthèses
- Focus sur les aspects réglementaires et pharmaceutiques

Réponds UNIQUEMENT par le paragraphe de résumé."""

                ai_summary = groq_annotator.complete_text(prompt, max_tokens=280, temperature=0.1)

                if ai_summary and len(ai_summary.strip()) > 20:
                    new_summary = ai_summary.strip()
                else:
                    # Fallback manuel
                    new_summary = f"Page {page.page_number}: synthèse de {total_pairs} élément(s) annoté(s) sur les entités « {', '.join(list(entities.keys())[:5])}{'…' if len(entities) > 5 else ''} »."
            else:
                # Fallback sans IA
                flat_count = sum(len(v) for v in entities.values())
                new_summary = f"Page {page.page_number}: {flat_count} valeur(s) annotée(s) sur {len(entities)} entité(s)."

        except Exception as e:
            print(f"Erreur génération résumé IA: {e}")
            # Fallback simple
            flat_count = sum(len(v) for v in entities.values())
            new_summary = f"Page {page.page_number}: {flat_count} annotation(s) sur {len(entities)} type(s) d'entité."

        # Sauvegarder le nouveau résumé
        page.annotations_summary = new_summary
        page.annotations_summary_generated_at = timezone.now()
        page.save(update_fields=['annotations_summary', 'annotations_summary_generated_at'])

        return JsonResponse({
            'success': True,
            'summary': new_summary,
            'entities_count': len(entities),
            'total_annotations': annotations.count(),
            'message': 'Résumé régénéré depuis les annotations'
        })

    except Exception as e:
        print(f"Erreur mise à jour résumé page {page_id}: {e}")
        return JsonResponse({'error': f'Erreur: {str(e)}'}, status=500)
@expert_required
@csrf_exempt
def validate_page_summary(request, page_id):
    """Validation du résumé d'une page"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    try:
        page = get_object_or_404(DocumentPage, id=page_id)
        data = json.loads(request.body)
        summary_text = data.get('summary_text', '').strip()

        if not summary_text:
            return JsonResponse({'error': 'Résumé vide'}, status=400)

        page.page_summary = summary_text
        page.summary_validated = True
        page.summary_validated_at = timezone.now()
        page.summary_validated_by = request.user
        page.save(update_fields=['page_summary', 'summary_validated', 'summary_validated_at', 'summary_validated_by'])

        return JsonResponse({'success': True, 'message': 'Résumé validé'})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)



# Fonctions pour l'enrichissement sémantique du JSON
@expert_required
@csrf_exempt
def enrich_document_json(request, doc_id):
    """Enrichit le JSON d'un document avec du contexte sémantique"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        document = get_object_or_404(RawDocument, id=doc_id)
        basic_json = document.global_annotations_json or {}

        if not basic_json.get('entities'):
            return JsonResponse({
                'error': 'Aucune entité trouvée dans le document. Veuillez d\'abord générer le JSON de base.'
            }, status=400)

        # Utiliser votre fonction d'enrichissement existante
        from .json_enrichment import enrich_document_json_for_expert
        enriched_json = enrich_document_json_for_expert(document, basic_json)

        document.enriched_annotations_json = enriched_json
        document.enriched_at = timezone.now()
        document.enriched_by = request.user
        document.save(update_fields=['enriched_annotations_json', 'enriched_at', 'enriched_by'])

        log_expert_action(
            user=request.user,
            action='json_enriched',
            annotation=None,
            document_id=document.id,
            document_title=document.title,
            reason="JSON enrichi automatiquement avec contexte sémantique"
        )

        return JsonResponse({
            'success': True,
            'message': 'JSON enrichi avec succès',
            'enriched_json': enriched_json
        })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)



@expert_required
def expert_view_document_annotation_json_enriched(request, doc_id):
    """Vue pour le JSON enrichi sémantique"""
    document = get_object_or_404(RawDocument, id=doc_id, is_validated=True)

    if not getattr(document, 'global_annotations_json', None):
        from django.test import RequestFactory
        factory = RequestFactory()
        fake_request = factory.post(f'/expert/annotation/document/{doc_id}/generate-summary/')
        fake_request.user = request.user
        expert_generate_document_annotation_summary(fake_request, doc_id)
        document.refresh_from_db()

    document_json = document.global_annotations_json or {}
    enriched_json = getattr(document, 'enriched_annotations_json', None)

    context = {
        'document': document,
        'global_annotations_json': document_json,
        'enriched_annotations_json': enriched_json,
        'display_json': enriched_json or document_json,
        'global_annotations_summary': getattr(document, 'global_annotations_summary', '') or '',
        'total_annotations': sum(p.annotations.count() for p in document.pages.all()),
        'annotated_pages': document.pages.filter(annotations__isnull=False).distinct().count(),
        'total_pages': document.total_pages,
        'allowed_entity_types': list(document_json.get('entities', {}).keys()),
        'has_enriched': bool(enriched_json),
        'enriched_stats': {
            'relations_count': len(enriched_json.get('relations', [])) if enriched_json else 0,
            'qa_pairs_count': len(enriched_json.get('questions_answers', [])) if enriched_json else 0,
            'contexts_count': len(enriched_json.get('contexts', {})) if enriched_json else 0,
        },
        'last_updated': (enriched_json or {}).get('last_updated'),
        'last_updated_by': (enriched_json or {}).get('last_updated_by'),
        'can_edit': True,
    }
    return render(request, 'expert/view_document_annotation_json_enriched.html', context)

@expert_required
@csrf_exempt
def qa_feedback(request, doc_id):
    """Gestion du feedback Q&A pour l'expert"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        document = get_object_or_404(RawDocument, id=doc_id)
        data = json.loads(request.body)
        question = data.get('question', '').strip()
        corrected_answer = data.get('corrected_answer', '').strip()
        source = data.get('source', 'enriched').lower()

        if not question or not corrected_answer:
            return JsonResponse({'error': 'Question ou réponse manquante'}, status=400)

        enriched_json = document.enriched_annotations_json or {}
        qa_list = enriched_json.setdefault('questions_answers', [])

        qa_list.append({
            'question': question,
            'answer': corrected_answer,
            'confidence': 1.0,
            'answer_type': 'expert_correction',
            'source': source,
            'created_by': 'expert',
            'created_at': timezone.now().isoformat()
        })

        document.enriched_annotations_json = enriched_json
        document.save(update_fields=['enriched_annotations_json'])

        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# Place ça en haut du fichier (près des autres helpers)
def _get_page_text(page: DocumentPage) -> str:
    """
    Retourne le meilleur texte exploitable pour une page, avec fallback.
    """
    candidates = [
        getattr(page, 'cleaned_text', '') or '',
        getattr(page, 'text_content', '') or '',
        getattr(page, 'ocr_text', '') or '',
        getattr(page, 'raw_text', '') or '',
        getattr(page, 'content', '') or '',
    ]
    # joindre si plusieurs champs ont du texte
    text = "\n".join([c.strip() for c in candidates if c and c.strip()])
    return text.strip()


import json, re

def _coerce_groq_entities(raw, page_text: str) -> list[dict]:
    """
    Accepte différentes formes de sortie Groq et normalise en:
    [{"type": str, "text": str, "start_pos": int, "end_pos": int}, ...]
    """
    # 1) déjà une liste dict
    if isinstance(raw, list):
        items = raw
    else:
        # 2) dict avec clés usuelles
        if isinstance(raw, dict):
            for key in ("entities", "annotations", "items", "data"):
                if key in raw and isinstance(raw[key], list):
                    items = raw[key]
                    break
            else:
                items = []
        else:
            # 3) string → tenter JSON
            if isinstance(raw, str):
                s = raw.strip()
                # retirer fences éventuels
                s = re.sub(r"^```(?:json)?\s*|\s*```$", "", s, flags=re.IGNORECASE)
                try:
                    parsed = json.loads(s)
                    return _coerce_groq_entities(parsed, page_text)
                except Exception:
                    # extraire premier tableau JSON plausible
                    m = re.search(r"\[\s*\{.*\}\s*\]", s, flags=re.DOTALL)
                    if m:
                        try:
                            parsed = json.loads(m.group(0))
                            return _coerce_groq_entities(parsed, page_text)
                        except Exception:
                            return []
                    return []
            return []

    norm: list[dict] = []
    used_spans: list[tuple[int, int]] = []

    def _safe_find(txt: str) -> tuple[int, int]:
        """
        trouve une occurrence non chevauchante dans page_text; sinon -1
        """
        if not txt:
            return -1, -1
        base = page_text.lower()
        needle = txt.lower().strip()
        start = base.find(needle)
        if start == -1:
            # fallback mot-clé
            for w in needle.split():
                if len(w) > 3:
                    start = base.find(w)
                    if start != -1:
                        end = start + len(w)
                        # vérifier chevauchement
                        for a, b in used_spans:
                            if not (end <= a or start >= b):
                                start = -1
                                break
                        if start != -1:
                            return start, end
            return -1, -1

        end = start + len(needle)
        # éviter chevauchements
        for a, b in used_spans:
            if not (end <= a or start >= b):
                return -1, -1
        return start, end

    for it in items:
        if not isinstance(it, dict):
            continue
        etype = (it.get("type") or it.get("label") or "").strip()
        etext = (it.get("text") or it.get("value") or "").strip()
        if not etype or not etext:
            continue

        sp = it.get("start_pos")
        ep = it.get("end_pos")

        try:
            sp = int(sp) if sp is not None else None
            ep = int(ep) if ep is not None else None
        except Exception:
            sp = ep = None

        if sp is None or ep is None or sp < 0 or ep <= sp or ep > len(page_text):
            sp, ep = _safe_find(etext)
            if sp == -1:
                # si aucune position possible, on garde quand même l'entité (positions 0..len)
                sp = 0
                ep = min(len(etext), len(page_text)) if page_text else len(etext)

        used_spans.append((sp, ep))
        norm.append({
            "type": etype,
            "text": etext,
            "start_pos": sp,
            "end_pos": ep
        })

    return norm


# expert/views.py
from django.utils import timezone

def build_page_summary_and_json(page: DocumentPage, user) -> tuple[str, dict]:
    """
    Recalcule ENTITIES + SUMMARY pour UNE page à partir des annotations validées/expert_created,
    met à jour page.annotations_summary et page.annotations_json, puis sauvegarde.
    Retourne (summary, entities_map)
    """
    anns = (
        page.annotations
        .filter(validation_status__in=['validated', 'expert_created'])
        .select_related('annotation_type')
        .order_by('start_pos')
    )

    from rawdocs.views import _build_entities_map, generate_entities_based_page_summary

    entities_map = _build_entities_map(anns, use_display_name=True)

    # Génère un résumé lisible (si pas d’annotations, message court)
    if entities_map:
        summary = generate_entities_based_page_summary(
            entities=entities_map,
            page_number=page.page_number,
            document_title=page.document.title
        )
    else:
        summary = f"Page {page.page_number}: aucune annotation validée."

    # JSON page
    page_json = {
        "document": {
            "id": str(page.document.id),
            "title": page.document.title,
            "doc_type": getattr(page.document, 'doc_type', None),
            "source": getattr(page.document, 'source', None),
        },
        "page": {
            "number": page.page_number,
            "annotations_count": anns.count(),
            "validated_count": anns.count(),
        },
        "entities": entities_map,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "updated_by": getattr(user, "username", None),
    }

    page.annotations_summary = summary
    page.annotations_summary_generated_at = timezone.now()
    page.annotations_json = page_json
    page.save(update_fields=['annotations_summary', 'annotations_summary_generated_at', 'annotations_json'])

    return summary, entities_map

################
def find_entity_in_text(entity_text, page_text, entity_type=""):
    """
    Recherche intelligente d'entité dans le texte avec support spécialisé pour les dates
    et autres formats variables.

    Args:
        entity_text (str): Texte de l'entité à chercher (ex: "January 2013")
        page_text (str): Texte de la page où chercher
        entity_type (str): Type d'entité pour optimiser la recherche

    Returns:
        tuple: (start_pos, end_pos, actual_text) ou (-1, -1, entity_text) si non trouvé
    """
    if not entity_text or not page_text:
        return -1, -1, entity_text

    page_lower = page_text.lower()
    entity_lower = entity_text.lower()

    # 1. Recherche exacte d'abord
    start_pos = page_lower.find(entity_lower)
    if start_pos >= 0:
        end_pos = start_pos + len(entity_text)
        actual_text = page_text[start_pos:end_pos]
        return start_pos, end_pos, actual_text

    # 2. Recherche spécialisée par type d'entité
    if any(keyword in entity_type.lower() for keyword in ['date', 'time', 'délai', 'deadline']):
        return _find_date_entity(entity_text, page_text)

    # 3. Recherche flexible avec variations
    result = _find_flexible_match(entity_text, page_text)
    if result[0] >= 0:
        return result

    # 4. Recherche par mots-clés (version améliorée)
    result = _find_keyword_match(entity_text, page_text)
    if result[0] >= 0:
        return result

    # 5. Pas trouvé
    return -1, -1, entity_text


def _find_date_entity(entity_text, page_text):
    """
    Recherche spécialisée pour les dates avec formats multiples
    """
    import re
    from datetime import datetime

    page_lower = page_text.lower()
    entity_lower = entity_text.lower()

    # Extraire les composants de date de l'entité
    date_patterns = [
        r'(\w+)\s+(\d{4})',  # "January 2013"
        r'(\d{1,2})/(\d{4})',  # "01/2013"
        r'(\d{1,2})-(\d{4})',  # "01-2013"
        r'(\w+)\s+(\d{1,2}),?\s+(\d{4})',  # "January 15, 2013"
        r'(\d{1,2})\s+(\w+)\s+(\d{4})',  # "15 January 2013"
    ]

    # Tenter de parser l'entité comme date
    entity_components = set()
    for pattern in date_patterns:
        match = re.search(pattern, entity_lower)
        if match:
            entity_components.update(match.groups())

    if not entity_components:
        # Si pas de format date reconnu, recherche normale
        return -1, -1, entity_text

    # Chercher ces composants dans différents formats dans le texte
    search_patterns = [
        # Format exact
        re.escape(entity_lower),

        # Variantes avec ponctuation
        re.escape(entity_lower.replace(',', '')),
        re.escape(entity_lower.replace(',', ' ')),

        # Si c'est "January 2013", chercher aussi:
        # - "January, 2013"
        # - "Jan 2013"
        # - "01/2013"
        # etc.
    ]

    # Ajouter des variantes spécialisées
    if len(entity_components) >= 2:
        components = list(entity_components)

        # Mois + année
        month_abbrevs = {
            'january': 'jan', 'february': 'feb', 'march': 'mar',
            'april': 'apr', 'may': 'may', 'june': 'jun',
            'july': 'jul', 'august': 'aug', 'september': 'sep',
            'october': 'oct', 'november': 'nov', 'december': 'dec'
        }

        for comp in components:
            if comp in month_abbrevs:
                # Chercher version abrégée
                abbrev_version = entity_lower.replace(comp, month_abbrevs[comp])
                search_patterns.append(re.escape(abbrev_version))

                # Chercher avec virgule
                comma_version = entity_lower.replace(comp, comp + ',')
                search_patterns.append(re.escape(comma_version))

    # Effectuer la recherche avec tous les patterns
    for pattern in search_patterns:
        match = re.search(pattern, page_lower)
        if match:
            start_pos = match.start()
            end_pos = match.end()
            actual_text = page_text[start_pos:end_pos]
            return start_pos, end_pos, actual_text

    # Recherche plus permissive : composants séparés mais proches
    return _find_date_components_nearby(entity_components, page_text)


def _find_date_components_nearby(components, page_text, max_distance=50):
    """
    Cherche les composants de date qui sont proches dans le texte
    """
    import re

    page_lower = page_text.lower()
    positions = []

    for comp in components:
        if len(comp) >= 3:  # Ignorer les composants trop courts
            for match in re.finditer(re.escape(comp), page_lower):
                positions.append((match.start(), match.end(), comp))

    if len(positions) < 2:
        return -1, -1, ""

    # Trouver la paire de composants la plus proche
    positions.sort()

    for i in range(len(positions) - 1):
        start1, end1, comp1 = positions[i]
        start2, end2, comp2 = positions[i + 1]

        distance = start2 - end1
        if 0 <= distance <= max_distance:
            # Prendre toute la zone entre les deux composants
            full_start = start1
            full_end = end2
            actual_text = page_text[full_start:full_end]
            return full_start, full_end, actual_text.strip()

    return -1, -1, ""


def _find_flexible_match(entity_text, page_text):
    """
    Recherche flexible avec variations de ponctuation, espaces, etc.
    """
    import re

    page_lower = page_text.lower()
    entity_lower = entity_text.lower()

    # Variations à tester
    variations = [
        entity_lower,
        entity_lower.replace(',', ''),
        entity_lower.replace(',', ' '),
        entity_lower.replace('-', ' '),
        entity_lower.replace('/', ' '),
        re.sub(r'\s+', ' ', entity_lower),  # Normaliser les espaces
        re.sub(r'\s+', r'\\s*', re.escape(entity_lower)),  # Espaces flexibles
    ]

    for variation in variations:
        if variation != entity_lower:  # Déjà testé avant
            # Recherche normale
            start_pos = page_lower.find(variation)
            if start_pos >= 0:
                end_pos = start_pos + len(variation)
                actual_text = page_text[start_pos:end_pos]
                return start_pos, end_pos, actual_text

            # Recherche regex si c'est un pattern
            if '\\' in variation:
                try:
                    match = re.search(variation, page_lower)
                    if match:
                        start_pos = match.start()
                        end_pos = match.end()
                        actual_text = page_text[start_pos:end_pos]
                        return start_pos, end_pos, actual_text
                except:
                    pass

    return -1, -1, entity_text


def _find_keyword_match(entity_text, page_text):
    """
    Recherche par mots-clés améliorée qui garde plus de contexte
    """
    page_lower = page_text.lower()
    words = entity_text.lower().split()

    # Trier par longueur décroissante pour privilégier les mots plus spécifiques
    words.sort(key=len, reverse=True)

    for word in words:
        if len(word) >= 3:  # Réduire le seuil de 4 à 3 caractères
            start_pos = page_lower.find(word)
            if start_pos >= 0:
                # Essayer de prendre plus de contexte autour du mot trouvé
                context_start = max(0, start_pos - 20)
                context_end = min(len(page_text), start_pos + len(word) + 20)
                context = page_text[context_start:context_end]

                # Chercher si d'autres mots de l'entité sont dans ce contexte
                context_lower = context.lower()
                other_words_found = sum(1 for w in words if w != word and w in context_lower)

                if other_words_found > 0:
                    # Prendre tout le contexte contenant plusieurs mots
                    return context_start, context_end, context.strip()
                else:
                    # Juste le mot trouvé
                    end_pos = start_pos + len(word)
                    actual_text = page_text[start_pos:end_pos]
                    return start_pos, end_pos, actual_text

    return -1, -1, entity_text

