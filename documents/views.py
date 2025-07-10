# # # documents/views.py
# # from django.shortcuts import render, get_object_or_404, redirect
# # from django.contrib.auth.decorators import login_required
# # from django.contrib import messages
# # from django.http import JsonResponse, FileResponse, Http404
# # from django.views.decorators.http import require_http_methods
# # from django.core.files.storage import default_storage
# # from django.conf import settings
# # import os
# # import mimetypes
# #
# # from .models import Document, DocumentType, DocumentContext
# # from annotation.models import Annotation, EntityType
# # from audit.models import AuditLog
# #
# #
# # @login_required
# # def document_list(request):
# #     """Liste des documents pour annotation"""
# #
# #     # DEBUG: Vérifier tous les documents
# #     all_documents = Document.objects.all()
# #     print(f"Tous les documents: {all_documents.count()}")
# #
# #     # DEBUG: Vérifier les documents par statut
# #     for status in ['uploaded', 'extracting', 'extracted', 'annotating', 'annotated', 'validated']:
# #         count = Document.objects.filter(status=status).count()
# #         print(f"Documents avec statut '{status}': {count}")
# #
# #     # DEBUG: Vérifier les documents assignés à l'utilisateur
# #     user_documents = Document.objects.filter(assigned_to=request.user)
# #     print(f"Documents assignés à {request.user}: {user_documents.count()}")
# #
# #     # Filtre selon le rôle de l'utilisateur
# #     if request.user.role == 'admin':
# #         documents = Document.objects.filter(
# #             status__in=['extracted', 'annotating']
# #         ).select_related('document_type', 'context')
# #     elif request.user.role == 'metadonneur':
# #         # Les métadonneurs peuvent voir les documents validés pour annotation
# #         documents = Document.objects.filter(
# #             status__in=['validated', 'annotating', 'annotated'],
# #             assigned_to=request.user
# #         ).select_related('document_type', 'context')
# #     else:
# #         # Pour les autres rôles (expert, annotateur, etc.)
# #         documents = Document.objects.filter(
# #             status__in=['extracted', 'annotating'],
# #             assigned_to=request.user
# #         ).select_related('document_type', 'context')
# #
# #     print(f"Documents filtrés finaux: {documents.count()}")
# #
# #     # DEBUG: Si aucun document filtré, on prend tous les documents de l'utilisateur
# #     if not documents.exists():
# #         print("Aucun document trouvé avec les filtres, affichage de tous les documents de l'utilisateur")
# #         documents = Document.objects.filter(assigned_to=request.user).select_related('document_type', 'context')
# #
# #     # Si toujours aucun document, on prend TOUS les documents (pour debug admin)
# #     if not documents.exists() and (request.user.is_staff or request.user.role == 'admin'):
# #         print("Mode debug admin: affichage de tous les documents")
# #         documents = Document.objects.all().select_related('document_type', 'context')
# #
# #     return render(request, 'documents/list.html', {'documents': documents})
# #
# #
# # @login_required
# # def document_annotate(request, document_id):
# #     """Interface d'annotation d'un document"""
# #     document = get_object_or_404(Document, id=document_id)
# #
# #     # Vérification des permissions élargie
# #     if not (request.user.role in ['admin', 'metadonneur'] or document.assigned_to == request.user):
# #         messages.error(request, 'Vous n\'avez pas les permissions pour accéder à ce document.')
# #         return redirect('documents:list')
# #
# #     # Marquer le document comme en cours d'annotation
# #     if document.status == 'extracted':
# #         document.status = 'annotating'
# #         document.save()
# #
# #     # Récupérer les annotations existantes
# #     annotations = Annotation.objects.filter(document=document).select_related('entity_type')
# #
# #     # Types d'entités disponibles
# #     entity_types = EntityType.objects.all()
# #
# #     # Contenu du document (simulation)
# #     document_content = """Multivariate analysis revealed that septic shock and bacteremia originating from
# #     lower respiratory tract infection were two independent risk factors for 30-day mortality."""
# #
# #     context = {
# #         'document': document,
# #         'annotations': annotations,
# #         'entity_types': entity_types,
# #         'document_content': document_content,
# #     }
# #
# #     return render(request, 'documents/annotate.html', context)
# #
# #
# # @login_required
# # def document_view(request, document_id):
# #     """Visualiser un document - VERSION ADAPTÉE"""
# #     document = get_object_or_404(Document, id=document_id)
# #
# #     # Permissions élargies pour inclure les métadonneurs
# #     if not (request.user.role in ['admin', 'metadonneur', 'expert'] or document.assigned_to == request.user):
# #         messages.error(request, 'Vous n\'avez pas les permissions pour visualiser ce document.')
# #         return JsonResponse({'error': 'Permission refusée'}, status=403)
# #
# #     # Log d'audit
# #     AuditLog.objects.create(
# #         user=request.user,
# #         document=document,
# #         action='view',
# #         description=f'Visualisation du document: {document.title}',
# #         ip_address=request.META.get('REMOTE_ADDR')
# #     )
# #
# #     # Vérifier que le fichier existe
# #     if not document.file or not os.path.exists(document.file.path):
# #         messages.error(request, 'Le fichier du document est introuvable.')
# #         return JsonResponse({'error': 'Fichier non trouvé'}, status=404)
# #
# #     # Déterminer le type de fichier
# #     file_extension = os.path.splitext(document.file.name)[1].lower()
# #     content_type, _ = mimetypes.guess_type(document.file.path)
# #
# #     # Si c'est un PDF, on peut le servir directement ou utiliser le template de visualisation
# #     if request.GET.get('download') == '1':
# #         # Mode téléchargement
# #         try:
# #             return FileResponse(
# #                 open(document.file.path, 'rb'),
# #                 as_attachment=True,
# #                 filename=os.path.basename(document.file.name)
# #             )
# #         except FileNotFoundError:
# #             return JsonResponse({'error': 'Fichier non trouvé'}, status=404)
# #
# #     elif file_extension == '.pdf':
# #         # Mode visualisation PDF dans le navigateur
# #         try:
# #             return FileResponse(
# #                 open(document.file.path, 'rb'),
# #                 content_type='application/pdf',
# #                 filename=document.file.name
# #             )
# #         except FileNotFoundError:
# #             return JsonResponse({'error': 'Fichier non trouvé'}, status=404)
# #
# #     else:
# #         # Pour les autres types de fichiers, utiliser le template de visualisation
# #         context = {
# #             'document': document,
# #             'file_extension': file_extension,
# #             'content_type': content_type,
# #             'is_pdf': file_extension == '.pdf',
# #             'is_image': file_extension in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff'],
# #             'is_text': file_extension in ['.txt', '.md', '.csv'],
# #             'file_url': document.file.url,
# #         }
# #
# #         return render(request, 'documents/view.html', context)
# #
# #
# # @login_required
# # def document_upload(request):
# #     """Upload d'un nouveau document"""
# #     if request.user.role not in ['admin', 'uploader']:
# #         messages.error(request, 'Vous n\'avez pas les permissions pour uploader des documents.')
# #         return redirect('dashboard:home')
# #
# #     if request.method == 'POST':
# #         from .forms import DocumentUploadForm
# #         form = DocumentUploadForm(request.POST, request.FILES)
# #         if form.is_valid():
# #             document = form.save(commit=False)
# #             document.save()
# #
# #             # Log d'audit
# #             AuditLog.objects.create(
# #                 user=request.user,
# #                 document=document,
# #                 action='upload',
# #                 description=f'Document {document.title} uploadé',
# #                 ip_address=request.META.get('REMOTE_ADDR')
# #             )
# #
# #             # Lancer l'extraction en arrière-plan
# #             from extraction.tasks import extract_document_metadata
# #             try:
# #                 extract_document_metadata.delay(document.id)
# #             except:
# #                 # Si Celery n'est pas disponible, appel direct
# #                 extract_document_metadata(document.id)
# #
# #             return JsonResponse({
# #                 'success': True,
# #                 'message': 'Document uploadé et extraction lancée',
# #                 'document_id': document.id
# #             })
# #         else:
# #             return JsonResponse({
# #                 'success': False,
# #                 'errors': form.errors
# #             })
# #     else:
# #         from .forms import DocumentUploadForm
# #         form = DocumentUploadForm()
# #
# #     return render(request, 'documents/upload.html', {'form': form})
# #
# #
# # @require_http_methods(["POST"])
# # @login_required
# # def validate_annotations(request, document_id):
# #     """Valider les annotations d'un document"""
# #     document = get_object_or_404(Document, id=document_id)
# #
# #     # Permissions élargies
# #     if not (request.user.role in ['admin', 'metadonneur'] or document.assigned_to == request.user):
# #         return JsonResponse({'error': 'Permission refusée'}, status=403)
# #
# #     # Marquer toutes les annotations comme validées
# #     Annotation.objects.filter(document=document, status='detected').update(
# #         status='validated',
# #         validated_by=request.user
# #     )
# #
# #     # Changer le statut du document
# #     document.status = 'annotated'
# #     document.validated_by = request.user
# #     document.save()
# #
# #     # Log d'audit
# #     AuditLog.objects.create(
# #         user=request.user,
# #         document=document,
# #         action='validate',
# #         description=f'Validation des annotations pour le document {document.title}',
# #         ip_address=request.META.get('REMOTE_ADDR')
# #     )
# #
# #     return JsonResponse({'success': True, 'message': 'Annotations validées avec succès'})
# #
# #
# # @require_http_methods(["POST"])
# # @login_required
# # def refuse_annotation(request, document_id):
# #     """Refuser l'annotation d'un document"""
# #     document = get_object_or_404(Document, id=document_id)
# #
# #     # Permissions élargies
# #     if not (request.user.role in ['admin', 'metadonneur'] or document.assigned_to == request.user):
# #         return JsonResponse({'error': 'Permission refusée'}, status=403)
# #
# #     document.status = 'refused'
# #     document.save()
# #
# #     # Log d'audit
# #     AuditLog.objects.create(
# #         user=request.user,
# #         document=document,
# #         action='refuse',
# #         description=f'Refus d\'annotation pour le document {document.title}',
# #         ip_address=request.META.get('REMOTE_ADDR')
# #     )
# #
# #     return JsonResponse({'success': True, 'message': 'Document refusé'})
# #
# #
# # @login_required
# # def document_stats(request, document_id):
# #     """Statistiques d'un document"""
# #     document = get_object_or_404(Document, id=document_id)
# #
# #     # Permissions élargies
# #     if not (request.user.role in ['admin', 'metadonneur', 'expert'] or document.assigned_to == request.user):
# #         return JsonResponse({'error': 'Permission refusée'}, status=403)
# #
# #     # Calculer les statistiques
# #     annotations_count = Annotation.objects.filter(document=document).count()
# #     validated_annotations = Annotation.objects.filter(
# #         document=document,
# #         status='validated'
# #     ).count()
# #
# #     # Taux d'extraction (si existe)
# #     extraction_rate = None
# #     if hasattr(document, 'extraction_results') and document.extraction_results.exists():
# #         extraction_result = document.extraction_results.first()
# #         if extraction_result and extraction_result.confidence_score:
# #             extraction_rate = round(extraction_result.confidence_score * 100, 1)
# #
# #     return JsonResponse({
# #         'annotations_count': annotations_count,
# #         'validated_annotations': validated_annotations,
# #         'extraction_rate': extraction_rate,
# #         'document_status': document.status,
# #         'document_title': document.title,
# #     })
# #
# #
# # # Vue supplémentaire pour le téléchargement direct
# # @login_required
# # def document_download(request, document_id):
# #     """Téléchargement direct d'un document"""
# #     document = get_object_or_404(Document, id=document_id)
# #
# #     # Permissions élargies
# #     if not (request.user.role in ['admin', 'metadonneur', 'expert'] or document.assigned_to == request.user):
# #         return JsonResponse({'error': 'Permission refusée'}, status=403)
# #
# #     # Vérifier que le fichier existe
# #     if not document.file or not os.path.exists(document.file.path):
# #         raise Http404("Fichier introuvable")
# #
# #     # Log d'audit
# #     AuditLog.objects.create(
# #         user=request.user,
# #         document=document,
# #         action='download',
# #         description=f'Téléchargement du document: {document.title}',
# #         ip_address=request.META.get('REMOTE_ADDR')
# #     )
# #
# #     # Retourner le fichier
# #     return FileResponse(
# #         open(document.file.path, 'rb'),
# #         as_attachment=True,
# #         filename=os.path.basename(document.file.name)
# #     )
# #
# #
# # # dashboard/views.py - Mise à jour pour inclure la validation experte
# # from django.shortcuts import render
# # from django.contrib.auth.decorators import login_required
# # from django.db.models import Count, Q
# # from documents.models import Document
# # from annotation.models import Annotation
# # from extraction.models import ExtractionResult
# # from django.contrib.auth import get_user_model
# # from django.http import JsonResponse
# #
# # User = get_user_model()
# #
# #
# # @login_required
# # def dashboard_home(request):
# #     user = request.user
# #
# #     # Redirection selon le rôle
# #     if user.role == 'metadonneur':
# #         return render(request, 'dashboard/metadonneur.html', get_metadonneur_context(user))
# #     elif user.role == 'annotateur':
# #         return render(request, 'dashboard/annotateur.html', get_annotateur_context(user))
# #     elif user.role == 'expert':
# #         return render(request, 'dashboard/expert.html', get_expert_context(user))
# #     else:
# #         return render(request, 'dashboard/admin.html', get_admin_context(user))
# #
# #
# # def get_annotateur_context(user):
# #     # Statistiques pour annotateur
# #     total_planned = 150
# #     documents_to_annotate = Document.objects.filter(
# #         status__in=['extracted', 'annotating'],
# #         assigned_to=user
# #     ).count()
# #
# #     documents_in_progress = Document.objects.filter(
# #         status='annotating',
# #         assigned_to=user
# #     ).count()
# #
# #     documents_completed = Document.objects.filter(
# #         status__in=['annotated', 'validated'],
# #         assigned_to=user
# #     ).count()
# #
# #     documents_refused = Document.objects.filter(
# #         status='refused',
# #         assigned_to=user
# #     ).count()
# #
# #     # Documents pour annotation
# #     documents_list = Document.objects.filter(
# #         status__in=['extracted', 'annotating'],
# #         assigned_to=user
# #     ).select_related('document_type', 'context')[:10]
# #
# #     # Statistiques des tâches
# #     total_annotations = Annotation.objects.filter(created_by=user).count()
# #     extraction_tasks = 15  # Exemple
# #     validation_tasks = 8  # Exemple
# #     finalization_tasks = 3  # Exemple
# #
# #     return {
# #         'total_planned': total_planned,
# #         'documents_to_annotate': documents_to_annotate,
# #         'documents_in_progress': documents_in_progress,
# #         'documents_completed': documents_completed,
# #         'documents_refused': documents_refused,
# #         'completion_rate': round((documents_to_annotate / total_planned) * 100, 1) if total_planned > 0 else 0,
# #         'progress_rate': round((documents_in_progress / 25) * 100, 1),
# #         'documents_list': documents_list,
# #         'task_stats': {
# #             'extraction': {'count': extraction_tasks, 'percentage': 35},
# #             'validation': {'count': validation_tasks, 'percentage': 19},
# #             'finalization': {'count': finalization_tasks, 'percentage': 7},
# #         }
# #     }
# #
# #
# # def get_metadonneur_context(user):
# #     # Statistiques pour métadonneur
# #     total_planned = 150
# #     documents_scraped = Document.objects.filter(status='uploaded').count()
# #     documents_in_extraction = Document.objects.filter(status='extracting').count()
# #     documents_completed = Document.objects.filter(status__in=['extracted', 'annotated']).count()
# #     documents_refused = Document.objects.filter(status='refused').count()
# #     documents_re_scraping = Document.objects.filter(status='re_extracting').count()
# #
# #     return {
# #         'total_planned': total_planned,
# #         'documents_scraped': documents_scraped,
# #         'documents_in_extraction': documents_in_extraction,
# #         'documents_completed': documents_completed,
# #         'documents_refused': documents_refused,
# #         'documents_re_scraping': documents_re_scraping,
# #         'completion_rate': round((documents_scraped / total_planned) * 100, 1) if total_planned > 0 else 0,
# #         'progress_rate': round((documents_in_extraction / 25) * 100, 1),
# #         'task_stats': {
# #             'extraction': {'count': 15, 'percentage': 35},
# #             'validation': {'count': 8, 'percentage': 19},
# #             'finalization': {'count': 3, 'percentage': 7},
# #         }
# #     }
# #
# #
# # def get_expert_context(user):
# #     # Statistiques pour expert - MISE À JOUR
# #     total_planned = 150
# #
# #     # Documents annotés prêts pour validation experte
# #     documents_scraped = Document.objects.filter(status__in=['annotated', 'validating']).count()
# #
# #     # Documents en cours de validation par cet expert
# #     documents_in_extraction = Document.objects.filter(
# #         status='validating',
# #         validated_by=user
# #     ).count()
# #
# #     # Documents validés définitivement par cet expert
# #     documents_completed = Document.objects.filter(
# #         status='validated',
# #         validated_by=user
# #     ).count()
# #
# #     # Documents refusés/remis en annotation
# #     documents_refused = Document.objects.filter(status='refused').count()
# #
# #     # Documents en attente de revalidation
# #     documents_re_scraping = Document.objects.filter(
# #         status='annotated'  # Annotés mais pas encore validés par expert
# #     ).count()
# #
# #     # Calculer les taux
# #     validation_rate = round((documents_completed / documents_scraped) * 100, 1) if documents_scraped > 0 else 0
# #     revalidation_rate = round((documents_re_scraping / 25) * 100, 1)
# #
# #     return {
# #         'total_planned': total_planned,
# #         'documents_scraped': documents_scraped,
# #         'documents_in_extraction': documents_in_extraction,
# #         'documents_completed': documents_completed,
# #         'documents_refused': documents_refused,
# #         'documents_re_scraping': documents_re_scraping,
# #         'completion_rate': round((documents_scraped / total_planned) * 100, 1) if total_planned > 0 else 0,
# #         'progress_rate': round((documents_in_extraction / 25) * 100, 1),
# #         'validation_rate': validation_rate,
# #         'revalidation_rate': revalidation_rate,
# #         'task_stats': {
# #             'validation': {'count': documents_scraped, 'percentage': 45},
# #             'revision': {'count': documents_re_scraping, 'percentage': 24},
# #             'control': {'count': documents_completed, 'percentage': 31},
# #         }
# #     }
# #
# #
# # def get_admin_context(user):
# #     # Statistiques globales pour admin
# #     total_users = User.objects.count()
# #     total_documents = Document.objects.count()
# #     documents_processed = Document.objects.filter(status__in=['validated', 'completed']).count()
# #
# #     return {
# #         'total_users': total_users,
# #         'total_documents': total_documents,
# #         'documents_processed': documents_processed,
# #         'processing_rate': round((documents_processed / total_documents) * 100, 1) if total_documents > 0 else 0,
# #     }
# #
# #
# # @login_required
# # def dashboard_stats(request):
# #     """API pour les statistiques du dashboard (JSON)"""
# #     user = request.user
# #
# #     # Filtrer selon le rôle
# #     if user.role == 'admin':
# #         documents = Document.objects.all()
# #     elif user.role in ['annotateur', 'expert']:
# #         documents = Document.objects.filter(assigned_to=user)
# #     elif user.role == 'metadonneur':
# #         documents = Document.objects.all()
# #     else:
# #         documents = Document.objects.none()
# #
# #     # Statistiques de base
# #     stats = {
# #         'total_documents': documents.count(),
# #         'documents_by_status': dict(
# #             documents.values('status')
# #             .annotate(count=Count('id'))
# #             .values_list('status', 'count')
# #         ),
# #     }
# #
# #     # Statistiques spécifiques selon le rôle
# #     if user.role == 'annotateur':
# #         stats.update({
# #             'annotations_created': Annotation.objects.filter(created_by=user).count(),
# #             'documents_annotated': documents.filter(status='annotated').count(),
# #         })
# #     elif user.role == 'metadonneur':
# #         stats.update({
# #             'documents_extracted': documents.filter(status='extracted').count(),
# #         })
# #     elif user.role == 'expert':
# #         # Statistiques spécialisées pour experts
# #         stats.update({
# #             'documents_pending_validation': Document.objects.filter(status='annotated').count(),
# #             'documents_validating': Document.objects.filter(
# #                 status='validating',
# #                 validated_by=user
# #             ).count(),
# #             'documents_validated': Document.objects.filter(
# #                 status='validated',
# #                 validated_by=user
# #             ).count(),
# #             'annotation_quality': calculate_annotation_quality(),
# #         })
# #     elif user.role == 'admin':
# #         stats.update({
# #             'total_users': User.objects.count(),
# #             'total_annotations': Annotation.objects.count(),
# #         })
# #
# #     return JsonResponse(stats)
# #
# #
# # def calculate_annotation_quality():
# #     """Calculer la qualité globale des annotations"""
# #     total_annotations = Annotation.objects.count()
# #     if total_annotations == 0:
# #         return 0.0
# #
# #     validated_annotations = Annotation.objects.filter(status='validated').count()
# #     return round((validated_annotations / total_annotations) * 100, 1)
#
#
#
#
#
#
#
# # documents/views.py - VERSION CORRIGÉE
# from django.shortcuts import render, get_object_or_404, redirect
# from django.contrib.auth.decorators import login_required
# from django.contrib import messages
# from django.http import JsonResponse, FileResponse, Http404
# from django.views.decorators.http import require_http_methods
# from django.core.files.storage import default_storage
# from django.conf import settings
# import os
# import mimetypes
# import logging
#
# from .models import Document, DocumentType, DocumentContext
# from annotation.models import Annotation, EntityType
# from audit.models import AuditLog
# from extraction.services import DocumentTextExtractor
# from extraction.tasks import auto_annotate_document
#
# logger = logging.getLogger(__name__)
#
#
# @login_required
# def document_list(request):
#     """Liste des documents pour annotation"""
#
#     # DEBUG: Vérifier tous les documents
#     all_documents = Document.objects.all()
#     print(f"Tous les documents: {all_documents.count()}")
#
#     # DEBUG: Vérifier les documents par statut
#     for status in ['uploaded', 'extracting', 'extracted', 'annotating', 'annotated', 'validated']:
#         count = Document.objects.filter(status=status).count()
#         print(f"Documents avec statut '{status}': {count}")
#
#     # DEBUG: Vérifier les documents assignés à l'utilisateur
#     user_documents = Document.objects.filter(assigned_to=request.user)
#     print(f"Documents assignés à {request.user}: {user_documents.count()}")
#
#     # Filtre selon le rôle de l'utilisateur
#     if request.user.role == 'admin':
#         documents = Document.objects.filter(
#             status__in=['extracted', 'annotating']
#         ).select_related('document_type', 'context')
#     elif request.user.role == 'metadonneur':
#         # Les métadonneurs peuvent voir les documents validés pour annotation
#         documents = Document.objects.filter(
#             status__in=['validated', 'annotating', 'annotated'],
#             assigned_to=request.user
#         ).select_related('document_type', 'context')
#     else:
#         # Pour les autres rôles (expert, annotateur, etc.)
#         documents = Document.objects.filter(
#             status__in=['extracted', 'annotating'],
#             assigned_to=request.user
#         ).select_related('document_type', 'context')
#
#     print(f"Documents filtrés finaux: {documents.count()}")
#
#     # DEBUG: Si aucun document filtré, on prend tous les documents de l'utilisateur
#     if not documents.exists():
#         print("Aucun document trouvé avec les filtres, affichage de tous les documents de l'utilisateur")
#         documents = Document.objects.filter(assigned_to=request.user).select_related('document_type', 'context')
#
#     # Si toujours aucun document, on prend TOUS les documents (pour debug admin)
#     if not documents.exists() and (request.user.is_staff or request.user.role == 'admin'):
#         print("Mode debug admin: affichage de tous les documents")
#         documents = Document.objects.all().select_related('document_type', 'context')
#
#     return render(request, 'documents/list.html', {'documents': documents})
#
#
# @login_required
# def document_annotate(request, document_id):
#     """Interface d'annotation d'un document - VERSION CORRIGÉE"""
#     document = get_object_or_404(Document, id=document_id)
#
#     # Vérification des permissions élargie
#     if not (request.user.role in ['admin', 'metadonneur'] or document.assigned_to == request.user):
#         messages.error(request, 'Vous n\'avez pas les permissions pour accéder à ce document.')
#         return redirect('documents:list')
#
#     # Marquer le document comme en cours d'annotation
#     if document.status == 'extracted':
#         document.status = 'annotating'
#         document.save()
#
#     # ===== EXTRACTION DU VRAI CONTENU DU DOCUMENT =====
#     document_content = ""
#     try:
#         # Vérifier que le fichier existe
#         if document.file and os.path.exists(document.file.path):
#             logger.info(f"Extraction du contenu pour le document {document_id}")
#
#             text_extractor = DocumentTextExtractor()
#             document_content = text_extractor.extract_text_from_file(
#                 document.file.path,
#                 document.file_type
#             )
#
#             logger.info(f"Contenu extrait: {len(document_content)} caractères")
#
#             if not document_content or len(document_content.strip()) < 10:
#                 document_content = "Le contenu du document est vide ou n'a pas pu être extrait."
#                 logger.warning(f"Contenu vide pour le document {document_id}")
#         else:
#             document_content = "Fichier du document introuvable."
#             logger.error(f"Fichier introuvable pour le document {document_id}")
#
#     except Exception as e:
#         logger.error(f"Erreur extraction texte document {document_id}: {e}")
#         document_content = f"Erreur lors de l'extraction du contenu: {str(e)}"
#
#     # ===== LANCER L'ANNOTATION AUTOMATIQUE SI NÉCESSAIRE =====
#     annotations = Annotation.objects.filter(document=document).select_related('entity_type', 'created_by')
#
#     # Si aucune annotation automatique n'existe, lancer l'IA
#     if not annotations.filter(is_automatic=True).exists() and document_content and len(document_content.strip()) > 50:
#         try:
#             logger.info(f"Lancement de l'annotation automatique pour le document {document_id}")
#
#             # Import de la fonction de tâche
#             from extraction.tasks import auto_annotate_document
#
#             # Appeler directement la fonction (pas de .delay() car Celery peut ne pas être disponible)
#             result = auto_annotate_document(document_id)
#
#             if result and result.get('success'):
#                 logger.info(f"Annotation automatique réussie: {result.get('annotations_count', 0)} annotations")
#                 messages.success(request,
#                                  f"Annotation automatique terminée : {result.get('annotations_count', 0)} entités détectées")
#
#                 # Recharger les annotations après l'annotation automatique
#                 annotations = Annotation.objects.filter(document=document).select_related('entity_type', 'created_by')
#             else:
#                 logger.warning(
#                     f"Annotation automatique échouée: {result.get('error', 'Erreur inconnue') if result else 'Aucun résultat'}")
#                 messages.warning(request, "L'annotation automatique n'a pas pu être effectuée.")
#
#         except Exception as e:
#             logger.error(f"Erreur lors du lancement de l'annotation automatique: {e}")
#             messages.warning(request, f"Erreur lors de l'annotation automatique: {str(e)}")
#
#     # Types d'entités disponibles
#     entity_types = EntityType.objects.all()
#
#     # Si aucun type d'entité n'existe, en créer quelques-uns par défaut
#     if not entity_types.exists():
#         default_entity_types = [
#             {'name': 'CONDITION', 'color': '#dc3545', 'description': 'Conditions médicales'},
#             {'name': 'FACTEUR', 'color': '#fd7e14', 'description': 'Facteurs de risque'},
#             {'name': 'METHODE', 'color': '#20c997', 'description': 'Méthodes et analyses'},
#             {'name': 'EFFET', 'color': '#6f42c1', 'description': 'Effets et résultats'},
#             {'name': 'AUTEUR', 'color': '#0dcaf0', 'description': 'Auteurs et personnes'},
#             {'name': 'ORGANISATION', 'color': '#198754', 'description': 'Organisations'},
#             {'name': 'DATE', 'color': '#ffc107', 'description': 'Dates'},
#             {'name': 'LIEU', 'color': '#6c757d', 'description': 'Lieux'},
#         ]
#
#         for et_data in default_entity_types:
#             EntityType.objects.get_or_create(
#                 name=et_data['name'],
#                 defaults={
#                     'color': et_data['color'],
#                     'description': et_data['description']
#                 }
#             )
#
#         # Recharger les types d'entités
#         entity_types = EntityType.objects.all()
#         messages.info(request, "Types d'entités par défaut créés.")
#
#     context = {
#         'document': document,
#         'annotations': annotations,
#         'entity_types': entity_types,
#         'document_content': document_content,
#     }
#
#     return render(request, 'documents/annotate.html', context)
#
#
# @login_required
# def document_view(request, document_id):
#     """Visualiser un document - VERSION ADAPTÉE"""
#     document = get_object_or_404(Document, id=document_id)
#
#     # Permissions élargies pour inclure les métadonneurs
#     if not (request.user.role in ['admin', 'metadonneur', 'expert'] or document.assigned_to == request.user):
#         messages.error(request, 'Vous n\'avez pas les permissions pour visualiser ce document.')
#         return JsonResponse({'error': 'Permission refusée'}, status=403)
#
#     # Log d'audit
#     AuditLog.objects.create(
#         user=request.user,
#         document=document,
#         action='view',
#         description=f'Visualisation du document: {document.title}',
#         ip_address=request.META.get('REMOTE_ADDR')
#     )
#
#     # Vérifier que le fichier existe
#     if not document.file or not os.path.exists(document.file.path):
#         messages.error(request, 'Le fichier du document est introuvable.')
#         return JsonResponse({'error': 'Fichier non trouvé'}, status=404)
#
#     # Déterminer le type de fichier
#     file_extension = os.path.splitext(document.file.name)[1].lower()
#     content_type, _ = mimetypes.guess_type(document.file.path)
#
#     # Si c'est un PDF, on peut le servir directement ou utiliser le template de visualisation
#     if request.GET.get('download') == '1':
#         # Mode téléchargement
#         try:
#             return FileResponse(
#                 open(document.file.path, 'rb'),
#                 as_attachment=True,
#                 filename=os.path.basename(document.file.name)
#             )
#         except FileNotFoundError:
#             return JsonResponse({'error': 'Fichier non trouvé'}, status=404)
#
#     elif file_extension == '.pdf':
#         # Mode visualisation PDF dans le navigateur
#         try:
#             return FileResponse(
#                 open(document.file.path, 'rb'),
#                 content_type='application/pdf',
#                 filename=document.file.name
#             )
#         except FileNotFoundError:
#             return JsonResponse({'error': 'Fichier non trouvé'}, status=404)
#
#     else:
#         # Pour les autres types de fichiers, utiliser le template de visualisation
#         context = {
#             'document': document,
#             'file_extension': file_extension,
#             'content_type': content_type,
#             'is_pdf': file_extension == '.pdf',
#             'is_image': file_extension in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff'],
#             'is_text': file_extension in ['.txt', '.md', '.csv'],
#             'file_url': document.file.url,
#         }
#
#         return render(request, 'documents/view.html', context)
#
#
# @login_required
# def document_upload(request):
#     """Upload d'un nouveau document"""
#     if request.user.role not in ['admin', 'uploader']:
#         messages.error(request, 'Vous n\'avez pas les permissions pour uploader des documents.')
#         return redirect('dashboard:home')
#
#     if request.method == 'POST':
#         from .forms import DocumentUploadForm
#         form = DocumentUploadForm(request.POST, request.FILES)
#         if form.is_valid():
#             document = form.save(commit=False)
#             document.save()
#
#             # Log d'audit
#             AuditLog.objects.create(
#                 user=request.user,
#                 document=document,
#                 action='upload',
#                 description=f'Document {document.title} uploadé',
#                 ip_address=request.META.get('REMOTE_ADDR')
#             )
#
#             # Lancer l'extraction en arrière-plan
#             from extraction.tasks import extract_document_metadata
#             try:
#                 # Appel direct de la fonction d'extraction
#                 result = extract_document_metadata(document.id)
#                 if result and result.get('success'):
#                     messages.success(request, 'Document uploadé et extraction terminée avec succès')
#                 else:
#                     messages.warning(request, 'Document uploadé mais extraction échouée')
#             except Exception as e:
#                 logger.error(f"Erreur extraction après upload: {e}")
#                 messages.warning(request, f'Document uploadé mais erreur extraction: {str(e)}')
#
#             return JsonResponse({
#                 'success': True,
#                 'message': 'Document uploadé et extraction lancée',
#                 'document_id': document.id
#             })
#         else:
#             return JsonResponse({
#                 'success': False,
#                 'errors': form.errors
#             })
#     else:
#         from .forms import DocumentUploadForm
#         form = DocumentUploadForm()
#
#     return render(request, 'documents/upload.html', {'form': form})
#
#
# @require_http_methods(["POST"])
# @login_required
# def validate_annotations(request, document_id):
#     """Valider les annotations d'un document"""
#     document = get_object_or_404(Document, id=document_id)
#
#     # Permissions élargies
#     if not (request.user.role in ['admin', 'metadonneur'] or document.assigned_to == request.user):
#         return JsonResponse({'error': 'Permission refusée'}, status=403)
#
#     # Marquer toutes les annotations comme validées
#     updated_count = Annotation.objects.filter(document=document, status='detected').update(
#         status='validated',
#         validated_by=request.user
#     )
#
#     # Changer le statut du document
#     document.status = 'annotated'
#     document.validated_by = request.user
#     document.save()
#
#     # Log d'audit
#     AuditLog.objects.create(
#         user=request.user,
#         document=document,
#         action='validate',
#         description=f'Validation de {updated_count} annotations pour le document {document.title}',
#         ip_address=request.META.get('REMOTE_ADDR')
#     )
#
#     return JsonResponse({
#         'success': True,
#         'message': f'{updated_count} annotations validées avec succès'
#     })
#
#
# @require_http_methods(["POST"])
# @login_required
# def refuse_annotation(request, document_id):
#     """Refuser l'annotation d'un document"""
#     document = get_object_or_404(Document, id=document_id)
#
#     # Permissions élargies
#     if not (request.user.role in ['admin', 'metadonneur'] or document.assigned_to == request.user):
#         return JsonResponse({'error': 'Permission refusée'}, status=403)
#
#     document.status = 'refused'
#     document.save()
#
#     # Log d'audit
#     AuditLog.objects.create(
#         user=request.user,
#         document=document,
#         action='refuse',
#         description=f'Refus d\'annotation pour le document {document.title}',
#         ip_address=request.META.get('REMOTE_ADDR')
#     )
#
#     return JsonResponse({'success': True, 'message': 'Document refusé'})
#
#
# @login_required
# def document_stats(request, document_id):
#     """Statistiques d'un document"""
#     document = get_object_or_404(Document, id=document_id)
#
#     # Permissions élargies
#     if not (request.user.role in ['admin', 'metadonneur', 'expert'] or document.assigned_to == request.user):
#         return JsonResponse({'error': 'Permission refusée'}, status=403)
#
#     # Calculer les statistiques
#     annotations_count = Annotation.objects.filter(document=document).count()
#     validated_annotations = Annotation.objects.filter(
#         document=document,
#         status='validated'
#     ).count()
#
#     # Taux d'extraction (si existe)
#     extraction_rate = None
#     if hasattr(document, 'extraction_results') and document.extraction_results.exists():
#         extraction_result = document.extraction_results.first()
#         if extraction_result and extraction_result.confidence_score:
#             extraction_rate = round(extraction_result.confidence_score * 100, 1)
#
#     return JsonResponse({
#         'annotations_count': annotations_count,
#         'validated_annotations': validated_annotations,
#         'extraction_rate': extraction_rate,
#         'document_status': document.status,
#         'document_title': document.title,
#     })
#
#
# # Vue supplémentaire pour le téléchargement direct
# @login_required
# def document_download(request, document_id):
#     """Téléchargement direct d'un document"""
#     document = get_object_or_404(Document, id=document_id)
#
#     # Permissions élargies
#     if not (request.user.role in ['admin', 'metadonneur', 'expert'] or document.assigned_to == request.user):
#         return JsonResponse({'error': 'Permission refusée'}, status=403)
#
#     # Vérifier que le fichier existe
#     if not document.file or not os.path.exists(document.file.path):
#         raise Http404("Fichier introuvable")
#
#     # Log d'audit
#     AuditLog.objects.create(
#         user=request.user,
#         document=document,
#         action='download',
#         description=f'Téléchargement du document: {document.title}',
#         ip_address=request.META.get('REMOTE_ADDR')
#     )
#
#     # Retourner le fichier
#     return FileResponse(
#         open(document.file.path, 'rb'),
#         as_attachment=True,
#         filename=os.path.basename(document.file.name)
#     )

