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

        # Documents ready for expert review with annotator info
        ready_documents = RawDocument.objects.filter(
            is_ready_for_expert=True
        ).select_related('owner').prefetch_related('pages__annotations')

        # Count pending annotations across all documents
        pending_annotations = Annotation.objects.filter(
            validation_status='pending'
        ).count()

        # Enrich documents with annotation stats
        enriched_documents = []
        for doc in ready_documents.order_by('-expert_ready_at')[:5]:
            doc.annotator = doc.owner  # Add annotator field
            doc.total_annotations = sum(page.annotations.count() for page in doc.pages.all())
            doc.pending_annotations = sum(
                page.annotations.filter(validation_status='pending').count() for page in doc.pages.all())
            doc.validated_annotations = sum(
                page.annotations.filter(validation_status='validated').count() for page in doc.pages.all())

            # Find the latest annotation date in an optimized way
            latest_annotation_date = Annotation.objects.filter(
                page__document=doc
            ).aggregate(
                latest_date=Max('created_at')
            )['latest_date']

            # Use the latest annotation date or a fallback date
            if latest_annotation_date:
                doc.updated_at = latest_annotation_date
            elif hasattr(doc, 'expert_ready_at') and doc.expert_ready_at:
                doc.updated_at = doc.expert_ready_at
            else:
                doc.updated_at = doc.created_at

            enriched_documents.append(doc)

        context.update({
            'ready_documents_count': ready_documents.count(),
            'pending_annotations': pending_annotations,
            'recent_documents': enriched_documents,
        })
        return context


@method_decorator(expert_required, name='dispatch')
class DocumentReviewView(LoginRequiredMixin, TemplateView):
    template_name = 'expert/document_review.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        document_id = self.kwargs['document_id']
        document = get_object_or_404(RawDocument, id=document_id)

        # Get pages with their annotations
        pages = document.pages.prefetch_related(
            'annotations__annotation_type'
        ).order_by('page_number')

        # Pagination by page
        paginator = Paginator(pages, 1)
        page_number = self.request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)

        current_page = page_obj.object_list[0] if page_obj.object_list else None

        # Get all annotation types for expert interface
        annotation_types = AnnotationType.objects.all().order_by('display_name')
        
        # Get existing annotations for current page
        existing_annotations = current_page.annotations.all() if current_page else []

        context.update({
            'document': document,
            'page_obj': page_obj,
            'current_page': current_page,
            'annotation_types': annotation_types,
            'existing_annotations': existing_annotations,
            'total_pages': document.total_pages,
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
                start_pos=data.get('start_offset', 0),
                end_pos=data.get('end_offset', len(text)),
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

# expert/views.py - Corriger la fonction validate_document

@expert_required
def validate_document(request, document_id):
    """Validate entire document and create product if it's a manufacturer document"""
    if request.method == 'POST':
        try:
            document = get_object_or_404(RawDocument, id=document_id)

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


@expert_required
def expert_annotate_document(request, doc_id):
    """Interface d'annotation pour Expert - copie de rawdocs.views.annotate_document"""
    document = get_object_or_404(RawDocument, id=doc_id, is_validated=True)
    
    # Pagination par page
    pages = document.pages.order_by('page_number')
    paginator = Paginator(pages, 1)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    current_page = page_obj.object_list[0] if page_obj.object_list else None
    
    # Types d'annotations disponibles
    annotation_types = AnnotationType.objects.all().order_by('display_name')
    
    # Annotations existantes pour la page courante
    existing_annotations = current_page.annotations.all() if current_page else []
    
    context = {
        'document': document,
        'page_obj': page_obj,
        'current_page': current_page,
        'annotation_types': annotation_types,
        'existing_annotations': existing_annotations,
        'total_pages': document.total_pages,
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
        annotations = page.annotations.select_related('annotation_type').order_by('start_pos')
        
        annotations_data = []
        for annotation in annotations:
            annotations_data.append({
                'id': annotation.id,
                'text': annotation.selected_text,
                'type': annotation.annotation_type.display_name,
                'type_name': annotation.annotation_type.name,
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
            document_title=document.title,
            total_pages=document.total_pages
        )

        # Sauvegarde
        document.global_annotations_json = document_json
        document.global_annotations_summary = summary
        document.global_annotations_summary_generated_at = timezone.now()
        document.save(update_fields=['global_annotations_json', 'global_annotations_summary', 'global_annotations_summary_generated_at'])

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
    """Visualisation du JSON et résumé d'une page - Expert - copie de rawdocs.views.view_page_annotation_json"""
    try:
        page = get_object_or_404(DocumentPage, id=page_id)

        # Si pas encore généré, le générer
        if not hasattr(page, 'annotations_json') or not page.annotations_json:
            # Déclencher la génération
            from django.test import RequestFactory
            factory = RequestFactory()
            fake_request = factory.post(f'/expert/annotation/page/{page_id}/generate-summary/')
            fake_request.user = request.user
            expert_generate_page_annotation_summary(fake_request, page_id)
            page.refresh_from_db()

        context = {
            'page': page,
            'document': page.document,
            'annotations_json': page.annotations_json if hasattr(page, 'annotations_json') else None,
            'annotations_summary': page.annotations_summary if hasattr(page, 'annotations_summary') else None,
            'total_annotations': page.annotations.count()
        }

        return render(request, 'expert/view_page_annotation_json.html', context)

    except Exception as e:
        messages.error(request, f"Erreur: {str(e)}")
        return redirect('expert:annotation_dashboard')


@expert_required
def expert_view_document_annotation_json(request, doc_id):
    """Visualisation du JSON et résumé global d'un document - Expert - copie de rawdocs.views.view_document_annotation_json"""
    try:
        document = get_object_or_404(RawDocument, id=doc_id, is_validated=True)

        # Si pas encore généré, le générer
        if not hasattr(document, 'global_annotations_json') or not document.global_annotations_json:
            # Déclencher la génération
            from django.test import RequestFactory
            factory = RequestFactory()
            fake_request = factory.post(f'/expert/annotation/document/{doc_id}/generate-summary/')
            fake_request.user = request.user
            expert_generate_document_annotation_summary(fake_request, doc_id)
            document.refresh_from_db()

        # Statistiques
        total_annotations = sum(page.annotations.count() for page in document.pages.all())
        annotated_pages = document.pages.filter(annotations__isnull=False).distinct().count()

        context = {
            'document': document,
            'global_annotations_json': document.global_annotations_json if hasattr(document, 'global_annotations_json') else None,
            'global_annotations_summary': document.global_annotations_summary if hasattr(document, 'global_annotations_summary') else None,
            'total_annotations': total_annotations,
            'annotated_pages': annotated_pages,
            'total_pages': document.total_pages
        }

        return render(request, 'expert/view_document_annotation_json.html', context)

    except Exception as e:
        messages.error(request, f"Erreur: {str(e)}")
        return redirect('expert:annotation_dashboard')