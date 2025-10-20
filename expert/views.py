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
    2: ["february", "feb", "feb.", "fÃ©vrier", "fevrier", "fÃ©vr", "fevr", "fÃ©vr.", "02"],
    3: ["march", "mar", "mar.", "mars", "03"],
    4: ["april", "apr", "apr.", "avril", "avr", "avr.", "04"],
    5: ["may", "mai", "05"],
    6: ["june", "jun", "jun.", "juin", "06"],
    7: ["july", "jul", "jul.", "juillet", "juil", "juil.", "07"],
    8: ["august", "aug", "aug.", "aoÃ»t", "aout", "08"],
    9: ["september", "sep", "sept", "sept.", "septembre", "09"],
    10: ["october", "oct", "oct.", "octobre", "10"],
    11: ["november", "nov", "nov.", "novembre", "11"],
    12: ["december", "dec", "dec.", "dÃ©cembre", "decembre", "dÃ©c", "dec", "12"],
}

def _is_date_like(s: str) -> tuple[bool, int|None, str|None]:
    """Vrai si s contient 'mois + annÃ©e' (FR/EN/abbr) ou formats 01/2013, 2013-01, 01-2013."""
    if not s: return (False, None, None)
    text = s.strip().lower()
    # mois + annÃ©e (FR/EN, abbr, ponctuation optionnelle)
    for mnum, variants in MONTH_MAP.items():
        month_alt = "|".join([re.escape(v) for v in variants if not v.isdigit()])
        if re.search(rf"\b(?:{month_alt})\s*[,/-]?\s*\b(20\d{{2}}|19\d{{2}})\b", text, flags=re.IGNORECASE):
            year = re.search(r"(20\d{2}|19\d{2})", text).group(1)
            return (True, mnum, year)
    # numÃ©riques (01/2013, 2013/01, 2013-01)
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

        # Base queryset: documents prÃªts pour rÃ©vision expert
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

        # Aggregates for annotations (limitÃ©s aux docs prÃªts)
        ann_qs = Annotation.objects.filter(
        page__document__in=docs_qs,
        validation_status__in=['pending', 'validated', 'expert_created']
    )
        total_annotations = ann_qs.count()
        validated_annotations = ann_qs.filter(validation_status='validated').count()
        pending_annotations = ann_qs.filter(validation_status='pending').count()
        rejected_annotations = ann_qs.filter(validation_status='rejected').count()

        # RÃ©partition des documents par statut de rÃ©vision
        completed_reviews = docs_qs.filter(total_ann__gt=0, validated_ann=F('total_ann')).count()
        # Documents avec annotations mais non totalement validÃ©s (inclut potentiellement des rejetÃ©s)
        in_progress_reviews = docs_qs.filter(total_ann__gt=0).exclude(validated_ann=F('total_ann')).count()
        # Documents ayant au moins une annotation rejetÃ©e
        rejected_documents = docs_qs.filter(rejected_ann__gt=0).count()
        # Documents sans aucune annotation encore
        to_review_count = docs_qs.filter(total_ann=0).count()

        # KPI dÃ©rivÃ©s
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
            # updated_at basÃ© sur la derniÃ¨re annotation sinon fallback
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
                page_summary = f"Page {current_page_num}: Aucune annotation disponible pour gÃ©nÃ©rer un rÃ©sumÃ©."

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
    Valide / rejette une annotation + régénère résumé page + met à jour JSON global (fusion) + déclenche global.
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

        # Régénère résumé page & met à jour JSON global (fusion)
        try:
            new_page_summary, _ = build_page_summary_and_json(annotation.page, request.user)
            update_document_global_json(annotation.page.document, request.user)
        except Exception as e:
            print(f"⚠️ Erreur régénération résumé/JSON après {action}: {e}")
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
    Création d'une annotation (pré-validée) + MAJ JSON fusionné + régénération résumé page/doc.
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

        # MAJ page + JSON global (fusion) + déclenchement résumé global
        try:
            build_page_summary_and_json(page, request.user)
            # Resume global (IMMEDIATE pour action manuelle expert - ignore le throttling)
            REGENERATION_CACHE.pop(page.document.id, None); trigger_summary_regeneration_safe(page.document, request.user, 0)  # Immediate for manual expert action
        except Exception as e:
            print(f"✖️ Erreur MAJ JSON/summary (create): {e}")

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
    Modification d'une annotation (→ validée) + MAJ JSON fusionné + régénération résumé page/doc.
    Version améliorée avec fusion pour préserver les annotations existantes.
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'})

    try:
        data = json.loads(request.body)
        annotation = get_object_or_404(Annotation, id=annotation_id)

        new_text = (data.get('text') or '').strip()
        new_entity_type_name = (data.get('entity_type') or '').strip()
        if not new_entity_type_name:
            return JsonResponse({'success': False, 'error': 'entity_type is required'})

        # Sauvegarder les anciennes valeurs pour diagnostic
        old_text = annotation.selected_text
        old_type = annotation.annotation_type.display_name

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

        # MAJ page + JSON global avec FUSION (préserver annotations existantes)
        new_page_summary = None
        fusion_success = False
        try:
            # Debug avant fusion
            debug_json_fusion(page.document, f"modify_annotation by {request.user.username}")
            print(f"🔄 Modification: '{old_text}' ({old_type}) → '{new_text}' ({new_entity_type_name})")

            # Fusion page : mise à jour intelligente des entités
            new_page_summary, merged_entities = build_page_summary_and_json(page, request.user)

            # Fusion document global : préserve toutes les autres annotations
            update_document_global_json(page.document, request.user)

            fusion_success = True
            print(f"✅ Fusion réussie - Annotation modifiée")

            # Debug après fusion
            debug_json_fusion(page.document, f"modify_annotation_completed by {request.user.username}")

        except Exception as e:
            print(f"⚠️ Erreur MAJ JSON/summary (modify): {e}")
            # Fallback : essayer juste la page
            try:
                new_page_summary, _ = build_page_summary_and_json(page, request.user)
                print(f"✅ Fallback page summary réussi")
            except Exception as e2:
                print(f"❌ Fallback page summary échoué: {e2}")

        # Déclenchement régénération globale (async)
            # Resume global (IMMEDIATE pour action manuelle expert - ignore le throttling)
            REGENERATION_CACHE.pop(page.document.id, None); trigger_summary_regeneration_safe(page.document, request.user, 0)  # Immediate for manual expert action
        except Exception as e:
            print(f"⚠️ Erreur déclenchement régénération (modify): {e}")

        return JsonResponse({
            'success': True,
            'message': 'Annotation modifiée, validée et JSON mis à jour avec préservation',
            'page_summary': new_page_summary,
            'auto_summary_triggered': True,
            'fusion_applied': fusion_success,
            'preservation_mode': 'active',
            'modification_details': {
                'old_text': old_text,
                'new_text': new_text,
                'old_type': old_type,
                'new_type': new_entity_type_name
            }
        })

    except Exception as e:
        print(f"❌ Erreur modify_annotation_ajax: {e}")
        return JsonResponse({'success': False, 'error': str(e)})


def debug_json_fusion(document, user_action="unknown"):
    """
    Fonction de diagnostic pour vérifier la fusion JSON
    """
    try:
        from django.db.models import Count

        # Compter les annotations par statut
        status_counts = {}
        for status in GLOBAL_JSON_STATUSES:
            count = document.pages.aggregate(
                total=Count('annotations', filter=Q(annotations__validation_status=status))
            )['total'] or 0
            status_counts[status] = count

        total_annotations = sum(status_counts.values())

        json_entities_count = 0
        json_entities_types = []
        if document.global_annotations_json:
            entities = document.global_annotations_json.get('entities', {})
            json_entities_count = sum(len(values) for values in entities.values())
            json_entities_types = list(entities.keys())

        print(f"[DEBUG] FUSION - Action: {user_action}")
        print(f"   📊 Annotations par statut: {status_counts}")
        print(f"   📊 Total annotations en DB: {total_annotations}")
        print(f"   📋 Total entités en JSON: {json_entities_count}")
        print(f"   📝 Types d'entités en JSON: {json_entities_types}")
        if total_annotations > 0:
            print(f"   ⚖️ Ratio JSON/DB: {json_entities_count / total_annotations:.2f}")
        else:
            print(f"   ⚖️ Pas d'annotations")

        if total_annotations > 0 and json_entities_count == 0:
            print("   ⚠️ PROBLÈME: JSON vide mais annotations présentes!")
        elif json_entities_count > 0:
            print("   ✅ JSON contient des entités")

    except Exception as e:
        print(f"   ❌ Erreur diagnostic: {e}")


def update_document_global_json(document, user=None):
    """
    Reconstruit complètement les entités à partir des annotations actuelles.
    CORRIGÉ: Ne fusionne plus avec l'existant pour refléter les suppressions.
    """
    from rawdocs.views import _build_entities_map

    all_annotations = Annotation.objects.filter(
        page__document=document,
        validation_status__in=GLOBAL_JSON_STATUSES  # Inclut pending, validated, expert_created
    ).select_related('annotation_type', 'page').order_by('page__page_number', 'start_pos')

    # Reconstruire complètement les entités à partir des annotations actuelles
    current_entities = _build_entities_map(all_annotations, use_display_name=True)

    # CORRECTION: Utiliser directement current_entities au lieu de fusionner
    # Cela permet de refléter les suppressions d'annotations
    document_json = {
        'document': {
            'id': str(document.id),
            'title': document.title,
            'doc_type': getattr(document, 'doc_type', None),
            'source': getattr(document, 'source', None),
            'total_pages': document.total_pages,
            'total_annotations': all_annotations.count(),
        },
        'entities': current_entities,  # Directement les entités actuelles
        'generated_at': datetime.utcnow().isoformat() + 'Z',
    }

    document.global_annotations_json = document_json
    document.save(update_fields=['global_annotations_json'])
    return document_json

@expert_required
@csrf_exempt
def delete_annotation_ajax(request, annotation_id):
    """Delete an annotation + rebuild JSON fusion (préserve pending)."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'})

    try:
        annotation = get_object_or_404(Annotation, id=annotation_id)
        doc = annotation.page.document

        # LOG avant suppression
        log_expert_action(
            user=request.user,
            action='annotation_deleted',
            annotation=annotation,
            reason=f"Manual deletion by expert. Annotation was: {annotation.validation_status}"
        )

        annotation.delete()

        # Rebuild JSON global en fusion conservant les pending restants
        try:
            update_document_global_json(doc, request.user)
            trigger_summary_regeneration_safe(doc, request.user, 3)
        except Exception as e:
            print(f"⚠️ Rebuild JSON after delete failed: {e}")

        return JsonResponse({'success': True, 'message': 'Annotation supprimée'})

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@expert_required
@csrf_exempt
def undo_validation_ajax(request, annotation_id):
    """
    Annuler la validation → 'pending' + régénère résumé page + MAJ JSON global (fusion)
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
            update_document_global_json(annotation.page.document, request.user)
        except Exception as e:
            print(f"⚠️ Erreur régénération résumé/JSON (undo): {e}")
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
        'form': 'ComprimÃ©',
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

    print("ðŸ” DEBUGGING PRODUCT ADDITIONAL ANNOTATIONS")
    print("=" * 50)

    for product in Product.objects.all():
        print(f"ðŸ“¦ Product: {product.name}")
        if hasattr(product, 'additional_annotations'):
            print(f"   additional_annotations: {product.additional_annotations}")
        else:
            print(f"   âŒ No additional_annotations field")
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
                    print(f"âœ… Saved additional annotations: {product_data['additional_annotations']}")
            except Exception as e:
                print(f"âš ï¸ Additional annotations field not ready yet: {e}")

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
            print(f"âœ… Updated additional annotations: {additional_annotations}")
        except Exception as e:
            print(f"âš ï¸ Could not update additional annotations: {e}")

    print(f"ðŸŽ¯ Updated existing product '{existing_product.name}' with {len(variations_created)} variations")

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

            # Fonction helper pour gÃ©rer les dates
            def safe_isoformat(date_value):
                if date_value is None:
                    return None
                if isinstance(date_value, str):
                    return date_value
                if hasattr(date_value, 'isoformat'):
                    return date_value.isoformat()
                return str(date_value)

            # Sauvegarder dans MongoDB avec toutes les mÃ©tadonnÃ©es lors de la validation
            from rawdocs.models import CustomFieldValue

            # Construire les mÃ©tadonnÃ©es complÃ¨tes
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

            # Ajouter les champs personnalisÃ©s
            custom_fields = {}
            for custom_value in CustomFieldValue.objects.filter(document=document):
                custom_fields[custom_value.field.name] = custom_value.value

            if custom_fields:
                metadata['custom_fields'] = custom_fields

            # RÃ©cupÃ©rer les entitÃ©s du JSON global si elles existent
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

            # PrÃ©parer le message Ã  renvoyer (et conserver messages Django pour fallback)
            response_message = ''
            if product:
                debug_product_annotations()
                variations_today = ProductVariation.objects.filter(
                    product=product,
                    submission_date=timezone.now().date()
                ).count()

                if variations_today > 0:
                    response_message = (
                        f'ðŸŽ‰ Document validÃ© avec succÃ¨s! Le produit "{product.name}" a Ã©tÃ© mis Ã  jour avec {variations_today} nouvelle(s) variation(s). '
                        f'Consultez l\'onglet "Variations" pour voir les changements.'
                    )
                    messages.success(request, response_message)
                else:
                    response_message = (
                        f'ðŸŽ‰ Document validÃ© avec succÃ¨s! Le produit "{product.name}" a Ã©tÃ© crÃ©Ã© dans le module client.'
                    )
                    messages.success(request, response_message)
            else:
                debug_info = debug_annotations_for_product(document)
                response_message = (
                    f'âš ï¸ Document validÃ© mais aucun produit crÃ©Ã©. DÃ©tails: {debug_info}'
                )
                messages.warning(request, response_message)

            # Si appel AJAX, renvoyer JSON au lieu de rediriger
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': True, 'message': response_message})

            return redirect('expert:dashboard')

        except Exception as e:
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'success': False, 'error': str(e)}, status=500)
            messages.error(request, f'âŒ Erreur lors de la validation: {str(e)}')
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
                "<p>Le fichier PDF n'a pas pu Ãªtre chargÃ©.</p>"
                "<script>window.close();</script></body></html>"
            )
    else:
        return HttpResponse(
            "<html><body><h2>Aucun fichier disponible</h2>"
            "<p>Ce document n'a pas de fichier PDF associÃ©.</p>"
            "<script>window.close();</script></body></html>"
        )


