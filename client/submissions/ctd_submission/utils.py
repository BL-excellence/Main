# ctd_submission/utils.py - VERSION CORRIGÉE COMPLÈTE
# Corrections pour l'intégration du processeur fidèle

import re
import json
import os
import time
import base64
from typing import Dict, List, Optional, Tuple, Union
import logging

# Optional heavy dependencies
try:
    import cv2
    CV2_AVAILABLE = True
except Exception:
    CV2_AVAILABLE = False
try:
    import fitz  # PyMuPDF
    FITZ_AVAILABLE = True
except Exception:
    FITZ_AVAILABLE = False
# OCR removed (not used)
OCR_AVAILABLE = False
try:
    from PIL import Image
except Exception:
    Image = None

# CORRECTION 1: Imports Django correctement gérés
try:
    from django.conf import settings
    from django.utils import timezone
    from django.core.cache import cache

    DJANGO_AVAILABLE = True
except ImportError:
    DJANGO_AVAILABLE = False


    class MockTimezone:
        @staticmethod
        def now():
            import datetime
            return datetime.datetime.now()


    timezone = MockTimezone()

# CORRECTION 2: Imports des modèles avec gestion d'erreurs
try:
    from . import models

    MODELS_AVAILABLE = True
except ImportError:
    MODELS_AVAILABLE = False
    models = None

# CORRECTION 3: Imports NLP optionnels avec gestion d'erreurs améliorée
try:
    import nltk
    from nltk.corpus import stopwords
    from nltk.tokenize import word_tokenize, sent_tokenize
    from nltk.stem import PorterStemmer
    from nltk.chunk import ne_chunk
    from nltk.tag import pos_tag

    NLTK_AVAILABLE = True
except ImportError:
    NLTK_AVAILABLE = False

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    import numpy as np
    NP_AVAILABLE = True
    SKLEARN_AVAILABLE = True
except ImportError:
    NP_AVAILABLE = False
    SKLEARN_AVAILABLE = False
    # Provide a minimal fallback to avoid NameError in type hints
    class _NPStub:
        ndarray = object
    np = _NPStub()

try:
    import requests

    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

logger = logging.getLogger(__name__)



# --- Minimal class stubs to satisfy imports during startup ---
class CTDAnalyzer:
    def analyze_document(self, document):
        return None

class DocumentProcessor:
    def extract_content(self, document):
        return {"text": getattr(document, "name", ""), "extracted": False}
    def update_document_from_template(self, document):
        return False

class IntelligentCopilot:
    def analyze_global_changes(self, document, changes):
        return []
    def get_smart_suggestions(self, document, change_type, content, context):
        return []
    def suggest_template_positions(self, document, template_data):
        return []

class DocumentExporter:
    def export_modified_document(self, document):
        return None

class CTDStructureGenerator:
    def initialize_default_structure(self):
        return []

class AdvancedCTDAnalyzer:
    pass

# ----------------------------------------------------------------

