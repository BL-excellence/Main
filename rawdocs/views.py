# rawdocs/views.py
from django.contrib.auth import views as auth_views
from rawdocs.groq_annotation_system import GroqAnnotator
from django.contrib import messages
from django.views.decorators.csrf import csrf_exempt
import os
import json
from PyPDF2 import PdfReader
from datetime import datetime
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth import authenticate, login
from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
import requests
from django.db import models 

# Define URLForm here since it's missing
class URLForm(forms.Form):
    pdf_url = forms.URLField(
        label="URL du PDF",
        widget=forms.URLInput(attrs={
            'placeholder': 'https://example.com/document.pdf',
            'class': 'upload-cell__input'
        })
    )

class RegisterForm(UserCreationForm):
    email = forms.EmailField(required=True)
    
    class Meta:
        model = User
        fields = ("username", "email", "password1", "password2")
    
    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        if commit:
            user.save()
        return user

# Import utils with proper error handling
try:
    from .utils import extract_metadonnees, extract_full_text
except ImportError:
    def extract_metadonnees(file_path, url):
        return {"title": "Unknown", "type": "unknown"}
    def extract_full_text(file_path):
        return "Text extraction not available"

from .models import RawDocument, DocumentPage, AnnotationType, Annotation, AnnotationSession


def is_annotateur(user):
    return user.groups.filter(name="Annotateur").exists()

def is_metadonneur(user):
    return user.groups.filter(name="Metadonneur").exists()

class CustomLoginView(auth_views.LoginView):
    """Custom login view with role-based redirects"""
    template_name = 'registration/login.html'
    
    def get_success_url(self):
        user = self.request.user
        
        # Check user groups and redirect accordingly
        user_groups = user.groups.all()
        if user_groups.exists():
            group_name = user_groups.first().name
            if group_name == "Metadonneur":
                return '/upload/'
            elif group_name == "Annotateur":
                return '/annotation/'
            elif group_name == "Expert":
                return '/annotation/'  # Or expert dashboard
        
        # Default fallback
        return '/upload/'

def register(request):
    """User registration view"""
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            uname = form.cleaned_data.get('username')
            pwd = form.cleaned_data.get('password1')
            user = authenticate(username=uname, password=pwd)
            login(request, user)
            
            # Redirect based on user role
            user_groups = user.groups.all()
            if user_groups.exists():
                group_name = user_groups.first().name
                if group_name == "Metadonneur":
                    return redirect('rawdocs:upload')
                elif group_name == "Annotateur":
                    return redirect('rawdocs:annotation_dashboard')
                elif group_name == "Expert":
                    return redirect('rawdocs:annotation_dashboard')
            
            return redirect('rawdocs:upload')
    else:
        form = RegisterForm()
    return render(request, 'registration/register.html', {'form': form})

@login_required(login_url='rawdocs:login')
@user_passes_test(is_metadonneur, login_url='rawdocs:login')
def upload_pdf(request):
    """Upload PDF from URL"""
    form = URLForm(request.POST or None)
    context = {'form': form}

    if request.method == 'POST' and form.is_valid():
        url = form.cleaned_data['pdf_url']
        try:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()

            # Save PDF
            ts = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = os.path.basename(url) or 'document.pdf'
            rd = RawDocument(url=url, owner=request.user)
            rd.file.save(os.path.join(ts, filename), ContentFile(resp.content))
            rd.save()

            # Extract metadata and text
            metadata = extract_metadonnees(rd.file.path, rd.url)
            extracted_text = extract_full_text(rd.file.path)

            context.update({
                'doc': rd,
                'metadata': metadata,
                'extracted_text': extracted_text,
            })
            
            messages.success(request, f"Document '{filename}' importé avec succès!")
            
        except requests.RequestException as e:
            messages.error(request, f"Erreur lors du téléchargement: {e}")
        except Exception as e:
            messages.error(request, f"Erreur lors du traitement: {e}")

    return render(request, 'rawdocs/upload.html', context)

@login_required(login_url='rawdocs:login')
@user_passes_test(is_metadonneur, login_url='rawdocs:login')
def document_list(request):
    """List all documents imported by the current user"""
    documents = RawDocument.objects.filter(owner=request.user).order_by('-created_at')
    return render(request, 'rawdocs/document_list.html', {
        'documents': documents
    })

