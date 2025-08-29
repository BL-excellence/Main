from django.shortcuts import render
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from rawdocs.models import MetadataFeedback, RawDocument, MetadataLearningMetrics
from django.db.models import Avg, Count
from collections import defaultdict

@staff_member_required
@login_required
def ai_performance_hub(request):
    return render(request, 'admin/ai_performance_hub.html')

@staff_member_required  
@login_required
def metadata_learning_dashboard(request):
    try:
        # Get all metadata feedbacks
        feedbacks = MetadataFeedback.objects.all().order_by('created_at')
        
        if not feedbacks.exists():
            context = {
                'no_data': True,
                'avg_score': 0,
                'total_feedbacks': 0,
                'improvement': 0,
                'field_stats': {},
                'document_stats': {}
            }
        else:
            # Calculate average score
            avg_score = feedbacks.aggregate(avg=Avg('feedback_score'))['avg'] or 0
            avg_score = avg_score * 100  # Convert to percentage
            total_feedbacks = feedbacks.count()
            
            # Calculate improvement (comparing first vs last feedbacks)
            first_feedback = feedbacks.first()
            last_feedback = feedbacks.last()
            improvement = 0
            
            if first_feedback and last_feedback and total_feedbacks > 1:
                first_score = first_feedback.feedback_score * 100
                last_score = last_feedback.feedback_score * 100
                if first_score > 0:
                    improvement = ((last_score - first_score) / first_score) * 100
            
            # Calculate field-level statistics
            field_stats = defaultdict(lambda: {'correct': 0, 'wrong': 0, 'missed': 0, 'precision': 0})
            
            for feedback in feedbacks:
                corrections = feedback.corrections_made
                
                # Count correct fields
                for item in corrections.get('kept_correct', []):
                    field_stats[item['field']]['correct'] += 1
                
                # Count wrong fields (corrected + removed)
                for item in corrections.get('corrected_fields', []):
                    field_stats[item['field']]['wrong'] += 1
                for item in corrections.get('removed_fields', []):
                    field_stats[item['field']]['wrong'] += 1
                
                # Count missed fields
                for item in corrections.get('missed_fields', []):
                    field_stats[item['field']]['missed'] += 1
            
            # Calculate precision for each field
            for field, stats in field_stats.items():
                total = stats['correct'] + stats['wrong'] + stats['missed']
                if total > 0:
                    stats['precision'] = round((stats['correct'] / total) * 100)
                else:
                    stats['precision'] = 0
            
            # Calculate document-level statistics
            document_stats = defaultdict(lambda: {
                'title': '',
                'correct': 0, 
                'wrong': 0, 
                'missed': 0, 
                'precision': 0
            })
            
            for feedback in feedbacks:
                doc_id = feedback.document.id
                document_stats[doc_id]['title'] = feedback.document.title or 'Sans titre'
                
                corrections = feedback.corrections_made
                
                # Count corrections for this document
                correct_count = len(corrections.get('kept_correct', []))
                wrong_count = len(corrections.get('corrected_fields', [])) + len(corrections.get('removed_fields', []))
                missed_count = len(corrections.get('missed_fields', []))
                
                document_stats[doc_id]['correct'] += correct_count
                document_stats[doc_id]['wrong'] += wrong_count
                document_stats[doc_id]['missed'] += missed_count
            
            # Calculate precision for each document
            for doc_id, stats in document_stats.items():
                total = stats['correct'] + stats['wrong'] + stats['missed']
                if total > 0:
                    stats['precision'] = round((stats['correct'] / total) * 100)
                else:
                    stats['precision'] = 0
            
            context = {
                'no_data': False,
                'avg_score': round(avg_score, 1),
                'total_feedbacks': total_feedbacks,
                'improvement': round(improvement, 1),
                'field_stats': dict(field_stats),
                'document_stats': dict(document_stats)
            }
            
    except Exception as e:
        context = {
            'error': str(e),
            'no_data': False,
            'avg_score': 0,
            'total_feedbacks': 0,
            'improvement': 0,
            'field_stats': {},
            'document_stats': {}
        }
    
    return render(request, 'admin/metadata_learning_dashboard.html', context)