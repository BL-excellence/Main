import os
import json
from datetime import datetime
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils import timezone
from django.core.files.base import ContentFile
from django.db import transaction

from rawdocs.models import RawDocument
from rawdocs.utils import extract_metadonnees, extract_full_text
from client.library.models import Document, DocumentCategory, RegulatoryAuthority


@login_required
def client_upload_document(request):
    """
    Interface d'upload de document pour les clients avec extraction automatique des métadonnées
    """
    if request.method == 'POST':
        try:
            # Récupérer le fichier uploadé
            uploaded_file = request.FILES.get('file')
            if not uploaded_file:
                messages.error(request, "Veuillez sélectionner un fichier à uploader.")
                return redirect('client:library:client_upload')

            # Créer un RawDocument temporaire pour l'extraction des métadonnées
            with transaction.atomic():
                # Créer le RawDocument avec le client comme owner et source 'Client'
                raw_document = RawDocument(
                    owner=request.user,
                    source='Client'  # Définir la source avant la sauvegarde pour le bon dossier
                )
                raw_document.file.save(uploaded_file.name, uploaded_file)
                raw_document.save()

                # Extraire les métadonnées en utilisant le même système que les métadonneurs
                print(f"🔍 Extraction des métadonnées pour le document client {raw_document.pk}")
                metadata = extract_metadonnees(raw_document.file.path, "")
                
                if metadata:
                    # Sauvegarder les métadonnées extraites dans le RawDocument
                    raw_document.title = metadata.get('title', '')
                    raw_document.doc_type = metadata.get('type', '')
                    raw_document.publication_date = metadata.get('publication_date', '')
                    raw_document.version = metadata.get('version', '')
                    raw_document.source = 'Client'  # FORCER la source à 'Client'
                    raw_document.context = metadata.get('context', '')
                    raw_document.country = metadata.get('country', '')
                    raw_document.language = metadata.get('language', '')
                    raw_document.url_source = metadata.get('url_source', '')
                    
                    # Marquer comme validé automatiquement pour les clients
                    raw_document.is_validated = True
                    raw_document.validated_at = timezone.now()
                    raw_document.save()
                    
                    print(f"✅ Métadonnées extraites et sauvegardées pour le document client {raw_document.pk}")
                    print(f"   - Titre: {raw_document.title}")
                    print(f"   - Type: {raw_document.doc_type}")
                    print(f"   - Source: {raw_document.source}")
                    print(f"   - Pays: {raw_document.country}")
                    
                    messages.success(request, f"Document '{raw_document.title or uploaded_file.name}' uploadé avec succès!")
                    return redirect('client:library:client_document_detail', pk=raw_document.pk)
                else:
                    # Même en cas d'échec de l'extraction, on garde le document avec source 'Client'
                    raw_document.title = uploaded_file.name
                    raw_document.source = 'Client'
                    raw_document.is_validated = True
                    raw_document.validated_at = timezone.now()
                    raw_document.save()
                    
                    messages.warning(request, f"Document '{uploaded_file.name}' uploadé, mais l'extraction automatique des métadonnées a échoué.")
                    return redirect('client:library:client_document_detail', pk=raw_document.pk)

        except Exception as e:
            print(f"❌ Erreur lors de l'upload client: {e}")
            messages.error(request, f"Erreur lors de l'upload du document: {str(e)}")
            return redirect('client:library:client_upload')
    
    # GET request - afficher le formulaire d'upload
    return render(request, 'client/library/client_upload.html')


@login_required
def client_document_detail(request, pk):
    """
    Détail d'un document uploadé par un client
    """
    document = get_object_or_404(RawDocument, pk=pk, owner=request.user, source='Client')
    
    # Préparer les métadonnées pour l'affichage
    metadata = {
        'title': document.title or 'Non spécifié',
        'doc_type': document.doc_type or 'Non spécifié', 
        'publication_date': document.publication_date or 'Non spécifiée',
        'version': document.version or 'Non spécifiée',
        'source': document.source or 'Client',
        'context': document.context or 'Non spécifié',
        'country': document.country or 'Non spécifié',
        'language': document.language or 'Non spécifiée',
        'url_source': document.url_source or 'Non spécifiée',
        'owner': document.owner.username if document.owner else 'Non spécifié',
        'created_at': document.created_at,
        'is_validated': document.is_validated,
        'validated_at': document.validated_at,
        'total_pages': document.total_pages,
        'pages_extracted': document.pages_extracted,
    }
    
    # Documents similaires (même type et pays, uploadés par des clients)
    related_documents = RawDocument.objects.filter(
        doc_type=document.doc_type,
        country=document.country,
        source='Client',
        is_validated=True
    ).exclude(pk=document.pk)[:5]
    
    context = {
        'document': document,
        'metadata': metadata,
        'related_documents': related_documents,
    }
    return render(request, 'client/library/client_document_detail.html', context)


@login_required
def client_documents_list(request):
    """
    Liste des documents uploadés par le client connecté
    """
    documents = RawDocument.objects.filter(
        owner=request.user,
        source='Client'
    ).order_by('-created_at')
    
    # Statistiques pour le client
    total_documents = documents.count()
    validated_documents = documents.filter(is_validated=True).count()
    
    # Types de documents uploadés par ce client
    document_types = documents.exclude(doc_type='').values_list('doc_type', flat=True).distinct()
    
    context = {
        'documents': documents,
        'total_documents': total_documents,
        'validated_documents': validated_documents,
        'document_types': document_types,
    }
    return render(request, 'client/library/client_documents_list.html', context)


@login_required
def delete_client_document(request, pk):
    """
    Supprimer un document uploadé par le client
    """
    document = get_object_or_404(RawDocument, pk=pk, owner=request.user, source='Client')
    
    if request.method == 'POST':
        document_title = document.title or 'Document sans titre'
        document.delete()
        messages.success(request, f"Document '{document_title}' supprimé avec succès.")
        return redirect('client:library:client_documents_list')
    
    return render(request, 'client/library/confirm_delete.html', {'document': document})


@login_required
def download_client_document(request, pk):
    """
    Télécharger un document uploadé par le client
    """
    from django.http import HttpResponse, Http404
    
    document = get_object_or_404(RawDocument, pk=pk, owner=request.user, source='Client')
    
    if not document.file:
        raise Http404("Fichier non trouvé")
    
    try:
        response = HttpResponse(document.file.read(), content_type='application/pdf')
        filename = document.file.name.split('/')[-1]
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
    except Exception as e:
        messages.error(request, f"Erreur lors du téléchargement: {str(e)}")
        return redirect('client:library:client_document_detail', pk=pk)