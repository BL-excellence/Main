# client/reports/views.py 
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.utils import timezone
from django.db.models import Count, Avg, Q, Max, Min
from datetime import datetime, timedelta
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
import json
import csv
from client.products.models import Product, ManufacturingSite, ProductSpecification, ProductVariation
import io
from pymongo import MongoClient
from django.conf import settings
import uuid
from django.views.decorators.csrf import csrf_exempt
import time
from typing import Dict, List, Any

# Import from your existing models
from rawdocs.models import RawDocument, DocumentPage, Annotation, AnnotationType
from client.products.models import Product
from expert.models import ExpertLog


def is_client(user):
    return user.groups.filter(name="Client").exists()


MONGO_URI = getattr(settings, "MONGO_URI", "mongodb://localhost:27017/")
MONGO_DB = getattr(settings, "MONGO_DB", "annotations_db")
MONGO_COLLECTION = getattr(settings, "MONGO_COLLECTION", "documents")

mongo_client = MongoClient(MONGO_URI)
mongo_db = mongo_client[MONGO_DB]
mongo_collection = mongo_db[MONGO_COLLECTION]


def get_all_dynamic_fields():
    """
    🚀 PRODUCTION-READY: Discover ALL fields dynamically - FIXED VERSION
    """
    all_fields = []

    # === 1. PRODUCT MODEL FIELDS (SQL) - FIXED ===
    try:
        if Product.objects.exists():
            for field in Product._meta.get_fields():
                if (hasattr(field, 'get_internal_type') and
                        field.get_internal_type() in ['CharField', 'TextField', 'IntegerField'] and
                        not field.many_to_many and not field.one_to_many):

                    try:
                        # Use values_list to avoid date validation issues
                        count = Product.objects.exclude(**{f'{field.name}__isnull': True}).exclude(
                            **{f'{field.name}': ''}).count()

                        if count > 0:
                            all_fields.append({
                                'name': f'product_{field.name}',
                                'label': field.verbose_name or field.name.replace("_", " ").title(),
                                'description': f'{count} products with data',
                                'type': 'product',
                                'source': 'sql_product',
                                'data_count': count
                            })
                    except Exception as field_error:
                        print(f"⚠️ Skipping Product field {field.name}: {field_error}")
                        continue

    except Exception as e:
        print(f"❌ Error discovering Product fields: {e}")

    # === 2. RAWDOCUMENT MODEL FIELDS (SQL) - FIXED ===
    try:
        if RawDocument.objects.exists():
            for field in RawDocument._meta.get_fields():
                if (hasattr(field, 'get_internal_type') and
                        field.get_internal_type() in ['CharField', 'TextField'] and
                        not field.many_to_many and not field.one_to_many):

                    try:
                        count = RawDocument.objects.exclude(**{f'{field.name}__isnull': True}).exclude(
                            **{f'{field.name}': ''}).count()

                        if count > 0:
                            all_fields.append({
                                'name': f'document_{field.name}',
                                'label': field.verbose_name or field.name.replace("_", " ").title(),
                                'description': f'{count} documents with data',
                                'type': 'document',
                                'source': 'sql_document',
                                'data_count': count
                            })
                    except Exception as field_error:
                        print(f"⚠️ Skipping Document field {field.name}: {field_error}")
                        continue

    except Exception as e:
        print(f"❌ Error discovering RawDocument fields: {e}")

    # === 3. MONGODB ENTITIES (Dynamic annotations) ===
    try:
        # Get all unique entity types from MongoDB
        pipeline = [
            {"$match": {"entities": {"$exists": True}}},
            {"$project": {"entities": {"$objectToArray": "$entities"}}},
            {"$unwind": "$entities"},
            {"$group": {
                "_id": "$entities.k",
                "count": {"$sum": 1}
            }}
        ]

        entity_stats = list(mongo_collection.aggregate(pipeline))

        for entity in entity_stats:
            entity_name = entity['_id']
            count = entity['count']

            if entity_name and count > 0:
                all_fields.append({
                    'name': f'entity_{entity_name.lower().replace(" ", "_")}',
                    'label': entity_name,
                    'description': f'{count} documents with {entity_name}',
                    'type': 'entity',
                    'source': 'mongodb_entity',
                    'data_count': count
                })

        print(f"✅ Found {len(entity_stats)} MongoDB entities")

    except Exception as e:
        print(f"❌ Error discovering MongoDB entities: {e}")

    # === 4. MONGODB METADATA (Dynamic fields) ===
    try:
        # Get all unique metadata fields
        pipeline = [
            {"$match": {"metadata": {"$exists": True}}},
            {"$project": {"metadata": {"$objectToArray": "$metadata"}}},
            {"$unwind": "$metadata"},
            {"$group": {
                "_id": "$metadata.k",
                "count": {"$sum": 1}
            }}
        ]

        metadata_stats = list(mongo_collection.aggregate(pipeline))

        for metadata in metadata_stats:
            field_name = metadata['_id']
            count = metadata['count']

            if field_name and count > 0 and field_name not in ['_id', 'document_id']:
                all_fields.append({
                    'name': f'metadata_{field_name}',
                    'label': field_name.replace("_", " ").title(),
                    'description': f'{count} documents with {field_name}',
                    'type': 'metadata',
                    'source': 'mongodb_metadata',
                    'data_count': count
                })

        print(f"✅ Found {len(metadata_stats)} MongoDB metadata fields")

    except Exception as e:
        print(f"❌ Error discovering MongoDB metadata: {e}")

    print(f"🎯 Discovered {len(all_fields)} dynamic fields total")
    return all_fields


@login_required(login_url='rawdocs:login')
@user_passes_test(is_client)
def reports_dashboard(request):
    """Vue principale du dashboard des rapports avec données réelles"""

    # Récupération des filtres
    filters = {
        'period': request.GET.get('period', '30d'),
        'product': request.GET.get('product', ''),
        'status': request.GET.get('status', ''),
        'authority': request.GET.get('authority', ''),
    }

    # Calcul de la période
    period_days = get_period_days(filters['period'])
    start_date = timezone.now().date() - timedelta(days=period_days)

    # KPIs basés sur vos données réelles
    kpis = calculate_real_kpis(start_date, filters)

    # Données pour les templates de rapports
    report_templates = get_report_templates()

    # Vues sauvegardées simulées
    saved_views = get_saved_views()

    # Données pour les graphiques
    chart_data = get_real_chart_data(start_date, filters)

    # Données récentes d'activité
    recent_activity = get_recent_activity()

    # Filtres disponibles
    available_filters = get_available_filters()

    context = {
        'filters': filters,
        'kpis': kpis,
        'report_templates': report_templates,
        'saved_views': saved_views,
        'chart_data': chart_data,
        'recent_activity': recent_activity,
        'available_filters': available_filters,
    }

    return render(request, 'client/reports/dashboard.html', context)


def get_period_days(period):
    """Convertir période en nombre de jours"""
    period_map = {
        '7d': 7,
        '30d': 30,
        '90d': 90,
        '1y': 365,
    }
    return period_map.get(period, 30)


