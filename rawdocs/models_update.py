# Add to rawdocs/models.py

class RawDocument(models.Model):
    # ... existing fields ...
    
    # Document-wide AI annotation status
    ai_annotated = models.BooleanField(default=False, help_text="Document has been processed by AI for annotations")
    ai_annotated_at = models.DateTimeField(null=True, blank=True, help_text="When AI annotation was last performed")
    
    # AI annotation metadata
    ai_annotation_source = models.CharField(
        max_length=50, 
        blank=True,
        help_text="Source of AI annotations (e.g. 'groq_llama3.3_70b')"
    )
    ai_annotation_confidence = models.FloatField(
        null=True, blank=True,
        help_text="Overall confidence score for AI annotations (0-100)"
    )
    ai_annotation_metadata = models.JSONField(
        null=True, blank=True,
        help_text="Additional metadata about the AI annotation process"
    )
    
    # User feedback on AI annotations
    ai_annotations_validated = models.BooleanField(
        default=False,
        help_text="AI annotations have been validated by a user"
    )
    ai_annotations_validated_at = models.DateTimeField(
        null=True, blank=True,
        help_text="When AI annotations were validated"
    )
    ai_annotations_validated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='validated_ai_annotations'
    )
    ai_annotations_feedback_score = models.FloatField(
        null=True, blank=True,
        help_text="User feedback score for AI annotations (0-100)"
    )
    
    # Usage statistics
    total_ai_annotations = models.IntegerField(
        default=0,
        help_text="Total number of AI-generated annotations"
    )
    accepted_ai_annotations = models.IntegerField(
        default=0,
        help_text="Number of AI annotations accepted by users"
    )
    rejected_ai_annotations = models.IntegerField(
        default=0,
        help_text="Number of AI annotations rejected by users"
    )
    modified_ai_annotations = models.IntegerField(
        default=0,
        help_text="Number of AI annotations modified by users"
    )

    def update_ai_annotation_stats(self):
        """Update AI annotation statistics"""
        from django.db.models import Count, Q
        
        stats = self.annotations.filter(source='ai').aggregate(
            total=Count('id'),
            accepted=Count('id', filter=Q(validation_status='validated')),
            rejected=Count('id', filter=Q(validation_status='rejected')),
            modified=Count('id', filter=Q(modified_by_human=True))
        )
        
        self.total_ai_annotations = stats['total']
        self.accepted_ai_annotations = stats['accepted']
        self.rejected_ai_annotations = stats['rejected']
        self.modified_ai_annotations = stats['modified']
        
        if self.total_ai_annotations > 0:
            self.ai_annotation_confidence = (
                (self.accepted_ai_annotations / self.total_ai_annotations) * 100
            )
        
        self.save(update_fields=[
            'total_ai_annotations',
            'accepted_ai_annotations', 
            'rejected_ai_annotations',
            'modified_ai_annotations',
            'ai_annotation_confidence'
        ])