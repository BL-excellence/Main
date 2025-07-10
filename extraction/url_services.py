# extraction/url_services.py - Services d'extraction par URL
import os
import tempfile
import requests
from urllib.parse import urlparse
from bs4 import BeautifulSoup
import logging
from datetime import datetime
from typing import Dict, Optional, Tuple
import re

logger = logging.getLogger(__name__)


class URLDocumentExtractor:
    """Service pour extraire les documents via URLs"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })

    def download_pdf_from_url(self, pdf_url: str) -> Optional[str]:
        """Télécharge un PDF depuis une URL et retourne le chemin temporaire"""
        try:
            logger.info(f"📥 Téléchargement PDF: {pdf_url}")

            response = self.session.get(pdf_url, timeout=30, stream=True)
            response.raise_for_status()

            # Vérifier que c'est bien un PDF
            content_type = response.headers.get('content-type', '').lower()
            if 'application/pdf' not in content_type and not pdf_url.lower().endswith('.pdf'):
                logger.warning(f"⚠️ Type de contenu suspect: {content_type}")

            # Créer un fichier temporaire
            temp_file = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)

            # Télécharger par chunks
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    temp_file.write(chunk)

            temp_file.close()

            # Vérifier la taille du fichier
            file_size = os.path.getsize(temp_file.name)
            logger.info(f"✅ PDF téléchargé: {file_size} bytes")

            if file_size < 1024:  # Moins de 1KB, probablement une erreur
                os.unlink(temp_file.name)
                raise Exception("Fichier PDF trop petit, probablement invalide")

            return temp_file.name

        except Exception as e:
            logger.error(f"❌ Erreur téléchargement PDF: {e}")
            return None

    def extract_title_from_pdf_url(self, pdf_url: str) -> Dict:
        """Extrait le titre d'un PDF depuis une URL"""
        temp_file = None
        try:
            # Télécharger le PDF
            temp_file = self.download_pdf_from_url(pdf_url)
            if not temp_file:
                return {
                    'success': False,
                    'error': 'Impossible de télécharger le PDF',
                    'title': '',
                    'text_preview': ''
                }

            # Extraire le texte et le titre
            from .services import DocumentTextExtractor, RobustTitleExtractor

            text_extractor = DocumentTextExtractor()
            title_extractor = RobustTitleExtractor()

            # Extraire le texte complet
            full_text = text_extractor.extract_text_from_file(temp_file, 'pdf')

            if not full_text or len(full_text.strip()) < 10:
                return {
                    'success': False,
                    'error': 'Impossible d\'extraire le texte du PDF',
                    'title': '',
                    'text_preview': ''
                }

            # Extraire le titre
            title_result = title_extractor.extract_title(full_text)

            return {
                'success': True,
                'title': title_result['title'],
                'confidence': title_result['confidence'],
                'method': title_result['method'],
                'text_preview': full_text[:500] + '...' if len(full_text) > 500 else full_text,
                'text_length': len(full_text),
                'temp_file_path': temp_file  # Garder le fichier temporaire pour traitement ultérieur
            }

        except Exception as e:
            logger.error(f"❌ Erreur extraction titre PDF: {e}")
            if temp_file and os.path.exists(temp_file):
                os.unlink(temp_file)
            return {
                'success': False,
                'error': str(e),
                'title': '',
                'text_preview': ''
            }

    def cleanup_temp_file(self, temp_file_path: str):
        """Nettoie un fichier temporaire"""
        try:
            if temp_file_path and os.path.exists(temp_file_path):
                os.unlink(temp_file_path)
                logger.debug(f"🗑️ Fichier temporaire supprimé: {temp_file_path}")
        except Exception as e:
            logger.warning(f"⚠️ Erreur suppression fichier temporaire: {e}")