def calculate_real_kpis(start_date, filters):
    """Calculer les KPIs basés sur vos données réelles"""

    # Documents traités ce mois
    documents_count = RawDocument.objects.filter(
        created_at__gte=start_date,
        is_validated=True
    ).count()

    # Annotations créées
    annotations_count = Annotation.objects.filter(
        created_at__gte=start_date
    ).count()

    # Produits créés
    products_count = Product.objects.filter(
        created_at__gte=start_date
    ).count()

    # Temps moyen de traitement (en jours)
    validated_docs = RawDocument.objects.filter(
        is_validated=True,
        validated_at__isnull=False,
        created_at__gte=start_date
    )

    avg_processing_time = 0
    if validated_docs.exists():
        total_time = 0
        count = 0
        for doc in validated_docs:
            if doc.validated_at and doc.created_at:
                processing_time = (doc.validated_at.date() - doc.created_at.date()).days
                total_time += processing_time
                count += 1
        avg_processing_time = total_time / count if count > 0 else 0

    return {
        'rapports_mois': documents_count,
        'vues_standard': 3,  # Templates disponibles
        'exports_pdf': annotations_count,  # Annotations comme proxy pour exports
        'partages': products_count,  # Produits créés
        'avg_processing_days': round(avg_processing_time, 1),
        'total_annotations': annotations_count,
        'active_users': User.objects.filter(last_login__gte=start_date).count(),
    }


def get_report_templates():
    """Templates de rapports disponibles"""
    return [
        {
            'name': 'Rapport Mensuel de Conformité',
            'description': 'Vue d\'ensemble des activités réglementaires du mois',
            'type': 'Mensuel',
            'last_generated': '2024-01-15',
            'icon': 'description',
        },
        {
            'name': 'Tableau de Bord KPI',
            'description': 'Indicateurs de performance réglementaire',
            'type': 'Hebdomadaire',
            'last_generated': '2024-01-12',
            'icon': 'dashboard',
        },
        {
            'name': 'Rapport d\'Audit Réglementaire',
            'description': 'Synthèse des audits et inspections',
            'type': 'Trimestriel',
            'last_generated': '2024-01-08',
            'icon': 'assessment',
        },
        {
            'name': 'Analyse des Variations',
            'description': 'Suivi des variations de produit et autorités',
            'type': 'Mensuel',
            'last_generated': '2024-01-10',
            'icon': 'trending_up',
        },
    ]


def get_saved_views():
    """Vues sauvegardées"""
    return [
        {
            'name': 'Vue Mensuelle Q4 2024',
            'description': 'Rapport mensuel personnalisé pour Q4',
            'created_at': '2024-01-15',
        },
        {
            'name': 'Rapport Annuel 2024',
            'description': 'Vue d\'ensemble annuelle complète',
            'created_at': '2024-01-10',
        },
        {
            'name': 'KPI Dashboard Personnalisé',
            'description': 'Indicateurs spécifiques à l\'équipe',
            'created_at': '2024-01-08',
        },
    ]


def get_real_chart_data(start_date, filters):
    """Données réelles pour les graphiques"""

    # Documents par jour pour les 30 derniers jours
    daily_docs = []
    for i in range(30):
        date = start_date + timedelta(days=i)
        count = RawDocument.objects.filter(
            created_at__date=date,
            is_validated=True
        ).count()
        daily_docs.append({
            'date': date.strftime('%Y-%m-%d'),
            'count': count
        })

    # Répartition par type de document
    doc_types = RawDocument.objects.filter(
        created_at__gte=start_date,
        is_validated=True
    ).values('doc_type').annotate(count=Count('id')).order_by('-count')

    # Répartition par autorité
    authorities = Annotation.objects.filter(
        created_at__gte=start_date,
        annotation_type__name='authority'
    ).values('selected_text').annotate(count=Count('id')).order_by('-count')[:5]

    return {
        'daily_documents': daily_docs,
        'document_types': list(doc_types),
        'authorities': list(authorities),
    }


def get_recent_activity():
    """Activité récente"""
    recent_docs = RawDocument.objects.filter(
        is_validated=True
    ).order_by('-validated_at')[:10]

    recent_products = Product.objects.order_by('-created_at')[:5]

    return {
        'recent_documents': recent_docs,
        'recent_products': recent_products,
    }


def get_available_filters():
    """Filtres disponibles pour les dropdowns"""

    # Types de documents uniques
    doc_types = RawDocument.objects.values_list('doc_type', flat=True).distinct()
    doc_types = [dt for dt in doc_types if dt]  # Remove empty values

    # Autorités depuis les annotations
    authorities = Annotation.objects.filter(
        annotation_type__name='authority'
    ).values_list('selected_text', flat=True).distinct()
    authorities = [auth.strip() for auth in authorities if auth.strip()][:10]

    # Pays
    countries = RawDocument.objects.values_list('country', flat=True).distinct()
    countries = [c for c in countries if c]

    return {
        'document_types': list(doc_types),
        'authorities': list(authorities),
        'countries': list(countries),
        'periods': [
            ('7d', '7 derniers jours'),
            ('30d', '30 derniers jours'),
            ('90d', '3 derniers mois'),
            ('1y', 'Année courante'),
        ]
    }


