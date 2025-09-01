# rawdocs/views.py
from django.utils import timezone  # AJOUT pour corriger le timezone warning
import time
from .groq_annotation_system import GroqAnnotator
import os
import json
import requests
from datetime import datetime
from PyPDF2 import PdfReader
from client.products.models import Product
from django.shortcuts import render, redirect, get_object_or_404
from django.core.files.base import ContentFile
from django.http import JsonResponse
from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User, Group
from django.core.paginator import Paginator
from django.db import transaction, models
from django import forms
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth import views as auth_views
from django.http import HttpResponse
from django.views.decorators.http import require_POST
from .metadata_rlhf_learning import MetadataRLHFLearner
from datetime import timezone as dt_timezone
from django.conf import settings
from pymongo import MongoClient
from django.utils import timezone


from .models import (
    RawDocument, MetadataLog,
    DocumentPage, AnnotationType,
    Annotation, AnnotationSession,
    AILearningMetrics, AnnotationFeedback,
    GlobalSummaryEditHistory
)
from .utils import extract_metadonnees, extract_full_text
from .annotation_utils import extract_pages_from_pdf
from .rlhf_learning import RLHFGroqAnnotator
from .table_image_extractor import TableImageExtractor


# --- Mongo client (réutilisé) ---
try:
    _mongo_client = MongoClient(settings.MONGO_URI, serverSelectionTimeoutMS=5000)
    _mongo_coll   = _mongo_client[settings.MONGO_DB][settings.MONGO_COLLECTION]
    print("✅ Mongo prêt :", settings.MONGO_URI, settings.MONGO_DB, settings.MONGO_COLLECTION)
except Exception as e:
    _mongo_client = None
    _mongo_coll   = None
    print("⚠️ Mongo init KO:", e)


# ——— Forms ——————————————————————————————————————————

class UploadForm(forms.Form):
    pdf_url = forms.URLField(
        required=False,
        widget=forms.URLInput(attrs={
            'placeholder': 'https://…',
            'class': 'upload-cell__input'
        })
    )
    pdf_file = forms.FileField(required=False)


class RegisterForm(UserCreationForm):
    email = forms.EmailField(required=True)
    role = forms.ChoiceField(choices=[
        ("Metadonneur", "Métadonneur"),
        ("Annotateur", "Annotateur"),
        ("Expert", "Expert"),
        ("Client", "Client"), 
        ("DevMetier",   "Dev métier"), 
    ], label="Profil")

    class Meta:
        model = User
        fields = ("username", "email", "role", "password1", "password2")

    def save(self, commit=True):
        user = super().save(commit)
        user.email = self.cleaned_data["email"]
        group = Group.objects.get_or_create(name=self.cleaned_data["role"])[0]  # CHANGE THIS LINE
        user.groups.add(group)
        if commit:
            user.save()
        return user


class MetadataEditForm(forms.Form):
    title = forms.CharField(required=False)
    type = forms.CharField(required=False)
    # Use CharField to accept free-text dates coming from LLM (e.g., "23 January 2025")
    publication_date = forms.CharField(required=False)
    version = forms.CharField(required=False)
    source = forms.CharField(required=False)
    context = forms.CharField(required=False)
    country = forms.CharField(required=False)
    language = forms.CharField(required=False)
    url_source = forms.URLField(required=False)


# ——— Permissions ——————————————————————————————————————

def is_metadonneur(user):
    return user.groups.filter(name="Metadonneur").exists()


def is_annotateur(user):
    return user.groups.filter(name="Annotateur").exists()


def is_expert(user):
    return user.groups.filter(name="Expert").exists()

def is_dev_metier(user):                              
    return user.groups.filter(name="DevMetier").exists()    


# ——— Authentication ————————————————————————————————————

from django.urls import reverse
from django.conf import settings


class CustomLoginView(auth_views.LoginView):
    template_name = 'registration/login.html'

    def get_success_url(self):
        user = self.request.user
        if user.groups.filter(name='Client').exists():
            return '/client/'  # We'll create this
        if user.groups.filter(name='Expert').exists():
            return reverse('expert:dashboard')
        if user.groups.filter(name='Annotateur').exists():
            return reverse('rawdocs:annotation_dashboard')
        if user.groups.filter(name='Metadonneur').exists():
            return reverse('rawdocs:dashboard')
        if user.groups.filter(name='DevMetier').exists():
            return reverse('rawdocs:dev_metier_dashboard')
        return '/'


def register(request):
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            uname = form.cleaned_data['username']
            pwd = form.cleaned_data['password1']
            user = authenticate(username=uname, password=pwd)
            login(request, user)

            # Redirect to proper dashboard based on role
            grp = form.cleaned_data['role']
            if grp == "Metadonneur":
                return redirect('rawdocs:dashboard')  # Metadonneur dashboard
            elif grp == "Annotateur":
                return redirect('rawdocs:annotation_dashboard')  # Annotateur dashboard
            elif grp == "Expert":
                return redirect('expert:dashboard')  # Expert dashboard
            elif grp == "Client":
                return redirect('/client/')  # Client dashboard
            elif   grp == "DevMetier":   
                return redirect('rawdocs:dev_metier_dashboard')  # dev metier dashboard
            else:
                return redirect('rawdocs:dashboard')  # Fallback
    else:
        form = RegisterForm()
    return render(request, 'registration/register.html', {'form': form})


# ——— Métadonneur Views ——————————————————————————————

@login_required(login_url='rawdocs:login')
@user_passes_test(is_metadonneur)
def dashboard_view(request):
    docs = RawDocument.objects.filter(owner=request.user).order_by('-created_at')
    # KPI calculés pour métadonneur (plus réalistes)
    total_imported = docs.count()
    validated_count = docs.filter(is_validated=True).count()
    pending_validation_count = docs.filter(is_validated=False).count()

    context = {
        'documents': docs,
        'total_scrapped': total_imported,
        'total_planned': 150,  # Valeur fixe plus cohérente
        'total_completed': validated_count,
        'in_progress': pending_validation_count,
        'pending_validation_count': pending_validation_count,
        'total_imported': total_imported,
        'total_in_reextraction': total_imported,
        # Placeholder charts
        'pie_data': json.dumps([15, 8, 12, 5, 3]),
        'bar_data': json.dumps([150, total_imported, validated_count, pending_validation_count]),
    }
    return render(request, 'rawdocs/dashboard.html', context)


@login_required(login_url='rawdocs:login')
@user_passes_test(is_metadonneur)
def upload_pdf(request):
    form = UploadForm(request.POST or None, request.FILES or None)
    context = {'form': form}

    # Handle metadata editing form submission
    if request.method == 'POST' and request.POST.get('edit_metadata'):
        doc_id = request.POST.get('doc_id')
        rd = get_object_or_404(RawDocument, id=doc_id, owner=request.user)
        edit_form = MetadataEditForm(request.POST)
        
        # Get ORIGINAL AI extracted metadata (what AI first extracted)
        ai_metadata = {}
        standard_fields = ['title', 'doc_type', 'publication_date', 'version', 'source', 'context', 'country', 'language', 'url_source']
        
        # Get ORIGINAL AI extracted metadata (what was first extracted by LLM)
        ai_metadata = rd.original_ai_metadata or {}

        if edit_form.is_valid():
            # Collect human corrections
            human_metadata = {}
            changes_made = False
            
            field_mapping = {
                'title': 'title',
                'type': 'doc_type', 
                'publication_date': 'publication_date',
                'version': 'version',
                'source': 'source',
                'context': 'context',
                'country': 'country',
                'language': 'language',
                'url_source': 'url_source'
            }
            
            for form_field, model_field in field_mapping.items():
                new_value = edit_form.cleaned_data.get(form_field, '') or ''
                old_value = getattr(rd, model_field, '') or ''
                human_metadata[form_field] = new_value
                
                if str(old_value) != str(new_value):
                    changes_made = True
                    MetadataLog.objects.create(
                        document=rd, field_name=form_field,
                        old_value=old_value, new_value=new_value,
                        modified_by=request.user
                    )
                    setattr(rd, model_field, new_value)
            
            if changes_made:
                rd.save()
                
                # Process RLHF Learning ONLY if changes were made
                from .metadata_rlhf_learning import MetadataRLHFLearner
                learner = MetadataRLHFLearner()
                feedback_result = learner.process_metadata_feedback(rd, ai_metadata, human_metadata, request.user)

                # Create detailed message with learning stats
                corrections = feedback_result['corrections_summary']
                score = int(feedback_result['feedback_score'] * 100)
                correct_count = len(corrections.get('kept_correct', []))
                wrong_count = len(corrections.get('corrected_fields', [])) + len(corrections.get('removed_fields', []))
                missed_count = len(corrections.get('missed_fields', []))

                # Show success message with learning stats
                learning_message = f"✅ Métadonnées sauvegardées! 🧠 IA Score: {score}% | ✅ Corrects: {correct_count} | ❌ Erreurs: {wrong_count} | 📝 Manqués: {missed_count}"
                messages.success(request, learning_message)

                # Pass learning data to template
                context['learning_feedback'] = {
                    'score': score,
                    'correct': correct_count,
                    'wrong': wrong_count,
                    'missed': missed_count,
                    'show': True,
                    'feedback_result': feedback_result
                }
            else:
                messages.info(request, "Aucune modification détectée.")
  

        metadata = extract_metadonnees(rd.file.path, rd.url or "")
        text = extract_full_text(rd.file.path)
        
        initial_data = {
            'title': rd.title or '',
            'type': rd.doc_type or '', 
            'publication_date': rd.publication_date or '',
            'version': rd.version or '',
            'source': rd.source or '',
            'context': rd.context or '',
            'country': rd.country or '',
            'language': rd.language or '',
            'url_source': rd.url_source or (rd.url or ''),
        }
        edit_form = MetadataEditForm(initial=initial_data)
        
        context.update({
            'doc': rd,
            'metadata': metadata,
            'extracted_text': text,
            'edit_form': edit_form,
            'logs': MetadataLog.objects.filter(document=rd).order_by('-modified_at')
        })
        
        return render(request, 'rawdocs/upload.html', context)

    # Handle file upload
    elif request.method == 'POST' and form.is_valid():
        try:
            # Priority to local file
            if form.cleaned_data.get('pdf_file'):
                f = form.cleaned_data['pdf_file']
                rd = RawDocument(owner=request.user)
                rd.file.save(f.name, f)
            else:
                url = form.cleaned_data['pdf_url']
                resp = requests.get(url, timeout=30)
                resp.raise_for_status()
                ts = datetime.now().strftime('%Y%m%d_%H%M%S')
                fn = os.path.basename(url) or 'document.pdf'
                rd = RawDocument(url=url, owner=request.user)
                rd.file.save(os.path.join(ts, fn), ContentFile(resp.content))

            rd.save()
            metadata = extract_metadonnees(rd.file.path, rd.url or "") or {}
            text = extract_full_text(rd.file.path)
            
            # Save extracted metadata to the model
            if metadata:
                rd.original_ai_metadata = metadata
                rd.title = metadata.get('title', '')
                rd.doc_type = metadata.get('type', '')
                rd.publication_date = metadata.get('publication_date', '')
                rd.version = metadata.get('version', '')
                rd.source = metadata.get('source', '')
                rd.context = metadata.get('context', '')
                rd.country = metadata.get('country', '')
                rd.language = metadata.get('language', '')
                rd.url_source = metadata.get('url_source', rd.url or '')
                rd.save()
                
                print(f"✅ Métadonnées LLM sauvegardées pour le document {rd.pk}")

            # Create form for editing with initial data
            initial_data = {
                'title': rd.title or '',
                'type': rd.doc_type or '', 
                'publication_date': rd.publication_date or '',
                'version': rd.version or '',
                'source': rd.source or '',
                'context': rd.context or '',
                'country': rd.country or '',
                'language': rd.language or '',
                'url_source': rd.url_source or (rd.url or ''),
            }
            edit_form = MetadataEditForm(initial=initial_data)

            context.update({
                'doc': rd,
                'metadata': metadata,
                'extracted_text': text,
                'edit_form': edit_form,
                'logs': MetadataLog.objects.filter(document=rd).order_by('-modified_at')
            })
            messages.success(request, "Document importé avec succès!")

        except Exception as e:
            messages.error(request, f"Erreur lors de l'import: {str(e)}")

    return render(request, 'rawdocs/upload.html', context)