class FaithfulPDFProcessor:
    """
    Processeur PDF amélioré pour extraction fidèle des tableaux avec préservation complète
    de la structure, position et mise en forme originale
    """

    def __init__(self):
        self.available_processors = []
        self.pdf_libraries = {}
        self._check_pdf_libraries()

        # Configuration pour extraction fidèle avec OCR éditables
        self.table_detection_config = {
            'min_rows': 2,
            'min_cols': 2,
            'cell_margin_tolerance': 3.0,
            'row_height_tolerance': 5.0,
            'col_width_tolerance': 8.0,
            'text_alignment_threshold': 0.7,
            'preserve_empty_cells': True,
            'detect_merged_cells': True,
            'preserve_cell_formatting': True
        }

        # Configuration OCR pour édition
        self.ocr_config = {
            'min_confidence': 30,  # Confiance minimum Tesseract
            'min_word_width': 10,  # Largeur minimum d'un mot en pixels
            'min_word_height': 8,  # Hauteur minimum d'un mot en pixels
            'merge_adjacent_words': True,  # Fusionner les mots adjacents
            'adjacent_threshold': 5,  # Seuil de proximité pour fusionner
            'font_size_estimation': True,  # Estimer la taille de police
            'preserve_line_breaks': True,  # Préserver les sauts de ligne
        }
        self.technical_ocr_config = {
            'min_confidence': 20,  # Réduire pour capturer plus d'éléments
            'min_word_width': 5,  # Réduire pour les petits chiffres
            'min_word_height': 5,  # Réduire pour les petites annotations
            'merge_adjacent_words': False,  # Ne pas fusionner pour garder la précision
            'adjacent_threshold': 3,
            'font_size_estimation': True,
            'preserve_line_breaks': True,
            'detect_symbols': True,  # NOUVEAU: Détecter les symboles
            'detect_dimensions': True,  # NOUVEAU: Détecter les cotes
            'enhance_image': True,  # NOUVEAU: Améliorer l'image avant OCR
            'multiple_passes': True  # NOUVEAU: Plusieurs passes OCR
        }

    def _enhance_image_for_technical_ocr(self, img: Image) -> List[Image]:
        """
        Améliore l'image pour une meilleure détection OCR des éléments techniques
        Retourne plusieurs versions optimisées de l'image
        """
        enhanced_images = []

        try:
            import cv2
            import numpy as np

            # Convertir PIL en OpenCV
            img_cv = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)

            # Version 1: Image originale légèrement améliorée
            enhanced1 = cv2.convertScaleAbs(img_cv, alpha=1.2, beta=10)
            enhanced_images.append(Image.fromarray(cv2.cvtColor(enhanced1, cv2.COLOR_BGR2RGB)))

            # Version 2: Amélioration du contraste adaptatif
            gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
            clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
            enhanced2 = clahe.apply(gray)
            enhanced2 = cv2.cvtColor(enhanced2, cv2.COLOR_GRAY2RGB)
            enhanced_images.append(Image.fromarray(enhanced2))

            # Version 3: Binarisation adaptative pour texte fin
            thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                           cv2.THRESH_BINARY, 11, 2)
            enhanced3 = cv2.cvtColor(thresh, cv2.COLOR_GRAY2RGB)
            enhanced_images.append(Image.fromarray(enhanced3))

            # Version 4: Augmentation de la résolution par interpolation
            height, width = img_cv.shape[:2]
            enhanced4 = cv2.resize(img_cv, (width * 2, height * 2), interpolation=cv2.INTER_CUBIC)
            enhanced_images.append(Image.fromarray(cv2.cvtColor(enhanced4, cv2.COLOR_BGR2RGB)))

            # Version 5: Détection des contours pour isoler le texte
            edges = cv2.Canny(gray, 50, 150)
            kernel = np.ones((2, 2), np.uint8)
            edges = cv2.dilate(edges, kernel, iterations=1)
            enhanced5 = cv2.cvtColor(edges, cv2.COLOR_GRAY2RGB)
            enhanced_images.append(Image.fromarray(enhanced5))

        except ImportError:
            logger.warning("OpenCV non disponible - utilisation de l'image originale uniquement")
            enhanced_images = [img]
        except Exception as e:
            logger.warning(f"Erreur amélioration image: {e}")
            enhanced_images = [img]

        return enhanced_images

    def _ocr_image_words(self, doc, xref: int, img_rect, dpi: int = 300):
        """
        OCR l'image (xref) et retourne une liste de mots avec leur bbox,
        normalisée en % par rapport à l'image.
        """
        if not OCR_AVAILABLE:
            return []

        try:
            fitz = self.pdf_libraries['pymupdf']

            # Rasterize uniquement le rectangle de l'image pour plus de précision
            # (on extrait l'image brute plutôt que la zone de page)
            pix = fitz.Pixmap(doc, xref)
            if pix.alpha:
                pix = fitz.Pixmap(fitz.csRGB, pix)

            # OCR disabled: skip generating OCR data
            return {"words": [], "image_pixel_size": {"width": float(pix.width), "height": float(pix.height)}}


        except Exception as e:
            logger.warning(f"OCR échec xref={xref}: {e}")
            return {"words": [], "image_pixel_size": None}
    def _check_pdf_libraries(self):
        """Vérifie et importe les bibliothèques PDF disponibles"""
        try:
            import fitz
            self.pdf_libraries['pymupdf'] = fitz
            self.available_processors.append('pymupdf')
            logger.info("✅ PyMuPDF disponible - extraction avancée activée")
        except ImportError:
            logger.warning("⚠️ PyMuPDF non disponible")

    def _assess_technical_ocr_quality(self, words: List[Dict]) -> Dict:
        """
        Évalue la qualité OCR spécifiquement pour les dessins techniques
        """
        if not words:
            return {
                "overall": "poor",
                "confidence_avg": 0,
                "editable_count": 0,
                "technical_elements": 0
            }

        confidences = [word.get("confidence", 0) for word in words]
        avg_confidence = sum(confidences) / len(confidences)

        # Compter les éléments techniques critiques
        technical_types = ['diameter', 'dimension', 'radius', 'section_line', 'annotation', 'angle']
        technical_count = sum(1 for word in words
                              if word.get("editing_metadata", {}).get("text_type") in technical_types)

        # Distribution de confiance
        high_confidence_count = sum(1 for c in confidences if c >= 70)
        medium_confidence_count = sum(1 for c in confidences if 40 <= c < 70)
        low_confidence_count = sum(1 for c in confidences if c < 40)

        # Évaluation globale adaptée aux dessins techniques
        if avg_confidence >= 70 and technical_count >= len(words) * 0.3:
            overall_quality = "excellent"
        elif avg_confidence >= 50 and technical_count >= len(words) * 0.2:
            overall_quality = "good"
        elif avg_confidence >= 30 and technical_count >= len(words) * 0.1:
            overall_quality = "fair"
        else:
            overall_quality = "poor"

        return {
            "overall": overall_quality,
            "confidence_avg": round(avg_confidence, 1),
            "editable_count": len(words),
            "technical_elements": technical_count,
            "quality_distribution": {
                "high": high_confidence_count,
                "medium": medium_confidence_count,
                "low": low_confidence_count
            },
            "technical_coverage": round((technical_count / len(words)) * 100, 1) if words else 0,
            "recommendation": self._get_technical_quality_recommendation(overall_quality,
                                                                         low_confidence_count,
                                                                         technical_count)
        }

    def _get_technical_quality_recommendation(self, quality: str, low_conf_count: int,
                                              technical_count: int) -> str:
        """
        Génère une recommandation spécifique aux dessins techniques
        """
        if quality == "poor":
            return "Qualité OCR faible pour dessin technique. Vérifiez manuellement toutes les cotes et annotations."
        elif low_conf_count > 3:
            return f"{low_conf_count} éléments incertains détectés. Vérifiez particulièrement les dimensions et symboles."
        elif technical_count == 0:
            return "Aucun élément technique détecté. L'image contient peut-être uniquement du graphisme."
        elif quality == "excellent":
            return f"Excellente détection : {technical_count} éléments techniques identifiés. Édition directe recommandée."
        else:
            return f"Détection correcte : {technical_count} éléments techniques trouvés. Vérifiez les éléments marqués en rouge."

    def _ocr_image_words_editable(self, doc, xref: int, img_rect, dpi: int = 300):
        """
        OCR avancé multi-passes pour détecter tous les éléments techniques
        """
        if not OCR_AVAILABLE:
            return {"words": [], "editable_elements": [], "image_pixel_size": None}

        try:
            fitz = self.pdf_libraries['pymupdf']

            # Extraire l'image avec haute résolution
            pix = fitz.Pixmap(doc, xref)
            if pix.alpha:
                pix = fitz.Pixmap(fitz.csRGB, pix)

            # Conversion en PIL Image
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            W, H = float(pix.width), float(pix.height)

            # NOUVEAU: Améliorer l'image avec plusieurs versions
            enhanced_images = self._enhance_image_for_technical_ocr(img)

            all_words = []

            # NOUVEAU: Plusieurs passes OCR avec différentes configurations
            ocr_configs = [
                # Configuration standard
                '--psm 6 -c preserve_interword_spaces=1',
                # Configuration pour texte épars (dimensions, annotations)
                '--psm 8 -c tessedit_char_whitelist=0123456789.,ØøABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-',
                # Configuration pour chiffres uniquement
                '--psm 8 -c tessedit_char_whitelist=0123456789.,',
                # Configuration pour détection fine
                '--psm 13 -c preserve_interword_spaces=1',
                # Configuration pour annotations (lettres seules)
                '--psm 8 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ-\''
            ]

            # Effectuer OCR sur chaque version d'image avec chaque configuration
            for img_version in enhanced_images:
                for config in ocr_configs:
                    try:
                        # OCR disabled: skip calling pytesseract
                        continue

                        # Traiter les résultats
                        words_batch = self._process_ocr_results(ocr_data, W, H, xref, config)
                        all_words.extend(words_batch)

                    except Exception as e:
                        logger.debug(f"Erreur OCR config {config}: {e}")
                        continue

            # NOUVEAU: Déduplication et filtrage intelligent
            unique_words = self._deduplicate_and_filter_words(all_words)

            # NOUVEAU: Détection de symboles et éléments spéciaux manqués
            symbol_words = self._detect_technical_symbols(img, W, H, xref)
            unique_words.extend(symbol_words)

            # Créer les éléments éditables optimisés
            editable_elements = self._create_editable_text_elements(unique_words, W, H)

            # Nettoyer la mémoire
            try:
                pix = None
            except:
                pass

            result = {
                "words": unique_words,
                "editable_elements": editable_elements,
                "image_pixel_size": {"width": W, "height": H},
                "ocr_quality": self._assess_technical_ocr_quality(unique_words),
                "editing_capabilities": {
                    "direct_edit": True,
                    "position_locked": True,
                    "font_preservation": True,
                    "confidence_weighted": True,
                    "technical_symbols": True
                }
            }

            # CORRECTION: Nettoyer tous les types NumPy avant de retourner
            return self._sanitize_for_json(result)

        except Exception as e:
            logger.warning(f"OCR technique échec xref={xref}: {e}")
            return {"words": [], "editable_elements": [], "image_pixel_size": None}

    def _estimate_technical_font_properties(self, text: str, width: int, height: int) -> Dict:
        """
        Estime les propriétés de police spécifiquement pour les éléments techniques
        """
        try:
            text_type = self._classify_technical_text_content(text)
            char_count = len(text)
            avg_char_width = width / char_count if char_count > 0 else width

            # Estimation de la taille de police selon le type technique
            if text_type in ['diameter', 'dimension', 'radius']:
                # Les cotes sont généralement en police plus grande
                estimated_font_size = max(10, min(height * 0.9, 24))
            elif text_type in ['annotation', 'section_line']:
                # Les annotations sont souvent plus petites
                estimated_font_size = max(8, min(height * 0.8, 16))
            elif text_type == 'label':
                # Les étiquettes peuvent être plus grandes
                estimated_font_size = max(12, min(height * 0.85, 32))
            else:
                # Police standard
                estimated_font_size = max(8, min(height * 0.8, 20))

            # Détection du style selon le contenu
            is_bold = self._is_technical_element_bold(text, text_type, height, avg_char_width)
            is_italic = text_type in ['detail_reference', 'volume_unit']
            is_monospace = text_type in ['dimension', 'diameter', 'radius', 'angle']

            # Police recommandée selon le type
            font_family = self._get_technical_font_family(text_type)

            # Densité de texte (utile pour l'affichage)
            text_density = char_count / (width * height) if width * height > 0 else 0

            return {
                "estimated_size": round(estimated_font_size),
                "char_width": round(avg_char_width, 1),
                "line_height": height,
                "is_bold_likely": is_bold,
                "is_italic": is_italic,
                "is_monospace": is_monospace,
                "font_family": font_family,
                "text_density": round(text_density, 4),
                "technical_type": text_type,
                "display_priority": self._get_display_priority(text_type)
            }

        except Exception as e:
            logger.debug(f"Erreur estimation police technique: {e}")
            return {
                "estimated_size": 12,
                "char_width": 8,
                "line_height": height,
                "is_bold_likely": False,
                "is_italic": False,
                "is_monospace": False,
                "font_family": "Arial",
                "text_density": 0,
                "technical_type": "text",
                "display_priority": 5
            }

    def _is_technical_element_bold(self, text: str, text_type: str, height: int,
                                   avg_char_width: float) -> bool:
        """
        Détermine si un élément technique est probablement en gras
        """
        # Les cotes principales sont souvent en gras
        if text_type in ['diameter', 'dimension', 'radius'] and height > 12:
            return True

        # Les annotations de coupe sont généralement en gras
        if text_type == 'section_line':
            return True

        # Les étiquettes importantes en majuscules
        if text_type == 'label' and text.isupper():
            return True

        # Estimation basée sur le ratio largeur/hauteur
        if avg_char_width > height * 0.7:  # Caractères larges = probablement gras
            return True

        return False

    def _get_technical_font_family(self, text_type: str) -> str:
        """
        Retourne la famille de police recommandée selon le type technique
        """
        font_families = {
            'diameter': 'Arial, sans-serif',
            'dimension': 'Arial, sans-serif',
            'radius': 'Arial, sans-serif',
            'angle': 'Arial, sans-serif',
            'section_line': 'Arial Black, sans-serif',
            'annotation': 'Arial, sans-serif',
            'detail_reference': 'Arial, sans-serif',
            'volume_unit': 'Times New Roman, serif',
            'tolerance': 'Arial, sans-serif',
            'label': 'Arial Black, sans-serif',
            'decimal_number': 'Courier New, monospace',
            'fraction': 'Times New Roman, serif'
        }

        return font_families.get(text_type, 'Arial, sans-serif')

    def _get_display_priority(self, text_type: str) -> int:
        """
        Retourne la priorité d'affichage (1 = plus important, 10 = moins important)
        """
        priorities = {
            'diameter': 1,
            'dimension': 1,
            'radius': 2,
            'section_line': 2,
            'annotation': 3,
            'angle': 3,
            'tolerance': 4,
            'detail_reference': 4,
            'volume_unit': 5,
            'label': 6,
            'decimal_number': 2,
            'fraction': 7,
            'description': 8,
            'text': 9
        }

        return priorities.get(text_type, 5)

    def _sanitize_for_json(self, obj):
        """
        Nettoie récursivement un objet pour le rendre compatible JSON
        Convertit les types NumPy en types Python natifs
        """
        import numpy as np

        if isinstance(obj, dict):
            return {key: self._sanitize_for_json(value) for key, value in obj.items()}
        elif isinstance(obj, list):
            return [self._sanitize_for_json(item) for item in obj]
        elif isinstance(obj, tuple):
            return tuple(self._sanitize_for_json(item) for item in obj)
        elif isinstance(obj, np.integer):
            return int(obj)
        elif isinstance(obj, np.floating):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        elif hasattr(obj, 'item'):  # Autres types numpy scalaires
            return obj.item()
        else:
            return obj

    def _detect_special_characters(self, gray: np.ndarray, W: float, H: float, xref: int) -> List[Dict]:
        """
        Détecte les caractères spéciaux souvent manqués par l'OCR standard
        """
        special_chars = []

        try:
            import cv2
            import numpy as np

            # Détection du symbole degré (°)
            degree_symbols = self._detect_degree_symbols(gray, W, H, xref)
            special_chars.extend(degree_symbols)

            # Détection du symbole plus/moins (±)
            plusminus_symbols = self._detect_plusminus_symbols(gray, W, H, xref)
            special_chars.extend(plusminus_symbols)

            # Détection des apostrophes/primes (')
            prime_symbols = self._detect_prime_symbols(gray, W, H, xref)
            special_chars.extend(prime_symbols)

            # Détection des symboles de rugosité/finition surface
            surface_symbols = self._detect_surface_symbols(gray, W, H, xref)
            special_chars.extend(surface_symbols)

        except Exception as e:
            logger.debug(f"Erreur détection caractères spéciaux: {e}")

        return special_chars

    def _detect_degree_symbols(self, gray: np.ndarray, W: float, H: float, xref: int) -> List[Dict]:
        """
        Détecte les symboles degré (°) par analyse morphologique
        """
        symbols = []

        try:
            import cv2
            import numpy as np

            # Template matching pour le symbole degré
            # Créer un template circulaire petit
            template_size = 8
            template = np.zeros((template_size, template_size), dtype=np.uint8)
            cv2.circle(template, (template_size // 2, template_size // 2), 2, 255, 1)

            # Recherche du template
            result = cv2.matchTemplate(gray, template, cv2.TM_CCOEFF_NORMED)
            threshold = 0.6
            locations = np.where(result >= threshold)

            for pt in zip(*locations[::-1]):
                # CORRECTION: conversion explicite en int
                x, y = int(pt[0]), int(pt[1])

                # Vérifier que c'est vraiment un symbole degré (position après des chiffres)
                if self._is_likely_degree_symbol(gray, x, y):
                    symbol_data = {
                        "text": "°",
                        "confidence": 75,
                        "bbox_img": {
                            "x": x, "y": y, "w": template_size, "h": template_size,
                            "x_pct": float((x / W) * 100.0),
                            "y_pct": float((y / H) * 100.0),
                            "w_pct": float((template_size / W) * 100.0),
                            "h_pct": float((template_size / H) * 100.0),
                        },
                        "font_info": {"estimated_size": 10, "is_symbol": True},
                        "editing_metadata": {
                            "word_id": f"symbol_{xref}_degree_{x}_{y}",
                            "editable": True,
                            "original_text": "°",
                            "text_type": "degree_symbol",
                            "detection_method": "template_matching"
                        }
                    }
                    symbols.append(symbol_data)

        except Exception as e:
            logger.debug(f"Erreur détection symbole degré: {e}")

        return symbols

    def _detect_plusminus_symbols(self, gray: np.ndarray, W: float, H: float, xref: int) -> List[Dict]:
        """
        Détecte les symboles plus/moins (±) par analyse de contours
        """
        symbols = []

        try:
            import cv2
            import numpy as np

            # Détection de contours
            contours, _ = cv2.findContours(gray, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            for contour in contours:
                # Filtrer par taille - CORRECTION: conversion explicite
                x, y, w, h = cv2.boundingRect(contour)
                x, y, w, h = int(x), int(y), int(w), int(h)

                if 8 <= w <= 20 and 10 <= h <= 25:
                    # Extraire la région
                    roi = gray[y:y + h, x:x + w]

                    # Vérifier s'il s'agit d'un symbole ± par analyse des lignes
                    if self._is_plusminus_pattern(roi):
                        symbol_data = {
                            "text": "±",
                            "confidence": 70,
                            "bbox_img": {
                                "x": x, "y": y, "w": w, "h": h,
                                "x_pct": float((x / W) * 100.0),
                                "y_pct": float((y / H) * 100.0),
                                "w_pct": float((w / W) * 100.0),
                                "h_pct": float((h / H) * 100.0),
                            },
                            "font_info": {"estimated_size": h, "is_symbol": True},
                            "editing_metadata": {
                                "word_id": f"symbol_{xref}_plusminus_{x}_{y}",
                                "editable": True,
                                "original_text": "±",
                                "text_type": "tolerance_symbol",
                                "detection_method": "contour_analysis"
                            }
                        }
                        symbols.append(symbol_data)

        except Exception as e:
            logger.debug(f"Erreur détection symbole ±: {e}")

        return symbols

    def _detect_prime_symbols(self, gray: np.ndarray, W: float, H: float, xref: int) -> List[Dict]:
        """
        Détecte les symboles prime/apostrophe (') pour les angles
        """
        symbols = []

        try:
            import cv2
            import numpy as np

            # Recherche de petites lignes verticales (caractéristique des primes)
            kernel = np.array([[1], [1], [1], [1]], dtype=np.int8)
            vertical_lines = cv2.filter2D(gray, -1, kernel)

            # Seuillage pour détecter les lignes fines
            _, thresh = cv2.threshold(vertical_lines, 200, 255, cv2.THRESH_BINARY)

            # Trouver les contours de ces lignes
            contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            for contour in contours:
                # CORRECTION: conversion explicite
                x, y, w, h = cv2.boundingRect(contour)
                x, y, w, h = int(x), int(y), int(w), int(h)

                # Filtrer pour les dimensions typiques d'une prime
                if 2 <= w <= 6 and 6 <= h <= 15 and h > w * 2:
                    # Vérifier le contexte (près de chiffres d'angle)
                    if self._is_likely_prime_symbol(gray, x, y, w, h):
                        symbol_data = {
                            "text": "'",
                            "confidence": 65,
                            "bbox_img": {
                                "x": x, "y": y, "w": w, "h": h,
                                "x_pct": float((x / W) * 100.0),
                                "y_pct": float((y / H) * 100.0),
                                "w_pct": float((w / W) * 100.0),
                                "h_pct": float((h / H) * 100.0),
                            },
                            "font_info": {"estimated_size": h, "is_symbol": True},
                            "editing_metadata": {
                                "word_id": f"symbol_{xref}_prime_{x}_{y}",
                                "editable": True,
                                "original_text": "'",
                                "text_type": "prime_symbol",
                                "detection_method": "line_detection"
                            }
                        }
                        symbols.append(symbol_data)

        except Exception as e:
            logger.debug(f"Erreur détection symbole prime: {e}")

        return symbols

    def _detect_surface_symbols(self, gray: np.ndarray, W: float, H: float, xref: int) -> List[Dict]:
        """
        Détecte les symboles de finition de surface (triangles, etc.)
        """
        symbols = []

        try:
            import cv2
            import numpy as np

            # Détection de contours triangulaires
            contours, _ = cv2.findContours(gray, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            for contour in contours:
                # Approximation polygonale
                epsilon = 0.02 * cv2.arcLength(contour, True)
                approx = cv2.approxPolyDP(contour, epsilon, True)

                # Vérifier si c'est un triangle
                if len(approx) == 3:
                    # CORRECTION: conversion explicite
                    x, y, w, h = cv2.boundingRect(contour)
                    x, y, w, h = int(x), int(y), int(w), int(h)

                    # Filtrer par taille appropriée pour symboles de surface
                    if 8 <= w <= 25 and 8 <= h <= 25:
                        symbol_data = {
                            "text": "▽",
                            "confidence": 60,
                            "bbox_img": {
                                "x": x, "y": y, "w": w, "h": h,
                                "x_pct": float((x / W) * 100.0),
                                "y_pct": float((y / H) * 100.0),
                                "w_pct": float((w / W) * 100.0),
                                "h_pct": float((h / H) * 100.0),
                            },
                            "font_info": {"estimated_size": max(w, h), "is_symbol": True},
                            "editing_metadata": {
                                "word_id": f"symbol_{xref}_surface_{x}_{y}",
                                "editable": True,
                                "original_text": "▽",
                                "text_type": "surface_symbol",
                                "detection_method": "shape_detection"
                            }
                        }
                        symbols.append(symbol_data)

        except Exception as e:
            logger.debug(f"Erreur détection symboles surface: {e}")

        return symbols

    # Méthodes utilitaires pour la validation des symboles

    def _is_likely_degree_symbol(self, gray: np.ndarray, x: int, y: int) -> bool:
        """Vérifie si la position est vraisemblable pour un symbole degré"""
        try:
            # Vérifier s'il y a des chiffres à gauche
            roi_left = gray[max(0, y - 5):y + 10, max(0, x - 20):x]
            return cv2.countNonZero(roi_left) > 10  # Présence de texte à gauche
        except:
            return True

    def _is_plusminus_pattern(self, roi: np.ndarray) -> bool:
        """Vérifie si la ROI contient un pattern ±"""
        try:
            h, w = roi.shape
            # Vérifier ligne horizontale au milieu
            mid_h = h // 2
            horizontal_line = roi[mid_h - 1:mid_h + 2, :]

            # Vérifier ligne verticale au milieu (partie supérieure seulement pour ±)
            mid_w = w // 2
            vertical_line = roi[:mid_h + 2, mid_w - 1:mid_w + 2]

            return (cv2.countNonZero(horizontal_line) > w * 0.6 and
                    cv2.countNonZero(vertical_line) > h * 0.3)
        except:
            return False

    def _is_likely_prime_symbol(self, gray: np.ndarray, x: int, y: int, w: int, h: int) -> bool:
        """Vérifie si c'est probablement un symbole prime"""
        try:
            # Vérifier s'il y a des chiffres à gauche (contexte d'angle)
            roi_left = gray[y:y + h, max(0, x - 15):x]
            # Vérifier aussi la position relative (les primes sont en haut à droite des chiffres)
            return cv2.countNonZero(roi_left) > 5 and y < gray.shape[0] * 0.7
        except:
            return True

    def _process_ocr_results(self, ocr_data: Dict, W: float, H: float, xref: int, config: str) -> List[Dict]:
        """
        Traite les résultats OCR avec filtrage adapté aux dessins techniques
        """
        words = []

        for i in range(len(ocr_data["text"])):
            txt = (ocr_data["text"][i] or "").strip()
            confidence = int(ocr_data.get("conf", [0])[i])  # Déjà converti en int

            # Filtrage adapté aux éléments techniques
            if not txt:
                continue

            # Accepter même les éléments de faible confiance s'ils ressemblent à des dimensions/annotations
            min_confidence = self._get_adaptive_confidence_threshold(txt, config)

            if confidence < min_confidence:
                continue

            # Coordonnées et dimensions - CORRECTION: conversion explicite en int
            x = int(ocr_data["left"][i])
            y = int(ocr_data["top"][i])
            w = int(ocr_data["width"][i])
            h = int(ocr_data["height"][i])

            # Accepter des éléments plus petits pour les annotations techniques
            min_width = 3 if self._is_technical_annotation(txt) else 8
            min_height = 3 if self._is_technical_annotation(txt) else 6

            if w < min_width or h < min_height:
                continue

            # Classification précise du type de texte technique
            text_type = self._classify_technical_text_content(txt)

            word_data = {
                "text": txt,
                "confidence": confidence,
                "bbox_img": {
                    "x": x, "y": y, "w": w, "h": h,
                    "x_pct": float((x / W) * 100.0),
                    "y_pct": float((y / H) * 100.0),
                    "w_pct": float((w / W) * 100.0),
                    "h_pct": float((h / H) * 100.0),
                },
                "font_info": self._estimate_technical_font_properties(txt, w, h),
                "editing_metadata": {
                    "word_id": f"word_{xref}_{i}_{hash(config)}",
                    "editable": True,
                    "original_text": txt,
                    "text_type": text_type,
                    "ocr_config": config
                }
            }

            words.append(word_data)

        return words

    def _detect_technical_symbols(self, img: Image, W: float, H: float, xref: int) -> List[Dict]:
        """
        Détection spécialisée pour les symboles techniques souvent manqués par l'OCR
        """
        symbols = []

        try:
            import cv2
            import numpy as np

            # Convertir en OpenCV
            img_cv = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
            gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)

            # Détecter les cercles (pour symboles Ø)
            circles = cv2.HoughCircles(gray, cv2.HOUGH_GRADIENT, 1, 20,
                                       param1=50, param2=30, minRadius=5, maxRadius=15)

            if circles is not None:
                circles = np.round(circles[0, :]).astype("int")
                for (x, y, r) in circles:
                    # Vérifier si c'est probablement un symbole Ø
                    if self._is_diameter_symbol_region(gray, x, y, r):
                        symbol_data = {
                            "text": "Ø",
                            "confidence": 80,
                            "bbox_img": {
                                "x": x - r, "y": y - r, "w": 2 * r, "h": 2 * r,
                                "x_pct": ((x - r) / W) * 100.0,
                                "y_pct": ((y - r) / H) * 100.0,
                                "w_pct": (2 * r / W) * 100.0,
                                "h_pct": (2 * r / H) * 100.0,
                            },
                            "font_info": {"estimated_size": r * 2, "is_symbol": True},
                            "editing_metadata": {
                                "word_id": f"symbol_{xref}_circle_{x}_{y}",
                                "editable": True,
                                "original_text": "Ø",
                                "text_type": "diameter_symbol",
                                "detection_method": "circle_detection"
                            }
                        }
                        symbols.append(symbol_data)

            # Détecter d'autres patterns géométriques pour symboles
            # (±, °, ', etc.)
            symbols.extend(self._detect_special_characters(gray, W, H, xref))

        except ImportError:
            logger.debug("OpenCV non disponible pour détection de symboles")
        except Exception as e:
            logger.debug(f"Erreur détection symboles: {e}")

        return symbols

    def _is_diameter_symbol_region(self, gray: np.ndarray, x: int, y: int, r: int) -> bool:
        """
        Vérifie si une région circulaire contient probablement un symbole de diamètre
        """
        try:
            # Extraire la région
            roi = gray[max(0, y - r - 2):y + r + 2, max(0, x - r - 2):x + r + 2]

            # Vérifier la présence d'une ligne diagonale (caractéristique du Ø)
            lines = cv2.HoughLinesP(roi, 1, np.pi / 180, threshold=5,
                                    minLineLength=r, maxLineGap=2)

            if lines is not None:
                for line in lines:
                    x1, y1, x2, y2 = line[0]
                    # Vérifier si la ligne est approximativement diagonale
                    angle = np.arctan2(y2 - y1, x2 - x1) * 180 / np.pi
                    if 30 <= abs(angle) <= 60:  # Ligne diagonale
                        return True

            return False
        except:
            return False

    def _deduplicate_and_filter_words(self, all_words: List[Dict]) -> List[Dict]:
        """
        Déduplique et filtre intelligemment les mots détectés par plusieurs passes OCR
        """
        if not all_words:
            return []

        # Grouper les mots par position approximative
        position_groups = {}
        tolerance = 5  # pixels

        for word in all_words:
            bbox = word["bbox_img"]
            center_x = bbox["x"] + bbox["w"] / 2
            center_y = bbox["y"] + bbox["h"] / 2

            # Trouver le groupe le plus proche
            group_key = None
            min_distance = float('inf')

            for existing_key in position_groups.keys():
                ex_x, ex_y = existing_key
                distance = ((center_x - ex_x) ** 2 + (center_y - ex_y) ** 2) ** 0.5

                if distance <= tolerance and distance < min_distance:
                    min_distance = distance
                    group_key = existing_key

            # Créer nouveau groupe si aucun trouvé
            if group_key is None:
                group_key = (center_x, center_y)
                position_groups[group_key] = []

            position_groups[group_key].append(word)

        # Sélectionner le meilleur mot de chaque groupe
        unique_words = []

        for group in position_groups.values():
            if len(group) == 1:
                unique_words.append(group[0])
            else:
                # Choisir le mot avec la meilleure combinaison confiance/pertinence
                best_word = max(group, key=lambda w: self._calculate_word_score(w))
                unique_words.append(best_word)

        return unique_words

    def _calculate_word_score(self, word: Dict) -> float:
        """
        Calcule un score pour un mot détecté (confiance + pertinence technique)
        """
        confidence = word.get("confidence", 0)
        text = word.get("text", "")
        text_type = word.get("editing_metadata", {}).get("text_type", "text")

        # Score de base sur la confiance
        score = confidence

        # Bonus pour types techniques importants
        type_bonuses = {
            'diameter': 20,
            'dimension': 15,
            'radius': 15,
            'section_line': 10,
            'annotation': 10,
            'angle': 10,
            'tolerance': 10,
            'decimal_number': 5
        }

        score += type_bonuses.get(text_type, 0)

        # Bonus pour pattern reconnaissables
        if re.match(r'^[øØ]\d+\.?\d*$', text):
            score += 25  # Diamètre bien formé
        elif re.match(r'^\d+\.?\d*$', text):
            score += 15  # Dimension bien formée
        elif re.match(r'^[A-Z]-[A-Z]$', text):
            score += 20  # Ligne de coupe bien formée

        # Malus pour texte trop court ou suspect
        if len(text) == 1 and not re.match(r'^[A-Z]$', text):
            score -= 20

        return score

    def _classify_technical_text_content(self, text: str) -> str:
        """
        Classification spécialisée pour éléments techniques de dessins
        """
        text_clean = text.strip()
        text_lower = text_clean.lower()

        # Dimensions avec symbole diamètre
        if re.match(r'^[øØ]\d+\.?\d*$', text_clean):
            return 'diameter'

        # Dimensions simples (chiffres avec décimales)
        elif re.match(r'^\d+\.?\d*$', text_clean):
            return 'dimension'

        # Rayons (R suivi de chiffres)
        elif re.match(r'^[rR]\d+\.?\d*$', text_clean):
            return 'radius'

        # Angles (degrés)
        elif re.match(r'^\d+\.?\d*°?$', text_clean):
            return 'angle'

        # Annotations de coupe (A-A, B-B, etc.)
        elif re.match(r'^[A-Z]-[A-Z]$', text_clean):
            return 'section_line'

        # Références de détail (Detail A, Detail C, etc.)
        elif re.match(r'^[Dd]etail\s+[A-Z]$', text_clean):
            return 'detail_reference'

        # Annotations simples (lettres seules)
        elif re.match(r'^[A-Z]\'?$', text_clean):
            return 'annotation'

        # Volumes et unités
        elif re.search(r'(cm3|mm3|cm²|mm²|ml)', text_lower):
            return 'volume_unit'

        # Tolérances (±)
        elif '±' in text_clean or '+/-' in text_clean:
            return 'tolerance'

        # Noms/marques (texte en majuscules)
        elif text_clean.isupper() and len(text_clean) > 2:
            return 'label'

        # Nombres avec virgule/point
        elif re.match(r'^\d+[,\.]\d+$', text_clean):
            return 'decimal_number'

        # Fractions
        elif '/' in text_clean and any(c.isdigit() for c in text_clean):
            return 'fraction'

        # Texte descriptif
        elif len(text_clean) > 5 and ' ' in text_clean:
            return 'description'

        else:
            return 'text'

    def _get_adaptive_confidence_threshold(self, text: str, config: str) -> int:
        """
        Seuil de confiance adaptatif selon le type de texte et la configuration OCR
        """
        text_type = self._classify_technical_text_content(text)

        # Seuils plus bas pour les éléments critiques des dessins techniques
        thresholds = {
            'diameter': 15,  # Très important - diamètres
            'dimension': 20,  # Important - cotes
            'radius': 25,  # Important - rayons
            'angle': 30,  # Modéré - angles
            'section_line': 25,  # Important - lignes de coupe
            'detail_reference': 30,  # Modéré - références
            'annotation': 20,  # Important - annotations
            'volume_unit': 35,  # Modéré - unités
            'tolerance': 25,  # Important - tolérances
            'label': 40,  # Standard - étiquettes
            'decimal_number': 20,  # Important - nombres décimaux
            'fraction': 30,  # Modéré - fractions
            'description': 50,  # Standard - descriptions
            'text': 40  # Standard - texte général
        }

        base_threshold = thresholds.get(text_type, 30)

        # Ajustement selon la configuration OCR
        if 'tessedit_char_whitelist' in config:
            base_threshold -= 10  # Plus tolérant avec whitelist

        return max(base_threshold, 10)  # Minimum 10%

    def _is_technical_annotation(self, text: str) -> bool:
        """
        Détermine si un texte est une annotation technique (accepter plus petites tailles)
        """
        text_type = self._classify_technical_text_content(text)
        return text_type in ['annotation', 'section_line', 'diameter', 'radius', 'dimension']


    def _estimate_font_properties(self, text: str, width: int, height: int) -> Dict:
        """
        Estime les propriétés de police basées sur les dimensions du texte
        """
        try:
            char_count = len(text)
            avg_char_width = width / char_count if char_count > 0 else width

            # Estimation de la taille de police (approximative)
            estimated_font_size = max(8, min(height * 0.8, 72))

            # Classification du style de texte
            is_bold = height > width / char_count * 1.2 if char_count > 0 else False
            is_uppercase = text.isupper() and len(text) > 1

            return {
                "estimated_size": round(estimated_font_size),
                "char_width": round(avg_char_width, 1),
                "line_height": height,
                "is_bold_likely": is_bold,
                "is_uppercase": is_uppercase,
                "text_density": char_count / (width * height) if width * height > 0 else 0
            }
        except:
            return {
                "estimated_size": 12,
                "char_width": 8,
                "line_height": height,
                "is_bold_likely": False,
                "is_uppercase": False,
                "text_density": 0
            }

    def _classify_text_content(self, text: str) -> str:
        """
        Classifie le type de contenu textuel pour l'édition appropriée
        """
        text_lower = text.lower().strip()

        # Numéros et identifiants
        if re.match(r'^\d+\.?\d*$', text):
            return 'number'
        elif re.match(r'^[A-Z]{2,}-[A-Z0-9]+-\d+$', text):
            return 'reference_id'
        elif re.match(r'^\d{1,2}[/.-]\d{1,2}[/.-]\d{4}$', text):
            return 'date'

        # Texte pharmaceutique
        elif any(term in text_lower for term in ['mg', 'ml', 'g', '%', 'µg']):
            return 'quantity'
        elif any(term in text_lower for term in ['pharmacopoeia', 'monograph', 'european']):
            return 'reference'
        elif len(text) > 20 and ' ' in text:
            return 'description'
        elif text.isupper() and len(text) > 2:
            return 'heading'
        else:
            return 'text'

    def _create_editable_text_elements(self, words: List[Dict], img_width: float, img_height: float) -> List[Dict]:
        """
        Crée des éléments de texte éditables optimisés avec regroupement intelligent
        """
        if not words:
            return []

        elements = []

        # Regroupement optionnel des mots adjacents
        if self.ocr_config.get('merge_adjacent_words', True):
            words = self._merge_adjacent_words(words)

        # Création des éléments éditables
        for idx, word in enumerate(words):
            bbox = word["bbox_img"]
            font_info = word.get("font_info", {})
            editing_meta = word.get("editing_metadata", {})

            # Style CSS dynamique basé sur les propriétés détectées
            element_style = self._generate_element_style(word, bbox, font_info)

            element = {
                "element_id": f"editable_text_{editing_meta.get('word_id', idx)}",
                "text": word["text"],
                "original_text": word["text"],
                "position": {
                    "left": bbox["x_pct"],
                    "top": bbox["y_pct"],
                    "width": bbox["w_pct"],
                    "height": bbox["h_pct"]
                },
                "style": element_style,
                "metadata": {
                    "confidence": word.get("confidence", 0),
                    "text_type": editing_meta.get("text_type", "text"),
                    "font_size": font_info.get("estimated_size", 12),
                    "is_bold": font_info.get("is_bold_likely", False),
                    "editable": True,
                    "validation_rules": self._get_validation_rules(editing_meta.get("text_type", "text"))
                },
                "events": {
                    "on_edit": "handleTextEdit",
                    "on_blur": "validateAndSave",
                    "on_focus": "highlightElement"
                }
            }

            elements.append(element)

        return elements

    def _merge_adjacent_words(self, words: List[Dict], threshold: int = None) -> List[Dict]:
        """
        Fusionne les mots adjacents pour former des éléments éditables plus cohérents
        """
        if not words or len(words) < 2:
            return words

        threshold = threshold or self.ocr_config.get('adjacent_threshold', 5)
        merged_words = []
        current_group = [words[0]]

        for i in range(1, len(words)):
            prev_word = current_group[-1]
            current_word = words[i]

            # Vérifier si les mots sont sur la même ligne et proches
            if self._are_words_adjacent(prev_word, current_word, threshold):
                current_group.append(current_word)
            else:
                # Finaliser le groupe actuel
                if len(current_group) == 1:
                    merged_words.append(current_group[0])
                else:
                    merged_words.append(self._merge_word_group(current_group))

                # Commencer un nouveau groupe
                current_group = [current_word]

        # Traiter le dernier groupe
        if len(current_group) == 1:
            merged_words.append(current_group[0])
        else:
            merged_words.append(self._merge_word_group(current_group))

        return merged_words

    def _are_words_adjacent(self, word1: Dict, word2: Dict, threshold: int) -> bool:
        """
        Détermine si deux mots sont adjacents et peuvent être fusionnés
        """
        bbox1 = word1["bbox_img"]
        bbox2 = word2["bbox_img"]

        # Vérifier l'alignement vertical (même ligne)
        y_overlap = abs(bbox1["y"] - bbox2["y"]) <= threshold
        height_similar = abs(bbox1["h"] - bbox2["h"]) <= threshold

        # Vérifier la proximité horizontale
        horizontal_gap = abs((bbox1["x"] + bbox1["w"]) - bbox2["x"])

        return y_overlap and height_similar and horizontal_gap <= threshold * 2

    def _merge_word_group(self, word_group: List[Dict]) -> Dict:
        """
        Fusionne un groupe de mots en un seul élément éditable
        """
        if len(word_group) == 1:
            return word_group[0]

        # Calculer le bbox englobant
        min_x = min(word["bbox_img"]["x"] for word in word_group)
        min_y = min(word["bbox_img"]["y"] for word in word_group)
        max_x = max(word["bbox_img"]["x"] + word["bbox_img"]["w"] for word in word_group)
        max_y = max(word["bbox_img"]["y"] + word["bbox_img"]["h"] for word in word_group)

        # Texture combinée
        combined_text = " ".join(word["text"] for word in word_group)

        # Confiance moyenne
        avg_confidence = sum(word.get("confidence", 0) for word in word_group) / len(word_group)

        # Premier mot comme base
        base_word = word_group[0].copy()

        # Mise à jour avec les données fusionnées
        base_word.update({
            "text": combined_text,
            "confidence": avg_confidence,
            "bbox_img": {
                "x": min_x,
                "y": min_y,
                "w": max_x - min_x,
                "h": max_y - min_y,
                "x_pct": (min_x / base_word["bbox_img"].get("image_width", 1)) * 100.0,
                "y_pct": (min_y / base_word["bbox_img"].get("image_height", 1)) * 100.0,
                "w_pct": ((max_x - min_x) / base_word["bbox_img"].get("image_width", 1)) * 100.0,
                "h_pct": ((max_y - min_y) / base_word["bbox_img"].get("image_height", 1)) * 100.0,
            },
            "editing_metadata": {
                **base_word.get("editing_metadata", {}),
                "is_merged": True,
                "original_word_count": len(word_group)
            }
        })

        return base_word

    def _generate_element_style(self, word: Dict, bbox: Dict, font_info: Dict) -> Dict:
        """
        Génère le style CSS pour un élément de texte éditable
        """
        text_type = word.get("editing_metadata", {}).get("text_type", "text")
        confidence = word.get("confidence", 100)

        # Style de base
        style = {
            "position": "absolute",
            "left": f"{bbox['x_pct']}%",
            "top": f"{bbox['y_pct']}%",
            "width": f"{bbox['w_pct']}%",
            "height": f"{bbox['h_pct']}%",
            "font-size": f"{font_info.get('estimated_size', 12)}px",
            "line-height": f"{bbox['h_pct']}%",
            "margin": "0",
            "padding": "1px",
            "border": "1px solid transparent",
            "background": "rgba(255, 255, 0, 0.1)",
            "cursor": "text",
            "z-index": "10",
            "white-space": "nowrap",
            "overflow": "hidden",
            "font-family": "'Arial', sans-serif"
        }

        # Styles spécifiques selon le type de texte
        if text_type == "number" or text_type == "quantity":
            style.update({
                "text-align": "right",
                "font-family": "'Courier New', monospace",
                "background": "rgba(0, 123, 255, 0.1)"
            })
        elif text_type == "heading":
            style.update({
                "font-weight": "bold",
                "background": "rgba(40, 167, 69, 0.1)"
            })
        elif text_type == "reference":
            style.update({
                "font-style": "italic",
                "background": "rgba(111, 66, 193, 0.1)"
            })
        elif text_type == "date":
            style.update({
                "background": "rgba(255, 193, 7, 0.1)"
            })

        # Ajustement selon la confiance OCR
        if confidence < 50:
            style.update({
                "border": "1px dashed #dc3545",
                "background": "rgba(220, 53, 69, 0.1)"
            })
        elif confidence < 75:
            style.update({
                "border": "1px dashed #ffc107"
            })

        return style

    def _get_validation_rules(self, text_type: str) -> Dict:
        """
        Retourne les règles de validation pour différents types de texte
        """
        rules = {
            "number": {
                "pattern": r"^\d+\.?\d*$",
                "message": "Doit être un nombre valide"
            },
            "date": {
                "pattern": r"^\d{1,2}[/.-]\d{1,2}[/.-]\d{4}$",
                "message": "Format de date requis: JJ/MM/AAAA"
            },
            "quantity": {
                "pattern": r"^\d+\.?\d*\s*(mg|ml|g|%|µg|kg|L)?$",
                "message": "Quantité avec unité optionnelle"
            },
            "reference_id": {
                "pattern": r"^[A-Z0-9\-/]+$",
                "message": "Identifiant de référence valide"
            }
        }

        return rules.get(text_type, {
            "pattern": r".*",
            "message": "Texte libre"
        })

    def _assess_ocr_quality(self, words: List[Dict]) -> Dict:
        """
        Évalue la qualité globale de l'OCR pour informer l'utilisateur
        """
        if not words:
            return {"overall": "poor", "confidence_avg": 0, "editable_count": 0}

        confidences = [word.get("confidence", 0) for word in words]
        avg_confidence = sum(confidences) / len(confidences)

        high_confidence_count = sum(1 for c in confidences if c >= 80)
        medium_confidence_count = sum(1 for c in confidences if 50 <= c < 80)
        low_confidence_count = sum(1 for c in confidences if c < 50)

        if avg_confidence >= 80:
            overall_quality = "excellent"
        elif avg_confidence >= 60:
            overall_quality = "good"
        elif avg_confidence >= 40:
            overall_quality = "fair"
        else:
            overall_quality = "poor"

        return {
            "overall": overall_quality,
            "confidence_avg": round(avg_confidence, 1),
            "editable_count": len(words),
            "quality_distribution": {
                "high": high_confidence_count,
                "medium": medium_confidence_count,
                "low": low_confidence_count
            },
            "recommendation": self._get_quality_recommendation(overall_quality, low_confidence_count)
        }

    def _get_quality_recommendation(self, quality: str, low_conf_count: int) -> str:
        """
        Génère une recommandation basée sur la qualité OCR
        """
        if quality == "poor":
            return "La qualité OCR est faible. Vérifiez manuellement les textes détectés."
        elif low_conf_count > 5:
            return f"{low_conf_count} éléments ont une confiance faible. Attention lors de l'édition."
        elif quality == "excellent":
            return "Excellente qualité OCR. Édition directe recommandée."
        else:
            return "Qualité OCR acceptable. Vérifiez les éléments marqués en rouge."

    def _generate_faithful_image_html_with_editable_text(self, image_element: Dict) -> str:
        """
        Génère le HTML pour une image avec texte éditable superposé - VERSION CORRIGÉE
        """
        ocr_overlay = image_element.get('ocr_overlay', {})
        editable_elements = ocr_overlay.get('editable_elements', [])
        image_data = image_element.get('image_data', '')
        image_info = ocr_overlay.get('image_pixel_size', {})
        ocr_quality = ocr_overlay.get('ocr_quality', {})

        # ID unique pour l'image
        image_id = f"editable-image-p{image_element['page']}-{image_element['index']}"

        html = f'''
        <div class="editable-image-container" id="{image_id}" 
             style="position: relative; margin: 20px 0; display: inline-block; max-width: 100%;">

            <!-- Barre d'informations OCR -->
            <div class="ocr-info-bar" style="background: #f8f9fa; padding: 8px 12px; border: 1px solid #dee2e6; 
                 border-radius: 6px 6px 0 0; font-size: 12px; color: #6c757d;">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <span>
                        <i class="fas fa-eye me-1" style="color: #28a745;"></i>
                        OCR: {ocr_quality.get('overall', 'N/A').title()} 
                        ({ocr_quality.get('confidence_avg', 0)}% confiance)
                    </span>
                    <span>
                        <i class="fas fa-edit me-1" style="color: #007bff;"></i>
                        {len(editable_elements)} éléments éditables
                    </span>
                    <button type="button" class="btn btn-sm btn-outline-primary toggle-edit-mode" 
                            data-target="{image_id}" style="font-size: 11px; padding: 2px 8px;">
                        <i class="fas fa-edit me-1"></i>Mode Édition
                    </button>
                </div>
                {f'<div class="mt-1"><small class="text-warning"><i class="fas fa-exclamation-triangle me-1"></i>{ocr_quality.get("recommendation", "")}</small></div>' if ocr_quality.get("recommendation") else ''}
            </div>

            <!-- Container de l'image avec overlay éditable -->
            <div class="image-with-overlay" style="position: relative; border: 1px solid #dee2e6; 
                 border-top: none; border-radius: 0 0 6px 6px; overflow: hidden;">

                <!-- Image de base NON éditable avec protection -->
                <img src="{image_data}" 
                     alt="Image {image_element['index']}" 
                     class="base-image non-editable-image"
                     contenteditable="false"
                     style="display: block; max-width: 100%; height: auto; position: relative; z-index: 1;
                            pointer-events: auto; user-select: none;"
                     data-image-index="{image_element['index']}"
                     data-page="{image_element['page']}"
                     data-original-width="{image_info.get('width', 'auto')}"
                     data-original-height="{image_info.get('height', 'auto')}"
                     onmousedown="return false;"
                     ondragstart="return false;"
                     onselectstart="return false;">

                <!-- Overlay des textes éditables avec isolation d'événements -->
                <div class="text-overlay-container edit-mode-hidden" 
                     style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; z-index: 10; 
                            pointer-events: none; background: transparent;">
        '''

        # Ajouter chaque élément de texte éditable
        for element in editable_elements:
            style_props = []
            for prop, value in element['style'].items():
                style_props.append(f"{prop}: {value}")

            style_string = "; ".join(style_props)

            confidence = element['metadata'].get('confidence', 100)
            text_type = element['metadata'].get('text_type', 'text')
            validation_rules = element['metadata'].get('validation_rules', {})

            # Classes CSS dynamiques
            css_classes = [
                'editable-text-element',
                f'text-type-{text_type}',
                f'confidence-{self._get_confidence_class(confidence)}'
            ]

            html += f'''
                <!-- Élément éditable avec isolation complète -->
                <div class="{' '.join(css_classes)}"
                     id="{element['element_id']}"
                     contenteditable="false"
                     spellcheck="false"
                     data-original-text="{element['original_text']}"
                     data-text-type="{text_type}"
                     data-confidence="{confidence}"
                     data-validation-pattern="{validation_rules.get('pattern', '')}"
                     data-validation-message="{validation_rules.get('message', '')}"
                     data-image-id="{image_id}"
                     style="{style_string}; pointer-events: auto; z-index: 15;"
                     title="Texte éditable - Confiance: {confidence}% - Type: {text_type}"
                     onblur="ImageTextEditor.saveTextEdit(this); event.stopPropagation();"
                     onfocus="ImageTextEditor.highlightTextElement(this); event.stopPropagation();"
                     oninput="ImageTextEditor.validateTextInput(this); event.stopPropagation();"
                     onmousedown="event.stopPropagation();"
                     onclick="event.stopPropagation();"
                     onkeydown="ImageTextEditor.handleKeydown(event); event.stopPropagation();">
                    {element['text']}
                </div>
            '''

        html += '''
                </div>

                <!-- Overlay transparent pour bloquer les clics sur l'image en mode édition -->
                <div class="image-click-blocker" 
                     style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; z-index: 5;
                            pointer-events: none; background: transparent; display: none;"
                     onmousedown="event.preventDefault(); event.stopPropagation(); return false;"
                     onclick="event.preventDefault(); event.stopPropagation(); return false;"></div>
            </div>

            <!-- Panneau de contrôles avancés -->
            <div class="advanced-controls" style="display: none; background: #f8f9fa; padding: 10px; 
                 border: 1px solid #dee2e6; border-top: none; border-radius: 0 0 6px 6px; font-size: 12px;">
                <div class="row">
                    <div class="col-md-6">
                        <label class="form-label">Zoom OCR:</label>
                        <input type="range" class="form-range" min="100" max="300" value="100" 
                               onchange="ImageTextEditor.adjustOCRZoom(this)" data-target="''' + image_id + '''">
                    </div>
                    <div class="col-md-6">
                        <label class="form-label">Affichage:</label>
                        <div class="btn-group btn-group-sm" role="group">
                            <input type="radio" class="btn-check" name="display-mode-''' + image_id + '''" 
                                   id="show-all-''' + image_id + '''" checked onchange="ImageTextEditor.toggleTextVisibility(this)">
                            <label class="btn btn-outline-secondary" for="show-all-''' + image_id + '''">Tout</label>

                            <input type="radio" class="btn-check" name="display-mode-''' + image_id + '''" 
                                   id="show-confident-''' + image_id + '''" onchange="ImageTextEditor.toggleTextVisibility(this)">
                            <label class="btn btn-outline-secondary" for="show-confident-''' + image_id + '''">Confiance élevée</label>

                            <input type="radio" class="btn-check" name="display-mode-''' + image_id + '''" 
                                   id="show-uncertain-''' + image_id + '''" onchange="ImageTextEditor.toggleTextVisibility(this)">
                            <label class="btn btn-outline-secondary" for="show-uncertain-''' + image_id + '''">À vérifier</label>
                        </div>
                    </div>
                </div>

                <div class="mt-2">
                    <button type="button" class="btn btn-sm btn-success me-2" onclick="ImageTextEditor.saveAllEdits('''' + image_id + '''')">
                        <i class="fas fa-save me-1"></i>Sauvegarder tout
                    </button>
                    <button type="button" class="btn btn-sm btn-warning me-2" onclick="ImageTextEditor.resetAllEdits('''' + image_id + '''')">
                        <i class="fas fa-undo me-1"></i>Annuler tout
                    </button>
                    <button type="button" class="btn btn-sm btn-info" onclick="ImageTextEditor.exportImageWithEdits('''' + image_id + '''')">
                        <i class="fas fa-download me-1"></i>Exporter
                    </button>
                </div>
            </div>
        </div>
        '''

        return html

    def _get_confidence_class(self, confidence: int) -> str:
        """Retourne la classe CSS selon la confiance"""
        if confidence >= 80:
            return "high"
        elif confidence >= 50:
            return "medium"
        else:
            return "low"

    def _generate_editable_image_css(self) -> str:
        """
        Génère les styles CSS pour l'édition de texte sur images - VERSION CORRIGÉE
        """
        return '''
        <style>
        /* Protection de l'image de base */
        .non-editable-image {
            pointer-events: auto !important;
            user-select: none !important;
            -webkit-user-select: none !important;
            -moz-user-select: none !important;
            -ms-user-select: none !important;
            contenteditable: false !important;
        }

        .non-editable-image:focus {
            outline: none !important;
            border: none !important;
        }

        /* Empêcher l'édition de l'image même si elle hérite de contenteditable */
        [contenteditable="true"] .non-editable-image {
            contenteditable: false !important;
            pointer-events: auto !important;
        }

        /* Conteneur principal d'image éditable */
        .editable-image-container {
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
            border-radius: 8px;
            overflow: hidden;
            background: white;
            /* Empêcher l'héritage contenteditable */
            contenteditable: false !important;
        }

        .editable-image-container * {
            /* Par défaut, rien n'est éditable sauf les éléments spécifiquement marqués */
            contenteditable: inherit;
        }

        .editable-image-container .base-image {
            transition: filter 0.3s ease;
            /* Protection absolue contre l'édition */
            contenteditable: false !important;
            pointer-events: auto !important;
        }

        .editable-image-container.edit-mode-active .base-image {
            filter: brightness(1.1) contrast(1.05);
            /* En mode édition, empêcher l'interaction avec l'image */
            pointer-events: none !important;
        }

        /* Bloquer les clics sur l'image en mode édition */
        .editable-image-container.edit-mode-active .image-click-blocker {
            display: block !important;
            pointer-events: auto !important;
            z-index: 2 !important;
        }

        /* Éléments de texte éditables */
        .editable-text-element {
            transition: all 0.2s ease;
            border-radius: 2px;
            font-family: inherit;
            resize: none;
            outline: none;
            text-overflow: ellipsis;
            /* Isolation complète des événements */
            pointer-events: auto !important;
            z-index: 15 !important;
            position: absolute !important;
            background: rgba(255, 255, 255, 0.9) !important;
            border: 1px solid transparent !important;
            padding: 2px 4px !important;
            min-height: 1em !important;
            line-height: 1.2 !important;
            overflow: hidden !important;
            word-wrap: break-word !important;
        }

        /* États d'édition clairs */
        .edit-mode-hidden .editable-text-element {
            contenteditable: false !important;
            pointer-events: none !important;
            opacity: 0.8;
            background: rgba(255, 255, 0, 0.3) !important;
            border: 1px solid rgba(255, 193, 7, 0.5) !important;
        }

        .edit-mode-active .editable-text-element {
            contenteditable: true !important;
            pointer-events: auto !important;
            opacity: 1;
            cursor: text !important;
        }

        .editable-text-element:hover {
            transform: scale(1.02);
            box-shadow: 0 2px 8px rgba(0,0,0,0.2);
            z-index: 20 !important;
            border: 2px solid #007bff !important;
        }

        .editable-text-element:focus {
            transform: scale(1.05) !important;
            box-shadow: 0 4px 12px rgba(0,123,255,0.4) !important;
            z-index: 25 !important;
            border: 2px solid #007bff !important;
            background: rgba(255,255,255,0.98) !important;
            outline: 2px solid rgba(0,123,255,0.3) !important;
            outline-offset: 2px !important;
        }

        /* Empêcher la sélection de texte sur l'image */
        .image-with-overlay {
            user-select: none;
            -webkit-user-select: none;
            -moz-user-select: none;
            -ms-user-select: none;
        }

        /* Permettre la sélection seulement dans les éléments éditables */
        .editable-text-element {
            user-select: text !important;
            -webkit-user-select: text !important;
            -moz-user-select: text !important;
            -ms-user-select: text !important;
        }

        /* Styles selon la confiance OCR */
        .editable-text-element.confidence-high {
            border-color: rgba(40, 167, 69, 0.7) !important;
            background: rgba(40, 167, 69, 0.1) !important;
        }

        .editable-text-element.confidence-medium {
            border-color: rgba(255, 193, 7, 0.7) !important;
            background: rgba(255, 193, 7, 0.15) !important;
        }

        .editable-text-element.confidence-low {
            border-color: rgba(220, 53, 69, 0.7) !important;
            background: rgba(220, 53, 69, 0.15) !important;
            animation: pulse-warning 3s infinite;
        }

        @keyframes pulse-warning {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.7; }
        }

        /* Styles selon le type de texte */
        .editable-text-element.text-type-number,
        .editable-text-element.text-type-quantity,
        .editable-text-element.text-type-dimension,
        .editable-text-element.text-type-diameter {
            font-family: 'Courier New', monospace !important;
            text-align: center !important;
            font-weight: bold !important;
            background: rgba(0, 123, 255, 0.15) !important;
        }

        .editable-text-element.text-type-annotation,
        .editable-text-element.text-type-section_line {
            font-weight: bold !important;
            text-align: center !important;
            background: rgba(40, 167, 69, 0.15) !important;
        }

        .editable-text-element.text-type-label {
            font-weight: bold !important;
            background: rgba(111, 66, 193, 0.15) !important;
        }

        /* États de validation */
        .editable-text-element.invalid {
            border: 2px solid #dc3545 !important;
            background: rgba(220, 53, 69, 0.2) !important;
            animation: shake 0.5s ease-in-out;
        }

        @keyframes shake {
            0%, 100% { transform: translateX(0); }
            25% { transform: translateX(-2px); }
            75% { transform: translateX(2px); }
        }

        .editable-text-element.valid {
            border: 2px solid #28a745 !important;
            background: rgba(40, 167, 69, 0.1) !important;
        }

        .editable-text-element.modified {
            border-left: 4px solid #ffc107 !important;
            background: rgba(255, 193, 7, 0.2) !important;
        }

        /* Mode édition global */
        .edit-mode-active .text-overlay-container {
            pointer-events: auto !important;
            z-index: 10 !important;
        }

        .edit-mode-hidden .text-overlay-container {
            pointer-events: none !important;
            z-index: 5 !important;
        }

        /* Responsive */
        @media (max-width: 768px) {
            .editable-text-element {
                font-size: 11px !important;
                min-height: 14px !important;
                padding: 1px 2px !important;
            }
        }

        /* Impression */
        @media print {
            .text-overlay-container {
                pointer-events: none !important;
            }

            .editable-text-element {
                border: none !important;
                background: transparent !important;
                box-shadow: none !important;
                transform: none !important;
            }

            .ocr-info-bar,
            .advanced-controls,
            .image-click-blocker {
                display: none !important;
            }
        }
        </style>
        '''

    def _generate_editable_image_javascript(self) -> str:
        """
        Génère le JavaScript pour l'interaction avec les textes éditables
        """
        return '''
        <script>
        // État global de l'éditeur d'images
        const ImageTextEditor = {
            activeElements: new Map(),
            originalValues: new Map(),
            modifiedElements: new Set(),
            validationRules: new Map(),

            // Initialisation
            init() {
                this.bindEvents();
                this.loadValidationRules();
            },

            // Liaison des événements
            bindEvents() {
                // Boutons toggle mode édition
                document.querySelectorAll('.toggle-edit-mode').forEach(btn => {
                    btn.addEventListener('click', (e) => {
                        this.toggleEditMode(e.target.dataset.target);
                    });
                });

                // Éléments éditables
                document.querySelectorAll('.editable-text-element').forEach(element => {
                    this.originalValues.set(element.id, element.textContent);

                    element.addEventListener('input', (e) => {
                        this.handleTextInput(e.target);
                    });

                    element.addEventListener('blur', (e) => {
                        this.saveTextEdit(e.target);
                    });

                    element.addEventListener('focus', (e) => {
                        this.highlightTextElement(e.target);
                    });

                    element.addEventListener('keydown', (e) => {
                        this.handleKeydown(e);
                    });
                });
            },

            // Chargement des règles de validation
            loadValidationRules() {
                document.querySelectorAll('.editable-text-element').forEach(element => {
                    const pattern = element.dataset.validationPattern;
                    const message = element.dataset.validationMessage;

                    if (pattern) {
                        this.validationRules.set(element.id, {
                            pattern: new RegExp(pattern),
                            message: message
                        });
                    }
                });
            },

            // Toggle mode édition
            toggleEditMode(imageId) {
                const container = document.getElementById(imageId);
                const btn = container.querySelector('.toggle-edit-mode');
                const overlay = container.querySelector('.text-overlay-container');
                const controls = container.querySelector('.advanced-controls');

                const isActive = container.classList.contains('edit-mode-active');

                if (isActive) {
                    // Désactiver le mode édition
                    container.classList.remove('edit-mode-active');
                    container.classList.add('edit-mode-hidden');
                    overlay.style.pointerEvents = 'none';
                    btn.classList.remove('active');
                    btn.innerHTML = '<i class="fas fa-edit me-1"></i>Mode Édition';
                    controls.style.display = 'none';

                    // Désactiver contenteditable
                    container.querySelectorAll('.editable-text-element').forEach(el => {
                        el.contentEditable = 'false';
                    });
                } else {
                    // Activer le mode édition
                    container.classList.add('edit-mode-active');
                    container.classList.remove('edit-mode-hidden');
                    overlay.style.pointerEvents = 'auto';
                    btn.classList.add('active');
                    btn.innerHTML = '<i class="fas fa-times me-1"></i>Arrêter l\\'édition';
                    controls.style.display = 'block';

                    // Activer contenteditable
                    container.querySelectorAll('.editable-text-element').forEach(el => {
                        el.contentEditable = 'true';
                    });
                }
            },

            // Gestion de la saisie de texte
            handleTextInput(element) {
                const originalValue = this.originalValues.get(element.id);
                const currentValue = element.textContent;

                // Marquer comme modifié
                if (currentValue !== originalValue) {
                    this.modifiedElements.add(element.id);
                    element.classList.add('modified');
                } else {
                    this.modifiedElements.delete(element.id);
                    element.classList.remove('modified');
                }

                // Validation en temps réel
                this.validateTextInput(element);

                // Ajustement automatique de la taille
                this.autoResizeElement(element);
            },

            // Validation de la saisie
            validateTextInput(element) {
                const rules = this.validationRules.get(element.id);
                const value = element.textContent.trim();

                // Supprimer les classes de validation précédentes
                element.classList.remove('valid', 'invalid');

                if (rules && value) {
                    if (rules.pattern.test(value)) {
                        element.classList.add('valid');
                        element.title = 'Valeur valide';
                    } else {
                        element.classList.add('invalid');
                        element.title = rules.message || 'Valeur invalide';
                    }
                }
            },

            // Ajustement automatique de la taille
            autoResizeElement(element) {
                const text = element.textContent;
                const textType = element.dataset.textType;

                // Pour les nombres et quantités, ajuster la largeur
                if (textType === 'number' || textType === 'quantity') {
                    const charCount = text.length;
                    const minWidth = Math.max(charCount * 8, 20);
                    element.style.minWidth = minWidth + 'px';
                }
            },

            // Gestion des raccourcis clavier
            handleKeydown(e) {
                const element = e.target;

                switch(e.key) {
                    case 'Escape':
                        this.cancelEdit(element);
                        e.preventDefault();
                        break;
                    case 'Enter':
                        if (!e.shiftKey) {
                            element.blur();
                            e.preventDefault();
                        }
                        break;
                    case 'Tab':
                        this.focusNextElement(element, !e.shiftKey);
                        e.preventDefault();
                        break;
                }
            },

            // Annuler l'édition
            cancelEdit(element) {
                const originalValue = this.originalValues.get(element.id);
                element.textContent = originalValue;
                element.classList.remove('modified', 'valid', 'invalid');
                this.modifiedElements.delete(element.id);
                element.blur();
            },

            // Focus sur l'élément suivant
            focusNextElement(currentElement, forward = true) {
                const container = currentElement.closest('.editable-image-container');
                const elements = Array.from(container.querySelectorAll('.editable-text-element'));
                const currentIndex = elements.indexOf(currentElement);

                let nextIndex;
                if (forward) {
                    nextIndex = (currentIndex + 1) % elements.length;
                } else {
                    nextIndex = (currentIndex - 1 + elements.length) % elements.length;
                }

                elements[nextIndex].focus();
            },

            // Mise en surbrillance d'un élément
            highlightTextElement(element) {
                // Supprimer la surbrillance des autres éléments
                document.querySelectorAll('.editable-text-element.highlighted').forEach(el => {
                    el.classList.remove('highlighted');
                });

                // Ajouter la surbrillance à l'élément actuel
                element.classList.add('highlighted');

                // Afficher les informations dans la console (ou dans un panel d'info)
                const info = {
                    text: element.textContent,
                    type: element.dataset.textType,
                    confidence: element.dataset.confidence,
                    modified: this.modifiedElements.has(element.id)
                };

                console.log('Élément sélectionné:', info);
            },

            // Sauvegarde d'un élément
            saveTextEdit(element) {
                const imageId = element.dataset.imageId;
                const elementId = element.id;
                const newValue = element.textContent.trim();
                const originalValue = this.originalValues.get(elementId);

                // Validation finale
                this.validateTextInput(element);

                if (element.classList.contains('invalid')) {
                    // Optionnel: empêcher la sauvegarde si invalide
                    // return false;
                }

                // Enregistrer la modification
                if (newValue !== originalValue) {
                    this.recordChange(imageId, elementId, originalValue, newValue);
                }

                // Notification visuelle
                this.showSaveNotification(element);
            },

            // Enregistrement d'un changement
            recordChange(imageId, elementId, oldValue, newValue) {
                const change = {
                    imageId: imageId,
                    elementId: elementId,
                    oldValue: oldValue,
                    newValue: newValue,
                    timestamp: new Date().toISOString(),
                    type: 'text_edit'
                };

                // Envoyer au serveur ou stocker localement
                console.log('Changement enregistré:', change);

                // Exemple d'envoi AJAX (à adapter selon votre backend)
                /*
                fetch('/api/documents/save-image-text-edit/', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value
                    },
                    body: JSON.stringify(change)
                });
                */
            },

            // Notification de sauvegarde
            showSaveNotification(element) {
                const originalBackground = element.style.background;
                element.style.background = 'rgba(40, 167, 69, 0.3)';

                setTimeout(() => {
                    element.style.background = originalBackground;
                }, 1000);
            },

            // Sauvegarder toutes les modifications d'une image
            saveAllEdits(imageId) {
                const container = document.getElementById(imageId);
                const modifiedElements = container.querySelectorAll('.editable-text-element.modified');

                modifiedElements.forEach(element => {
                    this.saveTextEdit(element);
                });

                alert(`${modifiedElements.length} modifications sauvegardées.`);
            },

            // Annuler toutes les modifications
            resetAllEdits(imageId) {
                if (!confirm('Êtes-vous sûr de vouloir annuler toutes les modifications ?')) {
                    return;
                }

                const container = document.getElementById(imageId);
                const modifiedElements = container.querySelectorAll('.editable-text-element.modified');

                modifiedElements.forEach(element => {
                    this.cancelEdit(element);
                });

                alert(`${modifiedElements.length} modifications annulées.`);
            },

            // Basculer la visibilité des éléments
            toggleTextVisibility(radioButton) {
                const imageId = radioButton.name.replace('display-mode-', '');
                const container = document.getElementById(imageId);
                const elements = container.querySelectorAll('.editable-text-element');

                elements.forEach(element => {
                    element.style.display = 'block'; // Reset
                });

                switch(radioButton.id) {
                    case `show-confident-${imageId}`:
                        elements.forEach(element => {
                            if (!element.classList.contains('confidence-high')) {
                                element.style.display = 'none';
                            }
                        });
                        break;
                    case `show-uncertain-${imageId}`:
                        elements.forEach(element => {
                            if (!element.classList.contains('confidence-low') && 
                                !element.classList.contains('confidence-medium')) {
                                element.style.display = 'none';
                            }
                        });
                        break;
                    // 'show-all' ne fait rien, tous les éléments restent visibles
                }
            },

            // Ajuster le zoom OCR
            adjustOCRZoom(slider) {
                const zoomValue = slider.value;
                const imageId = slider.dataset.target;
                const container = document.getElementById(imageId);
                const textElements = container.querySelectorAll('.editable-text-element');

                const scaleFactor = zoomValue / 100;

                textElements.forEach(element => {
                    const fontSize = element.style.fontSize;
                    const baseFontSize = parseInt(fontSize) || 12;
                    element.style.fontSize = (baseFontSize * scaleFactor) + 'px';
                });
            },

            // Exporter l'image avec les modifications
            exportImageWithEdits(imageId) {
                const container = document.getElementById(imageId);
                const modifications = {};

                container.querySelectorAll('.editable-text-element.modified').forEach(element => {
                    modifications[element.id] = {
                        original: this.originalValues.get(element.id),
                        modified: element.textContent,
                        type: element.dataset.textType,
                        confidence: element.dataset.confidence
                    };
                });

                // Créer et télécharger un fichier JSON avec les modifications
                const data = {
                    imageId: imageId,
                    modifications: modifications,
                    exportDate: new Date().toISOString()
                };

                const blob = new Blob([JSON.stringify(data, null, 2)], 
                                    {type: 'application/json'});
                const url = URL.createObjectURL(blob);

                const a = document.createElement('a');
                a.href = url;
                a.download = `image-edits-${imageId}.json`;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                URL.revokeObjectURL(url);
            }
        };

        // Fonctions globales pour les événements inline
        function saveTextEdit(element) {
            ImageTextEditor.saveTextEdit(element);
        }

        function highlightTextElement(element) {
            ImageTextEditor.highlightTextElement(element);
        }

        function validateTextInput(element) {
            ImageTextEditor.validateTextInput(element);
        }

        function toggleTextVisibility(radioButton) {
            ImageTextEditor.toggleTextVisibility(radioButton);
        }

        function adjustOCRZoom(slider) {
            ImageTextEditor.adjustOCRZoom(slider);
        }

        function saveAllEdits(imageId) {
            ImageTextEditor.saveAllEdits(imageId);
        }

        function resetAllEdits(imageId) {
            ImageTextEditor.resetAllEdits(imageId);
        }

        function exportImageWithEdits(imageId) {
            ImageTextEditor.exportImageWithEdits(imageId);
        }

        // Initialisation au chargement du document
        document.addEventListener('DOMContentLoaded', function() {
            ImageTextEditor.init();
        });
        </script>
        '''

    def extract_pdf_content_faithful(self, file_path: str) -> Dict:
        """
        Extraction PDF avec préservation complète et fidèle de la structure
        """
        logger.info(f"🔍 Début extraction fidèle: {os.path.basename(file_path)}")

        if not os.path.exists(file_path):
            return self._create_error_result(f"Fichier non trouvé: {file_path}")

        content = {
            'text': '',
            'html': '',
            'pages': [],
            'extracted': False,
            'type': 'pdf',
            'extraction_method': 'faithful_pymupdf',
            'structure': {
                'elements': [],
                'images': [],
                'tables': [],
                'text_blocks': [],
                'metadata': {}
            },
            'errors': []
        }

        # Extraction avec PyMuPDF amélioré
        if 'pymupdf' in self.available_processors:
            try:
                result = self._extract_with_faithful_pymupdf(file_path)
                if result and result.get('extracted', False):
                    content.update(result)
                    logger.info("✅ Extraction PyMuPDF fidèle réussie")
                    return content
            except Exception as e:
                logger.error(f"❌ Erreur PyMuPDF fidèle: {e}")
                content['errors'].append(f"PyMuPDF: {str(e)}")

        # Fallback avec double extraction (PyMuPDF + pdfplumber)
        if 'pdfplumber' in self.available_processors:
            try:
                result = self._extract_with_dual_approach(file_path)
                if result and result.get('extracted', False):
                    content.update(result)
                    logger.info("✅ Extraction double approche réussie")
                    return content
            except Exception as e:
                logger.error(f"❌ Erreur double approche: {e}")

        return self._extract_pdf_fallback(file_path)

    def _extract_with_faithful_pymupdf(self, file_path: str) -> Dict:
        """
        Extraction PyMuPDF avec algorithme de détection de tableaux amélioré
        """
        fitz = self.pdf_libraries['pymupdf']

        try:
            doc = fitz.open(file_path)

            content = {
                'text': '',
                'html': '',
                'pages': [],
                'extracted': True,
                'type': 'pdf',
                'extraction_method': 'faithful_pymupdf',
                'structure': {
                    'elements': [],
                    'images': [],
                    'tables': [],
                    'text_blocks': [],
                    'metadata': {}
                }
            }

            # Métadonnées du document
            metadata = doc.metadata or {}
            content['structure']['metadata'] = {
                'title': metadata.get('title', ''),
                'author': metadata.get('author', ''),
                'pages_count': doc.page_count,
                'creation_date': metadata.get('creationDate', ''),
            }

            # Traiter chaque page avec extraction fidèle
            for page_num in range(doc.page_count):
                try:
                    page = doc.load_page(page_num)
                    page_data = self._process_faithful_page(page, page_num + 1, doc)

                    # CORRECTION: Vérifier que page_data n'est pas None
                    if page_data:
                        content['pages'].append(page_data)
                        content['text'] += page_data['text'] + "\n\n"

                        # Agrégation des éléments structurés avec vérification None
                        content['structure']['elements'].extend(page_data.get('elements', []) or [])
                        content['structure']['images'].extend(page_data.get('images', []) or [])
                        content['structure']['tables'].extend(page_data.get('tables', []) or [])
                        content['structure']['text_blocks'].extend(page_data.get('text_blocks', []) or [])
                    else:
                        logger.warning(f"Page {page_num + 1} n'a pas pu être traitée - page_data est None")
                        # Ajouter une page vide pour maintenir la cohérence
                        content['pages'].append({
                            'page_number': page_num + 1,
                            'text': '',
                            'page_dimensions': {'width': 0, 'height': 0},
                            'elements': [],
                            'images': [],
                            'tables': [],
                            'text_blocks': [],
                            'chars_count': 0
                        })

                except Exception as page_error:
                    logger.warning(f"Erreur page {page_num + 1}: {page_error}")
                    # Ajouter une page d'erreur pour maintenir la cohérence
                    content['pages'].append({
                        'page_number': page_num + 1,
                        'text': f'Erreur lors du traitement de la page {page_num + 1}',
                        'page_dimensions': {'width': 0, 'height': 0},
                        'elements': [],
                        'images': [],
                        'tables': [],
                        'text_blocks': [],
                        'chars_count': 0,
                        'error': str(page_error)
                    })
                    continue

            # Générer le HTML fidèle
            content['html'] = self._generate_faithful_html(content)

            doc.close()
            return content

        except Exception as e:
            logger.error(f"Erreur extraction PyMuPDF fidèle: {e}")
            return {'extracted': False, 'error': str(e)}
    def _process_faithful_page(self, page, page_num: int, doc) -> Dict:
        """
        Version modifiée pour utiliser l'OCR éditable
        """
        try:
            # Obtenir les dimensions de la page
            page_rect = page.rect
            page_width = page_rect.width
            page_height = page_rect.height

            # Extraction du texte avec dictionnaire détaillé
            text_dict = page.get_text("dict")
            page_text = page.get_text()

            # Structures de données pour les éléments
            elements = []
            images = []
            tables = []
            text_blocks = []

            # 1. EXTRACTION DES TABLEAUX FIDÈLE
            tables_found = self._extract_faithful_tables(page, text_dict, page_num, page_width, page_height)
            tables.extend(tables_found)
            elements.extend(tables_found)

            # 2. EXTRACTION DES IMAGES avec OCR ÉDITABLE
            image_list = page.get_images(full=True)
            for img_index, img in enumerate(image_list):
                try:
                    img_rects = page.get_image_rects(img[0])
                    for rect in img_rects:
                        img_base64 = self._extract_image_base64(doc, img[0])

                        image_data = {
                            'type': 'image',
                            'page': page_num,
                            'index': img_index,
                            'xref': img[0],
                            'position': {
                                'x': float(rect.x0), 'y': float(rect.y0),
                                'width': float(rect.width), 'height': float(rect.height),
                                'x_percent': (rect.x0 / page_width) * 100,
                                'y_percent': (rect.y0 / page_height) * 100,
                                'width_percent': (rect.width / page_width) * 100,
                                'height_percent': (rect.height / page_height) * 100
                            },
                            'image_data': img_base64,
                            'ocr_overlay': None
                        }

                        # ⭐ NOUVEAU : OCR éditable avec éléments interactifs
                        if OCR_AVAILABLE:
                            ocr = self._ocr_image_words_editable(doc, img[0], rect)
                            image_data['ocr_overlay'] = ocr

                        images.append(image_data)
                        elements.append(image_data)

                except Exception as img_error:
                    logger.warning(f"Erreur extraction image {img_index}: {img_error}")

            # 3. EXTRACTION DES BLOCS DE TEXTE (hors tableaux)
            text_blocks_found = self._extract_faithful_text_blocks(
                text_dict, page_num, page_width, page_height, tables
            )
            text_blocks.extend(text_blocks_found)
            elements.extend(text_blocks_found)

            # Trier tous les éléments par position
            elements.sort(key=lambda x: (x['position']['y'], x['position']['x']))

            return {
                'page_number': page_num,
                'text': page_text,
                'page_dimensions': {
                    'width': page_width,
                    'height': page_height
                },
                'elements': elements,
                'images': images,
                'tables': tables,
                'text_blocks': text_blocks,
                'chars_count': len(page_text)
            }

        except Exception as e:
            logger.error(f"Erreur traitement page fidèle {page_num}: {e}")
            return None

    def _extract_faithful_tables(self, page, text_dict, page_num, page_width, page_height):
        tables = []
        try:
            if hasattr(page, 'find_tables'):
                found_tables = page.find_tables()
                for idx, tab in enumerate(found_tables):
                    bbox = tab.bbox
                    table_data = tab.extract()
                    if not table_data:
                        table_data = self._extract_table_with_pdfplumber(page_num, bbox)
                    if table_data:
                        tables.append(
                            self._process_faithful_table(tab, table_data, idx, page_num, page_width, page_height))

            # fallback si rien trouvé
            if not tables:
                tables = self._detect_tables_geometric_analysis(page, text_dict, page_num, page_width, page_height)
        except Exception as e:
            logger.error(f"Erreur extraction tableaux: {e}")
        return tables

    def _extract_table_with_pdfplumber(self, page_num, bbox):
        import pdfplumber
        tables_data = []
        with pdfplumber.open(self.current_pdf_path) as pdf:
            page_plumber = pdf.pages[page_num - 1]
            cropped = page_plumber.crop(bbox)
            extracted = cropped.extract_table()
            if extracted:
                tables_data = extracted
        return tables_data

    def _process_faithful_table(self, table_obj, table_data: List[List], tab_index: int,
                                page_num: int, page_width: float, page_height: float) -> Dict:
        """
        Traite un tableau détecté pour préserver sa structure fidèle
        """
        try:
            bbox = table_obj.bbox

            # Nettoyer et structurer les données du tableau
            cleaned_data = self._clean_and_structure_table_data(table_data)

            # Analyser la structure des colonnes
            column_info = self._analyze_table_columns(cleaned_data, bbox, page_width)

            # Détecter le header du tableau
            header_info = self._detect_table_header(cleaned_data)

            table_info = {
                'type': 'table',
                'page': page_num,
                'index': tab_index,
                'position': {
                    'x': float(bbox[0]),
                    'y': float(bbox[1]),
                    'width': float(bbox[2] - bbox[0]),
                    'height': float(bbox[3] - bbox[1]),
                    'x_percent': (bbox[0] / page_width) * 100,
                    'y_percent': (bbox[1] / page_height) * 100,
                    'width_percent': ((bbox[2] - bbox[0]) / page_width) * 100,
                    'height_percent': ((bbox[3] - bbox[1]) / page_height) * 100
                },
                'data': cleaned_data,
                'rows': len(cleaned_data),
                'cols': len(cleaned_data[0]) if cleaned_data and cleaned_data[0] else 0,
                'method': 'pymupdf_faithful',
                'structure': {
                    'column_info': column_info,
                    'header_info': header_info,
                    'has_borders': True,
                    'table_type': self._classify_table_type(cleaned_data)
                }
            }

            return table_info

        except Exception as e:
            logger.error(f"Erreur traitement tableau fidèle: {e}")
            return None

    def _clean_and_structure_table_data(self, raw_data):
        cleaned_data = []
        for row in raw_data:
            cleaned_row = [("" if cell is None or str(cell).lower() == "nan" else str(cell).strip()) for cell in row]
            if any(cell for cell in cleaned_row):
                cleaned_data.append(cleaned_row)
        # égaliser colonnes
        max_cols = max(len(r) for r in cleaned_data) if cleaned_data else 0
        for row in cleaned_data:
            while len(row) < max_cols:
                row.append("")
        return cleaned_data

    def _analyze_table_columns(self, table_data: List[List], bbox, page_width: float) -> List[Dict]:
        """
        Analyse la structure des colonnes du tableau
        """
        column_info = []

        if not table_data or not table_data[0]:
            return column_info

        cols = len(table_data[0])
        table_width = bbox[2] - bbox[0] if bbox else page_width * 0.8
        col_width = table_width / cols

        for col_idx in range(cols):
            # Analyser le contenu de la colonne
            col_contents = []
            for row in table_data:
                if col_idx < len(row) and row[col_idx]:
                    col_contents.append(row[col_idx])

            # Déterminer le type de colonne
            col_type = self._determine_column_type(col_contents)

            # Calculer les statistiques de la colonne
            avg_length = sum(len(content) for content in col_contents) / len(col_contents) if col_contents else 0
            max_length = max(len(content) for content in col_contents) if col_contents else 0

            column_info.append({
                'index': col_idx,
                'type': col_type,
                'width': col_width,
                'width_percent': (col_width / table_width) * 100,
                'avg_content_length': avg_length,
                'max_content_length': max_length,
                'sample_contents': col_contents[:3],  # Premiers contenus pour référence
                'alignment': self._detect_column_alignment(col_contents, col_type)
            })

        return column_info

    def _determine_column_type(self, contents: List[str]) -> str:
        """
        Détermine le type d'une colonne basé sur son contenu
        """
        if not contents:
            return 'empty'

        # Analyser les patterns dans le contenu
        numeric_count = 0
        text_count = 0
        reference_count = 0

        for content in contents:
            content = content.strip()
            if not content:
                continue

            # Vérifier si c'est numérique (avec unités possibles)
            if re.match(r'^\d+\.?\d*\s*(mg|g|ml|%|mm|cm|µg)?$', content, re.IGNORECASE):
                numeric_count += 1
            # Vérifier si c'est une référence (pharmacopée, monographie)
            elif any(term in content.lower() for term in ['pharmacopoeia', 'monograph', 'house', 'european']):
                reference_count += 1
            else:
                text_count += 1

        # Déterminer le type dominant
        total = len(contents)
        if numeric_count / total > 0.7:
            return 'numeric'
        elif reference_count / total > 0.5:
            return 'reference'
        elif any(word in ''.join(contents).lower() for word in ['ingredients', 'substance', 'component']):
            return 'ingredients'
        elif any(word in ''.join(contents).lower() for word in ['role', 'function', 'purpose']):
            return 'role'
        elif any(word in ''.join(contents).lower() for word in ['specification', 'standard', 'ref']):
            return 'specification'
        else:
            return 'text'

    def _detect_column_alignment(self, contents: List[str], col_type: str) -> str:
        """
        Détecte l'alignement approprié pour une colonne
        """
        if col_type == 'numeric':
            return 'right'
        elif col_type == 'reference':
            return 'left'
        elif col_type == 'ingredients':
            return 'left'
        else:
            return 'left'

    def _detect_table_header(self, table_data: List[List]) -> Dict:
        """
        Détecte et analyse l'en-tête du tableau
        """
        header_info = {
            'has_header': False,
            'header_rows': 0,
            'header_content': [],
            'header_style': 'normal'
        }

        if not table_data or len(table_data) < 2:
            return header_info

        # Analyser la première ligne pour déterminer si c'est un header
        first_row = table_data[0]

        # Caractéristiques d'un header
        header_indicators = 0

        # 1. Contenu court et descriptif
        if all(len(cell.strip()) < 50 and cell.strip() for cell in first_row):
            header_indicators += 1

        # 2. Mots-clés typiques d'en-tête
        header_keywords = ['ingredients', 'amount', 'role', 'specification', 'component', 'function', 'quantity']
        if any(any(keyword in cell.lower() for keyword in header_keywords) for cell in first_row):
            header_indicators += 2

        # 3. Différence de style avec les lignes suivantes
        if len(table_data) > 1:
            second_row = table_data[1]
            first_avg_length = sum(len(cell) for cell in first_row) / len(first_row)
            second_avg_length = sum(len(cell) for cell in second_row) / len(second_row)

            if first_avg_length < second_avg_length * 0.7:  # Header généralement plus court
                header_indicators += 1

        # Décision
        if header_indicators >= 2:
            header_info['has_header'] = True
            header_info['header_rows'] = 1
            header_info['header_content'] = first_row
            header_info['header_style'] = 'bold'

        return header_info

    def _classify_table_type(self, table_data: List[List]) -> str:
        """
        Classifie le type de tableau basé sur son contenu
        """
        if not table_data:
            return 'unknown'

        # Analyser le contenu global
        all_content = ' '.join(' '.join(row) for row in table_data).lower()

        # Types de tableaux pharmaceutiques
        if 'ingredients' in all_content and 'amount' in all_content:
            return 'composition'
        elif 'specification' in all_content and ('pharmacopoeia' in all_content or 'monograph' in all_content):
            return 'specifications'
        elif 'test' in all_content or 'method' in all_content:
            return 'analytical'
        elif 'stability' in all_content or 'storage' in all_content:
            return 'stability'
        elif 'dose' in all_content or 'dosage' in all_content:
            return 'dosage'
        else:
            return 'general'

    def _detect_tables_geometric_analysis(self, page, text_dict: Dict, page_num: int,
                                          page_width: float, page_height: float) -> List[Dict]:
        """
        Détection de tableaux par analyse géométrique des positions du texte
        """
        tables = []

        try:
            # Analyser tous les blocs de texte et leurs positions
            text_elements = self._extract_positioned_text_elements(text_dict)

            # Regrouper les éléments en grilles potentielles
            potential_grids = self._identify_text_grids(text_elements)

            # Convertir les grilles en tableaux
            for grid_idx, grid in enumerate(potential_grids):
                table_data = self._convert_grid_to_table(grid)

                if self._validate_table_structure(table_data):
                    # Calculer le bbox du tableau
                    bbox = self._calculate_grid_bbox(grid)

                    table_info = {
                        'type': 'table',
                        'page': page_num,
                        'index': grid_idx,
                        'position': {
                            'x': float(bbox[0]),
                            'y': float(bbox[1]),
                            'width': float(bbox[2] - bbox[0]),
                            'height': float(bbox[3] - bbox[1]),
                            'x_percent': (bbox[0] / page_width) * 100,
                            'y_percent': (bbox[1] / page_height) * 100,
                            'width_percent': ((bbox[2] - bbox[0]) / page_width) * 100,
                            'height_percent': ((bbox[3] - bbox[1]) / page_height) * 100
                        },
                        'data': table_data,
                        'rows': len(table_data),
                        'cols': len(table_data[0]) if table_data and table_data[0] else 0,
                        'method': 'geometric_analysis',
                        'structure': {
                            'detection_confidence': grid.get('confidence', 0.5),
                            'grid_type': grid.get('type', 'regular'),
                            'has_borders': False,
                            'table_type': self._classify_table_type(table_data)
                        }
                    }

                    tables.append(table_info)

        except Exception as e:
            logger.error(f"Erreur analyse géométrique: {e}")

        return tables

    def _extract_positioned_text_elements(self, text_dict: Dict) -> List[Dict]:
        """
        Extrait tous les éléments de texte avec leurs positions précises
        """
        elements = []

        for block in text_dict.get('blocks', []):
            if 'lines' in block:
                for line in block['lines']:
                    for span in line.get('spans', []):
                        text = span.get('text', '').strip()
                        if text:
                            bbox = span.get('bbox', [0, 0, 0, 0])
                            elements.append({
                                'text': text,
                                'x': bbox[0],
                                'y': bbox[1],
                                'width': bbox[2] - bbox[0],
                                'height': bbox[3] - bbox[1],
                                'right': bbox[2],
                                'bottom': bbox[3],
                                'font': span.get('font', ''),
                                'size': span.get('size', 12)
                            })

        return elements

    def _identify_text_grids(self, elements: List[Dict]) -> List[Dict]:
        """
        Identifie les grilles de texte pouvant former des tableaux
        """
        if len(elements) < 4:  # Minimum pour un tableau 2x2
            return []

        # Trier les éléments par position
        elements = sorted(elements, key=lambda x: (x['y'], x['x']))

        grids = []
        tolerance_y = 3.0  # Tolérance pour l'alignement vertical
        tolerance_x = 5.0  # Tolérance pour l'alignement horizontal

        # Grouper par lignes approximatives
        rows = []
        current_row = []
        current_y = None

        for element in elements:
            if current_y is None or abs(element['y'] - current_y) <= tolerance_y:
                current_row.append(element)
                current_y = element['y'] if current_y is None else current_y
            else:
                if len(current_row) >= 2:  # Au moins 2 colonnes
                    rows.append(sorted(current_row, key=lambda x: x['x']))
                current_row = [element]
                current_y = element['y']

        # Ajouter la dernière ligne
        if len(current_row) >= 2:
            rows.append(sorted(current_row, key=lambda x: x['x']))

        # Analyser les lignes pour former des grilles
        if len(rows) >= 2:  # Au moins 2 lignes
            grid = self._analyze_rows_for_grid(rows, tolerance_x)
            if grid:
                grids.append(grid)

        return grids

    def _analyze_rows_for_grid(self, rows: List[List[Dict]], tolerance_x: float) -> Optional[Dict]:
        """
        Analyse un ensemble de lignes pour former une grille cohérente
        """
        if len(rows) < 2:
            return None

        # Analyser la cohérence des colonnes
        column_positions = []

        # Utiliser la première ligne comme référence
        for element in rows[0]:
            column_positions.append(element['x'])

        # Vérifier la cohérence avec les autres lignes
        consistent_rows = 1  # La première ligne est toujours cohérente
        grid_data = [rows[0]]

        for row in rows[1:]:
            row_columns = []
            for col_pos in column_positions:
                # Chercher un élément proche de cette position de colonne
                closest_element = None
                min_distance = float('inf')

                for element in row:
                    distance = abs(element['x'] - col_pos)
                    if distance < min_distance and distance <= tolerance_x:
                        min_distance = distance
                        closest_element = element

                row_columns.append(closest_element)

            # Vérifier si la ligne a suffisamment d'éléments alignés
            aligned_elements = sum(1 for elem in row_columns if elem is not None)
            if aligned_elements >= len(column_positions) * 0.6:  # 60% des colonnes alignées
                consistent_rows += 1
                grid_data.append(row_columns)

        # Valider la grille
        if consistent_rows >= 2 and len(column_positions) >= 2:
            confidence = consistent_rows / len(rows)
            return {
                'rows': grid_data,
                'column_positions': column_positions,
                'confidence': confidence,
                'type': 'regular' if confidence > 0.8 else 'irregular'
            }

        return None

    def _convert_grid_to_table(self, grid: Dict) -> List[List[str]]:
        """
        Convertit une grille d'éléments en données de tableau
        """
        table_data = []

        for row in grid['rows']:
            table_row = []
            for element in row:
                if element:
                    table_row.append(element['text'])
                else:
                    table_row.append('')
            table_data.append(table_row)

        return table_data

    def _validate_table_structure(self, table_data: List[List[str]]) -> bool:
        """
        Valide qu'une structure de données forme un tableau cohérent
        """
        if not table_data or len(table_data) < 2:
            return False

        # Vérifier que les lignes ont une longueur similaire
        row_lengths = [len(row) for row in table_data]
        if len(set(row_lengths)) > 2:  # Trop de variations dans la longueur des lignes
            return False

        # Vérifier qu'il y a suffisamment de contenu
        total_cells = sum(row_lengths)
        filled_cells = sum(1 for row in table_data for cell in row if cell.strip())

        if filled_cells / total_cells < 0.3:  # Moins de 30% de cellules remplies
            return False

        return True

    def _calculate_grid_bbox(self, grid: Dict) -> Tuple[float, float, float, float]:
        """
        Calcule le bbox d'une grille
        """
        min_x = min_y = float('inf')
        max_x = max_y = float('-inf')

        for row in grid['rows']:
            for element in row:
                if element:
                    min_x = min(min_x, element['x'])
                    min_y = min(min_y, element['y'])
                    max_x = max(max_x, element['right'])
                    max_y = max(max_y, element['bottom'])

        return (min_x, min_y, max_x, max_y)

    def _extract_faithful_text_blocks(self, text_dict: Dict, page_num: int, page_width: float,
                                      page_height: float, tables: List[Dict]) -> List[Dict]:
        """
        Extrait les blocs de texte en évitant les zones de tableaux
        """
        text_blocks = []

        # Calculer les zones occupées par les tableaux
        table_zones = []
        for table in tables:
            pos = table['position']
            table_zones.append({
                'x1': pos['x'],
                'y1': pos['y'],
                'x2': pos['x'] + pos['width'],
                'y2': pos['y'] + pos['height']
            })

        try:
            blocks = text_dict.get('blocks', [])

            for block_idx, block in enumerate(blocks):
                if 'lines' in block:
                    bbox = block.get('bbox', [0, 0, 0, 0])

                    # Vérifier si ce bloc chevauche avec un tableau
                    overlaps_table = False
                    for zone in table_zones:
                        if (bbox[0] < zone['x2'] and bbox[2] > zone['x1'] and
                                bbox[1] < zone['y2'] and bbox[3] > zone['y1']):
                            overlaps_table = True
                            break

                    if overlaps_table:
                        continue  # Ignorer les blocs qui chevauchent avec les tableaux

                    # Extraire le texte du bloc
                    block_text = ""
                    for line in block['lines']:
                        spans = line.get('spans', [])
                        for span in spans:
                            text = span.get('text', '')
                            if text.strip():
                                block_text += text

                    if block_text.strip():
                        # Déterminer le type d'élément
                        element_type = self._classify_text_element(block_text)

                        text_block = {
                            'type': 'text',
                            'element_type': element_type,
                            'page': page_num,
                            'index': block_idx,
                            'text': block_text.strip(),
                            'position': {
                                'x': float(bbox[0]),
                                'y': float(bbox[1]),
                                'width': float(bbox[2] - bbox[0]),
                                'height': float(bbox[3] - bbox[1]),
                                'x_percent': (bbox[0] / page_width) * 100,
                                'y_percent': (bbox[1] / page_height) * 100,
                                'width_percent': ((bbox[2] - bbox[0]) / page_width) * 100,
                                'height_percent': ((bbox[3] - bbox[1]) / page_height) * 100
                            }
                        }

                        text_blocks.append(text_block)

        except Exception as e:
            logger.warning(f"Erreur extraction blocs texte: {e}")

        return text_blocks

    def _classify_text_element(self, text: str) -> str:
        """
        Classifie un élément de texte selon son contenu
        """
        text_lower = text.lower().strip()

        # Titre si court, en gras ou grande taille
        if len(text) < 100 and any(keyword in text_lower for keyword in ['description', 'composition', 'container']):
            return 'heading'

    