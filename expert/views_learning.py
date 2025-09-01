# expert/views_learning.py

import json
from datetime import timedelta

from django.db import models
from django.shortcuts import get_object_or_404, render
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone

from rawdocs.models import RawDocument
from .models import ExpertDelta, ExpertLearningStats
from .learning_service import ExpertLearningService
from .views import expert_required


@expert_required
@csrf_exempt
def compare_with_ai_and_learn(request, doc_id):
    """
    Compare la version actuelle de l'IA avec les corrections de l'expert
    et enregistre les différences pour l'apprentissage
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        document = get_object_or_404(RawDocument, id=doc_id)
        data = json.loads(request.body)

        # Récupérer les versions IA et Expert
        expert_json = data.get('expert_json', {})
        context = data.get('context', {})

        # Générer une nouvelle version IA pour comparaison
        from .json_enrichment import enrich_document_json_for_expert
        basic_json = document.global_annotations_json or {}

        # Générer la version IA "fraîche" (sans les corrections précédentes)
        fresh_ai_json = enrich_document_json_for_expert(document, basic_json)

        # Comparer et apprendre
        learning_service = ExpertLearningService()
        comparison_result = learning_service.compare_and_learn(
            document=document,
            ai_json=fresh_ai_json,
            expert_json=expert_json,
            expert_user=request.user,
            context=context
        )

        return JsonResponse({
            'success': True,
            'message': f"Comparaison terminée: {comparison_result['deltas_created']} différences enregistrées",
            'comparison': comparison_result,
            'ai_version': fresh_ai_json,  # Pour debug/affichage
        })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@expert_required
def get_learning_history(request, doc_id):
    """Récupère l'historique d'apprentissage pour un document"""
    try:
        document = get_object_or_404(RawDocument, id=doc_id)
        learning_service = ExpertLearningService()

        history = learning_service.get_learning_history(document)

        return JsonResponse({
            'success': True,
            'history': history
        })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@expert_required
@csrf_exempt
def enhance_with_learned_patterns(request, doc_id):
    """
    Applique les patterns appris pour améliorer le JSON courant
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        document = get_object_or_404(RawDocument, id=doc_id)
        data = json.loads(request.body)

        current_json = data.get('current_json') or document.enriched_annotations_json or {}
        document_context = {
            'title': document.title,
            'doc_type': document.doc_type,
            'country': document.country,
            'language': document.language,
        }

        learning_service = ExpertLearningService()
        enhancement_result = learning_service.enhance_with_learned_patterns(
            document=document,
            current_json=current_json,
            document_context=document_context
        )

        return JsonResponse({
            'success': True,
            'message': f"{enhancement_result['patterns_applied']} patterns appliqués",
            'enhanced_json': enhancement_result['enhanced_json'],
            'enhancements': enhancement_result['enhancements']
        })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@expert_required
def view_expert_deltas(request, doc_id):
    """Interface pour visualiser les différences IA vs Expert"""
    try:
        document = get_object_or_404(RawDocument, id=doc_id)

        # Récupérer tous les deltas pour ce document
        deltas = ExpertDelta.objects.filter(
            document=document,
            is_active=True
        ).select_related('expert').order_by('-created_at')

        # Grouper par session
        sessions = {}
        for delta in deltas:
            session_id = delta.session_id or 'unknown'
            if session_id not in sessions:
                sessions[session_id] = {
                    'session_id': session_id,
                    'expert': delta.expert.username,
                    'created_at': delta.created_at,
                    'deltas': []
                }
            sessions[session_id]['deltas'].append(delta)

        # Statistiques
        total_corrections = deltas.count()
        experts_count = deltas.values('expert').distinct().count()

        # Types de corrections les plus fréquents
        delta_types = {}
        for delta in deltas:
            delta_types[delta.delta_type] = delta_types.get(delta.delta_type, 0) + 1

        context = {
            'document': document,
            'sessions': list(sessions.values()),
            'total_corrections': total_corrections,
            'experts_count': experts_count,
            'delta_types': delta_types,
        }

        return render(request, 'expert/view_expert_deltas.html', context)

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@expert_required
@csrf_exempt
def rate_correction_quality(request, delta_id):
    """Permet à l'expert de noter la qualité d'une correction"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        delta = get_object_or_404(ExpertDelta, id=delta_id)
        data = json.loads(request.body)

        rating = data.get('rating')
        if rating not in [1, 2, 3, 4, 5]:
            return JsonResponse({'error': 'Rating must be 1-5'}, status=400)

        delta.expert_rating = rating
        delta.save(update_fields=['expert_rating'])

        return JsonResponse({
            'success': True,
            'message': f'Qualité notée: {rating}/5'
        })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@expert_required
def get_learning_stats(request):
    """Récupère les statistiques globales d'apprentissage"""
    try:
        # Stats globales pour cet expert
        expert_stats = ExpertLearningStats.objects.filter(
            expert=request.user
        ).aggregate(
            total_corrections=models.Sum('total_corrections'),
            total_relations=models.Sum('relations_improved'),
            total_qa=models.Sum('qa_improved'),
            avg_rating=models.Avg('avg_expert_rating')
        )

        # Progression dans le temps
        recent_stats = ExpertLearningStats.objects.filter(
            expert=request.user,
            period_start__gte=timezone.now() - timedelta(days=30)
        ).order_by('period_start')

        progression = []
        for stat in recent_stats:
            progression.append({
                'date': stat.period_start.strftime('%Y-%m-%d'),
                'corrections': stat.total_corrections,
                'relations': stat.relations_improved,
                'qa': stat.qa_improved
            })

        # Top des corrections les plus réutilisées
        top_reused = ExpertDelta.objects.filter(
            expert=request.user,
            is_active=True
        ).order_by('-reused_count')[:10]

        top_corrections = []
        for delta in top_reused:
            top_corrections.append({
                'summary': delta.correction_summary,
                'reused_count': delta.reused_count,
                'type': delta.get_delta_type_display(),
                'created_at': delta.created_at.strftime('%d/%m/%Y')
            })

        return JsonResponse({
            'success': True,
            'stats': {
                'global': expert_stats,
                'progression': progression,
                'top_corrections': top_corrections
            }
        })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@expert_required
@csrf_exempt
def regenerate_with_learning(request, doc_id):
    """
    Régénère le JSON enrichi en appliquant l'apprentissage des corrections précédentes
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        document = get_object_or_404(RawDocument, id=doc_id)

        # Générer la version de base
        from .json_enrichment import enrich_document_json_for_expert
        basic_json = document.global_annotations_json or {}
        base_enriched = enrich_document_json_for_expert(document, basic_json)

        # Appliquer l'apprentissage
        learning_service = ExpertLearningService()
        document_context = {
            'title': document.title,
            'doc_type': document.doc_type,
            'country': document.country,
            'language': document.language,
        }

        enhancement_result = learning_service.enhance_with_learned_patterns(
            document=document,
            current_json=base_enriched,
            document_context=document_context
        )

        # Sauvegarder la version améliorée
        enhanced_json = enhancement_result['enhanced_json']
        enhanced_json['metadata']['learning_applied'] = True
        enhanced_json['metadata']['patterns_applied'] = enhancement_result['patterns_applied']
        enhanced_json['metadata']['enhancements'] = enhancement_result['enhancements']

        document.enriched_annotations_json = enhanced_json
        document.save(update_fields=['enriched_annotations_json'])

        return JsonResponse({
            'success': True,
            'message': f"JSON régénéré avec {enhancement_result['patterns_applied']} améliorations",
            'enhanced_json': enhanced_json,
            'enhancements': enhancement_result['enhancements']
        })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)