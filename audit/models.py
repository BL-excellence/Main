# audit/models.py (CORRIGÉ)
from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()


class AuditLog(models.Model):
    ACTION_CHOICES = [
        ('upload', 'Document uploadé'),
        ('extract', 'Métadonnées extraites'),
        ('annotate', 'Annotation créée'),
        ('validate', 'Validation effectuée'),
        ('reject', 'Rejet effectué'),
        ('modify', 'Modification effectuée'),
        ('assign', 'Assignation effectuée'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    document = models.ForeignKey('documents.Document', on_delete=models.CASCADE, null=True, blank=True)
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    description = models.TextField()
    metadata = models.JSONField(default=dict)
    timestamp = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        verbose_name = "Log d'audit"
        verbose_name_plural = "Logs d'audit"
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.user.username} - {self.get_action_display()} - {self.timestamp}"


class DocumentVersion(models.Model):
    document = models.ForeignKey('documents.Document', on_delete=models.CASCADE, related_name='versions')
    version_number = models.CharField(max_length=20)
    description = models.TextField()
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    data_snapshot = models.JSONField(default=dict)

    class Meta:
        verbose_name = "Version de document"
        verbose_name_plural = "Versions de documents"
        ordering = ['-created_at']
        unique_together = ['document', 'version_number']

    def __str__(self):
        return f"{self.document.title} - v{self.version_number}"
