# expert/views.py
import os

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
    """AJAX endpoint to validate/reject annotation"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            annotation = get_object_or_404(Annotation, id=annotation_id)
            action = data.get('action')

            # Save state before modification
            old_status = annotation.validation_status

            if action == 'validate':
                annotation.validation_status = 'validated'
                annotation.validated_by = request.user
                annotation.validated_at = timezone.now()
                annotation.save()

                # LOG ACTION
                log_expert_action(
                    user=request.user,
                    action='annotation_validated',
                    annotation=annotation,
                    reason=f"Manual validation by expert. Status: {old_status} → validated"
                )

                return JsonResponse({
                    'success': True,
                    'message': 'Annotation validée',
                    'status': 'validated'
                })

            elif action == 'reject':
                annotation.validation_status = 'rejected'
                annotation.validated_by = request.user
                annotation.validated_at = timezone.now()
                annotation.save()

                # LOG ACTION
                log_expert_action(
                    user=request.user,
                    action='annotation_rejected',
                    annotation=annotation,
                    reason=f"Manual rejection by expert. Status: {old_status} → rejected"
                )

                return JsonResponse({
                    'success': True,
                    'message': 'Annotation rejetée',
                    'status': 'rejected'
                })

        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})

    return JsonResponse({'success': False, 'error': 'Method not allowed'})


@expert_required
@csrf_exempt
def create_annotation_ajax(request):
    """AJAX endpoint for experts to create new annotations"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            page_id = data.get('page_id')
            text = data.get('text')
            entity_type_name = data.get('entity_type')
            if not entity_type_name:
                return JsonResponse({'success': False, 'error': 'entity_type is required'})

            # Get the page
            page = get_object_or_404(DocumentPage, id=page_id)

            # Get or create the AnnotationType
            annotation_type, created = AnnotationType.objects.get_or_create(
                name=entity_type_name,
                defaults={
                    'display_name': entity_type_name.replace('_', ' ').title(),
                    'color': '#3b82f6',
                    'description': f"Expert created type: {entity_type_name}"
                }
            )

            # Create the annotation (experts create pre-validated annotations)
            annotation = Annotation.objects.create(
                page=page,
                selected_text=text,
                annotation_type=annotation_type,
                start_pos=data.get('start_pos', 0),  # Changed from 'start_offset'
                end_pos=data.get('end_pos', len(text)),  # Changed from 'end_offset'
                validation_status='expert_created',
                validated_by=request.user,
                validated_at=timezone.now(),
                created_by=request.user,
                source='expert'
            )

            # LOG ACTION
            log_expert_action(
                user=request.user,
                action='annotation_created',
                annotation=annotation,
                reason=f"New annotation created by expert in page {page.page_number}"
            )

            return JsonResponse({
                'success': True,
                'annotation_id': annotation.id,
                'message': 'Annotation créée avec succès'
            })

        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})

    return JsonResponse({'success': False, 'error': 'Method not allowed'})


