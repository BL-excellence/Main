# expert/learning_service.py

import json
import uuid
from typing import Dict, List, Any, Tuple, Optional
from django.utils import timezone
from django.db.models import Avg, Count
from difflib import SequenceMatcher

from .models import ExpertDelta, ExpertLearningStats
from .json_enrichment import JSONEnricher


class ExpertLearningService:
    """
    Service pour comparer les résultats IA avec les corrections expert
    et améliorer les futures générations
    """

    def __init__(self):
        self.enricher = JSONEnricher()

    def compare_and_learn(
            self,
            document,
            ai_json: Dict[str, Any],
            expert_json: Dict[str, Any],
            expert_user,
            context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Compare la version IA avec la version expert et enregistre les différences
        """
        context = context or {}
        deltas = []

        # Comparer les relations
        relation_deltas = self._compare_relations(
            ai_json.get('relations', []),
            expert_json.get('relations', [])
        )

        # Comparer les entités
        entity_deltas = self._compare_entities(
            ai_json.get('entities', {}),
            expert_json.get('entities', {})
        )

        # Comparer les Q&A
        qa_deltas = self._compare_qa(
            ai_json.get('questions_answers', []),
            expert_json.get('questions_answers', [])
        )

        # Enregistrer tous les deltas
        session_id = str(uuid.uuid4())[:8]

        for delta in relation_deltas + entity_deltas + qa_deltas:
            expert_delta = ExpertDelta.objects.create(
                document=document,
                expert=expert_user,
                session_id=session_id,
                delta_type=delta['type'],
                ai_version=delta['ai_version'],
                expert_version=delta['expert_version'],
                context=context,
                confidence_before=delta.get('confidence_before', 0.8)
            )
            deltas.append(expert_delta)

        # Mettre à jour les statistiques
        self._update_learning_stats(expert_user, document, deltas)

        return {
            'deltas_created': len(deltas),
            'relations_changed': len(relation_deltas),
            'entities_changed': len(entity_deltas),
            'qa_changed': len(qa_deltas),
            'session_id': session_id,
            'summary': self._generate_comparison_summary(deltas)
        }

    def _compare_relations(
            self,
            ai_relations: List[Dict],
            expert_relations: List[Dict]
    ) -> List[Dict]:
        """Compare les relations IA vs Expert"""
        deltas = []

        def relation_key(rel):
            if not isinstance(rel, dict):
                return ""
            source = rel.get('source', {})
            target = rel.get('target', {})
            return f"{source.get('type', '')}:{source.get('value', '')}--{rel.get('type', '')}-->{target.get('type', '')}:{target.get('value', '')}"

        # Index des relations IA et expert
        ai_map = {relation_key(rel): rel for rel in ai_relations}
        expert_map = {relation_key(rel): rel for rel in expert_relations}

        # Relations ajoutées par l'expert
        for key, expert_rel in expert_map.items():
            if key not in ai_map:
                deltas.append({
                    'type': 'relation_added',
                    'ai_version': {},
                    'expert_version': expert_rel,
                    'confidence_before': 0.0
                })

        # Relations modifiées par l'expert
        for key, expert_rel in expert_map.items():
            if key in ai_map:
                ai_rel = ai_map[key]
                # Vérifier si la description a été modifiée
                if (ai_rel.get('description', '').strip() !=
                        expert_rel.get('description', '').strip()):
                    deltas.append({
                        'type': 'relation_modified',
                        'ai_version': ai_rel,
                        'expert_version': expert_rel,
                        'confidence_before': ai_rel.get('confidence', 0.8)
                    })

        # Relations supprimées par l'expert
        for key, ai_rel in ai_map.items():
            if key not in expert_map:
                deltas.append({
                    'type': 'relation_removed',
                    'ai_version': ai_rel,
                    'expert_version': {},
                    'confidence_before': ai_rel.get('confidence', 0.8)
                })

        return deltas

    def _compare_entities(
            self,
            ai_entities: Dict[str, Any],
            expert_entities: Dict[str, Any]
    ) -> List[Dict]:
        """Compare les entités IA vs Expert"""
        deltas = []

        def normalize_entity_value(value):
            return value.strip().lower() if isinstance(value, str) else str(value).strip().lower()

        # Pour chaque type d'entité
        all_types = set(ai_entities.keys()) | set(expert_entities.keys())

        for entity_type in all_types:
            ai_items = self._extract_entity_values(ai_entities.get(entity_type, []))
            expert_items = self._extract_entity_values(expert_entities.get(entity_type, []))

            ai_set = {normalize_entity_value(item) for item in ai_items}
            expert_set = {normalize_entity_value(item) for item in expert_items}

            # Entités ajoutées par l'expert
            added = expert_set - ai_set
            if added:
                deltas.append({
                    'type': 'entity_added',
                    'ai_version': {'type': entity_type, 'items': list(ai_items)},
                    'expert_version': {'type': entity_type, 'items': list(expert_items), 'added': list(added)},
                    'confidence_before': 0.7
                })

            # Entités supprimées par l'expert
            removed = ai_set - expert_set
            if removed:
                deltas.append({
                    'type': 'entity_modified',
                    'ai_version': {'type': entity_type, 'items': list(ai_items)},
                    'expert_version': {'type': entity_type, 'items': list(expert_items), 'removed': list(removed)},
                    'confidence_before': 0.7
                })

        return deltas

    def _compare_qa(
            self,
            ai_qa: List[Dict],
            expert_qa: List[Dict]
    ) -> List[Dict]:
        """Compare les Q&A IA vs Expert"""
        deltas = []

        def normalize_text(text):
            return text.strip().lower() if isinstance(text, str) else ""

        # Index par question normalisée
        ai_map = {}
        for qa in ai_qa:
            if isinstance(qa, dict) and qa.get('question'):
                key = normalize_text(qa['question'])
                ai_map[key] = qa

        expert_map = {}
        for qa in expert_qa:
            if isinstance(qa, dict) and qa.get('question'):
                key = normalize_text(qa['question'])
                expert_map[key] = qa

        # Q&A ajoutées par l'expert
        for key, expert_qa_item in expert_map.items():
            if key not in ai_map:
                deltas.append({
                    'type': 'qa_added',
                    'ai_version': {},
                    'expert_version': expert_qa_item,
                    'confidence_before': 0.0
                })

        # Q&A modifiées par l'expert (réponse différente)
        for key, expert_qa_item in expert_map.items():
            if key in ai_map:
                ai_qa_item = ai_map[key]
                ai_answer = normalize_text(ai_qa_item.get('answer', ''))
                expert_answer = normalize_text(expert_qa_item.get('answer', ''))

                # Calculer la similarité
                similarity = SequenceMatcher(None, ai_answer, expert_answer).ratio()

                if similarity < 0.8:  # Réponse significativement différente
                    deltas.append({
                        'type': 'qa_corrected',
                        'ai_version': ai_qa_item,
                        'expert_version': expert_qa_item,
                        'confidence_before': ai_qa_item.get('confidence', 0.8),
                        'similarity': similarity
                    })

        return deltas

    def _extract_entity_values(self, entity_data):
        """Extrait les valeurs d'entités de différents formats"""
        if isinstance(entity_data, list):
            values = []
            for item in entity_data:
                if isinstance(item, str):
                    values.append(item)
                elif isinstance(item, dict):
                    values.append(item.get('value', ''))
            return [v for v in values if v]
        elif isinstance(entity_data, dict):
            items = entity_data.get('items', [])
            return self._extract_entity_values(items)
        return []

    def _update_learning_stats(self, expert_user, document, deltas):
        """Met à jour les statistiques d'apprentissage"""
        doc_type = getattr(document, 'doc_type', 'unknown')
        today = timezone.now().date()

        stats, created = ExpertLearningStats.objects.get_or_create(
            expert=expert_user,
            document_type=doc_type,
            period_start__date=today,
            defaults={
                'period_start': timezone.now(),
                'period_end': timezone.now(),
                'total_corrections': 0,
                'relations_improved': 0,
                'qa_improved': 0
            }
        )

        # Compter les corrections par type
        for delta in deltas:
            stats.total_corrections += 1
            if delta.delta_type.startswith('relation_'):
                stats.relations_improved += 1
            elif delta.delta_type.startswith('qa_'):
                stats.qa_improved += 1

        stats.save()

    def _generate_comparison_summary(self, deltas) -> Dict[str, Any]:
        """Génère un résumé lisible des changements"""
        summary = {
            'total_changes': len(deltas),
            'changes_by_type': {},
            'key_improvements': []
        }

        for delta in deltas:
            delta_type = delta.delta_type
            summary['changes_by_type'][delta_type] = summary['changes_by_type'].get(delta_type, 0) + 1

            # Ajouter des améliorations clés
            if delta_type == 'relation_added':
                rel = delta.expert_version
                summary['key_improvements'].append(
                    f"Ajout relation: {rel.get('source', {}).get('value', 'N/A')} → {rel.get('target', {}).get('value', 'N/A')}"
                )
            elif delta_type == 'qa_added':
                qa = delta.expert_version
                summary['key_improvements'].append(
                    f"Nouvelle Q&A: {qa.get('question', '')[:50]}..."
                )

        return summary

    def get_learning_history(
            self,
            document,
            limit: int = 20
    ) -> Dict[str, Any]:
        """Récupère l'historique d'apprentissage pour un document"""
        deltas = ExpertDelta.objects.filter(
            document=document,
            is_active=True
        ).order_by('-created_at')[:limit]

        history = []
        for delta in deltas:
            history.append({
                'id': delta.id,
                'type': delta.get_delta_type_display(),
                'expert': delta.expert.username,
                'created_at': delta.created_at.isoformat(),
                'summary': delta.correction_summary,
                'confidence_before': delta.confidence_before,
                'reused_count': delta.reused_count
            })

        return {
            'history': history,
            'total_corrections': len(history),
            'experts_involved': len(set(d['expert'] for d in history))
        }

    def enhance_with_learned_patterns(
            self,
            document,
            current_json: Dict[str, Any],
            document_context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Améliore le JSON actuel en utilisant les patterns appris
        """
        # Récupérer les corrections pertinentes
        relevant_deltas = ExpertDelta.objects.filter(
            document__doc_type=getattr(document, 'doc_type', ''),
            is_active=True,
            is_validated=True
        ).order_by('-reused_count', '-created_at')[:50]

        enhanced_json = current_json.copy()
        enhancements = []

        # Appliquer les patterns de relations
        for delta in relevant_deltas:
            if delta.delta_type == 'relation_added':
                # Vérifier si une relation similaire peut être appliquée
                similar_rel = self._find_similar_relation_pattern(
                    delta.expert_version,
                    enhanced_json,
                    document_context or {}
                )
                if similar_rel:
                    enhanced_json.setdefault('relations', []).append(similar_rel)
                    enhancements.append(f"Ajout relation apprise: {similar_rel.get('description', 'N/A')}")
                    delta.mark_reused()

        return {
            'enhanced_json': enhanced_json,
            'enhancements': enhancements,
            'patterns_applied': len(enhancements)
        }

    def _find_similar_relation_pattern(
            self,
            learned_relation: Dict[str, Any],
            current_json: Dict[str, Any],
            document_context: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Trouve si le pattern de relation appris peut être appliqué au JSON actuel
        """
        entities = current_json.get('entities', {})

        # Vérifier si les types d'entités nécessaires existent
        source_type = learned_relation.get('source', {}).get('type', '')
        target_type = learned_relation.get('target', {}).get('type', '')
        relation_type = learned_relation.get('type', '')

        if source_type in entities and target_type in entities:
            # Prendre les premières valeurs disponibles
            source_items = self._extract_entity_values(entities[source_type])
            target_items = self._extract_entity_values(entities[target_type])

            if source_items and target_items:
                # Créer une nouvelle relation basée sur le pattern appris
                return {
                    'type': relation_type,
                    'source': {'type': source_type, 'value': source_items[0]},
                    'target': {'type': target_type, 'value': target_items[0]},
                    'description': self.enricher.describe_relation_ai(
                        {'type': source_type, 'value': source_items[0]},
                        relation_type,
                        {'type': target_type, 'value': target_items[0]},
                        document_context
                    ),
                    'confidence': 0.85,
                    'learned_from': 'expert_pattern',
                    'created_at': timezone.now().isoformat()
                }

        return None