@expert_required
@csrf_exempt
def save_page_json(request, page_id):
    """Sauvegarde du JSON modifiÃ© d'une page"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        page = get_object_or_404(DocumentPage, id=page_id)
        data = json.loads(request.body)
        json_content = data.get('json_content')

        if not json_content:
            return JsonResponse({'error': 'JSON content is required'}, status=400)

        # Valider que le JSON est bien formatÃ©
        try:
            parsed_json = json.loads(json_content)
        except json.JSONDecodeError as e:
            return JsonResponse({'error': f'Invalid JSON format: {str(e)}'}, status=400)

        # Sauvegarder le nouveau JSON
        page.annotations_json = parsed_json
        page.annotations_summary_generated_at = timezone.now()
        page.save(update_fields=['annotations_json', 'annotations_summary_generated_at'])

        # Mise Ã  jour du JSON global du document
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
            'message': 'JSON sauvegardÃ© avec succÃ¨s'
        })

    except Exception as e:
        print(f"âŒ Erreur lors de la sauvegarde du JSON de la page: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)


# expert/views.py - Modifier uniquement la fonction save_document_json

# expert/views.py - Corriger la fonction save_document_json

@expert_required
@csrf_exempt
#################
# Ã€ ajouter dans expert/views.py

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
#         # 2) PrÃ©parer/initialiser le JSON global et les entitÃ©s si manquants
#         current_json = document.global_annotations_json or {}
#         current_json.setdefault('document', {})
#         current_entities = current_json.get('entities', {}) or {}
#
#         if not current_entities:
#             # Tenter de construire les entitÃ©s depuis les annotations du document
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
#             # Si toujours vide (ex: document sans annotations), initialiser des clÃ©s par dÃ©faut
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
#         # 1) Extraire les entitÃ©s du nouveau rÃ©sumÃ©:
#         #    a) via libellÃ©s existants (ClÃ©: valeur)
#         extracted_by_keys = extract_by_allowed_keys(new_summary, allowed_keys)
#         #    b) via texte libre (phrases), en dÃ©tectant entitÃ©/valeur
#         free_extracted = extract_entities_from_text(new_summary) or {}
#         #       b2) enrichissement par dÃ©tections ciblÃ©es (route, packaging, pack size, forme)
#         try:
#             # Route of Administration
#             route_vals = set()
#             for m in re.finditer(
#                     r"(?i)(?:par\s+voie\s+|voie\s+)(orale|intraveineuse|intramusculaire|sous\s*cutan[eÃ©]e|subcutan[eÃ©]e|nasale|topique|cutan[eÃ©]e|rectale|inhalation)",
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
#                     r"(?i)\b(blisters?|blister|flacons?|bouteilles?|bottles?|sachets?|ampoules?|seringues?\s*pr[Ã©e]remplies?)\b",
#                     new_summary):
#                 packaging_vals.add(m.group(0))
#             if packaging_vals:
#                 free_extracted.setdefault('Immediate Packaging', []).extend(sorted(packaging_vals))
#
#             # Pack Size (ex: 20 comprimÃ©s, 100 ml, 6 sachets)
#             pack_vals = set()
#             for m in re.finditer(
#                     r"(?i)\b([0-9]{1,4}\s*(?:comprim[ée]s?|g[ée]lules?|capsules?|sachets?|ml|ampoules?|unit[eÃ©]s?))\b",
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
#         #    c) Fusionner en ne gardant que les clÃ©s existantes (mapping canonique)
#         extracted_entities: dict[str, list[str]] = {}
#         for k, vals in (extracted_by_keys or {}).items():
#             extracted_entities.setdefault(k, []).extend(vals or [])
#         for raw_k, vals in (free_extracted or {}).items():
#             canon = _canonical_key(raw_k, allowed_keys)
#             if not canon:
#                 continue
#             extracted_entities.setdefault(canon, []).extend(vals or [])
#         # DÃ©duplication + nettoyage par type
#         for k, vals in list(extracted_entities.items()):
#             extracted_entities[k] = _clean_values_for_type(k, vals or [])
#         print(f"EntitÃ©s extraites (fusion): {extracted_entities}")
#
#         # 3) Mise Ã  jour fine par valeurs (ajouts/suppressions basÃ©es sur le rÃ©sumÃ©)
#         updated_entities = current_entities.copy()
#         changes_made = []
#         entities_added: dict[str, list[str]] = {}
#         entities_removed: dict[str, list[str]] = {}
#         changed_keys: list[str] = []
#
#         # Normaliser les clÃ©s permises (mapping insensible Ã  la casse)
#         key_map = {k.lower(): k for k in allowed_keys}
#
#         # Extraire entitÃ©s de l'ancien rÃ©sumÃ© pour dÃ©tecter suppressions (toutes clÃ©s)
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
#             # valeurs extraites anciennes et nouvelles pour cette clÃ©
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
#             # suppressions: prÃ©sentes avant, absentes maintenant
#             to_remove = old_norms - new_norms
#             # ajouts: prÃ©sentes dans le nouveau rÃ©sumÃ©, pas dÃ©jÃ  existantes
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
#         # 4) Sauvegarder le rÃ©sumÃ©
#         document.global_annotations_summary = new_summary
#         document.global_annotations_summary_generated_at = timezone.now()
#
#         # 5) Mettre Ã  jour le JSON
#         current_json['entities'] = updated_entities
#
#         # 6) Mettre Ã  jour les mÃ©tadonnÃ©es
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
#             reason += " | Aucune entitÃ© changÃ©e"
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
#             'message': 'RÃ©sumÃ© sauvegardÃ© et entitÃ©s synchronisÃ©es',
#             'updated_json': current_json,
#             'changes_made': changes_made,
#             'changed_keys': changed_keys,
#             'entities_added': entities_added,
#             'entities_removed': entities_removed,
#             'entities_changes': changes_made,
#         })
#
#         # mÃ©tadonnÃ©es de mise Ã  jour
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
#         # (optionnel) push Mongo iciâ€¦
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
#             'message': 'RÃ©sumÃ© sauvegardÃ©',
#             'updated_json': current_json,
#             'changed_keys': changed_keys,
#             'entities_changes': human_diffs,
#         })
#     except Exception as e:
#         import traceback; print(f"[ERROR] save_summary_changes error: {e}"); print(traceback.format_exc())
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
        page_id = payload.get('page_id', None)  # NOUVEAU: rÃ©cupÃ©rer l'ID de la page



        if not new_summary:
            return JsonResponse({'error': 'Summary cannot be empty'}, status=400)

        old_summary = document.global_annotations_summary or ""

        # 2) PrÃ©parer/initialiser le JSON global et les entitÃ©s si manquants
        current_json = document.global_annotations_json or {}
        current_json.setdefault('document', {})
        current_entities = current_json.get('entities', {}) or {}

        if not current_entities:
            # Construire les entitÃ©s depuis les annotations du document
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

        # ===== NOUVELLE FONCTIONNALITÃ‰ : ANNOTATION AUTOMATIQUE PAR IA =====
        new_annotations_created = []
        # MODIFICATION: Passer page_id Ã  la fonction
        if auto_annotate and old_summary != new_summary:
            try:
                new_entities = await_ai_extract_and_annotate(
                    document, old_summary, new_summary, allowed_keys,
                    request.user, page_id=page_id  # NOUVEAU: passer page_id
                )
                if new_entities:
                    new_annotations_created = new_entities
                    # Mettre Ã  jour current_entities avec les nouvelles entitÃ©s trouvÃ©es par IA
                    for entity_type, values in new_entities.items():
                        if entity_type in allowed_keys:
                            current_entities[entity_type] = list(set(current_entities.get(entity_type, []) + values))
            except Exception as e:
                import traceback; print(f"[WARNING] Erreur annotation IA automatique: {e}"); print(traceback.format_exc())

        # Extraction des entitÃ©s du nouveau rÃ©sumÃ© (mÃ©thode existante)
        extracted_by_keys = extract_by_allowed_keys(new_summary, allowed_keys)
        free_extracted = extract_entities_from_text(new_summary) or {}

        # Enrichissement par dÃ©tections ciblÃ©es (route, packaging, pack size, forme)
        try:
            # Route of Administration
            route_vals = set()
            for m in re.finditer(
                    r"(?i)(?:par\s+voie\s+|voie\s+)(orale|intraveineuse|intramusculaire|sous\s*cutan[eÃ©]e|subcutan[eÃ©]e|nasale|topique|cutan[eÃ©]e|rectale|inhalation)",
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
                    r"(?i)\b(blisters?|blister|flacons?|bouteilles?|bottles?|sachets?|ampoules?|seringues?\s*prÃ©?remplies?)\b",
                    new_summary):
                packaging_vals.add(m.group(0))
            if packaging_vals:
                free_extracted.setdefault('Immediate Packaging', []).extend(sorted(packaging_vals))

            # Pack Size
            pack_vals = set()
            for m in re.finditer(
                    r"(?i)\b([0-9]{1,4}\s*(?:comprim[ée]s?|gÃ©?lules?|capsules?|sachets?|ml|ampoules?|unit[eÃ©]s?))\b",
                    new_summary):
                pack_vals.add(m.group(1))
            if pack_vals:
                free_extracted.setdefault('Pack Size', []).extend(sorted(pack_vals))

            # Pharmaceutical Form
            form_vals = set()
            for m in re.finditer(
                    r"(?i)\b(comprim[ée]s?|gÃ©?lules?|capsules?|sirop|solution|suspension|poudre|injectable|tablet[s]?)\b",
                    new_summary):
                form_vals.add(m.group(0))
            if form_vals:
                free_extracted.setdefault('Pharmaceutical Form', []).extend(sorted(form_vals))
        except Exception:
            pass

        # Fusionner les entitÃ©s extraites
        extracted_entities: dict[str, list[str]] = {}
        for k, vals in (extracted_by_keys or {}).items():
            extracted_entities.setdefault(k, []).extend(vals or [])
        for raw_k, vals in (free_extracted or {}).items():
            canon = _canonical_key(raw_k, allowed_keys)
            if not canon:
                continue
            extracted_entities.setdefault(canon, []).extend(vals or [])

        # DÃ©duplication + nettoyage par type
        for k, vals in list(extracted_entities.items()):
            extracted_entities[k] = _clean_values_for_type(k, vals or [])

        # Mise Ã  jour fine par valeurs
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

        # Sauvegarder le rÃ©sumÃ©
        document.global_annotations_summary = new_summary
        document.global_annotations_summary_generated_at = timezone.now()

        # Mettre Ã  jour le JSON
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
            'message': 'RÃ©sumÃ© sauvegardÃ© et entitÃ©s synchronisÃ©es',
            'updated_json': current_json,
            'changes_made': changes_made,
            'changed_keys': changed_keys,
            'entities_added': entities_added,
            'entities_removed': entities_removed,
            'entities_changes': changes_made,
            'ai_annotations_created': new_annotations_created,  # Nouvelles annotations IA
        })

    except Exception as e:
        import traceback; print(f"[ERROR] save_summary_changes error: {e}"); print(traceback.format_exc())
        return JsonResponse({'error': str(e)}, status=500)


# Nouvelle fonction pour l'annotation automatique par IA
# def await_ai_extract_and_annotate(document, old_summary, new_summary, allowed_keys, user):
#     """
#     Utilise l'IA pour identifier les nouvelles informations dans le rÃ©sumÃ©
#     et crÃ©er automatiquement des annotations dans le document
#     """
#     try:
#         from rawdocs.groq_annotation_system import GroqAnnotator
#
#         # Calculer les diffÃ©rences entre ancien et nouveau rÃ©sumÃ©
#         diff_text = find_summary_differences(old_summary, new_summary)
#         if not diff_text.strip():
#             return {}
#
#         # Utiliser Groq pour identifier les entitÃ©s dans les nouvelles informations
#         groq_annotator = GroqAnnotator()
#
#         # Contexte pour l'IA
#         context = f"""
# Document: {document.title}
# Ancien rÃ©sumÃ©: {old_summary[:500]}...
# Nouveau rÃ©sumÃ©: {new_summary[:500]}...
# Types d'entitÃ©s autorisÃ©s: {', '.join(allowed_keys)}
#
# Nouvelles informations ajoutÃ©es:
# {diff_text}
# """
#
#         # Prompt pour extraire et crÃ©er des annotations
#         prompt = f"""
# Analyse les nouvelles informations ajoutÃ©es au rÃ©sumÃ© et identifie les entitÃ©s Ã  annoter automatiquement.
#
# Contexte: {context}
#
# Instructions:
# 1. Identifie UNIQUEMENT les nouvelles informations (qui n'Ã©taient pas dans l'ancien rÃ©sumÃ©)
# 2. Extrait les entitÃ©s pharmaceutiques pertinentes selon les types autorisÃ©s
# 3. Pour chaque entitÃ© trouvÃ©e, propose le texte exact Ã  annoter dans le document
#
# RÃ©ponds en JSON:
# {{
#     "entities_to_annotate": [
#         {{
#             "type": "entity_type",
#             "value": "texte exact",
#             "confidence": 0.0-1.0,
#             "context": "contexte oÃ¹ Ã§a apparaÃ®t"
#         }}
#     ]
# }}
# """
#
#         # Appel Ã  Groq
#         response = groq_annotator.complete_text(prompt, max_tokens=1000)
#
#         if response:
#             try:
#                 ai_result = json.loads(response)
#                 entities_to_annotate = ai_result.get('entities_to_annotate', [])
#
#                 created_annotations = {}
#
#                 # CrÃ©er automatiquement les annotations identifiÃ©es par l'IA
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
#                             # CrÃ©er l'annotation automatiquement
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
#                 print("âš ï¸ Erreur parsing rÃ©ponse IA pour annotation automatique")
#                 return {}
#
#         return {}
#
#     except Exception as e:
#         import traceback; print(f"[WARNING] Erreur annotation IA automatique: {e}"); print(traceback.format_exc())
#         return {}


def find_summary_differences(old_summary, new_summary):
    """Trouve les diffÃ©rences entre deux rÃ©sumÃ©s"""
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

            # Score basÃ© sur la prÃ©sence du texte exact ou similaire
            score = 0
            if entity_lower in text:
                score = 100
            else:
                # Recherche de mots-clÃ©s similaires
                words = entity_lower.split()
                for word in words:
                    if len(word) > 3 and word in text:
                        score += 20

            if score > best_score:
                best_score = score
                best_page = page

    return best_page if best_score > 30 else pages.first()


def create_ai_annotation(page, entity_value, entity_type, user, confidence):
    """CrÃ©e une annotation automatiquement via IA"""
    try:
        # Chercher le texte dans la page
        if hasattr(page, 'cleaned_text') and page.cleaned_text:
            text_content = page.cleaned_text
            start_pos = text_content.lower().find(entity_value.lower())

            if start_pos == -1:
                # Si pas trouvÃ© exactement, chercher des mots-clÃ©s
                words = entity_value.split()
                for word in words:
                    if len(word) > 3:
                        start_pos = text_content.lower().find(word.lower())
                        if start_pos != -1:
                            entity_value = word  # Utiliser le mot trouvÃ©
                            break

            if start_pos != -1:
                end_pos = start_pos + len(entity_value)

                # CrÃ©er ou rÃ©cupÃ©rer le type d'annotation
                annotation_type, created = AnnotationType.objects.get_or_create(
                    name=entity_type,
                    defaults={
                        'display_name': entity_type.replace('_', ' ').title(),
                        'color': '#8b5cf6',  # Violet pour les annotations IA automatiques
                        'description': f"Auto-generated by AI from summary: {entity_type}"
                    }
                )

                # CrÃ©er l'annotation
                annotation = Annotation.objects.create(
                    page=page,
                    selected_text=entity_value,
                    annotation_type=annotation_type,
                    start_pos=start_pos,
                    end_pos=end_pos,
                    validation_status='expert_created',  # PrÃ©-validÃ©e car crÃ©Ã©e par expert
                    validated_by=user,
                    validated_at=timezone.now(),
                    created_by=user,
                    source='expert_ai_auto',
                    confidence_score=confidence
                )

                print(f"âœ… Annotation IA automatique crÃ©Ã©e: {entity_value} ({entity_type}) dans page {page.page_number}")
                return True

        return False

    except Exception as e:
        print(f"âš ï¸ Erreur crÃ©ation annotation automatique: {e}")
        return False

# --- helpers backend : extraction stricte + nettoyage ---

import re


# Ajouter Ã  expert/views.py - Nouvelle fonction pour rÃ©gÃ©nÃ©ration automatique du rÃ©sumÃ©

@expert_required
@csrf_exempt
def auto_regenerate_summary_from_annotations(request, doc_id):
    """
    RÃ©gÃ©nÃ¨re automatiquement le rÃ©sumÃ© basÃ© sur les annotations actuelles
    AppelÃ© quand les annotations sont modifiÃ©es
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        document = get_object_or_404(RawDocument, id=doc_id)

        # RÃ©cupÃ©rer toutes les annotations validÃ©es du document
        all_annotations = Annotation.objects.filter(
            page__document=document,
            validation_status__in=['validated', 'expert_created']
        ).select_related('annotation_type', 'page').order_by('page__page_number', 'start_pos')

        if not all_annotations.exists():
            return JsonResponse({
                'success': False,
                'error': 'No validated annotations found'
            })

        # Construire les entitÃ©s depuis les annotations
        from rawdocs.views import _build_entities_map, generate_entities_based_document_summary
        entities = _build_entities_map(all_annotations, use_display_name=True)

        # GÃ©nÃ©rer un nouveau rÃ©sumÃ© basÃ© sur les annotations actuelles
        new_summary = generate_entities_based_document_summary(
            entities=entities,
            doc_title=document.title,
            doc_type=getattr(document, 'doc_type', None),
            total_annotations=all_annotations.count()
        )

        # Enrichir le rÃ©sumÃ© avec l'IA si possible
        try:
            enhanced_summary = enhance_summary_with_ai(document, entities, new_summary)
            if enhanced_summary and len(enhanced_summary) > len(new_summary):
                new_summary = enhanced_summary
        except Exception as e:
            print(f"âš ï¸ Erreur enrichissement rÃ©sumÃ© IA: {e}")

        # Sauvegarder le nouveau rÃ©sumÃ©
        old_summary = document.global_annotations_summary or ""
        document.global_annotations_summary = new_summary
        document.global_annotations_summary_generated_at = timezone.now()

        # Mettre Ã  jour le JSON global
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
            'message': 'RÃ©sumÃ© rÃ©gÃ©nÃ©rÃ© automatiquement depuis les annotations',
            'new_summary': new_summary,
            'updated_json': current_json,
            'annotations_count': all_annotations.count()
        })

    except Exception as e:
        print(f"â›” auto_regenerate_summary error: {e}")
        return JsonResponse({'error': str(e)}, status=500)


def enhance_summary_with_ai(document, entities, basic_summary):
    """
    Utilise l'IA pour enrichir le rÃ©sumÃ© gÃ©nÃ©rÃ© automatiquement
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
AmÃ©liore ce rÃ©sumÃ© pharmaceutique en ajoutant du contexte et des dÃ©tails pertinents basÃ©s sur les entitÃ©s extraites.

Document: {document.title}
Type: {getattr(document, 'doc_type', 'Pharmaceutique')}

RÃ©sumÃ© de base:
{basic_summary}

EntitÃ©s identifiÃ©es:
{entities_text}

Instructions:
1. Garde toutes les informations du rÃ©sumÃ© original
2. Ajoute des connexions logiques entre les entitÃ©s
3. Enrichis avec du contexte pharmaceutique pertinent
4. Maintiens un ton professionnel et prÃ©cis
5. Maximum 300 mots