@expert_required
@csrf_exempt
def modify_annotation_ajax(request, annotation_id):
    """Modify a rejected annotation"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            annotation = get_object_or_404(Annotation, id=annotation_id)

            new_text = data.get('text')
            new_entity_type_name = data.get('entity_type')

            # Save old values for logging
            old_text = annotation.selected_text
            old_entity_type_name = annotation.annotation_type.name
            old_status = annotation.validation_status

            # Get or create the new annotation type
            annotation_type, created = AnnotationType.objects.get_or_create(
                name=new_entity_type_name,
                defaults={
                    'display_name': new_entity_type_name.replace('_', ' ').title(),
                    'color': '#3b82f6',
                    'description': f"Expert type: {new_entity_type_name}"
                }
            )

            # Update the annotation
            annotation.selected_text = new_text
            annotation.annotation_type = annotation_type
            annotation.validation_status = 'validated'  # Auto-validate after expert modification
            annotation.validated_by = request.user
            annotation.validated_at = timezone.now()
            annotation.save()

            # LOG ACTION
            log_expert_action(
                user=request.user,
                action='annotation_modified',
                annotation=annotation,
                old_text=old_text,
                new_text=new_text,
                old_entity_type=old_entity_type_name,
                new_entity_type=new_entity_type_name,
                reason=f"Modification by expert. Status: {old_status} → validated"
            )

            try:
                # Mise à jour du JSON de la page
                page = annotation.page
                document = page.document
                page_annotations = page.annotations.all().select_related('annotation_type').order_by('start_pos')

                from rawdocs.views import _build_entities_map, generate_entities_based_page_summary
                page_entities = _build_entities_map(page_annotations, use_display_name=True)

                page_json = {
                    'document': {
                        'id': str(document.id),
                        'title': document.title,
                        'doc_type': getattr(document, 'doc_type', None),
                        'source': getattr(document, 'source', None),
                    },
                    'page': {
                        'number': page.page_number,
                        'annotations_count': page_annotations.count(),
                    },
                    'entities': page_entities,
                    'generated_at': datetime.utcnow().isoformat() + 'Z',
                }

                page.annotations_json = page_json
                page.save(update_fields=['annotations_json'])

                # Mise à jour du JSON du document
                all_annotations = Annotation.objects.filter(
                    page__document=document
                ).select_related('annotation_type', 'page').order_by('page__page_number', 'start_pos')

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

                print(f"✅ JSON mis à jour après modification pour la page {page.page_number} et le document")

            except Exception as e:
                print(f"❌ Erreur lors de la mise à jour du JSON après modification: {str(e)}")

            return JsonResponse({
                'success': True,
                'message': 'Annotation modifiée, validée et JSON mis à jour'
            })

        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})

    return JsonResponse({'success': False, 'error': 'Method not allowed'})


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
    """Undo validation of an annotation"""
    if request.method == 'POST':
        try:
            annotation = get_object_or_404(Annotation, id=annotation_id)

            # Save state before
            old_status = annotation.validation_status
            old_validator = getattr(annotation.validated_by, 'username',
                                    'Unknown') if annotation.validated_by else 'None'

            # Reset validation status
            annotation.validation_status = 'pending'
            annotation.validated_by = None
            annotation.validated_at = None
            annotation.save()

            # LOG ACTION
            log_expert_action(
                user=request.user,
                action='validation_undone',
                annotation=annotation,
                reason=f"Validation cancelled. Status: {old_status} → pending. Originally validated by: {old_validator}"
            )

            return JsonResponse({
                'success': True,
                'message': 'Validation annulée'
            })

        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})

    return JsonResponse({'success': False, 'error': 'Method not allowed'})


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

@expert_required
@csrf_exempt
def save_summary_changes(request, doc_id):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    try:
        document = get_object_or_404(RawDocument, id=doc_id)
        payload = json.loads(request.body)
        new_summary = (payload.get('summary_content') or '').strip()
        if not new_summary:
            return JsonResponse({'error': 'Summary cannot be empty'}, status=400)

        old_summary = document.global_annotations_summary or ""

        # 2) Préparer/initialiser le JSON global et les entités si manquants
        current_json = document.global_annotations_json or {}
        current_json.setdefault('document', {})
        current_entities = current_json.get('entities', {}) or {}

        if not current_entities:
            # Tenter de construire les entités depuis les annotations du document
            try:
                from rawdocs.views import _build_entities_map  # utilitaire existant
                all_annotations = Annotation.objects.filter(page__document=document).select_related('annotation_type')
                built = _build_entities_map(all_annotations, use_display_name=True) or {}
                current_entities = built
            except Exception:
                # Fallback minimal: construire une map simple type -> valeurs depuis les annotations
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

            # Si toujours vide (ex: document sans annotations), initialiser des clés par défaut
            if not current_entities:
                default_keys = [
                    'Invented Name',
                    'Strength',
                    'Pharmaceutical Form',
                    'Route Of Administration',
                    'Immediate Packaging',
                    'Pack Size',
                    'Ma Number',
                ]
                current_entities = {k: [] for k in default_keys}

            current_json['entities'] = current_entities

        allowed_keys = list(current_entities.keys())

        # 1) Extraire les entités du nouveau résumé:
        #    a) via libellés existants (Clé: valeur)
        extracted_by_keys = extract_by_allowed_keys(new_summary, allowed_keys)
        #    b) via texte libre (phrases), en détectant entité/valeur
        free_extracted = extract_entities_from_text(new_summary) or {}
        #       b2) enrichissement par détections ciblées (route, packaging, pack size, forme)
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
                    r"(?i)\b(blisters?|blister|flacons?|bouteilles?|bottles?|sachets?|ampoules?|seringues?\s*pr[ée]remplies?)\b",
                    new_summary):
                packaging_vals.add(m.group(0))
            if packaging_vals:
                free_extracted.setdefault('Immediate Packaging', []).extend(sorted(packaging_vals))

            # Pack Size (ex: 20 comprimés, 100 ml, 6 sachets)
            pack_vals = set()
            for m in re.finditer(
                    r"(?i)\b([0-9]{1,4}\s*(?:comprim[ée]s?|g[ée]lules?|capsules?|sachets?|ml|ampoules?|unit[eé]s?))\b",
                    new_summary):
                pack_vals.add(m.group(1))
            if pack_vals:
                free_extracted.setdefault('Pack Size', []).extend(sorted(pack_vals))

            # Pharmaceutical Form
            form_vals = set()
            for m in re.finditer(
                    r"(?i)\b(comprim[ée]s?|g[ée]lules?|capsules?|sirop|solution|suspension|poudre|injectable|tablet[s]?)\b",
                    new_summary):
                form_vals.add(m.group(0))
            if form_vals:
                free_extracted.setdefault('Pharmaceutical Form', []).extend(sorted(form_vals))
        except Exception:
            pass

        #    c) Fusionner en ne gardant que les clés existantes (mapping canonique)
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
        print(f"Entités extraites (fusion): {extracted_entities}")

        # 3) Mise à jour fine par valeurs (ajouts/suppressions basées sur le résumé)
        updated_entities = current_entities.copy()
        changes_made = []
        entities_added: dict[str, list[str]] = {}
        entities_removed: dict[str, list[str]] = {}
        changed_keys: list[str] = []

        # Normaliser les clés permises (mapping insensible à la casse)
        key_map = {k.lower(): k for k in allowed_keys}

        # Extraire entités de l'ancien résumé pour détecter suppressions (toutes clés)
        old_extracted = extract_by_allowed_keys(old_summary or "", allowed_keys)

        def _norm_val(s: str) -> str:
            return re.sub(r'\s+', ' ', (s or '').strip()).lower()

        for lower_k, canon_k in key_map.items():
            # valeurs existantes
            existing_vals = list(updated_entities.get(canon_k, []) or [])
            existing_norms = {_norm_val(v) for v in existing_vals}

            # valeurs extraites anciennes et nouvelles pour cette clé
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

            # suppressions: présentes avant, absentes maintenant
            to_remove = old_norms - new_norms
            # ajouts: présentes dans le nouveau résumé, pas déjà existantes
            to_add = [v for v in cleaned_new if _norm_val(v) not in existing_norms]

            # appliquer suppressions
            kept = [v for v in existing_vals if _norm_val(v) not in to_remove]
            removed_list = [v for v in existing_vals if _norm_val(v) in to_remove]
            # appliquer ajouts
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

        # 4) Sauvegarder le résumé
        document.global_annotations_summary = new_summary
        document.global_annotations_summary_generated_at = timezone.now()

        # 5) Mettre à jour le JSON
        current_json['entities'] = updated_entities

        # 6) Mettre à jour les métadonnées
        current_json['last_updated'] = timezone.now().isoformat()
        current_json['last_updated_by'] = request.user.username
        current_json['document'].update({
            'summary': new_summary,
            'summary_updated_at': timezone.now().isoformat(),
            'summary_updated_by': request.user.username,
        })

        # 7) Sauvegarder les modifications
        document.global_annotations_json = current_json
        document.save(update_fields=['global_annotations_summary', 'global_annotations_summary_generated_at',
                                     'global_annotations_json'])

        # Log de l'action
        reason = "Summary edited and entities synchronized"
        if changes_made:
            reason += " | Changes: " + " ; ".join(changes_made[:5])
        else:
            reason += " | Aucune entité changée"
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
        })

        # métadonnées de mise à jour
        current_json['last_updated'] = timezone.now().isoformat()
        current_json['last_updated_by'] = request.user.username
        current_json['document'].update({
            'summary': new_summary,
            'summary_updated_at': timezone.now().isoformat(),
            'summary_updated_by': request.user.username,
        })

        document.global_annotations_json = current_json
        document.save(update_fields=['global_annotations_json'])

        # (optionnel) push Mongo ici…

        # Log
        reason = "Summary edited; IA replace-only"
        if human_diffs:
            reason += " | " + " ; ".join(human_diffs[:5])
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
            'message': 'Résumé sauvegardé',
            'updated_json': current_json,
            'changed_keys': changed_keys,
            'entities_changes': human_diffs,
        })
    except Exception as e:
        print(f"❌ save_summary_changes error: {e}")
        return JsonResponse({'error': str(e)}, status=500)


# --- helpers backend : extraction stricte + nettoyage ---

import re


def extract_entities_from_text(text: str) -> dict:
    """
    Extraction intelligente des entités du texte avec support pour tous les types d'entités.
    Retourne un dict {Type: [valeurs]} avec support pour tous les types existants.
    """
    # Patterns de base pour les types courants (FR/EN + abréviations)
    base_patterns = {
        'Product': [
            # "Produit: X" ou "Product: X"
            r'\b(?:produit|médicament|product)\b\s*:?\s*((?-i:[A-Z])[\wÀ-ÿ\s\-\/]{2,60})',
            # "Le produit est X" / "The product is X"
            r'\b(?:produit|product)\b\s+(?:est|is)\s+((?-i:[A-Z])[\wÀ-ÿ\s\-\/]{2,60})',
            # "X est/sera/contient" en début de phrase (moins prioritaire)
            r'^(?:le\s+|the\s+)?([A-Z][\wÀ-ÿ\s\-\/]{3,60})\s+(?:est|sera|contient|is|contains)\b',
            # "Nom du produit: X"
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
        ]
    }

    # Patterns génériques pour capturer d'autres types possibles
    # Patterns génériques restreints pour limiter le bruit (capture jusqu'à la 1ère ponctuation forte)
    generic_patterns = [
        r'(?:{})\s*[:\-]\s*([^\.;\n]+)',  # Clé: valeur (éviter la virgule qui crée des fragments parasites)
        r'(?:{})\s+(?:est|is|are)\s+([^\.;\n]+)',
    ]

    results = {}

    # 1. Appliquer les patterns de base
    for entity_type, patterns in base_patterns.items():
        found_values = set()
        for pattern in patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE | re.MULTILINE)
            for match in matches:
                value = match.group(1).strip()
                if value and len(value) <= 100:  # Limite raisonnable
                    found_values.add(value)
        if found_values:
            results[entity_type] = list(found_values)

    # 2. Chercher d'autres types potentiels dans le texte
    potential_types = re.findall(r'\b([A-Z][a-z]+(?:_[A-Z][a-z]+)*)\b', text)
    for pot_type in potential_types:
        if pot_type not in results:
            found_values = set()
            for gen_pattern in generic_patterns:
                pattern = gen_pattern.format(pot_type)
                matches = re.finditer(pattern, text, re.IGNORECASE)
                for match in matches:
                    value = match.group(1).strip()
                    if value and len(value) <= 100:
                        found_values.add(value)
            if found_values:
                results[pot_type] = list(found_values)

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
    """Filtre fort par type pour éviter le bruit + déduplication canonique."""

    def norm(s: str) -> str:
        s = re.sub(r'\s+', ' ', (s or '').strip())
        # Insérer un espace entre le nombre et l'unité si manquant (ex: 500mg -> 500 mg)
        s = re.sub(r'(?i)\b([0-9]+(?:[.,][0-9]+)?)(mg|g|ml|l|µg|mcg|%|ui)\b', r'\1 \2', s)
        return s

    seen = set()
    keep = []

    if key.lower() in ('dosage', 'strength'):
        # N'accepter que "nombre + unité" (optionnellement avec /ml, /l, /g)
        strict_rx = re.compile(r'(?i)^[0-9]+(?:[.,][0-9]+)?\s*(?:mg|g|ml|l|µg|mcg|%|ui|iu)(?:\s*/\s*(?:ml|l|g))?$')
        for v in values or []:
            vv = norm(v)
            # Si la valeur contient du texte supplémentaire, extraire seulement la partie "nombre + unité"
            m = re.search(r'(?i)([0-9]+(?:[.,][0-9]+)?\s*(?:mg|g|ml|l|µg|mcg|%|ui|iu)(?:\s*/\s*(?:ml|l|g))?)', vv)
            if m:
                vv = norm(m.group(1))
            if strict_rx.match(vv):
                k = vv.lower()
                if k not in seen:
                    seen.add(k);
                    keep.append(vv)
        return keep

    # Nettoyages spécifiques pour éviter les segments parasites
    # Product / Substance Active: couper à la première conjonction forte ou virgule
    if key.lower() in ('product', 'invented name', 'substance active', 'substance_active', 'active ingredient'):
        cut_rx = re.compile(r'^(.*?)(?:\s+(?:et|and)\b|,|;|\.|$)', re.IGNORECASE)
        for v in values or []:
            vv = norm(v)
            m = cut_rx.match(vv)
            if m:
                vv = m.group(1).strip()
            # retirer un éventuel préfixe "est/est de/is/contains" mal capturé
            vv = re.sub(r'(?i)^(?:le\s+produit\s+est|the\s+product\s+is|est|est de|is|contains)\s+', '', vv).strip()
            # éviter d'attraper "produits de dégradation" → demander une majuscule initiale
            if not re.match(r'^(?-i:[A-Z]).*', vv):
                continue
            # filtrer les tokens courts
            if 1 < len(vv) <= 80:
                k = vv.lower()
                if k and k not in seen:
                    seen.add(k);
                    keep.append(vv)
        return keep

    # pour les autres, on enlève les fragments trop courts / mots vides
    stop = {'de', 'du', 'des', 'et', 'la', 'le', 'les', 'à', 'au', 'aux', 'pour', 'sur', 'dans', 'par', 'avec'}
    for v in values or []:
        vv = norm(v)
        # couper à ; . fin de phrase pour éviter de longues séquences
        vv = re.split(r'[;\.]', vv)[0].strip()
        if 2 < len(vv) <= 80 and vv.lower() not in stop:
            k = vv.lower()
            if k not in seen:
                seen.add(k);
                keep.append(vv)
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
    """Construit une map foldée -> clé canonique, avec synonymes courants."""
    syn: dict[str, str] = {}
    existing_keys = existing_keys or []

    # D'abord, les clés existantes elles-mêmes
    for ek in existing_keys:
        syn[_fold_key(ek)] = ek

    # Ensuite, lier des synonymes connus SEULEMENT si la clé canonique est présente
    def bind(canon: str, variants: list[str]):
        if canon in existing_keys:
            syn[_fold_key(canon)] = canon
            for v in variants:
                syn[_fold_key(v)] = canon

    bind('Invented Name', ['product', 'product name', 'nom du produit', 'nom commercial', 'invented name'])
    bind('Strength', ['dosage', 'posologie', 'concentration', 'teneur', 'strength'])
    # Supporter plusieurs variantes de clés canoniques si elles existent réellement dans le JSON
    for variant in ['Pharmaceutical Form', 'Form']:
        bind(variant, ['form', 'forme', 'presentation', 'pharmaceutical form', 'forme pharmaceutique'])
    for variant in ['Route Of Administration', 'Route', 'Voie']:
        bind(variant, ['route', 'voie', "voie d administration", 'route of administration', "voie d’administration",
                       'administration route'])
    for variant in ['Immediate Packaging', 'Packaging', 'Emballage']:
        bind(variant, ['packaging', 'emballage', 'immediate packaging', 'conditionnement'])
    for variant in ['Pack Size', 'Packsize', 'Pack']:
        bind(variant, ['pack size', 'taille du pack', 'taille de pack', 'taille de boîte', 'boîte'])
    for variant in ['Ma Number', 'AMM Number', 'Authorization Number']:
        bind(variant,
             ['ma number', 'numero amm', 'numéro amm', 'authorization number', 'marketing authorization number', 'amm'])
    for variant in ['Site', 'Manufacturing Site']:
        bind(variant, ['manufacturing site', 'site', 'usine', 'fabricant'])
    for variant in ['Country', 'Pays']:
        bind(variant, ['pays', 'country'])
    for variant in ['Substance Active', 'Substance_Active', 'Active Ingredient']:
        bind(variant, ['substance active', 'principe actif', 'active ingredient'])

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

    # Types d'annotations disponibles
    annotation_types = AnnotationType.objects.all().order_by('display_name')

    # Annotations existantes pour la page courante
    existing_annotations = current_page.annotations.all() if current_page else []

    context = {
        'document': document,
        'pages': pages,
        'current_page': current_page,
        'annotation_types': AnnotationType.objects.all(),
        'existing_annotations': existing_annotations,
        'total_pages': document.total_pages
    }

    return render(request, 'expert/annotate_document.html', context)


@expert_required
@csrf_exempt
def expert_ai_annotate_page_groq(request, page_id):
    """Annotation automatique avec Groq pour Expert - copie de rawdocs.views.ai_annotate_page_groq"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        page = get_object_or_404(DocumentPage, id=page_id)

        # Initialiser le système Groq
        groq_annotator = GroqAnnotator()

        # Créer les données de page
        page_data = {
            'page_num': page.page_number,
            'text': page.text_content,
            'char_count': len(page.text_content)
        }

        # Extraire les entités avec Groq
        entities = groq_annotator.annotate_page_with_groq(page_data)

        # Sauvegarder les annotations
        saved_annotations = []
        for entity in entities:
            # Créer ou récupérer le type d'annotation
            annotation_type, created = AnnotationType.objects.get_or_create(
                name=entity['type'],
                defaults={
                    'display_name': entity['type'].replace('_', ' ').title(),
                    'color': '#3b82f6',
                    'description': f"Expert AI type: {entity['type']}"
                }
            )

            # Créer l'annotation (pré-validée par l'expert)
            annotation = Annotation.objects.create(
                page=page,
                selected_text=entity['text'],
                annotation_type=annotation_type,
                start_pos=entity.get('start_pos', 0),
                end_pos=entity.get('end_pos', len(entity['text'])),
                validation_status='expert_created',
                validated_by=request.user,
                validated_at=timezone.now(),
                created_by=request.user,
                source='expert_ai'
            )

            saved_annotations.append({
                'id': annotation.id,
                'text': annotation.selected_text,
                'type': annotation.annotation_type.display_name,
                'start_pos': annotation.start_pos,
                'end_pos': annotation.end_pos
            })

        return JsonResponse({
            'success': True,
            'annotations': saved_annotations,
            'message': f'{len(saved_annotations)} annotations créées automatiquement'
        })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@expert_required
