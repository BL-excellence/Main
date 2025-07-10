# # # # # documents/models.py (CORRIGÉ)
# # # # from django.db import models
# # # # from django.contrib.auth import get_user_model
# # # #
# # # # User = get_user_model()
# # # #
# # # #
# # # # class DocumentType(models.Model):
# # # #     name = models.CharField(max_length=100)
# # # #     description = models.TextField(blank=True)
# # # #     color = models.CharField(max_length=7, default='#007bff')  # Hex color
# # # #
# # # #     class Meta:
# # # #         verbose_name = "Type de document"
# # # #         verbose_name_plural = "Types de documents"
# # # #
# # # #     def __str__(self):
# # # #         return self.name
# # # #
# # # #
# # # # class DocumentContext(models.Model):
# # # #     name = models.CharField(max_length=100)
# # # #     description = models.TextField(blank=True)
# # # #     color = models.CharField(max_length=7, default='#17a2b8')
# # # #
# # # #     class Meta:
# # # #         verbose_name = "Contexte de document"
# # # #         verbose_name_plural = "Contextes de documents"
# # # #
# # # #     def __str__(self):
# # # #         return self.name
# # # #
# # # #
# # # # class Document(models.Model):
# # # #     STATUS_CHOICES = [
# # # #         ('uploaded', 'Uploadé'),
# # # #         ('extracting', 'En extraction'),
# # # #         ('extracted', 'Extrait'),
# # # #         ('annotating', 'En annotation'),
# # # #         ('annotated', 'Annoté'),
# # # #         ('validating', 'En validation'),
# # # #         ('validated', 'Validé'),
# # # #         ('refused', 'Refusé'),
# # # #         ('completed', 'Terminé'),
# # # #     ]
# # # #
# # # #     title = models.CharField(max_length=255)
# # # #     file = models.FileField(upload_to='documents/%Y/%m/')
# # # #     file_type = models.CharField(max_length=10, blank=True)
# # # #     document_type = models.ForeignKey(DocumentType, on_delete=models.SET_NULL, null=True)
# # # #     context = models.ForeignKey(DocumentContext, on_delete=models.SET_NULL, null=True)
# # # #     status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='uploaded')
# # # #
# # # #     # Métadonnées extraites
# # # #     extracted_title = models.CharField(max_length=255, blank=True)
# # # #     language = models.CharField(max_length=10, blank=True)
# # # #     publication_date = models.DateField(null=True, blank=True)
# # # #     source = models.CharField(max_length=255, blank=True)
# # # #     version = models.CharField(max_length=50, blank=True)
# # # #     source_url = models.URLField(blank=True)
# # # #
# # # #     # Assignations
# # # #     assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
# # # #                                     related_name='assigned_documents')
# # # #     validated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
# # # #                                      related_name='validated_documents')
# # # #
# # # #     # Timestamps
# # # #     created_at = models.DateTimeField(auto_now_add=True)
# # # #     updated_at = models.DateTimeField(auto_now=True)
# # # #     extraction_started_at = models.DateTimeField(null=True, blank=True)
# # # #     extraction_completed_at = models.DateTimeField(null=True, blank=True)
# # # #
# # # #     class Meta:
# # # #         verbose_name = "Document"
# # # #         verbose_name_plural = "Documents"
# # # #         ordering = ['-created_at']
# # # #
# # # #     def __str__(self):
# # # #         return self.title
# # #
# # # # documents/models.py - Version avec deux dates EMA distinctes
# # # from django.db import models
# # # from django.contrib.auth import get_user_model
# # #
# # # User = get_user_model()
# # #
# # #
# # # class DocumentType(models.Model):
# # #     name = models.CharField(max_length=100)
# # #     description = models.TextField(blank=True)
# # #     color = models.CharField(max_length=7, default='#007bff')
# # #
# # #     class Meta:
# # #         verbose_name = "Type de document"
# # #         verbose_name_plural = "Types de documents"
# # #
# # #     def __str__(self):
# # #         return self.name
# # #
# # #
# # # class DocumentContext(models.Model):
# # #     name = models.CharField(max_length=100)
# # #     description = models.TextField(blank=True)
# # #     color = models.CharField(max_length=7, default='#17a2b8')
# # #
# # #     class Meta:
# # #         verbose_name = "Contexte de document"
# # #         verbose_name_plural = "Contextes de documents"
# # #
# # #     def __str__(self):
# # #         return self.name
# # #
# # #
# # # class Document(models.Model):
# # #     STATUS_CHOICES = [
# # #         ('uploaded', 'Uploadé'),
# # #         ('extracting', 'En extraction'),
# # #         ('extracted', 'Extrait'),
# # #         ('annotating', 'En annotation'),
# # #         ('annotated', 'Annoté'),
# # #         ('validating', 'En validation'),
# # #         ('validated', 'Validé'),
# # #         ('refused', 'Refusé'),
# # #         ('completed', 'Terminé'),
# # #     ]
# # #
# # #     title = models.CharField(max_length=255)
# # #     file = models.FileField(upload_to='documents/%Y/%m/')
# # #     file_type = models.CharField(max_length=10, blank=True)
# # #     document_type = models.ForeignKey(DocumentType, on_delete=models.SET_NULL, null=True)
# # #     context = models.ForeignKey(DocumentContext, on_delete=models.SET_NULL, null=True)
# # #     status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='uploaded')
# # #
# # #     # Métadonnées extraites du document
# # #     extracted_title = models.CharField(max_length=255, blank=True)
# # #     language = models.CharField(max_length=10, blank=True)
# # #     source = models.CharField(max_length=255, blank=True)
# # #     version = models.CharField(max_length=50, blank=True)
# # #     source_url = models.URLField(blank=True)
# # #
# # #     # === DATES DE PUBLICATION EMA (DEUX DATES DISTINCTES) ===
# # #
# # #     # Date "First published" du site EMA (première publication officielle)
# # #     original_publication_date = models.DateField(
# # #         null=True,
# # #         blank=True,
# # #         verbose_name="Première publication EMA",
# # #         help_text="Date 'First published' récupérée du site EMA (première publication officielle)"
# # #     )
# # #
# # #     # Date "Last updated" du site EMA (dernière mise à jour)
# # #     ema_publication_date = models.DateField(
# # #         null=True,
# # #         blank=True,
# # #         verbose_name="Dernière mise à jour EMA",
# # #         help_text="Date 'Last updated' récupérée du site EMA (dernière mise à jour)"
# # #     )
# # #
# # #     # URL du document sur le site EMA
# # #     ema_source_url = models.URLField(
# # #         blank=True,
# # #         verbose_name="URL source EMA",
# # #         help_text="URL du document sur le site de l'EMA"
# # #     )
# # #
# # #     # Titre tel qu'il apparaît sur le site EMA
# # #     ema_title = models.CharField(
# # #         max_length=500,
# # #         blank=True,
# # #         verbose_name="Titre EMA",
# # #         help_text="Titre du document tel qu'il apparaît sur le site EMA"
# # #     )
# # #
# # #     # Référence EMA (ex: EMEA-H-19984/03 Rev. 112)
# # #     ema_reference = models.CharField(
# # #         max_length=100,
# # #         blank=True,
# # #         verbose_name="Référence EMA",
# # #         help_text="Numéro de référence EMA du document"
# # #     )
# # #
# # #     # Métadonnées de la recherche EMA
# # #     ema_search_performed = models.BooleanField(
# # #         default=False,
# # #         verbose_name="Recherche EMA effectuée",
# # #         help_text="Indique si la recherche automatique sur le site EMA a été effectuée"
# # #     )
# # #
# # #     ema_search_results_count = models.IntegerField(
# # #         default=0,
# # #         verbose_name="Nombre de résultats EMA",
# # #         help_text="Nombre de résultats trouvés lors de la recherche EMA"
# # #     )
# # #
# # #     ema_similarity_score = models.FloatField(
# # #         default=0.0,
# # #         verbose_name="Score de similarité EMA",
# # #         help_text="Score de similarité entre le titre du document et le résultat EMA (0.0 à 1.0)"
# # #     )
# # #
# # #     ema_last_search_date = models.DateTimeField(
# # #         null=True,
# # #         blank=True,
# # #         verbose_name="Dernière recherche EMA",
# # #         help_text="Date et heure de la dernière recherche automatique EMA"
# # #     )
# # #
# # #     # Assignations
# # #     assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
# # #                                     related_name='assigned_documents')
# # #     validated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
# # #                                      related_name='validated_documents')
# # #
# # #     # Timestamps
# # #     created_at = models.DateTimeField(auto_now_add=True)
# # #     updated_at = models.DateTimeField(auto_now=True)
# # #     extraction_started_at = models.DateTimeField(null=True, blank=True)
# # #     extraction_completed_at = models.DateTimeField(null=True, blank=True)
# # #
# # #     class Meta:
# # #         verbose_name = "Document"
# # #         verbose_name_plural = "Documents"
# # #         ordering = ['-created_at']
# # #
# # #     def __str__(self):
# # #         return self.title
# # #
# # #     @property
# # #     def current_publication_date(self):
# # #         """Retourne la date de publication la plus récente (dernière mise à jour EMA)"""
# # #         return self.ema_publication_date or self.original_publication_date
# # #
# # #     @property
# # #     def has_ema_data(self):
# # #         """Indique si le document a des données EMA"""
# # #         return bool(self.ema_source_url and (self.original_publication_date or self.ema_publication_date))
# # #
# # #     @property
# # #     def has_been_updated(self):
# # #         """Indique si le document a été mis à jour après sa première publication"""
# # #         if not self.original_publication_date or not self.ema_publication_date:
# # #             return False
# # #         return self.ema_publication_date > self.original_publication_date
# # #
# # #     @property
# # #     def update_duration_days(self):
# # #         """Nombre de jours entre la première publication et la dernière mise à jour"""
# # #         if not self.has_been_updated:
# # #             return 0
# # #         return (self.ema_publication_date - self.original_publication_date).days
# # #
# # #     @property
# # #     def publication_status(self):
# # #         """Statut de publication basé sur les dates EMA"""
# # #         if not self.ema_search_performed:
# # #             return "Recherche EMA en attente"
# # #
# # #         if not self.original_publication_date and not self.ema_publication_date:
# # #             return "Non trouvé sur EMA"
# # #
# # #         if self.has_been_updated:
# # #             return f"Mis à jour (+{self.update_duration_days} jours)"
# # #         elif self.ema_publication_date:
# # #             return "Version actuelle"
# # #         elif self.original_publication_date:
# # #             return "Première version"
# # #         else:
# # #             return "Statut inconnu"
# # #
# # #     @property
# # #     def publication_status_class(self):
# # #         """Classe CSS pour le statut de publication"""
# # #         if not self.ema_search_performed:
# # #             return "secondary"
# # #
# # #         if not self.original_publication_date and not self.ema_publication_date:
# # #             return "warning"
# # #
# # #         if self.has_been_updated:
# # #             return "info"  # Bleu pour les mises à jour
# # #         elif self.current_publication_date:
# # #             return "success"  # Vert pour les versions actuelles
# # #         else:
# # #             return "secondary"
# # #
# # #     def get_ema_info(self):
# # #         """Retourne un dictionnaire avec toutes les informations EMA"""
# # #         return {
# # #             'has_ema_data': self.has_ema_data,
# # #             'first_published': self.original_publication_date,
# # #             'last_updated': self.ema_publication_date,
# # #             'current_date': self.current_publication_date,
# # #             'has_been_updated': self.has_been_updated,
# # #             'update_duration_days': self.update_duration_days,
# # #             'status': self.publication_status,
# # #             'status_class': self.publication_status_class,
# # #             'ema_url': self.ema_source_url,
# # #             'ema_title': self.ema_title,
# # #             'ema_reference': self.ema_reference,
# # #             'similarity_score': self.ema_similarity_score,
# # #             'search_performed': self.ema_search_performed,
# # #             'results_count': self.ema_search_results_count,
# # #             'last_search': self.ema_last_search_date,
# # #         }
# # #
# # #     def get_timeline_events(self):
# # #         """Retourne une chronologie des événements de publication"""
# # #         events = []
# # #
# # #         if self.original_publication_date:
# # #             events.append({
# # #                 'date': self.original_publication_date,
# # #                 'type': 'first_published',
# # #                 'description': 'Première publication EMA',
# # #                 'icon': 'bi-calendar-plus',
# # #                 'class': 'success'
# # #             })
# # #
# # #         if self.ema_publication_date and self.has_been_updated:
# # #             events.append({
# # #                 'date': self.ema_publication_date,
# # #                 'type': 'last_updated',
# # #                 'description': f'Mise à jour EMA (+{self.update_duration_days} jours)',
# # #                 'icon': 'bi-arrow-clockwise',
# # #                 'class': 'info'
# # #             })
# # #
# # #         if self.ema_last_search_date:
# # #             events.append({
# # #                 'date': self.ema_last_search_date.date(),
# # #                 'type': 'search_performed',
# # #                 'description': 'Recherche EMA effectuée',
# # #                 'icon': 'bi-search',
# # #                 'class': 'secondary'
# # #             })
# # #
# # #         return sorted(events, key=lambda x: x['date'], reverse=True)
# # #
# # #     # Méthodes pour compatibilité avec l'ancien code
# # #     @property
# # #     def publication_date(self):
# # #         """Alias pour compatibilité - retourne la date actuelle"""
# # #         return self.current_publication_date
# # #
# # #     def get_publication_info(self):
# # #         """Alias pour compatibilité"""
# # #         return self.get_ema_info()
# #
# # from django.db import models
# # from django.contrib.auth import get_user_model
# #
# # User = get_user_model()
# #
# # class DocumentType(models.Model):
# #     name = models.CharField(max_length=100)
# #     description = models.TextField(blank=True)
# #     color = models.CharField(max_length=7, default='#007bff')
# #
# #     class Meta:
# #         verbose_name = "Type de document"
# #         verbose_name_plural = "Types de documents"
# #
# #     def __str__(self):
# #         return self.name
# #
# # class DocumentContext(models.Model):
# #     name = models.CharField(max_length=100)
# #     description = models.TextField(blank=True)
# #     color = models.CharField(max_length=7, default='#17a2b8')
# #
# #     class Meta:
# #         verbose_name = "Contexte de document"
# #         verbose_name_plural = "Contextes de documents"
# #
# #     def __str__(self):
# #         return self.name
# #
# # class Document(models.Model):
# #     STATUS_CHOICES = [
# #         ('uploaded', 'Uploadé'),
# #         ('extracting', 'En extraction'),
# #         ('extracted', 'Extrait'),
# #         ('annotating', 'En annotation'),
# #         ('annotated', 'Annoté'),
# #         ('validating', 'En validation'),
# #         ('validated', 'Validé'),
# #         ('refused', 'Refusé'),
# #         ('completed', 'Terminé'),
# #     ]
# #
# #     title = models.CharField(max_length=255)
# #     file = models.FileField(upload_to='documents/%Y/%m/')
# #     file_type = models.CharField(max_length=10, blank=True)
# #     document_type = models.ForeignKey(DocumentType, on_delete=models.SET_NULL, null=True)
# #     context = models.ForeignKey(DocumentContext, on_delete=models.SET_NULL, null=True)
# #     status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='uploaded')
# #
# #     # Métadonnées extraites
# #     extracted_title = models.CharField(max_length=255, blank=True)
# #     language = models.CharField(max_length=10, blank=True)
# #     source = models.CharField(max_length=255, blank=True)
# #     version = models.CharField(max_length=50, blank=True, null=True)
# #     source_url = models.URLField(blank=True)
# #
# #     # === Champs EMA ===
# #     original_publication_date = models.DateField(
# #         null=True, blank=True,
# #         verbose_name="Première publication EMA",
# #         help_text="Date 'First published' récupérée du site EMA (première publication officielle)"
# #     )
# #     ema_publication_date = models.DateField(
# #         null=True, blank=True,
# #         verbose_name="Dernière mise à jour EMA",
# #         help_text="Date 'Last updated' récupérée du site EMA (dernière mise à jour)"
# #     )
# #     ema_source_url = models.URLField(
# #         blank=True,
# #         verbose_name="URL source EMA",
# #         help_text="URL du document sur le site de l'EMA"
# #     )
# #     ema_title = models.CharField(
# #         max_length=500, blank=True,
# #         verbose_name="Titre EMA",
# #         help_text="Titre du document tel qu'il apparaît sur le site EMA"
# #     )
# #     ema_reference = models.CharField(
# #         max_length=100, blank=True,
# #         verbose_name="Référence EMA",
# #         help_text="Numéro de référence EMA du document"
# #     )
# #     ema_search_performed = models.BooleanField(
# #         default=False,
# #         verbose_name="Recherche EMA effectuée",
# #         help_text="Indique si la recherche automatique sur le site EMA a été effectuée"
# #     )
# #     ema_search_results_count = models.IntegerField(
# #         default=0,
# #         verbose_name="Nombre de résultats EMA",
# #         help_text="Nombre de résultats trouvés lors de la recherche EMA"
# #     )
# #     ema_similarity_score = models.FloatField(
# #         default=0.0,
# #         verbose_name="Score de similarité EMA",
# #         help_text="Score de similarité entre le titre du document et le résultat EMA (0.0 à 1.0)"
# #     )
# #     ema_last_search_date = models.DateTimeField(
# #         null=True, blank=True,
# #         verbose_name="Dernière recherche EMA",
# #         help_text="Date et heure de la dernière recherche automatique EMA"
# #     )
# #
# #     # Assignations
# #     assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
# #                                     related_name='assigned_documents')
# #     validated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
# #                                      related_name='validated_documents')
# #
# #     # Timestamps
# #     created_at = models.DateTimeField(auto_now_add=True)
# #     updated_at = models.DateTimeField(auto_now=True)
# #     extraction_started_at = models.DateTimeField(null=True, blank=True)
# #     extraction_completed_at = models.DateTimeField(null=True, blank=True)
# #
# #     class Meta:
# #         verbose_name = "Document"
# #         verbose_name_plural = "Documents"
# #         ordering = ['-created_at']
# #
# #     def __str__(self):
# #         return self.title
# #
# #     @property
# #     def current_publication_date(self):
# #         """Retourne la date de publication la plus récente (dernière mise à jour EMA)"""
# #         return self.ema_publication_date or self.original_publication_date
# #
# #     @property
# #     def has_ema_data(self):
# #         """Indique si le document a des données EMA valides"""
# #         return bool(self.ema_source_url and (self.original_publication_date or self.ema_publication_date))
# #
# #     @property
# #     def has_been_updated(self):
# #         """Indique si le document a été mis à jour après sa première publication"""
# #         if not self.original_publication_date or not self.ema_publication_date:
# #             return False
# #         return self.ema_publication_date > self.original_publication_date
# #
# #     @property
# #     def update_duration_days(self):
# #         """Nombre de jours entre la première publication et la dernière mise à jour"""
# #         if not self.has_been_updated:
# #             return 0
# #         return (self.ema_publication_date - self.original_publication_date).days
# #
# #     @property
# #     def publication_status(self):
# #         """Statut de publication basé sur les dates EMA"""
# #         if not self.ema_search_performed:
# #             return "Recherche EMA en attente"
# #
# #         if not self.original_publication_date and not self.ema_publication_date:
# #             return "Non trouvé sur EMA"
# #
# #         if self.has_been_updated:
# #             return f"Mis à jour (+{self.update_duration_days} jours)"
# #         elif self.ema_publication_date:
# #             return "Version actuelle"
# #         elif self.original_publication_date:
# #             return "Première version"
# #         else:
# #             return "Statut inconnu"
# #
# #     @property
# #     def publication_status_class(self):
# #         """Classe CSS pour le statut de publication"""
# #         if not self.ema_search_performed:
# #             return "secondary"
# #
# #         if not self.original_publication_date and not self.ema_publication_date:
# #             return "warning"
# #
# #         if self.has_been_updated:
# #             return "info"  # Bleu pour les mises à jour
# #         elif self.current_publication_date:
# #             return "success"  # Vert pour les versions actuelles
# #         else:
# #             return "secondary"
# #
# #     def get_ema_info(self):
# #         """Retourne un dict complet avec infos EMA"""
# #         return {
# #             'has_ema_data': self.has_ema_data,
# #             'first_published': self.original_publication_date,
# #             'last_updated': self.ema_publication_date,
# #             'current_date': self.current_publication_date,
# #             'has_been_updated': self.has_been_updated,
# #             'update_duration_days': self.update_duration_days,
# #             'status': self.publication_status,
# #             'status_class': self.publication_status_class,
# #             'ema_url': self.ema_source_url,
# #             'ema_title': self.ema_title,
# #             'ema_reference': self.ema_reference,
# #             'similarity_score': self.ema_similarity_score,
# #             'search_performed': self.ema_search_performed,
# #             'results_count': self.ema_search_results_count,
# #             'last_search': self.ema_last_search_date,
# #         }
# #
# #     def get_timeline_events(self):
# #         """Retourne la chronologie des événements EMA"""
# #         events = []
# #
# #         if self.original_publication_date:
# #             events.append({
# #                 'date': self.original_publication_date,
# #                 'type': 'first_published',
# #                 'description': 'Première publication EMA',
# #                 'icon': 'bi-calendar-plus',
# #                 'class': 'success'
# #             })
# #
# #         if self.ema_publication_date and self.has_been_updated:
# #             events.append({
# #                 'date': self.ema_publication_date,
# #                 'type': 'last_updated',
# #                 'description': f'Mise à jour EMA (+{self.update_duration_days} jours)',
# #                 'icon': 'bi-arrow-clockwise',
# #                 'class': 'info'
# #             })
# #
# #         if self.ema_last_search_date:
# #             events.append({
# #                 'date': self.ema_last_search_date.date(),
# #                 'type': 'search_performed',
# #                 'description': 'Recherche EMA effectuée',
# #                 'icon': 'bi-search',
# #                 'class': 'secondary'
# #             })
# #
# #         return sorted(events, key=lambda x: x['date'], reverse=True)
# #
# #     # Pour compatibilité avec ancien champ publication_date
# #     @property
# #     def publication_date(self):
# #         return self.current_publication_date
# #
# #     def get_publication_info(self):
# #         return self.get_ema_info()
#
# # documents/models.py - VERSION CORRIGÉE
# from django.db import models
# from django.contrib.auth import get_user_model
#
# User = get_user_model()
#
# class DocumentType(models.Model):
#     name = models.CharField(max_length=100)
#     description = models.TextField(blank=True)
#     color = models.CharField(max_length=7, default='#007bff')
#
#     class Meta:
#         verbose_name = "Type de document"
#         verbose_name_plural = "Types de documents"
#
#     def __str__(self):
#         return self.name
#
# class DocumentContext(models.Model):
#     name = models.CharField(max_length=100)
#     description = models.TextField(blank=True)
#     color = models.CharField(max_length=7, default='#17a2b8')
#
#     class Meta:
#         verbose_name = "Contexte de document"
#         verbose_name_plural = "Contextes de documents"
#
#     def __str__(self):
#         return self.name
#
# class Document(models.Model):
#     STATUS_CHOICES = [
#         ('uploaded', 'Uploadé'),
#         ('extracting', 'En extraction'),
#         ('extracted', 'Extrait'),
#         ('annotating', 'En annotation'),
#         ('annotated', 'Annoté'),
#         ('validating', 'En validation'),
#         ('validated', 'Validé'),
#         ('refused', 'Refusé'),
#         ('completed', 'Terminé'),
#     ]
#
#     title = models.CharField(max_length=255)
#     file = models.FileField(upload_to='documents/%Y/%m/')
#     file_type = models.CharField(max_length=10, blank=True)
#     document_type = models.ForeignKey(DocumentType, on_delete=models.SET_NULL, null=True)
#     context = models.ForeignKey(DocumentContext, on_delete=models.SET_NULL, null=True)
#     status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='uploaded')
#
#     # Métadonnées extraites du document
#     extracted_title = models.CharField(max_length=255, blank=True)
#     language = models.CharField(max_length=10, blank=True)
#     source = models.CharField(max_length=255, blank=True)
#     version = models.CharField(max_length=50, blank=True, null=True)
#     source_url = models.URLField(blank=True)
#
#     # ✅ AJOUT: Date de publication extraite du document (distincte des dates EMA)
#     publication_date = models.DateField(
#         null=True, blank=True,
#         verbose_name="Date de publication",
#         help_text="Date de publication extraite du contenu du document"
#     )
#
#     # === Champs EMA (inchangés) ===
#     original_publication_date = models.DateField(
#         null=True, blank=True,
#         verbose_name="Première publication EMA",
#         help_text="Date 'First published' récupérée du site EMA (première publication officielle)"
#     )
#     ema_publication_date = models.DateField(
#         null=True, blank=True,
#         verbose_name="Dernière mise à jour EMA",
#         help_text="Date 'Last updated' récupérée du site EMA (dernière mise à jour)"
#     )
#     ema_source_url = models.URLField(
#         blank=True,
#         verbose_name="URL source EMA",
#         help_text="URL du document sur le site de l'EMA"
#     )
#     ema_title = models.CharField(
#         max_length=500, blank=True,
#         verbose_name="Titre EMA",
#         help_text="Titre du document tel qu'il apparaît sur le site EMA"
#     )
#     ema_reference = models.CharField(
#         max_length=100, blank=True,
#         verbose_name="Référence EMA",
#         help_text="Numéro de référence EMA du document"
#     )
#     ema_search_performed = models.BooleanField(
#         default=False,
#         verbose_name="Recherche EMA effectuée",
#         help_text="Indique si la recherche automatique sur le site EMA a été effectuée"
#     )
#     ema_search_results_count = models.IntegerField(
#         default=0,
#         verbose_name="Nombre de résultats EMA",
#         help_text="Nombre de résultats trouvés lors de la recherche EMA"
#     )
#     ema_similarity_score = models.FloatField(
#         default=0.0,
#         verbose_name="Score de similarité EMA",
#         help_text="Score de similarité entre le titre du document et le résultat EMA (0.0 à 1.0)"
#     )
#     ema_last_search_date = models.DateTimeField(
#         null=True, blank=True,
#         verbose_name="Dernière recherche EMA",
#         help_text="Date et heure de la dernière recherche automatique EMA"
#     )
#
#     # Assignations
#     assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
#                                     related_name='assigned_documents')
#     validated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
#                                      related_name='validated_documents')
#
#     # Timestamps
#     created_at = models.DateTimeField(auto_now_add=True)
#     updated_at = models.DateTimeField(auto_now=True)
#     extraction_started_at = models.DateTimeField(null=True, blank=True)
#     extraction_completed_at = models.DateTimeField(null=True, blank=True)
#
#     class Meta:
#         verbose_name = "Document"
#         verbose_name_plural = "Documents"
#         ordering = ['-created_at']
#
#     def __str__(self):
#         return self.title
#
#     # ✅ CHANGEMENT: current_publication_date devient une propriété dérivée
#     @property
#     def current_publication_date(self):
#         """Retourne la date de publication la plus récente (priorité: EMA > document)"""
#         return self.ema_publication_date or self.original_publication_date or self.publication_date
#
#     @property
#     def has_ema_data(self):
#         """Indique si le document a des données EMA valides"""
#         return bool(self.ema_source_url and (self.original_publication_date or self.ema_publication_date))
#
#     @property
#     def has_been_updated(self):
#         """Indique si le document a été mis à jour après sa première publication"""
#         if not self.original_publication_date or not self.ema_publication_date:
#             return False
#         return self.ema_publication_date > self.original_publication_date
#
#     @property
#     def update_duration_days(self):
#         """Nombre de jours entre la première publication et la dernière mise à jour"""
#         if not self.has_been_updated:
#             return 0
#         return (self.ema_publication_date - self.original_publication_date).days
#
#     @property
#     def publication_status(self):
#         """Statut de publication basé sur les dates EMA"""
#         if not self.ema_search_performed:
#             return "Recherche EMA en attente"
#
#         if not self.original_publication_date and not self.ema_publication_date:
#             if self.publication_date:
#                 return "Date du document uniquement"
#             return "Non trouvé sur EMA"
#
#         if self.has_been_updated:
#             return f"Mis à jour (+{self.update_duration_days} jours)"
#         elif self.ema_publication_date:
#             return "Version actuelle"
#         elif self.original_publication_date:
#             return "Première version"
#         else:
#             return "Statut inconnu"
#
#     @property
#     def publication_status_class(self):
#         """Classe CSS pour le statut de publication"""
#         if not self.ema_search_performed:
#             return "secondary"
#
#         if not self.original_publication_date and not self.ema_publication_date:
#             if self.publication_date:
#                 return "light"  # Gris clair pour date document seule
#             return "warning"
#
#         if self.has_been_updated:
#             return "info"  # Bleu pour les mises à jour
#         elif self.current_publication_date:
#             return "success"  # Vert pour les versions actuelles
#         else:
#             return "secondary"
#
#     def get_ema_info(self):
#         """Retourne un dict complet avec infos EMA"""
#         return {
#             'has_ema_data': self.has_ema_data,
#             'first_published': self.original_publication_date,
#             'last_updated': self.ema_publication_date,
#             'document_date': self.publication_date,  # ✅ AJOUT
#             'current_date': self.current_publication_date,
#             'has_been_updated': self.has_been_updated,
#             'update_duration_days': self.update_duration_days,
#             'status': self.publication_status,
#             'status_class': self.publication_status_class,
#             'ema_url': self.ema_source_url,
#             'ema_title': self.ema_title,
#             'ema_reference': self.ema_reference,
#             'similarity_score': self.ema_similarity_score,
#             'search_performed': self.ema_search_performed,
#             'results_count': self.ema_search_results_count,
#             'last_search': self.ema_last_search_date,
#         }
#
#     def get_timeline_events(self):
#         """Retourne la chronologie des événements EMA"""
#         events = []
#
#         # ✅ AJOUT: Date du document
#         if self.publication_date:
#             events.append({
#                 'date': self.publication_date,
#                 'type': 'document_date',
#                 'description': 'Date extraite du document',
#                 'icon': 'bi-file-text',
#                 'class': 'light'
#             })
#
#         if self.original_publication_date:
#             events.append({
#                 'date': self.original_publication_date,
#                 'type': 'first_published',
#                 'description': 'Première publication EMA',
#                 'icon': 'bi-calendar-plus',
#                 'class': 'success'
#             })
#
#         if self.ema_publication_date and self.has_been_updated:
#             events.append({
#                 'date': self.ema_publication_date,
#                 'type': 'last_updated',
#                 'description': f'Mise à jour EMA (+{self.update_duration_days} jours)',
#                 'icon': 'bi-arrow-clockwise',
#                 'class': 'info'
#             })
#
#         if self.ema_last_search_date:
#             events.append({
#                 'date': self.ema_last_search_date.date(),
#                 'type': 'search_performed',
#                 'description': 'Recherche EMA effectuée',
#                 'icon': 'bi-search',
#                 'class': 'secondary'
#             })
#
#         return sorted(events, key=lambda x: x['date'], reverse=True)
#
#     def get_publication_info(self):
#         """Alias pour compatibilité"""
#         return self.get_ema_info()