# documents/views.py - Vue upload avec support des URLs
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, FileResponse, Http404
from django.views.decorators.http import require_http_methods
from django.core.files.storage import default_storage
from django.conf import settings
import os
import mimetypes
import logging

from .models import Document, DocumentType, DocumentContext
from .forms import DocumentUploadForm
from annotation.models import Annotation, EntityType
from audit.models import AuditLog
from extraction.services import DocumentTextExtractor
from extraction.tasks import extract_document_metadata, process_document_from_urls

logger = logging.getLogger(__name__)


@login_required
def document_upload(request):
    """Upload d'un nouveau document avec support des URLs"""
    if request.user.role not in ['admin', 'uploader', 'metadonneur']:
        messages.error(request, 'Vous n\'avez pas les permissions pour uploader des documents.')
        return redirect('dashboard:home')

    if request.method == 'POST':
        form = DocumentUploadForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                document = form.save(commit=False)
                document.assigned_to = request.user
                document.save()

                upload_mode = form.cleaned_data.get('upload_mode')

                # Log d'audit
                AuditLog.objects.create(
                    user=request.user,
                    document=document,
                    action='upload',
                    description=f'Document {document.title} créé en mode {upload_mode}',
                    ip_address=request.META.get('REMOTE_ADDR')
                )

                if upload_mode == 'file':
                    # Mode fichier classique
                    logger.info(f"📁 Upload fichier classique: {document.title}")

                    # Lancer l'extraction classique
                    try:
                        result = extract_document_metadata(document.id)
                        if result and result.get('success'):
                            return JsonResponse({
                                'success': True,
                                'message': 'Document uploadé et extraction terminée avec succès',
                                'document_id': document.id
                            })
                        else:
                            messages.warning(request, 'Document uploadé mais extraction échouée')
                            return JsonResponse({
                                'success': True,
                                'message': 'Document uploadé (extraction partielle)',
                                'document_id': document.id
                            })
                    except Exception as e:
                        logger.error(f"Erreur extraction après upload: {e}")
                        return JsonResponse({
                            'success': True,
                            'message': f'Document uploadé mais erreur extraction: {str(e)}',
                            'document_id': document.id
                        })

                elif upload_mode == 'url':
                    # Mode URLs
                    logger.info(f"🔗 Upload via URLs: {document.title}")
                    logger.info(f"   PDF: {document.direct_pdf_url}")
                    logger.info(f"   EMA: {document.ema_page_url}")

                    # Lancer le traitement par URLs
                    try:
                        result = process_document_from_urls(
                            document.id,
                            document.direct_pdf_url,
                            document.ema_page_url
                        )

                        if result and result.get('success'):
                            return JsonResponse({
                                'success': True,
                                'message': 'Document créé et traitement par URLs terminé avec succès',
                                'document_id': document.id,
                                'title_extracted': result.get('title_extracted', ''),
                                'ema_data_found': result.get('ema_data_found', False)
                            })
                        else:
                            error_msg = result.get('error', 'Erreur inconnue') if result else 'Aucun résultat'
                            return JsonResponse({
                                'success': False,
                                'error': f'Échec traitement URLs: {error_msg}'
                            })
                    except Exception as e:
                        logger.error(f"Erreur traitement URLs: {e}")
                        # Supprimer le document en cas d'échec critique
                        document.delete()
                        return JsonResponse({
                            'success': False,
                            'error': f'Erreur critique traitement URLs: {str(e)}'
                        })

            except Exception as e:
                logger.error(f"Erreur création document: {e}")
                return JsonResponse({
                    'success': False,
                    'error': f'Erreur création document: {str(e)}'
                })
        else:
            # Erreurs de validation du formulaire
            return JsonResponse({
                'success': False,
                'errors': form.errors
            })
    else:
        form = DocumentUploadForm()

    context = {
        'form': form,
        'document_types': DocumentType.objects.all().order_by('name'),
        'document_contexts': DocumentContext.objects.all().order_by('name')
    }

    return render(request, 'documents/upload.html', context)