RÃ©sumÃ© enrichi:"""

        response = groq_annotator.complete_text(prompt, max_tokens=800)

        if response and len(response.strip()) > len(basic_summary):
            return response.strip()

        return basic_summary

    except Exception as e:
        print(f"âš ï¸ Erreur enrichissement rÃ©sumÃ©: {e}")
        return basic_summary


# Modifier aussi les fonctions d'annotation existantes pour dÃ©clencher la rÃ©gÃ©nÃ©ration
# Par exemple, dans expert_save_manual_annotation, expert_delete_annotation, etc.

def trigger_summary_regeneration(document, user):
    """
    DÃ©clenche la rÃ©gÃ©nÃ©ration automatique du rÃ©sumÃ© en arriÃ¨re-plan
    """
    try:
        from django.test import RequestFactory
        factory = RequestFactory()
        fake_request = factory.post(f'/expert/document/{document.id}/auto-regenerate-summary/')
        fake_request.user = user

        # Appeler la fonction de rÃ©gÃ©nÃ©ration
        result = auto_regenerate_summary_from_annotations(fake_request, document.id)
        return True
    except Exception as e:
        print(f"âš ï¸ Erreur dÃ©clenchement rÃ©gÃ©nÃ©ration rÃ©sumÃ©: {e}")
        return False
def extract_entities_from_text(text: str) -> dict:
    """
    Extraction intelligente des entitÃ©s du texte (FR/EN + abrÃ©viations).
    Ajout: dÃ©tection robuste des Date (mois + annÃ©e, formats dd Month yyyy, mm/yyyy, yyyy-mm, etc.).
    """
    base_patterns = {
        'Product': [
            r'\b(?:produit|médicament|product)\b\s*:?\s*((?-i:[A-Z])[\w\s\-\/]{2,60})',
            r'\b(?:produit|product)\b\s+(?:est|is)\s+((?-i:[A-Z])[\w\s\-\/]{2,60})',
            r'^(?:le\s+|the\s+)?([A-Z][\w\s\-\/]{3,60})\s+(?:est|sera|contient|is|contains)\b',
            r'(?:nom du produit|product name)\s*:?\s*([A-Z][\w\s\-\/]{2,60})'
        ],
        'Dosage': [
            r'\b([0-9]+(?:[.,][0-9]+)?\s*(?:mg|g|ml|l|Âµg|mcg|%|UI|iu|mg\/ml|g\/l))\b',
            r'(?:dosage|posologie|concentration|strength)\s*:?\s*([0-9]+(?:[.,][0-9]+)?\s*(?:mg|g|ml|l|Âµg|mcg|%|UI|iu|mg\/ml|g\/l))',
        ],
        'Substance_Active': [
            r'(?:substance active|principe actif|active ingredient)\s*:?\s*([A-Z][\w\s\-]{2,60})',
            r'(?:contient|à base de|contains)\s+([A-Z][\w\s\-]{2,60})'
        ],
        'Site': [
            r'(?:site|usine|fabricant|manufacturing site|manufacturer)\s*:?\s*([A-Z][\w\s\.\-]{2,80})',
            r'(?:fabriqu[ée]|produit|manufactured|made)\s*(?:à|par|by|in)\s*([A-Z][\w\s\.\-]{2,80})'
        ],
        'Pays': [
            r'(?:pays|country)\s*:?\s*([A-Z][\w\s\-]{2,40})',
            r'(?:en|au|aux|in)\s+([A-Z][\w\s\-]{2,40})(?=[\s,\.]|$)'
        ],
        'Strength': [
            r'(?:strength|force|puissance|teneur)\s*(?:de|:)?\s*([0-9]+(?:[.,][0-9]+)?\s*(?:mg|g|ml|l|Âµg|mcg|%|UI|iu))',
            r'(?:concentration)\s*(?:de|:)?\s*([0-9]+(?:[.,][0-9]+)?\s*(?:mg|g|ml|l|Âµg|mcg|%|UI|iu))',
            r'(?:est\s+de|is)\s*([0-9]+(?:[.,][0-9]+)?\s*(?:mg|g|ml|l|Âµg|mcg|%|UI|iu))',
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
                # anti-bruit Date: refuser annÃ©e seule
                if entity_type == 'Date' and re.fullmatch(r'\d{4}', v):
                    continue
                if v and len(v) <= 100:
                    vals.add(v)
        if vals:
            results[entity_type] = list(vals)
    return results



def extract_by_allowed_keys(text: str, allowed_keys: list[str]) -> dict:
    """
    Extraction basÃ©e sur les libellÃ©s des clÃ©s existantes (insensible Ã  la casse).
    Pour chaque clÃ© existante, capture des valeurs sous les formes:
    - "<ClÃ©>: <valeur>"
    - "<ClÃ©> est/is/are <valeur>"
    Les valeurs extraites sont ensuite nettoyÃ©es par _clean_values_for_type.
    """
    results: dict[str, list[str]] = {}

    def norm_one(s: str) -> str:
        s = re.sub(r"\s+", " ", (s or "").strip())
        # normaliser espace entre nombre et unitÃ©
        s = re.sub(r"(?i)\b([0-9]+(?:[.,][0-9]+)?)(mg|g|ml|l|Âµg|mcg|%|ui)\b", r"\1 \2", s)
        return s

    text = text or ""

    for key in allowed_keys or []:
        if not key:
            continue
        label = re.escape(key)
        patterns = [
            rf"(?i)\b{label}\b\s*[:\-]\s*([^\.;\n]+)",  # ClÃ©: valeur
            rf"(?i)\b{label}\b\s*(?:est|is|are)\s*([^\.;\n]+)",  # ClÃ© est/is/are valeur
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
        s = re.sub(r'(?i)\b([0-9]+(?:[.,][0-9]+)?)(mg|g|ml|l|Âµg|mcg|%|ui)\b', r'\1 \2', s)
        return s

    seen, keep = set(), []
    k = (key or '').strip().lower()

    # --- Dates ---
    if k in {'date', 'publication date', 'effective date', 'date de publication', 'deadline'}:
        for v in values or []:
            vv = norm(v).rstrip('.,;:')
            ok, _, _ = _is_date_like(vv)
            if not ok:  # Ã©viter '2013' seule
                continue
            slug = vv.lower()
            if slug not in seen:
                seen.add(slug); keep.append(vv)
        return keep

    if k in {'dosage', 'strength'}:
        strict_rx = re.compile(r'(?i)^[0-9]+(?:[.,][0-9]+)?\s*(?:mg|g|ml|l|Âµg|mcg|%|ui|iu)(?:\s*/\s*(?:ml|l|g))?$')
        for v in values or []:
            vv = norm(v)
            m = re.search(r'(?i)([0-9]+(?:[.,][0-9]+)?\s*(?:mg|g|ml|l|Âµg|mcg|%|ui|iu)(?:\s*/\s*(?:ml|l|g))?)', vv)
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
            if not re.match(r'^(?-i:[A-Z]).*', vv):  # Ã©viter 'produits de dÃ©gradation'
                continue
            if 1 < len(vv) <= 80:
                slug = vv.lower()
                if slug not in seen:
                    seen.add(slug); keep.append(vv)
        return keep

    stop = {'de','du','des','et','la','le','les','Ã ','au','aux','pour','sur','dans','par','avec'}
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
    """Construit une map foldÃ©e -> clÃ© canonique, avec synonymes courants (FR/EN).
    Note: on ne relie des synonymes quâ€™aux clÃ©s VRAIMENT prÃ©sentes dans existing_keys.
    """
    syn: dict[str, str] = {}
    existing_keys = existing_keys or []

    # ClÃ©s existantes -> elles-mÃªmes
    for ek in existing_keys:
        syn[_fold_key(ek)] = ek

    # Lier des synonymes SEULEMENT si la clÃ© canonique est dÃ©jÃ  prÃ©sente
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
            'route', 'voie', 'voie d administration', "voie dâ€™administration",
            'route of administration', 'administration route'
        ])
    # Dates (ne liera ces synonymes que si la clÃ© canonique correspondante existe dÃ©jÃ )
    for variant in ['Date', 'Effective Date', 'Publication Date', 'Update Date', 'Deadline', 'Start Date']:
        bind(variant, [
            'date', 'effective date', 'date effective', 'publication date', 'date de publication',
            'update date', 'date de mise Ã  jour', 'deadline', 'Ã©chÃ©ance', 'date limite',
            'start date', 'date de dÃ©but', "date d'entrÃ©e en vigueur", 'date d effet', 'date dâ€™effet'
        ])


    # Conditionnement immÃ©diat
    for variant in ['Immediate Packaging', 'Packaging', 'Emballage']:
        bind(variant, ['packaging', 'emballage', 'immediate packaging', 'conditionnement'])

    # Taille de pack
    for variant in ['Pack Size', 'Packsize', 'Pack']:
        bind(variant, ['pack size', 'taille du pack', 'taille de pack', 'taille de boÃ®te', 'boÃ®te'])

    # NumÃ©ro d'AMM
    for variant in ['Ma Number', 'AMM Number', 'Authorization Number']:
        bind(variant, [
            'ma number', 'numero amm', 'numÃ©ro amm',
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
    # Permet de canoniser vers la clÃ© 'Date' (ou variantes) si elle existe dÃ©jÃ  dans le JSON
    for variant in ['Date', 'Publication Date', 'Effective Date', 'Deadline']:
        bind(variant, [
            'date', 'publication date', 'effective date', 'deadline',
            'date de publication', "date d'effet", 'date dâ€™effet',
            "date d'entrÃ©e en vigueur", "date d'entree en vigueur",
            'date effective', 'date limite', 'date de validitÃ©', 'date de validite'
        ])

    # DÃ©lai / Duration (durées, Ã  distinguer des dates)
    bind('Delay', ['dÃ©lai', 'delai', 'durée', 'duree', 'duration', 'timeframe'])

    return syn



def _canonical_key(key: str, existing_keys: list[str]) -> str | None:
    """Retourne la clÃ© canonique parmi existing_keys en utilisant un matching accent/casse/synonymes."""
    if not key:
        return None
    syn = _build_synonym_map(existing_keys)
    folded = _fold_key(key)
    return syn.get(folded)


def update_document_json_with_entities_replace_only(document, new_entities: dict) -> tuple[dict, list[str]]:
    """
    Remplace les valeurs des entitÃ©s EXISTANTES uniquement, sans en crÃ©er.
    Nettoie et dÃ©duplique. Retourne (json_mis_a_jour, liste_cles_modifiees).
    """
    current_json = document.global_annotations_json or {}
    entities = current_json.get('entities', {}) or {}
    changed = []

    existing_keys = list(entities.keys())
    if not existing_keys:
        # Rien Ã  faire si pas d'entitÃ©s existantes
        return current_json, changed

    for raw_key, values in (new_entities or {}).items():
        canon = _canonical_key(raw_key, existing_keys)
        if not canon:
            continue  # on ignore les types non prÃ©sents pour Ã©viter d'en crÃ©er
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
    """trim + dÃ©dup (insensible Ã  la casse) + espaces normalisÃ©s"""
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
    Applique des changements SEULEMENT sur les clÃ©s dÃ©jÃ  existantes.
    Retourne (entities_mises_a_jour, keys_modifiÃ©es, traces_humaines)
    """
    if not existing_entities:
        return existing_entities, [], []

    allowed = {k: k for k in existing_entities.keys()}  # map canonique
    changed_keys, human_diffs = [], []

    for raw_k, vals in (proposed_changes or {}).items():
        # ne pas crÃ©er de nouveaux types : on ne garde que les clÃ©s existantes (match insensible casse)
        canon = next((ek for ek in allowed if ek.lower() == (raw_k or '').lower()), None)
        if not canon:
            continue

        new_vals = _normalize_values(vals)
        old_vals = existing_entities.get(canon, [])
        if new_vals != old_vals:
            existing_entities[canon] = new_vals
            changed_keys.append(canon)
            human_diffs.append(f"{canon}: {old_vals} â†’ {new_vals}")

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

    # A) SDK officiel Groq (recommandÃ©)
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
            print(f"âš ï¸ GROQ SDK path failed: {e}")

    # B) Fallback via votre GroqAnnotator s'il expose une mÃ©thode utilisable
    if not content:
        try:
            ga = GroqAnnotator()
            # Essayez une mÃ©thode JSON si elle existe dans votre classe
            for m in ("chat_json", "complete_json", "ask_json"):
                if hasattr(ga, m):
                    content = getattr(ga, m)(
                        system=system, user=user,
                        model=getattr(settings, "GROQ_MODEL", "llama3-70b-8192"),
                        temperature=0.1, max_tokens=400
                    )
                    break
        except Exception as e:
            print(f"âš ï¸ GroqAnnotator fallback failed: {e}")

    if not content:
        return {}  # IA indispo â†’ pas de modif

    try:
        data = json.loads(content) if isinstance(content, str) else content
        raw_changes = data.get("changes", {}) if isinstance(data, dict) else {}
    except Exception:
        return {}

    # Filtrer: uniquement les clÃ©s existantes
    filtered = {}
    for k, vals in (raw_changes or {}).items():
        if any(k.lower() == ak.lower() for ak in allowed_keys):
            filtered[k] = _normalize_values(vals)
    return filtered


