# rawdocs/models.py

from os.path import join
from datetime import datetime
from django.db import models
from django.conf import settings
from django.contrib.auth.models import User
def pdf_upload_to(instance, filename):
    """
    Place chaque PDF téléchargé dans un sous-dossier horodaté.
    Ex. "20250626_143502/mon_document.pdf"
    """
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    return join(ts, filename)

class RawDocument(models.Model):
    url        = models.URLField(help_text="URL d'origine du PDF")
    file       = models.FileField(upload_to=pdf_upload_to, help_text="Fichier PDF téléchargé")
    created_at = models.DateTimeField(auto_now_add=True)

    # On autorise NULL/blank pour ne pas casser les anciens enregistrements
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='raw_documents',
        null=True,
        blank=True,
        help_text="Utilisateur qui a téléchargé ce document"
    )
    title = models.TextField(blank=True, help_text="Titre du document")
    doc_type = models.CharField(max_length=100, blank=True, help_text="Type du document (guide, rapport, etc.)")
    language = models.CharField(max_length=10, blank=True, help_text="Langue détectée (fr, en...)")
    version = models.CharField(max_length=50, blank=True, help_text="Version extraite")
    source = models.CharField(max_length=255, blank=True, help_text="Nom de l'organisation (ex: EMA, FDA...)")
    publication_date = models.CharField(max_length=100, blank=True, help_text="Date de publication")
    context = models.TextField(blank=True, help_text="Contexte extrait (2 phrases max)")
    country = models.CharField(max_length=100, blank=True, help_text="Pays détecté (GPE ou domaine TLD)")

    def __str__(self):
        owner_name = self.owner.username if self.owner else "–"
        return f"PDF #{self.pk} ({self.url}) – par {owner_name}"


class MetadataLog(models.Model):
    document = models.ForeignKey('RawDocument', on_delete=models.CASCADE)
    field_name = models.CharField(max_length=100)
    old_value = models.TextField(null=True, blank=True)
    new_value = models.TextField(null=True, blank=True)
    modified_at = models.DateTimeField(auto_now_add=True)
    modified_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)

    def __str__(self):
        return f"{self.field_name}: {self.old_value} -> {self.new_value}"