# annotation/models.py (CORRIGÉ)
from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()


class EntityType(models.Model):
    name = models.CharField(max_length=100)
    color = models.CharField(max_length=7)
    description = models.TextField(blank=True)

    class Meta:
        verbose_name = "Type d'entité"
        verbose_name_plural = "Types d'entités"

    def __str__(self):
        return self.name


class Annotation(models.Model):
    STATUS_CHOICES = [
        ('detected', 'Détectée'),
        ('validated', 'Validée'),
        ('rejected', 'Rejetée'),
        ('modified', 'Modifiée'),
    ]

    document = models.ForeignKey('documents.Document', on_delete=models.CASCADE, related_name='annotations')
    entity_type = models.ForeignKey(EntityType, on_delete=models.CASCADE)
    text = models.TextField()
    start_position = models.IntegerField()
    end_position = models.IntegerField()
    confidence_score = models.FloatField(default=0.0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='detected')

    # Qui a créé/modifié l'annotation
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_annotations')
    validated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                     related_name='validated_annotations')

    # Annotation automatique ou manuelle
    is_automatic = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Annotation"
        verbose_name_plural = "Annotations"
        ordering = ['start_position']

    def __str__(self):
        return f"{self.text} ({self.entity_type.name})"