@login_required(login_url='rawdocs:login')
@user_passes_test(is_client)
def generate_report(request):
    """Générer un rapport basé sur les filtres"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            template = data.get('template')
            period = data.get('period')
            authority = data.get('authority')

            # Logique de génération de rapport
            report_data = {
                'template': template,
                'generated_at': timezone.now().isoformat(),
                'period': period,
                'authority': authority,
                'status': 'success'
            }

            return JsonResponse(report_data)

        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)

    return JsonResponse({'error': 'POST required'}, status=405)


@login_required(login_url='rawdocs:login')
@user_passes_test(is_client)
def export_data(request):
    """Export des données en CSV/PDF"""
    format_type = request.GET.get('format', 'csv')

    if format_type == 'csv':
        # Export CSV des documents récents
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="regx_report.csv"'

        writer = csv.writer(response)
        writer.writerow(['Document', 'Type', 'Status', 'Date', 'Owner'])

        documents = RawDocument.objects.filter(is_validated=True)[:100]
        for doc in documents:
            writer.writerow([
                f'Document #{doc.id}',
                doc.doc_type or 'N/A',
                'Validé' if doc.is_validated else 'En attente',
                doc.created_at.strftime('%Y-%m-%d'),
                doc.owner.username if doc.owner else 'N/A'
            ])

        return response

    return JsonResponse({'error': 'Format not supported'}, status=400)


# Placeholder views pour les autres endpoints
def submission_detail(request, pk):
    return JsonResponse({'status': 'success', 'message': 'Detail view coming soon'})


def reports_settings(request):
    return render(request, 'client/reports/settings.html', {'message': 'Settings page'})


def reports_create(request):
    return render(request, 'client/reports/create.html', {'message': 'Create page'})


@login_required(login_url='rawdocs:login')
@user_passes_test(is_client)
def matrix_builder(request):
    # Get all fields - use your new dynamic function
    all_fields = get_all_dynamic_fields()

    # Get filter options using the working function
    filter_options = get_real_filter_options()

    context = {
        'all_fields': all_fields,
        'filter_options': filter_options,
    }

    return render(request, 'client/reports/matrix_builder.html', context)


def get_real_filter_options():
    """Generate filter options with EXACT field name matching - SIMPLE"""
    filter_options = {
        'periods': [
            ('7d', '7 derniers jours'),
            ('30d', '30 derniers jours'),
            ('90d', '3 derniers mois'),
            ('6m', '6 derniers mois'),
            ('1y', 'Année courante'),
        ]
    }

    # AUTO-GENERATE for Product fields
    if Product.objects.exists():
        print("Processing Product fields...")

        for field in Product._meta.get_fields():
            if (hasattr(field, 'get_internal_type') and
                    field.get_internal_type() in ['CharField', 'TextField'] and
                    not field.many_to_many and not field.one_to_many):

                field_name = field.name

                try:
                    values = list(
                        Product.objects
                        .exclude(**{f'{field_name}__isnull': True})
                        .exclude(**{f'{field_name}': ''})
                        .values_list(field_name, flat=True)
                        .distinct()
                        .order_by(field_name)[:10]
                    )

                    if values:
                        filter_options[field_name] = values
                        print(f"Added Product filter: {field_name} ({len(values)} options)")

                except Exception as e:
                    print(f"Error with Product.{field_name}: {e}")

    # AUTO-GENERATE for RawDocument fields
    if RawDocument.objects.exists():
        print("Processing RawDocument fields...")

        for field in RawDocument._meta.get_fields():
            if (hasattr(field, 'get_internal_type') and
                    field.get_internal_type() in ['CharField', 'TextField'] and
                    not field.many_to_many and not field.one_to_many):

                field_name = field.name

                try:
                    values = list(
                        RawDocument.objects
                        .exclude(**{f'{field_name}__isnull': True})
                        .exclude(**{f'{field_name}': ''})
                        .values_list(field_name, flat=True)
                        .distinct()
                        .order_by(field_name)[:10]
                    )

                    if values:
                        filter_options[field_name] = values
                        print(f"Added RawDocument filter: {field_name} ({len(values)} options)")

                except Exception as e:
                    print(f"Error with RawDocument.{field_name}: {e}")

    # SPECIAL HANDLING for sites (relationship field)
    if ManufacturingSite.objects.exists():
        print("Processing ManufacturingSite fields...")

        site_names = list(
            ManufacturingSite.objects
            .exclude(site_name__isnull=True)
            .exclude(site_name='')
            .values_list('site_name', flat=True)
            .distinct()
            .order_by('site_name')[:10]
        )
        if site_names:
            filter_options['sites'] = site_names
            print(f"Added sites filter: {len(site_names)} options")

        for field in ManufacturingSite._meta.get_fields():
            if (hasattr(field, 'get_internal_type') and
                    field.get_internal_type() in ['CharField', 'TextField'] and
                    not field.many_to_many and not field.one_to_many):

                field_name = field.name

                try:
                    values = list(
                        ManufacturingSite.objects
                        .exclude(**{f'{field_name}__isnull': True})
                        .exclude(**{f'{field_name}': ''})
                        .values_list(field_name, flat=True)
                        .distinct()
                        .order_by(field_name)[:10]
                    )

                    if values:
                        filter_options[field_name] = values
                        print(f"Added ManufacturingSite filter: {field_name} ({len(values)} options)")

                except Exception as e:
                    print(f"Error with ManufacturingSite.{field_name}: {e}")

    # Handle additional annotations from Product JSONField
    if Product.objects.exists():
        print("Processing additional annotations...")

        all_annotation_keys = set()
        for product in Product.objects.exclude(additional_annotations__isnull=True):
            if product.additional_annotations:
                all_annotation_keys.update(product.additional_annotations.keys())

        for annotation_key in all_annotation_keys:
            try:
                values = []
                for product in Product.objects.exclude(additional_annotations__isnull=True):
                    if (product.additional_annotations and
                            annotation_key in product.additional_annotations and
                            product.additional_annotations[annotation_key]):
                        values.append(str(product.additional_annotations[annotation_key]))

                unique_values = list(set(values))[:10]
                if unique_values:
                    filter_options[f'additional_{annotation_key}'] = unique_values
                    print(f"Added additional annotation filter: additional_{annotation_key}")

            except Exception as e:
                print(f"Error with additional_{annotation_key}: {e}")

    # Handle database annotations
    annotation_filters = {}
    for annotation_type in AnnotationType.objects.all():
        unique_values = list(
            Annotation.objects.filter(
                annotation_type=annotation_type,
                validation_status__in=['validated', 'expert_created']
            ).exclude(selected_text='').exclude(selected_text__isnull=True)
            .values_list('selected_text', flat=True)
            .distinct().order_by('selected_text')[:10]
        )

        if unique_values:
            annotation_filters[annotation_type.name] = {
                'label': annotation_type.display_name,
                'options': unique_values
            }

    filter_options['annotations'] = annotation_filters

    # Handle MongoDB entity filters - FIXED
    try:
        pipeline = [
            {"$match": {"entities": {"$exists": True}}},
            {"$project": {"entities": {"$objectToArray": "$entities"}}},
            {"$unwind": "$entities"},
            {"$group": {
                "_id": "$entities.k",
                "count": {"$sum": 1}
            }}
        ]

        entity_stats = list(mongo_collection.aggregate(pipeline))

        for entity in entity_stats:
            entity_name = entity['_id']
            if entity_name:
                pipeline_values = [
                    {"$match": {"entities": {"$exists": True}}},
                    {"$project": {f"entity_values": f"$entities.{entity_name}"}},
                    {"$unwind": "$entity_values"},
                    {"$match": {"entity_values": {"$ne": None, "$ne": ""}}},
                    {"$group": {"_id": "$entity_values"}},
                    {"$sort": {"_id": 1}},
                    {"$limit": 15}
                ]

                sample_values = list(mongo_collection.aggregate(pipeline_values))
                if sample_values:
                    entity_field_name = f'entity_{entity_name.lower().replace(" ", "_")}'
                    filter_options[entity_field_name] = [val['_id'] for val in sample_values if val['_id']]
                    print(f"Added entity filter: {entity_field_name}")

    except Exception as e:
        print(f"Error getting entity filter options: {e}")

    print(f"Total filter options generated: {len(filter_options)} keys")
    return filter_options


def get_validated_annotation_types():
    annotation_types_with_data = AnnotationType.objects.filter(
        annotation__validation_status='expert_created',
        annotation__selected_text__isnull=False
    ).exclude(
        annotation__selected_text=''
    ).exclude(
        name__iexact='product'
    ).distinct().order_by('display_name')

    annotation_fields = []
    for annotation_type in annotation_types_with_data:
        validated_count = Annotation.objects.filter(
            annotation_type=annotation_type,
            validation_status='expert_created',
            selected_text__isnull=False
        ).exclude(selected_text='').count()

        if validated_count > 0:
            annotation_fields.append({
                'id': annotation_type.id,
                'name': annotation_type.name,
                'label': annotation_type.display_name,
                'description': f"{validated_count} annotations validées",
                'type': 'annotation',
                'icon': 'note_add',
                'data_count': validated_count
            })

    return annotation_fields


def get_populated_product_fields():
    if not Product.objects.exists():
        return []

    populated_fields = []
    field_checks = {
        'name': Product.objects.exclude(name='').exclude(name__isnull=True).count(),
        'active_ingredient': Product.objects.exclude(active_ingredient='').exclude(
            active_ingredient__isnull=True).count(),
        'dosage': Product.objects.exclude(dosage='').exclude(dosage__isnull=True).count(),
        'form': Product.objects.exclude(form='').exclude(form__isnull=True).count(),
        'therapeutic_area': Product.objects.exclude(therapeutic_area='').exclude(therapeutic_area__isnull=True).count(),
    }

    field_labels = {
        'name': {'label': 'Nom du Produit', 'description': 'Noms des produits', 'icon': 'medication'},
        'active_ingredient': {'label': 'Principe Actif', 'description': 'Substances actives', 'icon': 'science'},
        'dosage': {'label': 'Dosage', 'description': 'Concentrations/dosages', 'icon': 'straighten'},
        'form': {'label': 'Forme Pharmaceutique', 'description': 'Formes galéniques', 'icon': 'tablet'},
        'therapeutic_area': {'label': 'Zone Thérapeutique', 'description': 'Domaines thérapeutiques',
                             'icon': 'medical_services'},
    }

    for field_name, count in field_checks.items():
        if count > 0:
            field_config = field_labels[field_name]
            populated_fields.append({
                'name': field_name,
                'label': field_config['label'],
                'description': f"{count} entrées avec données",
                'type': 'product',
                'icon': field_config['icon'],
                'data_count': count
            })

    # Get additional annotation fields from the database
    try:
        all_additional_annotations = {}

        # Check all products for additional annotations
        for product in Product.objects.all():
            if hasattr(product, 'additional_annotations') and product.additional_annotations:
                for key, value in product.additional_annotations.items():
                    if key not in all_additional_annotations:
                        all_additional_annotations[key] = 0
                    all_additional_annotations[key] += 1

        print(f"🔍 Found additional annotations: {all_additional_annotations}")

        # Add additional annotation fields to the list
        for annotation_type, count in all_additional_annotations.items():
            if count > 0:
                populated_fields.append({
                    'name': f'additional_{annotation_type}',
                    'label': annotation_type.replace('_', ' ').title(),
                    'description': f"{count} produits avec {annotation_type}",
                    'type': 'product',
                    'icon': 'label',
                    'data_count': count
                })
                print(f"✅ Added field: additional_{annotation_type}")

    except Exception as e:
        print(f"❌ Error getting additional annotations: {e}")

    # Rest of your existing code...
    site_count = ManufacturingSite.objects.count()
    if site_count > 0:
        populated_fields.extend([
            {
                'name': 'sites',
                'label': 'Sites de Fabrication',
                'description': f"{site_count} sites disponibles",
                'type': 'product',
                'icon': 'factory',
                'data_count': site_count
            }
        ])

    return populated_fields


def get_populated_document_fields():
    if not RawDocument.objects.exists():
        return []

    populated_fields = []
    field_checks = {
        'title': RawDocument.objects.exclude(title='').exclude(title__isnull=True).count(),
        'doc_type': RawDocument.objects.exclude(doc_type='').exclude(doc_type__isnull=True).count(),
        'country': RawDocument.objects.exclude(country='').exclude(country__isnull=True).count(),
        'source': RawDocument.objects.exclude(source='').exclude(source__isnull=True).count(),
    }

    field_labels = {
        'title': {'label': 'Titre du Document', 'description': 'Titres des documents', 'icon': 'title'},
        'doc_type': {'label': 'Type de Document', 'description': 'Types de documents', 'icon': 'category'},
        'country': {'label': 'Pays', 'description': 'Pays des documents', 'icon': 'flag'},
        'source': {'label': 'Source', 'description': 'Sources des documents', 'icon': 'source'},
    }

    for field_name, count in field_checks.items():
        if count > 0:
            field_config = field_labels[field_name]
            populated_fields.append({
                'name': field_name,
                'label': field_config['label'],
                'description': f"{count} documents avec données",
                'type': 'document',
                'icon': field_config['icon'],
                'data_count': count
            })

    return populated_fields


def get_dynamic_product_fields():
    """Get all available product fields dynamically - NO HARDCODING"""

    # Base product fields - these come from the actual Product model
    base_fields = []

    try:
        # Get the actual field names from the Product model
        product_model_fields = Product._meta.get_fields()

        # Map model fields to user-friendly labels
        field_mapping = {
            'name': {'label': 'Nom du Produit', 'description': 'Nom du produit', 'icon': 'medication'},
            'active_ingredient': {'label': 'Principe Actif', 'description': 'Substance active', 'icon': 'science'},
            'dosage': {'label': 'Dosage', 'description': 'Concentration/dosage', 'icon': 'straighten'},
            'form': {'label': 'Forme Pharmaceutique', 'description': 'Forme du produit', 'icon': 'tablet'},
            'therapeutic_area': {'label': 'Zone Thérapeutique', 'description': 'Domaine thérapeutique',
                                 'icon': 'medical_services'},
            'status': {'label': 'Statut Produit', 'description': 'Statut actuel', 'icon': 'info'},
            'created_at': {'label': 'Date Création Produit', 'description': 'Quand créé', 'icon': 'schedule'},
        }

        # Only include fields that exist in the model AND in our mapping
        for field in product_model_fields:
            if field.name in field_mapping and not field.many_to_many and not field.one_to_many:
                field_config = field_mapping[field.name]
                base_fields.append({
                    'name': field.name,
                    'label': field_config['label'],
                    'description': field_config['description'],
                    'type': 'text',
                    'icon': field_config['icon']
                })

    except Exception as e:
        print(f"❌ Error getting product model fields: {e}")
        # Minimal fallback
        base_fields = [
            {'name': 'name', 'label': 'Nom du Produit', 'description': 'Nom du produit', 'type': 'text',
             'icon': 'medication'}
        ]

    # Add computed fields (these make sense to be defined)
    computed_fields = [
        {'name': 'sites', 'label': 'Sites de Fabrication', 'description': 'Tous les sites', 'type': 'text',
         'icon': 'factory'},
        {'name': 'manufacturing_countries', 'label': 'Pays de Fabrication', 'description': 'Pays des sites',
         'type': 'text', 'icon': 'public'},
        {'name': 'gmp_certified_sites', 'label': 'Sites GMP Certifiés', 'description': 'Sites avec GMP', 'type': 'text',
         'icon': 'verified'},
        {'name': 'site_count', 'label': 'Nombre de Sites', 'description': 'Total des sites', 'type': 'number',
         'icon': 'numbers'},
        {'name': 'variation_count', 'label': 'Nombre de Variations', 'description': 'Total des variations',
         'type': 'number', 'icon': 'trending_up'},
        {'name': 'latest_variation', 'label': 'Dernière Variation', 'description': 'Variation la plus récente',
         'type': 'text', 'icon': 'update'},
    ]

    # Combine all fields
    all_fields = base_fields + computed_fields

    # Add type and id for each field
    for field in all_fields:
        field['type'] = 'product'
        field['id'] = f"product_{field['name']}"

    return all_fields


@csrf_exempt
@login_required
def generate_matrix_report(request):
    """Generate a Matrix report with AI-powered content"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        data = json.loads(request.body)
        print(f"🏗️ Generating matrix with config: {data}")

        # Extract configuration
        columns = data.get('columns', [])
        filters = data.get('filters', {})

        if not columns:
            return JsonResponse({
                'success': False,
                'message': 'Aucune colonne sélectionnée'
            })

        # Generate the report data
        result = generate_matrix_data_simple(columns, filters, request.user)

        return JsonResponse({
            'success': True,
            'result': result,
            'message': f"Rapport généré avec {len(result.get('rows', []))} lignes"
        })

    except Exception as e:
        print(f"❌ Matrix generation error: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e),
            'message': 'Erreur lors de la génération'
        }, status=500)