@login_required(login_url='rawdocs:login')
@user_passes_test(is_metadonneur, login_url='rawdocs:login')
def document_metadata(request, doc_id):
    """Return JSON metadata for a document"""
    rd = get_object_or_404(RawDocument, id=doc_id, owner=request.user)
    metadata = extract_metadonnees(rd.file.path, rd.url)
    return JsonResponse(metadata)

@login_required(login_url='rawdocs:login')
@user_passes_test(is_metadonneur, login_url='rawdocs:login')
def delete_document(request, doc_id):
    """Delete a document"""
    rd = get_object_or_404(RawDocument, id=doc_id, owner=request.user)
    if request.method == 'POST':
        rd.delete()
        return redirect('rawdocs:document_list')
    # Redirect to list on GET
    return redirect('rawdocs:document_list')

@login_required(login_url='rawdocs:login')
@user_passes_test(is_metadonneur, login_url='rawdocs:login')
def validate_document(request, doc_id):
    """Validate a document for annotation"""
    document = get_object_or_404(RawDocument, id=doc_id, owner=request.user)
    
    if request.method == 'POST':
        # Extract pages if not already done
        if not document.pages_extracted:
            try:
                reader = PdfReader(document.file.path)
                pages_text = [page.extract_text() or "" for page in reader.pages]
                # Create DocumentPage objects
                for page_num, page_text in enumerate(pages_text, 1):
                    DocumentPage.objects.create(
                        document=document,
                        page_number=page_num,
                        raw_text=page_text,
                        cleaned_text=page_text  # Could add more cleaning here
                    )
                
                document.total_pages = len(pages_text)
                document.pages_extracted = True
                
            except Exception as e:
                messages.error(request, f"Erreur lors de l'extraction des pages: {e}")
                return redirect('rawdocs:document_list')
        
        # Mark as validated
        document.is_validated = True
        document.validated_at = datetime.now()
        document.save()
        
        # Create annotation types if they don't exist - FIXED INDENTATION
        types_data = [
            ('procedure_type', 'Code de Variation', '#3b82f6'),
            ('authority', 'Autorité', '#8b5cf6'),
            ('legal_reference', 'Référence Légale', '#f59e0b'),
            ('required_document', 'Document Requis', '#ef4444'),
            ('required_condition', 'Condition Requise', '#06b6d4'),
            ('delay', 'Délai', '#84cc16'),
        ]
        
        for name, display_name, color in types_data:
            AnnotationType.objects.get_or_create(
                name=name, 
                defaults={
                    'display_name': display_name, 
                    'color': color
                }
            )
        
        messages.success(request, f"Document validé et prêt pour l'annotation ({document.total_pages} pages)")
        return redirect('rawdocs:document_list')
    
    return render(request, 'rawdocs/validate_document.html', {'document': document})

@login_required(login_url='rawdocs:login')
@user_passes_test(is_annotateur, login_url='rawdocs:login') 
def annotation_dashboard(request):
    """Dashboard for annotators"""
    # Get validated documents available for annotation
    validated_docs = RawDocument.objects.filter(
        is_validated=True,
        pages_extracted=True
    ).order_by('-validated_at')
    
    # Pagination
    paginator = Paginator(validated_docs, 10)
    page_number = request.GET.get('page')
    documents = paginator.get_page(page_number)
    
    return render(request, 'rawdocs/annotation_dashboard.html', {
        'documents': documents
    })

@login_required(login_url='rawdocs:login')
@user_passes_test(is_annotateur, login_url='rawdocs:login')
def annotate_document(request, doc_id):
    """Main annotation interface"""
    document = get_object_or_404(RawDocument, id=doc_id, is_validated=True)
    
    # Get all pages
    pages = document.pages.all()
    
    # Get current page
    current_page_num = int(request.GET.get('page', 1))
    current_page = get_object_or_404(DocumentPage, document=document, page_number=current_page_num)
    
    # Get annotation types
    annotation_types = AnnotationType.objects.all()
    
    # Get existing annotations for this page
    existing_annotations = current_page.annotations.all().order_by('start_pos')
    
    context = {
        'document': document,
        'pages': pages,
        'current_page': current_page,
        'annotation_types': annotation_types,
        'existing_annotations': existing_annotations,
        'total_pages': document.total_pages,
    }
    
    return render(request, 'rawdocs/annotate_document.html', context)