@login_required(login_url='rawdocs:login')
@user_passes_test(is_metadonneur)
def document_list(request):
    docs = RawDocument.objects.filter(owner=request.user).order_by('-created_at')
    for d in docs:
        d.basename = os.path.basename(d.file.name)
    return render(request, 'rawdocs/document_list.html', {'documents': docs})


@login_required(login_url='rawdocs:login')
@user_passes_test(is_metadonneur)
def document_metadata(request, doc_id):
    rd = get_object_or_404(RawDocument, id=doc_id, owner=request.user)
    return JsonResponse(extract_metadonnees(rd.file.path, rd.url or ""))


@login_required(login_url='rawdocs:login')
@user_passes_test(is_metadonneur)
def delete_document(request, doc_id):
    rd = get_object_or_404(RawDocument, id=doc_id, owner=request.user)
    if request.method == 'POST':
        rd.delete()
        messages.success(request, "Document supprimé avec succès")
    return redirect('rawdocs:document_list')


@login_required(login_url='rawdocs:login')
@user_passes_test(is_metadonneur)
def edit_metadata(request, doc_id):
    rd = get_object_or_404(RawDocument, id=doc_id, owner=request.user)
    metadata = extract_metadonnees(rd.file.path, rd.url or "")

    if request.method == 'POST':
        form = MetadataEditForm(request.POST)        
        if form.is_valid():
            # Handle standard fields (your existing code)
            standard_fields = ['title', 'type', 'publication_date', 'version', 'source', 'context', 'country', 'language', 'url_source']
            
            for field_name in standard_fields:
                if field_name in form.cleaned_data:
                    new_value = form.cleaned_data[field_name]
                    old_value = metadata.get(field_name)
                    if str(old_value) != str(new_value):
                        MetadataLog.objects.create(
                            document=rd, field_name=field_name,
                            old_value=old_value, new_value=new_value,
                            modified_by=request.user
                        )
                        metadata[field_name] = new_value

            # Persist updates to the RawDocument model so changes are visible everywhere (Library, details, etc.)
            rd.title = form.cleaned_data.get('title', rd.title) or ''
            rd.doc_type = form.cleaned_data.get('type', rd.doc_type) or ''
            rd.publication_date = form.cleaned_data.get('publication_date', rd.publication_date) or ''
            rd.version = form.cleaned_data.get('version', rd.version) or ''
            rd.source = form.cleaned_data.get('source', rd.source) or ''
            rd.context = form.cleaned_data.get('context', rd.context) or ''
            rd.country = form.cleaned_data.get('country', rd.country) or ''
            rd.language = form.cleaned_data.get('language', rd.language) or ''
            rd.url_source = form.cleaned_data.get('url_source', rd.url_source) or (rd.url or '')
            rd.save()
            
            from .models import CustomField, CustomFieldValue
            for key, value in request.POST.items():
                if key.startswith('custom_'):
                    field_name = key.replace('custom_', '')
                    try:
                        custom_field = CustomField.objects.get(name=field_name)
                        custom_value, created = CustomFieldValue.objects.get_or_create(
                            document=rd,
                            field=custom_field,
                            defaults={'value': value}
                        )
                        if not created:
                            # Log the change
                            old_val = custom_value.value
                            custom_value.value = value
                            custom_value.save()
                            
                            MetadataLog.objects.create(
                                document=rd, 
                                field_name=f"Custom: {field_name}",
                                old_value=old_val, 
                                new_value=value,
                                modified_by=request.user
                            )
                    except CustomField.DoesNotExist:
                        pass
            
            
            return redirect('rawdocs:document_list')
    else:
        initial_data = {
            'title': rd.title or '',
            'type': rd.doc_type or '',
            'publication_date': rd.publication_date or '',
            'version': rd.version or '',
            'source': rd.source or '',
            'context': rd.context or '',
            'country': rd.country or '',
            'language': rd.language or '',
            'url_source': rd.url_source or (rd.url or ''),
        }
        form = MetadataEditForm(initial=initial_data)

    logs = MetadataLog.objects.filter(document=rd).order_by('-modified_at')
    
    # Load existing custom fields fo this document ONLY
    from .models import CustomField, CustomFieldValue
    custom_fields_data = []
    for custom_value in CustomFieldValue.objects.filter(document=rd):
        custom_fields_data.append({
            'name': custom_value.field.name,
            'type': custom_value.field.field_type,
            'value': custom_value.value
        })
    
    return render(request, 'rawdocs/edit_metadata.html', {
        'form': form,
        'metadata': metadata,
        'doc': rd,
        'logs': logs,
        'custom_fields_data': custom_fields_data  # ADD THIS LINE
    })