@login_required
def document_list(request):
    """Liste des documents pour annotation"""

    # DEBUG: Vérifier tous les documents
    all_documents = Document.objects.all()
    print(f"Tous les documents: {all_documents.count()}")

    # DEBUG: Vérifier les documents par statut
    for status in ['uploaded', 'extracting', 'extracted', 'annotating', 'annotated', 'validated']:
        count = Document.objects.filter(status=status).count()
        print(f"Documents avec statut '{status}': {count}")

    # DEBUG: Vérifier les documents assignés à l'utilisateur
    user_documents = Document.objects.filter(assigned_to=request.user)
    print(f"Documents assignés à {request.user}: {user_documents.count()}")

    # Filtre selon le rôle de l'utilisateur
    if request.user.role == 'admin':
        documents = Document.objects.filter(
            status__in=['extracted', 'annotating']
        ).select_related('document_type', 'context')
    elif request.user.role == 'metadonneur':
        # Les métadonneurs peuvent voir les documents validés pour annotation
        documents = Document.objects.filter(
            status__in=['validated', 'annotating', 'annotated'],
            assigned_to=request.user
        ).select_related('document_type', 'context')
    else:
        # Pour les autres rôles (expert, annotateur, etc.)
        documents = Document.objects.filter(
            status__in=['extracted', 'annotating'],
            assigned_to=request.user
        ).select_related('document_type', 'context')

    print(f"Documents filtrés finaux: {documents.count()}")

    # DEBUG: Si aucun document filtré, on prend tous les documents de l'utilisateur
    if not documents.exists():
        print("Aucun document trouvé avec les filtres, affichage de tous les documents de l'utilisateur")
        documents = Document.objects.filter(assigned_to=request.user).select_related('document_type', 'context')

    # Si toujours aucun document, on prend TOUS les documents (pour debug admin)
    if not documents.exists() and (request.user.is_staff or request.user.role == 'admin'):
        print("Mode debug admin: affichage de tous les documents")
        documents = Document.objects.all().select_related('document_type', 'context')

    return render(request, 'documents/list.html', {'documents': documents})