class EMAPageExtractor:
    """Service pour extraire les métadonnées depuis une page EMA"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })

    def extract_metadata_from_ema_page(self, ema_page_url: str, target_title: str) -> Dict:
        """Extrait les métadonnées depuis une page EMA spécifique"""
        try:
            logger.info(f"🔍 Extraction métadonnées EMA: {ema_page_url}")
            logger.info(f"🎯 Recherche du titre: '{target_title}'")

            response = self.session.get(ema_page_url, timeout=30)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')

            # Métadonnées par défaut
            metadata = {
                'success': False,
                'ema_title': '',
                'ema_source_url': '',
                'original_publication_date': None,
                'ema_publication_date': None,
                'ema_reference': '',
                'similarity_score': 0.0,
                'search_performed': True,
                'search_timestamp': datetime.now().isoformat(),
                'error': None
            }

            # 1. Extraire le titre de la page
            page_title = self._extract_page_title(soup)
            if page_title:
                metadata['ema_title'] = page_title
                metadata['similarity_score'] = self._calculate_similarity(target_title, page_title)

            # 2. Extraire les dates
            dates = self._extract_dates_from_page(soup)
            metadata.update(dates)

            # 3. Extraire la référence EMA
            reference = self._extract_ema_reference(soup)
            if reference:
                metadata['ema_reference'] = reference

            # 4. Chercher l'URL du PDF sur la page
            pdf_url = self._find_pdf_url_on_page(soup, ema_page_url)
            if pdf_url:
                metadata['ema_source_url'] = pdf_url

            # Déterminer le succès basé sur la présence de données
            if metadata['ema_title'] or metadata['original_publication_date'] or metadata['ema_reference']:
                metadata['success'] = True
                logger.info(f"✅ Métadonnées EMA extraites avec succès")
            else:
                metadata['error'] = "Aucune métadonnée pertinente trouvée sur la page"
                logger.warning(f"⚠️ Aucune métadonnée trouvée")

            return metadata

        except Exception as e:
            logger.error(f"❌ Erreur extraction page EMA: {e}")
            return {
                'success': False,
                'error': str(e),
                'search_performed': True,
                'search_timestamp': datetime.now().isoformat(),
                'ema_title': '',
                'ema_source_url': '',
                'original_publication_date': None,
                'ema_publication_date': None,
                'ema_reference': '',
                'similarity_score': 0.0
            }

    def _extract_page_title(self, soup: BeautifulSoup) -> str:
        """Extrait le titre de la page EMA"""
        # Différents sélecteurs possibles pour le titre
        title_selectors = [
            'h1.page-title',
            'h1',
            '.field--name-title',
            '.page-header h1',
            'title'
        ]

        for selector in title_selectors:
            element = soup.select_one(selector)
            if element:
                title = element.get_text(strip=True)
                if title and len(title) > 5:
                    return title

        return ""

    def _extract_dates_from_page(self, soup: BeautifulSoup) -> Dict:
        """Extrait les dates de publication de la page EMA"""
        dates = {
            'original_publication_date': None,
            'ema_publication_date': None
        }

        # Sélecteurs pour les métadonnées de dates
        date_selectors = [
            ('.field--name-field-first-published', 'original_publication_date'),
            ('.field--name-field-date', 'original_publication_date'),
            ('.field--name-field-last-updated', 'ema_publication_date'),
            ('.field--name-field-updated', 'ema_publication_date'),
            ('.dates-metadata .first-published', 'original_publication_date'),
            ('.dates-metadata .last-updated', 'ema_publication_date')
        ]

        for selector, field_name in date_selectors:
            date_elem = soup.select_one(selector)
            if date_elem:
                # Chercher un élément time
                time_elem = date_elem.select_one('time')
                if time_elem:
                    date_value = time_elem.get('datetime') or time_elem.get_text(strip=True)
                else:
                    date_value = date_elem.get_text(strip=True)

                parsed_date = self._parse_date(date_value)
                if parsed_date:
                    dates[field_name] = parsed_date

        # Recherche alternative par patterns dans le texte
        if not dates['original_publication_date'] and not dates['ema_publication_date']:
            text_content = soup.get_text()
            date_patterns = [
                (r'First published:\s*(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{4})', 'original_publication_date'),
                (r'Published:\s*(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{4})', 'original_publication_date'),
                (r'Last updated:\s*(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{4})', 'ema_publication_date'),
                (r'Updated:\s*(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{4})', 'ema_publication_date'),
            ]

            for pattern, field_name in date_patterns:
                matches = re.findall(pattern, text_content)
                if matches and not dates[field_name]:
                    parsed_date = self._parse_date(matches[0])
                    if parsed_date:
                        dates[field_name] = parsed_date

        return dates

    def _extract_ema_reference(self, soup: BeautifulSoup) -> str:
        """Extrait la référence EMA de la page"""
        # Sélecteurs pour la référence
        ref_selectors = [
            '.field--name-field-ema-reference-number',
            '.field--name-field-reference',
            '[class*="reference"]'
        ]

        for selector in ref_selectors:
            ref_elem = soup.select_one(selector)
            if ref_elem:
                reference = ref_elem.get_text(strip=True)
                if reference:
                    return reference

        # Recherche par patterns dans le texte
        text_content = soup.get_text()
        ref_patterns = [
            r'EMA[\/\-]\d+[\/\-]\d+',
            r'EMEA[\/\-]\d+[\/\-]\d+',
            r'\b[A-Z]{2,}[\/\-]\d+[\/\-]\d+\b'
        ]

        for pattern in ref_patterns:
            match = re.search(pattern, text_content)
            if match:
                return match.group()

        return ""

    def _find_pdf_url_on_page(self, soup: BeautifulSoup, base_url: str) -> str:
        """Trouve l'URL du PDF sur la page EMA"""
        pdf_links = soup.find_all('a', href=lambda x: x and x.endswith('.pdf'))

        for link in pdf_links:
            href = link.get('href')
            if href:
                # Construire l'URL complète
                if href.startswith('http'):
                    return href
                elif href.startswith('/'):
                    from urllib.parse import urljoin
                    return urljoin('https://www.ema.europa.eu', href)
                else:
                    from urllib.parse import urljoin
                    return urljoin(base_url, href)

        return ""

    def _parse_date(self, date_str: str) -> Optional[str]:
        """Parse une date dans différents formats et retourne au format ISO"""
        if not date_str:
            return None

        date_str = date_str.strip()

        # Formats de date courants
        date_formats = [
            '%Y-%m-%dT%H:%M:%SZ',  # ISO avec timezone
            '%Y-%m-%dT%H:%M:%S',  # ISO sans timezone
            '%Y-%m-%d',  # ISO simple
            '%d/%m/%Y',  # DD/MM/YYYY
            '%d-%m-%Y',  # DD-MM-YYYY
            '%d %B %Y',  # DD Month YYYY
            '%d %b %Y',  # DD Mon YYYY
            '%B %d, %Y',  # Month DD, YYYY
            '%b %d, %Y'  # Mon DD, YYYY
        ]

        for fmt in date_formats:
            try:
                parsed = datetime.strptime(date_str, fmt)
                return parsed.strftime('%Y-%m-%d')
            except ValueError:
                continue

        # Tentative d'extraction de date avec regex
        date_match = re.search(r'(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{4})', date_str)
        if date_match:
            day, month, year = map(int, date_match.groups())
            try:
                parsed = datetime(year, month, day)
                return parsed.strftime('%Y-%m-%d')
            except ValueError:
                pass

        return None

    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """Calcule un score de similarité simple entre deux textes"""
        if not text1 or not text2:
            return 0.0

        # Normaliser les textes
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())

        if not words1 and not words2:
            return 1.0

        intersection = words1.intersection(words2)
        union = words1.union(words2)

        return len(intersection) / len(union) if union else 0.0