def save_document_json(request, doc_id):
    """Sauvegarde du JSON global modifiÃ© d'un document (et stockage MongoDB avec mÃ©tadonnÃ©es complÃ¨tes)"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        document = get_object_or_404(RawDocument, id=doc_id)
        data = json.loads(request.body)
        json_content = data.get('json_content')

        if not json_content:
            return JsonResponse({'error': 'JSON content is required'}, status=400)

        # Valider que le JSON est bien formatÃ©
        try:
            parsed_json = json.loads(json_content)
        except json.JSONDecodeError as e:
            return JsonResponse({'error': f'Invalid JSON format: {str(e)}'}, status=400)

        # Fonction helper pour gÃ©rer les dates
        def safe_isoformat(date_value):
            if date_value is None:
                return None
            if isinstance(date_value, str):
                return date_value
            if hasattr(date_value, 'isoformat'):
                return date_value.isoformat()
            return str(date_value)

        # Enrichir le JSON avec TOUTES les mÃ©tadonnÃ©es du document
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

        # Ajouter les champs personnalisÃ©s s'ils existent
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

        # Sauvegarder dans MongoDB avec toutes les mÃ©tadonnÃ©es
        mongo_collection.update_one(
            {"document_id": str(document.id)},
            {
                "$set": {
                    "document_id": str(document.id),
                    "title": document.title,
                    "metadata": parsed_json['document']['metadata'],  # Toutes les mÃ©tadonnÃ©es
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
            'message': 'JSON sauvegardÃ© avec succÃ¨s (SQL + MongoDB avec mÃ©tadonnÃ©es complÃ¨tes)'
        })

    except Exception as e:
        print(f"âŒ Erreur lors de la sauvegarde du JSON: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)


# â€”â€”â€” NOUVELLES VUES ANNOTATION EXPERT (copiÃ©es et adaptÃ©es de rawdocs) â€”â€”â€”â€”â€”â€”â€”â€”â€”â€”â€”â€”â€”â€”â€”â€”â€”â€”â€”â€”â€”â€”â€”â€”â€”â€”â€”â€”â€”â€”â€”â€”â€”

from django.contrib.auth.decorators import login_required
from datetime import datetime
from rawdocs.groq_annotation_system import GroqAnnotator


@expert_required
def expert_annotation_dashboard(request):
    """Dashboard annotation pour Expert - copie de rawdocs.views.annotation_dashboard"""
    # RÃ©cupÃ©rer tous les documents validÃ©s (prÃªts pour annotation)
    documents = RawDocument.objects.filter(is_validated=True).select_related('owner').order_by('-created_at')

    # Statistiques
    total_documents = documents.count()
    total_pages = sum(doc.total_pages for doc in documents)

    # Pages avec au moins une annotation
    annotated_pages = DocumentPage.objects.filter(
        document__in=documents,
        annotations__isnull=False
    ).distinct().count()

    # Documents en cours d'annotation (au moins une page annotÃ©e mais pas toutes)
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

    # Types d'annotations par dÃ©faut (mÃªmes que cÃ´tÃ© Annotateur) + types dÃ©jÃ  utilisÃ©s
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


# Ajouter ces fonctions utilitaires dans expert/views.py - Ã€ la fin du fichier

# ===== FONCTIONS UTILITAIRES POUR LA SYNCHRONISATION AUTOMATIQUE =====

# Variables globales pour la gestion des rÃ©gÃ©nÃ©rations
REGENERATION_CACHE = {}
CACHE_DURATION = 5  # secondes entre rÃ©gÃ©nÃ©rations pour un mÃªme document


def should_regenerate_summary(document_id):
    """VÃ©rifie si on doit rÃ©gÃ©nÃ©rer le rÃ©sumÃ© (Ã©vite les appels trop frÃ©quents)"""
    import time

    last_regeneration = REGENERATION_CACHE.get(document_id, 0)
    current_time = time.time()

    if current_time - last_regeneration > CACHE_DURATION:
        REGENERATION_CACHE[document_id] = current_time
        return True

    return False


def trigger_summary_regeneration(document, user):
    """Version de base pour rÃ©gÃ©nÃ©ration du rÃ©sumÃ©"""
    if not should_regenerate_summary(document.id):
        print(f"â° RÃ©gÃ©nÃ©ration rÃ©sumÃ© ignorÃ©e (trop rÃ©cente) pour doc {document.id}")
        return False

    try:
        from django.test import RequestFactory
        factory = RequestFactory()
        fake_request = factory.post(f'/expert/document/{document.id}/auto-regenerate-summary/')
        fake_request.user = user

        # Appeler la fonction de rÃ©gÃ©nÃ©ration
        result = auto_regenerate_summary_from_annotations(fake_request, document.id)

        if hasattr(result, 'status_code') and result.status_code == 200:
            print(f"[OK] Regeneration resume reussie pour doc {document.id}")
            return True
        else:
            print(f"âš ï¸ RÃ©gÃ©nÃ©ration rÃ©sumÃ© Ã©chouÃ©e pour doc {document.id}")
            return False

    except Exception as e:
        print(f"âš ï¸ Erreur dÃ©clenchement rÃ©gÃ©nÃ©ration rÃ©sumÃ©: {e}")
        return False


def trigger_summary_regeneration_safe(document, user, delay_seconds=1):  # Réduire de 5 à 1 seconde
    """Version sécurisée avec délai réduit"""
    import time
    import threading

    def delayed_regeneration():
        try:
            time.sleep(delay_seconds)
            trigger_summary_regeneration(document, user)
        except Exception as e:
            print(f"⚠️ Erreur régénération différée: {e}")

    thread = threading.Thread(target=delayed_regeneration)
    thread.daemon = True
    thread.start()

    print(f"🔄 Régénération programmée dans {delay_seconds}s pour doc {document.id}")

# ===== FONCTIONS POUR L'ANNOTATION AUTOMATIQUE PAR IA =====

def find_summary_differences(old_summary, new_summary):
    """Trouve les diffÃ©rences entre deux rÃ©sumÃ©s"""
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

            # Score basÃ© sur la prÃ©sence du texte exact ou similaire
            score = 0
            if entity_lower in text:
                score = 100
            else:
                # Recherche de mots-clÃ©s similaires
                words = entity_lower.split()
                for word in words:
                    if len(word) > 3 and word in text:
                        score += 20

            if score > best_score:
                best_score = score
                best_page = page

    # Si aucune page pertinente, retourner la premiÃ¨re page
    return best_page if best_score > 30 else pages.first()


def create_ai_annotation(page, entity_value, entity_type, user, confidence=0.8):
    """CrÃ©e une annotation automatiquement via IA"""
    try:
        # Chercher le texte dans la page
        text_content = getattr(page, 'cleaned_text', '') or getattr(page, 'text_content', '')
        if text_content:
            start_pos = text_content.lower().find(entity_value.lower())

            if start_pos == -1:
                # Si pas trouvÃ© exactement, chercher des mots-clÃ©s
                words = entity_value.split()
                for word in words:
                    if len(word) > 3:
                        start_pos = text_content.lower().find(word.lower())
                        if start_pos != -1:
                            entity_value = word  # Utiliser le mot trouvÃ©
                            break

            if start_pos != -1:
                end_pos = start_pos + len(entity_value)

                # CrÃ©er ou rÃ©cupÃ©rer le type d'annotation
                annotation_type, created = AnnotationType.objects.get_or_create(
                    name=entity_type,
                    defaults={
                        'display_name': entity_type.replace('_', ' ').title(),
                        'color': '#8b5cf6',  # Violet pour les annotations IA automatiques
                        'description': f"Auto-generated by AI from summary: {entity_type}"
                    }
                )

                # CrÃ©er l'annotation
                annotation = Annotation.objects.create(
                    page=page,
                    selected_text=entity_value,
                    annotation_type=annotation_type,
                    start_pos=start_pos,
                    end_pos=end_pos,
                    validation_status='expert_created',  # PrÃ©-validÃ©e car crÃ©Ã©e par expert
                    validated_by=user,
                    validated_at=timezone.now(),
                    created_by=user,
                    source='expert_ai_auto'
                )

                print(f"âœ… Annotation IA automatique crÃ©Ã©e: {entity_value} ({entity_type}) dans page {page.page_number}")
                return annotation

        return None

    except Exception as e:
        print(f"âš ï¸ Erreur crÃ©ation annotation automatique: {e}")
        return None


def await_ai_extract_and_annotate(document, old_summary, new_summary, allowed_keys, user, page_id=None):
    """
    Version amÃ©liorÃ©e qui limite les annotations Ã  la page spÃ©cifique
    et vÃ©rifie que le texte existe vraiment avant de crÃ©er l'annotation.
    """
    try:
        from rawdocs.groq_annotation_system import GroqAnnotator
        from django.utils import timezone
        from django.db.models import Q

        # Si page_id est fourni, on travaille uniquement sur cette page
        if page_id:
            target_page = DocumentPage.objects.filter(id=page_id).first()
            if not target_page:
                print(f"âš ï¸ Page {page_id} non trouvÃ©e")
                return {}
        else:
            target_page = None

        # ---------- helpers dates (inchangÃ©) ----------
        MONTHS_EN = {
            "january": "01","jan": "01","february": "02","feb": "02","march": "03","mar": "03",
            "april": "04","apr": "04","may": "05","june": "06","jun": "06","july": "07","jul": "07",
            "august": "08","aug": "08","september": "09","sep": "09","sept":"09",
            "october": "10","oct": "10","november": "11","nov": "11","december": "12","dec": "12"
        }
        MONTHS_FR = {
            "janvier":"01","fÃ©vrier":"02","fevrier":"02","mars":"03","avril":"04","mai":"05","juin":"06",
            "juillet":"07","aoÃ»t":"08","aout":"08","septembre":"09","octobre":"10","novembre":"11",
            "dÃ©cembre":"12","decembre":"12"
        }
        MONTHS_ALL = {**MONTHS_EN, **MONTHS_FR}

        def _norm(s: str) -> str:
            return re.sub(r"\s+", " ", (s or "").strip())

        def _canonical_date_key():
            # choisit une clÃ© Date existante si possible
            for k in ["Date", "Effective Date", "Publication Date", "Update Date", "Deadline", "Start Date"]:
                canon = _canonical_key(k, allowed_keys)
                if canon:
                    return canon
            return None

        DATE_KEY = _canonical_date_key()

        # dÃ©tecte toute forme de date (jour-mois-annÃ©e, mois-annÃ©e, numÃ©riquesâ€¦)
        DAY = r"(0?[1-9]|[12]\d|3[01])"
        YEAR = r"(?:19|20)\d{2}"
        MONTH_TXT = r"[A-Za-zÃ©Ã¨ÃªÃ«Ã Ã¢Ã®Ã¯Ã´Ã¶Ã¹Ã»Ã¼]{3,}"
        MONTH_NUM = r"(0?[1-9]|1[0-2])"
        # formes texte et numÃ©riques
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
            Ã€ partir d'une forme '5 June 2014' ou '5 Jun 2014' ou '5 juin 2014', gÃ©nÃ¨re :
            - '5 Jun 2014' / 'June 5, 2014' / '05/06/2014' / '2014-06-05'
            - si mois-annÃ©e seulement â†’ 'Jun 2014' / '06/2014' / '2014-06'
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
                    out.add(re.sub(r"(?i)\b([A-Za-zÃ©Ã¨ÃªÃ«Ã Ã¢Ã®Ã¯Ã´Ã¶Ã¹Ã»Ã¼]+)\s+(\d{{4}})\b", r"\1, \2", s))  # January, 2013
            # numÃ©riques â†’ gÃ©nÃ©rer quelques tournures inverses
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
            # force Date si le token ressemble Ã  une date
            if DATE_KEY and _is_date_token(value):
                return DATE_KEY
            return _canonical_key(raw_type, allowed_keys) or raw_type

        # ---------- extraction locale des entitÃ©s dans un rÃ©sumÃ© ----------
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

            # 2) fusionner avec heuristique gÃ©nÃ©rique et recanoniser
            for raw_k, vals in (by_text or {}).items():
                for v in (vals or []):
                    v = _norm(v)
                    k2 = _coerce_type_for_value(raw_k, v)
                    out.setdefault(k2, [])
                    if v and v not in out[k2]:
                        out[k2].append(v)

            # dÃ©dup
            for k, vals in list(out.items()):
                out[k] = list({v.lower(): v for v in vals}.values())
                if not out[k]:
                    del out[k]
            return out

        # ---------- diff entitÃ©s (ajouts / retraits) ----------
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
                print(f"âš ï¸ Deselect error {entity_type_canon}='{value}': {e}")
                return 0

        # ---------- pipeline principal ----------
                # ---------- extraction des changements ----------
                added_local, removed_local = _diff_entities(old_summary or "", new_summary or "")

                # Option IA : enrichissement (optionnel)
                ai_added, ai_removed = {}, {}
                if not added_local and not removed_local:
                    # Si pas de changements dÃ©tectÃ©s localement, demander Ã  l'IA
                    try:
                        diff_text = find_summary_differences(old_summary or "", new_summary or "")
                        if diff_text.strip():
                            ga = GroqAnnotator()
                            prompt = f"""
        Analyse les changements dans ce rÃ©sumÃ© et identifie les entitÃ©s Ã  annoter.
        IMPORTANT: Ne retourne QUE les entitÃ©s qui sont NOUVELLES ou MODIFIÃ‰ES.

        Types autorisÃ©s: {', '.join(allowed_keys)}

        Ancien rÃ©sumÃ©:
        {old_summary[:500]}

        Nouveau rÃ©sumÃ©:
        {new_summary[:500]}

        Changements dÃ©tectÃ©s:
        {diff_text}

        RÃ©ponds en JSON strict:
        {{
          "added": {{ "<Type>": ["valeur exacte dans le texte"] }},
          "removed": {{ "<Type>": ["valeur supprimÃ©e"] }}
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
                        print(f"âš ï¸ IA assist skipped: {e}")

                # Fusionner les rÃ©sultats
                added_all = _merge(added_local, ai_added)
                removed_all = _merge(removed_local, ai_removed)

                # 1) DÃ©sÃ©lection des valeurs retirÃ©es (inchangÃ©)
                for etype, values in (removed_all or {}).items():
                    for val in values:
                        if target_page:
                            # DÃ©sÃ©lectionner uniquement sur la page cible
                            _deselect_annotation_on_page(target_page, etype, val, user)
                        else:
                            _deselect_existing_annotation(document, etype, val, user)

                # 2) CrÃ©ation des annotations UNIQUEMENT sur la page spÃ©cifiÃ©e
                created_map: dict[str, list[str]] = {}

                for etype, values in (added_all or {}).items():
                    for val in values:
                        if target_page:
                            # CrÃ©er l'annotation UNIQUEMENT si le texte existe dans la page
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
                import traceback; print(f"[WARNING] Erreur annotation IA automatique: {e}"); print(traceback.format_exc())
                return {}

    except Exception as e:
        import traceback; print(f"[WARNING] Erreur annotation IA automatique: {e}"); print(traceback.format_exc())
        return {}


def create_annotation_if_text_exists(page, entity_value, entity_type, user, confidence=0.9):
    """
    CrÃ©e une annotation SEULEMENT si le texte existe vraiment dans la page.
    Utilise plusieurs stratÃ©gies de recherche pour Ãªtre plus robuste.
    """
    try:
        # Obtenir le texte de la page
        page_text = _get_page_text(page)
        if not page_text:
            print(f"âš ï¸ Page {page.page_number} sans texte")
            return False

        # StratÃ©gies de recherche dans l'ordre de prÃ©fÃ©rence
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

        # 4. Recherche par mots-clÃ©s significatifs
        if not search_results:
            keywords = extract_significant_keywords(entity_value)
            if keywords:
                keyword_result = find_by_keywords_in_page(keywords, page_text, entity_value)
                if keyword_result:
                    search_results.append(keyword_result)

        # Si aucun rÃ©sultat, on n'annote pas
        if not search_results:
            print(f"âš ï¸ Texte '{entity_value}' non trouvÃ© dans page {page.page_number}")
            return False

        # Utiliser le meilleur rÃ©sultat
        best_result = max(search_results, key=lambda x: x['confidence'])

        # CrÃ©er l'annotation uniquement si la confiance est suffisante
        if best_result['confidence'] < 0.5:
            print(f"âš ï¸ Confiance trop faible ({best_result['confidence']}) pour '{entity_value}'")
            return False

        # CrÃ©er ou rÃ©cupÃ©rer le type d'annotation
        annotation_type, _ = AnnotationType.objects.get_or_create(
            name=entity_type,
            defaults={
                'display_name': entity_type.replace('_', ' ').title(),
                'color': '#8b5cf6',
                'description': f"Auto-generated by AI from summary: {entity_type}"
            }
        )

        # VÃ©rifier qu'une annotation similaire n'existe pas dÃ©jÃ
        existing = Annotation.objects.filter(
            page=page,
            annotation_type=annotation_type,
            start_pos__lte=best_result['start'] + 5,
            start_pos__gte=best_result['start'] - 5,
            validation_status__in=['validated', 'expert_created', 'pending']
        ).first()

        if existing:
            print(f"â„¹ï¸ Annotation similaire dÃ©jÃ  existante pour '{entity_value}'")
            return False

        # CrÃ©er l'annotation
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

        print(f"âœ… Annotation crÃ©Ã©e: '{best_result['text']}' ({entity_type}) "
              f"page {page.page_number} pos [{best_result['start']}:{best_result['end']}]")
        return True

    except Exception as e:
        print(f"âŒ Erreur crÃ©ation annotation: {e}")
        return False


def find_real_position(original_text, normalized_text, norm_pos):
    """Trouve la position rÃ©elle dans le texte original Ã  partir de la position normalisÃ©e."""
    if norm_pos < 0:
        return -1

    # Compter les caractÃ¨res jusqu'Ã  norm_pos dans le texte normalisÃ©
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
    """Extrait les mots-clÃ©s significatifs d'un texte."""
    # Mots vides Ã  ignorer
    stopwords = {'le', 'la', 'les', 'de', 'du', 'des', 'un', 'une', 'et', 'ou',
                 'Ã ', 'au', 'aux', 'pour', 'par', 'sur', 'dans', 'avec', 'sans',
                 'the', 'a', 'an', 'and', 'or', 'for', 'by', 'on', 'in', 'with'}

    words = re.findall(r'\b\w+\b', text.lower())
    keywords = [w for w in words if len(w) >= min_length and w not in stopwords]

    # Prioriser les mots commenÃ§ant par une majuscule (noms propres)
    capitalized = re.findall(r'\b[A-Z]\w+\b', text)

    return capitalized + keywords


def find_by_keywords_in_page(keywords, page_text, original_value):
    """Cherche une sÃ©quence de mots-clÃ©s dans le texte."""
    if not keywords:
        return None

    page_lower = page_text.lower()
    best_match = None
    best_score = 0

    # Chercher chaque mot-clÃ©
    for keyword in keywords[:3]:  # Limiter aux 3 premiers mots-clÃ©s
        keyword_lower = keyword.lower()
        pos = page_lower.find(keyword_lower)

        if pos >= 0:
            # Ã‰tendre la recherche autour du mot-clÃ©
            context_start = max(0, pos - 50)
            context_end = min(len(page_text), pos + len(keyword) + 50)
            context = page_text[context_start:context_end]

            # Calculer un score basÃ© sur le nombre de mots-clÃ©s trouvÃ©s
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
    """Recherche spÃ©cialisÃ©e pour les dates avec formats multiples."""
    # Utiliser la fonction existante mais adaptÃ©e pour retourner le bon format
    start, end, text = find_date_span_in_text(page_text, date_value)

    if start is not None:
        return {
            'start': start,
            'end': end,
            'text': text,
            'confidence': 0.9
        }

    # Essayer d'autres formats de date
    # ... (logique additionnelle si nÃ©cessaire)

    return None


def _deselect_annotation_on_page(page, entity_type_canon, value, user):
    """DÃ©sÃ©lectionne les annotations uniquement sur une page spÃ©cifique."""
    try:
        from django.db.models import Q

        qs_type = AnnotationType.objects.filter(
            Q(name__iexact=entity_type_canon) | Q(display_name__iexact=entity_type_canon)
        )

        if not qs_type.exists():
            return 0

        qs = Annotation.objects.filter(
            page=page,  # Limiter Ã  la page spÃ©cifique
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
            print(f"â„¹ï¸ {count} annotation(s) dÃ©sÃ©lectionnÃ©e(s) pour '{value}' sur page {page.page_number}")

        return count

    except Exception as e:
        print(f"âš ï¸ Erreur dÃ©sÃ©lection: {e}")
        return 0
def enhance_summary_with_ai(document, entities, basic_summary):
    """
    Utilise l'IA pour enrichir le rÃ©sumÃ© gÃ©nÃ©rÃ© automatiquement
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
AmÃ©liore ce rÃ©sumÃ© pharmaceutique en ajoutant du contexte et des dÃ©tails pertinents basÃ©s sur les entitÃ©s extraites.

Document: {document.title}
Type: {getattr(document, 'doc_type', 'Pharmaceutique')}

RÃ©sumÃ© de base:
{basic_summary}

EntitÃ©s identifiÃ©es:
{entities_text}

Instructions:
1. Garde toutes les informations du rÃ©sumÃ© original
2. Ajoute des connexions logiques entre les entitÃ©s
3. Enrichis avec du contexte pharmaceutique pertinent
4. Maintiens un ton professionnel et prÃ©cis
5. Maximum 300 mots

RÃ©sumÃ© enrichi:"""

        response = groq_annotator.complete_text(prompt, max_tokens=800)

        if response and len(response.strip()) > len(basic_summary):
            return response.strip()

        return basic_summary

    except Exception as e:
        print(f"âš ï¸ Erreur enrichissement rÃ©sumÃ©: {e}")
        return basic_summary


# ===== FONCTION DE NETTOYAGE POUR LA MAINTENANCE =====

def cleanup_regeneration_cache():
    """Nettoie le cache des rÃ©gÃ©nÃ©rations (Ã  appeler pÃ©riodiquement)"""
    import time
    current_time = time.time()

    # Supprimer les entrÃ©es anciennes
    expired_keys = [
        doc_id for doc_id, timestamp in REGENERATION_CACHE.items()
        if current_time - timestamp > CACHE_DURATION * 2
    ]

    for key in expired_keys:
        del REGENERATION_CACHE[key]

    if expired_keys:
        print(f"[CLEANUP] Cache regeneration nettoye: {len(expired_keys)} entrÃ©es supprimÃ©es")


# ===== DÃ‰CORATEUR POUR EVITER LES APPELS TROP FREQUENTS =====

def with_regeneration_throttle(delay_seconds=5):
    """DÃ©corateur pour limiter la frÃ©quence des rÃ©gÃ©nÃ©rations"""

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
                print(f"â° Fonction {func.__name__} throttlÃ©e pour doc {document.id}")
                return False

        return wrapper

    return decorator


# Usage avec le dÃ©corateur:
# @with_regeneration_throttle(delay_seconds=3)
# def my_regeneration_function(document, user):
#     # votre code ici
# expert/views.py

@expert_required
@csrf_exempt
def expert_ai_annotate_page_groq(request, page_id):
    """
    Version corrigÃ©e qui gÃ¨re les erreurs API et le nouveau format de retour GROQ
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

        # VÃ©rification de l'API GROQ
        try:
            from rawdocs.groq_annotation_system import GroqAnnotator
            groq_annotator = GroqAnnotator()

            # VÃ©rifier si GROQ est disponible
            if not groq_annotator.enabled:
                return JsonResponse({
                    'success': False,
                    'error': "API GROQ non configurÃ©e ou clÃ© invalide (erreur 401)",
                    'message': "Veuillez vÃ©rifier votre clÃ© API GROQ dans les paramÃ¨tres.",
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

            # RÃ©cupÃ©rer le schÃ©ma depuis l'attribut last_schema
            annotation_schema = getattr(groq_annotator, 'last_schema', [])

            if not isinstance(raw_annotations, list):
                raise Exception(f"Format de retour GROQ inattendu: {type(raw_annotations)}")

            print(f"âœ… GROQ retour: {len(raw_annotations)} annotations, {len(annotation_schema)} types")

        except Exception as e:
            error_msg = str(e)
            print(f"âŒ Erreur appel GROQ: {error_msg}")

            if "401" in error_msg or "invalide" in error_msg:
                return JsonResponse({
                    'success': False,
                    'error': "ClÃ© API GROQ invalide ou expirÃ©e",
                    'message': "Veuillez renouveler votre clÃ© API GROQ.",
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
                'message': "GROQ connectÃ© mais aucune entitÃ© dÃ©tectÃ©e.",
                'page_summary': getattr(page, 'annotations_summary', None)
            })

        # CrÃ©ation des annotations
        saved = []
        for item in entities:
            try:
                etype = (item.get('type') or '').strip()
                etext = (item.get('text') or '').strip()

                if not etype or not etext:
                    continue

                # CrÃ©er le type d'annotation
                annotation_type, created = AnnotationType.objects.get_or_create(
                    name=etype,
                    defaults={
                        'display_name': etype.replace('_', ' ').title(),
                        'color': '#3b82f6',
                        'description': f"GROQ AI type: {etype}"
                    }
                )

                # Positions sÃ©curisÃ©es
                sp = max(0, int(item.get('start_pos', 0)))
                ep = max(sp + 1, min(int(item.get('end_pos', sp + len(etext))), len(page_text)))

                # CrÃ©er l'annotation
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
                print(f"âš ï¸ Erreur crÃ©ation annotation '{etext}': {e}")
                continue

        # Mise Ã  jour JSON
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
            print(f"âš ï¸ Erreur mise Ã  jour JSON: {e}")

        return JsonResponse({
            'success': True,
            'annotations': saved,
            'message': f"{len(saved)} annotation(s) crÃ©Ã©e(s) par GROQ",
            'page_summary': getattr(page, 'annotations_summary', ''),
            'groq_status': 'success'
        })

    except Exception as e:
        print(f"âŒ Erreur critique: {e}")
        return JsonResponse({
            'success': False,
            'error': f"Erreur systÃ¨me: {str(e)}",
            'fallback_available': True
        }, status=500)

@expert_required
@csrf_exempt
def expert_save_manual_annotation(request):
    """
    CrÃ©ation d'une annotation manuelle (prÃ©-validÃ©e) + MAJ JSON page/doc + rÃ©gÃ©nÃ©ration automatique
    du rÃ©sumÃ© de la page + retour du nouveau rÃ©sumÃ©.
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
            source='expert'
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

            # rÃ©sumÃ© global (asynchrone / throttlÃ©)
            # Resume global (IMMEDIATE pour action manuelle expert - ignore le throttling)
            try:
                REGENERATION_CACHE.pop(page.document.id, None)
                trigger_summary_regeneration_safe(page.document, request.user, 0)  # Immediate for manual expert action
            except Exception as e:
                print(f"âš ï¸ Erreur dÃ©clenchement rÃ©gÃ©nÃ©ration document (manual): {e}")

        except Exception as e:
            print(f"âŒ Erreur MAJ JSON/summary (manual): {e}")

        return JsonResponse({
            'success': True,
            'annotation_id': annotation.id,
            'message': 'Annotation sauvegardÃ©e avec succÃ¨s et JSON mis Ã  jour',
            'page_summary': page.annotations_summary,
            'auto_summary_triggered': True
        })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@expert_required
def expert_get_page_annotations(request, page_id):
    """Récupération des annotations d'une page pour Expert - version robuste"""
    try:
        # CORRECTION: Ne pas utiliser get_object_or_404 qui cause une exception
        # Utiliser get() avec gestion manuelle du DoesNotExist
        try:
            page = DocumentPage.objects.get(id=page_id)
        except DocumentPage.DoesNotExist:
            print(f"⚠️ Page {page_id} introuvable")
            return JsonResponse({
                'success': False,
                'error': f'Page {page_id} not found',
                'annotations': []  # Retourner une liste vide pour éviter les erreurs frontend
            }, status=404)

        annotations = page.annotations.filter(
            validation_status__in=['pending', 'validated', 'expert_created', 'rejected']
        ).select_related('annotation_type', 'validated_by').order_by('start_pos')

        annotations_data = []
        for annotation in annotations:
            try:
                # Gestion robuste des relations qui peuvent être None
                annotation_type = annotation.annotation_type
                if not annotation_type:
                    print(f"⚠️ Annotation {annotation.id} sans annotation_type")
                    continue

                validated_by = annotation.validated_by
                validated_by_username = validated_by.username if validated_by else None

                # Gestion robuste des dates
                created_at = None
                if annotation.created_at:
                    try:
                        created_at = annotation.created_at.isoformat()
                    except Exception as e:
                        print(f"⚠️ Erreur sérialisation created_at pour annotation {annotation.id}: {e}")

                validated_at = None
                if annotation.validated_at:
                    try:
                        validated_at = annotation.validated_at.isoformat()
                    except Exception as e:
                        print(f"⚠️ Erreur sérialisation validated_at pour annotation {annotation.id}: {e}")

                annotations_data.append({
                    'id': annotation.id,
                    'selected_text': annotation.selected_text or '',
                    'type_display': annotation_type.display_name or annotation_type.name or 'Unknown',
                    'type': annotation_type.name or 'unknown',
                    'color': getattr(annotation_type, 'color', '#666666'),
                    'start_pos': annotation.start_pos or 0,
                    'end_pos': annotation.end_pos or 0,
                    'validation_status': annotation.validation_status or 'pending',
                    'created_at': created_at,
                    'validated_at': validated_at,
                    'validated_by': validated_by_username,
                })

            except Exception as e:
                print(f"⚠️ Erreur traitement annotation {annotation.id}: {e}")
                # Continuer avec les autres annotations au lieu de faire planter la requête
                continue

        return JsonResponse({
            'success': True,
            'annotations': annotations_data,
            'total_count': len(annotations_data)
        })

    except Exception as e:
        print(f"❌ Erreur critique expert_get_page_annotations page {page_id}: {e}")
        return JsonResponse({
            'success': False,
            'error': f'Erreur serveur: {str(e)}',
            'annotations': []  # Toujours retourner une structure cohérente
        }, status=500)

@expert_required
@csrf_exempt
def expert_delete_annotation(request, annotation_id):
    """
    Suppression d'annotation + MAJ JSON page/doc + rÃ©gÃ©nÃ©ration rÃ©sumÃ© page + retour rÃ©sumÃ©.
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
                REGENERATION_CACHE.pop(document.id, None)
                trigger_summary_regeneration_safe(document, request.user, 0)  # Immediate for manual expert action
            except Exception as e:
                print(f"âš ï¸ Erreur dÃ©clenchement rÃ©gÃ©nÃ©ration aprÃ¨s suppression: {e}")

        except Exception as e:
            print(f"âŒ Erreur MAJ JSON/summary (delete): {e}")
            new_page_summary = None

        return JsonResponse({'success': True, 'message': 'Annotation supprimÃ©e', 'page_summary': new_page_summary})

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
            'message': f'{validated_count} annotations validÃ©es'
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

        # (optionnel) mettre aussi Ã  jour le JSON global du document pour rester cohÃ©rent
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
    """GÃ©nÃ©ration du JSON et rÃ©sumÃ© global pour un document - Expert - copie de rawdocs.views.generate_document_annotation_summary"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        document = get_object_or_404(RawDocument, id=doc_id, is_validated=True)

        # RÃ©cupÃ©rer toutes les annotations du document
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

        # RÃ©sumÃ© Ã  partir des seules entitÃ©s/valeurs
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
            'message': f'JSON et rÃ©sumÃ© globaux gÃ©nÃ©rÃ©s pour le document'
        })
    except Exception as e:
        print(f"âŒ Erreur gÃ©nÃ©ration rÃ©sumÃ© document {doc_id}: {e}")
        return JsonResponse({'error': f'Erreur lors de la gÃ©nÃ©ration: {str(e)}'}, status=500)


@expert_required
def expert_view_page_annotation_json(request, page_id):
    """Visualisation du JSON et rÃ©sumÃ© d'une page - Expert avec navigation"""
    try:
        page = get_object_or_404(DocumentPage, id=page_id)
        document = page.document

        # Si pas encore gÃ©nÃ©rÃ©, le gÃ©nÃ©rer
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
    """Visualisation et Ã©dition du JSON et rÃ©sumÃ© global d'un document - Expert avec analyse rÃ©glementaire"""
    try:
        document = get_object_or_404(RawDocument, id=doc_id, is_validated=True)

        if request.method == 'POST' and request.headers.get('x-requested-with') == 'XMLHttpRequest':
            # Mode Ã©dition AJAX
            try:
                data = json.loads(request.body)
                action = data.get('action', '')

                if action == 'save_summary':
                    # DÃ©lÃ©guer Ã  la fonction existante
                    return save_summary_changes(request, doc_id)
                elif action == 'save_json':
                    # DÃ©lÃ©guer Ã  la fonction existante
                    return save_document_json(request, doc_id)
                else:
                    return JsonResponse({'error': 'Action non reconnue'}, status=400)
            except Exception as e:
                return JsonResponse({'error': str(e)}, status=500)

        # Mode affichage GET
        # Si pas encore gÃ©nÃ©rÃ©, le gÃ©nÃ©rer
        if not hasattr(document, 'global_annotations_json') or not document.global_annotations_json:
            # DÃ©clencher la gÃ©nÃ©ration
            from django.test import RequestFactory
            factory = RequestFactory()
            fake_request = factory.post(f'/expert/annotation/document/{doc_id}/generate-summary/')
            fake_request.user = request.user
            expert_generate_document_annotation_summary(fake_request, doc_id)
            document.refresh_from_db()

        # Enrichir le contexte pour l'Ã©dition
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
            'can_edit': True,  # Activer l'interface d'Ã©dition
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


# Fonctions pour la gestion des rÃ©sumÃ©s de page
# @expert_required
# @csrf_exempt
# def save_page_summary(request, page_id):
#     """Sauvegarde du rÃ©sumÃ© d'une page"""
#     if request.method != 'POST':
#         return JsonResponse({'error': 'POST required'}, status=405)
#     try:
#         page = get_object_or_404(DocumentPage, id=page_id)
#         data = json.loads(request.body)
#         summary_text = data.get('summary_text', '').strip()
#
#         page.page_summary = summary_text
#         page.summary_validated = False  # RÃ©initialiser la validation
#         page.summary_validated_at = None
#         page.summary_validated_by = None
#         page.save(update_fields=['page_summary', 'summary_validated', 'summary_validated_at', 'summary_validated_by'])
#
#         return JsonResponse({'success': True, 'message': 'RÃ©sumÃ© sauvegardÃ©'})
#     except Exception as e:
#         return JsonResponse({'error': str(e)}, status=500)

# Ajouter ces vues dans expert/views.py

# Ajouter ces vues dans expert/views.py

@login_required
@user_passes_test(is_expert)
@csrf_exempt
def save_page_summary(request, page_id):
    """Version corrigée avec gestion d'erreurs robuste"""
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

        old_summary = page.annotations_summary or ""

        print(f"\n{'=' * 60}")
        print(f"📝 SAVE_PAGE_SUMMARY - Page {page.page_number}")
        print(f"   Auto-annotate: {auto_annotate}, Auto-delete: {auto_delete}")
        print(f"{'=' * 60}\n")

        # Initialiser sync_result avec structure complète
        sync_result = {
            'annotations_created': 0,
            'annotations_deleted': 0,
            'annotations_rejected': 0,
            'details': {},
            'errors': []  # ✅ Toujours initialiser
        }

        # SYNCHRONISATION
        if auto_annotate and old_summary != new_summary:
            try:
                result = synchronize_page_annotations_with_summary(
                    page=page,
                    old_summary=old_summary,
                    new_summary=new_summary,
                    user=request.user,
                    auto_delete=auto_delete
                )

                # ✅ Fusionner les résultats de manière sûre
                if isinstance(result, dict):
                    sync_result['annotations_created'] = result.get('annotations_created', 0)
                    sync_result['annotations_deleted'] = result.get('annotations_deleted', 0)
                    sync_result['annotations_rejected'] = result.get('annotations_rejected', 0)
                    sync_result['details'] = result.get('details', {})
                    # ✅ Ajouter les erreurs s'il y en a
                    if 'errors' in result:
                        sync_result['errors'].extend(result['errors'])

                print(
                    f"✅ Synchronisation OK: +{sync_result['annotations_created']} -{sync_result['annotations_deleted']}")

            except Exception as e:
                error_msg = f"Erreur synchronisation: {str(e)}"
                print(f"❌ {error_msg}")
                import traceback
                traceback.print_exc()
                sync_result['errors'].append(error_msg)

        # Sauvegarder le résumé
        page.annotations_summary = new_summary
        page.annotations_summary_generated_at = timezone.now()
        page.save(update_fields=['annotations_summary', 'annotations_summary_generated_at'])

        # Reconstruire le JSON
        try:
            build_page_summary_and_json(page, request.user)
        except Exception as e:
            error_msg = f"Erreur JSON: {str(e)}"
            print(f"❌ {error_msg}")
            sync_result['errors'].append(error_msg)

        # Message
        message = 'Résumé sauvegardé'
        if sync_result['annotations_created'] > 0 or sync_result['annotations_deleted'] > 0:
            message = f"Synchronisation : +{sync_result['annotations_created']} -{sync_result['annotations_deleted']}"

        # ✅ Vérification sûre des erreurs
        if sync_result.get('errors'):  # Utiliser .get() au lieu d'accès direct
            message += f" ({len(sync_result['errors'])} erreur(s))"

        return JsonResponse({
            'success': True,
            'message': message,
            'summary': new_summary,
            'sync_result': sync_result
        })

    except Exception as e:
        error_msg = f"Erreur save_page_summary: {str(e)}"
        print(f"❌ {error_msg}")
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'error': error_msg
        }, status=500)