@login_required
def document_annotate(request, document_id):
    """Interface d'annotation d'un document - VERSION CORRIGÉE"""
    document = get_object_or_404(Document, id=document_id)

    # Vérification des permissions élargie
    if not (request.user.role in ['admin', 'metadonneur'] or document.assigned_to == request.user):
        messages.error(request, 'Vous n\'avez pas les permissions pour accéder à ce document.')
        return redirect('documents:list')

    # Marquer le document comme en cours d'annotation
    if document.status == 'extracted':
        document.status = 'annotating'
        document.save()

    # ===== EXTRACTION DU VRAI CONTENU DU DOCUMENT =====
    document_content = ""
    try:
        # Vérifier s'il y a un fichier local ou s'il faut utiliser l'URL
        if document.file and os.path.exists(document.file.path):
            logger.info(f"Extraction du contenu depuis fichier local pour le document {document_id}")
            text_extractor = DocumentTextExtractor()
            document_content = text_extractor.extract_text_from_file(
                document.file.path,
                document.file_type
            )
        elif document.direct_pdf_url:
            logger.info(f"Extraction du contenu depuis URL pour le document {document_id}")
            from extraction.url_services import URLDocumentExtractor
            url_extractor = URLDocumentExtractor()

            # Télécharger temporairement et extraire le contenu
            temp_file = url_extractor.download_pdf_from_url(document.direct_pdf_url)
            if temp_file:
                text_extractor = DocumentTextExtractor()
                document_content = text_extractor.extract_text_from_file(temp_file, 'pdf')
                url_extractor.cleanup_temp_file(temp_file)
            else:
                document_content = "Impossible de télécharger le document depuis l'URL."
        else:
            document_content = "Aucun fichier ou URL disponible pour ce document."

        logger.info(f"Contenu extrait: {len(document_content)} caractères")

        if not document_content or len(document_content.strip()) < 10:
            document_content = "Le contenu du document est vide ou n'a pas pu être extrait."
            logger.warning(f"Contenu vide pour le document {document_id}")

    except Exception as e:
        logger.error(f"Erreur extraction texte document {document_id}: {e}")
        document_content = f"Erreur lors de l'extraction du contenu: {str(e)}"

    # ===== LANCER L'ANNOTATION AUTOMATIQUE SI NÉCESSAIRE =====
    annotations = Annotation.objects.filter(document=document).select_related('entity_type', 'created_by')

    # Si aucune annotation automatique n'existe, lancer l'IA
    if not annotations.filter(is_automatic=True).exists() and document_content and len(document_content.strip()) > 50:
        try:
            logger.info(f"Lancement de l'annotation automatique pour le document {document_id}")

            # Import de la fonction de tâche
            from extraction.tasks import auto_annotate_document

            # Appeler directement la fonction (pas de .delay() car Celery peut ne pas être disponible)
            result = auto_annotate_document(document_id)

            if result and result.get('success'):
                logger.info(f"Annotation automatique réussie: {result.get('annotations_count', 0)} annotations")
                messages.success(request,
                                 f"Annotation automatique terminée : {result.get('annotations_count', 0)} entités détectées")

                # Recharger les annotations après l'annotation automatique
                annotations = Annotation.objects.filter(document=document).select_related('entity_type', 'created_by')
            else:
                logger.warning(
                    f"Annotation automatique échouée: {result.get('error', 'Erreur inconnue') if result else 'Aucun résultat'}")
                messages.warning(request, "L'annotation automatique n'a pas pu être effectuée.")

        except Exception as e:
            logger.error(f"Erreur lors du lancement de l'annotation automatique: {e}")
            messages.warning(request, f"Erreur lors de l'annotation automatique: {str(e)}")

    # Types d'entités disponibles
    entity_types = EntityType.objects.all()

    # Si aucun type d'entité n'existe, en créer quelques-uns par défaut
    if not entity_types.exists():
        default_entity_types = [
            {'name': 'CONDITION', 'color': '#dc3545', 'description': 'Conditions médicales'},
            {'name': 'FACTEUR', 'color': '#fd7e14', 'description': 'Facteurs de risque'},
            {'name': 'METHODE', 'color': '#20c997', 'description': 'Méthodes et analyses'},
            {'name': 'EFFET', 'color': '#6f42c1', 'description': 'Effets et résultats'},
            {'name': 'AUTEUR', 'color': '#0dcaf0', 'description': 'Auteurs et personnes'},
            {'name': 'ORGANISATION', 'color': '#198754', 'description': 'Organisations'},
            {'name': 'DATE', 'color': '#ffc107', 'description': 'Dates'},
            {'name': 'LIEU', 'color': '#6c757d', 'description': 'Lieux'},
        ]

        for et_data in default_entity_types:
            EntityType.objects.get_or_create(
                name=et_data['name'],
                defaults={
                    'color': et_data['color'],
                    'description': et_data['description']
                }
            )

        # Recharger les types d'entités
        entity_types = EntityType.objects.all()
        messages.info(request, "Types d'entités par défaut créés.")

    context = {
        'document': document,
        'annotations': annotations,
        'entity_types': entity_types,
        'document_content': document_content,
    }

    return render(request, 'documents/annotate.html', context)


