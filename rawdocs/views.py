# rawdocs/views.py
import os
import json
import requests
from datetime import datetime
from PyPDF2 import PdfReader

from django.shortcuts import render, redirect, get_object_or_404
from django.core.files.base import ContentFile
from django.http import JsonResponse
from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User, Group
from django.core.paginator import Paginator
from django.db import transaction
from django import forms
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth import views as auth_views
from django.db import models

from .models import (
    RawDocument, MetadataLog,
    DocumentPage, AnnotationType,
    Annotation, AnnotationSession,
    AILearningMetrics, AnnotationFeedback
)
from .utils import extract_metadonnees, extract_full_text
from .annotation_utils import extract_pages_from_pdf, create_annotation_types
from .groq_annotation_system import GroqAnnotator
from .rlhf_learning import RLHFGroqAnnotator

# ——— Forms ——————————————————————————————————————————

class UploadForm(forms.Form):
    pdf_url = forms.URLField(required=False,
                             widget=forms.URLInput(attrs={'placeholder': 'https://…', 'class': 'upload-cell__input'}))
    pdf_file = forms.FileField(required=False)


class RegisterForm(UserCreationForm):
    email = forms.EmailField(required=True)
    role = forms.ChoiceField(choices=[
        ("Metadonneur", "Métadonneur"),
        ("Annotateur", "Annotateur"),
        ("Expert", "Expert"),
    ], label="Profil")

    class Meta:
        model = User
        fields = ("username", "email", "role", "password1", "password2")

    def save(self, commit=True):
        user = super().save(commit)
        user.email = self.cleaned_data["email"]
        group = Group.objects.get(name=self.cleaned_data["role"])
        user.groups.add(group)
        if commit:
            user.save()
        return user


class URLForm(forms.Form):
    pdf_url = forms.URLField(label="URL du PDF",
                             widget=forms.URLInput(attrs={'placeholder': 'https://…', 'class': 'upload-cell__input'}))


class MetadataEditForm(forms.Form):
    title = forms.CharField(required=False)
    type = forms.CharField(required=False)
    publication_date = forms.DateField(required=False,
                                     widget=forms.DateInput(attrs={'type': 'date'}))
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


# ——— Authentication ————————————————————————————————————

class CustomLoginView(auth_views.LoginView):
    template_name = 'registration/login.html'

    def get_success_url(self):
        user = self.request.user
        if is_metadonneur(user):
            return '/dashboard/'
        elif is_annotateur(user) or is_expert(user):
            return '/annotation/'
        return '/upload/'


def register(request):
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            uname, pwd = form.cleaned_data['username'], form.cleaned_data['password1']
            login(request, authenticate(username=uname, password=pwd))
            grp = form.cleaned_data['role']
            return redirect(grp == "Metadonneur" and 'rawdocs:upload' or 'rawdocs:annotation_dashboard')
    else:
        form = RegisterForm()
    return render(request, 'registration/register.html', {'form': form})


# ——— Métadonneur Views ——————————————————————————————

@login_required(login_url='rawdocs:login')
@user_passes_test(is_metadonneur)
def dashboard_view(request):
    docs = RawDocument.objects.filter(owner=request.user).order_by('-created_at')
    context = {
        'documents': docs,
        'total_scrapped': docs.count(),
        'total_planned': 150,
        'total_completed': 0,
        'in_progress': 12,
        'pie_data': json.dumps([15, 8, 12, 5, 3]),
        'bar_data': json.dumps([150, docs.count(), 0, 12]),
    }
    return render(request, 'rawdocs/dashboard.html', context)


@login_required(login_url='rawdocs:login')
@user_passes_test(is_metadonneur)
def upload_pdf(request):
    form = UploadForm(request.POST or None, request.FILES or None)
    context = {'form': form}
    if request.method == 'POST' and form.is_valid():
        try:
            # fichier local prioritaire
            if form.cleaned_data.get('pdf_file'):
                f = form.cleaned_data['pdf_file']
                rd = RawDocument(owner=request.user)
                rd.file.save(f.name, f)
            else:
                url = form.cleaned_data['pdf_url']
                resp = requests.get(url, timeout=30)
                resp.raise_for_status()
                ts, fn = datetime.now().strftime('%Y%m%d_%H%M%S'), os.path.basename(url)
                rd = RawDocument(url=url, owner=request.user)
                rd.file.save(os.path.join(ts, fn), ContentFile(resp.content))
            
            rd.save()
            metadata = extract_metadonnees(rd.file.path, rd.url or "")
            text = extract_full_text(rd.file.path)
            context.update({'doc': rd, 'metadata': metadata, 'extracted_text': text})
            messages.success(request, "Document importé avec succès!")
            
        except Exception as e:
            messages.error(request, f"Erreur lors de l'import: {str(e)}")
            
    return render(request, 'rawdocs/upload.html', context)