@login_required(login_url='rawdocs:login')
@user_passes_test(is_metadonneur)
def reextract_metadata(request, doc_id):
    """Relance l'extraction, écrase les champs du modèle et logue les changements."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    rd = get_object_or_404(RawDocument, id=doc_id, owner=request.user)

    try:
        new_metadata = extract_metadonnees(rd.file.path, rd.url or "") or {}

        # mapping: modèle -> clé metadata
        mapping = {
            'title': ('title',),
            'doc_type': ('type',),
            'publication_date': ('publication_date',),
            'version': ('version',),
            'source': ('source',),
            'context': ('context',),
            'country': ('country',),
            'language': ('language',),
            'url_source': ('url_source',),
        }

        # Appliquer tous les champs et logger les changements
        for model_field, meta_keys in mapping.items():
            meta_key = meta_keys[0]
            old_val = getattr(rd, model_field, '') or ''
            # Ne pas écraser par une valeur vide; écraser seulement si on a une vraie nouvelle valeur non vide
            candidate_val = new_metadata.get(meta_key, None)
            new_val = (candidate_val if candidate_val is not None else '')
            if new_val == '':
                continue
            if str(old_val) != str(new_val):
                MetadataLog.objects.create(
                    document=rd,
                    field_name=('type' if model_field == 'doc_type' else model_field),
                    old_value=old_val,
                    new_value=new_val,
                    modified_by=request.user
                )
                setattr(rd, model_field, new_val)

        rd.save()

        return JsonResponse({'success': True, 'metadata': new_metadata})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required(login_url='rawdocs:login')
@user_passes_test(is_metadonneur)
def validate_document(request, doc_id):
    document = get_object_or_404(RawDocument, id=doc_id, owner=request.user)

    if request.method == 'POST':
        if not document.pages_extracted:
            try:
                reader = PdfReader(document.file.path)
                pages_text = [page.extract_text() or "" for page in reader.pages]

                with transaction.atomic():
                    for page_num, page_text in enumerate(pages_text, 1):
                        DocumentPage.objects.create(
                            document=document,
                            page_number=page_num,
                            raw_text=page_text,
                            cleaned_text=page_text
                        )

                    document.total_pages = len(pages_text)
                    document.pages_extracted = True

                    document.is_validated = True
                    document.validated_at = datetime.now()
                    document.save()

                    messages.success(request, f"Document validé ({document.total_pages} pages)")
                    create_product_from_metadata(document)
                    return redirect('rawdocs:document_list')
            except Exception as e:
                messages.error(request, f"Erreur lors de l'extraction: {str(e)}")
                return redirect('rawdocs:document_list')

    return render(request, 'rawdocs/validate_document.html', {'document': document})


# ——— Annotateur Views ——————————————————————————————

@login_required(login_url='rawdocs:login')
@user_passes_test(is_annotateur)
def annotation_dashboard(request):
    # Base queryset: documents prêts pour annotation
    docs = RawDocument.objects.filter(
        is_validated=True,
        pages_extracted=True
    ).order_by('-validated_at')

    from django.db.models import Q, F, Count, Sum

    # Annoter la queryset avec le nombre de pages annotées par document
    docs_with_progress = docs.annotate(
        annotated_pages_count=Count('pages', filter=Q(pages__is_annotated=True))
    )

    # Pagination pour le tableau (sur la queryset annotée)
    paginator = Paginator(docs_with_progress, 10)
    page = request.GET.get('page')
    documents_page = paginator.get_page(page)

    # KPI dynamiques
    total_documents = docs_with_progress.count()
    total_pages = docs_with_progress.aggregate(total=Sum('total_pages'))['total'] or 0

    # Nombre de pages annotées (toutes docs confondues)
    total_annotated_pages = DocumentPage.objects.filter(
        document__in=docs_with_progress,
        is_annotated=True
    ).count()

    # Documents complétés: toutes les pages annotées
    completed_count = docs_with_progress.filter(
        total_pages__gt=0,
        annotated_pages_count=F('total_pages')
    ).count()

    # Documents en cours: au moins 1 page annotée mais pas toutes
    in_progress_count = docs_with_progress.filter(
        annotated_pages_count__gt=0
    ).exclude(
        annotated_pages_count=F('total_pages')
    ).count()

    to_annotate_count = max(0, total_documents - in_progress_count - completed_count)

    avg_annotated_pages_per_doc = (total_annotated_pages / total_documents) if total_documents > 0 else 0

    context = {
        'documents': documents_page,
        'total_documents': total_documents,
        'total_pages': total_pages,
        'total_annotated_pages': total_annotated_pages,
        'in_progress_count': in_progress_count,
        'completed_count': completed_count,
        'to_annotate_count': to_annotate_count,
        'avg_annotated_pages_per_doc': avg_annotated_pages_per_doc,
    }

    return render(request, 'rawdocs/annotation_dashboard.html', context)


@login_required(login_url='rawdocs:login')
@user_passes_test(is_annotateur)
def annotate_document(request, doc_id):
    document = get_object_or_404(RawDocument, id=doc_id, is_validated=True)
    pages = document.pages.all()
    pnum = int(request.GET.get('page', 1))
    page_obj = get_object_or_404(DocumentPage, document=document, page_number=pnum)

    # Build contextual annotation types (reduced/dynamic)
    used_type_ids = Annotation.objects.filter(page__document=document).values_list('annotation_type_id', flat=True).distinct()
    context_text = " ".join([document.context or '', document.doc_type or '', document.source or '']).lower()
    whitelist = set()
    if any(k in context_text for k in ['pharma','pharmacie','medicament','drug','clinical','trial','essai']):
        whitelist.update([AnnotationType.REQUIRED_DOCUMENT, AnnotationType.AUTHORITY, AnnotationType.LEGAL_REFERENCE, AnnotationType.DELAY, AnnotationType.PROCEDURE_TYPE, AnnotationType.VARIATION_CODE, AnnotationType.REQUIRED_CONDITION, AnnotationType.FILE_TYPE])
    elif any(k in context_text for k in ['regulatory','réglementaire','compliance']):
        whitelist.update([AnnotationType.REQUIRED_DOCUMENT, AnnotationType.AUTHORITY, AnnotationType.LEGAL_REFERENCE, AnnotationType.DELAY, AnnotationType.PROCEDURE_TYPE])
    elif any(k in context_text for k in ['ema','europe','eu']):
        whitelist.update([AnnotationType.AUTHORITY, AnnotationType.LEGAL_REFERENCE, AnnotationType.DELAY, AnnotationType.PROCEDURE_TYPE, AnnotationType.REQUIRED_DOCUMENT])
    elif any(k in context_text for k in ['fda','usa','united states']):
        whitelist.update([AnnotationType.AUTHORITY, AnnotationType.LEGAL_REFERENCE, AnnotationType.DELAY, AnnotationType.REQUIRED_DOCUMENT])
    else:
        whitelist.update([AnnotationType.REQUIRED_DOCUMENT, AnnotationType.AUTHORITY, AnnotationType.LEGAL_REFERENCE, AnnotationType.DELAY, AnnotationType.PROCEDURE_TYPE])

    base_qs = AnnotationType.objects.filter(name__in=list(whitelist))
    used_qs = AnnotationType.objects.filter(id__in=used_type_ids)
    annotation_types = (base_qs | used_qs).distinct().order_by('display_name')

    return render(request, 'rawdocs/annotate_document.html', {
        'document': document,
        'pages': pages,
        'current_page': page_obj,
        'annotation_types': annotation_types,
        'existing_annotations': page_obj.annotations.all().order_by('start_pos'),
        'total_pages': document.total_pages
    })


@login_required(login_url='rawdocs:login')
@user_passes_test(is_annotateur)
def save_manual_annotation(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        data = json.loads(request.body)
        page = get_object_or_404(DocumentPage, id=data['page_id'])
        atype = get_object_or_404(AnnotationType, id=data['type_id'])

        ann = Annotation.objects.create(
            page=page,
            annotation_type=atype,
            start_pos=data['start_pos'],
            end_pos=data['end_pos'],
            selected_text=data['selected_text'],
            confidence_score=100.0,
            created_by=request.user
        )

        return JsonResponse({
            'success': True,
            'annotation_id': ann.id,
            'message': 'Annotation sauvegardée'
        })
    except Exception as e:
        return JsonResponse({
            'error': str(e),
            'message': 'Erreur lors de la sauvegarde'
        }, status=500)
    

@login_required
def get_page_annotations(request, page_id):
    try:
        page = get_object_or_404(DocumentPage, id=page_id)
        annotations = page.annotations.all().select_related('annotation_type').order_by('start_pos')
        
        anns = []
        for a in annotations:
            anns.append({
                'id': a.id,
                'start_pos': a.start_pos,
                'end_pos': a.end_pos,
                'selected_text': a.selected_text,
                'type': a.annotation_type.name,
                'type_display': a.annotation_type.display_name,
                'color': a.annotation_type.color,
                'confidence': a.confidence_score,
                'reasoning': a.ai_reasoning,
                'is_validated': getattr(a, 'is_validated', False),
            })

        return JsonResponse({
            'success': True,
            'annotations': anns,
            'page_text': page.cleaned_text,
            'total_annotations': len(anns)
        })
        
    except Exception as e:
        print(f"Error loading annotations: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e),
            'annotations': [],
            'page_text': '',
            'total_annotations': 0
        })
    

@login_required
@csrf_exempt  
def delete_annotation(request, annotation_id):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        ann = get_object_or_404(Annotation, id=annotation_id)
        
        # Check permissions
        if ann.created_by != request.user and not request.user.groups.filter(name="Expert").exists():
            return JsonResponse({'error': 'Permission denied'}, status=403)

        # Store page reference before deletion
        page = ann.page
        
        # Delete the annotation
        ann.delete()
        
        # Check if page still has annotations
        remaining_annotations = page.annotations.count()
        if remaining_annotations == 0:
            page.is_annotated = False
            page.save()

        return JsonResponse({
            'success': True,
            'message': 'Annotation supprimée',
            'remaining_annotations': remaining_annotations
        })
        
    except Exception as e:
        print(f"Error deleting annotation: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
    

@login_required
@csrf_exempt
def validate_page_annotations(request, page_id):
    """Validate page annotations with RLHF learning"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        page = get_object_or_404(DocumentPage, id=page_id)

        # Get AI annotations from session or reconstruct from DB
        ai_session_key = f'ai_annotations_{page_id}'
        ai_session_data = request.session.get(ai_session_key, [])

        if not ai_session_data:
            ai_session_data = []
            for ann in page.annotations.filter(ai_reasoning__icontains='GROQ'):
                ai_session_data.append({
                    'text': ann.selected_text,
                    'type': ann.annotation_type.name,
                    'start_pos': ann.start_pos,
                    'end_pos': ann.end_pos,
                    'confidence': ann.confidence_score / 100.0
                })

        # Get current annotations (after human edits)
        current_annotations = []
        for annotation in page.annotations.all():
            current_annotations.append({
                'text': annotation.selected_text,
                'type': annotation.annotation_type.name,
                'start_pos': annotation.start_pos,
                'end_pos': annotation.end_pos,
                'confidence': annotation.confidence_score / 100.0
            })

        # Process feedback with RLHF
        rlhf_annotator = RLHFGroqAnnotator()
        feedback_result = rlhf_annotator.process_human_feedback(
            page_id=page_id,
            ai_annotations=ai_session_data,
            human_annotations=current_annotations,
            annotator_id=request.user.id
        )

        # Update page status
        page.is_validated_by_human = True
        page.human_validated_at = datetime.now()
        page.validated_by = request.user
        page.save()

        # Clear session
        if ai_session_key in request.session:
            del request.session[ai_session_key]

        # If all pages of the document are validated by human, auto-submit for expert review
        doc = page.document
        try:
            total = doc.total_pages or doc.pages.count()
            validated = doc.pages.filter(is_validated_by_human=True).count()
            if total > 0 and validated >= total and not doc.is_ready_for_expert:
                doc.is_ready_for_expert = True
                doc.expert_ready_at = datetime.now()
                doc.save(update_fields=['is_ready_for_expert', 'expert_ready_at'])
        except Exception:
            pass

        return JsonResponse({
            'success': True,
            'message': f'Page validée! Score: {feedback_result["feedback_score"]:.0%} - IA améliorée!',
            'feedback_score': feedback_result['feedback_score'],
            'corrections_summary': feedback_result['corrections_summary'],
            'ai_improved': True
        })

    except Exception as e:
        print(f"Validation error: {e}")
        return JsonResponse({
            'error': f'Erreur lors de la validation: {str(e)}'
        }, status=500)


@login_required
def get_learning_dashboard(request):
    """Get AI learning metrics dashboard"""
    try:
        # Get recent metrics
        recent_metrics = AILearningMetrics.objects.order_by('-created_at')[:10]

        # Prepare improvement data
        improvement_data = [{
            'date': m.created_at.strftime('%Y-%m-%d'),
            'f1_score': m.f1_score,
            'precision': m.precision_score,
            'recall': m.recall_score
        } for m in recent_metrics]

        # Get feedback stats
        total_feedbacks = AnnotationFeedback.objects.count()
        avg_feedback_score = AnnotationFeedback.objects.aggregate(
            avg_score=models.Avg('feedback_score')
        )['avg_score'] or 0

        # Get entity performance from latest metric
        latest_metric = recent_metrics.first()
        entity_performance = latest_metric.entity_performance if latest_metric else {}

        return JsonResponse({
            'total_feedbacks': total_feedbacks,
            'average_feedback_score': avg_feedback_score,
            'improvement_trend': improvement_data,
            'entity_performance': entity_performance,
            'learning_active': True
        })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@csrf_exempt