@login_required
def document_view(request, document_id):
    """Visualiser un document - VERSION ADAPTÉE pour URLs"""
    document = get_object_or_404(Document, id=document_id)

    # Permissions élargies pour inclure les métadonneurs
    if not (request.user.role in ['admin', 'metadonneur', 'expert'] or document.assigned_to == request.user):
        messages.error(request, 'Vous n\'avez pas les permissions pour visualiser ce document.')
        return JsonResponse({'error': 'Permission refusée'}, status=403)

    # Log d'audit
    AuditLog.objects.create(
        user=request.user,
        document=document,
        action='view',
        description=f'Visualisation du document: {document.title}',
        ip_address=request.META.get('REMOTE_ADDR')
    )

    # Gestion différente selon le mode (fichier local ou URL)
    if document.file and os.path.exists(document.file.path):
        # Mode fichier local
        file_extension = os.path.splitext(document.file.name)[1].lower()
        content_type, _ = mimetypes.guess_type(document.file.path)

        # Mode téléchargement
        if request.GET.get('download') == '1':
            try:
                return FileResponse(
                    open(document.file.path, 'rb'),
                    as_attachment=True,
                    filename=os.path.basename(document.file.name)
                )
            except FileNotFoundError:
                return JsonResponse({'error': 'Fichier non trouvé'}, status=404)

        # Mode visualisation PDF dans le navigateur
        elif file_extension == '.pdf':
            try:
                return FileResponse(
                    open(document.file.path, 'rb'),
                    content_type='application/pdf',
                    filename=document.file.name
                )
            except FileNotFoundError:
                return JsonResponse({'error': 'Fichier non trouvé'}, status=404)

    elif document.direct_pdf_url:
        # Mode URL - rediriger vers l'URL directe du PDF
        if request.GET.get('download') == '1':
            # Forcer le téléchargement via notre serveur
            try:
                from extraction.url_services import URLDocumentExtractor
                url_extractor = URLDocumentExtractor()
                temp_file = url_extractor.download_pdf_from_url(document.direct_pdf_url)

                if temp_file:
                    response = FileResponse(
                        open(temp_file, 'rb'),
                        as_attachment=True,
                        filename=f"{document.title}.pdf"
                    )
                    # Nettoyer le fichier temporaire après envoi
                    url_extractor.cleanup_temp_file(temp_file)
                    return response
                else:
                    return JsonResponse({'error': 'Impossible de télécharger le fichier'}, status=404)
            except Exception as e:
                return JsonResponse({'error': f'Erreur téléchargement: {str(e)}'}, status=500)
        else:
            # Redirection vers l'URL directe pour visualisation
            return redirect(document.direct_pdf_url)

    else:
        # Aucun fichier ni URL disponible
        return JsonResponse({'error': 'Aucun fichier ou URL disponible'}, status=404)