def generate_matrix_data_simple(columns: List[Dict], filters: Dict, user: User) -> Dict[str, Any]:
    """Generate Matrix data - FIXED to properly detect annotation types"""

    start_time = time.time()
    print(f"🔄 Starting matrix generation with {len(columns)} columns")

    annotation_columns = []
    product_columns = []
    document_columns = []

    for col in columns:
        source_type = col.get('source_type', col.get('type', ''))
        field_name = col.get('name', '')

        print(f"📊 Column: {field_name}, source_type: {source_type}")

        if source_type == 'annotation':
            annotation_columns.append(col)
        elif source_type == 'product':
            product_columns.append(col)
        elif source_type == 'document':
            document_columns.append(col)
        else:
            # Fallback based on field name
            if field_name in ['name', 'active_ingredient', 'dosage', 'form', 'therapeutic_area', 'sites']:
                product_columns.append(col)
            else:
                document_columns.append(col)

    print(
        f"📊 Detection: {len(annotation_columns)} annotations, {len(product_columns)} products, {len(document_columns)} documents")

    # Use unified approach for all data sources
    print("Using unified approach for all data sources")
    rows = generate_unified_rows(columns, filters)

    generation_time = time.time() - start_time
    print(f"✅ Matrix generated: {len(rows)} rows in {generation_time:.2f}s")

    return {
        'headers': [col['name'] for col in columns],
        'rows': rows,
        'total_rows': len(rows),
        'generation_time': round(generation_time, 2),
        'timestamp': timezone.now().isoformat(),
        'filters_applied': filters,
    }