def ai_annotate_page_groq(request, page_id):
    """AI annotation with GROQ and RLHF"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        page = get_object_or_404(DocumentPage, id=page_id)

        # Clear existing annotations
        page.annotations.all().delete()

        # Initialize RLHF annotator
        groq_annotator = GroqAnnotator()

        # Create page data for dynamic annotation
        page_data = {
            'page_num': page.page_number,
            'text': page.cleaned_text,
            'char_count': len(page.cleaned_text)
        }

        # Get annotations with dynamic schema
        annotations, schema = groq_annotator.annotate_page_with_groq(page_data)

        # Store in session for feedback processing
        request.session[f'ai_annotations_{page_id}'] = annotations

        # Save to DB
        saved_count = 0
        for ann_data in annotations:
            try:
                ann_type, _ = AnnotationType.objects.get_or_create(
                    name=ann_data['type'],
                    defaults={
                        'display_name': ann_data['type'].replace('_', ' ').title(),
                        'color': '#3b82f6',
                        'description': f"GROQ detected {ann_data['type']}"
                    }
                )

                Annotation.objects.create(
                    page=page,
                    annotation_type=ann_type,
                    start_pos=ann_data.get('start_pos', 0),
                    end_pos=ann_data.get('end_pos', 0),
                    selected_text=ann_data.get('text', ''),
                    confidence_score=ann_data.get('confidence', 0.8) * 100,
                    ai_reasoning=ann_data.get('reasoning', 'GROQ classification'),
                    created_by=request.user
                )
                saved_count += 1
            except Exception as e:
                print(f"Error saving annotation: {e}")
                continue

        # Update page status
        if saved_count > 0:
            page.is_annotated = True
            page.annotated_at = datetime.now()
            page.annotated_by = request.user
            page.save()

        return JsonResponse({
            'success': True,
            'annotations_created': saved_count,
            'message': f'{saved_count} annotations créées avec GROQ!',
            'learning_enhanced': True
        })

    except Exception as e:
        print(f"GROQ annotation error: {e}")
        return JsonResponse({
            'error': f'Erreur GROQ: {str(e)}'
        }, status=500)


@login_required
def get_document_status(request, doc_id):
    """Get document validation status"""
    try:
        document = get_object_or_404(RawDocument, id=doc_id)
        total_pages = document.pages.count()
        validated_pages = document.pages.filter(is_validated_by_human=True).count()

        return JsonResponse({
            'total_pages': total_pages,
            'validated_pages': validated_pages,
            'is_ready_for_expert': document.is_ready_for_expert,
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@csrf_exempt
def submit_for_expert_review(request, doc_id):
    """Submit entire document for expert review"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        document = get_object_or_404(RawDocument, id=doc_id)
        document.is_ready_for_expert = True
        document.expert_ready_at = datetime.now()
        document.save()

        return JsonResponse({
            'success': True,
            'message': 'Document soumis pour révision expert!'
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@csrf_exempt
def create_annotation_type(request):
    """Create a new annotation type"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        data = json.loads(request.body)
        name = data.get('name', '').strip().lower().replace(' ', '_')
        display_name = data.get('display_name', '').strip()

        if not name or not display_name:
            return JsonResponse({'error': 'Name and display name are required'}, status=400)

        # Check if already exists
        if AnnotationType.objects.filter(name=name).exists():
            return JsonResponse({'error': f'Annotation type "{display_name}" already exists'}, status=400)

        # Create new annotation type
        annotation_type = AnnotationType.objects.create(
            name=name,
            display_name=display_name,
            color='#6366f1',  # Default purple color
            description=f'Custom annotation type created by {request.user.username}'
        )

        return JsonResponse({
            'success': True,
            'annotation_type': {
                'id': annotation_type.id,
                'name': annotation_type.name,
                'display_name': annotation_type.display_name,
                'color': annotation_type.color
            },
            'message': f'Annotation type "{display_name}" created successfully!'
        })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@csrf_exempt
def delete_annotation_type(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        data = json.loads(request.body)
        type_id = data.get('type_id')

        if not type_id:
            return JsonResponse({'error': 'Type ID required'}, status=400)

        # Get the annotation type
        annotation_type = get_object_or_404(AnnotationType, id=type_id)

        # Count how many annotations will be deleted
        annotation_count = Annotation.objects.filter(annotation_type=annotation_type).count()

        display_name = annotation_type.display_name

        # FORCE DELETE: Delete all annotations using this type first
        if annotation_count > 0:
            deleted_annotations = Annotation.objects.filter(annotation_type=annotation_type).delete()
            print(f"🗑️ Deleted {annotation_count} annotations of type '{display_name}'")

        # Now delete the annotation type itself
        annotation_type.delete()

        # Create success message
        if annotation_count > 0:
            message = f'Annotation type "{display_name}" and {annotation_count} associated annotation(s) deleted successfully!'
        else:
            message = f'Annotation type "{display_name}" deleted successfully!'

        return JsonResponse({
            'success': True,
            'message': message,
            'deleted_annotations': annotation_count
        })

    except Exception as e:
        print(f"❌ Error deleting annotation type: {e}")
        return JsonResponse({'error': str(e)}, status=500)
    
@login_required
def view_original_document(request, document_id):
    """View the original document PDF - RAWDOCS VERSION"""
    document = get_object_or_404(RawDocument, id=document_id)
    
    # Case 1: Document has a local file
    if document.file:
        try:
            # Serve the PDF file directly in browser
            response = HttpResponse(document.file.read(), content_type='application/pdf')
            response['Content-Disposition'] = f'inline; filename="{document.file.name}"'
            return response
        except Exception as e:
            # If file doesn't exist, show error
            return HttpResponse(
                f"<html><body><h2>Erreur</h2>"
                f"<p>Le fichier PDF n'a pas pu être chargé: {str(e)}</p>"
                f"<script>window.close();</script></body></html>"
            )
    
    # Case 2: Document was uploaded via URL
    elif document.url:
        try:
            # Redirect to the original URL
            return redirect(document.url)
        except Exception as e:
            return HttpResponse(
                f"<html><body><h2>Erreur</h2>"
                f"<p>Impossible d'accéder au document via URL: {str(e)}</p>"
                f"<p><a href='{document.url}' target='_blank'>Essayer d'ouvrir directement: {document.url}</a></p>"
                f"<script>window.close();</script></body></html>"
            )
    
    # Case 3: No file and no URL
    else:
        return HttpResponse(
            "<html><body><h2>Aucun fichier disponible</h2>"
            "<p>Ce document n'a ni fichier PDF ni URL source associé.</p>"
            "<script>window.close();</script></body></html>"
        )

@login_required
def document_tables_images(request, document_id):
    """
    Vue pour afficher les tableaux et images extraits d'un document
    """
    try:
        document = RawDocument.objects.get(id=document_id)
        
        # Vérifier les permissions
        if not request.user.is_staff and document.owner != request.user:
            messages.error(request, "Vous n'avez pas accès à ce document.")
            return redirect('rawdocs:document_list')
        
        # Créer l'extracteur
        extractor = TableImageExtractor(document.file.path)
        
        # Extraire tableaux et images
        tables = extractor.extract_tables_with_structure()
        images = extractor.extract_images()
        
        # Obtenir le HTML combiné
        combined_html = extractor.get_combined_html()
        
        # Résumé de l'extraction
        summary = extractor.get_extraction_summary()
        
        context = {
            'document': document,
            'tables': tables,
            'images': images,
            'combined_html': combined_html,
            'summary': summary,
            'total_elements': len(tables) + len(images)
        }
        
        return render(request, 'rawdocs/document_tables_images.html', context)
        
    except RawDocument.DoesNotExist:
        messages.error(request, "Document non trouvé.")
        return redirect('rawdocs:document_list')
    except Exception as e:
        messages.error(request, f"Erreur lors de l'extraction: {str(e)}")
        return redirect('rawdocs:document_detail', document_id=document_id)

@login_required
def export_tables_excel(request, document_id):
    """
    Exporte les tableaux d'un document vers Excel
    """
    try:
        document = RawDocument.objects.get(id=document_id)
        
        # Vérifier les permissions
        if not request.user.is_staff and document.owner != request.user:
            return JsonResponse({'error': 'Accès non autorisé'}, status=403)
        
        # Créer l'extracteur et extraire les tableaux
        extractor = TableImageExtractor(document.file.path)
        tables = extractor.extract_tables_with_structure()
        
        if not tables:
            return JsonResponse({'error': 'Aucun tableau trouvé dans ce document'}, status=404)
        
        # Créer le fichier Excel
        response = HttpResponse(
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        filename = f"tableaux_{document.title}_{document.id}.xlsx"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        # Utiliser un buffer pour créer le fichier Excel
        import io
        import pandas as pd
        
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            for table in tables:
                sheet_name = f"Page_{table['page']}_Table_{table['table_number']}"
                # Limiter la longueur du nom de feuille
                if len(sheet_name) > 31:
                    sheet_name = f"P{table['page']}_T{table['table_number']}"
                
                table['dataframe'].to_excel(writer, sheet_name=sheet_name, index=False)
        
        buffer.seek(0)
        response.write(buffer.getvalue())
        buffer.close()
        
        return response
        
    except RawDocument.DoesNotExist:
        return JsonResponse({'error': 'Document non trouvé'}, status=404)
    except Exception as e:
        return JsonResponse({'error': f'Erreur lors de l\'export: {str(e)}'}, status=500)

@login_required
def document_detail(request, document_id):
    """
    Vue pour afficher les détails d'un document
    """
    try:
        document = get_object_or_404(RawDocument, id=document_id)
        
        # Vérifier les permissions
        if not request.user.is_staff and document.owner != request.user:
            messages.error(request, "Vous n'avez pas accès à ce document.")
            return redirect('rawdocs:document_list')
        
        # Ajouter basename pour le template
        document.basename = os.path.basename(document.file.name) if document.file else "Document sans fichier"
        
        context = {
            'doc': document,
            'document': document,
        }
        
        return render(request, 'rawdocs/details_metadata.html', context)
        
    except RawDocument.DoesNotExist:
        messages.error(request, "Document non trouvé.")
        return redirect('rawdocs:document_list')
    except Exception as e:
        messages.error(request, f"Erreur lors de l'affichage du document: {str(e)}")
        return redirect('rawdocs:document_list')
    
@login_required
def add_field_ajax(request):
    if request.method == 'POST':
        import json
        data = json.loads(request.body)
        name = data.get('name')
        field_type = data.get('type', 'text')
        doc_id = data.get('doc_id')  # Get document ID
        
        from .models import CustomField, CustomFieldValue, RawDocument
        
        # Get the document
        document = get_object_or_404(RawDocument, id=doc_id)
        
        # Get or create the field type globally (for field type reference)
        field, created = CustomField.objects.get_or_create(
            name=name,
            defaults={'field_type': field_type}
        )
        
        # Create the field value ONLY for this specific document
        custom_value, value_created = CustomFieldValue.objects.get_or_create(
            document=document,
            field=field,
            defaults={'value': ''}  # Empty value initially
        )
        
        if value_created:
            return JsonResponse({
                'success': True, 
                'message': f'Field "{name}" added to this document only!'
            })
        else:
            return JsonResponse({
                'success': False, 
                'message': f'Field "{name}" already exists for this document!'
            })
    
    return JsonResponse({'success': False})

@login_required  
def save_custom_field(request):
    if request.method == 'POST':
        doc_id = request.POST.get('doc_id')
        field_name = request.POST.get('field_name')
        value = request.POST.get('value', '')
        
        from .models import RawDocument, CustomField, CustomFieldValue
        document = get_object_or_404(RawDocument, id=doc_id)
        field = get_object_or_404(CustomField, name=field_name)
        
        custom_value, created = CustomFieldValue.objects.get_or_create(
            document=document,
            field=field,
            defaults={'value': value}
        )
        if not created:
            custom_value.value = value
            custom_value.save()
            
        return JsonResponse({'success': True})
    
    return JsonResponse({'success': False})


def create_product_from_metadata(document):
    """Create product from custom metadata fields"""
    from .models import CustomFieldValue
    from client.products.models import Product
    
    # Find Product/Produit field (case insensitive)
    custom_values = CustomFieldValue.objects.filter(document=document)
    
    product_field = None
    product_name = None
    
    for custom_value in custom_values:
        field_name = custom_value.field.name.lower()
        if field_name in ['product', 'produit']:
            product_name = custom_value.value.strip()
            break
    
    if not product_name:
        return None
    
    # Create product with metadata fields
    product_data = {'name': product_name}
    
    # Auto-map matching fields
    field_mapping = {
        'dosage': 'dosage',
        'dose': 'dosage', 
        'active_ingredient': 'active_ingredient',
        'substance_active': 'active_ingredient',
        'form': 'form',
        'forme': 'form',
        'therapeutic_area': 'therapeutic_area',
        'zone_therapeutique': 'therapeutic_area'
    }
    
    for custom_value in custom_values:
        field_name = custom_value.field.name.lower()
        if field_name in field_mapping and custom_value.value:
            product_data[field_mapping[field_name]] = custom_value.value
    
    # Create the product
    product = Product.objects.create(
        name=product_data['name'],
        dosage=product_data.get('dosage', ''),
        active_ingredient=product_data.get('active_ingredient', ''),
        form=product_data.get('form', ''),
        therapeutic_area=product_data.get('therapeutic_area', ''),
        status='commercialise',
        source_document=document
    )
    
    print(f"✅ Product '{product.name}' created from metadata!")
    return product


###############################
# rawdocs/views.py - AJOUTER ces vues au fichier existant

from .regulatory_analyzer import RegulatoryAnalyzer
from .models import DocumentRegulatoryAnalysis


# =================== NOUVELLES VUES POUR L'ANALYSE RÉGLEMENTAIRE ===================

@login_required
@csrf_exempt
def analyze_page_regulatory(request, page_id):
    """
    Analyse réglementaire d'une page spécifique avec GROQ
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        page = get_object_or_404(DocumentPage, id=page_id)

        # Vérifier les permissions (annotateur ou plus)
        if not (is_annotateur(request.user) or is_expert(request.user) or is_metadonneur(request.user)):
            return JsonResponse({'error': 'Permission denied'}, status=403)

        print(f"🔍 Lancement analyse réglementaire page {page.page_number}")

        # Initialiser l'analyseur
        analyzer = RegulatoryAnalyzer()

        # Obtenir le contexte du document
        document_context = f"{page.document.title} - {page.document.doc_type} - {page.document.source}"

        # Analyser la page
        analysis = analyzer.analyze_page_regulatory_content(
            page_text=page.cleaned_text,
            page_num=page.page_number,
            document_context=document_context
        )

        # Sauvegarder l'analyse dans la base de données
        page.regulatory_analysis = analysis
        page.page_summary = analysis.get('page_summary', '')
        page.regulatory_obligations = analysis.get('regulatory_obligations', [])
        page.critical_deadlines = analysis.get('critical_deadlines', [])
        page.regulatory_importance_score = analysis.get('regulatory_importance_score', 0)
        page.is_regulatory_analyzed = True
        page.regulatory_analyzed_at = datetime.now()
        page.regulatory_analyzed_by = request.user
        page.save()

        print(
            f"✅ Analyse réglementaire page {page.page_number} sauvegardée - Score: {page.regulatory_importance_score}")

        return JsonResponse({
            'success': True,
            'message': f'Page {page.page_number} analysée avec succès!',
            'analysis': analysis,
            'importance_score': page.regulatory_importance_score
        })

    except Exception as e:
        print(f"❌ Erreur analyse réglementaire page {page_id}: {e}")
        return JsonResponse({
            'error': f'Erreur lors de l\'analyse: {str(e)}'
        }, status=500)


@login_required
@csrf_exempt
def analyze_document_regulatory_bulk(request, doc_id):
    """
    Analyse réglementaire complète d'un document (toutes les pages)
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        document = get_object_or_404(RawDocument, id=doc_id, is_validated=True)

        # Vérifier les permissions
        if not (is_annotateur(request.user) or is_expert(request.user) or is_metadonneur(request.user)):
            return JsonResponse({'error': 'Permission denied'}, status=403)

        print(f"🔍 Lancement analyse réglementaire complète document {doc_id}")

        # Initialiser l'analyseur
        analyzer = RegulatoryAnalyzer()
        document_context = f"{document.title} - {document.doc_type} - {document.source}"

        # Analyser toutes les pages
        pages = document.pages.all().order_by('page_number')
        analyses = []
        analyzed_count = 0

        for page in pages:
            try:
                print(f"📄 Analyse page {page.page_number}/{document.total_pages}")

                analysis = analyzer.analyze_page_regulatory_content(
                    page_text=page.cleaned_text,
                    page_num=page.page_number,
                    document_context=document_context
                )

                # Sauvegarder l'analyse
                page.regulatory_analysis = analysis
                page.page_summary = analysis.get('page_summary', '')
                page.regulatory_obligations = analysis.get('regulatory_obligations', [])
                page.critical_deadlines = analysis.get('critical_deadlines', [])
                page.regulatory_importance_score = analysis.get('regulatory_importance_score', 0)
                page.is_regulatory_analyzed = True
                page.regulatory_analyzed_at = datetime.now()
                page.regulatory_analyzed_by = request.user
                page.save()

                analyses.append(analysis)
                analyzed_count += 1

                # Pause pour éviter les limites d'API
                time.sleep(2)

            except Exception as e:
                print(f"❌ Erreur page {page.page_number}: {e}")
                continue

        # Générer le résumé global
        print(f"📊 Génération résumé global avec {len(analyses)} analyses...")
        global_analysis = analyzer.generate_document_global_summary(document, analyses)

        # Sauvegarder l'analyse globale
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
                    1 for a in analyses if a.get('regulatory_importance_score', 0) > 30)
            }
        )

        print(f"✅ Analyse complète terminée: {analyzed_count} pages analysées")

        return JsonResponse({
            'success': True,
            'message': f'Document analysé avec succès! {analyzed_count} pages traitées.',
            'analyzed_pages': analyzed_count,
            'total_pages': document.total_pages,
            'global_score': global_analysis.get('global_regulatory_score', 0),
            'global_analysis': global_analysis
        })

    except Exception as e:
        print(f"❌ Erreur analyse document {doc_id}: {e}")
        return JsonResponse({
            'error': f'Erreur lors de l\'analyse: {str(e)}'
        }, status=500)


@login_required
def get_page_regulatory_analysis(request, page_id):
    """
    Récupère l'analyse réglementaire d'une page
    """
    try:
        page = get_object_or_404(DocumentPage, id=page_id)

        if not page.is_regulatory_analyzed:
            return JsonResponse({
                'analyzed': False,
                'message': 'Page non analysée'
            })

        return JsonResponse({
            'analyzed': True,
            'page_summary': page.page_summary,
            'importance_score': page.regulatory_importance_score,
            'regulatory_analysis': page.regulatory_analysis,
            'analyzed_at': page.regulatory_analyzed_at.isoformat() if page.regulatory_analyzed_at else None
        })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def get_document_regulatory_summary(request, doc_id):
    """
    Récupère le résumé réglementaire global d'un document
    """
    try:
        document = get_object_or_404(RawDocument, id=doc_id)

        # Statistiques des pages
        total_pages = document.pages.count()
        analyzed_pages = document.pages.filter(is_regulatory_analyzed=True).count()
        high_importance_pages = document.pages.filter(regulatory_importance_score__gte=70).count()

        # Analyse globale si disponible
        try:
            global_analysis = document.regulatory_analysis
            has_global_analysis = True
        except DocumentRegulatoryAnalysis.DoesNotExist:
            global_analysis = None
            has_global_analysis = False

        # Résumé des pages importantes
        important_pages = []
        for page in document.pages.filter(regulatory_importance_score__gte=50).order_by('-regulatory_importance_score')[
                    :5]:
            important_pages.append({
                'page_number': page.page_number,
                'summary': page.page_summary,
                'score': page.regulatory_importance_score,
                'key_points': page.regulatory_analysis.get('key_regulatory_points',
                                                           []) if page.regulatory_analysis else []
            })

        return JsonResponse({
            'has_global_analysis': has_global_analysis,
            'stats': {
                'total_pages': total_pages,
                'analyzed_pages': analyzed_pages,
                'high_importance_pages': high_importance_pages,
                'completion_percentage': int((analyzed_pages / total_pages * 100)) if total_pages > 0 else 0
            },
            'global_summary': global_analysis.global_summary if global_analysis else '',
            'global_score': global_analysis.global_regulatory_score if global_analysis else 0,
            'consolidated_analysis': global_analysis.consolidated_analysis if global_analysis else {},
            'important_pages': important_pages
        })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# =================== MISE À JOUR DE LA VUE ANNOTATION EXISTANTE ===================

@login_required
@user_passes_test(is_annotateur)
def annotate_document(request, doc_id):
    """Vue d'annotation mise à jour avec analyse réglementaire"""
    document = get_object_or_404(RawDocument, id=doc_id, is_validated=True)
    pages = document.pages.all()
    pnum = int(request.GET.get('page', 1))
    page_obj = get_object_or_404(DocumentPage, document=document, page_number=pnum)

    # Statistiques d'analyse réglementaire
    regulatory_stats = {
        'total_pages': document.total_pages,
        'analyzed_pages': pages.filter(is_regulatory_analyzed=True).count(),
        'high_importance_pages': pages.filter(regulatory_importance_score__gte=70).count(),
    }
    regulatory_stats['completion_percentage'] = int(
        (regulatory_stats['analyzed_pages'] / regulatory_stats['total_pages'] * 100)) if regulatory_stats[
                                                                                             'total_pages'] > 0 else 0

    # Analyse globale du document
    try:
        global_analysis = document.regulatory_analysis
    except DocumentRegulatoryAnalysis.DoesNotExist:
        global_analysis = None

    # Build reduced, default annotation types + include types already used in this document
    used_type_ids = Annotation.objects.filter(page__document=document).values_list('annotation_type_id', flat=True).distinct()

    # Default whitelist (keywords-independent)
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

    return render(request, 'rawdocs/annotate_document.html', {
        'document': document,
        'pages': pages,
        'current_page': page_obj,
        'annotation_types': annotation_types,
        'existing_annotations': page_obj.annotations.all().order_by('start_pos'),
        'total_pages': document.total_pages,
        # Nouvelles données pour l'analyse réglementaire
        'regulatory_stats': regulatory_stats,
        'global_analysis': global_analysis,
        'page_analysis': page_obj.regulatory_analysis if page_obj.is_regulatory_analyzed else None,
        'page_summary': page_obj.page_summary,
        'page_importance_score': page_obj.regulatory_importance_score
    })


# =================== VUE POUR LE DASHBOARD D'ANALYSE RÉGLEMENTAIRE ===================

@login_required
@user_passes_test(is_annotateur)
def regulatory_analysis_dashboard(request):
    """
    Dashboard spécialisé pour l'analyse réglementaire
    """
    # Documents disponibles pour analyse
    documents = RawDocument.objects.filter(
        is_validated=True,
        pages_extracted=True
    ).order_by('-validated_at')

    # Statistiques globales
    total_documents = documents.count()
    analyzed_documents = documents.filter(regulatory_analysis__isnull=False).count()

    # Documents avec analyse en cours ou complète
    documents_with_stats = []
    for doc in documents[:20]:  # Limiter pour performance
        analyzed_pages = doc.pages.filter(is_regulatory_analyzed=True).count()
        total_pages = doc.total_pages
        completion = int((analyzed_pages / total_pages * 100)) if total_pages > 0 else 0

        try:
            global_score = doc.regulatory_analysis.global_regulatory_score
        except DocumentRegulatoryAnalysis.DoesNotExist:
            global_score = 0

        documents_with_stats.append({
            'document': doc,
            'analyzed_pages': analyzed_pages,
            'total_pages': total_pages,
            'completion_percentage': completion,
            'global_score': global_score
        })

    context = {
        'documents_with_stats': documents_with_stats,
        'total_documents': total_documents,
        'analyzed_documents': analyzed_documents,
        'analysis_completion': int((analyzed_documents / total_documents * 100)) if total_documents > 0 else 0
    }

    return render(request, 'rawdocs/regulatory_analysis_dashboard.html', context)


# =================== VUES POUR L'ÉDITION DES ANNOTATIONS ===================

@login_required
@csrf_exempt
def edit_annotation(request, annotation_id):
    """
    Permet de modifier une annotation existante
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        annotation = get_object_or_404(Annotation, id=annotation_id)

        # Vérifier les permissions
        if not (is_annotateur(request.user) or is_expert(request.user) or is_metadonneur(request.user)):
            return JsonResponse({'error': 'Permission denied'}, status=403)

        data = json.loads(request.body)

        # Vérifier les champs requis
        required_fields = ['selected_text', 'annotation_type_id']
        for field in required_fields:
            if field not in data:
                return JsonResponse({'error': f'Champ requis manquant: {field}'}, status=400)

        # Obtenir le nouveau type d'annotation
        new_annotation_type = get_object_or_404(AnnotationType, id=data['annotation_type_id'])

        # Sauvegarder les anciennes valeurs pour logging
        old_values = {
            'selected_text': annotation.selected_text,
            'annotation_type': annotation.annotation_type.display_name,
            'start_pos': annotation.start_pos,
            'end_pos': annotation.end_pos
        }

        # Mettre à jour l'annotation
        annotation.selected_text = data['selected_text'].strip()
        annotation.annotation_type = new_annotation_type

        # Mettre à jour les positions si fournies
        if 'start_pos' in data:
            annotation.start_pos = int(data['start_pos'])
        if 'end_pos' in data:
            annotation.end_pos = int(data['end_pos'])

        # Marquer comme modifiée par un humain
        annotation.modified_by_human = True
        annotation.human_modified_at = timezone.now()
        annotation.last_modified_by = request.user

        # Ajouter une note sur la modification
        if annotation.ai_reasoning:
            annotation.ai_reasoning = f"[Modifié par {request.user.username}] {annotation.ai_reasoning}"
        else:
            annotation.ai_reasoning = f"Annotation modifiée par {request.user.username}"

        annotation.save()

        # Logger la modification (optionnel)
        print(f"✏️ Annotation {annotation_id} modifiée par {request.user.username}")
        print(f"   Ancien texte: '{old_values['selected_text']}'")
        print(f"   Nouveau texte: '{annotation.selected_text}'")
        print(f"   Ancien type: {old_values['annotation_type']}")
        print(f"   Nouveau type: {annotation.annotation_type.display_name}")

        return JsonResponse({
            'success': True,
            'message': 'Annotation modifiée avec succès',
            'annotation': {
                'id': annotation.id,
                'selected_text': annotation.selected_text,
                'annotation_type': {
                    'id': annotation.annotation_type.id,
                    'name': annotation.annotation_type.name,
                    'display_name': annotation.annotation_type.display_name,
                    'color': annotation.annotation_type.color
                },
                'confidence_score': annotation.confidence_score,
                'ai_reasoning': annotation.ai_reasoning,
                'start_pos': annotation.start_pos,
                'end_pos': annotation.end_pos,
                'modified_by_human': True
            }
        })

    except json.JSONDecodeError:
        return JsonResponse({'error': 'JSON invalide'}, status=400)
    except Exception as e:
        print(f"❌ Erreur modification annotation {annotation_id}: {e}")
        return JsonResponse({'error': f'Erreur lors de la modification: {str(e)}'}, status=500)


@login_required
def get_annotation_details(request, annotation_id):
    """
    Récupère les détails d'une annotation pour l'édition
    """
    try:
        annotation = get_object_or_404(Annotation, id=annotation_id)

        # Vérifier les permissions
        if not (is_annotateur(request.user) or is_expert(request.user) or is_metadonneur(request.user)):
            return JsonResponse({'error': 'Permission denied'}, status=403)

        return JsonResponse({
            'success': True,
            'annotation': {
                'id': annotation.id,
                'selected_text': annotation.selected_text,
                'annotation_type': {
                    'id': annotation.annotation_type.id,
                    'name': annotation.annotation_type.name,
                    'display_name': annotation.annotation_type.display_name,
                    'color': annotation.annotation_type.color
                },
                'confidence_score': annotation.confidence_score,
                'ai_reasoning': annotation.ai_reasoning,
                'start_pos': annotation.start_pos,
                'end_pos': annotation.end_pos,
                'created_by': annotation.created_by.username if annotation.created_by else None,
                'modified_by_human': getattr(annotation, 'modified_by_human', False)
            }
        })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required(login_url='rawdocs:login')
@user_passes_test(is_dev_metier, login_url='rawdocs:login')
def dev_metier_dashboard(request):
    # Documents validés par l'EXPERT uniquement
    validated_documents = (
        RawDocument.objects
        .filter(is_expert_validated=True)
        .order_by('-expert_validated_at')[:100]
    )

    for doc in validated_documents:
        # nom de fichier lisible dans le template
        doc.basename = os.path.basename(doc.file.name) if doc.file else ''

    # Quelques stats simples pour les graphes
    total_docs = RawDocument.objects.count()
    expert_validated_count = validated_documents.count()
    remaining = max(total_docs - expert_validated_count, 0)

    bar_data = json.dumps([150, total_docs, expert_validated_count, remaining])
    pie_data = json.dumps([30, 20, 25, 10, 15])  # garde tel quel si c'est du fake data

    return render(request, 'rawdocs/dev_metier_dashboard.html', {
        "validated_documents": validated_documents,
        "bar_data": bar_data,
        "pie_data": pie_data,
    })

# =================== NOUVELLES VUES POUR JSON ET RÉSUMÉS D'ANNOTATIONS ===================

from .regulatory_analyzer import RegulatoryAnalyzer

from collections import OrderedDict
from datetime import datetime

def _build_entities_map(annotations_qs, use_display_name=True):
    """
    Construit {entité -> [valeurs_uniques]} à partir d'un QuerySet d'annotations.
    - use_display_name=True : clé = display_name (lisible)
      sinon clé = name (technique)
    """
    entities = OrderedDict()
    seen_per_key = {}

    for ann in annotations_qs:
        key = ann.annotation_type.display_name if use_display_name else ann.annotation_type.name
        val = (ann.selected_text or "").strip()
        if not val:
            continue

        if key not in entities:
            entities[key] = []
            seen_per_key[key] = set()

        if val not in seen_per_key[key]:
            entities[key].append(val)
            seen_per_key[key].add(val)

    return entities

@login_required
@csrf_exempt
def generate_page_annotation_summary(request, page_id):
    """
    Produit un JSON minimaliste (doc info + entities) et un résumé
    basés uniquement sur {entité -> valeurs} pour UNE page.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        page = get_object_or_404(DocumentPage, id=page_id)

        if not (is_annotateur(request.user) or is_expert(request.user) or is_metadonneur(request.user)):
            return JsonResponse({'error': 'Permission denied'}, status=403)

        # Récupérer les annotations de la page
        annotations = page.annotations.all().select_related('annotation_type').order_by('start_pos')

        # Construire entities -> [valeurs]
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
        page.save(update_fields=['annotations_json', 'annotations_summary'])

        return JsonResponse({
            'success': True,
            'page_json': page_json,
            'summary': summary,
            'message': f'JSON et résumé générés pour la page {page.page_number}'
        })
    except Exception as e:
        print(f"❌ Erreur génération résumé page {page_id}: {e}")
        return JsonResponse({'error': f'Erreur lors de la génération: {str(e)}'}, status=500)



@login_required
@csrf_exempt
def generate_document_annotation_summary(request, doc_id):
    """
    Produit un JSON global minimaliste (doc info + entities) et un résumé
    basés uniquement sur {entité -> valeurs} pour TOUT le document.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        document = get_object_or_404(RawDocument, id=doc_id, is_validated=True)

        if not (is_annotateur(request.user) or is_expert(request.user) or is_metadonneur(request.user)):
            return JsonResponse({'error': 'Permission denied'}, status=403)

        pages = document.pages.all().order_by('page_number')

        # Agrégation globale des entités
        global_entities = OrderedDict()
        total_annotations_count = 0

        for page in pages:
            page_annotations = page.annotations.all().select_related('annotation_type').order_by('start_pos')
            total_annotations_count += page_annotations.count()

            page_entities = _build_entities_map(page_annotations, use_display_name=True)
            # Fusion {entité -> valeurs}
            for ent, vals in page_entities.items():
                if ent not in global_entities:
                    global_entities[ent] = []
                for v in vals:
                    if v not in global_entities[ent]:
                        global_entities[ent].append(v)

        global_json = {
            'document': {
                'id': str(document.id),
                'title': document.title,
                'doc_type': getattr(document, 'doc_type', None),
                'source': getattr(document, 'source', None),
                'total_pages': getattr(document, 'total_pages', pages.count()),
                'total_annotations': total_annotations_count,
            },
            'entities': global_entities,
            'generated_at': datetime.utcnow().isoformat() + 'Z',
        }

        # Résumé global basé uniquement sur les entités/valeurs
        global_summary = generate_entities_based_document_summary(
            entities=global_entities,
            doc_title=document.title,
            doc_type=getattr(document, 'doc_type', None),
            total_annotations=total_annotations_count
        )

        document.global_annotations_json = global_json
        document.global_annotations_summary = global_summary
        document.save(update_fields=['global_annotations_json', 'global_annotations_summary'])

        return JsonResponse({
            'success': True,
            'global_json': global_json,
            'global_summary': global_summary,
            'stats': {
                'total_pages': getattr(document, 'total_pages', pages.count()),
                'total_annotations': total_annotations_count,
                'entities_count': len(global_entities)
            },
            'message': 'JSON global et résumé générés pour le document complet'
        })
    except Exception as e:
        print(f"❌ Erreur génération résumé document {doc_id}: {e}")
        return JsonResponse({'error': f'Erreur lors de la génération: {str(e)}'}, status=500)

def generate_entities_based_page_summary(entities, page_number, document_title):
    """
    Résumé NL d'une page à partir du dict {entité -> [valeurs]}.
    """
    try:
        if not entities:
            return "Aucune entité annotée sur cette page."

        # Préparer un texte compact pour le prompt/backup
        lines = []
        total_pairs = 0
        for ent, vals in entities.items():
            total_pairs += len(vals)
            preview = "; ".join(vals[:4]) + ("…" if len(vals) > 4 else "")
            lines.append(f"- {ent}: {preview}")

        structured_view = "\n".join(lines)

        prompt = f"""Tu es un expert en analyse documentaire.
Génère un résumé court (3–4 phrases) et fluide basé UNIQUEMENT sur les entités et leurs valeurs.

DOCUMENT: {document_title}
PAGE: {page_number}

ENTITÉS → VALEURS:
{structured_view}

Contraintes:
- Ne liste pas tout; synthétise les thèmes/infos clés.
- Utilise un ton pro et clair.
- Termine par le nombre total de paires entité-valeur entre parenthèses.

Réponds UNIQUEMENT par le paragraphe.
"""

        analyzer = RegulatoryAnalyzer()
        response = analyzer.call_groq_api(prompt, max_tokens=280)
        return response.strip() if response else f"Page {page_number}: synthèse de {total_pairs} élément(s) annoté(s) sur les entités « {', '.join(list(entities.keys())[:5])}{'…' if len(entities)>5 else ''} »."
    except Exception as e:
        print(f"❌ Erreur génération résumé (page): {e}")
        # Fallback minimal
        flat_count = sum(len(v) for v in entities.values())
        return f"Page {page_number}: {flat_count} valeur(s) annotée(s) sur {len(entities)} entité(s)."


def generate_entities_based_document_summary(entities, doc_title, doc_type, total_annotations):
    """
    Résumé NL global à partir du dict {entité -> [valeurs]}.
    """
    try:
        if not entities:
            return "Aucune entité annotée dans ce document."

        # Top entités par volume
        ranked = sorted(entities.items(), key=lambda kv: len(kv[1]), reverse=True)
        top_lines = [f"- {k}: {len(v)} valeur(s)" for k, v in ranked[:6]]
        repartition = "\n".join(top_lines)

        prompt = f"""Tu es un expert en analyse documentaire.
Produis un résumé exécutif (4–6 phrases) basé UNIQUEMENT sur les entités et leurs valeurs.

DOCUMENT: {doc_title}
TYPE: {doc_type or '—'}
TOTAL ANNOTATIONS: {total_annotations}

RÉPARTITION (Top entités par nombre de valeurs):
{repartition}

Contraintes:
- Extrais les thèmes majeurs qui se dégagent des entités dominantes.
- Indique la couverture globale (ex.: diversité des entités, répartition).
- Reste factuel, ton professionnel, sans lister toutes les valeurs.

Réponds UNIQUEMENT par le paragraphe.
"""

        analyzer = RegulatoryAnalyzer()
        response = analyzer.call_groq_api(prompt, max_tokens=360)
        if response:
            return response.strip()

        # Fallback succinct
        top_names = [k for k, _ in ranked[:3]]
        total_values = sum(len(v) for v in entities.values())
        return (f"Le document agrège {total_values} valeur(s) annotée(s) sur {len(entities)} entité(s). "
                f"Principales entités : {', '.join(top_names)}.")
    except Exception as e:
        print(f"❌ Erreur génération résumé (document): {e}")
        total_values = sum(len(v) for v in entities.values())
        return f"Document : {total_values} valeur(s) sur {len(entities)} entité(s)."

@login_required
def view_page_annotation_json(request, page_id):
    """
    Affiche le JSON et résumé d'une page dans une vue dédiée
    """
    try:
        page = get_object_or_404(DocumentPage, id=page_id)

        # Vérifier les permissions
        if not (is_annotateur(request.user) or is_expert(request.user) or is_metadonneur(request.user)):
            messages.error(request, "Permission denied")
            return redirect('rawdocs:annotation_dashboard')

        # Si pas encore généré, le générer
        if not hasattr(page, 'annotations_json') or not page.annotations_json:
            # Déclencher la génération
            from django.test import RequestFactory
            factory = RequestFactory()
            fake_request = factory.post(f'/generate-page-annotation-summary/{page_id}/')
            fake_request.user = request.user
            generate_page_annotation_summary(fake_request, page_id)
            page.refresh_from_db()

        context = {
            'page': page,
            'document': page.document,
            'annotations_json': page.annotations_json if hasattr(page, 'annotations_json') else None,
            'annotations_summary': page.annotations_summary if hasattr(page, 'annotations_summary') else None,
            'total_annotations': page.annotations.count()
        }

        return render(request, 'rawdocs/view_page_annotation_json.html', context)

    except Exception as e:
        messages.error(request, f"Erreur: {str(e)}")
        return redirect('rawdocs:annotation_dashboard')
    

@login_required
@user_passes_test(is_dev_metier)
@csrf_exempt
def dev_metier_generate_page_annotation_summary(request, page_id):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        page = get_object_or_404(DocumentPage, id=page_id)

        # Récupérer les annotations de la page
        annotations = page.annotations.all().select_related('annotation_type').order_by('start_pos')

        # Construire entities -> [valeurs]
        entities = _build_entities_map(annotations, use_display_name=True)

        # JSON minimaliste de la page
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

        # Résumé basé sur les entités de la page
        summary = generate_entities_based_page_summary(
            entities=entities,
            page_number=page.page_number,
            document_title=page.document.title
        )

        # Sauvegarde avec timestamp
        page.annotations_json = page_json
        page.annotations_summary = summary
        page.annotations_summary_generated_at = timezone.now()  # ⭐ NOUVEAU
        page.save(update_fields=['annotations_json', 'annotations_summary', 'annotations_summary_generated_at'])

        return JsonResponse({'success': True, 'page_json': page_json, 'summary': summary})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required(login_url='rawdocs:login')
@user_passes_test(is_dev_metier, login_url='rawdocs:login')
def dev_metier_document_annotation_json(request, doc_id):
    document = get_object_or_404(RawDocument, id=doc_id, is_expert_validated=True)

    # Générer le JSON global si absent avec gestion d'erreur
    if not document.global_annotations_json:
        try:
            from django.test import RequestFactory
            fake = RequestFactory().post(f'/expert/annotation/document/{doc_id}/generate-summary/')
            fake.user = request.user
            # Appel à la fonction de génération (à adapter selon votre structure)
            generate_document_annotation_summary(fake, doc_id)
            document.refresh_from_db()
        except Exception as e:
            messages.warning(request, f"Génération globale non effectuée : {e}")

    # Gestion de la page sélectionnée avec meilleure gestion d'erreur
    selected_page_number = request.GET.get('page') or None
    page_json = None
    page_summary = None

    if selected_page_number:
        try:
            page_num = int(selected_page_number)
            page = DocumentPage.objects.get(document=document, page_number=page_num)

            # Générer le JSON de la page si absent
            if not page.annotations_json:
                from django.test import RequestFactory
                fake = RequestFactory().post(f'/dev-metier/annotation/page/{page.id}/generate-summary/')
                fake.user = request.user
                dev_metier_generate_page_annotation_summary(fake, page.id)  # ⭐ NOUVEAU
                page.refresh_from_db()

            page_json = page.annotations_json or {}
            page_summary = page.annotations_summary or ""
        except (ValueError, DocumentPage.DoesNotExist):
            messages.error(request, f"Page {selected_page_number} introuvable pour ce document.")

    pages = document.pages.all().order_by('page_number')

    context = {
        'document': document,
        'global_annotations_json': document.global_annotations_json or {},
        'global_annotations_summary': document.global_annotations_summary or "",
        'page_json': page_json,
        'page_summary': page_summary,
        'pages': pages,
        'selected_page_number': selected_page_number,
        'total_annotations': sum(p.annotations.count() for p in document.pages.all()),
        'annotated_pages': document.pages.filter(annotations__isnull=False).distinct().count(),
        'total_pages': document.total_pages,
    }
    return render(request, 'rawdocs/view_document_annotation_json_devmetier.html', context)


@login_required
def view_document_annotation_json(request, doc_id):
    """
    Affiche le JSON global et résumé du document dans une vue dédiée avec édition pour expert
    """
    try:
        document = get_object_or_404(RawDocument, id=doc_id, is_validated=True)

        # Vérifier les permissions
        if not (is_annotateur(request.user) or is_expert(request.user) or is_metadonneur(request.user)):
            messages.error(request, "Permission denied")
            return redirect('rawdocs:annotation_dashboard')

        # Si pas encore généré, le générer
        if not hasattr(document, 'global_annotations_json') or not document.global_annotations_json:
            # Déclencher la génération
            from django.test import RequestFactory
            factory = RequestFactory()
            fake_request = factory.post(f'/generate-document-annotation-summary/{doc_id}/')
            fake_request.user = request.user
            generate_document_annotation_summary(fake_request, doc_id)
            document.refresh_from_db()

        # Statistiques
        total_annotations = sum(page.annotations.count() for page in document.pages.all())
        annotated_pages = document.pages.filter(annotations__isnull=False).distinct().count()

        context = {
            'document': document,
            'global_annotations_json': document.global_annotations_json if hasattr(document,
                                                                                   'global_annotations_json') else None,
            'global_annotations_summary': document.global_annotations_summary if hasattr(document,
                                                                                         'global_annotations_summary') else None,
            'total_annotations': total_annotations,
            'annotated_pages': annotated_pages,
            'total_pages': document.total_pages
        }

        return render(request, 'rawdocs/view_document_annotation_json.html', context)

    except Exception as e:
        messages.error(request, f"Erreur: {str(e)}")
        return redirect('rawdocs:annotation_dashboard')

##################edit################
# Ajouter cette nouvelle vue dans rawdocs/views.py

@login_required
@csrf_exempt
def edit_annotation(request, annotation_id):
    """
    Permet de modifier une annotation existante
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        annotation = get_object_or_404(Annotation, id=annotation_id)

        # Vérifier les permissions
        if not (is_annotateur(request.user) or is_expert(request.user) or is_metadonneur(request.user)):
            return JsonResponse({'error': 'Permission denied'}, status=403)

        data = json.loads(request.body)

        # Vérifier les champs requis
        required_fields = ['selected_text', 'annotation_type_id']
        for field in required_fields:
            if field not in data:
                return JsonResponse({'error': f'Champ requis manquant: {field}'}, status=400)

        # Obtenir le nouveau type d'annotation
        new_annotation_type = get_object_or_404(AnnotationType, id=data['annotation_type_id'])

        # Sauvegarder les anciennes valeurs pour logging
        old_values = {
            'selected_text': annotation.selected_text,
            'annotation_type': annotation.annotation_type.display_name,
            'start_pos': annotation.start_pos,
            'end_pos': annotation.end_pos
        }

        # Mettre à jour l'annotation
        annotation.selected_text = data['selected_text'].strip()
        annotation.annotation_type = new_annotation_type

        # Mettre à jour les positions si fournies
        if 'start_pos' in data:
            annotation.start_pos = int(data['start_pos'])
        if 'end_pos' in data:
            annotation.end_pos = int(data['end_pos'])

        # Marquer comme modifiée par un humain
        annotation.modified_by_human = True
        annotation.human_modified_at = timezone.now()
        annotation.last_modified_by = request.user

        # Ajouter une note sur la modification
        if annotation.ai_reasoning:
            annotation.ai_reasoning = f"[Modifié par {request.user.username}] {annotation.ai_reasoning}"
        else:
            annotation.ai_reasoning = f"Annotation modifiée par {request.user.username}"

        annotation.save()

        # Logger la modification (optionnel)
        print(f"✏️ Annotation {annotation_id} modifiée par {request.user.username}")
        print(f"   Ancien texte: '{old_values['selected_text']}'")
        print(f"   Nouveau texte: '{annotation.selected_text}'")
        print(f"   Ancien type: {old_values['annotation_type']}")
        print(f"   Nouveau type: {annotation.annotation_type.display_name}")

        return JsonResponse({
            'success': True,
            'message': 'Annotation modifiée avec succès',
            'annotation': {
                'id': annotation.id,
                'selected_text': annotation.selected_text,
                'annotation_type': {
                    'id': annotation.annotation_type.id,
                    'name': annotation.annotation_type.name,
                    'display_name': annotation.annotation_type.display_name,
                    'color': annotation.annotation_type.color
                },
                'confidence_score': annotation.confidence_score,
                'ai_reasoning': annotation.ai_reasoning,
                'start_pos': annotation.start_pos,
                'end_pos': annotation.end_pos,
                'modified_by_human': True
            }
        })

    except json.JSONDecodeError:
        return JsonResponse({'error': 'JSON invalide'}, status=400)
    except Exception as e:
        print(f"❌ Erreur modification annotation {annotation_id}: {e}")
        return JsonResponse({'error': f'Erreur lors de la modification: {str(e)}'}, status=500)


@login_required
def get_annotation_details(request, annotation_id):
    """
    Récupère les détails d'une annotation pour l'édition
    """
    try:
        annotation = get_object_or_404(Annotation, id=annotation_id)

        # Vérifier les permissions
        if not (is_annotateur(request.user) or is_expert(request.user) or is_metadonneur(request.user)):
            return JsonResponse({'error': 'Permission denied'}, status=403)

        return JsonResponse({
            'success': True,
            'annotation': {
                'id': annotation.id,
                'selected_text': annotation.selected_text,
                'annotation_type': {
                    'id': annotation.annotation_type.id,
                    'name': annotation.annotation_type.name,
                    'display_name': annotation.annotation_type.display_name,
                    'color': annotation.annotation_type.color
                },
                'confidence_score': annotation.confidence_score,
                'ai_reasoning': annotation.ai_reasoning,
                'start_pos': annotation.start_pos,
                'end_pos': annotation.end_pos,
                'created_by': annotation.created_by.username if annotation.created_by else None,
                'modified_by_human': getattr(annotation, 'modified_by_human', False)
            }
        })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

# =================== NOUVELLES VUES POUR L'ÉDITION DU RÉSUMÉ GLOBAL PAR L'EXPERT ===================

from .models import GlobalSummaryEditHistory  # Import du modèle depuis models.py

@login_required
@user_passes_test(is_expert)
@csrf_exempt
def edit_global_summary(request, doc_id):
    """
    Permet à l'expert de modifier le résumé global du document
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        document = get_object_or_404(RawDocument, id=doc_id)
        data = json.loads(request.body)

        if 'summary' not in data:
            return JsonResponse({'error': 'Résumé manquant'}, status=400)

        # Sauvegarder l'ancien résumé pour l'historique
        old_summary = document.global_annotations_summary or ""
        new_summary = data['summary'].strip()

        # Créer une entrée dans l'historique
        GlobalSummaryEditHistory.objects.create(
            document=document,
            old_summary=old_summary,
            new_summary=new_summary,
            modified_by=request.user,
            reason=data.get('reason', 'Modification expert')
        )

        # Mettre à jour le résumé
        document.global_annotations_summary = new_summary
        document.save(update_fields=['global_annotations_summary'])

        return JsonResponse({
            'success': True,
            'message': 'Résumé global mis à jour avec succès',
            'summary': new_summary
        })

    except json.JSONDecodeError:
        return JsonResponse({'error': 'JSON invalide'}, status=400)
    except Exception as e:
        print(f"❌ Erreur modification résumé global du document {doc_id}: {e}")
        return JsonResponse({'error': f'Erreur lors de la modification: {str(e)}'}, status=500)

@login_required
@user_passes_test(is_expert)
def get_global_summary_history(request, doc_id):
    """
    Récupère l'historique des modifications du résumé global
    """
    try:
        document = get_object_or_404(RawDocument, id=doc_id)
        history = GlobalSummaryEditHistory.objects.filter(
            document=document
        ).order_by('-modified_at')

        history_data = [{
            'old_summary': entry.old_summary,
            'new_summary': entry.new_summary,
            'modified_by': entry.modified_by.username if entry.modified_by else "Système",
            'modified_at': entry.modified_at.isoformat(),
            'reason': entry.reason
        } for entry in history]

        return JsonResponse({
            'success': True,
            'history': history_data
        })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@login_required
@user_passes_test(is_expert)
@csrf_exempt
def validate_global_summary(request, doc_id):
    """
    Permet à l'expert de valider le résumé global
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        document = get_object_or_404(RawDocument, id=doc_id)
        data = json.loads(request.body)

        # Marquer comme validé par l'expert
        document.global_summary_validated = True
        document.global_summary_validated_at = timezone.now()
        document.global_summary_validated_by = request.user
        document.expert_comments = data.get('comments', '')
        document.save()

        return JsonResponse({
            'success': True,
            'message': 'Résumé global validé avec succès'
        })

    except json.JSONDecodeError:
        return JsonResponse({'error': 'JSON invalide'}, status=400)
    except Exception as e:
        print(f"❌ Erreur validation résumé global du document {doc_id}: {e}")
        return JsonResponse({'error': f'Erreur lors de la validation: {str(e)}'}, status=500)
    


@login_required
@user_passes_test(is_metadonneur)
def metadata_learning_dashboard(request):
    """Dashboard showing AI learning statistics with proper calculations"""
    try:
        from .models import MetadataFeedback, MetadataLearningMetrics
        
        total_feedbacks = MetadataFeedback.objects.count()
        
        if total_feedbacks == 0:
            return render(request, 'rawdocs/learning_dashboard.html', {
                'no_data': True
            })
        
        # Calculate average score
        avg_score = MetadataFeedback.objects.aggregate(
            avg=models.Avg('feedback_score')
        )['avg'] or 0
        
        # Field performance with percentages calculated
        field_stats = {}
        document_stats = {}  # NEW: Track per-document performance
        
        for feedback in MetadataFeedback.objects.all():
            corrections = feedback.corrections_made
            doc_id = feedback.document.id
            doc_title = feedback.document.title or f"Document {doc_id}"
            
            # Initialize document stats
            if doc_id not in document_stats:
                document_stats[doc_id] = {
                    'title': doc_title,
                    'correct': 0,
                    'wrong': 0,
                    'missed': 0,
                    'precision': 0
                }
            
            for kept in corrections.get('kept_correct', []):
                field = kept.get('field')
                if field not in field_stats:
                    field_stats[field] = {'correct': 0, 'wrong': 0, 'missed': 0}
                field_stats[field]['correct'] += 1
                document_stats[doc_id]['correct'] += 1
            
            for wrong in corrections.get('corrected_fields', []):
                field = wrong.get('field')
                if field not in field_stats:
                    field_stats[field] = {'correct': 0, 'wrong': 0, 'missed': 0}
                field_stats[field]['wrong'] += 1
                document_stats[doc_id]['wrong'] += 1
            
            for missed in corrections.get('missed_fields', []):
                field = missed.get('field')
                if field not in field_stats:
                    field_stats[field] = {'correct': 0, 'wrong': 0, 'missed': 0}
                field_stats[field]['missed'] += 1
                document_stats[doc_id]['missed'] += 1
        
        # Calculate precision percentages
        for field, stats in field_stats.items():
            total = stats['correct'] + stats['wrong'] + stats['missed']
            stats['precision'] = int((stats['correct'] / total * 100)) if total > 0 else 0
        
        for doc_id, stats in document_stats.items():
            total = stats['correct'] + stats['wrong'] + stats['missed']
            stats['precision'] = int((stats['correct'] / total * 100)) if total > 0 else 0
        
        # Get improvement trend
        feedbacks = MetadataFeedback.objects.order_by('created_at')
        improvement = 0
        if feedbacks.count() >= 2:
            first_score = feedbacks.first().feedback_score * 100
            last_score = feedbacks.last().feedback_score * 100
            improvement = int(last_score - first_score)
        
        return render(request, 'rawdocs/learning_dashboard.html', {
            'total_feedbacks': total_feedbacks,
            'avg_score': int(avg_score * 100),
            'field_stats': field_stats,
            'document_stats': document_stats,  # NEW: Pass document stats
            'improvement': improvement,
            'has_data': True
        })
        
    except Exception as e:
        print(f"Learning dashboard error: {e}")
        return render(request, 'rawdocs/learning_dashboard.html', {'error': str(e)})

@login_required 
def metadata_learning_api(request):
    """API for learning stats"""
    try:
        from .models import MetadataFeedback
        
        total = MetadataFeedback.objects.count()
        avg = MetadataFeedback.objects.aggregate(avg=models.Avg('feedback_score'))['avg'] or 0
        
        return JsonResponse({
            'total_feedbacks': total,
            'average_score': avg * 100,
            'learning_active': total > 0
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
    

from django.views.decorators.http import require_http_methods
from django.http import JsonResponse
from django.shortcuts import get_object_or_404

@require_http_methods(["POST"])
def clear_page_annotations(request, page_id):
    try:
        page = get_object_or_404(DocumentPage, id=page_id)
        page.annotations.all().delete()
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
@user_passes_test(is_dev_metier)
@csrf_exempt
def save_document_json_devmetier(request, doc_id):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Méthode non autorisée'}, status=405)

    try:
        # 1) Charger le doc validé (même logique qu’avant)
        document = get_object_or_404(RawDocument, id=doc_id, is_validated=True)

        # 2) Sécurité groupe
        if not is_dev_metier(request.user):
            return JsonResponse({'success': False, 'error': 'Permission refusée'}, status=403)

        # 3) Parser JSON
        data = json.loads(request.body)
        json_content = data.get('json_content')
        if json_content is None:
            return JsonResponse({'success': False, 'error': 'Contenu JSON manquant'}, status=400)
        try:
            json.dumps(json_content)  # vérifie sérialisable
        except (TypeError, ValueError):
            return JsonResponse({'success': False, 'error': 'JSON invalide'}, status=400)

        # 4) Historique (ancien JSON)
        old_json = document.global_annotations_json or {}

        # 5) Sauvegarde côté Django (SQLite) - complète (pas update_fields)
        document.global_annotations_json = json_content
        document.save()

        # 6) Sauvegarde Mongo (UPsert par rawdoc_id)
        mongo_write = {'matched': None, 'modified': None, 'upserted': None}
        if _mongo_coll is not None:
            payload = {
                "rawdoc_id": int(doc_id),
                "title": getattr(document, "title", None),
                "file_name": getattr(document, "file_name", None),
                "owner": getattr(getattr(document, "owner", None), "username", None),
                "total_pages": getattr(document, "total_pages", None),
                "global_annotations_json": json_content,
                "updated_at": timezone.now(),
                "updated_by": request.user.username,
            }
            res = _mongo_coll.update_one(
                {"rawdoc_id": int(doc_id)},
                {"$set": payload},
                upsert=True,
            )
            mongo_write = {
                'matched': res.matched_count,
                'modified': res.modified_count,
                'upserted': getattr(res, "upserted_id", None) is not None
            }
            print(f"✅ Mongo write d{doc_id}: matched={res.matched_count} modified={res.modified_count} upserted={getattr(res,'upserted_id',None)}")
        else:
            print("⚠️ Pas de connexion Mongo (_mongo_coll is None)")

        # 7) Historique application
        GlobalSummaryEditHistory.objects.create(
            document=document,
            old_summary=json.dumps(old_json),
            new_summary=json.dumps(json_content),
            modified_by=request.user,
            reason='Modification JSON via éditeur Dev Métier'
        )

        return JsonResponse({
            'success': True,
            'message': 'JSON global sauvegardé dans MongoDB',
            'mongo': mongo_write
        })

    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'JSON invalide dans la requête'}, status=400)
    except Exception as e:
        print(f"❌ Erreur sauvegarde JSON document {doc_id}: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