@login_required(login_url='rawdocs:login')
@user_passes_test(is_annotateur, login_url='rawdocs:login')
def save_manual_annotation(request):
    """Save a manual annotation"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    
    try:
        data = json.loads(request.body)
        
        page = get_object_or_404(DocumentPage, id=data['page_id'])
        annotation_type = get_object_or_404(AnnotationType, id=data['type_id'])
        
        # Create annotation - manual annotations are 100% confidence
        annotation = Annotation.objects.create(
            page=page,
            annotation_type=annotation_type,
            start_pos=data['start_pos'],
            end_pos=data['end_pos'],
            selected_text=data['selected_text'],
            confidence_score=100.0,  # Manual annotations are 100%
            created_by=request.user
        )
        
        return JsonResponse({
            'success': True,
            'annotation_id': annotation.id,
            'message': 'Annotation manuelle sauvegardée'
        })
        
    except Exception as e:
        return JsonResponse({
            'error': f'Erreur lors de la sauvegarde: {str(e)}'
        }, status=500)

@login_required(login_url='rawdocs:login')
def get_page_annotations(request, page_id):
    """Get all annotations for a page"""
    page = get_object_or_404(DocumentPage, id=page_id)
    
    annotations = []
    for ann in page.annotations.all().order_by('start_pos'):
        annotations.append({
            'id': ann.id,
            'start_pos': ann.start_pos,
            'end_pos': ann.end_pos,
            'selected_text': ann.selected_text,
            'type': ann.annotation_type.name,
            'type_display': ann.annotation_type.display_name,
            'color': ann.annotation_type.color,
            'confidence': ann.confidence_score,
            'reasoning': ann.ai_reasoning,
            'is_validated': ann.is_validated,
        })
    
    return JsonResponse({
        'annotations': annotations,
        'page_text': page.cleaned_text
    })

@login_required(login_url='rawdocs:login')
@user_passes_test(is_annotateur, login_url='rawdocs:login')
def delete_annotation(request, annotation_id):
    """Delete an annotation"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    
    try:
        annotation = get_object_or_404(Annotation, id=annotation_id)
        
        # Check permission (can only delete own annotations or if expert)
        if (annotation.created_by != request.user and 
            not request.user.groups.filter(name="Expert").exists()):
            return JsonResponse({'error': 'Permission denied'}, status=403)
        
        annotation.delete()
        
        return JsonResponse({
            'success': True,
            'message': 'Annotation supprimée'
        })
        
    except Exception as e:
        return JsonResponse({
            'error': f'Erreur lors de la suppression: {str(e)}'
        }, status=500)
    
    
from .rlhf_learning import RLHFGroqAnnotator


@login_required
@csrf_exempt
def validate_page_annotations(request, page_id):
    """
    Validate page annotations and trigger RLHF learning
    """
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
    """
    Get AI learning progress dashboard
    """
    try:
        from .models import AILearningMetrics, AnnotationFeedback
        
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

@login_required
@csrf_exempt  
def ai_annotate_page_groq(request, page_id):
    """
    Enhanced AI annotation with RLHF learning
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    
    try:
        page = get_object_or_404(DocumentPage, id=page_id)
        
        # Clear existing annotations for this page
        page.annotations.all().delete()
        
        # Initialize RLHF annotator (now with learning)
        rlhf_annotator = RLHFGroqAnnotator()
        
        print(f"🚀 Processing page {page.page_number} with RLHF-enhanced GROQ...")
        
        # Use adaptive prompt based on learning
        adaptive_prompt = rlhf_annotator.create_adaptive_prompt(page.cleaned_text)
        
        # Call GROQ with enhanced prompt
        response = rlhf_annotator.call_groq_api(adaptive_prompt)
        
        if response:
            annotations = rlhf_annotator.parse_groq_response(response, page.page_number)
        else:
            annotations = []
        
        # Store AI annotations in session for later feedback processing
        request.session[f'ai_annotations_{page_id}'] = annotations
        
        # Save to database
        saved_count = 0
        for ann_data in annotations:
            try:
                # Get or create annotation type
                ann_type, created = AnnotationType.objects.get_or_create(
                    name=ann_data['type'],
                    defaults={
                        'display_name': ann_data['type'].replace('_', ' ').title(),
                        'color': '#3b82f6',
                        'description': f"RLHF GROQ Llama 3.3 70B detected {ann_data['type']}"
                    }
                )
                
                # Create annotation
                annotation = Annotation.objects.create(
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
        
        # Update page status
        if saved_count > 0:
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
        print(f"❌ Enhanced GROQ annotation error: {e}")
        return JsonResponse({
            'error': f'Erreur RLHF GROQ: {str(e)}'
        }, status=500)