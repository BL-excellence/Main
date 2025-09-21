# Add to rawdocs/models.py

class DocumentAnnotationFeedback(models.Model):
    """Tracks feedback on document-wide AI annotations"""
    document = models.ForeignKey('RawDocument', on_delete=models.CASCADE, related_name='annotation_feedbacks')
    annotator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    
    # Original AI predictions
    ai_annotations = models.JSONField(
        help_text="Original AI annotations before human validation"
    )
    
    # Human corrections
    human_annotations = models.JSONField(
        help_text="Final annotations after human validation/corrections"
    )
    
    # Feedback analysis
    corrections = models.JSONField(
        help_text="Analysis of what was corrected"
    )
    
    # Stats
    total_annotations = models.IntegerField(default=0)
    correct_annotations = models.IntegerField(default=0)
    wrong_annotations = models.IntegerField(default=0)
    missed_annotations = models.IntegerField(default=0)
    feedback_score = models.FloatField(default=0.0)
    
    # Analysis of correction patterns
    correction_patterns = models.JSONField(
        null=True, blank=True,
        help_text="Patterns in how annotations were corrected"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['document', 'annotator']
        

# Add to rawdocs/rlhf_learning.py

class RLHFGroqAnnotator:
    """Enhanced RLHF learner for document-wide annotations"""
    
    def process_document_feedback(
        self,
        document_id: int,
        ai_annotations: List[Dict],
        human_annotations: List[Dict],
        annotator_id: int
    ) -> Dict[str, Any]:
        """
        Process feedback for document-wide annotations.
        Analyzes differences between AI and human annotations to improve the model.
        """
        try:
            # Group annotations by page
            ai_by_page = self._group_annotations_by_page(ai_annotations)
            human_by_page = self._group_annotations_by_page(human_annotations)
            
            # Analyze corrections page by page
            corrections_by_page = {}
            stats = {
                'total': 0,
                'correct': 0,
                'wrong': 0,
                'missed': 0
            }
            
            for page_num in set(ai_by_page.keys()) | set(human_by_page.keys()):
                page_ai = ai_by_page.get(page_num, [])
                page_human = human_by_page.get(page_num, [])
                
                # Analyze this page's annotations
                page_analysis = self._analyze_annotations(page_ai, page_human)
                corrections_by_page[page_num] = page_analysis
                
                # Update stats
                stats['total'] += len(page_human)
                stats['correct'] += len(page_analysis['kept_correct'])
                stats['wrong'] += len(page_analysis['corrected'])
                stats['missed'] += len(page_analysis['missed'])
            
            # Calculate overall feedback score
            if stats['total'] > 0:
                feedback_score = stats['correct'] / stats['total']
            else:
                feedback_score = 0.0
                
            # Save feedback
            from .models import DocumentAnnotationFeedback, RawDocument
            
            feedback = DocumentAnnotationFeedback.objects.create(
                document_id=document_id,
                annotator_id=annotator_id,
                ai_annotations=ai_annotations,
                human_annotations=human_annotations,
                corrections=corrections_by_page,
                total_annotations=stats['total'],
                correct_annotations=stats['correct'],
                wrong_annotations=stats['wrong'],
                missed_annotations=stats['missed'],
                feedback_score=feedback_score
            )
            
            # Update document stats
            document = RawDocument.objects.get(id=document_id)
            document.ai_annotations_validated = True
            document.ai_annotations_validated_at = timezone.now()
            document.ai_annotations_validated_by_id = annotator_id
            document.ai_annotations_feedback_score = feedback_score * 100
            document.update_ai_annotation_stats()
            document.save()
            
            return {
                'feedback_id': feedback.id,
                'feedback_score': feedback_score,
                'stats': stats,
                'corrections_summary': corrections_by_page
            }
            
        except Exception as e:
            print(f"Error processing document feedback: {e}")
            return {
                'error': str(e),
                'feedback_score': 0.0,
                'stats': {
                    'total': 0,
                    'correct': 0,
                    'wrong': 0,
                    'missed': 0
                }
            }
            
    def _group_annotations_by_page(self, annotations: List[Dict]) -> Dict[int, List[Dict]]:
        """Group annotations by page number"""
        by_page = {}
        for ann in annotations:
            page = ann.get('page_num', 1)
            if page not in by_page:
                by_page[page] = []
            by_page[page].append(ann)
        return by_page
        
    def _analyze_annotations(
        self,
        ai_annotations: List[Dict],
        human_annotations: List[Dict]
    ) -> Dict[str, List[Dict]]:
        """Analyze differences between AI and human annotations"""
        # Convert to sets for comparison
        ai_texts = {(a['text'], a['type']) for a in ai_annotations}
        human_texts = {(h['text'], h['type']) for h in human_annotations}
        
        # Find corrections
        kept = ai_texts & human_texts
        corrected = ai_texts - human_texts
        missed = human_texts - ai_texts
        
        # Get full annotation details
        kept_anns = [a for a in ai_annotations if (a['text'], a['type']) in kept]
        corrected_anns = [a for a in ai_annotations if (a['text'], a['type']) in corrected]
        missed_anns = [h for h in human_annotations if (h['text'], h['type']) in missed]
        
        return {
            'kept_correct': kept_anns,
            'corrected': corrected_anns,
            'missed': missed_anns
        }