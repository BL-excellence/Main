from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils.decorators import method_decorator
from django.views.generic import View
from rest_framework import generics, status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from .models import Product, ProductSpecification, ManufacturingSite, ProductVariation
from .serializers import ProductListSerializer, ProductDetailSerializer
import json
import logging
import base64
import hashlib
import requests
from django.contrib.auth.models import User
import tempfile
import zipfile
import os
from google.auth.transport.requests import Request
from pathlib import Path
from cryptography.fernet import Fernet
from django.conf import settings
from django.utils import timezone
from datetime import datetime, timedelta
import uuid
from .models import CloudConnection, ProductECTDFile, CloudProvider

logger = logging.getLogger(__name__)
def setup_rar_tool():
    """Auto-detect RAR tool on Windows"""
    import rarfile
    import os
    
    # Common Windows paths for RAR tools
    possible_paths = [
        r"C:\Program Files\7-Zip\7z.exe",
        r"C:\Program Files (x86)\7-Zip\7z.exe",
        r"C:\Program Files\WinRAR\unrar.exe",
        r"C:\Program Files (x86)\WinRAR\unrar.exe",
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            rarfile.UNRAR_TOOL = path
            print(f"✅ Found RAR tool: {path}")
            return True
    
    print("❌ No RAR tool found. Please install 7-Zip or WinRAR")
    return False


def products_list_view(request):
    """Vue principale des produits"""
    return render(request, 'client/products/products_list.html')

def product_detail_view(request, pk):
    """Vue détail d'un produit"""
    product = get_object_or_404(Product, pk=pk)
    return render(request, 'client/products/product_detail.html', {'product': product})


def setup_rar_tool():
    """Auto-detect RAR tool on Windows"""
    import rarfile
    import os
    
    # Try to find unrar.exe first (preferred)
    unrar_paths = [
        r"C:\Program Files\WinRAR\unrar.exe",
        r"C:\Program Files (x86)\WinRAR\unrar.exe",
    ]
    
    for path in unrar_paths:
        if os.path.exists(path):
            rarfile.UNRAR_TOOL = path
            print(f"✅ Found UNRAR tool: {path}")
            return True
    
    # If no unrar, try 7-Zip but with special handling
    sevenzip_paths = [
        r"C:\Program Files\7-Zip\7z.exe",
        r"C:\Program Files (x86)\7-Zip\7z.exe",
    ]
    
    for path in sevenzip_paths:
        if os.path.exists(path):
            # 7-Zip needs special configuration
            rarfile.UNRAR_TOOL = path
            rarfile.ORIG_UNRAR_TOOL = path
            # Set 7-Zip specific options
            rarfile.UNRAR_TOOL_OPTIONS = ['x', '-y']  # extract with yes to all
            print(f"✅ Found 7-Zip tool: {path}")
            return True
    
    print("❌ No RAR tool found. Please install WinRAR or 7-Zip")
    return False

class ProductListAPIView(generics.ListCreateAPIView):
    serializer_class = ProductListSerializer
    
    def get_queryset(self):
        queryset = Product.objects.all().order_by('-created_at')
        search = self.request.GET.get('search', '')
        
        if search:
            queryset = queryset.filter(
                name__icontains=search
            ) | queryset.filter(
                active_ingredient__icontains=search
            )
        
        return queryset
    
    def create(self, request, *args, **kwargs):
        """Create a new product with all related data"""
        try:
            
            data = request.data
                
            logger.info(f"Creating product with data: {data}")
            
            # Extract product data
            product_data = data.get('product', {})
            regulatory_data = data.get('regulatory', {})
            sites_data = data.get('sites', [])
            
            # Create product
            product_serializer = ProductListSerializer(data=product_data)
            if product_serializer.is_valid():
                product = product_serializer.save()
                logger.info(f"Product created with ID: {product.id}")
                
                # Create regulatory specification only if we have the required fields
                if (regulatory_data and 
                    regulatory_data.get('renewal_date') and 
                    regulatory_data.get('approval_date')):
                    
                    from datetime import datetime
                    
                    # Parse date strings to date objects
                    approval_date = None
                    renewal_date = None
                    
                    if regulatory_data.get('approval_date'):
                        approval_date = datetime.strptime(regulatory_data.get('approval_date'), '%Y-%m-%d').date()
                    
                    if regulatory_data.get('renewal_date'):
                        renewal_date = datetime.strptime(regulatory_data.get('renewal_date'), '%Y-%m-%d').date()
                    
                    spec = ProductSpecification.objects.create(
                        product=product,
                        country_code=regulatory_data.get('country_code', 'FR'),
                        amm_number=regulatory_data.get('amm_number', ''),
                        approval_date=approval_date,
                        renewal_date=renewal_date,
                        ctd_dossier_complete=regulatory_data.get('ctd_dossier_complete', False),
                        gmp_certificate=regulatory_data.get('gmp_certificate', False),
                        inspection_report=regulatory_data.get('inspection_report', False),
                        rcp_etiquetage=regulatory_data.get('rcp_etiquetage', False),
                    )
                    logger.info(f"Regulatory spec created for product {product.id}")
                # Create manufacturing sites if provided
                for site_data in sites_data:
                    if site_data.get('country') and site_data.get('city') and site_data.get('site_name'):
                        site = ManufacturingSite.objects.create(
                            product=product,
                            country=site_data['country'],
                            city=site_data['city'],
                            site_name=site_data['site_name'],
                            gmp_certified=site_data.get('gmp_certified', False)
                        )
                        logger.info(f"Site created: {site.site_name} for product {product.id}")
                
                # Return the product in the same format as the list
                response_data = {
                    'id': product.id,
                    'name': product.name,
                    'active_ingredient': product.active_ingredient,
                    'dosage': product.dosage,
                    'form': product.form,
                    'therapeutic_area': product.therapeutic_area,
                    'status': product.status,
                    'created_at': product.created_at.isoformat(),
                    'updated_at': product.updated_at.isoformat(),
                }
                
                return Response(response_data, status=status.HTTP_201_CREATED)
            else:
                logger.error(f"Product validation failed: {product_serializer.errors}")
                return Response(
                    {'errors': product_serializer.errors},
                    status=status.HTTP_400_BAD_REQUEST
                )
                
        except Exception as e:
            logger.error(f"Error creating product: {str(e)}")
            return Response(
                {'error': f'Erreur lors de la création du produit: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class ProductDetailAPIView(generics.RetrieveAPIView):
    queryset = Product.objects.all()
    serializer_class = ProductDetailSerializer

@api_view(['GET'])
def search_products(request):
    """Search products"""
    query = request.GET.get('q', '')
    if query:
        products = Product.objects.filter(
            name__icontains=query
        ) | Product.objects.filter(
            active_ingredient__icontains=query
        )
    else:
        products = Product.objects.all()
    
    serializer = ProductListSerializer(products, many=True)
    return Response(serializer.data)

@api_view(['GET'])
def product_overview(request, pk):
    """API pour l'onglet Vue d'ensemble"""
    try:
        product = get_object_or_404(Product, pk=pk)
        specifications = ProductSpecification.objects.filter(product=product)
        
        logger.info(f"Loading overview for product {pk}")
        
        data = {
            'product': {
                'id': product.id,
                'name': product.name,
                'active_ingredient': product.active_ingredient,
                'dosage': product.dosage,
                'form': product.form,
                'therapeutic_area': product.therapeutic_area,
                'status': product.status,
                'source_document': product.source_document.id if product.source_document else None, 
                'created_at': product.created_at.isoformat(),
                'updated_at': product.updated_at.isoformat(),
            },
            'specifications': [
                {
                    'country': spec.country_code,
                    'amm_number': spec.amm_number,
                    'approval_date': spec.approval_date.isoformat() if spec.approval_date else None,
                    'renewal_date': spec.renewal_date.isoformat() if spec.renewal_date else None,
                    'documents': {
                        'ctd_dossier_complete': spec.ctd_dossier_complete,
                        'gmp_certificate': spec.gmp_certificate,
                        'inspection_report': spec.inspection_report,
                        'rcp_etiquetage': spec.rcp_etiquetage,
                    }
                }
                for spec in specifications
            ]
        }
        
        logger.info(f"Overview data for product {pk}: {len(data['specifications'])} specifications")
        return Response(data)
        
    except Product.DoesNotExist:
        logger.error(f"Product {pk} not found")
        return Response(
            {'error': 'Produit non trouvé'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Error loading overview for product {pk}: {str(e)}")
        return Response(
            {'error': str(e)}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['GET'])
def product_sites(request, pk):
    """API pour l'onglet Sites"""
    try:
        product = get_object_or_404(Product, pk=pk)
        sites = ManufacturingSite.objects.filter(product=product)
        
        logger.info(f"Loading sites for product {pk}: {sites.count()} sites found")
        
        data = [
            {
                'id': site.id,
                'country': site.country,
                'city': site.city,
                'site_name': site.site_name,
                'gmp_certified': site.gmp_certified,
                'gmp_expiry': site.gmp_expiry.isoformat() if site.gmp_expiry else None,
                'last_audit': site.last_audit.isoformat() if site.last_audit else None,
            }
            for site in sites
        ]
        
        return Response(data)
        
    except Product.DoesNotExist:
        logger.error(f"Product {pk} not found")
        return Response(
            {'error': 'Produit non trouvé'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Error loading sites for product {pk}: {str(e)}")
        return Response(
            {'error': str(e)}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['GET'])
def product_variations(request, pk):
    """API pour l'onglet Variations"""
    try:
        product = get_object_or_404(Product, pk=pk)
        variations = ProductVariation.objects.filter(product=product).order_by('-submission_date')
        
        logger.info(f"Loading variations for product {pk}: {variations.count()} variations found")
        
        data = [
            {
                'id': var.id,
                'variation_type': var.variation_type,
                'title': var.title,
                'description': var.description,
                'submission_date': var.submission_date.isoformat() if var.submission_date else None,
                'approval_date': var.approval_date.isoformat() if var.approval_date else None,
                'status': var.status,
            }
            for var in variations
        ]
        
        return Response(data)
        
    except Product.DoesNotExist:
        logger.error(f"Product {pk} not found")
        return Response(
            {'error': 'Produit non trouvé'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Error loading variations for product {pk}: {str(e)}")
        return Response(
            {'error': str(e)}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    

def product_source_document_view(request, pk):
    """View to display the source document for a product"""
    product = get_object_or_404(Product, pk=pk)
    
    # Check if product has a source document
    if hasattr(product, 'source_document') and product.source_document:
        document = product.source_document
        
        # Check if document file exists
        if document.file:
            try:
                # Serve the PDF file directly in browser
                response = HttpResponse(document.file.read(), content_type='application/pdf')
                response['Content-Disposition'] = f'inline; filename="{document.file.name}"'
                return response
            except:
                # If file doesn't exist, show error
                return HttpResponse(
                    "<html><body><h2>Erreur</h2>"
                    "<p>Le fichier PDF n'a pas pu être chargé.</p>"
                    "<script>window.close();</script></body></html>"
                )
        else:
            return HttpResponse(
                "<html><body><h2>Aucun fichier disponible</h2>"
                "<p>Ce document n'a pas de fichier PDF associé.</p>"
                "<script>window.close();</script></body></html>"
            )
    else:
        # Return a simple message if no source document exists
        return HttpResponse(
            "<html><body><h2>Aucun document source disponible</h2>"
            "<p>Ce produit n'a pas de document source associé.</p>"
            "<script>window.close();</script></body></html>"
        )
    
@api_view(['POST'])
def add_product_variation(request, pk):
    """API pour ajouter une nouvelle variation"""
    try:
        product = get_object_or_404(Product, pk=pk)
        
        # Get data from request
        data = request.data
        
        # Parse the submission_date string to a date object
        submission_date = None
        if data.get('submission_date'):
            from datetime import datetime
            submission_date = datetime.strptime(data.get('submission_date'), '%Y-%m-%d').date()
        
        # Create the variation
        variation = ProductVariation.objects.create(
            product=product,
            variation_type=data.get('variation_type'),
            title=data.get('title', ''),
            description=data.get('description', ''),
            submission_date=submission_date,  # Now it's a date object
            status='soumis'  # Default status
        )
        
        logger.info(f"Variation created for product {pk}: {variation.title}")
        
        # Return the created variation
        response_data = {
            'id': variation.id,
            'variation_type': variation.variation_type,
            'title': variation.title,
            'description': variation.description,
            'submission_date': variation.submission_date.isoformat() if variation.submission_date else None,
            'approval_date': variation.approval_date.isoformat() if variation.approval_date else None,
            'status': variation.status,
        }
        
        return Response(response_data, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        logger.error(f"Error creating variation for product {pk}: {str(e)}")
        return Response(
            {'error': str(e)}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    
@api_view(['GET'])
def setup_cloud_connection(request):
    connections = CloudConnection.objects.filter(user=request.user)
    data = {
        'existing_connections': [
            {
                'id': conn.id,
                'provider': conn.get_provider_display(),
                'name': conn.connection_name,
                'is_compliant': all([conn.data_residency_eu, conn.scc_agreement, conn.dpa_signed])
            }
            for conn in connections
        ],
        'available_providers': [
            {'id': provider[0], 'name': provider[1]}
            for provider in CloudProvider.choices
        ]
    }
    return Response(data)

@api_view(['POST'])
def initiate_cloud_oauth(request):
    
    provider = request.data.get('provider')
    connection_name = request.data.get('connection_name', f'{provider}_connection')
    
    # Vérifications RGPD (gardez cette partie)
    required_rgpd_data = {
        'eu_residency': request.data.get('eu_residency'),
        'scc_agreement': request.data.get('scc_agreement'),
        'dpa_signed': request.data.get('dpa_signed'),
        'data_subjects_categories': request.data.get('data_subjects_categories', []),
        'sub_processors_acknowledged': request.data.get('sub_processors_acknowledged'),
        'privacy_notice_method': request.data.get('privacy_notice_method'),
        'technical_measures_confirmed': request.data.get('technical_measures_confirmed'),
        'transfer_safeguards_confirmed': request.data.get('transfer_safeguards_confirmed'),
        'final_validation': request.data.get('final_validation')
    }
    
    missing_fields = [field for field, value in required_rgpd_data.items() if not value]
    if missing_fields:
        return Response({
            'error': 'Conformité RGPD incomplète',
            'missing_requirements': missing_fields
        }, status=400)
    
    oauth_state = str(uuid.uuid4())
    
    # Stocker les données RGPD en session
    request.session[f'oauth_state_{oauth_state}'] = {
        'provider': provider,
        'connection_name': connection_name,
        'user_id': request.user.id,
        'rgpd_data': required_rgpd_data,
        'expires_at': (timezone.now() + timedelta(minutes=10)).isoformat()
    }
    
    # URLs OAuth RÉELLES
    if provider == 'google_drive':
        oauth_url = (
            f"https://accounts.google.com/o/oauth2/v2/auth?"
            f"client_id={settings.GOOGLE_OAUTH_CLIENT_ID}&"
            f"response_type=code&"
            f"scope=https://www.googleapis.com/auth/drive.readonly https://www.googleapis.com/auth/userinfo.email&"
            f"redirect_uri={settings.OAUTH_REDIRECT_URI}&"
            f"state={oauth_state}&"
            f"access_type=offline&"
            f"prompt=consent"
        )

    elif provider == 'onedrive':
        oauth_url = (
            f"https://login.microsoftonline.com/common/oauth2/v2.0/authorize?"
            f"client_id={settings.MICROSOFT_CLIENT_ID}&"
            f"response_type=code&"
            f"scope=https://graph.microsoft.com/Files.Read offline_access&"
            f"redirect_uri={settings.OAUTH_REDIRECT_URI}&"
            f"state={oauth_state}&"
            f"prompt=consent"
        )
    else:
        return Response({'error': 'Provider non supporté'}, status=400)
    
    return Response({
        'oauth_url': oauth_url,
        'state': oauth_state,
        'provider': provider,
        'message': 'Redirection vers authentification RÉELLE'
    })


def exchange_oauth_code_for_tokens(provider: str, code: str) -> dict:
    """Échanger le code OAuth contre des tokens d'accès réels"""
    
    token_endpoints = {
        'google_drive': 'https://oauth2.googleapis.com/token',
        'onedrive': 'https://login.microsoftonline.com/common/oauth2/v2.0/token',
        'sharepoint': 'https://login.microsoftonline.com/common/oauth2/v2.0/token',
        'dropbox': 'https://api.dropboxapi.com/oauth2/token',
        'box': 'https://api.box.com/oauth2/token'
    }
    
    client_credentials = {
        'google_drive': {
            'client_id': settings.GOOGLE_OAUTH_CLIENT_ID,
            'client_secret': settings.GOOGLE_OAUTH_CLIENT_SECRET
        },
        'onedrive': {
            'client_id': settings.MICROSOFT_CLIENT_ID,
            'client_secret': settings.MICROSOFT_CLIENT_SECRET
        },
        'sharepoint': {
            'client_id': settings.MICROSOFT_CLIENT_ID,
            'client_secret': settings.MICROSOFT_CLIENT_SECRET
        },
        'dropbox': {
            'client_id': settings.DROPBOX_CLIENT_ID,
            'client_secret': settings.DROPBOX_CLIENT_SECRET
        },
        'box': {
            'client_id': settings.BOX_CLIENT_ID,
            'client_secret': settings.BOX_CLIENT_SECRET
        }
    }
    
    if provider not in token_endpoints:
        raise ValueError(f"Provider {provider} non supporté")
    
    creds = client_credentials[provider]
    
    # Préparer la requête de token - OneDrive needs specific scope
    if provider == 'onedrive':
        token_data = {
            'grant_type': 'authorization_code',
            'code': code,
            'client_id': creds['client_id'],
            'client_secret': creds['client_secret'],
            'redirect_uri': settings.OAUTH_REDIRECT_URI,
            'scope': 'https://graph.microsoft.com/Files.Read offline_access'
        }
    else:
        token_data = {
            'grant_type': 'authorization_code',
            'code': code,
            'client_id': creds['client_id'],
            'client_secret': creds['client_secret'],
            'redirect_uri': settings.OAUTH_REDIRECT_URI
        }
    
    try:
        response = requests.post(
            token_endpoints[provider],
            data=token_data,
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            timeout=30
        )
        response.raise_for_status()
        
        tokens = response.json()
        logger.info(f"✅ Tokens obtenus pour {provider}")
        logger.info(f"DEBUG: Token response keys: {list(tokens.keys())}")
        return tokens
        
    except requests.RequestException as e:
        logger.error(f"❌ Erreur échange tokens {provider}: {e}")
        raise Exception(f"Échec de l'échange de tokens: {e}")

def encrypt_token_real(token: str, user) -> bytes:
    """Chiffrement réel des tokens avec Fernet"""
    
    if not token:
        return b''
    
    # Générer une clé basée sur l'utilisateur et le secret Django
    key_material = f"{settings.SECRET_KEY}:{user.pk}:{user.username}:{user.date_joined.isoformat()}"
    key = base64.urlsafe_b64encode(hashlib.sha256(key_material.encode()).digest())
    
    fernet = Fernet(key)
    return fernet.encrypt(token.encode())

def decrypt_token_real(encrypted_token: bytes, user) -> str:
    """Déchiffrement réel des tokens"""
    
    if not encrypted_token:
        return ''
    
    key_material = f"{settings.SECRET_KEY}:{user.pk}:{user.username}:{user.date_joined.isoformat()}"
    key = base64.urlsafe_b64encode(hashlib.sha256(key_material.encode()).digest())
    
    fernet = Fernet(key)
    return fernet.decrypt(encrypted_token).decode()

@api_view(['POST'])
def sync_ectd_files(request, pk):
    """Synchronisation réelle des fichiers eCTD depuis le cloud"""
    
    product = get_object_or_404(Product, pk=pk)
    connection_id = request.data.get('connection_id')
    folder_path = request.data.get('folder_path', '/')
    
    if not connection_id:
        return Response({'error': 'Connexion cloud requise'}, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        connection = CloudConnection.objects.get(id=connection_id, user=request.user)
        
        # Vérifier la conformité RGPD
        if not connection.rgpd_compliance_validated:
            return Response({
                'error': 'Connexion non conforme aux exigences RGPD'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Vérifier l'expiration du token
        if connection.expires_at and timezone.now() > connection.expires_at:
            return Response({
                'error': 'Token expiré, reconnexion requise'
            }, status=status.HTTP_401_UNAUTHORIZED)
        
        # Obtenir le connecteur cloud approprié
        connector = get_cloud_connector(connection)
        
        # Lancement de la synchronisation réelle
        sync_result = perform_real_ectd_sync(product, connector, connection, folder_path, request.user)
        
        # Mise à jour de l'audit trail
        update_connection_audit(connection, sync_result, product.id)
        
        return Response({
            'success': True,
            'files_processed': sync_result['files_count'],
            'total_size_mb': sync_result['total_size_mb'],
            'processing_time': sync_result['processing_time'],
            'ectd_modules_found': sync_result['modules_found'],
            'message': f"✅ {sync_result['files_count']} fichiers eCTD synchronisés avec succès"
        })
        
    except CloudConnection.DoesNotExist:
        return Response({'error': 'Connexion cloud introuvable'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"Erreur sync eCTD réelle: {e}")
        return Response({
            'error': 'Erreur lors de la synchronisation',
            'details': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

def get_cloud_connector(connection: CloudConnection):
    """Factory pour obtenir le bon connecteur cloud"""
    
    # Déchiffrer le token
    access_token = decrypt_token_real(connection.encrypted_access_token, connection.user)
    
    connector_classes = {
        'google_drive': GoogleDriveConnector,
        'onedrive': OneDriveConnector,
        'sharepoint': SharePointConnector,
        'dropbox': DropboxConnector,
        'box': BoxConnector
    }
    
    if connection.provider not in connector_classes:
        raise ValueError(f"Connecteur non disponible pour {connection.provider}")
    
    return connector_classes[connection.provider](access_token, connection)

def perform_real_ectd_sync(product: Product, connector, connection: CloudConnection, folder_path: str, user) -> dict:
    """Process ZIP files and store REAL folder structure"""
    
    start_time = timezone.now()
    files_processed = 0
    total_size = 0
    modules_found = set()
    
    try:
        cloud_files = connector.list_files_recursive(folder_path)
        print(f"DEBUG: Raw cloud files: {cloud_files}")
        
        ectd_files = filter_real_ectd_files(cloud_files)
        print(f"DEBUG: Filtered ZIP files: {ectd_files}")
        
        for file_info in ectd_files:
            try:
                # Download ZIP file
                file_data = connector.download_file_secure(file_info['id']) 
                
                folder_structure = process_archive_file(file_data, file_info['name'])
                print(f"📁 REAL Folder structure: {folder_structure}")
                
                ectd_file = ProductECTDFile.objects.create(
                    product=product,
                    cloud_connection=connection,
                    file_name=file_info['name'],
                    file_path=file_info['id'], 
                    ectd_section=f'ZIP: {len(folder_structure)} folders',
                    uploaded_by=user
                )
                
     
                import json
                ectd_file.ectd_section = f'ZIP_STRUCTURE:{json.dumps(folder_structure)}'
                ectd_file.save()
                
                files_processed += 1
                total_size += file_info['size']
                modules_found.add('ZIP Archive')
                
                print(f"✅ ZIP file processed: {file_info['name']}")
                
            except Exception as e:
                print(f"❌ Error processing ZIP {file_info['name']}: {e}")
                continue
        
        processing_time = (timezone.now() - start_time).total_seconds()
        
        return {
            'files_count': files_processed,
            'total_size_mb': round(total_size / (1024 * 1024), 2),
            'processing_time': round(processing_time, 2),
            'modules_found': list(modules_found),
            'status': 'completed'
        }
        
    except Exception as e:
        print(f"❌ Full error: {e}")
        logger.error(f"Erreur synchronisation: {e}")
        raise    
    
import rarfile

def process_archive_file(file_data, archive_name):
    """Extract ZIP and RAR and return folder structure"""
    try:
        file_extension = os.path.splitext(archive_name)[1].lower()
        print(f"🔍 DEBUG: Processing {archive_name} ({len(file_data)} bytes)")
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_extension) as temp_file:
            temp_file.write(file_data)
            temp_file_path = temp_file.name
        
        folder_structure = {}
        
        # Handle ZIP files
        if file_extension == '.zip':
            if not zipfile.is_zipfile(temp_file_path):
                print(f"❌ DEBUG: {archive_name} is not a valid ZIP file")
                return {}
            
            print(f"✅ DEBUG: {archive_name} is a valid ZIP file")
            
            with zipfile.ZipFile(temp_file_path, 'r') as archive_ref:
                file_list = archive_ref.namelist()
                print(f"📁 DEBUG: Found {len(file_list)} total files in ZIP")
                print(f"📁 DEBUG: File list sample: {file_list[:10]}")
                
                pdf_count = 0
                for file_path in file_list:
                    print(f"🔍 DEBUG: Checking file: {file_path}")
                    if not file_path.endswith('/') and file_path.lower().endswith('.pdf'):
                        pdf_count += 1
                        print(f"✅ DEBUG: Found PDF: {file_path}")
                        folder_structure = _add_to_structure(folder_structure, file_path, archive_ref.getinfo(file_path).file_size)
                
                print(f"📄 DEBUG: Total PDFs found: {pdf_count}")
        
        # Handle RAR files - FIXED VERSION
        elif file_extension == '.rar':
            try:
                import rarfile
                setup_rar_tool()  # Auto-detect tool
                
                print(f"✅ DEBUG: {archive_name} is a RAR file, processing...")
                
                with rarfile.RarFile(temp_file_path, 'r') as rar_ref:  # rar_ref variable
                    file_list = rar_ref.namelist()  # FIXED: use rar_ref instead of archive_ref
                    print(f"📁 DEBUG: Found {len(file_list)} total files in RAR")
                    print(f"📁 DEBUG: File list sample: {file_list[:10]}")
                    
                    pdf_count = 0
                    for file_path in file_list:
                        print(f"🔍 DEBUG: Checking RAR file: {file_path}")
                        if not file_path.endswith('/') and file_path.lower().endswith('.pdf'):
                            pdf_count += 1
                            print(f"✅ DEBUG: Found PDF in RAR: {file_path}")
                            file_info = rar_ref.getinfo(file_path)  # FIXED: use rar_ref instead of archive_ref
                            folder_structure = _add_to_structure(folder_structure, file_path, file_info.file_size)
                    
                    print(f"📄 DEBUG: Total PDFs found in RAR: {pdf_count}")
                    
            except ImportError:
                print("❌ DEBUG: rarfile library not installed. Install with: pip install rarfile")
                return {}
            except rarfile.RarCannotExec:
                print("❌ DEBUG: RAR tool not found. Install unrar or 7-zip")
                return {}
            except Exception as e:
                print(f"❌ DEBUG: Error processing RAR file: {e}")
                import traceback
                traceback.print_exc()
                return {}
        else:
            print(f"❌ DEBUG: Unsupported file type: {archive_name}. Only ZIP and RAR files are supported.")
            return {}
        
        os.unlink(temp_file_path)
        print(f"✅ DEBUG: Final structure has {len(folder_structure)} folders")
        print(f"📁 DEBUG: Final structure: {folder_structure}")
        return folder_structure
        
    except Exception as e:
        print(f"❌ DEBUG: Error processing archive: {e}")
        import traceback
        traceback.print_exc()
        return {}
    

def _add_to_structure(folder_structure, file_path, file_size):
    """Helper function to add file to structure"""
    path_parts = file_path.split('/')
    folder_path = '/'.join(path_parts[:-1]) if len(path_parts) > 1 else 'Root'
    file_name = path_parts[-1]
    
    if folder_path not in folder_structure:
        folder_structure[folder_path] = []
    
    folder_structure[folder_path].append({
        'name': file_name,
        'path': file_path,
        'size': file_size
    })
    
    return folder_structure
    

@api_view(['GET'])
def oauth_callback(request):
    """Callback OAuth RÉEL"""
    code = request.GET.get('code')
    state = request.GET.get('state')
    error = request.GET.get('error')
    
    if error:
        return HttpResponse(f"<h2>❌ Erreur OAuth: {error}</h2><script>window.close();</script>")
    
    if not code or not state:
        return HttpResponse("<h2>❌ Paramètres manquants</h2><script>window.close();</script>")
    
    # Récupérer les données de session
    session_key = f'oauth_state_{state}'
    oauth_params = request.session.get(session_key)
    
    if not oauth_params:
        return HttpResponse("<h2>❌ Session expirée</h2><script>window.close();</script>")
    
    try:
        # Échanger le code contre des tokens RÉELS
        tokens = exchange_oauth_code_for_tokens(oauth_params['provider'], code)
        
        if tokens and 'access_token' in tokens:
            user = User.objects.get(id=oauth_params['user_id'])
            
            print(f"DEBUG: Refresh token from Google: {tokens.get('refresh_token', 'NOT_FOUND')}")
            
            connection = CloudConnection.objects.create(
                user=user,
                provider=oauth_params['provider'],
                connection_name=oauth_params['connection_name'],
                encrypted_access_token=encrypt_token_real(tokens['access_token'], user),
                encrypted_refresh_token=encrypt_token_real(tokens.get('refresh_token', ''), user) if tokens.get('refresh_token') else b'',
                data_residency_eu=oauth_params['rgpd_data']['eu_residency'],
                scc_agreement=oauth_params['rgpd_data']['scc_agreement'],
                dpa_signed=oauth_params['rgpd_data']['dpa_signed'],
                rgpd_compliance_validated=True,
                rgpd_validation_date=timezone.now()
            )
            
            print(f"DEBUG: Connection created with encrypted_refresh_token: {connection.encrypted_refresh_token}")
            
            # Nettoyage
            del request.session[session_key]
            
            return HttpResponse(f"""
                <h2>✅ Connexion {oauth_params['provider']} Réussie!</h2>
                <p>Votre cloud est maintenant connecté avec les VRAIES APIs.</p>
                <script>setTimeout(() => window.close(), 2000);</script>
            """)
        else:
            return HttpResponse("<h2>❌ Échec obtention tokens</h2><script>window.close();</script>")
            
    except Exception as e:
        logger.error(f"Erreur callback OAuth: {e}")
        return HttpResponse(f"<h2>❌ Erreur: {e}</h2><script>window.close();</script>")
    
def get_sub_processors_list(provider: str) -> list:
    """Liste des sous-traitants par provider"""
    sub_processors = {
        'google_drive': [
            {'name': 'Google Cloud Platform', 'activity': 'Hébergement', 'country': 'US/EU'},
            {'name': 'Akamai', 'activity': 'CDN', 'country': 'Global'}
        ],
        'onedrive': [
            {'name': 'Microsoft Azure', 'activity': 'Hébergement', 'country': 'EU'},
            {'name': 'Akamai', 'activity': 'CDN', 'country': 'Global'}
        ],
        # ... autres providers
    }
    return sub_processors.get(provider, [])

def get_technical_measures(provider: str) -> dict:
    """Mesures techniques par provider"""
    return {
        'encryption_at_rest': True,
        'encryption_in_transit': True,
        'access_controls': True,
        'audit_logging': True,
        'backup_encryption': True,
        'incident_response': True
    }

def get_organizational_measures() -> dict:
    """Mesures organisationnelles"""
    return {
        'staff_training': True,
        'access_management': True,
        'incident_procedures': True,
        'data_retention_policy': True,
        'regular_audits': True
    }

@api_view(['GET'])
def product_ectd_files(request, pk):
    """Lister les fichiers eCTD d'un produit - SIMPLIFIED"""
    
    try:
        product = get_object_or_404(Product, pk=pk)
        ectd_files = ProductECTDFile.objects.filter(product=product).order_by('ectd_section', 'file_name')
        
        data = {
            'files_by_module': {},
            'total_files': ectd_files.count(),
            'total_size_mb': 1.0  # Fake size since we don't have file_size field
        }
        
        # Grouper par module eCTD
        for file in ectd_files:
            module = 'Documents'  # Simple module name
            if module not in data['files_by_module']:
                data['files_by_module'][module] = []
            
            data['files_by_module'][module].append({
                'id': file.id,
                'name': file.file_name,
                'section': file.ectd_section,
                'size_mb': 1.0,  # Fake size
                'uploaded_at': file.uploaded_at.isoformat(),
                'sync_status': 'completed'  # Fake status
            })
        
        return Response(data)
        
    except Exception as e:
        logger.error(f"Erreur product_ectd_files: {e}")
        return Response({'error': str(e)}, status=500)
    
    
def update_connection_audit(connection, sync_result, product_id):
    """Mettre à jour l'audit trail de la connexion"""
    if not connection.audit_log:
        connection.audit_log = []
    
    connection.audit_log.append({
        'action': 'ectd_sync',
        'timestamp': timezone.now().isoformat(),
        'product_id': product_id,
        'files_synced': sync_result['files_count'],
        'total_size_mb': sync_result['total_size_mb']
    })
    connection.last_used = timezone.now()
    connection.save()

def filter_real_ectd_files(cloud_files):
    """Accept both ZIP and RAR files"""
    filtered_files = []
    for file_info in cloud_files:
        filename_lower = file_info['name'].lower()
        
        if filename_lower.endswith('.zip') or filename_lower.endswith('.rar'):
            filtered_files.append(file_info)
    
    return filtered_files

def analyze_ectd_file(file_info, file_data):
    return {
        'module': 'Documents',
        'section': 'Documents', 
        'document_type': 'PDF Document',
        'contains_personal_data': False
    }

def calculate_retention_date(ectd_metadata):
    """Calculer la date de rétention selon les règles pharmaceutiques"""
    from datetime import timedelta
    return timezone.now().date() + timedelta(days=2555)
@api_view(['GET'])
def get_zip_structure(request, pk, file_id):
    """Get ZIP file structure from stored eCTD file"""
    try:
        product = get_object_or_404(Product, pk=pk)
        ectd_file = get_object_or_404(ProductECTDFile, id=file_id, product=product)
        
        # Extract folder structure from ectd_section field
        if ectd_file.ectd_section.startswith('ZIP_STRUCTURE:'):
            structure_json = ectd_file.ectd_section.replace('ZIP_STRUCTURE:', '')
            folder_structure = json.loads(structure_json)
            
            # Count totals
            total_folders = len(folder_structure)
            total_files = sum(len(files) for files in folder_structure.values())
            
            return Response({
                'zip_name': ectd_file.file_name,
                'folder_structure': folder_structure,
                'total_folders': total_folders,
                'total_files': total_files
            })
        else:
            return Response({
                'error': 'Structure de fichier non disponible'
            }, status=status.HTTP_404_NOT_FOUND)
            
    except ProductECTDFile.DoesNotExist:
        return Response({
            'error': 'Fichier eCTD introuvable'
        }, status=status.HTTP_404_NOT_FOUND)
    except json.JSONDecodeError:
        return Response({
            'error': 'Structure de fichier corrompue'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    except Exception as e:
        logger.error(f"Erreur get_zip_structure: {e}")
        return Response({
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
def view_pdf_file(request, pk, file_id):
    """View PDF file from ZIP/RAR archive"""
    try:
        file_path = request.GET.get('file_path')
        if not file_path:
            return HttpResponse("File path parameter missing", status=400)
            
        product = get_object_or_404(Product, pk=pk)
        ectd_file = get_object_or_404(ProductECTDFile, id=file_id, product=product)
        
        # Get the cloud connection
        connection = ectd_file.cloud_connection
        connector = get_cloud_connector(connection)
        
        # Download the archive file
        archive_data = connector.download_file_secure(ectd_file.file_path)
        
        # Determine file type
        file_extension = os.path.splitext(ectd_file.file_name)[1].lower()
        
        # Create temporary file with correct extension
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_extension) as temp_archive:
            temp_archive.write(archive_data)
            temp_archive_path = temp_archive.name
        
        try:
            pdf_data = None
            
            # Handle ZIP files
            if file_extension == '.zip':
                if not zipfile.is_zipfile(temp_archive_path):
                    return HttpResponse("<h2>Erreur</h2><p>Le fichier n'est pas un ZIP valide</p>", status=400)
                
                with zipfile.ZipFile(temp_archive_path, 'r') as zip_ref:
                    if file_path not in zip_ref.namelist():
                        available_files = [f for f in zip_ref.namelist() if f.endswith('.pdf')]
                        return HttpResponse(f"<h2>Fichier non trouvé</h2><p>Le fichier '{file_path}' n'existe pas dans l'archive ZIP.</p><p>Fichiers PDF disponibles: {available_files[:5]}</p>", status=404)
                    
                    pdf_data = zip_ref.read(file_path)
            
           # Handle RAR files
            elif file_extension == '.rar':
                try:
                    import rarfile
                    setup_rar_tool()  # Auto-detect tool
                    
                    # Verify RAR file integrity first
                    try:
                        with rarfile.RarFile(temp_archive_path, 'r') as rar_test:
                            rar_test.testrar()  # Test archive integrity
                    except rarfile.BadRarFile:
                        return HttpResponse("<h2>Erreur RAR</h2><p>Le fichier RAR est corrompu ou incomplet.</p>", status=400)
                    except Exception as e:
                        return HttpResponse(f"<h2>Erreur RAR</h2><p>Impossible de vérifier l'intégrité du fichier: {e}</p>", status=400)
                    
                    with rarfile.RarFile(temp_archive_path, 'r') as rar_ref:
                        if file_path not in rar_ref.namelist():
                            available_files = [f for f in rar_ref.namelist() if f.endswith('.pdf')]
                            return HttpResponse(f"<h2>Fichier non trouvé</h2><p>Le fichier '{file_path}' n'existe pas dans l'archive RAR.</p><p>Fichiers PDF disponibles: {available_files[:5]}</p>", status=404)
                        
                        try:
                            pdf_data = rar_ref.read(file_path)
                        except Exception as e:
                            return HttpResponse(f"<h2>Erreur lecture RAR</h2><p>Impossible de lire le fichier depuis l'archive: {e}</p><p>Le fichier pourrait être corrompu.</p>", status=500)
                            
                except ImportError:
                    return HttpResponse("<h2>Erreur</h2><p>Support RAR non disponible. Contactez l'administrateur.</p>", status=500)
                except rarfile.RarCannotExec:
                    return HttpResponse("<h2>Erreur</h2><p>Outil RAR non trouvé. Contactez l'administrateur.</p>", status=500)
                except Exception as e:
                    return HttpResponse(f"<h2>Erreur RAR</h2><p>Erreur lors de la lecture du fichier RAR: {e}</p>", status=500)
            
            else:
                return HttpResponse(f"<h2>Erreur</h2><p>Type de fichier non supporté: {file_extension}</p>", status=400)
            
            if pdf_data:
                response = HttpResponse(pdf_data, content_type='application/pdf')
                response['Content-Disposition'] = f'inline; filename="{os.path.basename(file_path)}"'
                return response
            else:
                return HttpResponse("<h2>Erreur</h2><p>Impossible de lire le fichier PDF</p>", status=500)
                
        finally:
            os.unlink(temp_archive_path)
            
    except Exception as e:
        logger.error(f"Error viewing PDF: {e}")
        return HttpResponse(f"<h2>Erreur</h2><p>Erreur: {str(e)}</p>", status=500)
  

@api_view(['DELETE'])
def delete_ectd_files(request, pk):
    """Delete all eCTD files for a product"""
    try:
        product = get_object_or_404(Product, pk=pk)
        deleted_count = ProductECTDFile.objects.filter(product=product).count()
        ProductECTDFile.objects.filter(product=product).delete()
        
        return Response({
            'success': True,
            'deleted_count': deleted_count,
            'message': f'{deleted_count} fichiers supprimés'
        })

        
    except Exception as e:
        logger.error(f"Error deleting eCTD files: {e}")
        return Response({
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
class GoogleDriveConnector:
    def __init__(self, access_token, connection):
        self.access_token = access_token
        self.connection = connection
    
    def get_credentials(self):
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        
        refresh_token = None
        if hasattr(self.connection, 'encrypted_refresh_token') and self.connection.encrypted_refresh_token:
            try:
                decrypted = decrypt_token_real(self.connection.encrypted_refresh_token, self.connection.user)
                refresh_token = decrypted if decrypted else None
            except Exception as e:
                print(f"Error decrypting refresh token: {e}")
        
        credentials = Credentials(
            token=self.access_token,
            refresh_token=refresh_token,
            token_uri='https://oauth2.googleapis.com/token',
            client_id=settings.GOOGLE_OAUTH_CLIENT_ID,
            client_secret=settings.GOOGLE_OAUTH_CLIENT_SECRET,
            scopes=['https://www.googleapis.com/auth/drive.readonly']
        )
        
        # Refresh token if expired
        if credentials.expired and credentials.refresh_token:
            print("🔄 Refreshing expired credentials...")
            try:
                credentials.refresh(Request())
                # Update the stored access token
                self.access_token = credentials.token
                self.connection.encrypted_access_token = encrypt_token_real(credentials.token, self.connection.user)
                self.connection.save()
                print("✅ Credentials refreshed successfully")
            except Exception as e:
                print(f"❌ Failed to refresh credentials: {e}")
        
        return credentials
    
    def decrypt_token_real(encrypted_token: bytes, user) -> str:
        """Déchiffrement réel des tokens"""
        
        if not encrypted_token:
            print("DEBUG: No encrypted token provided")
            return ''
        
        print(f"DEBUG: Decrypting token of length: {len(encrypted_token)}")
        
        key_material = f"{settings.SECRET_KEY}:{user.pk}:{user.username}:{user.date_joined.isoformat()}"
        key = base64.urlsafe_b64encode(hashlib.sha256(key_material.encode()).digest())
        
        try:
            fernet = Fernet(key)
            decrypted = fernet.decrypt(encrypted_token).decode()
            print(f"DEBUG: Successfully decrypted token of length: {len(decrypted)}")
            return decrypted
        except Exception as e:
            print(f"DEBUG: Decryption failed: {e}")
            return ''
        
    
    def list_files_recursive(self, folder_path):
        """Get REAL ZIP and RAR files from Google Drive"""
        try:
            from googleapiclient.discovery import build
            
            credentials = self.get_credentials()
            service = build('drive', 'v3', credentials=credentials)
            
            # Search for both ZIP and RAR files
            files = []
            
            # Search for ZIP files
            zip_query = "name contains '.zip' and 'me' in owners"
            zip_results = service.files().list(
                q=zip_query,
                fields="files(id, name, size)",
                pageSize=50
            ).execute()
            
            # Search for RAR files
            rar_query = "name contains '.rar' and 'me' in owners"
            rar_results = service.files().list(
                q=rar_query,
                fields="files(id, name, size)",
                pageSize=50
            ).execute()
            
            # Combine results
            all_files = zip_results.get('files', []) + rar_results.get('files', [])
            
            print(f"📁 Found {len(all_files)} archive files (ZIP/RAR) in My Drive")
            
            for file in all_files:
                if file['name'].lower().endswith(('.zip', '.rar')):
                    file_size = int(file.get('size', 0)) if file.get('size') else 0
                    files.append({
                        'name': file['name'],
                        'path': f"/{file['name']}",
                        'size': file_size,
                        'id': file['id']
                    })
                    print(f"  📄 Found: {file['name']} ({file_size} bytes)")
            
            return files
            
        except Exception as e:
            print(f"❌ REAL Google Drive API Error: {e}")
            raise Exception(f"Failed to access Google Drive: {e}")
        

    def download_file_secure(self, file_path):
        """Download REAL file from Google Drive with retry"""
        import time
        max_retries = 3
        
        for attempt in range(max_retries):
            try:
                from googleapiclient.discovery import build
                
                credentials = self.get_credentials()
                service = build('drive', 'v3', credentials=credentials)
                
                file_id = file_path
                print(f"🔽 Downloading file ID: {file_id} (attempt {attempt + 1}/{max_retries})")
                
                # Get file info first to check size
                file_info = service.files().get(fileId=file_id, fields="name,size").execute()
                expected_size = int(file_info.get('size', 0))
                print(f"📊 Expected file size: {expected_size} bytes")
                
                # Download the file
                request = service.files().get_media(fileId=file_id)
                file_content = request.execute()
                
                actual_size = len(file_content)
                print(f"✅ Downloaded {actual_size} bytes")
                
                # Verify download completeness
                if actual_size != expected_size:
                    print(f"⚠️ Size mismatch: expected {expected_size}, got {actual_size}")
                    if attempt < max_retries - 1:
                        print(f"🔄 Retrying download...")
                        time.sleep(2)
                        continue
                    else:
                        raise Exception(f"Incomplete download: expected {expected_size} bytes, got {actual_size}")
                
                return file_content
                
            except Exception as e:
                print(f"❌ Error downloading from Google Drive (attempt {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    print(f"🔄 Retrying in 2 seconds...")
                    time.sleep(2)
                else:
                    raise Exception(f"Failed to download file after {max_retries} attempts: {e}")
        
class OneDriveConnector:
    def __init__(self, access_token, connection):
        self.access_token = access_token
        self.connection = connection
    
    def get_credentials(self):
        """OneDrive uses simple bearer token authentication"""
        return {
            'access_token': self.access_token,
            'token_type': 'Bearer'
        }
    
    def list_files_recursive(self, folder_path):
        """Get REAL ZIP and RAR files from OneDrive"""
        try:
            import requests
            
            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'Content-Type': 'application/json'
            }
            
            # Search for ZIP and RAR files in OneDrive
            files = []
            
            # OneDrive Graph API search endpoint
            search_url = 'https://graph.microsoft.com/v1.0/me/drive/root/search(q=\'.zip OR .rar\')'
            
            response = requests.get(search_url, headers=headers, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            found_files = data.get('value', [])
            
            print(f"📁 Found {len(found_files)} archive files in OneDrive")
            
            for file in found_files:
                if file['name'].lower().endswith(('.zip', '.rar')):
                    file_size = file.get('size', 0)
                    files.append({
                        'name': file['name'],
                        'path': f"/{file['name']}",
                        'size': file_size,
                        'id': file['id']
                    })
                    print(f"  📄 Found: {file['name']} ({file_size} bytes)")
            
            return files
            
        except Exception as e:
            print(f"❌ REAL OneDrive API Error: {e}")
            raise Exception(f"Failed to access OneDrive: {e}")
    
    def download_file_secure(self, file_id):
        """Download REAL file from OneDrive"""
        import time
        max_retries = 3
        
        for attempt in range(max_retries):
            try:
                import requests
                
                headers = {
                    'Authorization': f'Bearer {self.access_token}'
                }
                
                print(f"🔽 Downloading OneDrive file ID: {file_id} (attempt {attempt + 1}/{max_retries})")
                
                # Get file metadata first
                metadata_url = f'https://graph.microsoft.com/v1.0/me/drive/items/{file_id}'
                metadata_response = requests.get(metadata_url, headers=headers, timeout=30)
                metadata_response.raise_for_status()
                
                file_info = metadata_response.json()
                expected_size = int(file_info.get('size', 0))
                print(f"📊 Expected file size: {expected_size} bytes")
                
                # Download the file content
                download_url = f'https://graph.microsoft.com/v1.0/me/drive/items/{file_id}/content'
                download_response = requests.get(download_url, headers=headers, timeout=120)
                download_response.raise_for_status()
                
                file_content = download_response.content
                actual_size = len(file_content)
                print(f"✅ Downloaded {actual_size} bytes from OneDrive")
                
                # Verify download completeness
                if actual_size != expected_size:
                    print(f"⚠️ Size mismatch: expected {expected_size}, got {actual_size}")
                    if attempt < max_retries - 1:
                        print(f"🔄 Retrying download...")
                        time.sleep(2)
                        continue
                    else:
                        raise Exception(f"Incomplete download: expected {expected_size} bytes, got {actual_size}")
                
                return file_content
                
            except Exception as e:
                print(f"❌ Error downloading from OneDrive (attempt {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    print(f"🔄 Retrying in 2 seconds...")
                    time.sleep(2)
                else:
                    raise Exception(f"Failed to download file after {max_retries} attempts: {e}")

class SharePointConnector(GoogleDriveConnector):
    pass

class DropboxConnector(GoogleDriveConnector):
    pass

class BoxConnector(GoogleDriveConnector):
    pass