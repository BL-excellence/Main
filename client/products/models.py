from django.db import models
from django.urls import reverse
from django.contrib.auth.models import User 
import json
from datetime import datetime, timedelta

class Product(models.Model):
    STATUS_CHOICES = [
        ('commercialise', 'Commercialisé'),
        ('developpement', 'En développement'),
        ('arrete', 'Arrêté'),
    ]
    
    name = models.CharField(max_length=255, verbose_name="Nom du produit")
    active_ingredient = models.CharField(max_length=255, verbose_name="Principe actif")
    dosage = models.CharField(max_length=100, verbose_name="Dosage")
    form = models.CharField(max_length=100, verbose_name="Forme")
    therapeutic_area = models.CharField(max_length=200, verbose_name="Zone thérapeutique")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='developpement')
    source_document = models.ForeignKey(
        'rawdocs.RawDocument', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        verbose_name="Document source",
        help_text="Document original ayant généré ce produit"
    )
    additional_annotations = models.JSONField(default=dict, blank=True, verbose_name="Annotations supplémentaires")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Produit"
        verbose_name_plural = "Produits"
        ordering = ['-created_at']
    
    def __str__(self):
        return self.name
    
    def get_absolute_url(self):
        return reverse('products:detail', kwargs={'pk': self.pk})

class ProductSpecification(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='specifications')
    country_code = models.CharField(max_length=3, verbose_name="Code pays")
    amm_number = models.CharField(max_length=100, verbose_name="Numéro AMM")
    approval_date = models.DateField(verbose_name="Date d'approbation")
    renewal_date = models.DateField(verbose_name="Date de renouvellement")
    
    # Documents status
    ctd_dossier_complete = models.BooleanField(default=False, verbose_name="Dossier CTD complet")
    gmp_certificate = models.BooleanField(default=False, verbose_name="Certificat GMP")
    inspection_report = models.BooleanField(default=False, verbose_name="Rapport d'inspection")
    rcp_etiquetage = models.BooleanField(default=False, verbose_name="RCP et étiquetage")
    
    is_active = models.BooleanField(default=True, verbose_name="Actif")
    
    class Meta:
        verbose_name = "Spécification produit"
        verbose_name_plural = "Spécifications produits"
        unique_together = ['product', 'country_code']
    
    def __str__(self):
        return f"{self.product.name} - {self.country_code}"

class ManufacturingSite(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='sites')
    country = models.CharField(max_length=100, verbose_name="Pays")
    city = models.CharField(max_length=100, verbose_name="Ville")
    site_name = models.CharField(max_length=255, verbose_name="Nom du site")
    
    gmp_certified = models.BooleanField(default=False, verbose_name="Certifié GMP")
    gmp_expiry = models.DateField(null=True, blank=True, verbose_name="Expiration GMP")
    last_audit = models.DateField(null=True, blank=True, verbose_name="Dernier audit")
    
    class Meta:
        verbose_name = "Site de fabrication"
        verbose_name_plural = "Sites de fabrication"
    
    def __str__(self):
        return f"{self.site_name} - {self.city}"

class ProductVariation(models.Model):
    VARIATION_TYPES = [
        ('type_ia', 'Type IA'),
        ('type_ib', 'Type IB'),
        ('type_ii', 'Type II'),
    ]
    
    STATUS_CHOICES = [
        ('soumis', 'Soumis'),
        ('en_cours', 'En cours'),
        ('approuve', 'Approuvé'),
        ('rejete', 'Rejeté'),
    ]
    
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='variations')
    variation_type = models.CharField(max_length=10, choices=VARIATION_TYPES)
    title = models.CharField(max_length=255, verbose_name="Titre")
    description = models.TextField(verbose_name="Description")
    submission_date = models.DateField(verbose_name="Date de soumission")
    approval_date = models.DateField(null=True, blank=True, verbose_name="Date d'approbation")
    additional_annotations = models.JSONField(default=dict, blank=True, verbose_name="Annotations supplémentaires")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='soumis')
    
    class Meta:
        verbose_name = "Variation produit"
        verbose_name_plural = "Variations produits"
        ordering = ['-submission_date']
    
    def __str__(self):
        return f"{self.title} - {self.variation_type}"
    
class CloudProvider(models.TextChoices):
    GOOGLE_DRIVE = 'google_drive', 'Google Drive'
    ONEDRIVE = 'onedrive', 'Microsoft OneDrive'
    SHAREPOINT = 'sharepoint', 'SharePoint'
    DROPBOX = 'dropbox', 'Dropbox'
    BOX = 'box', 'Box'

class CloudConnection(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='cloud_connections')
    provider = models.CharField(max_length=20, choices=CloudProvider.choices)
    connection_name = models.CharField(max_length=100)
    encrypted_access_token = models.BinaryField()
    data_residency_eu = models.BooleanField(default=False)
    scc_agreement = models.BooleanField(default=False)
    dpa_signed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    audit_log = models.JSONField(default=dict)
    data_subjects_categories = models.JSONField(default=list, help_text="Catégories de personnes concernées")
    sub_processors = models.JSONField(default=list, help_text="Liste des sous-traitants de second rang")
    expires_at = models.DateTimeField(null=True, blank=True)
    encrypted_refresh_token = models.BinaryField(null=True, blank=True)
    last_used = models.DateTimeField(null=True, blank=True)
    
    data_subject_information_method = models.CharField(max_length=200, blank=True)
    privacy_notice_provider = models.CharField(max_length=100, choices=[
        ('client', 'Client LFB'),
        ('provider', 'Fournisseur Cloud'),
        ('both', 'Les deux')
    ], default='client')
    
    # RGPD - Mesures techniques et organisationnelles
    technical_measures = models.JSONField(default=dict, help_text="Mesures techniques de sécurité")
    organizational_measures = models.JSONField(default=dict, help_text="Mesures organisationnelles")
    
    # RGPD - Transferts hors UE
    transfers_outside_eu = models.BooleanField(default=False)
    transfer_countries = models.JSONField(default=list, help_text="Pays de transfert")
    transfer_safeguards = models.CharField(max_length=100, choices=[
        ('adequacy_decision', 'Décision d\'adéquation'),
        ('scc', 'Clauses Contractuelles Types'),
        ('bcr', 'Binding Corporate Rules'),
        ('derogation', 'Dérogation')
    ], blank=True)
    
    # Validation obligatoire
    rgpd_compliance_validated = models.BooleanField(default=False)
    rgpd_validation_date = models.DateTimeField(null=True, blank=True)
    rgpd_validator = models.CharField(max_length=200, blank=True)

class ProductECTDFile(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='ectd_files')
    cloud_connection = models.ForeignKey(CloudConnection, on_delete=models.CASCADE)
    file_name = models.CharField(max_length=255)
    file_path = models.CharField(max_length=500)
    ectd_section = models.CharField(max_length=10, blank=True)
    uploaded_by = models.ForeignKey(User, on_delete=models.CASCADE)
    uploaded_at = models.DateTimeField(auto_now_add=True)
