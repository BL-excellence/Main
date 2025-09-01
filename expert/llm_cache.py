# expert/llm_cache.py
import hashlib
import json
import time
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from django.core.cache import cache
from django.conf import settings
import logging

logger = logging.getLogger(__name__)


class LLMCacheManager:
    """Gestionnaire de cache intelligent pour les appels LLM"""

    def __init__(self):
        self.cache_timeout = getattr(settings, 'LLM_CACHE_TIMEOUT', 3600 * 24)  # 24h par défaut
        self.rate_limit_window = getattr(settings, 'LLM_RATE_LIMIT_WINDOW', 3600)  # 1h
        self.rate_limit_calls = getattr(settings, 'LLM_RATE_LIMIT_CALLS', 100)  # 100 calls/h

    def _generate_cache_key(self, operation: str, **kwargs) -> str:
        """Génère une clé de cache basée sur l'opération et les paramètres"""
        # Créer un hash des paramètres pour une clé unique et stable
        params_str = json.dumps(kwargs, sort_keys=True, ensure_ascii=False)
        params_hash = hashlib.md5(params_str.encode()).hexdigest()[:12]
        return f"llm_cache:{operation}:{params_hash}"

    def _get_rate_limit_key(self, user_id: Optional[str] = None) -> str:
        """Génère une clé pour le rate limiting"""
        user_part = user_id or 'anonymous'
        return f"llm_rate_limit:{user_part}"

    def check_rate_limit(self, user_id: Optional[str] = None) -> tuple[bool, int]:
        """
        Vérifie si l'utilisateur peut faire un appel LLM
        Returns: (can_call, remaining_calls)
        """
        rate_key = self._get_rate_limit_key(user_id)

        # Récupérer le compteur actuel
        current_calls = cache.get(rate_key, 0)

        if current_calls >= self.rate_limit_calls:
            return False, 0

        # Incrémenter le compteur
        cache.set(rate_key, current_calls + 1, self.rate_limit_window)

        return True, self.rate_limit_calls - (current_calls + 1)

    def get_cached_response(self, operation: str, **kwargs) -> Optional[Any]:
        """Récupère une réponse en cache"""
        cache_key = self._generate_cache_key(operation, **kwargs)

        try:
            cached_data = cache.get(cache_key)
            if cached_data:
                # Vérifier la validité temporelle si nécessaire
                if isinstance(cached_data, dict) and 'timestamp' in cached_data:
                    timestamp = datetime.fromisoformat(cached_data['timestamp'])
                    if datetime.now() - timestamp > timedelta(seconds=self.cache_timeout):
                        cache.delete(cache_key)
                        return None
                    return cached_data.get('response')

                return cached_data

        except Exception as e:
            logger.warning(f"Erreur lors de la récupération du cache: {e}")

        return None

    def set_cached_response(self, operation: str, response: Any, **kwargs) -> None:
        """Met en cache une réponse"""
        cache_key = self._generate_cache_key(operation, **kwargs)

        try:
            # Encapsuler avec métadonnées
            cached_data = {
                'response': response,
                'timestamp': datetime.now().isoformat(),
                'operation': operation
            }

            cache.set(cache_key, cached_data, self.cache_timeout)

        except Exception as e:
            logger.warning(f"Erreur lors de la mise en cache: {e}")

    def invalidate_pattern(self, pattern: str) -> int:
        """Invalide tous les caches correspondant au pattern"""
        try:
            # Note: Cette implémentation dépend du backend de cache
            # Pour Redis, on pourrait utiliser SCAN avec pattern
            # Pour Memcached, il faut maintenir un index des clés

            # Implémentation basique pour développement
            # En production, utiliser Redis avec SCAN
            if hasattr(cache, 'delete_pattern'):
                return cache.delete_pattern(f"llm_cache:{pattern}*")

            logger.info(f"Invalidation de pattern non supportée pour ce backend de cache")
            return 0

        except Exception as e:
            logger.warning(f"Erreur lors de l'invalidation: {e}")
            return 0