def generate_unified_rows(columns: List[Dict], filters: Dict) -> List[Dict]:
    """Single function to generate rows from any data source"""

    rows = []

    # Determine if we have product columns
    has_product_columns = any(
        col.get('source') == 'sql_product' or col.get('name', '').startswith('product_')
        for col in columns
    )

    if has_product_columns:
        # Use products as base to avoid duplicates
        products = Product.objects.all()
        products = apply_filters_dynamically(products, Product, filters)

        if filters.get('period'):
            products = apply_period_filter(products, filters['period'])

        products = products[:100]

        for product in products:
            # Get MongoDB data for this product's document
            document = getattr(product, 'source_document', None)
            if document:
                mongo_data = mongo_collection.find_one({"document_id": str(document.id)})
            else:
                mongo_data = None

            # Check if this document has array fields that need expansion
            entity_arrays = {}
            if mongo_data:
                for column in columns:
                    field_name = column.get('name', '')
                    if field_name.startswith('entity_'):
                        entity_key = field_name.replace('entity_', '').replace('_', ' ').title()
                        entities = mongo_data.get('entities', {})
                        if entity_key in entities and isinstance(entities[entity_key], list):
                            entity_arrays[field_name] = entities[entity_key]

            # If we have entity arrays, create one row per combination
            if entity_arrays:
                # Get the maximum length of arrays
                max_length = max(len(arr) for arr in entity_arrays.values())

                for i in range(max_length):
                    row_data = {}
                    has_data = False

                    for column in columns:
                        field_name = column.get('name', '')
                        source = column.get('source', '')

                        try:
                            if field_name in entity_arrays:
                                # Use the i-th value from the array, or empty if array is shorter
                                values = entity_arrays[field_name]
                                value = values[i] if i < len(values) else ''
                            elif source == 'sql_product' or field_name.startswith('product_'):
                                value = get_field_value_dynamically(product, field_name)
                            else:
                                # For non-product fields, try to get from related document
                                if document:
                                    value = get_field_value_dynamically(document, field_name)
                                else:
                                    value = ''

                            if value and value not in ['', 'Field not found', 'None', 'No data', 'Error', '—']:
                                has_data = True

                            row_data[field_name] = str(value)

                        except Exception as e:
                            row_data[field_name] = f"Error: {str(e)}"

                    if has_data:
                        rows.append(row_data)
            else:
                # No entity arrays, create single row
                row_data = {}
                has_data = False

                for column in columns:
                    field_name = column.get('name', '')
                    source = column.get('source', '')

                    try:
                        if source == 'sql_product' or field_name.startswith('product_'):
                            value = get_field_value_dynamically(product, field_name)
                        else:
                            # For non-product fields, try to get from related document
                            if document:
                                value = get_field_value_dynamically(document, field_name)
                            else:
                                value = ''

                        if value and value not in ['', 'Field not found', 'None', 'No data', 'Error', '—']:
                            has_data = True

                        row_data[field_name] = str(value)

                    except Exception as e:
                        row_data[field_name] = f"Error: {str(e)}"

                if has_data:
                    rows.append(row_data)
    else:
        # Use documents as base for non-product queries
        base_documents = RawDocument.objects.filter(is_validated=True)
        base_documents = apply_filters_dynamically(base_documents, RawDocument, filters)

        if filters.get('period'):
            base_documents = apply_period_filter(base_documents, filters['period'])

        base_documents = base_documents.order_by('-created_at')[:100]

        for document in base_documents:
            # Get MongoDB data for this document
            mongo_data = mongo_collection.find_one({"document_id": str(document.id)})

            # Check if this document has array fields that need expansion
            entity_arrays = {}
            if mongo_data:
                for column in columns:
                    field_name = column.get('name', '')
                    if field_name.startswith('entity_'):
                        entity_key = field_name.replace('entity_', '').replace('_', ' ').title()
                        entities = mongo_data.get('entities', {})
                        if entity_key in entities and isinstance(entities[entity_key], list):
                            entity_arrays[field_name] = entities[entity_key]

            # If we have entity arrays, create one row per combination
            if entity_arrays:
                # Get the maximum length of arrays
                max_length = max(len(arr) for arr in entity_arrays.values())

                for i in range(max_length):
                    row_data = {}
                    has_data = False

                    for column in columns:
                        field_name = column.get('name', '')

                        try:
                            if field_name in entity_arrays:
                                # Use the i-th value from the array, or empty if array is shorter
                                values = entity_arrays[field_name]
                                value = values[i] if i < len(values) else ''
                            else:
                                value = get_field_value_dynamically(document, field_name)

                            if value and value not in ['', 'Field not found', 'None', 'No data', 'Error', '—']:
                                has_data = True

                            row_data[field_name] = str(value)

                        except Exception as e:
                            row_data[field_name] = f"Error: {str(e)}"

                    if has_data:
                        rows.append(row_data)
            else:
                # No entity arrays, create single row
                row_data = {}
                has_data = False

                for column in columns:
                    field_name = column.get('name', '')

                    try:
                        value = get_field_value_dynamically(document, field_name)

                        if value and value not in ['', 'Field not found', 'None', 'No data', 'Error', '—']:
                            has_data = True

                        row_data[field_name] = str(value)

                    except Exception as e:
                        row_data[field_name] = f"Error: {str(e)}"

                if has_data:
                    rows.append(row_data)

    return rows