# helpers -------------------------------------------------------------

from typing import Dict, List, Iterable

def _normalize(s: str) -> str:
    return (s or "").strip().strip('.,;:Â·').lower()

def _normalize_entities(entities: Dict[str, Iterable[str]]) -> Dict[str, List[str]]:
    """Nettoie, dÃ©duplique et retire les valeurs vides."""
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
    Enrichit/valide les entitÃ©s dÃ©tectÃ©es.
    - Si un GroqAnnotator est fourni et expose une mÃ©thode utile, on lâ€™utilise.
    - Sinon, fallback : normalisation + dÃ©doublonnage + filtrage trivial par prÃ©sence dans le texte.
    Retourne le mÃªme schÃ©ma {entity_type: [values...]}.
    """
    # Fallback immÃ©diat si rien Ã  faire
    if not entities:
        return {}

    # Tentatives dâ€™utilisation de lâ€™annotateur si prÃ©sent
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

    # Fallback simple : on garde les valeurs prÃ©sentes dans le texte (quand possible)
    text_lc = (page_text or "").lower()
    filtered: Dict[str, List[str]] = {}
    for etype, vals in _normalize_entities(entities).items():
        keep: List[str] = []
        for v in vals:
            # trÃ¨s permissif : gardÃ© si valeur ou version normalisÃ©e est dans le texte
            vn = _normalize(v)
            if not text_lc or (vn and vn in text_lc) or (v and v.lower() in text_lc):
                keep.append(v)
        if keep:
            filtered[etype] = keep
    return filtered


# 2) CrÃ©ation dâ€™annotation -------------------------------------------

def create_page_annotation_from_entity(
    page,
    entity_type: str,
    entity_value: str,
    user,
):
    """
    CrÃ©e lâ€™annotation (si elle nâ€™existe pas dÃ©jÃ , insensible Ã  la casse).
    Retourne lâ€™instance crÃ©Ã©e, ou None si un doublon existait dÃ©jÃ .

    HypothÃ¨ses Django courantes :
    - ModÃ¨le PageAnnotation avec champs : page, entity_type, entity_value, created_by
    - Adapte les noms de champs au besoin.
    """
    # Normalisation pour Ã©viter les doublons
    norm_value = _normalize(entity_value)

    # --- Variante modÃ¨le Django (recommandÃ©e) ---
    try:
        from rawdocs.models import PageAnnotation  # adapte le chemin si besoin

        # Existence (insensible Ã  la casse)
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
        # --- Fallback trÃ¨s simple si tu nâ€™utilises pas Django ---
        # On essaie d'utiliser un conteneur en mÃ©moire sur l'objet page.
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
    Valide et filtre les rÃ©sultats de l'analyse IA pour Ã©viter les erreurs.
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

            # VÃ©rifier que l'entitÃ© n'existe pas dÃ©jÃ
            existing_values = existing_entities.get(entity_type, [])
            if value.lower() not in [v.lower() for v in existing_values]:
                # VÃ©rifier prÃ©sence dans le texte (pour les entitÃ©s non-date)
                if 'date' not in entity_type.lower() or value.lower() in page_text_lower or confidence > 0.9:
                    validated_values.append(value_data)

        if validated_values:
            validated['entities_to_add'][entity_type] = validated_values

    # Valider les suppressions
    for entity_type, values in analysis.get('entities_to_remove', {}).items():
        if entity_type in existing_entities:
            # Ne supprimer que les entitÃ©s qui existent rÃ©ellement
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

            # VÃ©rifier que l'ancienne valeur existe
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
        print(f"âš ï¸ Erreur analyse fallback: {e}")
        return {
            'entities_to_add': {},
            'entities_to_remove': {},
            'entities_to_modify': {},
            'removal_confidence': 0.5,
            'analysis_summary': f'Erreur analyse: {str(e)}'
        }


def analyze_summary_changes_with_ai(page, old_summary, new_summary, existing_entities, page_text):
    """
    Utilise l'IA pour analyser intelligemment les changements dans le rÃ©sumÃ©
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

        prompt = f"""Tu es un expert en analyse documentaire pharmaceutique. Analyse les changements dans le rÃ©sumÃ© d'une page en tenant compte du contexte existant.

CONTEXTE:
- Document: {context_data['document_title']}
- Page: {context_data['page_number']}

ENTITÃ‰S EXISTANTES (JSON actuel):
{json.dumps(existing_entities, ensure_ascii=False, indent=2)}

ANCIEN RÃ‰SUMÃ‰:
{context_data['old_summary']}

NOUVEAU RÃ‰SUMÃ‰:
{context_data['new_summary']}

EXTRAIT DU TEXTE DE PAGE (pour rÃ©fÃ©rence):
{context_data['page_text_preview']}

INSTRUCTIONS:
1. Identifie les entitÃ©s qui doivent Ãªtre AJOUTÃ‰ES (nouvelles dans le rÃ©sumÃ©)
2. Identifie les entitÃ©s qui doivent Ãªtre SUPPRIMÃ‰ES (retirÃ©es du rÃ©sumÃ©)
3. Identifie les entitÃ©s MODIFIÃ‰ES (changement de valeur)
4. Pour chaque entitÃ©, Ã©value si elle existe rÃ©ellement dans le texte de la page
5. Donne un niveau de confiance (0.0-1.0) pour chaque action

TYPES D'ENTITÃ‰S PHARMACEUTIQUES Ã€ CONSIDÃ‰RER:
- Product/Invented Name
- Strength/Dosage  
- Pharmaceutical Form
- Route Of Administration
- Date/Deadline
- Ma Number/Authorization
- Manufacturing Site
- Active Ingredient

RÃ©ponds UNIQUEMENT en JSON strict:
{{
  "entities_to_add": {{
    "<EntityType>": [
      {{
        "value": "texte exact Ã  annoter",
        "confidence": 0.9,
        "context": "contexte oÃ¹ apparaÃ®t l'entitÃ©",
        "reasoning": "pourquoi cette entitÃ© doit Ãªtre ajoutÃ©e"
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
  "analysis_summary": "RÃ©sumÃ© de l'analyse des changements"
}}"""

        # Appel Ã  l'IA
        raw_response = groq_annotator.complete_text(
            prompt=prompt,
            max_tokens=1500,
            temperature=0.1
        )

        if raw_response:
            try:
                # Nettoyer la rÃ©ponse
                clean_response = raw_response.strip()
                if clean_response.startswith('```'):
                    clean_response = clean_response.split('\n', 1)[1]
                if clean_response.endswith('```'):
                    clean_response = clean_response.rsplit('\n', 1)[0]

                analysis = json.loads(clean_response)

                # Validation et nettoyage des rÃ©sultats
                validated_analysis = validate_ai_analysis(analysis, existing_entities, page_text)

                return validated_analysis

            except json.JSONDecodeError as e:
                print(f"âš ï¸ Erreur parsing rÃ©ponse IA: {e}")
                return _fallback_analysis(old_summary, new_summary, existing_entities)
        else:
            return _fallback_analysis(old_summary, new_summary, existing_entities)

    except Exception as e:
        print(f"âš ï¸ Erreur analyse IA: {e}")
        return _fallback_analysis(old_summary, new_summary, existing_entities)