# documents/models.py - VERSION CORRIGÉE avec champs URL
from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()


class DocumentType(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    color = models.CharField(max_length=7, default='#007bff')

    class Meta:
        verbose_name = "Type de document"
        verbose_name_plural = "Types de documents"

    def __str__(self):
        return self.name


class DocumentContext(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    color = models.CharField(max_length=7, default='#17a2b8')

    class Meta:
        verbose_name = "Contexte de document"
        verbose_name_plural = "Contextes de documents"

    def __str__(self):
        return self.name


class Document(models.Model):
    STATUS_CHOICES = [
        ('uploaded', 'Uploadé'),
        ('extracting', 'En extraction'),
        ('extracted', 'Extrait'),
        ('annotating', 'En annotation'),
        ('annotated', 'Annoté'),
        ('validating', 'En validation'),
        ('validated', 'Validé'),
        ('refused', 'Refusé'),
        ('completed', 'Terminé'),
    ]

    title = models.CharField(max_length=255)
    file = models.FileField(upload_to='documents/%Y/%m/', blank=True, null=True)  # Maintenant optionnel
    file_type = models.CharField(max_length=10, blank=True)
    document_type = models.ForeignKey(DocumentType, on_delete=models.SET_NULL, null=True)
    context = models.ForeignKey(DocumentContext, on_delete=models.SET_NULL, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='uploaded')

    # ✅ NOUVEAUX CHAMPS : URLs fournies par l'utilisateur
    direct_pdf_url = models.URLField(
        max_length=255,
        blank=True,
        verbose_name="URL directe du PDF",
        help_text="URL directe vers le fichier PDF (pour extraction du contenu)"
    )

    ema_page_url = models.URLField(
        blank=True,
        verbose_name="URL de la page EMA",
        help_text="URL de la page web EMA contenant les métadonnées du document"
    )

    # Métadonnées extraites du document
    extracted_title = models.CharField(max_length=255, blank=True)
    language = models.CharField(max_length=10, blank=True)
    source = models.CharField(max_length=255, blank=True)
    version = models.CharField(max_length=50, blank=True, null=True)
    source_url = models.URLField(blank=True)

    # Date de publication extraite du document (distincte des dates EMA)
    publication_date = models.DateField(
        null=True, blank=True,
        verbose_name="Date de publication",
        help_text="Date de publication extraite du contenu du document"
    )

    # === Champs EMA (inchangés) ===
    original_publication_date = models.DateField(
        null=True, blank=True,
        verbose_name="Première publication EMA",
        help_text="Date 'First published' récupérée du site EMA (première publication officielle)"
    )
    ema_publication_date = models.DateField(
        null=True, blank=True,
        verbose_name="Dernière mise à jour EMA",
        help_text="Date 'Last updated' récupérée du site EMA (dernière mise à jour)"
    )
    ema_source_url = models.URLField(
        blank=True,
        verbose_name="URL source EMA",
        help_text="URL du document sur le site de l'EMA"
    )
    ema_title = models.CharField(
        max_length=500, blank=True,
        verbose_name="Titre EMA",
        help_text="Titre du document tel qu'il apparaît sur le site EMA"
    )
    ema_reference = models.CharField(
        max_length=100, blank=True,
        verbose_name="Référence EMA",
        help_text="Numéro de référence EMA du document"
    )
    ema_search_performed = models.BooleanField(
        default=False,
        verbose_name="Recherche EMA effectuée",
        help_text="Indique si la recherche automatique sur le site EMA a été effectuée"
    )
    ema_search_results_count = models.IntegerField(
        default=0,
        verbose_name="Nombre de résultats EMA",
        help_text="Nombre de résultats trouvés lors de la recherche EMA"
    )
    ema_similarity_score = models.FloatField(
        default=0.0,
        verbose_name="Score de similarité EMA",
        help_text="Score de similarité entre le titre du document et le résultat EMA (0.0 à 1.0)"
    )
    ema_last_search_date = models.DateTimeField(
        null=True, blank=True,
        verbose_name="Dernière recherche EMA",
        help_text="Date et heure de la dernière recherche automatique EMA"
    )

    # Assignations
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='assigned_documents')
    validated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                     related_name='validated_documents')

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    extraction_started_at = models.DateTimeField(null=True, blank=True)
    extraction_completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Document"
        verbose_name_plural = "Documents"
        ordering = ['-created_at']

    def __str__(self):
        return self.title

    @property
    def current_publication_date(self):
        """Retourne la date de publication la plus récente (priorité: EMA > document)"""
        return self.ema_publication_date or self.original_publication_date or self.publication_date

    @property
    def has_ema_data(self):
        """Indique si le document a des données EMA valides"""
        return bool(self.ema_source_url and (self.original_publication_date or self.ema_publication_date))

    @property
    def has_been_updated(self):
        """Indique si le document a été mis à jour après sa première publication"""
        if not self.original_publication_date or not self.ema_publication_date:
            return False
        return self.ema_publication_date > self.original_publication_date

    @property
    def update_duration_days(self):
        """Nombre de jours entre la première publication et la dernière mise à jour"""
        if not self.has_been_updated:
            return 0
        return (self.ema_publication_date - self.original_publication_date).days

    @property
    def publication_status(self):
        """Statut de publication basé sur les dates EMA"""
        if not self.ema_search_performed:
            return "Recherche EMA en attente"

        if not self.original_publication_date and not self.ema_publication_date:
            if self.publication_date:
                return "Date du document uniquement"
            return "Non trouvé sur EMA"

        if self.has_been_updated:
            return f"Mis à jour (+{self.update_duration_days} jours)"
        elif self.ema_publication_date:
            return "Version actuelle"
        elif self.original_publication_date:
            return "Première version"
        else:
            return "Statut inconnu"

    @property
    def publication_status_class(self):
        """Classe CSS pour le statut de publication"""
        if not self.ema_search_performed:
            return "secondary"

        if not self.original_publication_date and not self.ema_publication_date:
            if self.publication_date:
                return "light"  # Gris clair pour date document seule
            return "warning"

        if self.has_been_updated:
            return "info"  # Bleu pour les mises à jour
        elif self.current_publication_date:
            return "success"  # Vert pour les versions actuelles
        else:
            return "secondary"

    @property
    def has_urls(self):
        """Vérifie si le document a des URLs fournies"""
        return bool(self.direct_pdf_url or self.ema_page_url)

    @property
    def can_extract_from_url(self):
        """Vérifie si l'extraction par URL est possible"""
        return bool(self.direct_pdf_url and self.ema_page_url)

    def get_ema_info(self):
        """Retourne un dict complet avec infos EMA"""
        return {
            'has_ema_data': self.has_ema_data,
            'first_published': self.original_publication_date,
            'last_updated': self.ema_publication_date,
            'document_date': self.publication_date,
            'current_date': self.current_publication_date,
            'has_been_updated': self.has_been_updated,
            'update_duration_days': self.update_duration_days,
            'status': self.publication_status,
            'status_class': self.publication_status_class,
            'ema_url': self.ema_source_url,
            'ema_title': self.ema_title,
            'ema_reference': self.ema_reference,
            'similarity_score': self.ema_similarity_score,
            'search_performed': self.ema_search_performed,
            'results_count': self.ema_search_results_count,
            'last_search': self.ema_last_search_date,
            # Nouveaux champs
            'direct_pdf_url': self.direct_pdf_url,
            'ema_page_url': self.ema_page_url,
            'can_extract_from_url': self.can_extract_from_url,
        }

    def get_timeline_events(self):
        """Retourne la chronologie des événements EMA"""
        events = []

        # Date du document
        if self.publication_date:
            events.append({
                'date': self.publication_date,
                'type': 'document_date',
                'description': 'Date extraite du document',
                'icon': 'bi-file-text',
                'class': 'light'
            })

        if self.original_publication_date:
            events.append({
                'date': self.original_publication_date,
                'type': 'first_published',
                'description': 'Première publication EMA',
                'icon': 'bi-calendar-plus',
                'class': 'success'
            })

        if self.ema_publication_date and self.has_been_updated:
            events.append({
                'date': self.ema_publication_date,
                'type': 'last_updated',
                'description': f'Mise à jour EMA (+{self.update_duration_days} jours)',
                'icon': 'bi-arrow-clockwise',
                'class': 'info'
            })

        if self.ema_last_search_date:
            events.append({
                'date': self.ema_last_search_date.date(),
                'type': 'search_performed',
                'description': 'Recherche EMA effectuée',
                'icon': 'bi-search',
                'class': 'secondary'
            })

        return sorted(events, key=lambda x: x['date'], reverse=True)

    def get_publication_info(self):
        """Alias pour compatibilité"""
        return self.get_ema_info()