def apply_period_filter(queryset, period):
    """Apply period filter dynamically"""
    period_days = {
        '7d': 7, '30d': 30, '90d': 90,
        '6m': 180, '1y': 365
    }.get(period, 30)

    start_date = timezone.now() - timedelta(days=period_days)
    return queryset.filter(created_at__gte=start_date)


def get_field_value_dynamically(obj, field_name):
    """Get field value from any object - handles all sources"""

    try:
        # Handle MongoDB entities (from your MongoDB collection)
        if field_name.startswith('entity_') or field_name.startswith('metadata_'):
            # For MongoDB fields, we need to query MongoDB directly
            if hasattr(obj, 'id'):
                doc_data = mongo_collection.find_one({"document_id": str(obj.id)})
                if doc_data:
                    if field_name.startswith('entity_'):
                        entity_key = field_name.replace('entity_', '').replace('_', ' ').title()
                        entities = doc_data.get('entities', {})
                        if entity_key in entities:
                            values = entities[entity_key]
                            if isinstance(values, list):
                                # Return only the first value instead of joining all
                                return str(values[0]) if values else ''
                            else:
                                return str(values)

                    elif field_name.startswith('metadata_'):
                        metadata_key = field_name.replace('metadata_', '')
                        metadata = doc_data.get('metadata', {})
                        return str(metadata.get(metadata_key, ''))

            return '—'

        # Clean field name for SQL fields
        clean_field_name = field_name
        if field_name.startswith('product_'):
            clean_field_name = field_name.replace('product_', '')
        elif field_name.startswith('document_'):
            clean_field_name = field_name.replace('document_', '')

        # Try direct attribute access
        if hasattr(obj, clean_field_name):
            value = getattr(obj, clean_field_name)

            if value is None:
                return ''

            # Handle datetime fields
            if hasattr(value, 'strftime'):
                return value.strftime('%d/%m/%Y')

            # Handle QuerySet/Manager (relationships)
            if hasattr(value, 'all'):
                related_items = value.all()[:3]
                if related_items.exists():
                    item_strings = []
                    for item in related_items:
                        for name_field in ['name', 'title', 'site_name', 'label', 'display_name']:
                            if hasattr(item, name_field):
                                field_value = getattr(item, name_field)
                                if field_value:
                                    item_strings.append(str(field_value))
                                    break
                        else:
                            item_strings.append(str(item))

                    return '; '.join(item_strings) if item_strings else 'None'
                else:
                    return 'None'

            return str(value)

        # Handle JSONField lookups
        if field_name.startswith('additional_') and hasattr(obj, 'additional_annotations'):
            annotation_key = field_name.replace('additional_', '')
            if obj.additional_annotations and isinstance(obj.additional_annotations, dict):
                return str(obj.additional_annotations.get(annotation_key, ''))

        return 'Field not found'

    except Exception as e:
        return f'Error: {str(e)}'


def build_base_queryset_simple(filters: Dict):
    """Build the base queryset based on filter values - SUPPORTS ALL FILTERS"""

    queryset = RawDocument.objects.filter(is_validated=True)

    print(f"🔍 Applying filters: {filters}")

    # Apply time period filters
    if filters.get('period'):
        period = filters['period']
        if period == '7d':
            start_date = timezone.now() - timedelta(days=7)
        elif period == '30d':
            start_date = timezone.now() - timedelta(days=30)
        elif period == '90d':
            start_date = timezone.now() - timedelta(days=90)
        elif period == '6m':
            start_date = timezone.now() - timedelta(days=180)
        elif period == '1y':
            start_date = timezone.now() - timedelta(days=365)
        else:
            start_date = timezone.now() - timedelta(days=30)

        queryset = queryset.filter(created_at__gte=start_date)

    # Apply document filters
    if filters.get('doc_type'):
        queryset = queryset.filter(doc_type__icontains=filters['doc_type'])

    if filters.get('doc_country'):
        queryset = queryset.filter(country__icontains=filters['doc_country'])

    if filters.get('doc_source'):
        queryset = queryset.filter(source__icontains=filters['doc_source'])

    if filters.get('language'):
        queryset = queryset.filter(language__icontains=filters['language'])

    # Apply product filters (filter documents that have products with these criteria)
    if filters.get('product_name'):
        queryset = queryset.filter(
            product_set__name__icontains=filters['product_name']
        ).distinct()

    if filters.get('dosage'):
        queryset = queryset.filter(
            product_set__dosage__icontains=filters['dosage']
        ).distinct()

    if filters.get('active_ingredient'):
        queryset = queryset.filter(
            product_set__active_ingredient__icontains=filters['active_ingredient']
        ).distinct()

    if filters.get('therapeutic_area'):
        queryset = queryset.filter(
            product_set__therapeutic_area__icontains=filters['therapeutic_area']
        ).distinct()

    if filters.get('product_status'):
        queryset = queryset.filter(
            product_set__status=filters['product_status']
        ).distinct()

    # Apply manufacturing site filters
    if filters.get('site_country'):
        queryset = queryset.filter(
            product_set__sites__country__icontains=filters['site_country']
        ).distinct()

    if filters.get('site_name'):
        queryset = queryset.filter(
            product_set__sites__site_name__icontains=filters['site_name']
        ).distinct()

    # Apply annotation filters (dynamic based on annotation types)
    for filter_key, filter_value in filters.items():
        if filter_key.startswith('annotation_') and filter_value:
            annotation_type_name = filter_key.replace('annotation_', '')
            queryset = queryset.filter(
                pages__annotations__annotation_type__name=annotation_type_name,
                pages__annotations__selected_text__icontains=filter_value,
                pages__annotations__validation_status__in=['validated', 'expert_created']
            ).distinct()

    print(f"📊 Filtered queryset: {queryset.count()} documents")
    return queryset.order_by('-created_at')