@login_required(login_url='rawdocs:login')
@user_passes_test(is_metadonneur)
def document_list(request):
    docs = RawDocument.objects.filter(owner=request.user).order_by('-created_at')
    for d in docs: d.basename = os.path.basename(d.file.name)
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
        messages.success(request, "Document supprimé avec succès!")
    return redirect('rawdocs:document_list')


@login_required(login_url='rawdocs:login')
@user_passes_test(is_metadonneur)
def edit_metadata(request, doc_id):
    rd = get_object_or_404(RawDocument, id=doc_id, owner=request.user)
    metadata = extract_metadonnees(rd.file.path, rd.url or "")
    
    if request.method == 'POST':
        form = MetadataEditForm(request.POST)
        if form.is_valid():
            for f, v in form.cleaned_data.items():
                old = metadata.get(f)
                if str(old) != str(v):
                    MetadataLog.objects.create(
                        document=rd, field_name=f,
                        old_value=old, new_value=v,
                        modified_by=request.user
                    )
                    metadata[f] = v
            messages.success(request, "Métadonnées mises à jour!")
            return redirect('rawdocs:document_list')
    else:
        form = MetadataEditForm(initial=metadata)
        
    logs = MetadataLog.objects.filter(document=rd).order_by('-modified_at')
    return render(request, 'rawdocs/edit_metadata.html', {
        'form': form, 'metadata': metadata,
        'doc': rd, 'logs': logs
    })


@login_required(login_url='rawdocs:login')
@user_passes_test(is_metadonneur)
def validate_document(request, doc_id):
    document = get_object_or_404(RawDocument, id=doc_id, owner=request.user)
    
    if request.method == 'POST':
        if not document.pages_extracted:
            try:
                pages = extract_pages_from_pdf(document.file.path)
                for i, text in enumerate(pages, 1):
                    DocumentPage.objects.create(
                        document=document,
                        page_number=i,
                        raw_text=text,
                        cleaned_text=text
                    )
                document.total_pages = len(pages)
                document.pages_extracted = True
            except Exception as e:
                messages.error(request, f"Erreur lors de l'extraction des pages: {e}")
                return redirect('rawdocs:document_list')
        
        document.is_validated = True
        document.validated_at = datetime.now()
        document.save()
        
        # Create standard annotation types
        create_annotation_types()
        
        messages.success(request, f"Document validé ({document.total_pages} pages). Prêt pour annotation!")
        return redirect('rawdocs:document_list')
    
    return render(request, 'rawdocs/validate_document.html', {'document': document})


# ——— Annotateur Views ——————————————————————————————

@login_required(login_url='rawdocs:login')
@user_passes_test(is_annotateur)
def annotation_dashboard(request):
    docs = RawDocument.objects.filter(is_validated=True, pages_extracted=True).order_by('-validated_at')
    paginator = Paginator(docs, 10)
    page = request.GET.get('page')
    return render(request, 'rawdocs/annotation_dashboard.html', {
        'documents': paginator.get_page(page)
    })