class CachedLLMClient:
    """Client LLM avec cache intelligent"""

    def __init__(self, base_client, user_id: Optional[str] = None):
        self.client = base_client
        self.cache_manager = LLMCacheManager()
        self.user_id = user_id

        # Configuration des opérations cachables
        self.cacheable_operations = {
            'entity_classification': 3600 * 48,  # 48h - Stable
            'relation_inference': 3600 * 24,  # 24h - Assez stable
            'semantic_summary': 3600 * 12,  # 12h - Peut changer
            'qa_generation': 3600 * 6,  # 6h - Variable
            'relation_description': 3600 * 72,  # 72h - Très stable
        }

    def _should_cache(self, operation: str) -> bool:
        """Détermine si une opération doit être cachée"""
        return operation in self.cacheable_operations

    def _get_cache_timeout(self, operation: str) -> int:
        """Récupère le timeout de cache pour une opération"""
        return self.cacheable_operations.get(operation, 3600)

    def chat_json_cached(self, operation: str, messages: List[Dict], **kwargs) -> Optional[Dict]:
        """Appel chat_json avec cache"""
        # Vérifier le rate limiting
        can_call, remaining = self.cache_manager.check_rate_limit(self.user_id)
        if not can_call:
            logger.warning(f"Rate limit atteint pour {self.user_id}")
            return None

        # Construire les paramètres de cache
        cache_params = {
            'messages': messages,
            'model': getattr(self.client, 'model', 'unknown'),
            'temperature': getattr(self.client, 'temperature', 0.2),
            **kwargs
        }

        # Vérifier le cache si l'opération est cachable
        if self._should_cache(operation):
            cached_response = self.cache_manager.get_cached_response(operation, **cache_params)
            if cached_response:
                logger.debug(f"Cache hit pour {operation}")
                return cached_response

        # Faire l'appel réel au LLM
        try:
            response = self.client.chat_json(messages, **kwargs)

            # Mettre en cache si applicable
            if response and self._should_cache(operation):
                # Utiliser le timeout spécifique à l'opération
                original_timeout = self.cache_manager.cache_timeout
                self.cache_manager.cache_timeout = self._get_cache_timeout(operation)

                self.cache_manager.set_cached_response(operation, response, **cache_params)

                # Restaurer le timeout original
                self.cache_manager.cache_timeout = original_timeout

            return response

        except Exception as e:
            logger.error(f"Erreur LLM pour {operation}: {e}")
            return None

    def chat_text_cached(self, operation: str, messages: List[Dict], **kwargs) -> Optional[str]:
        """Appel chat_text avec cache"""
        # Logique similaire à chat_json_cached
        can_call, remaining = self.cache_manager.check_rate_limit(self.user_id)
        if not can_call:
            logger.warning(f"Rate limit atteint pour {self.user_id}")
            return None

        cache_params = {
            'messages': messages,
            'model': getattr(self.client, 'model', 'unknown'),
            'temperature': getattr(self.client, 'temperature', 0.2),
            **kwargs
        }

        if self._should_cache(operation):
            cached_response = self.cache_manager.get_cached_response(operation, **cache_params)
            if cached_response:
                return cached_response

        try:
            response = self.client.chat_text(messages, **kwargs)

            if response and self._should_cache(operation):
                original_timeout = self.cache_manager.cache_timeout
                self.cache_manager.cache_timeout = self._get_cache_timeout(operation)

                self.cache_manager.set_cached_response(operation, response, **cache_params)

                self.cache_manager.cache_timeout = original_timeout

            return response

        except Exception as e:
            logger.error(f"Erreur LLM pour {operation}: {e}")
            return None


class BatchLLMProcessor:
    """Processeur batch pour optimiser les appels LLM multiples"""

    def __init__(self, cached_client: CachedLLMClient):
        self.client = cached_client
        self.batch_size = 5  # Nombre d'éléments à traiter ensemble

    def batch_classify_entities(self, entities: List[Dict]) -> List[Dict]:
        """Classification par batch d'entités"""
        results = []

        # Traiter par chunks
        for i in range(0, len(entities), self.batch_size):
            batch = entities[i:i + self.batch_size]

            # Créer le prompt pour le batch
            system_prompt = (
                "Tu analyses une liste d'entités pharmaceutiques et retournes "
                "une classification JSON pour chacune."
            )

            user_prompt = {
                "entities": batch,
                "task": "Classifier chaque entité avec type thérapeutique, "
                        "classe pharmacologique, et propriétés."
            }

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(user_prompt, ensure_ascii=False)}
            ]

            # Appel avec cache
            batch_results = self.client.chat_json_cached(
                'entity_classification_batch',
                messages,
                max_tokens=1000
            )

            if batch_results and 'classifications' in batch_results:
                results.extend(batch_results['classifications'])
            else:
                # Fallback : traitement individuel
                for entity in batch:
                    individual_result = self._classify_single_entity(entity)
                    results.append(individual_result)

        return results

    def _classify_single_entity(self, entity: Dict) -> Dict:
        """Classification individuelle en cas d'échec du batch"""
        # Implémentation de fallback
        return {
            'entity': entity,
            'classification': 'unknown',
            'confidence': 0.3,
            'source': 'fallback'
        }


# Intégration dans les vues existantes
def get_cached_llm_client(request) -> CachedLLMClient:
    """Factory pour créer un client LLM avec cache"""
    from expert.llm_client import LLMClient

    base_client = LLMClient()
    user_id = str(request.user.id) if request.user.is_authenticated else None

    return CachedLLMClient(base_client, user_id)


# Middleware pour monitoring des performances LLM
class LLMPerformanceMiddleware:
    """Middleware pour monitorer les performances des appels LLM"""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Marquer le début de la requête
        start_time = time.time()

        response = self.get_response(request)

        # Enregistrer les métriques si c'est une vue avec LLM
        if hasattr(request, '_llm_calls_made'):
            duration = time.time() - start_time

            # Log des performances (peut être étendu vers Prometheus/Grafana)
            logger.info(
                f"LLM Performance - User: {getattr(request.user, 'id', 'anon')}, "
                f"Calls: {request._llm_calls_made}, Duration: {duration:.2f}s, "
                f"Path: {request.path}"
            )

        return response