# [Les autres vues restent inchangées...]

@login_required
@require_http_methods(["POST"])
def validate_annotations(request, document_id):
    """Valider les annotations d'un document"""
    document = get_object_or_404(Document, id=document_id)

    # Permissions élargies
    if not (request.user.role in ['admin', 'metadonneur'] or document.assigned_to == request.user):
        return JsonResponse({'error': 'Permission refusée'}, status=403)

    # Marquer toutes les annotations comme validées
    updated_count = Annotation.objects.filter(document=document, status='detected').update(
        status='validated',
        validated_by=request.user
    )

    # Changer le statut du document
    document.status = 'annotated'
    document.validated_by = request.user
    document.save()

    # Log d'audit
    AuditLog.objects.create(
        user=request.user,
        document=document,
        action='validate',
        description=f'Validation de {updated_count} annotations pour le document {document.title}',
        ip_address=request.META.get('REMOTE_ADDR')
    )

    return JsonResponse({
        'success': True,
        'message': f'{updated_count} annotations validées avec succès'
    })


@login_required
@require_http_methods(["POST"])
def refuse_annotation(request, document_id):
    """Refuser l'annotation d'un document"""
    document = get_object_or_404(Document, id=document_id)

    # Permissions élargies
    if not (request.user.role in ['admin', 'metadonneur'] or document.assigned_to == request.user):
        return JsonResponse({'error': 'Permission refusée'}, status=403)

    document.status = 'refused'
    document.save()

    # Log d'audit
    AuditLog.objects.create(
        user=request.user,
        document=document,
        action='refuse',
        description=f'Refus d\'annotation pour le document {document.title}',
        ip_address=request.META.get('REMOTE_ADDR')
    )

    return JsonResponse({'success': True, 'message': 'Document refusé'})


