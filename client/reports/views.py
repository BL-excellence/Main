from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.utils import timezone
from django.db.models import Count, Avg, Q, Case, When, IntegerField
from datetime import datetime, timedelta
from client.products.models import Product
from .models import ReportSubmission, ReportKPI, ReportHeatmap
import json
import csv
import io

def reports_dashboard(request):
    """Vue principale du dashboard des rapports"""
    
    # Récupération des filtres
    filters = {
        'period': request.GET.get('period', '30d'),
        'product': request.GET.get('product', ''),
        'status': request.GET.get('status', ''),
        'team': request.GET.get('team', ''),
    }
    
    # Calcul de la période
    period_days = get_period_days(filters['period'])
    start_date = timezone.now().date() - timedelta(days=period_days)
    
    # Construction du queryset avec filtres
    submissions_qs = ReportSubmission.objects.filter(
        submission_date__gte=start_date
    )
    
    if filters['product']:
        submissions_qs = submissions_qs.filter(product_id=filters['product'])
    if filters['status']:
        submissions_qs = submissions_qs.filter(status=filters['status'])
    if filters['team']:
        submissions_qs = submissions_qs.filter(team=filters['team'])
    
    # Calcul des KPIs
    kpis = calculate_kpis(submissions_qs, start_date)
    
    # Données pour les graphiques
    chart_data = get_chart_data(submissions_qs, start_date)
    
    # Données heatmap
    heatmap_data = get_heatmap_data(filters)
    
    # Soumissions récentes
    recent_submissions = submissions_qs.select_related('product').order_by('-submission_date')[:10]
    
    # Produits pour le filtre
    products = Product.objects.all()
    
    # Compte des filtres actifs
    active_filters_count = sum(1 for v in filters.values() if v)
    
    context = {
        'filters': filters,
        'active_filters_count': active_filters_count,
        'kpis': kpis,
        'trend_data': json.dumps(chart_data['trend']),
        'status_data': json.dumps(chart_data['status']),
        'heatmap_data': heatmap_data,
        'recent_submissions': recent_submissions,
        'products': products,
    }
    
    return render(request, 'client/reports/dashboard.html', context)

def calculate_kpis(submissions_qs, start_date):
    """Calcule les KPIs principaux"""
    
    # Période précédente pour les comparaisons
    period_length = (timezone.now().date() - start_date).days
    previous_start = start_date - timedelta(days=period_length)
    previous_submissions = ReportSubmission.objects.filter(
        submission_date__gte=previous_start,
        submission_date__lt=start_date
    )
    
    # KPIs actuels
    total_submissions = submissions_qs.count()
    
    # Calcul manuel du délai moyen (puisque days_delay est une propriété)
    total_delay = 0
    submission_count = 0
    for submission in submissions_qs:
        total_delay += submission.days_delay
        submission_count += 1
    
    average_delay = total_delay / submission_count if submission_count > 0 else 0
    
    success_count = submissions_qs.filter(status='approuve').count()
    success_rate = (success_count / total_submissions * 100) if total_submissions > 0 else 0
    
    delayed_count = submissions_qs.filter(
        estimated_completion__lt=timezone.now().date(),
        status__in=['en-cours', 'en-attente']
    ).count()
    
    # KPIs précédents pour les tendances
    previous_total = previous_submissions.count()
    previous_success = previous_submissions.filter(status='approuve').count()
    previous_success_rate = (previous_success / previous_total * 100) if previous_total > 0 else 0
    previous_delayed = previous_submissions.filter(
        estimated_completion__lt=start_date,
        status__in=['en-cours', 'en-attente']
    ).count()
    
    # Calcul des tendances
    submissions_trend = calculate_trend(total_submissions, previous_total)
    delay_trend = -5  # Simplification pour l'exemple
    success_trend = success_rate - previous_success_rate
    delayed_trend = calculate_trend(delayed_count, previous_delayed)
    
    return {
        'total_submissions': total_submissions,
        'average_delay': int(average_delay),
        'success_rate': int(success_rate),
        'delayed_count': delayed_count,
        'submissions_trend': submissions_trend,
        'delay_trend': delay_trend,
        'success_trend': success_trend,
        'delayed_trend': delayed_trend,
    }

def calculate_trend(current, previous):
    """Calcule la tendance en pourcentage"""
    if previous == 0:
        return 100 if current > 0 else 0
    return ((current - previous) / previous) * 100