@login_required(login_url='rawdocs:login')
@user_passes_test(is_annotateur)
def annotate_document(request, doc_id):
    document = get_object_or_404(RawDocument, id=doc_id, is_validated=True)
    pages = document.pages.all()
    pnum = int(request.GET.get('page', 1))
    page_obj = get_object_or_404(DocumentPage, document=document, page_number=pnum)
    
    # Ajoutez ce contexte si vous utilisez l'URL dans le template
    from django.urls import reverse
    validate_url = reverse('rawdocs:validate_page_annotations', args=[page_obj.id])
    
    return render(request, 'rawdocs/annotate_document.html', {
        'document': document,
        'pages': pages,
        'current_page': page_obj,
        'annotation_types': AnnotationType.objects.all(),
        'existing_annotations': page_obj.annotations.all().order_by('start_pos'),
        'total_pages': document.total_pages,
        'validate_page_url': validate_url,  # Passez l'URL au template
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
        
        return JsonResponse({'success': True, 'annotation_id': ann.id})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required(login_url='rawdocs:login')
def get_page_annotations(request, page_id):
    page = get_object_or_404(DocumentPage, id=page_id)
    anns = [{
        'id': a.id,
        'start_pos': a.start_pos,
        'end_pos': a.end_pos,
        'selected_text': a.selected_text,
        'type': a.annotation_type.name,
        'type_display': a.annotation_type.display_name,
        'color': a.annotation_type.color,
        'confidence': a.confidence_score,
        'reasoning': a.ai_reasoning,
        'is_validated': a.is_validated,
    } for a in page.annotations.all().order_by('start_pos')]
    
    return JsonResponse({
        'annotations': anns,
        'page_text': page.cleaned_text
    })


@login_required(login_url='rawdocs:login')
@user_passes_test(is_annotateur)
def delete_annotation(request, annotation_id):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    
    ann = get_object_or_404(Annotation, id=annotation_id)
    if ann.created_by != request.user and not is_expert(request.user):
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    ann.delete()
    return JsonResponse({'success': True})


@login_required
@csrf_exempt
def ai_annotate_page_groq(request, page_id):
    """Enhanced AI annotation with RLHF learning"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        page = get_object_or_404(DocumentPage, id=page_id)

        # Initialize RLHF annotator
        try:
            annotator = RLHFGroqAnnotator()
        except ValueError as e:
            return JsonResponse({
                'error': 'GROQ_API_KEY environment variable not set. Get free key from https://console.groq.com/',
                'details': str(e)
            }, status=500)

        print(f"🚀 Processing page {page.page_number} with RLHF-enhanced GROQ...")

        # 1) Créer le prompt adaptatif
        adaptive_prompt = annotator.create_adaptive_prompt(page.cleaned_text)

        # 2) Appel à l'API GROQ
        response = annotator.call_groq_api(adaptive_prompt)

        # 3) Parse de la réponse
        annotations = annotator.parse_groq_response(response, page.page_number) if response else []

        # Store AI annotations in session for later feedback
        request.session[f'ai_annotations_{page_id}'] = annotations

        # Sauvegarde en base
        saved_count = 0
        for ann_data in annotations:
            try:
                ann_type, _ = AnnotationType.objects.get_or_create(
                    name=ann_data['type'],
                    defaults={
                        'display_name': ann_data['type'].replace('_', ' ').title(),
                        'color': '#3b82f6',
                        'description': f"RLHF GROQ Llama 3.3 70B detected {ann_data['type']}"
                    }
                )
                Annotation.objects.create(
                    page=page,
                    annotation_type=ann_type,
                    start_pos=ann_data.get('start_pos', 0),
                    end_pos=ann_data.get('end_pos', 0),
                    selected_text=ann_data.get('text', ''),
                    confidence_score=ann_data.get('confidence', 0.8) * 100,
                    ai_reasoning=ann_data.get('reasoning', 'RLHF-enhanced GROQ classification'),
                    created_by=request.user
                )
                saved_count += 1
            except Exception as e:
                print(f"❌ Error saving annotation: {e}")
                continue

        if saved_count:
            page.is_annotated = True
            page.annotated_at = datetime.now()
            page.annotated_by = request.user
            page.save()

        return JsonResponse({
            'success': True,
            'annotations_created': saved_count,
            'message': f'{saved_count} annotations créées avec RLHF GROQ! 🧠',
            'learning_enhanced': True,
            'cost_estimate': 0.0
        })

    except Exception as e:
        print(f"❌ GROQ annotation error: {e}")
        return JsonResponse({'error': f'Erreur GROQ: {str(e)}'}, status=500)


@login_required
@csrf_exempt
def validate_page_annotations(request, page_id):
    """Validate page annotations and trigger RLHF learning"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    
    try:
        page = get_object_or_404(DocumentPage, id=page_id)
        
        # Get AI annotations that were made before human corrections
        ai_session_data = request.session.get(f'ai_annotations_{page_id}', [])
        
        # Get current annotations (after human corrections)
        current_annotations = []
        for annotation in page.annotations.all():
            current_annotations.append({
                'text': annotation.selected_text,
                'type': annotation.annotation_type.name,
                'start_pos': annotation.start_pos,
                'end_pos': annotation.end_pos,
                'confidence': annotation.confidence_score / 100.0
            })
        
        # Initialize RLHF annotator
        rlhf_annotator = RLHFGroqAnnotator()
        
        # Process human feedback
        feedback_result = rlhf_annotator.process_human_feedback(
            page_id=page_id,
            ai_annotations=ai_session_data,
            human_annotations=current_annotations,
            annotator_id=request.user.id
        )
        
        # Mark page as validated
        page.is_validated_by_human = True
        page.human_validated_at = datetime.now()
        page.validated_by = request.user
        page.save()
        
        # Clear the session data
        if f'ai_annotations_{page_id}' in request.session:
            del request.session[f'ai_annotations_{page_id}']
        
        return JsonResponse({
            'success': True,
            'message': f'Page validée! Score: {feedback_result["feedback_score"]:.0%} - IA améliorée! 🎓',
            'feedback_score': feedback_result['feedback_score'],
            'corrections_summary': feedback_result['corrections_summary'],
            'ai_improved': True
        })
        
    except Exception as e:
        print(f"❌ Validation error: {e}")
        return JsonResponse({
            'error': f'Erreur lors de la validation: {str(e)}'
        }, status=500)


@login_required
def get_learning_dashboard(request):
    """Get AI learning progress dashboard"""
    try:
        # Get recent metrics
        recent_metrics = AILearningMetrics.objects.order_by('-created_at')[:10]
        
        # Calculate improvement over time
        improvement_data = []
        for metric in recent_metrics:
            improvement_data.append({
                'date': metric.created_at.strftime('%Y-%m-%d'),
                'f1_score': metric.f1_score,
                'precision': metric.precision_score,
                'recall': metric.recall_score
            })
        
        # Get feedback summary
        total_feedbacks = AnnotationFeedback.objects.count()
        avg_feedback_score = AnnotationFeedback.objects.aggregate(
            avg_score=models.Avg('feedback_score')
        )['avg_score'] or 0
        
        # Get entity performance
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