@login_required
def document_stats(request, document_id):
    """Statistiques d'un document"""
    document = get_object_or_404(Document, id=document_id)

    # Permissions élargies
    if not (request.user.role in ['admin', 'metadonneur', 'expert'] or document.assigned_to == request.user):
        return JsonResponse({'error': 'Permission refusée'}, status=403)

    # Calculer les statistiques
    annotations_count = Annotation.objects.filter(document=document).count()
    validated_annotations = Annotation.objects.filter(
        document=document,
        status='validated'
    ).count()

    # Taux d'extraction (si existe)
    extraction_rate = None
    if hasattr(document, 'extraction_results') and document.extraction_results.exists():
        extraction_result = document.extraction_results.first()
        if extraction_result and extraction_result.confidence_score:
            extraction_rate = round(extraction_result.confidence_score * 100, 1)

    return JsonResponse({
        'annotations_count': annotations_count,
        'validated_annotations': validated_annotations,
        'extraction_rate': extraction_rate,
        'document_status': document.status,
        'document_title': document.title,
        'has_file': bool(document.file),
        'has_urls': document.has_urls,
        'can_extract_from_url': document.can_extract_from_url,
    })


@login_required
def document_download(request, document_id):
    """Téléchargement direct d'un document"""
    document = get_object_or_404(Document, id=document_id)

    # Permissions élargies
    if not (request.user.role in ['admin', 'metadonneur', 'expert'] or document.assigned_to == request.user):
        return JsonResponse({'error': 'Permission refusée'}, status=403)

    # Gestion différente selon le mode
    if document.file and os.path.exists(document.file.path):
        # Mode fichier local
        return FileResponse(
            open(document.file.path, 'rb'),
            as_attachment=True,
            filename=os.path.basename(document.file.name)
        )
    elif document.direct_pdf_url:
        # Mode URL - télécharger via notre serveur
        try:
            from extraction.url_services import URLDocumentExtractor
            url_extractor = URLDocumentExtractor()
            temp_file = url_extractor.download_pdf_from_url(document.direct_pdf_url)

            if temp_file:
                response = FileResponse(
                    open(temp_file, 'rb'),
                    as_attachment=True,
                    filename=f"{document.title}.pdf"
                )
                # Nettoyer après envoi
                url_extractor.cleanup_temp_file(temp_file)
                return response
            else:
                raise Http404("Impossible de télécharger le fichier")
        except Exception as e:
            raise Http404(f"Erreur téléchargement: {str(e)}")
    else:
        raise Http404("Aucun fichier ou URL disponible")

    # Log d'audit
    AuditLog.objects.create(
        user=request.user,
        document=document,
        action='download',
        description=f'Téléchargement du document: {document.title}',
        ip_address=request.META.get('REMOTE_ADDR')
    )