class URLDocumentProcessor:
    """Processeur principal pour les documents via URL"""

    def __init__(self):
        self.url_extractor = URLDocumentExtractor()
        self.ema_extractor = EMAPageExtractor()

    def process_document_from_urls(self, direct_pdf_url: str, ema_page_url: str) -> Dict:
        """Traite un document complet à partir des URLs"""
        logger.info(f"🚀 Traitement document via URLs")
        logger.info(f"   PDF: {direct_pdf_url}")
        logger.info(f"   EMA: {ema_page_url}")

        result = {
            'success': False,
            'title_extraction': None,
            'ema_metadata': None,
            'temp_file_path': None,
            'error': None
        }

        try:
            # 1. Extraire le titre du PDF
            logger.info("📄 Étape 1: Extraction du titre depuis le PDF")
            title_result = self.url_extractor.extract_title_from_pdf_url(direct_pdf_url)
            result['title_extraction'] = title_result

            if not title_result['success']:
                result['error'] = f"Échec extraction titre: {title_result['error']}"
                return result

            extracted_title = title_result['title']
            logger.info(f"✅ Titre extrait: '{extracted_title}'")

            # 2. Extraire les métadonnées EMA
            logger.info("🔍 Étape 2: Extraction métadonnées depuis la page EMA")
            ema_result = self.ema_extractor.extract_metadata_from_ema_page(ema_page_url, extracted_title)
            result['ema_metadata'] = ema_result

            if not ema_result['success']:
                logger.warning(f"⚠️ Échec extraction EMA: {ema_result.get('error', 'Erreur inconnue')}")
            else:
                logger.info(f"✅ Métadonnées EMA extraites")

            # 3. Garder le fichier temporaire pour traitement ultérieur
            result['temp_file_path'] = title_result.get('temp_file_path')

            result['success'] = True
            logger.info("🎉 Traitement par URLs terminé avec succès")

            return result

        except Exception as e:
            logger.error(f"❌ Erreur traitement URLs: {e}")
            result['error'] = str(e)

            # Nettoyer le fichier temporaire en cas d'erreur
            if result.get('temp_file_path'):
                self.url_extractor.cleanup_temp_file(result['temp_file_path'])

            return result

    def cleanup_processing_files(self, temp_file_path: str):
        """Nettoie les fichiers temporaires du traitement"""
        if temp_file_path:
            self.url_extractor.cleanup_temp_file(temp_file_path)