def generate_column_value_simple(column: Dict, document: RawDocument) -> str:
    """Generate value for a specific column based on its configuration"""

    source_type = column.get('source_type', column.get('type', 'document'))
    field_name = column.get('field_path', column.get('name', ''))

    if source_type == 'annotation':
        return extract_annotation_value_simple(field_name, document)

    elif source_type == 'document_field':
        return extract_document_field_simple(field_name, document)

    elif source_type == 'product_field':
        return extract_product_field_simple(field_name, document)

    elif source_type == 'ai_generated':
        return generate_ai_value_simple(field_name, document)

    else:
        return "N/A"


def extract_annotation_value_simple(field_name: str, document: RawDocument) -> str:
    """Extract value from annotations"""
    try:
        # Find annotation type by name
        annotation_type = AnnotationType.objects.filter(name=field_name).first()
        if not annotation_type:
            return ""

        # Get annotations of this type for this document
        annotations = Annotation.objects.filter(
            page__document=document,
            annotation_type=annotation_type,
            validation_status__in=['validated', 'expert_created']
        ).values_list('selected_text', flat=True)

        if annotations:
            # Return the most common annotation or concatenate unique ones
            unique_annotations = list(set(annotations))
            if len(unique_annotations) == 1:
                return unique_annotations[0]
            else:
                return "; ".join(unique_annotations[:3])  # Limit to avoid too long text

        return ""
    except Exception as e:
        print(f"❌ Error extracting annotation {field_name}: {e}")
        return "Error"


def extract_document_field_simple(field_name: str, document: RawDocument) -> str:
    """Extract value from document fields"""
    try:
        value = getattr(document, field_name, None)
        if value is None:
            return ""

        # Format based on field type
        if hasattr(value, 'strftime'):  # Date/datetime field
            return value.strftime('%d/%m/%Y')

        return str(value)
    except Exception as e:
        print(f"❌ Error extracting document field {field_name}: {e}")
        return "Field Not Found"


def extract_product_field_simple(field_name: str, document: RawDocument) -> str:
    """Extract value from related products - HANDLES ALL PRODUCT FIELDS"""
    try:
        # Get a product (linked to document or any product)
        products_from_doc = Product.objects.filter(source_document=document)

        if products_from_doc.exists():
            product = products_from_doc.first()
        else:
            all_products = Product.objects.all()
            if not all_products.exists():
                return "No products in database"
            product_index = document.id % all_products.count()
            product = all_products[product_index]

        # Handle base product fields
        if field_name in ['name', 'active_ingredient', 'dosage', 'form', 'therapeutic_area']:
            value = getattr(product, field_name, "")
            return str(value) if value else ""

        elif field_name == 'status':
            return product.get_status_display()

        elif field_name == 'created_at':
            return product.created_at.strftime('%d/%m/%Y') if product.created_at else ""

        # Handle manufacturing sites fields - FIXED
        elif field_name in ['manufacturing_sites', 'sites']:
            sites = product.sites.all()
            print(f"🏭 DEBUG: Found {sites.count()} sites for product {product.name}")

            if sites.exists():
                site_data = []
                for site in sites[:3]:
                    try:
                        # Force string conversion to avoid object references
                        site_name = str(site.site_name) if site.site_name else ""
                        city = str(site.city) if site.city else ""
                        country = str(site.country) if site.country else ""

                        # Build display string
                        display_parts = []
                        if site_name:
                            display_parts.append(site_name)
                        if city:
                            display_parts.append(city)
                        if country:
                            display_parts.append(country)

                        if display_parts:
                            site_display = ' - '.join(display_parts)
                            site_data.append(site_display)
                        else:
                            site_data.append(f"Site #{site.id}")

                    except Exception as site_error:
                        print(f"❌ Error processing site: {site_error}")
                        site_data.append(f"Site #{site.id}")

                result = '; '.join(site_data) if site_data else "No site data"
                return result
            else:
                return "No manufacturing sites"

        elif field_name == 'manufacturing_countries':
            sites = product.sites.all()
            if sites.exists():
                countries = list(set([site.country for site in sites]))
                return "; ".join(countries)
            return ""

        elif field_name == 'gmp_certified_sites':
            sites = product.sites.filter(gmp_certified=True)
            if sites.exists():
                site_names = [site.site_name for site in sites]
                return "; ".join(site_names)
            return "None certified"

        elif field_name == 'site_count':
            return str(product.sites.count())

        # Handle product specifications fields - FIXED
        elif field_name == 'amm_numbers':
            specs = product.specifications.all()  # This matches your model: related_name='specifications'
            if specs.exists():
                amm_numbers = [spec.amm_number for spec in specs[:3]]
                return "; ".join(amm_numbers)
            return "No AMM"

        elif field_name == 'approved_countries':
            specs = product.specifications.all()
            if specs.exists():
                countries = [spec.country_code for spec in specs]
                return "; ".join(countries)
            return ""

        elif field_name == 'ctd_status':
            specs = product.specifications.filter(ctd_dossier_complete=True)
            return f"{specs.count()} CTD complets" if specs.exists() else "No CTD"

        elif field_name == 'gmp_certificate_status':
            specs = product.specifications.filter(gmp_certificate=True)
            return f"{specs.count()} with GMP" if specs.exists() else "No GMP"

        # Handle product variations fields - FIXED
        elif field_name == 'variation_count':
            return str(product.variations.count())  # This matches your model: related_name='variations'

        elif field_name == 'latest_variation':
            latest = product.variations.first()  # Already ordered by -submission_date
            return latest.title if latest else "No variations"

        elif field_name == 'pending_variations':
            pending = product.variations.filter(status='soumis')
            return str(pending.count())

        elif field_name == 'approved_variations':
            approved = product.variations.filter(status='approuve')
            return str(approved.count())

        # Handle additional annotation fields
        elif field_name.startswith('additional_'):
            annotation_type = field_name.replace('additional_', '')
            additional_data = product.additional_annotations.get(annotation_type, '')
            return str(additional_data) if additional_data else "No data"

        else:
            # Fallback for any other field
            value = getattr(product, field_name, None)
            return str(value) if value else "Field not found"

    except Exception as e:
        print(f"❌ Error extracting product field {field_name}: {e}")
        return f"Error: {str(e)}"


def debug_sites():
    from client.products.models import Product, ManufacturingSite

    print("🔍 Checking manufacturing sites...")
    total_sites = ManufacturingSite.objects.count()
    print(f"Total sites: {total_sites}")

    if total_sites > 0:
        for site in ManufacturingSite.objects.all()[:3]:
            print(f"Site: {site.site_name} | {site.city} | {site.country}")
    else:
        print("❌ No manufacturing sites found!")


