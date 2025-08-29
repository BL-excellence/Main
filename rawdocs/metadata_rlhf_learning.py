# rawdocs/metadata_rlhf_learning.py
"""
Metadata RLHF Learning System - learns from metadonneur corrections
"""
import json
import os
from collections import defaultdict
from datetime import datetime
from .utils import extract_metadonnees

class MetadataRLHFLearner:
    def __init__(self):
        self.learning_data = {}
        self.load_learning_data()
    
    def load_learning_data(self):
        try:
            from .models import MetadataLearningMetrics
            latest = MetadataLearningMetrics.objects.order_by('-created_at').first()
            if latest:
                self.learning_data = latest.field_performance
        except Exception as e:
            print(f"No previous metadata learning data: {e}")
    
    # ADD THIS MISSING METHOD:
    def process_metadata_feedback(self, document, ai_metadata, human_metadata, user):
        """Process feedback from metadonneur corrections"""
        corrections = self.analyze_metadata_corrections(ai_metadata, human_metadata)
        feedback_score = self.calculate_metadata_feedback_score(corrections)
        
        # Save feedback
        self.save_metadata_feedback(document, ai_metadata, human_metadata, corrections, feedback_score, user)
        
        # Update learning models
        self.update_metadata_learning_models(corrections)
        
        return {
            'feedback_score': feedback_score,
            'corrections_summary': corrections,
            'learning_updated': True
        }
    
    def analyze_metadata_corrections(self, ai_metadata, human_metadata):
        corrections = {
            'kept_correct': [],      # AI extracted and human kept
            'corrected_fields': [],  # AI extracted but human changed
            'missed_fields': [],     # AI missed but human added
            'removed_fields': []     # AI extracted but human removed
        }
        
        standard_fields = ['title', 'type', 'publication_date', 'version', 'source', 'context', 'country', 'language', 'url_source']
        
        for field in standard_fields:
            ai_value = ai_metadata.get(field, '').strip()
            human_value = human_metadata.get(field, '').strip()
            
            if ai_value and human_value:
                if ai_value == human_value:
                    corrections['kept_correct'].append({'field': field, 'value': ai_value})
                else:
                    corrections['corrected_fields'].append({
                        'field': field, 
                        'ai_value': ai_value, 
                        'human_value': human_value
                    })
            elif ai_value and not human_value:
                corrections['removed_fields'].append({'field': field, 'ai_value': ai_value})
            elif not ai_value and human_value:
                corrections['missed_fields'].append({'field': field, 'human_value': human_value})
        
        return corrections
    
    def calculate_metadata_feedback_score(self, corrections):
        correct = len(corrections['kept_correct'])
        wrong = len(corrections['corrected_fields']) + len(corrections['removed_fields'])
        missed = len(corrections['missed_fields'])
        
        total_expected = correct + wrong + missed
        if total_expected == 0:
            return 1.0
        
        return correct / total_expected
    
    def save_metadata_feedback(self, document, ai_metadata, human_metadata, corrections, score, user):
        try:
            from .models import MetadataFeedback
            MetadataFeedback.objects.update_or_create(
                document=document,
                metadonneur=user,
                defaults={
                    'ai_metadata_before': ai_metadata,
                    'human_metadata_after': human_metadata,
                    'corrections_made': corrections,
                    'feedback_score': score
                }
            )
        except Exception as e:
            print(f"Error saving metadata feedback: {e}")
    
    def update_metadata_learning_models(self, corrections):
        try:
            from .models import MetadataLearningMetrics
            
            # Calculate field-level performance
            field_performance = defaultdict(lambda: {'correct': 0, 'wrong': 0, 'missed': 0})
            
            for item in corrections['kept_correct']:
                field_performance[item['field']]['correct'] += 1
            
            for item in corrections['corrected_fields'] + corrections['removed_fields']:
                field_performance[item['field']]['wrong'] += 1
            
            for item in corrections['missed_fields']:
                field_performance[item['field']]['missed'] += 1
            
            # Save metrics
            MetadataLearningMetrics.objects.create(
                field_performance=dict(field_performance),
                total_feedbacks=1,
                avg_feedback_score=self.calculate_metadata_feedback_score(corrections)
            )
            
        except Exception as e:
            print(f"Error updating metadata learning: {e}")