# extraction/services/ema_scraper.py - Version améliorée avec cache
import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime, timedelta
from urllib.parse import urlencode, quote
import time
import logging
import hashlib
from typing import Optional, Dict, List, Tuple
from django.core.cache import cache
from django.conf import settings

logger = logging.getLogger(__name__)


class EnhancedEMAScrapingService:
    """Service amélioré pour récupérer automatiquement les dates EMA avec cache"""

    def __init__(self):
        self.base_url = "https://www.ema.europa.eu"
        self.search_url = f"{self.base_url}/en/search"

        # Cache settings
        self.cache_timeout = getattr(settings, 'EMA_CACHE_TIMEOUT', 3600 * 24)  # 24h par défaut
        self.cache_prefix = 'ema_search'

        # Headers pour simuler un navigateur réel
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9,fr;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Cache-Control': 'max-age=0'
        }

        # Session pour maintenir les cookies
        self.session = requests.Session()
        self.session.headers.update(self.headers)

        # Configuration des timeouts et retry
        self.default_timeout = 30
        self.max_retries = 3
        self.retry_delay = 2

    def extract_publication_dates_automatic(self, document_title: str, use_cache: bool = True) -> Dict:
        """
        Extraire automatiquement les dates de publication EMA avec cache
        """
        try:
            logger.info(f"🔍 Extraction automatique EMA pour: {document_title}")

            # Vérifier le cache en premier
            if use_cache:
                cached_result = self._get_cached_result(document_title)
                if cached_result:
                    logger.info(f"📦 Résultat trouvé en cache pour: {document_title}")
                    return cached_result

            # 1. Nettoyer et optimiser le titre pour la recherche
            search_title = self._optimize_search_title(document_title)
            logger.info(f"🔧 Titre optimisé pour recherche: {search_title}")

            # 2. Effectuer la recherche sur EMA avec retry
            search_results = self._perform_ema_search_with_retry(search_title)

            if not search_results:
                logger.warning(f"⚠️ Aucun résultat trouvé pour '{document_title}'")
                result = self._get_empty_result()
                self._cache_result(document_title, result)
                return result

            # 3. Analyser les résultats pour trouver le meilleur match
            best_match = self._find_best_match(document_title, search_results)

            if not best_match:
                logger.warning(f"⚠️ Aucun match pertinent pour '{document_title}'")
                result = self._get_empty_result()
                self._cache_result(document_title, result)
                return result

            # 4. Extraire les dates du meilleur résultat
            dates_info = self._extract_dates_from_result(best_match)

            # 5. Si pas de dates dans les résultats, aller sur la page détaillée
            if not dates_info.get('first_published') or not dates_info.get('last_updated'):
                if best_match.get('url'):
                    detailed_dates = self._extract_dates_from_detail_page_with_retry(best_match['url'])
                    dates_info.update(detailed_dates)

            # 6. Compiler le résultat final
            result = {
                'success': True,
                'first_published': dates_info.get('first_published'),
                'last_updated': dates_info.get('last_updated'),
                'ema_url': best_match.get('url'),
                'ema_title': best_match.get('title'),
                'ema_reference': best_match.get('reference'),
                'similarity_score': best_match.get('similarity', 0),
                'search_results_count': len(search_results),
                'cached': False
            }

            # Mettre en cache le résultat
            self._cache_result(document_title, result)

            logger.info(f"✅ Extraction réussie - First: {result['first_published']}, Last: {result['last_updated']}")
            return result

        except requests.exceptions.RequestException as e:
            logger.error(f"🌐 Erreur réseau lors de l'extraction EMA: {e}")
            return self._get_empty_result(error=f"Erreur réseau: {str(e)}")
        except Exception as e:
            logger.error(f"💥 Erreur inattendue extraction automatique EMA: {e}")
            return self._get_empty_result(error=str(e))

    def _get_cache_key(self, document_title: str) -> str:
        """Générer une clé de cache unique pour le titre"""
        # Normaliser le titre et créer un hash
        normalized_title = self._optimize_search_title(document_title).lower()
        title_hash = hashlib.md5(normalized_title.encode()).hexdigest()
        return f"{self.cache_prefix}:{title_hash}"

    def _get_cached_result(self, document_title: str) -> Optional[Dict]:
        """Récupérer le résultat depuis le cache"""
        try:
            cache_key = self._get_cache_key(document_title)
            cached_data = cache.get(cache_key)
            if cached_data:
                cached_data['cached'] = True
                return cached_data
            return None
        except Exception as e:
            logger.warning(f"⚠️ Erreur lecture cache: {e}")
            return None

    def _cache_result(self, document_title: str, result: Dict):
        """Mettre en cache le résultat"""
        try:
            cache_key = self._get_cache_key(document_title)
            # Ne pas cacher le flag 'cached'
            cache_data = {k: v for k, v in result.items() if k != 'cached'}
            cache.set(cache_key, cache_data, self.cache_timeout)
            logger.debug(f"📦 Résultat mis en cache pour: {document_title}")
        except Exception as e:
            logger.warning(f"⚠️ Erreur mise en cache: {e}")

    def _perform_ema_search_with_retry(self, search_term: str) -> List[Dict]:
        """Effectuer la recherche sur le site EMA avec retry"""
        last_exception = None

        for attempt in range(self.max_retries):
            try:
                logger.info(f"🔄 Tentative {attempt + 1}/{self.max_retries} pour la recherche EMA")

                # Paramètres de recherche optimisés
                search_params = {
                    'search_api_fulltext': search_term,
                    'sort_by': 'search_api_relevance',
                    'sort_order': 'DESC',
                    'f[0]': 'ema_search_entity_is_document%3ADocument'
                }

                search_url = f"{self.search_url}?{urlencode(search_params)}"
                logger.debug(f"🔗 URL de recherche: {search_url}")

                response = self.session.get(search_url, timeout=self.default_timeout)
                response.raise_for_status()

                soup = BeautifulSoup(response.content, 'html.parser')
                results = self._parse_search_results_enhanced(soup)

                if results:
                    logger.info(f"✅ Recherche réussie: {len(results)} résultats trouvés")
                    return results
                else:
                    logger.warning(f"⚠️ Aucun résultat trouvé (tentative {attempt + 1})")

            except requests.exceptions.Timeout as e:
                last_exception = e
                logger.warning(f"⏱️ Timeout lors de la recherche (tentative {attempt + 1}): {e}")
            except requests.exceptions.RequestException as e:
                last_exception = e
                logger.warning(f"🌐 Erreur réseau (tentative {attempt + 1}): {e}")
            except Exception as e:
                last_exception = e
                logger.error(f"💥 Erreur inattendue (tentative {attempt + 1}): {e}")

            # Attendre avant le retry (sauf à la dernière tentative)
            if attempt < self.max_retries - 1:
                wait_time = self.retry_delay * (attempt + 1)
                logger.info(f"⏳ Attente de {wait_time}s avant retry...")
                time.sleep(wait_time)

        # Si toutes les tentatives ont échoué
        logger.error(f"❌ Échec de toutes les tentatives de recherche EMA: {last_exception}")
        return []

    def _extract_dates_from_detail_page_with_retry(self, document_url: str) -> Dict:
        """Extraire les dates depuis la page détaillée avec retry"""
        last_exception = None

        for attempt in range(self.max_retries):
            try:
                logger.info(f"📄 Extraction dates page détaillée (tentative {attempt + 1}): {document_url}")

                response = self.session.get(document_url, timeout=self.default_timeout)
                response.raise_for_status()

                soup = BeautifulSoup(response.content, 'html.parser')
                dates_info = {}

                # Chercher les dates dans différents patterns
                page_text = soup.get_text()

                # Pattern 1: "First published: DD/MM/YYYY"
                first_match = re.search(r'First published:\s*(\d{2}/\d{2}/\d{4})', page_text, re.IGNORECASE)
                if first_match:
                    try:
                        dates_info['first_published'] = datetime.strptime(first_match.group(1), '%d/%m/%Y').date()
                    except ValueError:
                        pass

                # Pattern 2: "Last updated: DD/MM/YYYY"
                last_match = re.search(r'Last updated:\s*(\d{2}/\d{2}/\d{4})', page_text, re.IGNORECASE)
                if last_match:
                    try:
                        dates_info['last_updated'] = datetime.strptime(last_match.group(1), '%d/%m/%Y').date()
                    except ValueError:
                        pass

                logger.info(f"✅ Dates extraites page détaillée: {dates_info}")
                return dates_info

            except requests.exceptions.Timeout as e:
                last_exception = e
                logger.warning(f"⏱️ Timeout page détaillée (tentative {attempt + 1}): {e}")
            except requests.exceptions.RequestException as e:
                last_exception = e
                logger.warning(f"🌐 Erreur réseau page détaillée (tentative {attempt + 1}): {e}")
            except Exception as e:
                last_exception = e
                logger.error(f"💥 Erreur page détaillée (tentative {attempt + 1}): {e}")

            # Attendre avant le retry
            if attempt < self.max_retries - 1:
                wait_time = self.retry_delay * (attempt + 1)
                logger.info(f"⏳ Attente de {wait_time}s avant retry page détaillée...")
                time.sleep(wait_time)

        logger.error(f"❌ Échec extraction page détaillée après {self.max_retries} tentatives: {last_exception}")
        return {}

    # === Méthodes existantes (inchangées) ===
    def _optimize_search_title(self, title: str) -> str:
        """Optimiser le titre pour la recherche EMA (inchangée)"""
        clean_title = re.sub(r'[^\w\s-]', ' ', title)
        clean_title = re.sub(r'\s+', ' ', clean_title).strip()

        priority_keywords = {
            'european', 'medicines', 'agency', 'ema', 'guideline', 'guidance',
            'recommendation', 'procedural', 'advice', 'assessment', 'opinion',
            'draft', 'final', 'centralised', 'procedure', 'post-authorisation'
        }

        exclude_words = {'the', 'of', 'for', 'and', 'or', 'in', 'on', 'at', 'to', 'a', 'an'}

        words = clean_title.lower().split()
        priority_words = [w for w in words if w in priority_keywords]
        normal_words = [w for w in words if w not in priority_keywords and w not in exclude_words and len(w) > 2]

        search_words = priority_words + normal_words[:6]
        return ' '.join(search_words)

    def _parse_search_results_enhanced(self, soup: BeautifulSoup) -> List[Dict]:
        """Parser les résultats de recherche (inchangée)"""
        results = []

        try:
            result_containers = soup.find_all(['div', 'article'],
                                              class_=re.compile(r'views-row|search-result|result-item'))

            for container in result_containers:
                result = {}

                # Titre et lien
                title_link = container.find('a', href=True)
                if title_link:
                    result['title'] = title_link.get_text(strip=True)
                    href = title_link.get('href')
                    if href.startswith('/'):
                        result['url'] = f"{self.base_url}{href}"
                    else:
                        result['url'] = href

                # Référence du document
                ref_elem = container.find(text=re.compile(r'Reference Number:|EMEA-|EMA/'))
                if ref_elem:
                    ref_text = ref_elem.parent.get_text() if ref_elem.parent else str(ref_elem)
                    ref_match = re.search(r'(EMEA-[^\s]+|EMA/[^\s]+)', ref_text)
                    if ref_match:
                        result['reference'] = ref_match.group(1)

                # Dates directement dans les résultats
                self._extract_dates_from_text(container.get_text(), result)

                # Type de document
                doc_type = container.find(['span', 'div'], class_=re.compile(r'type|category'))
                if doc_type:
                    result['document_type'] = doc_type.get_text(strip=True)

                # Snippet/description
                snippet = container.find(['p', 'div'], class_=re.compile(r'snippet|summary|description|field-content'))
                if snippet:
                    result['snippet'] = snippet.get_text(strip=True)[:300]

                if result.get('title') and result.get('url'):
                    results.append(result)

            logger.info(f"📊 Total de {len(results)} résultats parsés")

        except Exception as e:
            logger.error(f"💥 Erreur lors du parsing des résultats: {e}")

        return results

    def _extract_dates_from_text(self, text: str, result: Dict):
        """Extraire les dates depuis le texte (inchangée)"""
        first_published_pattern = r'First published:\s*(\d{2}/\d{2}/\d{4})'
        last_updated_pattern = r'Last updated:\s*(\d{2}/\d{2}/\d{4})'

        first_match = re.search(first_published_pattern, text, re.IGNORECASE)
        if first_match:
            try:
                result['first_published'] = datetime.strptime(first_match.group(1), '%d/%m/%Y').date()
            except ValueError:
                pass

        last_match = re.search(last_updated_pattern, text, re.IGNORECASE)
        if last_match:
            try:
                result['last_updated'] = datetime.strptime(last_match.group(1), '%d/%m/%Y').date()
            except ValueError:
                pass

    def _find_best_match(self, original_title: str, search_results: List[Dict]) -> Optional[Dict]:
        """Trouver le meilleur match (inchangée)"""
        if not search_results:
            return None

        scored_results = []
        for result in search_results:
            similarity = self._calculate_enhanced_similarity(original_title, result.get('title', ''))
            result['similarity'] = similarity
            scored_results.append(result)

        scored_results.sort(key=lambda x: x['similarity'], reverse=True)

        best_result = scored_results[0]
        if best_result['similarity'] >= 0.3:
            logger.info(f"✅ Meilleur match: {best_result['title']} (similarité: {best_result['similarity']:.2f})")
            return best_result

        logger.warning(f"⚠️ Aucun match avec similarité suffisante (meilleur: {best_result['similarity']:.2f})")
        return None

    def _calculate_enhanced_similarity(self, title1: str, title2: str) -> float:
        """Calculer la similarité améliorée (inchangée)"""
        if not title1 or not title2:
            return 0.0

        t1_words = set(re.findall(r'\w+', title1.lower()))
        t2_words = set(re.findall(r'\w+', title2.lower()))

        if not t1_words or not t2_words:
            return 0.0

        important_words = {'european', 'medicines', 'agency', 'guideline', 'procedural', 'advice', 'centralised'}

        intersection = len(t1_words.intersection(t2_words))
        union = len(t1_words.union(t2_words))
        base_similarity = intersection / union if union > 0 else 0.0

        important_matches = len(t1_words.intersection(t2_words).intersection(important_words))
        bonus = important_matches * 0.1

        return min(1.0, base_similarity + bonus)

    def _extract_dates_from_result(self, result: Dict) -> Dict:
        """Extraire les dates depuis un résultat (inchangée)"""
        dates_info = {}

        if 'first_published' in result:
            dates_info['first_published'] = result['first_published']
        if 'last_updated' in result:
            dates_info['last_updated'] = result['last_updated']

        if result.get('snippet'):
            self._extract_dates_from_text(result['snippet'], dates_info)

        return dates_info

    def _get_empty_result(self, error: str = None) -> Dict:
        """Retourner un résultat vide (inchangée)"""
        return {
            'success': False,
            'first_published': None,
            'last_updated': None,
            'ema_url': '',
            'ema_title': '',
            'ema_reference': '',
            'similarity_score': 0,
            'search_results_count': 0,
            'error': error,
            'cached': False
        }

    def clear_cache_for_title(self, document_title: str):
        """Vider le cache pour un titre spécifique"""
        try:
            cache_key = self._get_cache_key(document_title)
            cache.delete(cache_key)
            logger.info(f"🗑️ Cache vidé pour: {document_title}")
        except Exception as e:
            logger.warning(f"⚠️ Erreur vidage cache: {e}")

    def clear_all_cache(self):
        """Vider tout le cache EMA (attention: peut être lent)"""
        try:
            # Cette méthode dépend du backend de cache utilisé
            if hasattr(cache, 'delete_pattern'):
                cache.delete_pattern(f"{self.cache_prefix}:*")
            else:
                logger.warning("⚠️ Vidage global du cache non supporté par le backend")
        except Exception as e:
            logger.warning(f"⚠️ Erreur vidage global cache: {e}")