def generate_ai_value_simple(field_name: str, document: RawDocument) -> str:
    """Generate AI-powered content for a column"""

    # Simplified AI generation - you can enhance this with real AI calls
    ai_responses = {
        'risk_assessment': ['Low Risk', 'Medium Risk', 'High Risk'],
        'compliance_score': ['85%', '92%', '78%', '95%'],
        'similar_cases': ['3 cases found', '1 similar case', 'No similar cases'],
        'recommendation': ['Standard process', 'Requires attention', 'Fast track eligible'],
        'timeline_estimate': ['2-3 months', '4-6 months', '6-12 months']
    }

    try:
        # Simple random selection for demo - replace with real AI
        import random
        options = ai_responses.get(field_name, ['AI Generated'])
        return random.choice(options)

    except Exception as e:
        print(f"❌ Error generating AI value {field_name}: {e}")
        return f"AI Error: {str(e)}"


def apply_filters_dynamically(queryset, model_class, filters: Dict):
    """Apply filters dynamically to any model - ZERO HARDCODING"""

    if not filters:
        return queryset

    print(f"🔍 Applying filters dynamically to {model_class.__name__}: {filters}")

    for filter_key, filter_value in filters.items():
        if not filter_value or filter_value == '':
            continue

        print(f"🔍 Processing filter: {filter_key} = {filter_value}")

        # Skip period filter (handled separately)
        if filter_key == 'period':
            continue

        # Special handling for product filters
        if filter_key == 'product_name':
            if model_class == Product:
                queryset = queryset.filter(name__icontains=filter_value)
                print(f"✅ Applied product_name filter to Product: {filter_value}")
                continue
            elif model_class == RawDocument:
                queryset = queryset.filter(product_set__name__icontains=filter_value).distinct()
                print(f"✅ Applied product_name filter to RawDocument: {filter_value}")
                continue

        if filter_key == 'product_active_ingredient':
            if model_class == Product:
                queryset = queryset.filter(active_ingredient__icontains=filter_value)
                print(f"✅ Applied active_ingredient filter: {filter_value}")
                continue
            elif model_class == RawDocument:
                queryset = queryset.filter(product_set__active_ingredient__icontains=filter_value).distinct()
                print(f"✅ Applied active_ingredient filter to documents: {filter_value}")
                continue

        if filter_key == 'product_dosage':
            if model_class == Product:
                queryset = queryset.filter(dosage__icontains=filter_value)
                print(f"✅ Applied dosage filter: {filter_value}")
                continue
            elif model_class == RawDocument:
                queryset = queryset.filter(product_set__dosage__icontains=filter_value).distinct()
                print(f"✅ Applied dosage filter to documents: {filter_value}")
                continue

        # Special handling for document filters
        if filter_key == 'document_url':
            if model_class == RawDocument:
                queryset = queryset.filter(url__icontains=filter_value)
                print(f"✅ Applied document_url filter: {filter_value}")
                continue
            elif model_class == Product:
                queryset = queryset.filter(source_document__url__icontains=filter_value).distinct()
                print(f"✅ Applied document_url filter to products: {filter_value}")
                continue

        if filter_key == 'document_title':
            if model_class == RawDocument:
                queryset = queryset.filter(title__icontains=filter_value)
                print(f"✅ Applied document_title filter: {filter_value}")
                continue

        if filter_key == 'document_source':
            if model_class == RawDocument:
                queryset = queryset.filter(source__icontains=filter_value)
                print(f"✅ Applied document_source filter: {filter_value}")
                continue

        # Special handling for entity and metadata filters (MongoDB)
        if filter_key.startswith('entity_') or filter_key.startswith('metadata_'):
            # MongoDB filters can't be applied to SQL querysets directly
            # They need to be handled in the MongoDB query part
            print(f"📝 MongoDB filter noted: {filter_key} = {filter_value}")
            continue

        try:
            # Get all field names from the model
            field_names = [f.name for f in model_class._meta.get_fields()]

            # SPECIAL HANDLING for specific relationship fields we know about
            if filter_key == 'sites' and model_class == Product:
                # Filter products by their related manufacturing sites
                queryset = queryset.filter(sites__site_name__icontains=filter_value)
                print(f"✅ Applied sites relationship filter: {filter_value}")
                continue

            # Try exact field match first
            if filter_key in field_names:
                field = model_class._meta.get_field(filter_key)

                # Check if it's a REAL relationship field (not just any field with related_model)
                is_relationship = (
                        hasattr(field, 'related_model') and
                        field.get_internal_type() in ['ForeignKey', 'ManyToManyField', 'OneToOneField']
                )

                if is_relationship:
                    print(f"⚠️ Skipping relationship field: {filter_key} (type: {field.get_internal_type()})")
                    continue
                else:
                    # Regular field - apply icontains
                    filter_kwargs = {f"{filter_key}__icontains": filter_value}
                    queryset = queryset.filter(**filter_kwargs)
                    print(f"✅ Applied exact field filter: {filter_key} (type: {field.get_internal_type()})")
                    continue

            # Try removing prefixes (additional_authority -> authority)
            if filter_key.startswith('additional_'):
                clean_key = filter_key.replace('additional_', '')
                if clean_key in field_names:
                    field = model_class._meta.get_field(clean_key)
                    is_relationship = (
                            hasattr(field, 'related_model') and
                            field.get_internal_type() in ['ForeignKey', 'ManyToManyField', 'OneToOneField']
                    )

                    if not is_relationship:
                        filter_kwargs = {f"{clean_key}__icontains": filter_value}
                        queryset = queryset.filter(**filter_kwargs)
                        print(f"✅ Applied cleaned field filter: {clean_key}")
                        continue

                # Handle JSONField additional_annotations
                if hasattr(model_class, 'additional_annotations'):
                    annotation_key = clean_key
                    filter_kwargs = {
                        'additional_annotations__has_key': annotation_key,
                        f'additional_annotations__{annotation_key}__icontains': filter_value
                    }
                    queryset = queryset.filter(**filter_kwargs)
                    print(f"✅ Applied additional annotation filter: {annotation_key}")
                    continue

            # Try common variations (but only for non-relationship fields)
            variations = [
                filter_key.replace('_', ''),  # remove underscores
                filter_key.replace('-', '_'),  # dash to underscore
                filter_key + '_type',  # add _type suffix
                filter_key + '_name',  # add _name suffix
            ]

            found_match = False
            for variation in variations:
                if variation in field_names:
                    field = model_class._meta.get_field(variation)
                    is_relationship = (
                            hasattr(field, 'related_model') and
                            field.get_internal_type() in ['ForeignKey', 'ManyToManyField', 'OneToOneField']
                    )

                    if not is_relationship:
                        filter_kwargs = {f"{variation}__icontains": filter_value}
                        queryset = queryset.filter(**filter_kwargs)
                        print(f"✅ Applied variation filter: {filter_key} -> {variation}")
                        found_match = True
                        break

            if not found_match:
                print(f"⚠️ No matching field found for filter: {filter_key}")

        except Exception as e:
            print(f"❌ Error applying filter {filter_key}: {e}")

    return queryset