def create_page_annotation_with_smart_positioning(page, entity_type, entity_value, user, confidence=0.8, context='',
                                                  existing_json=None):
    """
    CrÃ©e une annotation avec positionnement intelligent basÃ© sur le contexte existant
    et recherche optimisÃ©e dans le texte.
    """
    try:
        page_text = _get_page_text(page)
        if not page_text:
            print(f"âš ï¸ Pas de texte disponible pour la page {page.page_number}")
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
            print(f"âš ï¸ EntitÃ© '{entity_value}' non trouvÃ©e dans le texte de la page {page.page_number}")
            return False

        # CrÃ©er le type d'annotation
        annotation_type, _ = AnnotationType.objects.get_or_create(
            name=entity_type,
            defaults={
                'display_name': entity_type.replace('_', ' ').title(),
                'color': '#8b5cf6',
                'description': f"Smart annotation: {entity_type}"
            }
        )

        # VÃ©rifier les doublons
        existing = Annotation.objects.filter(
            page=page,
            annotation_type=annotation_type,
            start_pos__lte=start_pos + 10,
            start_pos__gte=start_pos - 10,
            validation_status__in=['validated', 'expert_created', 'pending']
        ).first()

        if existing:
            print(f"â„¹ï¸ Annotation similaire dÃ©jÃ  existante: {existing.selected_text}")
            return False

        # CrÃ©er l'annotation
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

        print(f"âœ… Annotation intelligente crÃ©Ã©e: '{actual_text}' ({entity_type}) page {page.page_number}")
        return True

    except Exception as e:
        print(f"âš ï¸ Erreur crÃ©ation annotation intelligente: {e}")
        return False


def find_entity_in_text_enhanced(entity_text, page_text, entity_type='', existing_annotations=None, context_hint=''):
    """
    Version amÃ©liorÃ©e de la recherche d'entitÃ© qui utilise le contexte du JSON existant.
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
    Utilise le contexte des annotations existantes pour amÃ©liorer la recherche.
    """
    try:
        existing_entities = existing_annotations.get('entities', {})
        page_text_lower = page_text.lower()
        entity_lower = entity_text.lower()

        # Chercher des entitÃ©s similaires ou liÃ©es
        for entity_type, values in existing_entities.items():
            for value in values:
                value_pos = page_text_lower.find(value.lower())
                if value_pos != -1:
                    # Chercher l'entitÃ© cible dans un rayon autour de cette annotation
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
        print(f"âš ï¸ Erreur recherche avec contexte annotations: {e}")
        return -1, -1, entity_text


def _find_entity_using_context_hint(entity_text, page_text, context_hint):
    """
    Utilise l'indice de contexte fourni par l'IA pour localiser l'entitÃ©.
    """
    try:
        page_text_lower = page_text.lower()
        context_lower = context_hint.lower()
        entity_lower = entity_text.lower()

        # Chercher le contexte d'abord
        context_pos = page_text_lower.find(context_lower)
        if context_pos != -1:
            # Chercher l'entitÃ© prÃ¨s du contexte
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
        print(f"âš ï¸ Erreur recherche avec contexte hint: {e}")
        return -1, -1, entity_text


def remove_page_annotations_for_entity_enhanced(page, entity_type, entity_value, user, existing_json=None,
                                                confidence_threshold=0.8, hard_delete=False):
    """
    Version amÃ©liorÃ©e de suppression qui prend en compte le contexte du JSON existant.
    """
    try:
        # Utiliser la fonction existante mais avec une validation supplÃ©mentaire
        result = remove_page_annotations_for_entity(
            page=page,
            entity_type=entity_type,
            entity_value=entity_value,
            user=user,
            hard_delete=hard_delete
        )

        # Validation supplÃ©mentaire basÃ©e sur le JSON existant
        if existing_json and confidence_threshold > 0.7:
            existing_entities = existing_json.get('entities', {})
            if entity_type in existing_entities:
                existing_values = [v.lower() for v in existing_entities[entity_type]]
                if entity_value.lower() not in existing_values:
                    print(f"â„¹ï¸ EntitÃ© '{entity_value}' pas dans le JSON existant, suppression annulÃ©e")
                    return {'count': 0, 'message': 'EntitÃ© non trouvÃ©e dans le JSON existant'}

        return result

    except Exception as e:
        print(f"âš ï¸ Erreur suppression annotations amÃ©liorÃ©e: {e}")
        return {'count': 0, 'error': str(e)}


def synchronize_page_annotations_with_summary(page, old_summary, new_summary, user, auto_delete=True):
    """
    VERSION DEBUG ULTRA-SIMPLE
    """
    sync_result = {
        'annotations_created': 0,
        'annotations_deleted': 0,
        'annotations_rejected': 0,
        'details': {'added': {}, 'removed': {}},
        'errors': []
    }

    try:
        print(f"\n{'=' * 80}")
        print(f"DEBUG SYNCHRONISATION - Page {page.page_number}")
        print(f"{'=' * 80}")
        print(f"\n📄 ANCIEN RÉSUMÉ:")
        print(old_summary[:500])
        print(f"\n📄 NOUVEAU RÉSUMÉ:")
        print(new_summary[:500])

        # Extraction manuelle simple pour les dates
        import re

        def extract_dates_simple(text):
            """Extraction ultra-simple des dates"""
            dates = []
            # Chercher format "mai 2012", "May 2012", etc.
            for match in re.finditer(
                    r'\b(janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre|january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+(\d{4})\b',
                    text, re.IGNORECASE):
                dates.append(match.group(0))
            return dates

        old_dates = extract_dates_simple(old_summary or "")
        new_dates = extract_dates_simple(new_summary or "")

        print(f"\n📅 DATES DÉTECTÉES:")
        print(f"   Anciennes: {old_dates}")
        print(f"   Nouvelles: {new_dates}")

        # Normaliser pour comparaison
        old_dates_lower = [d.lower().strip() for d in old_dates]
        new_dates_lower = [d.lower().strip() for d in new_dates]

        # Trouver suppressions et ajouts
        removed_dates = [d for d in old_dates if d.lower().strip() not in new_dates_lower]
        added_dates = [d for d in new_dates if d.lower().strip() not in old_dates_lower]

        print(f"\n🔄 CHANGEMENTS:")
        print(f"   ❌ À supprimer: {removed_dates}")
        print(f"   ✅ À ajouter: {added_dates}")

        # TRAITER LES SUPPRESSIONS
        if removed_dates and auto_delete:
            for date_value in removed_dates:
                print(f"\n{'—' * 40}")
                print(f"❌ SUPPRESSION DE: '{date_value}'")

                # Chercher toutes les annotations de type Date sur cette page
                all_page_annotations = Annotation.objects.filter(
                    page=page,
                    validation_status__in=['pending', 'validated', 'expert_created']
                )

                print(f"   📊 {all_page_annotations.count()} annotations totales sur la page")

                # Filtrer par type Date
                date_annotations = []
                for ann in all_page_annotations:
                    type_name = ann.annotation_type.name.lower()
                    if 'date' in type_name or 'deadline' in type_name:
                        date_annotations.append(ann)

                print(f"   📅 {len(date_annotations)} annotations de type Date")

                # Chercher correspondance
                matched = []
                for ann in date_annotations:
                    ann_text = ann.selected_text.strip()
                    print(f"      Comparaison: '{date_value}' vs '{ann_text}'")

                    # Normaliser les deux
                    norm1 = normalize_date_format(date_value)
                    norm2 = normalize_date_format(ann_text)
                    print(f"         Normalisé: '{norm1}' vs '{norm2}'")

                    # Utiliser la fonction are_dates_equivalent pour gérer FR/EN
                    if are_dates_equivalent(date_value, ann_text):
                        matched.append(ann)
                        print(f"         ✅ MATCH TROUVÉ (dates équivalentes)!")
                    else:
                        print(f"         ❌ Dates différentes: '{date_value}' != '{ann_text}'")

                if matched:
                    print(f"   ✅ {len(matched)} annotation(s) correspondante(s) trouvée(s)")
                    for ann in matched:
                        ann.validation_status = 'rejected'
                        ann.validated_by = user
                        ann.validated_at = timezone.now()
                        ann.save()
                        sync_result['annotations_rejected'] += 1
                        print(f"      ⛔ Annotation {ann.id} rejetée: '{ann.selected_text}'")
                else:
                    print(f"   ⚠️ AUCUNE annotation correspondante trouvée!")
                    sync_result['errors'].append(f"Annotation non trouvée pour: {date_value}")

        # TRAITER LES AJOUTS
        if added_dates:
            print(f"\n{'—' * 40}")
            print(f"✅ AJOUTS:")
            for date_value in added_dates:
                print(f"   Nouvelle date à annoter: '{date_value}'")

                # Créer l'annotation automatiquement
                try:
                    # Déterminer le type d'annotation (Date par défaut)
                    annotation_type_name = 'Date'

                    # Appeler la fonction de création
                    created = create_page_annotation_if_exists(page, annotation_type_name, date_value, user)

                    if created:
                        sync_result['annotations_created'] += 1
                        print(f"      ✅ Annotation créée avec succès pour '{date_value}'")
                    else:
                        print(f"      ⚠️ Impossible de créer l'annotation pour '{date_value}'")
                        sync_result['errors'].append(f"Création échouée: {date_value}")

                except Exception as e:
                    error_msg = f"Erreur création pour '{date_value}': {str(e)}"
                    print(f"      ❌ {error_msg}")
                    sync_result['errors'].append(error_msg)

        print(f"\n{'=' * 80}")
        print(f"📊 RÉSULTAT FINAL:")
        print(f"   ✅ Créées: {sync_result['annotations_created']}")
        print(f"   ❌ Rejetées: {sync_result['annotations_rejected']}")
        print(f"   ⚠️ Erreurs: {len(sync_result['errors'])}")
        if sync_result['errors']:
            for err in sync_result['errors']:
                print(f"      - {err}")
        print(f"{'=' * 80}\n")

        return sync_result

    except Exception as e:
        error_msg = f"Erreur: {str(e)}"
        print(f"❌ {error_msg}")
        import traceback
        traceback.print_exc()
        sync_result['errors'].append(error_msg)
        return sync_result


def create_page_annotation_if_exists(page, entity_type, entity_value, user):
    """
    Crée une annotation SEULEMENT si le texte existe dans la page
    Supporte les dates multilingues (FR/EN)
    """
    try:
        page_text = _get_page_text(page)
        if not page_text:
            print(f"   ⚠️ Pas de texte disponible")
            return False

        # Recherche simple d'abord
        start_pos = page_text.lower().find(entity_value.lower())
        found_text = entity_value

        # Si pas trouvé et que c'est une Date, chercher équivalent FR/EN
        if start_pos == -1 and entity_type.lower() in ['date', 'deadline', 'delay']:
            print(f"   🔍 Recherche de date équivalente pour '{entity_value}'...")

            # Extraire mois et année de entity_value
            import re

            # Normaliser la date recherchée
            norm_target = normalize_date_format(entity_value)
            if norm_target and '/' in norm_target:
                target_month, target_year = norm_target.split('/')

                # Rechercher toutes les dates potentielles dans le texte
                date_pattern = r'\b(january|february|march|april|may|june|july|august|september|october|november|december|janvier|février|fevrier|mars|avril|mai|juin|juillet|août|aout|septembre|octobre|novembre|décembre|decembre|jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)\s+(\d{4})\b'

                for match in re.finditer(date_pattern, page_text, re.IGNORECASE):
                    candidate_text = match.group(0)
                    norm_candidate = normalize_date_format(candidate_text)

                    print(f"      Candidat: '{candidate_text}' -> '{norm_candidate}'")

                    if norm_candidate == norm_target:
                        start_pos = match.start()
                        found_text = candidate_text
                        print(f"      ✅ Équivalent trouvé: '{found_text}'")
                        break

        if start_pos == -1:
            print(f"   ⚠️ Texte '{entity_value}' non trouvé dans la page")
            return False

        end_pos = start_pos + len(found_text)

        # Créer le type
        annotation_type, _ = AnnotationType.objects.get_or_create(
            name=entity_type,
            defaults={
                'display_name': entity_type.replace('_', ' ').title(),
                'color': '#10b981',
                'description': f"Auto: {entity_type}"
            }
        )

        # Vérifier si existe déjà (avec le texte trouvé)
        existing = Annotation.objects.filter(
            page=page,
            annotation_type=annotation_type,
            selected_text__iexact=found_text
        ).first()

        if existing:
            print(f"   ℹ️ Annotation déjà existante: '{found_text}'")
            return False

        # Créer l'annotation avec le texte réellement trouvé dans la page
        annotation = Annotation.objects.create(
            page=page,
            selected_text=found_text,
            annotation_type=annotation_type,
            start_pos=start_pos,
            end_pos=end_pos,
            validation_status='expert_created',
            validated_by=user,
            validated_at=timezone.now(),
            created_by=user,
            source='expert_sync'
        )

        print(f"   ✅ Annotation créée: '{found_text}' (recherché: '{entity_value}')")
        return True

    except Exception as e:
        print(f"   ❌ Erreur création: {e}")
        return False