def get_chart_data(submissions_qs, start_date):
    """Prépare les données pour les graphiques"""
    
    # Données de tendance par mois
    trend_data = {
        'labels': ['Jan', 'Fév', 'Mar', 'Avr', 'Mai', 'Jun'],
        'datasets': [
            {
                'label': 'Total soumissions',
                'data': [65, 78, 82, 91, 95, 88],
                'borderColor': '#3498db',
                'backgroundColor': 'rgba(52, 152, 219, 0.1)',
                'tension': 0.4,
                'fill': False
            },
            {
                'label': 'Approuvées',
                'data': [52, 68, 71, 79, 83, 76],
                'borderColor': '#27ae60',
                'backgroundColor': 'rgba(39, 174, 96, 0.1)',
                'tension': 0.4,
                'fill': False
            },
            {
                'label': 'Rejetées',
                'data': [8, 6, 7, 9, 8, 7],
                'borderColor': '#e74c3c',
                'backgroundColor': 'rgba(231, 76, 60, 0.1)',
                'tension': 0.4,
                'fill': False
            }
        ]
    }
    
    # Données de statut (utilise les données réelles si disponibles)
    status_counts = submissions_qs.values('status').annotate(count=Count('id'))
    
    # Préparer les données pour le graphique
    status_data = {
        'labels': [],
        'datasets': [{
            'data': [],
            'backgroundColor': ['#27ae60', '#3498db', '#f39c12', '#e74c3c'],
            'borderWidth': 0,
            'cutout': '60%'
        }]
    }
    
    status_labels = {
        'approuve': 'Approuvé',
        'en-cours': 'En cours',
        'en-attente': 'En attente',
        'rejete': 'Rejeté'
    }
    
    # Si nous avons des données réelles, les utiliser
    if status_counts.exists():
        for item in status_counts:
            status_data['labels'].append(status_labels.get(item['status'], item['status']))
            status_data['datasets'][0]['data'].append(item['count'])
    else:
        # Données par défaut si pas de données
        status_data['labels'] = ['Approuvé', 'En cours', 'En attente', 'Rejeté']
        status_data['datasets'][0]['data'] = [156, 67, 18, 6]
    
    return {
        'trend': trend_data,
        'status': status_data
    }

def get_heatmap_data(filters):
    """Prépare les données pour la heatmap"""
    
    # Récupération des données heatmap
    heatmap_qs = ReportHeatmap.objects.select_related('product').all()
    
    if filters['product']:
        heatmap_qs = heatmap_qs.filter(product_id=filters['product'])
    
    # Si nous avons des données réelles, les utiliser
    if heatmap_qs.exists():
        return [
            {
                'product': item.product.name,
                'authorization_delay': item.authorization_delay,
                'authorization_status': item.authorization_status,
                'variation_delay': item.variation_delay,
                'variation_status': item.variation_status,
                'renewal_delay': item.renewal_delay,
                'renewal_status': item.renewal_status,
            }
            for item in heatmap_qs
        ]
    else:
        # Données par défaut si pas de données
        return [
            {
                'product': 'Médicament A',
                'authorization_delay': 25,
                'authorization_status': 'good',
                'variation_delay': 45,
                'variation_status': 'warning',
                'renewal_delay': 70,
                'renewal_status': 'critical',
            },
            {
                'product': 'Médicament B',
                'authorization_delay': 30,
                'authorization_status': 'good',
                'variation_delay': 35,
                'variation_status': 'warning',
                'renewal_delay': None,
                'renewal_status': 'good',
            },
            {
                'product': 'Dispositif X',
                'authorization_delay': 20,
                'authorization_status': 'good',
                'variation_delay': 28,
                'variation_status': 'good',
                'renewal_delay': None,
                'renewal_status': 'good',
            }
        ]

def get_period_days(period):
    """Convertit la période en nombre de jours"""
    period_mapping = {
        '30d': 30,
        '90d': 90,
        '6m': 180,
        '1y': 365,
    }
    return period_mapping.get(period, 30)

def export_data(request):
    """Export des données en différents formats"""
    
    export_format = request.GET.get('format', 'csv')
    
    # Récupération des données avec filtres
    filters = {
        'period': request.GET.get('period', '30d'),
        'product': request.GET.get('product', ''),
        'status': request.GET.get('status', ''),
        'team': request.GET.get('team', ''),
    }
    
    period_days = get_period_days(filters['period'])
    start_date = timezone.now().date() - timedelta(days=period_days)
    
    submissions_qs = ReportSubmission.objects.filter(
        submission_date__gte=start_date
    ).select_related('product')
    
    if filters['product']:
        submissions_qs = submissions_qs.filter(product_id=filters['product'])
    if filters['status']:
        submissions_qs = submissions_qs.filter(status=filters['status'])
    if filters['team']:
        submissions_qs = submissions_qs.filter(team=filters['team'])
    
    # Export selon le format
    if export_format == 'csv':
        return export_csv(submissions_qs)
    elif export_format == 'excel':
        return export_excel(submissions_qs)
    elif export_format == 'pdf':
        return export_pdf(submissions_qs)
    
    return JsonResponse({'error': 'Format non supporté'}, status=400)

def export_csv(submissions_qs):
    """Export CSV"""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="regx_report.csv"'
    
    writer = csv.writer(response)
    writer.writerow([
        'Produit', 'Type', 'Statut', 'Date soumission', 
        'Date estimée', 'Responsable', 'Progression', 'Retard (jours)'
    ])
    
    for submission in submissions_qs:
        writer.writerow([
            submission.product.name,
            submission.get_type_display(),
            submission.get_status_display(),
            submission.submission_date.strftime('%d/%m/%Y'),
            submission.estimated_completion.strftime('%d/%m/%Y'),
            submission.responsible,
            f"{submission.progress}%",
            submission.days_delay
        ])
    
    return response

def export_excel(submissions_qs):
    """Export Excel - Placeholder"""
    # Pour l'instant, retourne un CSV
    return export_csv(submissions_qs)

def export_pdf(submissions_qs):
    """Export PDF - Placeholder"""
    # Pour l'instant, retourne un CSV
    return export_csv(submissions_qs)

def submission_detail(request, pk):
    """Détail d'une soumission"""
    submission = get_object_or_404(ReportSubmission, pk=pk)
    return render(request, 'reports/submission_detail.html', {
        'submission': submission
    })

def reports_settings(request):
    """Paramètres des rapports"""
    return render(request, 'reports/settings.html')

def reports_create(request):
    """Créer un nouveau rapport"""
    return render(request, 'reports/create.html')