@csrf_exempt
def expert_save_manual_annotation(request):
    """Sauvegarde d'annotation manuelle pour Expert - copie de rawdocs.views.save_manual_annotation"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        data = json.loads(request.body)
        page_id = data.get('page_id')
        selected_text = data.get('selected_text')
        entity_type = data.get('entity_type')
        if not entity_type:
            return JsonResponse({'success': False, 'error': 'entity_type is required'})
        start_pos = data.get('start_pos', 0)
        end_pos = data.get('end_pos', 0)

        page = get_object_or_404(DocumentPage, id=page_id)

        # Créer ou récupérer le type d'annotation
        annotation_type, created = AnnotationType.objects.get_or_create(
            name=entity_type,
            defaults={
                'display_name': entity_type.replace('_', ' ').title(),
                'color': '#3b82f6',
                'description': f"Expert manual type: {entity_type}"
            }
        )

        # Créer l'annotation (pré-validée par l'expert)
        annotation = Annotation.objects.create(
            page=page,
            selected_text=selected_text,
            annotation_type=annotation_type,
            start_pos=start_pos,
            end_pos=end_pos,
            validation_status='expert_created',
            validated_by=request.user,
            validated_at=timezone.now(),
            created_by=request.user,
            source='expert_manual'
        )

        # LOG ACTION
        log_expert_action(
            user=request.user,
            action='annotation_created',
            annotation=annotation,
            reason=f"Manual annotation created by expert in page {page.page_number}"
        )

        # Mise à jour automatique des JSON après création
        try:
            # Récupérer les annotations de la page
            annotations = page.annotations.all().select_related('annotation_type').order_by('start_pos')

            # Construire entities -> [valeurs]
            from rawdocs.views import _build_entities_map, generate_entities_based_page_summary
            entities = _build_entities_map(annotations, use_display_name=True)

            # JSON minimaliste pour la page
            page_json = {
                'document': {
                    'id': str(page.document.id),
                    'title': page.document.title,
                    'doc_type': getattr(page.document, 'doc_type', None),
                    'source': getattr(page.document, 'source', None),
                },
                'page': {
                    'number': page.page_number,
                    'annotations_count': annotations.count(),
                },
                'entities': entities,
                'generated_at': datetime.utcnow().isoformat() + 'Z',
            }

            # Mise à jour du JSON de la page
            page.annotations_json = page_json
            page.save(update_fields=['annotations_json'])

            # Mise à jour du JSON du document
            all_annotations = Annotation.objects.filter(
                page__document=page.document
            ).select_related('annotation_type', 'page').order_by('page__page_number', 'start_pos')

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

            print(f"✅ JSON mis à jour pour la page {page.page_number} et le document")

        except Exception as e:
            print(f"❌ Erreur lors de la mise à jour du JSON: {str(e)}")

        return JsonResponse({
            'success': True,
            'annotation_id': annotation.id,
            'message': 'Annotation sauvegardée avec succès et JSON mis à jour'
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
    """Suppression d'annotation pour Expert - copie de rawdocs.views.delete_annotation"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        annotation = get_object_or_404(Annotation, id=annotation_id)

        # LOG ACTION BEFORE DELETION
        log_expert_action(
            user=request.user,
            action='annotation_deleted',
            annotation=annotation,
            reason=f"Manual deletion by expert. Annotation was: {annotation.validation_status}"
        )

        # Sauvegarder les références avant la suppression
        page = annotation.page
        document = page.document

        # Supprimer l'annotation
        annotation.delete()

        try:
            # Mise à jour du JSON de la page
            page_annotations = page.annotations.filter(
                validation_status__in=['validated', 'expert_created']
            ).select_related('annotation_type').order_by('start_pos')

            from rawdocs.views import _build_entities_map, generate_entities_based_page_summary
            page_entities = _build_entities_map(page_annotations, use_display_name=True)

            # Filtrer les entités non pertinentes
            filtered_entities = {}
            for entity_type, values in page_entities.items():
                if values and any(value.strip() for value in values):
                    filtered_entities[entity_type] = [v for v in values if v.strip()]

            page_json = {
                'document': {
                    'id': str(document.id),
                    'title': document.title,
                    'doc_type': getattr(document, 'doc_type', None),
                    'source': getattr(document, 'source', None),
                },
                'page': {
                    'number': page.page_number,
                    'annotations_count': len(page_annotations),
                    'validated_count': len(page_annotations),
                },
                'entities': filtered_entities,
                'generated_at': datetime.utcnow().isoformat() + 'Z',
            }

            page.annotations_json = page_json
            page.save(update_fields=['annotations_json'])

            # Mise à jour du JSON du document
            all_annotations = Annotation.objects.filter(
                page__document=document,
                validation_status__in=['validated', 'expert_created']  # Ne prendre que les annotations validées
            ).select_related('annotation_type', 'page').order_by('page__page_number', 'start_pos')

            document_entities = _build_entities_map(all_annotations, use_display_name=True)

            # Filtrer les entités pour ne garder que celles qui sont pertinentes
            filtered_entities = {}
            for entity_type, values in document_entities.items():
                if values and any(value.strip() for value in values):
                    filtered_entities[entity_type] = [v for v in values if v.strip()]

            document_json = {
                'document': {
                    'id': str(document.id),
                    'title': document.title,
                    'doc_type': getattr(document, 'doc_type', None),
                    'source': getattr(document, 'source', None),
                    'total_pages': document.total_pages,
                    'total_annotations': len(all_annotations),
                },
                'entities': filtered_entities,  # Utiliser les entités filtrées
                'generated_at': datetime.utcnow().isoformat() + 'Z',
            }

            document.global_annotations_json = document_json
            document.save(update_fields=['global_annotations_json'])

            print(f"✅ JSON mis à jour après suppression pour la page {page.page_number} et le document")

        except Exception as e:
            print(f"❌ Erreur lors de la mise à jour du JSON après suppression: {str(e)}")

        return JsonResponse({
            'success': True,
            'message': 'Annotation supprimée avec succès et JSON mis à jour'
        })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


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
    """Génération du JSON et résumé pour une page - Expert - copie de rawdocs.views.generate_page_annotation_summary"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        page = get_object_or_404(DocumentPage, id=page_id)

        # Récupérer les annotations de la page
        annotations = page.annotations.all().select_related('annotation_type').order_by('start_pos')

        # Construire entities -> [valeurs] (utiliser la fonction de rawdocs)
        from rawdocs.views import _build_entities_map, generate_entities_based_page_summary
        entities = _build_entities_map(annotations, use_display_name=True)

        # JSON minimaliste
        page_json = {
            'document': {
                'id': str(page.document.id),
                'title': page.document.title,
                'doc_type': getattr(page.document, 'doc_type', None),
                'source': getattr(page.document, 'source', None),
            },
            'page': {
                'number': page.page_number,
                'annotations_count': annotations.count(),
            },
            'entities': entities,
            'generated_at': datetime.utcnow().isoformat() + 'Z',
        }

        # Résumé à partir des seules entités/valeurs
        summary = generate_entities_based_page_summary(
            entities=entities,
            page_number=page.page_number,
            document_title=page.document.title
        )

        # Sauvegarde
        page.annotations_json = page_json
        page.annotations_summary = summary
        page.annotations_summary_generated_at = timezone.now()
        page.save(update_fields=['annotations_json', 'annotations_summary', 'annotations_summary_generated_at'])

        return JsonResponse({
            'success': True,
            'page_json': page_json,
            'summary': summary,
            'message': f'JSON et résumé générés pour la page {page.page_number}'
        })
    except Exception as e:
        print(f"❌ Erreur génération résumé page {page_id}: {e}")
        return JsonResponse({'error': f'Erreur lors de la génération: {str(e)}'}, status=500)


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
    