def remove_page_annotations_for_entity(page, entity_type, entity_value, user, hard_delete=False):
    """
    Supprime ou rejette les annotations - VERSION AMÉLIORÉE pour dates multilingues
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
            print(f"⚠️ Type '{entity_type}' non trouvé")
            return {'count': 0, 'message': f'Type {entity_type} non trouvé'}

        # Rechercher les annotations sur cette page
        annotations = Annotation.objects.filter(
            page=page,
            annotation_type__in=annotation_types,
            validation_status__in=['pending', 'validated', 'expert_created']
        )

        matching_annotations = []
        entity_lower = entity_value.lower().strip()

        # ✅ AMÉLIORATION : normaliser la valeur cherchée si c'est une date
        is_date_type = any(keyword in entity_type.lower() for keyword in ['date', 'deadline', 'délai'])
        entity_normalized = normalize_date_format(entity_value) if is_date_type else None

        for ann in annotations:
            ann_text_lower = ann.selected_text.lower().strip()

            # Correspondance exacte
            if ann_text_lower == entity_lower:
                matching_annotations.append(ann)
                continue

            # Pour les dates : vérifier équivalence multilingue
            if is_date_type:
                # ✅ Normaliser l'annotation aussi
                ann_normalized = normalize_date_format(ann.selected_text)

                if entity_normalized and ann_normalized == entity_normalized:
                    print(f"✅ Date match: '{entity_value}' == '{ann.selected_text}' (normalisé: {entity_normalized})")
                    matching_annotations.append(ann)
                    continue

                # Vérifier aussi avec are_dates_equivalent
                if are_dates_equivalent(ann.selected_text, entity_value):
                    print(f"✅ Date équivalente: '{entity_value}' == '{ann.selected_text}'")
                    matching_annotations.append(ann)
                    continue

            # Correspondance partielle pour autres types
            if entity_lower in ann_text_lower or ann_text_lower in entity_lower:
                matching_annotations.append(ann)

        if not matching_annotations:
            print(f"⚠️ Aucune annotation trouvée pour '{entity_value}' (type: {entity_type})")
            return {'count': 0, 'message': f'Aucune annotation trouvée pour "{entity_value}"'}

        count = 0
        for ann in matching_annotations:
            if hard_delete:
                ann_id = ann.id
                ann.delete()
                print(f"❌ Annotation {ann_id} supprimée: '{ann.selected_text}' (page {page.page_number})")
            else:
                ann.validation_status = 'rejected'
                ann.validated_by = user
                ann.validated_at = timezone.now()
                ann.save(update_fields=['validation_status', 'validated_by', 'validated_at'])
                print(f"⛔ Annotation {ann.id} rejetée: '{ann.selected_text}' (page {page.page_number})")
            count += 1

        return {
            'count': count,
            'message': f'{count} annotation(s) {"supprimée(s)" if hard_delete else "rejetée(s)"} pour "{entity_value}"'
        }

    except Exception as e:
        print(f"❌ Erreur suppression annotations: {e}")
        import traceback
        traceback.print_exc()
        return {'count': 0, 'error': str(e)}


def extract_entities_from_summary(summary_text):
    """
    Extrait toutes les entitÃ©s d'un rÃ©sumÃ©
    Utilise les patterns existants + dÃ©tection intelligente
    """
    if not summary_text:
        return {}

    # Utiliser la fonction existante
    entities = extract_entities_from_text(summary_text)

    # Ajouter une dÃ©tection par structure "Type: valeur"
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
    Vérifie si deux dates sont équivalentes malgré des formats/langues différents
    Ex: "mai 2012" == "May 2012" == "05/2012" == "2012-05"
    """
    if not date1 or not date2:
        return False

    # Normaliser les deux dates
    norm1 = normalize_date_format(date1)
    norm2 = normalize_date_format(date2)

    if norm1 == norm2:
        return True

    # Vérifier aussi avec la fonction _is_date_like
    ok1, month1, year1 = _is_date_like(date1)
    ok2, month2, year2 = _is_date_like(date2)

    if ok1 and ok2:
        return month1 == month2 and year1 == year2

    return False


def normalize_date_format(date_str):
    """
    Normalise une date dans un format standard MM/YYYY
    Supporte français et anglais
    """
    if not date_str:
        return ""

    import re

    # Dictionnaire mois FR → numéro
    months_fr = {
        'janvier': '01', 'jan': '01', 'janv': '01',
        'février': '02', 'fevrier': '02', 'fév': '02', 'fev': '02', 'feb': '02',
        'mars': '03', 'mar': '03',
        'avril': '04', 'avr': '04', 'apr': '04',
        'mai': '05', 'may': '05',
        'juin': '06', 'jun': '06',
        'juillet': '07', 'juil': '07', 'jul': '07',
        'août': '08', 'aout': '08', 'aug': '08',
        'septembre': '09', 'sept': '09', 'sep': '09',
        'octobre': '10', 'oct': '10',
        'novembre': '11', 'nov': '11',
        'décembre': '12', 'decembre': '12', 'déc': '12', 'dec': '12'
    }

    # Dictionnaire mois EN → numéro
    months_en = {
        'january': '01', 'jan': '01',
        'february': '02', 'feb': '02',
        'march': '03', 'mar': '03',
        'april': '04', 'apr': '04',
        'may': '05',
        'june': '06', 'jun': '06',
        'july': '07', 'jul': '07',
        'august': '08', 'aug': '08',
        'september': '09', 'sep': '09', 'sept': '09',
        'october': '10', 'oct': '10',
        'november': '11', 'nov': '11',
        'december': '12', 'dec': '12'
    }

    # Combiner les deux dictionnaires
    all_months = {**months_fr, **months_en}

    date_lower = date_str.lower().strip()

    # Chercher mois textuel + année
    for month_name, month_num in all_months.items():
        if month_name in date_lower:
            # Extraire l'année
            year_match = re.search(r'(\d{4})', date_lower)
            if year_match:
                return f"{month_num}/{year_match.group(1)}"

    # Format numérique MM/YYYY ou MM-YYYY
    numeric_match = re.search(r'(\d{1,2})[/-](\d{4})', date_lower)
    if numeric_match:
        month = numeric_match.group(1).zfill(2)
        year = numeric_match.group(2)
        return f"{month}/{year}"

    # Format YYYY-MM ou YYYY/MM
    reverse_match = re.search(r'(\d{4})[/-](\d{1,2})', date_lower)
    if reverse_match:
        year = reverse_match.group(1)
        month = reverse_match.group(2).zfill(2)
        return f"{month}/{year}"

    return date_str
@login_required
@user_passes_test(is_expert)
@csrf_exempt
def update_summary_from_annotations(request, page_id):
    """
    RÃ©gÃ©nÃ¨re automatiquement le rÃ©sumÃ© de page basÃ© sur les annotations actuelles
    AppelÃ© quand l'expert modifie/ajoute/supprime des annotations
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        page = get_object_or_404(DocumentPage, id=page_id)

        # RÃ©cupÃ©rer toutes les annotations de la page
        annotations = page.annotations.all().select_related('annotation_type').order_by('start_pos')

        if not annotations.exists():
            # Pas d'annotations = rÃ©sumÃ© vide ou gÃ©nÃ©rique
            new_summary = f"Page {page.page_number}: Aucune annotation disponible."
            page.annotations_summary = new_summary
            page.annotations_summary_generated_at = timezone.now()
            page.save(update_fields=['annotations_summary', 'annotations_summary_generated_at'])

            return JsonResponse({
                'success': True,
                'summary': new_summary,
                'message': 'RÃ©sumÃ© mis Ã  jour (aucune annotation)'
            })

        # Construire les entitÃ©s depuis les annotations
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

        # GÃ©nÃ©rer le rÃ©sumÃ© avec IA si possible
        try:
            from rawdocs.groq_annotation_system import GroqAnnotator
            groq_annotator = GroqAnnotator()

            if groq_annotator.enabled and entities:
                # PrÃ©parer les donnÃ©es structurÃ©es pour le prompt
                lines = []
                total_pairs = 0
                for ent, vals in entities.items():
                    total_pairs += len(vals)
                    preview = "; ".join(vals[:4]) + ("â€¦" if len(vals) > 4 else "")
                    lines.append(f"- {ent}: {preview}")

                structured_view = "\n".join(lines)

                prompt = f"""Tu es un expert en analyse documentaire rÃ©glementaire.
GÃ©nÃ¨re un rÃ©sumÃ© court (3-4 phrases) et fluide basÃ© UNIQUEMENT sur les entitÃ©s annotÃ©es.

DOCUMENT: {page.document.title}
PAGE: {page.page_number}

ENTITÃ‰S ANNOTÃ‰ES:
{structured_view}

Contraintes:
- Ne liste pas tout; synthÃ©tise les thÃ¨mes/infos clÃ©s
- Utilise un ton professionnel et clair
- Termine par le nombre total de paires entitÃ©-valeur entre parenthÃ¨ses
- Focus sur les aspects rÃ©glementaires et pharmaceutiques

RÃ©ponds UNIQUEMENT par le paragraphe de rÃ©sumÃ©."""

                ai_summary = groq_annotator.complete_text(prompt, max_tokens=280, temperature=0.1)

                if ai_summary and len(ai_summary.strip()) > 20:
                    new_summary = ai_summary.strip()
                else:
                    # Fallback manuel
                    new_summary = f"Page {page.page_number}: synthÃ¨se de {total_pairs} Ã©lÃ©ment(s) annotÃ©(s) sur les entitÃ©s Â« {', '.join(list(entities.keys())[:5])}{'â€¦' if len(entities) > 5 else ''} Â»."
            else:
                # Fallback sans IA
                flat_count = sum(len(v) for v in entities.values())
                new_summary = f"Page {page.page_number}: {flat_count} valeur(s) annotÃ©e(s) sur {len(entities)} entitÃ©(s)."

        except Exception as e:
            print(f"Erreur gÃ©nÃ©ration rÃ©sumÃ© IA: {e}")
            # Fallback simple
            flat_count = sum(len(v) for v in entities.values())
            new_summary = f"Page {page.page_number}: {flat_count} annotation(s) sur {len(entities)} type(s) d'entitÃ©."

        # Sauvegarder le nouveau rÃ©sumÃ©
        page.annotations_summary = new_summary
        page.annotations_summary_generated_at = timezone.now()
        page.save(update_fields=['annotations_summary', 'annotations_summary_generated_at'])

        return JsonResponse({
            'success': True,
            'summary': new_summary,
            'entities_count': len(entities),
            'total_annotations': annotations.count(),
            'message': 'RÃ©sumÃ© rÃ©gÃ©nÃ©rÃ© depuis les annotations'
        })

    except Exception as e:
        print(f"Erreur mise Ã  jour rÃ©sumÃ© page {page_id}: {e}")
        return JsonResponse({'error': f'Erreur: {str(e)}'}, status=500)
@expert_required
@csrf_exempt
def validate_page_summary(request, page_id):
    """Validation du rÃ©sumÃ© d'une page"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    try:
        page = get_object_or_404(DocumentPage, id=page_id)
        data = json.loads(request.body)
        summary_text = data.get('summary_text', '').strip()

        if not summary_text:
            return JsonResponse({'error': 'RÃ©sumÃ© vide'}, status=400)

        page.page_summary = summary_text
        page.summary_validated = True
        page.summary_validated_at = timezone.now()
        page.summary_validated_by = request.user
        page.save(update_fields=['page_summary', 'summary_validated', 'summary_validated_at', 'summary_validated_by'])

        return JsonResponse({'success': True, 'message': 'RÃ©sumÃ© validÃ©'})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)



# Fonctions pour l'enrichissement sÃ©mantique du JSON
@expert_required
@csrf_exempt
def enrich_document_json(request, doc_id):
    """Enrichit le JSON d'un document avec du contexte sÃ©mantique"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        document = get_object_or_404(RawDocument, id=doc_id)
        basic_json = document.global_annotations_json or {}

        if not basic_json.get('entities'):
            return JsonResponse({
                'error': 'Aucune entitÃ© trouvÃ©e dans le document. Veuillez d\'abord gÃ©nÃ©rer le JSON de base.'
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
            reason="JSON enrichi automatiquement avec contexte sÃ©mantique"
        )

        return JsonResponse({
            'success': True,
            'message': 'JSON enrichi avec succÃ¨s',
            'enriched_json': enriched_json
        })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)



@expert_required
def expert_view_document_annotation_json_enriched(request, doc_id):
    """Vue pour le JSON enrichi sÃ©mantique"""
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
            return JsonResponse({'error': 'Question ou rÃ©ponse manquante'}, status=400)

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


# Place Ã§a en haut du fichier (prÃ¨s des autres helpers)
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
    Accepte diffÃ©rentes formes de sortie Groq et normalise en:
    [{"type": str, "text": str, "start_pos": int, "end_pos": int}, ...]
    """
    # 1) dÃ©jÃ  une liste dict
    if isinstance(raw, list):
        items = raw
    else:
        # 2) dict avec clÃ©s usuelles
        if isinstance(raw, dict):
            for key in ("entities", "annotations", "items", "data"):
                if key in raw and isinstance(raw[key], list):
                    items = raw[key]
                    break
            else:
                items = []
        else:
            # 3) string â†’ tenter JSON
            if isinstance(raw, str):
                s = raw.strip()
                # retirer fences Ã©ventuels
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
            # fallback mot-clÃ©
            for w in needle.split():
                if len(w) > 3:
                    start = base.find(w)
                    if start != -1:
                        end = start + len(w)
                        # vÃ©rifier chevauchement
                        for a, b in used_spans:
                            if not (end <= a or start >= b):
                                start = -1
                                break
                        if start != -1:
                            return start, end
            return -1, -1

        end = start + len(needle)
        # Ã©viter chevauchements
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
                # si aucune position possible, on garde quand mÃªme l'entitÃ© (positions 0..len)
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
    Recalcule ENTITIES + SUMMARY pour UNE page à partir des annotations actuelles.
    CORRIGÉ: Reconstruit complètement au lieu de fusionner pour refléter les suppressions.
    """
    # Récupérer les annotations actuelles avec les mêmes statuts que le JSON global
    anns = (
        page.annotations
        .filter(validation_status__in=GLOBAL_JSON_STATUSES)  # Inclut pending, validated, expert_created
        .select_related('annotation_type')
        .order_by('start_pos')
    )

    from rawdocs.views import _build_entities_map, generate_entities_based_page_summary

    # Construire les entités à partir des annotations actuelles
    current_entities = _build_entities_map(anns, use_display_name=True)

    # CORRECTION: Utiliser directement current_entities au lieu de fusionner
    # Cela permet de refléter les suppressions d'annotations

    # Générer un résumé lisible
    if current_entities:
        summary = generate_entities_based_page_summary(
            entities=current_entities,
            page_number=page.page_number,
            document_title=page.document.title
        )
    else:
        summary = f"Page {page.page_number}: aucune annotation."

    # JSON page avec entités actuelles (pas de fusion)
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
            "total_annotations_on_page": page.annotations.count(),  # Total incluant tous statuts
        },
        "entities": current_entities,  # Directement les entités actuelles
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "updated_by": getattr(user, "username", None),
        "rebuild_applied": True,  # Indicateur de reconstruction complète
    }

    page.annotations_summary = summary
    page.annotations_summary_generated_at = timezone.now()
    page.annotations_json = page_json
    page.save(update_fields=['annotations_summary', 'annotations_summary_generated_at', 'annotations_json'])

    return summary, current_entities

################
def find_entity_in_text(entity_text, page_text, entity_type=""):
    """
    Recherche intelligente d'entitÃ© dans le texte avec support spÃ©cialisÃ© pour les dates
    et autres formats variables.

    Args:
        entity_text (str): Texte de l'entitÃ© Ã  chercher (ex: "January 2013")
        page_text (str): Texte de la page oÃ¹ chercher
        entity_type (str): Type d'entitÃ© pour optimiser la recherche

    Returns:
        tuple: (start_pos, end_pos, actual_text) ou (-1, -1, entity_text) si non trouvÃ©
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

    # 2. Recherche spÃ©cialisÃ©e par type d'entitÃ©
    if any(keyword in entity_type.lower() for keyword in ['date', 'time', 'dÃ©lai', 'deadline']):
        return _find_date_entity(entity_text, page_text)

    # 3. Recherche flexible avec variations
    result = _find_flexible_match(entity_text, page_text)
    if result[0] >= 0:
        return result

    # 4. Recherche par mots-clÃ©s (version amÃ©liorÃ©e)
    result = _find_keyword_match(entity_text, page_text)
    if result[0] >= 0:
        return result

    # 5. Pas trouvÃ©
    return -1, -1, entity_text


