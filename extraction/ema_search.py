# extraction/ema_search.py - Version ultra-robuste de la recherche EMA
import requests
import time
import re
import logging
from bs4 import BeautifulSoup
from urllib.parse import quote_plus, urljoin
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)


class RobustEMASearcher:
    """Moteur de recherche EMA ultra-robuste avec multiples stratégies de fallback"""

    def __init__(self):
        self.base_url = "https://www.ema.europa.eu"
        self.search_url = f"{self.base_url}/en/search"
        self.session = self._create_session()

    def _create_session(self) -> requests.Session:
        """Crée une session avec des headers réalistes"""
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9,fr;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'DNT': '1',
            'Cache-Control': 'max-age=0'
        })
        return session

    def normalize_title(self, title: str) -> str:
        """Normalise un titre pour améliorer la correspondance"""
        if not title:
            return ""

        # Convertir en minuscules et nettoyer
        normalized = re.sub(r'[^\w\s-]', ' ', title.lower())
        normalized = re.sub(r'\s+', ' ', normalized).strip()

        # Supprimer les mots vides courants
        stop_words = {
            'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by',
            'from', 'a', 'an', 'as', 'how', 'what', 'where', 'when', 'why', 'which', 'who',
            'le', 'la', 'les', 'de', 'du', 'des', 'et', 'à', 'dans', 'pour', 'sur', 'avec'
        }

        words = [w for w in normalized.split() if w not in stop_words and len(w) > 2]
        return ' '.join(words)

    def calculate_similarity(self, text1: str, text2: str) -> float:
        """Calcule la similarité entre deux textes de manière robuste"""
        if not text1 or not text2:
            return 0.0

        norm1 = self.normalize_title(text1)
        norm2 = self.normalize_title(text2)

        if not norm1 or not norm2:
            return 0.0

        # Similarité de séquence
        seq_similarity = SequenceMatcher(None, norm1, norm2).ratio()

        # Similarité de mots
        words1 = set(norm1.split())
        words2 = set(norm2.split())

        if not words1 and not words2:
            return 1.0
        if not words1 or not words2:
            return 0.0

        intersection = len(words1.intersection(words2))
        union = len(words1.union(words2))
        word_similarity = intersection / union if union > 0 else 0.0

        # Combinaison pondérée
        return (seq_similarity * 0.3) + (word_similarity * 0.7)

    def generate_search_queries(self, title: str) -> List[str]:
        """Génère plusieurs variantes de recherche pour maximiser les chances de succès"""
        queries = []

        # 1. Titre exact entre guillemets
        queries.append(f'"{title}"')

        # 2. Titre sans guillemets
        queries.append(title)

        # 3. Mots-clés principaux (mots de plus de 4 caractères)
        important_words = [w for w in title.split() if len(w) > 4]
        if important_words:
            queries.append(' '.join(important_words[:4]))

        # 4. Première partie du titre
        words = title.split()
        if len(words) > 3:
            queries.append(' '.join(words[:len(words) // 2]))

        # 5. Acronymes et termes techniques
        acronyms = re.findall(r'\b[A-Z]{2,}\b', title)
        technical_terms = re.findall(
            r'\b(guidance|guideline|procedure|protocol|meeting|briefing|application|authorization|approval)\b', title,
            re.IGNORECASE)

        if acronyms:
            queries.append(' '.join(acronyms))

        if technical_terms:
            queries.append(' '.join(technical_terms))

        # 6. Mots-clés médicaux/pharmaceutiques
        medical_keywords = re.findall(
            r'\b(medicine|drug|therapeutic|clinical|medical|pharmaceutical|treatment|vaccine|therapy)\b', title,
            re.IGNORECASE)
        if medical_keywords:
            queries.append(' '.join(medical_keywords))

        # 7. Dernière tentative avec juste les mots les plus longs
        long_words = [w for w in title.split() if len(w) > 6]
        if long_words:
            queries.append(' '.join(long_words[:3]))

        # Retourner les queries uniques
        unique_queries = []
        for q in queries:
            if q and q not in unique_queries:
                unique_queries.append(q)

        return unique_queries[:8]  # Limiter à 8 tentatives max

    def search_ema_page(self, query: str, retry_count: int = 3) -> Optional[BeautifulSoup]:
        """Effectue une recherche sur le site EMA avec retry automatique"""
        for attempt in range(retry_count):
            try:
                logger.info(f"🔍 Recherche EMA (tentative {attempt + 1}): '{query}'")

                params = {
                    'search_api_fulltext': query,
                    'f[0]': 'ema_search_entity_is_document:Document'
                }

                response = self.session.get(
                    self.search_url,
                    params=params,
                    timeout=30,
                    allow_redirects=True
                )

                response.raise_for_status()

                # Vérifier que c'est bien du HTML
                if 'text/html' not in response.headers.get('content-type', ''):
                    logger.warning(f"⚠️ Réponse non-HTML reçue: {response.headers.get('content-type')}")
                    time.sleep(2)
                    continue

                soup = BeautifulSoup(response.text, 'html.parser')

                # Vérifier que la page est valide
                if self._is_valid_search_page(soup):
                    logger.debug(f"✅ Page de recherche valide reçue")
                    return soup
                else:
                    logger.warning(f"⚠️ Page de recherche invalide, retry...")
                    time.sleep(2)
                    continue

            except requests.exceptions.Timeout:
                logger.warning(f"⏰ Timeout pour la recherche (tentative {attempt + 1})")
                time.sleep(3)
            except requests.exceptions.RequestException as e:
                logger.warning(f"🌐 Erreur réseau (tentative {attempt + 1}): {e}")
                time.sleep(3)
            except Exception as e:
                logger.error(f"❌ Erreur inattendue (tentative {attempt + 1}): {e}")
                time.sleep(3)

        logger.error(f"❌ Échec de la recherche après {retry_count} tentatives")
        return None

    def _is_valid_search_page(self, soup: BeautifulSoup) -> bool:
        """Vérifie que la page de recherche est valide"""
        # Vérifier la présence d'éléments caractéristiques
        indicators = [
            soup.find('title'),
            soup.find('body'),
            soup.find(attrs={'class': lambda x: x and 'search' in x.lower()}) if soup.find(
                attrs={'class': lambda x: x and 'search' in x.lower()}) else soup.find('form'),
        ]

        return any(indicators)

    def extract_search_results(self, soup: BeautifulSoup) -> List[Dict]:
        """Extrait les résultats de recherche avec multiples sélecteurs de fallback"""
        results = []

        # Multiples sélecteurs CSS pour s'adapter aux changements de structure
        result_selectors = [
            # Sélecteurs spécifiques EMA
            '.search-results .search-result',
            '.view-content .views-row',
            '.item-list .item',
            '.bcl-listing .row > div[class*="col"]',

            # Sélecteurs génériques
            '[class*="search-result"]',
            '[class*="result-item"]',
            '.views-row',
            '.list-item',

            # Fallback très large
            'article',
            '.content [class*="item"]',
            'div[class*="search"] > div',
        ]

        found_results = []
        for selector in result_selectors:
            try:
                elements = soup.select(selector)
                if elements:
                    # Filtrer les éléments qui semblent être de vrais résultats
                    valid_elements = []
                    for elem in elements:
                        if self._is_valid_result_element(elem):
                            valid_elements.append(elem)

                    if valid_elements:
                        logger.debug(f"✅ Trouvé {len(valid_elements)} résultats avec sélecteur: {selector}")
                        found_results = valid_elements
                        break
            except Exception as e:
                logger.debug(f"⚠️ Erreur avec sélecteur {selector}: {e}")
                continue

        # Extraire les informations de chaque résultat
        for i, result_elem in enumerate(found_results[:10]):  # Limiter à 10 résultats
            try:
                result_data = self._extract_result_data(result_elem)
                if result_data and result_data.get('title'):
                    results.append(result_data)
                    logger.debug(f"📄 Résultat {i + 1}: {result_data['title'][:50]}...")
            except Exception as e:
                logger.warning(f"⚠️ Erreur extraction résultat {i + 1}: {e}")
                continue

        logger.info(f"📊 {len(results)} résultats extraits au total")
        return results

    def _is_valid_result_element(self, elem) -> bool:
        """Vérifie qu'un élément semble être un vrai résultat de recherche"""
        try:
            # Doit contenir du texte
            text_content = elem.get_text(strip=True)
            if len(text_content) < 20:
                return False

            # Doit contenir un lien
            links = elem.find_all('a', href=True)
            if not links:
                return False

            # Ne doit pas être un élément de navigation
            text_lower = text_content.lower()
            navigation_indicators = [
                'home', 'search', 'filter', 'sort', 'page', 'next', 'previous',
                'menu', 'navigation', 'breadcrumb', 'footer', 'header'
            ]

            if any(indicator in text_lower for indicator in navigation_indicators):
                return False

            # Doit avoir une taille raisonnable
            if len(text_content) > 2000:  # Trop long, probablement pas un résultat individuel
                return False

            return True

        except Exception:
            return False

    def _extract_result_data(self, result_elem) -> Optional[Dict]:
        """Extrait les données d'un résultat de recherche"""
        try:
            data = {
                'title': '',
                'url': '',
                'description': '',
                'date': None,
                'reference': '',
                'metadata': {}
            }

            # Extraction du titre et URL avec multiples stratégies
            title_link = None
            title_selectors = [
                'h3 a', 'h2 a', 'h4 a', 'h1 a',
                '.title a', '.heading a',
                'a[href*="/en/"]',
                '.field--name-title a',
                '.node-title a'
            ]

            for selector in title_selectors:
                title_link = result_elem.select_one(selector)
                if title_link and title_link.get_text(strip=True):
                    break

            # Si pas de lien de titre trouvé, prendre le premier lien significatif
            if not title_link:
                all_links = result_elem.find_all('a', href=True)
                for link in all_links:
                    text = link.get_text(strip=True)
                    href = link.get('href', '')
                    if (text and len(text) > 10 and
                            ('/en/' in href or href.endswith('.pdf')) and
                            not any(skip in text.lower() for skip in ['view', 'download', 'read more'])):
                        title_link = link
                        break

            if title_link:
                data['title'] = title_link.get_text(strip=True)
                href = title_link.get('href', '')
                if href:
                    if href.startswith('http'):
                        data['url'] = href
                    else:
                        data['url'] = urljoin(self.base_url, href)

            # Extraction de la description
            desc_selectors = [
                '.description', '.summary', '.field--name-body',
                '.field--name-field-meta-description', '.content',
                'p', '.excerpt'
            ]

            for selector in desc_selectors:
                desc_elem = result_elem.select_one(selector)
                if desc_elem:
                    desc_text = desc_elem.get_text(strip=True)
                    if desc_text and len(desc_text) > 20:
                        data['description'] = desc_text[:300]
                        break

            # Extraction des métadonnées (dates, références)
            self._extract_metadata(result_elem, data)

            return data if data['title'] else None

        except Exception as e:
            logger.warning(f"⚠️ Erreur extraction données résultat: {e}")
            return None

    def _extract_metadata(self, result_elem, data: Dict):
        """Extrait les métadonnées d'un résultat"""
        try:
            text_content = result_elem.get_text()

            # Extraction des dates
            date_patterns = [
                r'\b(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{4})\b',
                r'\b(\d{4}[\/\-\.]\d{1,2}[\/\-\.]\d{1,2})\b',
                r'\b(\d{1,2}\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{4})\b'
            ]

            for pattern in date_patterns:
                matches = re.findall(pattern, text_content, re.IGNORECASE)
                if matches:
                    data['date'] = matches[0] if isinstance(matches[0], str) else matches[0][0]
                    break

            # Extraction des références EMA
            ref_patterns = [
                r'\b(EMA[\/\-]\d+[\/\-]\d+)\b',
                r'\b(EMEA[\/\-]\d+[\/\-]\d+)\b',
                r'\b([A-Z]{3,}[\/\-]\d+[\/\-]\d+)\b'
            ]

            for pattern in ref_patterns:
                matches = re.findall(pattern, text_content)
                if matches:
                    data['reference'] = matches[0]
                    break

            # Extraction d'autres métadonnées
            if 'KB' in text_content and 'PDF' in text_content:
                size_match = re.search(r'(\d+(?:\.\d+)?)\s*KB', text_content)
                if size_match:
                    data['metadata']['file_size'] = f"{size_match.group(1)} KB"

            if 'guidance' in text_content.lower():
                data['metadata']['document_type'] = 'guidance'
            elif 'directive' in text_content.lower():
                data['metadata']['document_type'] = 'directive'

        except Exception as e:
            logger.debug(f"⚠️ Erreur extraction métadonnées: {e}")

    def get_document_details(self, document_url: str) -> Dict:
        """Récupère les détails complets d'un document depuis sa page"""
        try:
            logger.debug(f"📄 Récupération détails: {document_url}")

            response = self.session.get(document_url, timeout=20)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')

            details = {
                'original_publication_date': None,
                'ema_publication_date': None,
                'ema_reference': '',
                'ema_source_url': document_url,
                'ema_title': '',
                'additional_info': {}
            }

            # Titre de la page
            title_selectors = ['h1', '.page-title', '.field--name-title', 'title']
            for selector in title_selectors:
                title_elem = soup.select_one(selector)
                if title_elem and title_elem.get_text(strip=True):
                    details['ema_title'] = title_elem.get_text(strip=True)
                    break

            # Dates avec sélecteurs multiples
            self._extract_page_dates(soup, details)

            # Référence EMA
            self._extract_page_reference(soup, details)

            return details

        except Exception as e:
            logger.warning(f"⚠️ Erreur récupération détails: {e}")
            return {
                'original_publication_date': None,
                'ema_publication_date': None,
                'ema_reference': '',
                'ema_source_url': document_url,
                'ema_title': '',
                'additional_info': {}
            }

    def _extract_page_dates(self, soup: BeautifulSoup, details: Dict):
        """Extrait les dates de publication depuis la page du document"""
        date_selectors = [
            ('.field--name-field-first-published time', 'original_publication_date'),
            ('.field--name-field-date time', 'original_publication_date'),
            ('.field--name-field-last-updated time', 'ema_publication_date'),
            ('.dates-metadata .first-published time', 'original_publication_date'),
            ('.dates-metadata .last-updated time', 'ema_publication_date'),
            ('.publication-date time', 'original_publication_date'),
            ('.updated-date time', 'ema_publication_date')
        ]

        for selector, field_name in date_selectors:
            try:
                time_elem = soup.select_one(selector)
                if time_elem:
                    date_value = time_elem.get('datetime') or time_elem.get_text(strip=True)
                    parsed_date = self._parse_date(date_value)
                    if parsed_date:
                        details[field_name] = parsed_date.isoformat()
            except Exception as e:
                logger.debug(f"⚠️ Erreur extraction date {selector}: {e}")

    def _extract_page_reference(self, soup: BeautifulSoup, details: Dict):
        """Extrait la référence EMA depuis la page du document"""
        ref_selectors = [
            '.field--name-field-ema-reference-number',
            '.field--name-field-reference',
            '.reference-number',
            '[class*="reference"]'
        ]

        for selector in ref_selectors:
            try:
                ref_elem = soup.select_one(selector)
                if ref_elem and ref_elem.get_text(strip=True):
                    details['ema_reference'] = ref_elem.get_text(strip=True)
                    return
            except Exception as e:
                logger.debug(f"⚠️ Erreur extraction référence {selector}: {e}")

        # Fallback: chercher dans le texte
        try:
            text_content = soup.get_text()
            ref_patterns = [
                r'EMA[\/\-]\d+[\/\-]\d+',
                r'EMEA[\/\-]\d+[\/\-]\d+',
                r'\b[A-Z]{3,}[\/\-]\d+[\/\-]\d+\b'
            ]

            for pattern in ref_patterns:
                match = re.search(pattern, text_content)
                if match:
                    details['ema_reference'] = match.group()
                    return
        except Exception as e:
            logger.debug(f"⚠️ Erreur extraction référence fallback: {e}")

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse une date de manière robuste"""
        if not date_str:
            return None

        date_str = date_str.strip()

        # Formats de date courants
        date_formats = [
            '%Y-%m-%dT%H:%M:%SZ',
            '%Y-%m-%dT%H:%M:%S',
            '%Y-%m-%d',
            '%d/%m/%Y',
            '%d-%m-%Y',
            '%d %B %Y',
            '%d %b %Y',
            '%B %d, %Y',
            '%b %d, %Y'
        ]

        for fmt in date_formats:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue

        # Tentative d'extraction avec regex
        date_match = re.search(r'(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{4})', date_str)
        if date_match:
            try:
                day, month, year = map(int, date_match.groups())
                return datetime(year, month, day)
            except ValueError:
                pass

        return None

    def search_document(self, title: str) -> Dict:
        """Recherche principale avec toutes les stratégies de fallback"""
        logger.info(f"🚀 Recherche EMA pour: '{title}'")

        # Générer les queries de recherche
        search_queries = self.generate_search_queries(title)
        logger.info(f"📝 {len(search_queries)} stratégies de recherche générées")

        best_result = None
        best_similarity = 0.0
        search_attempts = []

        for i, query in enumerate(search_queries):
            logger.info(f"🔍 Stratégie {i + 1}/{len(search_queries)}: '{query}'")
            search_attempts.append(query)

            try:
                # Rechercher sur EMA
                soup = self.search_ema_page(query)
                if not soup:
                    logger.warning(f"❌ Pas de résultats pour: '{query}'")
                    continue

                # Extraire les résultats
                results = self.extract_search_results(soup)
                if not results:
                    logger.warning(f"❌ Aucun résultat extrait pour: '{query}'")
                    continue

                # Évaluer chaque résultat
                for result in results:
                    similarity = self.calculate_similarity(title, result['title'])
                    result['similarity'] = similarity

                    logger.debug(f"📊 Similarité {similarity:.3f}: '{result['title'][:60]}...'")

                    if similarity > best_similarity:
                        best_similarity = similarity
                        best_result = result
                        best_result['search_query_used'] = query
                        best_result['strategy_number'] = i + 1

                # Si on a trouvé un bon match, on peut s'arrêter
                if best_similarity > 0.8:
                    logger.info(f"✅ Excellent match trouvé (similarité: {best_similarity:.3f})")
                    break
                elif best_similarity > 0.6:
                    logger.info(f"✅ Bon match trouvé (similarité: {best_similarity:.3f})")
                    # Continuer pour voir si on trouve mieux, mais ne pas faire toutes les stratégies
                    if i >= len(search_queries) // 2:
                        break

            except Exception as e:
                logger.error(f"❌ Erreur stratégie {i + 1}: {e}")
                continue

            # Pause entre les requêtes pour éviter le rate limiting
            if i < len(search_queries) - 1:
                time.sleep(1)

        # Construire la réponse finale
        if best_result and best_similarity > 0.3:  # Seuil minimum de similarité
            logger.info(
                f"✅ Meilleur résultat trouvé: '{best_result['title'][:60]}...' (similarité: {best_similarity:.3f})")

            # Récupérer les détails complets si on a une URL
            if best_result.get('url'):
                try:
                    detailed_info = self.get_document_details(best_result['url'])
                    best_result.update(detailed_info)
                except Exception as e:
                    logger.warning(f"⚠️ Erreur récupération détails: {e}")

            return {
                'ema_title': best_result.get('title', ''),
                'ema_source_url': best_result.get('url', ''),
                'original_publication_date': best_result.get('original_publication_date'),
                'ema_publication_date': best_result.get('ema_publication_date') or best_result.get('date'),
                'ema_reference': best_result.get('ema_reference', ''),
                'similarity_score': best_similarity,
                'search_successful': True,
                'search_performed': True,
                'search_term_used': best_result.get('search_query_used', title),
                'strategy_used': f"Stratégie {best_result.get('strategy_number', 1)}",
                'search_timestamp': datetime.now().isoformat(),
                'search_attempts': search_attempts
            }
        else:
            logger.warning(f"❌ Aucun résultat pertinent trouvé pour: '{title}'")
            return {
                'ema_title': '',
                'ema_source_url': '',
                'original_publication_date': None,
                'ema_publication_date': None,
                'ema_reference': '',
                'similarity_score': 0.0,
                'search_successful': False,
                'search_performed': True,
                'search_term_used': title,
                'strategy_used': f"Toutes les stratégies échouées",
                'search_timestamp': datetime.now().isoformat(),
                'search_attempts': search_attempts,
                'search_error': f"Aucun résultat avec similarité > 0.3 (meilleur: {best_similarity:.3f})"
            }


# Fonction principale utilisée par le reste de l'application
def fetch_ema_dates_by_title(title: str) -> Dict:
    """
    Point d'entrée principal pour la recherche EMA
    Utilise le moteur de recherche robuste
    """
    try:
        searcher = RobustEMASearcher()
        return searcher.search_document(title)
    except Exception as e:
        logger.error(f"❌ Erreur critique dans la recherche EMA: {e}")
        return {
            'ema_title': '',
            'ema_source_url': '',
            'original_publication_date': None,
            'ema_publication_date': None,
            'ema_reference': '',
            'similarity_score': 0.0,
            'search_successful': False,
            'search_performed': True,
            'search_term_used': title,
            'search_timestamp': datetime.now().isoformat(),
            'search_error': f"Erreur critique: {str(e)}"
        }


# Fonction de test pour débugger
def test_ema_search():
    """Fonction de test pour débugger la recherche EMA"""
    logging.basicConfig(level=logging.INFO)

    test_titles = [
        "Innovation Task Force (ITF) briefing meeting - Instructions on how to apply",
        "Guideline on the requirements for clinical documentation for orally inhaled products",
        "Paxlovid",
        "COVID-19 vaccine guidance",
        "EMA guidance on clinical trials"
    ]

    for title in test_titles:
        print(f"\n{'=' * 80}")
        print(f"TEST: '{title}'")
        print('=' * 80)

        result = fetch_ema_dates_by_title(title)

        print(f"✅ Succès: {result['search_successful']}")
        if result['search_successful']:
            print(f"📄 Titre trouvé: '{result['ema_title']}'")
            print(f"🔗 URL: {result['ema_source_url']}")
            print(f"📅 Date pub.: {result['original_publication_date']}")
            print(f"📅 Mise à jour: {result['ema_publication_date']}")
            print(f"📋 Référence: {result['ema_reference']}")
            print(f"🎯 Similarité: {result['similarity_score']:.3f}")
            print(f"🔍 Stratégie: {result.get('strategy_used', 'N/A')}")
        else:
            print(f"❌ Erreur: {result.get('search_error', 'Non spécifiée')}")
            print(f"🔍 Tentatives: {result.get('search_attempts', [])}")

        time.sleep(2)  # Pause entre les tests


if __name__ == "__main__":
    test_ema_search()