def _find_date_entity(entity_text, page_text):
    """
    Recherche spÃ©cialisÃ©e pour les dates avec formats multiples
    """
    import re
    from datetime import datetime

    page_lower = page_text.lower()
    entity_lower = entity_text.lower()

    # Extraire les composants de date de l'entitÃ©
    date_patterns = [
        r'(\w+)\s+(\d{4})',  # "January 2013"
        r'(\d{1,2})/(\d{4})',  # "01/2013"
        r'(\d{1,2})-(\d{4})',  # "01-2013"
        r'(\w+)\s+(\d{1,2}),?\s+(\d{4})',  # "January 15, 2013"
        r'(\d{1,2})\s+(\w+)\s+(\d{4})',  # "15 January 2013"
    ]

    # Tenter de parser l'entitÃ© comme date
    entity_components = set()
    for pattern in date_patterns:
        match = re.search(pattern, entity_lower)
        if match:
            entity_components.update(match.groups())

    if not entity_components:
        # Si pas de format date reconnu, recherche normale
        return -1, -1, entity_text

    # Chercher ces composants dans diffÃ©rents formats dans le texte
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

    # Ajouter des variantes spÃ©cialisÃ©es
    if len(entity_components) >= 2:
        components = list(entity_components)

        # Mois + annÃ©e
        month_abbrevs = {
            'january': 'jan', 'february': 'feb', 'march': 'mar',
            'april': 'apr', 'may': 'may', 'june': 'jun',
            'july': 'jul', 'august': 'aug', 'september': 'sep',
            'october': 'oct', 'november': 'nov', 'december': 'dec'
        }

        for comp in components:
            if comp in month_abbrevs:
                # Chercher version abrÃ©gÃ©e
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

    # Recherche plus permissive : composants sÃ©parÃ©s mais proches
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

    # Variations Ã  tester
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
        if variation != entity_lower:  # DÃ©jÃ  testÃ© avant
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
    Recherche par mots-clÃ©s amÃ©liorÃ©e qui garde plus de contexte
    """
    page_lower = page_text.lower()
    words = entity_text.lower().split()

    # Trier par longueur dÃ©croissante pour privilÃ©gier les mots plus spÃ©cifiques
    words.sort(key=len, reverse=True)

    for word in words:
        if len(word) >= 3:  # RÃ©duire le seuil de 4 Ã  3 caractÃ¨res
            start_pos = page_lower.find(word)
            if start_pos >= 0:
                # Essayer de prendre plus de contexte autour du mot trouvÃ©
                context_start = max(0, start_pos - 20)
                context_end = min(len(page_text), start_pos + len(word) + 20)
                context = page_text[context_start:context_end]

                # Chercher si d'autres mots de l'entitÃ© sont dans ce contexte
                context_lower = context.lower()
                other_words_found = sum(1 for w in words if w != word and w in context_lower)

                if other_words_found > 0:
                    # Prendre tout le contexte contenant plusieurs mots
                    return context_start, context_end, context.strip()
                else:
                    # Juste le mot trouvÃ©
                    end_pos = start_pos + len(word)
                    actual_text = page_text[start_pos:end_pos]
                    return start_pos, end_pos, actual_text

    return -1, -1, entity_text



# --- Conserver les annotations annotateur (pending) dans le JSON global ---
GLOBAL_JSON_STATUSES = ['pending', 'validated', 'expert_created']

def _normalize_values(values):
    """trim + dédup (insensible à la casse) + espaces normalisés"""
    seen, out = set(), []
    for v in values or []:
        vv = re.sub(r'\s+', ' ', (v or '').strip())
        key = vv.lower()
        if vv and key not in seen:
            seen.add(key)
            out.append(vv)
    return out


def _merge_entities_preserve(old_entities: dict | None, new_entities: dict | None) -> dict:
    """
    Fusionne les entités en conservant l'existant (dédupe insensible à la casse/espaces).
    Version améliorée qui préserve l'ordre et évite les doublons.
    """
    merged = {}

    # D'abord, copier toutes les entités existantes
    for k, v in (old_entities or {}).items():
        merged[k] = _normalize_values(v)

    # Ensuite, ajouter/fusionner les nouvelles entités
    for k, vals in (new_entities or {}).items():
        if k in merged:
            # Fusionner avec existant (éviter doublons)
            existing_normalized = {val.lower().strip() for val in merged[k]}
            for val in (vals or []):
                normalized_val = val.lower().strip()
                if normalized_val and normalized_val not in existing_normalized:
                    merged[k].append(val)
                    existing_normalized.add(normalized_val)
        else:
            # Nouvelle entité
            merged[k] = _normalize_values(vals or [])

    # Nettoyer les entités vides
    return {k: v for k, v in merged.items() if v}


@expert_required
@csrf_exempt
def create_annotation_ajax(request):
    """
    Création d'une annotation (pré-validée) + MAJ JSON fusionné + régénération résumé page/doc.
    Version améliorée avec fusion pour préserver les annotations existantes.
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

        # MAJ page + JSON global avec FUSION (préserver annotations existantes)
        new_page_summary = None
        fusion_success = False
        try:
            # Debug avant fusion
            debug_json_fusion(page.document, f"create_annotation by {request.user.username}")

            # Fusion page : conserve + ajoute nouvelles entités
            new_page_summary, merged_entities = build_page_summary_and_json(page, request.user)

            # Fusion document global : conserve + ajoute
            update_document_global_json(page.document, request.user)

            fusion_success = True
            print(f"✅ Fusion réussie - Annotation ajoutée: '{text}' ({entity_type_name})")

            # Debug après fusion
            debug_json_fusion(page.document, f"create_annotation_completed by {request.user.username}")

        except Exception as e:
            print(f"⚠️ Erreur MAJ JSON/summary (create): {e}")
            # Fallback : essayer juste la page
            try:
                new_page_summary, _ = build_page_summary_and_json(page, request.user)
                print(f"✅ Fallback page summary réussi")
            except Exception as e2:
                print(f"❌ Fallback page summary échoué: {e2}")

        # Déclenchement régénération globale (async)
            # Resume global (IMMEDIATE pour action manuelle expert - ignore le throttling)
            REGENERATION_CACHE.pop(page.document.id, None); trigger_summary_regeneration_safe(page.document, request.user, 0)  # Immediate for manual expert action
        except Exception as e:
            print(f"⚠️ Erreur déclenchement régénération (create): {e}")

        return JsonResponse({
            'success': True,
            'annotation_id': annotation.id,
            'message': 'Annotation créée avec succès',
            'page_summary': new_page_summary,
            'auto_summary_triggered': True,
            'fusion_applied': fusion_success,
            'preservation_mode': 'active'  # Indique que les annotations existantes sont préservées
        })

    except Exception as e:
        print(f"❌ Erreur create_annotation_ajax: {e}")
        return JsonResponse({'success': False, 'error': str(e)})

# --- UPSERT SANS SUPPRESSION POUR LES ANNOTATIONS D'UNE PAGE ---

from typing import Iterable, Tuple

def _overlap(a: Tuple[int,int], b: Tuple[int,int]) -> bool:
    """True si deux intervalles [start,end) se chevauchent un minimum."""
    (a0, a1), (b0, b1) = a, b
    return max(a0, b0) < min(a1, b1)

def _same_text(a: str, b: str) -> bool:
    return (a or '').strip().lower() == (b or '').strip().lower()

def upsert_annotations_for_page(
    page: DocumentPage,
    items: Iterable[dict],
    source: str = "groq_llama3.3_70b",
    default_status: str = "pending",
    min_overlap_chars: int = 2
) -> list[Annotation]:
    """
    Insère ou met à jour des annotations IA SANS toucher aux autres (pas de delete).
    On matche sur (type, texte ~, chevauchement positions) pour décider update vs insert.
    """
    created_or_updated = []
    existing = list(
        Annotation.objects.filter(page=page)
        .select_related("annotation_type")
        .order_by("start_pos")
    )

    # cache types par nom
    type_cache: dict[str, AnnotationType] = {}

    for it in items or []:
        raw_type = (it.get("type") or "").strip()
        raw_text = (it.get("text") or "").strip()
        if not raw_type or not raw_text:
            continue

        start_pos = int(it.get("start_pos") or 0)
        end_pos   = int(it.get("end_pos") or max(start_pos + len(raw_text), start_pos + 1))
        conf      = it.get("confidence", 0.8)

        # type (get_or_create)
        if raw_type not in type_cache:
            at, _ = AnnotationType.objects.get_or_create(
                name=raw_type,
                defaults={
                    "display_name": raw_type.replace("_", " ").title(),
                    "color": "#54a0ff",
                    "description": f"Auto ({source})"
                }
            )
            type_cache[raw_type] = at
        atype = type_cache[raw_type]

        # tentative de match sur existant de la même page
        matched = None
        for ann in existing:
            if ann.annotation_type_id != atype.id:
                continue
            if not _same_text(ann.selected_text, raw_text):
                continue
            if _overlap((ann.start_pos or 0, ann.end_pos or 0), (start_pos, end_pos)):
                # assez de chevauchement ?
                if min(ann.end_pos, end_pos) - max(ann.start_pos, start_pos) >= min_overlap_chars:
                    matched = ann
                    break

        if matched:
            # mise à jour légère: positions/confiance/source, ne touche pas status expert/annotateur
            changed = False
            if matched.start_pos != start_pos or matched.end_pos != end_pos:
                matched.start_pos, matched.end_pos = start_pos, end_pos
                changed = True
            if getattr(matched, "confidence_score", None) != conf:
                try:
                    matched.confidence_score = conf
                    changed = True
                except Exception:
                    pass
            if matched.source != source:
                matched.source = source
                changed = True
            if changed:
                matched.save(update_fields=["start_pos", "end_pos", "source"] + (["confidence_score"] if hasattr(matched, "confidence_score") else []))
            created_or_updated.append(matched)
        else:
            # INSERT: on ne supprime rien d'autre
            ann = Annotation.objects.create(
                page=page,
                selected_text=raw_text,
                annotation_type=atype,
                start_pos=start_pos,
                end_pos=end_pos,
                validation_status=default_status,  # ex: 'pending' si annotateur, ou 'expert_created' côté expert
                source=source
            )
            created_or_updated.append(ann)

    return created_or_updated
@csrf_exempt
@login_required
def annotate_page_with_groq_view(request, page_id):
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "POST required"}, status=405)

    page = get_object_or_404(DocumentPage, id=page_id)
    data = json.loads(request.body or "{}")

    # 1) appeler ton annotateur pour obtenir 'items' (liste de dicts)
    from rawdocs.groq_annotation_system import GroqAnnotator
    annotator = GroqAnnotator()
    anns, _schema = annotator.annotate_page_with_groq({
        "page_num": page.page_number,
        "text": getattr(page, "cleaned_text", "") or getattr(page, "text_content", "") or ""
    })

    # 2) UPSERT — aucune suppression
    upsert_annotations_for_page(
        page,
        anns,
        source="groq_llama3.3_70b",
        default_status="pending"  # garder comme 'pending' côté annotateur
    )

    # 3) Mettre à jour résumé/JSON (fusion, pas d’écrasement)
    try:
        build_page_summary_and_json(page, request.user)  # doit être non destructif côté DB
        update_document_global_json(page.document, request.user)
    except Exception as e:
        print(f"⚠️ post-groq update failed: {e}")

    return JsonResponse({"success": True, "count": len(anns)})


# expert/views.py - Ajouter cette fonction après les autres vues

# expert/views.py - Ajouter ces fonctions

@expert_required
def expert_review_annotations(request, doc_id):
    """
    Interface de révision Expert pour valider/rejeter les annotations des annotateurs.
    L'expert peut voir toutes les annotations pending et les valider/rejeter une par une.
    """
    document = get_object_or_404(RawDocument, id=doc_id, is_ready_for_expert=True)

    # Récupérer toutes les annotations pending (créées par les annotateurs)
    pending_annotations = Annotation.objects.filter(
        page__document=document,
        validation_status='pending'
    ).select_related(
        'page',
        'annotation_type',
        'created_by'
    ).order_by('page__page_number', 'start_pos')

    # Statistiques globales
    total_annotations = Annotation.objects.filter(page__document=document).count()
    validated_annotations = Annotation.objects.filter(
        page__document=document,
        validation_status__in=['validated', 'expert_created']
    ).count()
    rejected_annotations = Annotation.objects.filter(
        page__document=document,
        validation_status='rejected'
    ).count()

    # Grouper par page pour affichage organisé
    pages_with_annotations = {}
    for ann in pending_annotations:
        page_num = ann.page.page_number
        if page_num not in pages_with_annotations:
            pages_with_annotations[page_num] = {
                'page': ann.page,
                'annotations': [],
                'page_text_preview': (ann.page.cleaned_text or '')[
                                     :200] + '...' if ann.page.cleaned_text else 'Pas de texte disponible'
            }
        pages_with_annotations[page_num]['annotations'].append(ann)

    # Trier par numéro de page
    pages_with_annotations = dict(sorted(pages_with_annotations.items()))

    context = {
        'document': document,
        'pages_with_annotations': pages_with_annotations,
        'total_pending': pending_annotations.count(),
        'total_annotations': total_annotations,
        'validated_annotations': validated_annotations,
        'rejected_annotations': rejected_annotations,
        'completion_percentage': int((validated_annotations / total_annotations * 100)) if total_annotations > 0 else 0,
    }

    return render(request, 'expert/review_annotations.html', context)


@expert_required
@csrf_exempt
def expert_bulk_validate_annotations(request, doc_id):
    """Validation en masse de toutes les annotations pending d'un document"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        document = get_object_or_404(RawDocument, id=doc_id)

        pending_annotations = Annotation.objects.filter(
            page__document=document,
            validation_status='pending'
        )

        count = 0
        for ann in pending_annotations:
            ann.validation_status = 'validated'
            ann.validated_by = request.user
            ann.validated_at = timezone.now()
            ann.save(update_fields=['validation_status', 'validated_by', 'validated_at'])
            count += 1

        # Mettre à jour le JSON global après validation en masse
        try:
            update_document_global_json(document, request.user)
        except Exception as e:
            print(f"⚠️ Erreur MAJ JSON après validation en masse: {e}")

        return JsonResponse({
            'success': True,
            'message': f'{count} annotation(s) validée(s) avec succès',
            'validated_count': count
        })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

# ============================================
# 📄 PROXY PDF POUR IFRAME
# ============================================
@expert_required
def get_page_image(request, doc_id, page_num):
    """
    Génère et retourne une image PNG d'une page spécifique du PDF
    """
    from django.http import HttpResponse, Http404
    from rawdocs.models import RawDocument
    import logging

    logger = logging.getLogger(__name__)

    try:
        # Vérifier que le document existe
        try:
            document = RawDocument.objects.get(pk=doc_id)
        except RawDocument.DoesNotExist:
            logger.error(f"Document {doc_id} n'existe pas")
            raise Http404(f'Document {doc_id} non trouvé')

        if not document.file:
            logger.error(f"Document {doc_id} n'a pas de fichier associé")
            raise Http404('PDF non trouvé - aucun fichier associé')

        file_path = document.file.path

        # Vérifier si le fichier existe
        import os
        if not os.path.exists(file_path):
            logger.error(f"Fichier PDF introuvable: {file_path}")
            raise Http404(f'Fichier PDF introuvable: {file_path}')

        # Ouvrir le PDF avec PyMuPDF
        import fitz
        pdf_document = fitz.open(file_path)

        # Vérifier que le numéro de page est valide
        if page_num < 1 or page_num > len(pdf_document):
            pdf_document.close()
            raise Http404(f'Page {page_num} invalide. Le document contient {len(pdf_document)} pages.')

        # Obtenir la page (index 0-based)
        page = pdf_document[page_num - 1]

        # Convertir la page en image (zoom factor pour qualité)
        zoom = 2.0  # Facteur de zoom pour meilleure qualité
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat, alpha=False)

        # Convertir en PNG
        img_data = pix.tobytes("png")

        pdf_document.close()

        # Retourner l'image
        response = HttpResponse(img_data, content_type='image/png')
        response['Cache-Control'] = 'public, max-age=3600'  # Cache 1 heure
        return response

    except Http404:
        raise
    except Exception as e:
        logger.error(f"Erreur lors de la génération de l'image de la page: {e}", exc_info=True)
        raise Http404(f'Erreur: {str(e)}')


def expert_proxy_pdf(request, doc_id):
    """
    Vue proxy pour servir le PDF avec les en-têtes appropriés
    pour permettre l'affichage dans une iframe (contournement X-Frame-Options)
    """
    from django.http import FileResponse, Http404, HttpResponse
    from rawdocs.models import RawDocument
    import os
    import logging

    logger = logging.getLogger(__name__)

    try:
        document = get_object_or_404(RawDocument, pk=doc_id)
        logger.info(f"Document trouvé: {document.id}")

        if not document.file:
            logger.error(f"Document {doc_id} n'a pas de fichier associé")
            raise Http404('PDF non trouvé - aucun fichier associé au document')

        file_path = document.file.path
        logger.info(f"Chemin du fichier initial: {file_path}")

        # Vérifier si le fichier existe, sinon essayer de corriger les chemins dupliqués
        if not os.path.exists(file_path):
            logger.warning(f"Fichier introuvable à: {file_path}")

            # Essayer de détecter et corriger les chemins avec répertoires dupliqués
            # Ex: media/20250921_170539/20250921_170539/E9_Guideline.pdf
            #  -> media/20250921_170539/E9_Guideline.pdf
            path_parts = file_path.split(os.sep)

            # Chercher les répertoires dupliqués consécutifs
            corrected_parts = []
            skip_next = False
            for i, part in enumerate(path_parts):
                if skip_next:
                    skip_next = False
                    continue
                if i < len(path_parts) - 1 and part == path_parts[i + 1]:
                    # Répertoire dupliqué trouvé, garder seulement le premier
                    corrected_parts.append(part)
                    skip_next = True
                    logger.info(f"Répertoire dupliqué détecté: {part}")
                else:
                    corrected_parts.append(part)

            corrected_path = os.sep.join(corrected_parts)

            if corrected_path != file_path and os.path.exists(corrected_path):
                logger.info(f"Chemin corrigé trouvé: {corrected_path}")
                file_path = corrected_path
            else:
                # Si la correction ne fonctionne pas, essayer de chercher le fichier
                # dans les sous-répertoires du répertoire parent
                media_root = settings.MEDIA_ROOT
                filename = os.path.basename(file_path)

                # Chercher dans media_root et ses sous-répertoires
                for root, dirs, files in os.walk(media_root):
                    if filename in files:
                        potential_path = os.path.join(root, filename)
                        logger.info(f"Fichier trouvé à: {potential_path}")
                        file_path = potential_path
                        break
                else:
                    logger.error(f"Fichier PDF introuvable après toutes les tentatives")
                    raise Http404(f'Fichier PDF introuvable: {filename}')

        # Servir le fichier avec les en-têtes appropriés
        response = FileResponse(open(file_path, 'rb'), content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="{os.path.basename(file_path)}"'
        response['X-Frame-Options'] = 'SAMEORIGIN'
        response['Cache-Control'] = 'no-cache'

        logger.info(f"PDF servi avec succès: {file_path}")
        return response

    except Exception as e:
        logger.error(f"Erreur lors du chargement du PDF {doc_id}: {str(e)}")
        raise