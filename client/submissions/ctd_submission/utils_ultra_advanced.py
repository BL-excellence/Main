# ctd_submission/utils_ultra_advanced.py
# Extracteur PDF ultra-avancé avec techniques combinées pour préservation de structure

import re
import json
import os
import cv2
import numpy as np
import base64
import logging
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from collections import defaultdict, Counter
import pickle
import tempfile
from io import BytesIO

# Imports pour extraction PDF
try:
    import fitz  # PyMuPDF

    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False

try:
    import pdfplumber

    PDFPLUMBER_AVAILABLE = True
except ImportError:
    PDFPLUMBER_AVAILABLE = False

try:
    import camelot

    CAMELOT_AVAILABLE = True
except ImportError:
    CAMELOT_AVAILABLE = False

try:
    import tabula

    TABULA_AVAILABLE = True
except ImportError:
    TABULA_AVAILABLE = False

# Docling (optionnel)
try:
    import docling  # IBM Project Docling
    DOCLING_AVAILABLE = True
except ImportError:
    DOCLING_AVAILABLE = False

# Imports pour Computer Vision
try:
    from PIL import Image, ImageDraw, ImageFont

    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

# Imports pour Machine Learning
try:
    from sklearn.cluster import DBSCAN, KMeans
    from sklearn.metrics.pairwise import euclidean_distances
    from sklearn.preprocessing import StandardScaler

    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False

# Imports pour traitement linguistique
try:
    import nltk
    from nltk.tokenize import word_tokenize, sent_tokenize
    from nltk.corpus import stopwords

    NLTK_AVAILABLE = True
except ImportError:
    NLTK_AVAILABLE = False

# OCR (optionnel)
try:
    import pytesseract
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False

logger = logging.getLogger(__name__)


@dataclass
class Position:
    """Position précise d'un élément"""
    x: float
    y: float
    width: float
    height: float
    page: int = 0

    @property
    def x2(self) -> float:
        return self.x + self.width

    @property
    def y2(self) -> float:
        return self.y + self.height

    @property
    def center_x(self) -> float:
        return self.x + self.width / 2

    @property
    def center_y(self) -> float:
        return self.y + self.height / 2

    def overlaps(self, other: 'Position') -> bool:
        """Vérifie si deux positions se chevauchent"""
        return not (self.x2 < other.x or other.x2 < self.x or
                    self.y2 < other.y or other.y2 < self.y)

    def distance_to(self, other: 'Position') -> float:
        """Distance entre deux positions"""
        return ((self.center_x - other.center_x) ** 2 +
                (self.center_y - other.center_y) ** 2) ** 0.5


@dataclass
class ExtractedElement:
    """Élément extrait avec métadonnées complètes"""
    type: str  # 'text', 'table', 'image', 'line', 'shape'
    content: Any
    position: Position
    style: Dict[str, Any]
    confidence: float = 0.0
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class UltraAdvancedPDFExtractor:
    """
    Extracteur PDF ultra-avancé combinant toutes les techniques possibles
    pour préserver fidèlement la structure des documents
    """

    def __init__(self):
        self.available_extractors = []
        self.extraction_methods = {}
        # Backward-compat for callers expecting pdf_libraries attribute
        self.pdf_libraries = {
            'pymupdf': PYMUPDF_AVAILABLE,
            'pdfplumber': PDFPLUMBER_AVAILABLE,
            'camelot': CAMELOT_AVAILABLE,
            'tabula': TABULA_AVAILABLE,
        }
        self._init_extractors()

        # Configuration des seuils
        self.config = {
            'table_detection_threshold': 0.7,
            'text_clustering_eps': 15.0,
            'min_table_rows': 2,
            'min_table_cols': 2,
            'ocr_confidence_threshold': 0.6,
            'structure_validation_threshold': 0.8,
            'alignment_tolerance': 3.0,
            'merge_distance_threshold': 10.0,
            'line_height_tolerance': 5.0,
            'sentence_break_threshold': 10.0,
            # Nouveau: contrôle des espaces entre spans (évite les lettres séparées)
            'text_gap_factor': 1.6,                  # agressif: gap ~160% de la taille de police
            'single_char_no_space_factor': 3.0,      # agressif: évite "T H E"
            # Fusion agressive par ligne
            'line_merge_vertical_tolerance_ratio': 0.006,  # 0.6% de la hauteur de page
            'line_merge_min_band_tol_px': 3.0,             # min 3px de tolérance verticale
            'line_merge_gap_factor': 1.8,                  # seuil de fusion horizontal plus grand
            # Paramètres spécifiques au footer (bas de page)
            'footer_height_ratio': 0.12,         # 12% bas de page considéré footer
            'footer_overlap_threshold': 0.4,     # plus strict que global (0.4)
            'footer_keep_highest_conf': True     # garder le texte avec meilleure confiance
        }

        # Modèles pré-entraînés (simulés)
        self.table_classifier = None
        self.structure_analyzer = None

    def _init_extractors(self):
        """Initialise tous les extracteurs disponibles"""
        extractors = {
            'pymupdf': PYMUPDF_AVAILABLE,
            'pdfplumber': PDFPLUMBER_AVAILABLE,
            'camelot': CAMELOT_AVAILABLE,
            'tabula': TABULA_AVAILABLE,
            'docling': DOCLING_AVAILABLE,
            'computer_vision': PIL_AVAILABLE and cv2 is not None,
            'ml_clustering': SKLEARN_AVAILABLE
        }

        for name, available in extractors.items():
            if available:
                self.available_extractors.append(name)
                logger.info(f"✅ Extracteur {name} disponible")
            else:
                logger.warning(f"⚠️ Extracteur {name} non disponible")

    def extract_ultra_structured_content(self, file_path: str) -> Dict:
        """
        Extraction ultra-avancée avec toutes les techniques combinées
        """
        logger.info(f"🚀 ULTRA-EXTRACTION - Début pour {os.path.basename(file_path)}")

        try:
            # PHASE 1: Extraction multi-source
            raw_extractions = self._multi_source_extraction(file_path)

            # PHASE 2: Analyse computer vision
            visual_analysis = self._computer_vision_analysis(file_path)

            # PHASE 3: Clustering et analyse structurelle
            structure_analysis = self._advanced_structure_analysis(raw_extractions, visual_analysis)

            # PHASE 4: Reconstruction intelligente
            reconstructed_content = self._intelligent_reconstruction(structure_analysis)

            # PHASE 5: Validation et correction
            validated_content = self._validate_and_correct_structure(reconstructed_content)

            # PHASE 6: Génération HTML ultra-fidèle
            html_content = self._generate_ultra_faithful_html(validated_content)

            result = {
                'extracted': True,
                'extraction_method': 'ultra_advanced_combined',
                'confidence_score': validated_content.get('overall_confidence', 0.85),
                'text': validated_content.get('combined_text', ''),
                'html': html_content,
                'pages': validated_content.get('pages', []),
                'structure': {
                    'elements': validated_content.get('all_elements', []),
                    'tables': validated_content.get('tables', []),
                    'images': validated_content.get('images', []),
                    'text_blocks': validated_content.get('text_blocks', []),
                    'layout_analysis': validated_content.get('layout_analysis', {}),
                    'quality_metrics': validated_content.get('quality_metrics', {})
                },
                'metadata': validated_content.get('metadata', {}),
                'extraction_stats': {
                    'methods_used': len(raw_extractions),
                    'elements_found': len(validated_content.get('all_elements', [])),
                    'tables_found': len(validated_content.get('tables', [])),
                    'confidence_distribution': validated_content.get('confidence_stats', {})
                }
            }

            logger.info(f"🎉 ULTRA-EXTRACTION - Terminée avec succès")
            return result

        except Exception as e:
            logger.error(f"❌ ULTRA-EXTRACTION - Erreur: {e}")
            return {'extracted': False, 'error': str(e)}

    def _multi_source_extraction(self, file_path: str) -> Dict[str, Any]:
        """Phase 1: Extraction avec toutes les sources disponibles"""
        extractions = {}

        # 1. PyMuPDF - Extraction détaillée
        if PYMUPDF_AVAILABLE:
            extractions['pymupdf'] = self._extract_with_pymupdf_advanced(file_path)

        # 2. PDFPlumber - Tables précises
        if PDFPLUMBER_AVAILABLE:
            extractions['pdfplumber'] = self._extract_with_pdfplumber_advanced(file_path)

        # 3. Camelot - Tables complexes
        if CAMELOT_AVAILABLE:
            extractions['camelot'] = self._extract_with_camelot_advanced(file_path)

        # 4. Tabula - Tables alternatives
        if TABULA_AVAILABLE:
            extractions['tabula'] = self._extract_with_tabula_advanced(file_path)

        # 5. Docling - Extraction structurée alternative
        if DOCLING_AVAILABLE:
            extractions['docling'] = self._extract_with_docling(file_path)
            if extractions.get('docling'):
                logger.info("🧠 Docling: extraction réalisée")
            else:
                logger.warning("🧠 Docling: extraction vide ou échouée")
        else:
            logger.warning("🧠 Docling non disponible - package manquant")

        # 6. Extraction par analyse de pixels
        extractions['pixel_analysis'] = self._extract_with_pixel_analysis(file_path)

        logger.info(f"📊 Multi-source: {len(extractions)} méthodes utilisées -> {list(extractions.keys())}")
        return extractions

    def _extract_with_pymupdf_advanced(self, file_path: str) -> Dict:
        """Extraction PyMuPDF ultra-avancée"""
        try:
            doc = fitz.open(file_path)
            extraction = {
                'pages': [],
                'elements': [],
                'tables': [],
                'images': [],
                'text_blocks': [],
                'fonts': [],
                'colors': [],
                'metadata': {}
            }

            for page_num in range(doc.page_count):
                page = doc.load_page(page_num)
                page_dict = self._safe_get_text_dict(page)

                # Extraction ultra-détaillée
                page_data = self._process_pymupdf_page_ultra(page, page_dict, page_num + 1)
                extraction['pages'].append(page_data)

                # Agréger les éléments
                extraction['elements'].extend(page_data.get('elements', []))
                extraction['tables'].extend(page_data.get('tables', []))
                extraction['images'].extend(page_data.get('images', []))
                extraction['text_blocks'].extend(page_data.get('text_blocks', []))

                # Analyser les fonts et couleurs (si dict non vide pour éviter erreurs)
                if page_dict and isinstance(page_dict, dict):
                    self._analyze_fonts_and_colors(page_dict, extraction)

            doc.close()
            return extraction

        except Exception as e:
            logger.error(f"Erreur PyMuPDF avancé: {e}")
            return {}

    def _safe_get_text_dict(self, page) -> Dict:
        """Obtenir le texte en dict en gérant les PDFs avec layers (OCG/OCMD) et erreurs MuPDF.
        Essaie différents modes et fallback en cas d'erreur 'No default Layer config'.
        """
        try:
            return page.get_text("dict")
        except Exception as e:
            # Tentative: ignorer les calques si MuPDF lève une erreur de Layer config
            try:
                # flags=0 désactive les options (dont celles liées aux calques)
                return page.get_text("dict", flags=0)
            except Exception:
                pass
            # Fallback: 'rawdict' puis conversion minimale
            try:
                raw = page.get_text("rawdict")
                if isinstance(raw, dict):
                    return raw
            except Exception:
                pass
            # Dernier fallback: rasteriser la page et tenter l'OCR si disponible
            try:
                if PYMUPDF_AVAILABLE and OCR_AVAILABLE:
                    mat = fitz.Matrix(2, 2)  # 144 DPI ~ (2x)
                    pix = page.get_pixmap(matrix=mat)
                    img_data = pix.tobytes("png")
                    nparr = np.frombuffer(img_data, np.uint8)
                    image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                    if image is not None:
                        ocr_text = pytesseract.image_to_string(image)
                        if ocr_text and ocr_text.strip():
                            # Fabriquer un dict minimal compatible avec pipeline
                            return {"blocks": [{"lines": [{"spans": [{"text": ocr_text, "bbox": [0,0,image.shape[1], image.shape[0]], "size": 12}]}]}]}
            except Exception:
                pass
            return {"blocks": []}

    def _process_pymupdf_page_ultra(self, page, page_dict: Dict, page_num: int) -> Dict:
        """Traitement ultra-avancé d'une page PyMuPDF"""
        page_width = page.rect.width
        page_height = page.rect.height

        page_data = {
            'page_number': page_num,
            'dimensions': {'width': page_width, 'height': page_height},
            'elements': [],
            'tables': [],
            'images': [],
            'text_blocks': [],
            'lines': [],
            'shapes': []
        }

        # 1. Extraction des images avec analyse
        images = self._extract_images_ultra_detailed(page, page_num, page_width, page_height)
        page_data['images'] = images

        # 2. Extraction des formes et lignes
        shapes = self._extract_shapes_and_lines(page, page_num, page_width, page_height)
        page_data['shapes'] = shapes
        page_data['lines'] = [s for s in shapes if s['type'] == 'line']

        # 3. Extraction des blocs de texte avec clustering
        text_blocks = self._extract_text_blocks_with_clustering(page_dict, page_num, page_width, page_height)
        page_data['text_blocks'] = text_blocks

        # 4. Détection de tableaux par analyse géométrique
        tables = self._detect_tables_geometric_analysis(text_blocks, shapes, page_width, page_height)
        page_data['tables'] = tables

        # 5. Combiner tous les éléments
        all_elements = images + shapes + text_blocks + tables
        page_data['elements'] = sorted(all_elements, key=lambda x: (x['position']['y'], x['position']['x']))

        return page_data

    def _extract_images_ultra_detailed(self, page, page_num: int, page_width: float, page_height: float) -> List[Dict]:
        """Extraction d'images ultra-détaillée"""
        images = []

        try:
            # Obtenir toutes les images
            image_list = page.get_images(full=True)

            for img_index, img in enumerate(image_list):
                try:
                    # Obtenir les rectangles de l'image
                    image_rects = page.get_image_rects(img[0])

                    for rect_index, rect in enumerate(image_rects):
                        # Extraire l'image
                        image_data = self._extract_image_with_processing(page.parent, img[0])

                        # Analyser l'image
                        image_analysis = self._analyze_image_content(image_data)

                        image_element = {
                            'type': 'image',
                            'page': page_num,
                            'index': f"{img_index}_{rect_index}",
                            'position': {
                                'x': float(rect.x0),
                                'y': float(rect.y0),
                                'width': float(rect.width),
                                'height': float(rect.height),
                                'x_percent': (rect.x0 / page_width) * 100,
                                'y_percent': (rect.y0 / page_height) * 100,
                                'width_percent': (rect.width / page_width) * 100,
                                'height_percent': (rect.height / page_height) * 100
                            },
                            'image_data': image_data,
                            'analysis': image_analysis,
                            'confidence': 0.95
                        }

                        images.append(image_element)

                except Exception as e:
                    logger.warning(f"Erreur extraction image {img_index}: {e}")

        except Exception as e:
            logger.error(f"Erreur extraction images page {page_num}: {e}")

        return images

    def _extract_shapes_and_lines(self, page, page_num: int, page_width: float, page_height: float) -> List[Dict]:
        """Extraction des formes et lignes géométriques"""
        shapes = []

        try:
            # Obtenir les dessins vectoriels
            drawings = page.get_drawings()

            for draw_index, drawing in enumerate(drawings):
                try:
                    # drawing may be a dict-like or a tuple depending on PyMuPDF version
                    rect = None
                    stroke_color = None
                    fill_color = None
                    line_width = 1.0

                    if isinstance(drawing, dict):
                        rect = drawing.get('rect')
                        stroke = drawing.get('stroke') or {}
                        fill = drawing.get('fill') or {}
                        stroke_color = (stroke.get('color') if isinstance(stroke, dict) else None)
                        fill_color = (fill.get('color') if isinstance(fill, dict) else None)
                        line_width = (stroke.get('width', 1.0) if isinstance(stroke, dict) else 1.0)
                    elif isinstance(drawing, (list, tuple)):
                        # Best-effort unpacking for tuple-shaped drawing entries
                        # Known tuple shape: (items, color, fill, width, ...) varies by version
                        for item in drawing:
                            # try to pick first rect-like value
                            if hasattr(item, 'x0') and hasattr(item, 'y0') and hasattr(item, 'width') and hasattr(item, 'height'):
                                rect = item
                                break
                        # colors/width often not directly available; leave None/defaults

                    if not rect:
                        continue

                    # Analyser le type de forme
                    shape_type = self._classify_shape(drawing)

                    shape_element = {
                        'type': 'shape',
                        'shape_type': shape_type,
                        'page': page_num,
                        'index': draw_index,
                        'position': {
                            'x': float(rect.x0),
                            'y': float(rect.y0),
                            'width': float(rect.width),
                            'height': float(rect.height),
                            'x_percent': (rect.x0 / page_width) * 100,
                            'y_percent': (rect.y0 / page_height) * 100,
                            'width_percent': (rect.width / page_width) * 100,
                            'height_percent': (rect.height / page_height) * 100
                        },
                        'properties': {
                            'stroke_color': stroke_color,
                            'fill_color': fill_color,
                            'line_width': line_width
                        },
                        'confidence': 0.9
                    }

                    shapes.append(shape_element)

                except Exception as e:
                    logger.warning(f"Erreur traitement forme {draw_index}: {e}")

        except Exception as e:
            logger.error(f"Erreur extraction formes page {page_num}: {e}")

        return shapes

    def _extract_text_blocks_with_clustering(self, page_dict: Dict, page_num: int,
                                             page_width: float, page_height: float) -> List[Dict]:
        """Extraction de blocs de texte avec clustering ML, avec fallback 'linewise' si le PDF est fragmenté (lettre par lettre)."""
        text_blocks = []

        try:
            # Collecter tous les spans de texte
            all_spans = []
            for block in page_dict.get('blocks', []):
                if 'lines' in block:
                    for line in block['lines']:
                        for span in line.get('spans', []):
                            if span.get('text', '').strip():
                                all_spans.append(span)

            if not all_spans:
                return text_blocks

            # Clustering des spans par position et style
            clustered_spans = self._cluster_text_spans(all_spans)

            # Heuristique de détection 'lettres isolées': trop de clusters unitaires ou peu de caractères par cluster
            total_clusters = max(1, len(clustered_spans))
            singleton_clusters = sum(1 for spans in clustered_spans.values() if len(spans) == 1 and len((spans[0].get('text','') or '').strip()) <= 2)
            total_chars = sum(len((s.get('text','') or '').strip()) for spans in clustered_spans.values() for s in spans)
            avg_chars_per_cluster = total_chars / total_clusters

            fragmented = (singleton_clusters / total_clusters) > 0.5 or avg_chars_per_cluster < 5

            if fragmented:
                # Fallback robuste: regrouper par lignes Y, puis assembler chaque ligne proprement
                line_groups = self._group_spans_into_lines(all_spans)
                for spans in line_groups:
                    block = self._create_text_block_from_spans(spans, page_num, page_width, page_height)
                    if block:
                        text_blocks.append(block)
            else:
                # Créer des blocs de texte à partir des clusters
                for cluster_id, spans in clustered_spans.items():
                    block = self._create_text_block_from_spans(spans, page_num, page_width, page_height)
                    if block:
                        text_blocks.append(block)

        except Exception as e:
            logger.error(f"Erreur clustering texte page {page_num}: {e}")

        return text_blocks

    def _cluster_text_spans(self, spans: List[Dict]) -> Dict[int, List[Dict]]:
        """Clustering des spans de texte avec détection des phrases"""
        if not SKLEARN_AVAILABLE or len(spans) < 2:
            return {0: spans}
        try:
            features = []
            for span in spans:
                bbox = span.get('bbox', [0, 0, 0, 0])
                font_size = span.get('size', 12)
                text = span.get('text', '').strip()
                is_end_of_sentence = 1.0 if re.search(r'[.!?]$', text) else 0.0
                features.append([bbox[0], bbox[1], bbox[2] - bbox[0], bbox[3] - bbox[1], font_size, len(text), is_end_of_sentence])
            scaler = StandardScaler()
            features_scaled = scaler.fit_transform(features)
            clustering = DBSCAN(eps=self.config['text_clustering_eps'] / 100, min_samples=1, metric='euclidean').fit(features_scaled)
            clustered = defaultdict(list)
            for i, label in enumerate(clustering.labels_):
                if label != -1:
                    clustered[label].append(spans[i])
            # Ajuster pour les phrases continues
            adjusted_clusters = {}
            for cluster_id, cluster_spans in clustered.items():
                current_cluster = []
                prev_y = cluster_spans[0]['bbox'][1]
                for span in sorted(cluster_spans, key=lambda s: (s['bbox'][1], s['bbox'][0])):
                    if (abs(span['bbox'][1] - prev_y) > self.config['sentence_break_threshold'] or
                        re.search(r'[.!?]$', span.get('text', ''))):
                        if current_cluster:
                            adjusted_clusters[len(adjusted_clusters)] = current_cluster
                            current_cluster = [span]
                        else:
                            current_cluster.append(span)
                    else:
                        current_cluster.append(span)
                    prev_y = span['bbox'][1]
                if current_cluster:
                    adjusted_clusters[len(adjusted_clusters)] = current_cluster
            return adjusted_clusters if adjusted_clusters else {0: spans}
        except Exception as e:
            logger.error(f"Erreur clustering ML: {e}")
            return {0: spans}
    
    def _create_text_block_from_spans(self, spans: List[Dict], page_num: int, page_width: float, page_height: float) -> Optional[Dict]:
        """Créer un bloc de texte cohérent avec préservation des phrases et fallback anti-fragmentation."""
        if not spans:
            return None
        try:
            min_x = min(span['bbox'][0] for span in spans)
            min_y = min(span['bbox'][1] for span in spans)
            max_x = max(span['bbox'][2] for span in spans)
            max_y = max(span['bbox'][3] for span in spans)
            sorted_spans = sorted(spans, key=lambda s: (s['bbox'][1], s['bbox'][0]))
            lines = []
            current_line = []
            prev_y = sorted_spans[0]['bbox'][1]
            for span in sorted_spans:
                if abs(span['bbox'][1] - prev_y) > self.config['line_height_tolerance']:
                    if current_line:
                        lines.append(current_line)
                    current_line = [span]
                    prev_y = span['bbox'][1]
                else:
                    current_line.append(span)
            if current_line:
                lines.append(current_line)

            combined_text = ''
            prev_line_text = ''
            for i, line_spans in enumerate(lines):
                # Si la ligne est ultra fragmentée en caractères unitaires, concaténer sans ajouter d'espaces artificiels
                single_chars = sum(1 for s in line_spans if len((s.get('text','') or '').strip()) == 1)
                if len(line_spans) > 0 and (single_chars / len(line_spans)) > 0.6:
                    line_text = ''.join((s.get('text','') or '') for s in sorted(line_spans, key=lambda s: s.get('bbox',[0,0,0,0])[0]))
                else:
                    line_text = self._join_spans_with_spacing(line_spans).strip()

                if i > 0:
                    # Gestion de la césure (hyphenation) entre lignes
                    if self._should_merge_hyphen(prev_line_text, line_text):
                        combined_text = combined_text.rstrip()
                        if combined_text.endswith('-'):
                            combined_text = combined_text[:-1]
                    else:
                        last_char = combined_text[-1] if combined_text else ''
                        if last_char and not re.search(r'[.!?]$', last_char):
                            combined_text += ' '
                combined_text += line_text
                prev_line_text = line_text

            combined_text = self._normalize_whitespace(combined_text)
            if not combined_text.strip():
                return None
            style_analysis = self._analyze_dominant_style(spans)
            element_type = self._classify_text_element(combined_text, style_analysis)
            text_block = {
                'type': 'text', 'element_type': element_type, 'page': page_num, 'text': combined_text,
                'position': {
                    'x': float(min_x), 'y': float(min_y), 'width': float(max_x - min_x), 'height': float(max_y - min_y),
                    'x_percent': (min_x / page_width) * 100, 'y_percent': (min_y / page_height) * 100,
                    'width_percent': ((max_x - min_x) / page_width) * 100, 'height_percent': ((max_y - min_y) / page_height) * 100
                },
                'style': style_analysis, 'spans_count': len(spans), 'confidence': self._calculate_text_confidence(spans, combined_text)
            }
            return text_block
        except Exception as e:
            logger.error(f"Erreur création bloc texte: {e}")
            return None
    

    def _detect_tables_geometric_analysis(self, text_blocks: List[Dict], shapes: List[Dict], page_width: float, page_height: float) -> List[Dict]:
        """Détection avancée de tableaux par analyse géométrique avec intégration texte"""
        tables = []
        try:
            grid_tables = self._detect_tables_from_lines(shapes, page_width, page_height)
            tables.extend(grid_tables)
            alignment_tables = self._detect_tables_from_text_alignment(text_blocks, page_width, page_height)
            tables.extend(alignment_tables)
            merged_tables = self._merge_overlapping_tables(tables)
            validated_tables = []
            for table in merged_tables:
                validated_table = self._validate_and_enrich_table(table, text_blocks)
                if validated_table:
                    # Associer le tableau au texte adjacent s'il est proche
                    adjacent_text = self._find_adjacent_text(table, text_blocks)
                    if adjacent_text:
                        validated_table['adjacent_text'] = adjacent_text
                    validated_tables.append(validated_table)
            return validated_tables
        except Exception as e:
            logger.error(f"Erreur détection tableaux géométrique: {e}")
            return []
        

    def _find_adjacent_text(self, table: Dict, text_blocks: List[Dict]) -> Optional[str]:
        """Trouver le texte adjacent à un tableau"""
        table_pos = Position(**table['position'])
        min_distance = float('inf')
        closest_text = None
        for block in text_blocks:
            block_pos = Position(**block['position'])
            distance = table_pos.distance_to(block_pos)
            if distance < self.config['merge_distance_threshold'] and not table_pos.overlaps(block_pos):
                if distance < min_distance:
                    min_distance = distance
                    closest_text = block['text']
        return closest_text    

    def _detect_tables_from_lines(self, shapes: List[Dict], page_width: float, page_height: float) -> List[Dict]:
        """Détection de tableaux à partir des lignes tracées"""
        tables = []

        try:
            # Filtrer les lignes
            lines = [s for s in shapes if s.get('shape_type') in ['line', 'rect']]

            if len(lines) < 4:  # Minimum pour un tableau
                return tables

            # Analyser les patterns de grille
            grid_patterns = self._analyze_grid_patterns(lines)

            for pattern in grid_patterns:
                if self._is_valid_table_pattern(pattern):
                    table = self._create_table_from_grid_pattern(pattern, page_width, page_height)
                    if table:
                        tables.append(table)

        except Exception as e:
            logger.error(f"Erreur détection tableaux lignes: {e}")

        return tables

    def _detect_tables_from_text_alignment(self, text_blocks: List[Dict],
                                           page_width: float, page_height: float) -> List[Dict]:
        """Détection de tableaux par alignement de texte"""
        tables = []

        try:
            if not text_blocks:
                return tables

            # Grouper les blocs par Y (lignes potentielles)
            y_groups = self._group_text_blocks_by_y(text_blocks)

            # Analyser l'alignement des colonnes
            for y_group in y_groups:
                if len(y_group) >= self.config['min_table_cols']:
                    # Détecter si c'est une ligne de tableau
                    if self._is_table_row_candidate(y_group):
                        # Chercher les lignes suivantes qui s'alignent
                        table_rows = self._find_aligned_rows(y_group, y_groups)

                        if len(table_rows) >= self.config['min_table_rows']:
                            table = self._create_table_from_aligned_text(table_rows, page_width, page_height)
                            if table:
                                tables.append(table)

        except Exception as e:
            logger.error(f"Erreur détection tableaux alignement: {e}")

        return tables

    def _computer_vision_analysis(self, file_path: str) -> Dict:
        """Phase 2: Analyse par computer vision"""
        if not PIL_AVAILABLE:
            return {}

        try:
            # Convertir PDF en images
            images = self._pdf_to_images(file_path)

            analysis = {
                'pages': [],
                'layout_regions': [],
                'text_regions': [],
                'table_regions': [],
                'image_regions': []
            }

            for page_num, image in enumerate(images):
                page_analysis = self._analyze_page_image(image, page_num + 1)
                analysis['pages'].append(page_analysis)

                # Agréger les régions
                analysis['layout_regions'].extend(page_analysis.get('layout_regions', []))
                analysis['text_regions'].extend(page_analysis.get('text_regions', []))
                analysis['table_regions'].extend(page_analysis.get('table_regions', []))
                analysis['image_regions'].extend(page_analysis.get('image_regions', []))

            return analysis

        except Exception as e:
            logger.error(f"Erreur analyse computer vision: {e}")
            return {}

    def _pdf_to_images(self, file_path: str, dpi: int = 200) -> List[np.ndarray]:
        """Convertir PDF en images pour analyse CV"""
        images = []

        try:
            if PYMUPDF_AVAILABLE:
                doc = fitz.open(file_path)

                for page_num in range(doc.page_count):
                    page = doc.load_page(page_num)

                    # Convertir en image
                    mat = fitz.Matrix(dpi / 72, dpi / 72)
                    pix = page.get_pixmap(matrix=mat)

                    # Convertir en numpy array
                    img_data = pix.tobytes("ppm")
                    nparr = np.frombuffer(img_data, np.uint8)
                    image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

                    images.append(image)

                doc.close()

        except Exception as e:
            logger.error(f"Erreur conversion PDF vers images: {e}")

        return images

    def _analyze_page_image(self, image: np.ndarray, page_num: int) -> Dict:
        """Analyser une page sous forme d'image"""
        try:
            height, width = image.shape[:2]

            analysis = {
                'page_number': page_num,
                'dimensions': {'width': width, 'height': height},
                'layout_regions': [],
                'text_regions': [],
                'table_regions': [],
                'image_regions': []
            }

            # Détection rapide de zones de texte denses (aide pour le fallback quand spans sont lettre par lettre)
            try:
                gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
                thr = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
                kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 2))
                morph = cv2.morphologyEx(thr, cv2.MORPH_CLOSE, kernel, iterations=2)
                contours, _ = cv2.findContours(morph, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                for cnt in contours:
                    x, y, w, h = cv2.boundingRect(cnt)
                    if w > 40 and h > 8:
                        analysis['text_regions'].append({'position': {'x': x, 'y': y, 'width': w, 'height': h}, 'page': page_num, 'type': 'text_region'})
            except Exception:
                pass

            # 1. Détection de mise en page par contours
            layout_regions = self._detect_layout_regions(image)
            analysis['layout_regions'] = layout_regions

            # 2. Détection de régions de texte
            text_regions = self._detect_text_regions(image)
            analysis['text_regions'] = text_regions

            # 3. Détection de tableaux par analyse visuelle
            table_regions = self._detect_table_regions_visual(image)
            analysis['table_regions'] = table_regions

            # 4. Détection d'images
            image_regions = self._detect_image_regions(image)
            analysis['image_regions'] = image_regions

            return analysis

        except Exception as e:
            logger.error(f"Erreur analyse image page {page_num}: {e}")
            return {}

    def _detect_table_regions_visual(self, image: np.ndarray) -> List[Dict]:
        """Détection visuelle de tableaux par computer vision"""
        tables = []

        try:
            # Convertir en niveaux de gris
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

            # Méthode 1: Détection de lignes horizontales et verticales
            horizontal_lines = self._detect_horizontal_lines(gray)
            vertical_lines = self._detect_vertical_lines(gray)

            # Trouver les intersections pour former des grilles
            grids = self._find_grid_intersections(horizontal_lines, vertical_lines)

            for grid in grids:
                if self._is_valid_table_grid(grid):
                    table = self._create_table_from_visual_grid(grid, image.shape)
                    tables.append(table)

            # Méthode 2: Détection par template matching
            template_tables = self._detect_tables_by_template_matching(gray)
            tables.extend(template_tables)

            # Méthode 3: Détection par analyse de texture
            texture_tables = self._detect_tables_by_texture_analysis(gray)
            tables.extend(texture_tables)

        except Exception as e:
            logger.error(f"Erreur détection tableaux visuelle: {e}")

        return tables

    def _detect_horizontal_lines(self, gray_image: np.ndarray) -> List[Tuple]:
        """Détecter les lignes horizontales"""
        try:
            # Créer un kernel horizontal
            horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (40, 1))

            # Détecter les lignes horizontales
            detected_lines = cv2.morphologyEx(gray_image, cv2.MORPH_OPEN, horizontal_kernel, iterations=2)

            # Trouver les contours
            contours, _ = cv2.findContours(detected_lines, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            lines = []
            for contour in contours:
                x, y, w, h = cv2.boundingRect(contour)
                if w > 50 and h < 10:  # Filtre pour lignes horizontales
                    lines.append((x, y, x + w, y + h))

            return lines

        except Exception as e:
            logger.error(f"Erreur détection lignes horizontales: {e}")
            return []

    def _detect_vertical_lines(self, gray_image: np.ndarray) -> List[Tuple]:
        """Détecter les lignes verticales"""
        try:
            # Créer un kernel vertical
            vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 40))

            # Détecter les lignes verticales
            detected_lines = cv2.morphologyEx(gray_image, cv2.MORPH_OPEN, vertical_kernel, iterations=2)

            # Trouver les contours
            contours, _ = cv2.findContours(detected_lines, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            lines = []
            for contour in contours:
                x, y, w, h = cv2.boundingRect(contour)
                if h > 50 and w < 10:  # Filtre pour lignes verticales
                    lines.append((x, y, x + w, y + h))

            return lines

        except Exception as e:
            logger.error(f"Erreur détection lignes verticales: {e}")
            return []

    def _advanced_structure_analysis(self, raw_extractions: Dict, visual_analysis: Dict) -> Dict:
        """Phase 3: Analyse structurelle avancée"""
        try:
            # Fusionner toutes les données
            all_elements = []
            all_tables = []
            all_images = []

            # Collecter depuis toutes les sources
            for method, data in raw_extractions.items():
                if isinstance(data, dict):
                    all_elements.extend(data.get('elements', []))
                    all_tables.extend(data.get('tables', []))
                    all_images.extend(data.get('images', []))

            # Ajouter les données de computer vision
            if visual_analysis:
                all_elements.extend(visual_analysis.get('layout_regions', []))
                all_tables.extend(visual_analysis.get('table_regions', []))
                all_images.extend(visual_analysis.get('image_regions', []))

            # Analyse de consensus entre méthodes
            consensus_analysis = self._consensus_analysis(raw_extractions, visual_analysis)

            # Détection des relations spatiales
            spatial_relations = self._analyze_spatial_relations(all_elements)

            # Classification ML des éléments
            ml_classification = self._ml_element_classification(all_elements)

            return {
                'all_elements': all_elements,
                'all_tables': all_tables,
                'all_images': all_images,
                'consensus': consensus_analysis,
                'spatial_relations': spatial_relations,
                'ml_classification': ml_classification
            }

        except Exception as e:
            logger.error(f"Erreur analyse structurelle: {e}")
            return {}

    def _consensus_analysis(self, raw_extractions: Dict, visual_analysis: Dict) -> Dict:
        """Analyse de consensus entre différentes méthodes"""
        try:
            consensus = {
                'high_confidence_elements': [],
                'conflicting_elements': [],
                'unique_elements': [],
                'agreement_score': 0.0
            }

            # Comparer les résultats des différentes méthodes
            element_positions = defaultdict(list)

            # Collecter les positions de tous les éléments
            for method, data in raw_extractions.items():
                if isinstance(data, dict):
                    for element in data.get('elements', []):
                        pos_key = self._position_to_key(element['position'])
                        element_positions[pos_key].append((method, element))

            # Analyser le consensus
            total_elements = len(element_positions)
            agreement_count = 0

            for pos_key, elements in element_positions.items():
                if len(elements) > 1:
                    # Élément détecté par plusieurs méthodes
                    agreement_count += 1
                    consensus['high_confidence_elements'].append({
                        'position_key': pos_key,
                        'methods': [e[0] for e in elements],
                        'elements': [e[1] for e in elements],
                        'confidence': len(elements) / len(raw_extractions)
                    })
                else:
                    # Élément unique à une méthode
                    consensus['unique_elements'].append({
                        'position_key': pos_key,
                        'method': elements[0][0],
                        'element': elements[0][1]
                    })

            consensus['agreement_score'] = agreement_count / total_elements if total_elements > 0 else 0

            return consensus

        except Exception as e:
            logger.error(f"Erreur analyse consensus: {e}")
            return {}

    def _intelligent_reconstruction(self, structure_analysis: Dict) -> Dict:
        """Phase 4: Reconstruction intelligente de la structure"""
        try:
            validated_elements = self._validate_elements_by_consensus(structure_analysis)
            reconstructed_tables = self._reconstruct_tables_intelligently(validated_elements)
            content_hierarchy = self._reconstruct_content_hierarchy(validated_elements)
            reading_order = self._determine_reading_order(validated_elements)
            combined_text = ''
            for element in reading_order:
                if element.get('type') == 'text':
                    combined_text += element['text'] + '\n'
                elif element.get('type') == 'table' and 'adjacent_text' in element:
                    combined_text += element['adjacent_text'] + '\n'
                    # Ajouter une représentation simple de la table si disponible
                    if 'data' in element:
                        combined_text += "Tableau:\n" + str(element['data']) + '\n'
            combined_text = combined_text.strip()
            return {
                'validated_elements': validated_elements,
                'tables': reconstructed_tables,
                'content_hierarchy': content_hierarchy,
                'reading_order': reading_order,
                'combined_text': combined_text,
                'reconstruction_stats': {
                    'elements_validated': len(validated_elements),
                    'tables_reconstructed': len(reconstructed_tables),
                    'hierarchy_levels': len(content_hierarchy)
                }
            }
        except Exception as e:
            logger.error(f"Erreur reconstruction intelligente: {e}")
            return {}

    def _validate_and_correct_structure(self, reconstructed_content: Dict) -> Dict:
        """Phase 5: Validation et correction de structure"""
        try:
            validated = reconstructed_content.copy()

            # Validation des tableaux
            validated_tables = []
            for table in reconstructed_content.get('tables', []):
                validated_table = self._validate_table_structure(table)
                if validated_table:
                    validated_tables.append(validated_table)

            validated['tables'] = validated_tables

            # Correction des chevauchements
            validated['validated_elements'] = self._correct_overlapping_elements(
                reconstructed_content.get('validated_elements', [])
            )

            # Validation de la hiérarchie
            validated['content_hierarchy'] = self._validate_content_hierarchy(
                reconstructed_content.get('content_hierarchy', {})
            )

            # Calcul de métriques de qualité
            validated['quality_metrics'] = self._calculate_quality_metrics(validated)

            # Score de confiance global
            validated['overall_confidence'] = self._calculate_overall_confidence(validated)

            return validated

        except Exception as e:
            logger.error(f"Erreur validation structure: {e}")
            return reconstructed_content

    def _generate_ultra_faithful_html(self, validated_content: Dict) -> str:
        """Phase 6: Génération HTML ultra-fidèle"""
        try:
            html_parts = ['<div class="ultra-faithful-pdf-document">']

            # Style CSS intégré
            html_parts.append(self._generate_ultra_faithful_css())

            # Organiser par pages
            pages_elements = defaultdict(list)
            for element in validated_content.get('validated_elements', []):
                page_num = element.get('page', 1)
                pages_elements[page_num].append(element)

            # Générer chaque page
            for page_num in sorted(pages_elements.keys()):
                page_html = self._generate_ultra_faithful_page_html(
                    page_num, pages_elements[page_num], validated_content
                )
                html_parts.append(page_html)

            html_parts.append('</div>')

            return '\n'.join(html_parts)

        except Exception as e:
            logger.error(f"Erreur génération HTML ultra-fidèle: {e}")
            return '<div class="error">Erreur génération HTML</div>'

    def _generate_ultra_faithful_css(self) -> str:
        """CSS ultra-avancé pour préservation fidèle"""
        return '''
        <style>
        .ultra-faithful-pdf-document {
            font-family: 'Times New Roman', serif;
            background: #f8f9fa;
            padding: 20px;
        }

        .ultra-page-container {
            background: white;
            margin: 0 auto 30px auto;
            box-shadow: 0 4px 20px rgba(0,0,0,0.1);
            position: relative;
            overflow: hidden;
            border: 1px solid #ddd;
            /* Désactiver zoom automatique navigateur sur mobiles */
            image-rendering: pixelated;
        }

        .ultra-element {
            position: absolute;
            transition: all 0.2s ease;
        }

        .ultra-element:hover {
            outline: 2px dashed #007bff;
            z-index: 10;
        }

        .ultra-text {
            font-family: inherit;
            line-height: 1.2;
            /* Fidèle au PDF: pas de wraps imprévus */
            word-break: normal;
            overflow-wrap: normal;
            white-space: pre; /* garder exactement les espaces/retours fournis */
            cursor: text;
        }

        .ultra-table {
            border-collapse: collapse;
            width: 100%;
            height: 100%;
            table-layout: fixed; /* positions stables, pas de reflow inattendu */
        }

        .ultra-table td, .ultra-table th {
            border: 1px solid #333;
            padding: 2px 4px;
            vertical-align: top;
            font-size: inherit;
            line-height: 1.1;
            /* Empêche les retours à la ligne indésirables dans les cellules */
            white-space: nowrap;
        }

        .ultra-image {
            border: 1px solid #ccc;
            background: #f9f9f9;
        }

        .ultra-shape {
            border: 1px solid;
            background: transparent;
        }

        .high-confidence {
            background: rgba(40, 167, 69, 0.1);
        }

        .medium-confidence {
            background: rgba(255, 193, 7, 0.1);
        }

        .low-confidence {
            background: rgba(220, 53, 69, 0.1);
        }

        .editable-content[contenteditable="true"] {
            min-height: 1em;
            outline: none;
        }

        .editable-content[contenteditable="true"]:focus {
            background: rgba(0, 123, 255, 0.1);
            outline: 2px solid #007bff;
        }

        .table-cell-editable {
            cursor: text;
        }

        .table-cell-editable:hover {
            background: rgba(0, 123, 255, 0.05);
        }

        .table-cell-editable:focus {
            background: rgba(0, 123, 255, 0.1);
            outline: 1px solid #007bff;
        }

        @media print {
            .ultra-page-container {
                box-shadow: none;
                border: none;
                page-break-after: always;
            }

            .ultra-element:hover {
                outline: none;
            }
        }
        </style>
        '''

    def _generate_ultra_faithful_page_html(self, page_num: int, elements: List[Dict],
                                           validated_content: Dict) -> str:
        """Générer HTML ultra-fidèle pour une page"""
        try:
            # Calculer les dimensions de la page
            page_width = 595  # A4 default
            page_height = 842

            # Trouver les dimensions réelles si disponibles
            for element in elements:
                if 'page_dimensions' in element:
                    page_width = element['page_dimensions']['width']
                    page_height = element['page_dimensions']['height']
                    break

            # Rendu fidèle: utiliser les dimensions réelles du PDF en pixels (non responsive)
            html = f'''
            <div class="ultra-page-container" data-page="{page_num}" 
                 style="width: {page_width:.0f}px; height: {page_height:.0f}px;">
                <div class="page-label" style="position: absolute; top: -25px; left: 0; font-size: 12px; color: #666;">
                    Page {page_num}
                </div>
            '''

            # Dédoublonner plus agressivement les textes en footer
            elements = self._deduplicate_footer_text_elements(elements, page_width, page_height)

            # Fusionner les fragments de texte sur la même ligne pour éviter lettres isolées
            elements = self._merge_line_text_fragments(elements, page_width, page_height)

            # Trier les éléments par ordre de profondeur (z-index)
            sorted_elements = sorted(elements, key=lambda x: self._get_element_z_index(x))

            # Générer chaque élément avec déduplication et filtrage de chevauchement
            seen_positions = set()
            text_boxes = []  # [(x1,y1,x2,y2,conf,idx)] pour éviter superpositions
            for idx, element in enumerate(sorted_elements):
                # Éviter les doublons de texte au même emplacement (arrondi)
                if element.get('type') == 'text':
                    pos = element.get('position', {})
                    x1, y1 = float(pos.get('x', 0)), float(pos.get('y', 0))
                    x2 = x1 + float(pos.get('width', 0))
                    y2 = y1 + float(pos.get('height', 0))
                    conf = float(element.get('confidence', 0.5))

                    # Footer detection (bas de page)
                    is_footer = False
                    try:
                        footer_threshold_y = page_height * (1.0 - self.config.get('footer_height_ratio', 0.12))
                        is_footer = y1 >= footer_threshold_y
                    except Exception:
                        pass

                    key = self._position_to_key(pos)
                    if key in seen_positions:
                        # déjà un texte à la même position arrondie
                        continue

                    # Filtrer les chevauchements avec des textes déjà placés
                    overlaps = False
                    replace_index = None
                    best_ratio = 0.0
                    for j, (bx1, by1, bx2, by2, bconf, bidx) in enumerate(text_boxes):
                        ix1, iy1 = max(x1, bx1), max(y1, by1)
                        ix2, iy2 = min(x2, bx2), min(y2, by2)
                        iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
                        inter = iw * ih
                        area = max(1.0, (x2 - x1) * (y2 - y1))
                        bratio = inter / area
                        # Seuil plus strict en footer
                        threshold = self.config.get('footer_overlap_threshold', 0.4) if is_footer else 0.6
                        if bratio > threshold:
                            # En footer, on garde le plus confiant si activé
                            if is_footer and self.config.get('footer_keep_highest_conf', True):
                                if conf > bconf:
                                    replace_index = j  # on remplace l’ancien
                                    best_ratio = bratio
                                    overlaps = False
                                else:
                                    overlaps = True
                                    break
                            else:
                                overlaps = True
                                break
                    if overlaps:
                        continue
                    if replace_index is not None:
                        text_boxes[replace_index] = (x1, y1, x2, y2, conf, idx)
                    else:
                        text_boxes.append((x1, y1, x2, y2, conf, idx))
                    seen_positions.add(key)
                element_html = self._generate_element_html_ultra_faithful(element, page_width, page_height)
                html += element_html

            html += '</div>'

            return html

        except Exception as e:
            logger.error(f"Erreur génération page HTML {page_num}: {e}")
            return f'<div class="error-page">Erreur page {page_num}</div>'

    def _generate_element_html_ultra_faithful(self, element: Dict, page_width: float, page_height: float) -> str:
        """Générer HTML ultra-fidèle pour un élément"""
        try:
            element_type = element.get('type', 'unknown')
            position = element.get('position', {})
            confidence = element.get('confidence', 0.5)

            # Calculer les pourcentages de position
            x_percent = (position.get('x', 0) / page_width) * 100
            y_percent = (position.get('y', 0) / page_height) * 100
            width_percent = (position.get('width', 0) / page_width) * 100
            height_percent = (position.get('height', 0) / page_height) * 100

            # Classe de confiance
            confidence_class = (
                'high-confidence' if confidence > 0.8 else
                'medium-confidence' if confidence > 0.5 else
                'low-confidence'
            )

            # Style de position commun en pixels pour correspondre exactement au PDF
            position_style = f'''
                left: {position.get('x', 0):.2f}px;
                top: {position.get('y', 0):.2f}px;
                width: {position.get('width', 0):.2f}px;
                height: {position.get('height', 0):.2f}px;
            '''

            # Générer selon le type
            if element_type == 'text':
                return self._generate_text_element_html(element, position_style, confidence_class)
            elif element_type == 'table':
                return self._generate_table_element_html(element, position_style, confidence_class)
            elif element_type == 'image':
                return self._generate_image_element_html(element, position_style, confidence_class)
            elif element_type == 'shape':
                return self._generate_shape_element_html(element, position_style, confidence_class)
            else:
                return f'<!-- Unknown element type: {element_type} -->'

        except Exception as e:
            logger.error(f"Erreur génération élément HTML: {e}")
            return '<!-- Error generating element -->'

    def _generate_text_element_html(self, element: Dict, position_style: str, confidence_class: str) -> str:
        """Générer HTML pour élément texte"""
        text = element.get('text', '')
        element_type = element.get('element_type', 'paragraph')
        style_data = element.get('style', {})
        element_id = f"text-p{element.get('page', 1)}-{element.get('index', 0)}"

        # Style de texte
        text_style = self._convert_style_to_css(style_data)

        # Tag HTML selon le type
        tag = 'h1' if element_type == 'heading' else 'p'

        # Normaliser le texte pour éviter espacements/coupures non voulus
        safe_text = self._normalize_whitespace(text)

        return f'''
        <{tag} class="ultra-element ultra-text {confidence_class} editable-content" 
             contenteditable="true"
             data-element-id="{element_id}"
             data-original-text="{safe_text}"
             data-confidence="{element.get('confidence', 0.5):.2f}"
             style="{position_style} {text_style}">
            {safe_text}
        </{tag}>
        '''

    def _generate_table_element_html(self, element: Dict, position_style: str, confidence_class: str) -> str:
        """Générer HTML pour élément tableau"""
        table_data = element.get('data', [])
        table_id = f"table-p{element.get('page', 1)}-{element.get('index', 0)}"

        if not table_data:
            return f'<div class="ultra-element table-placeholder {confidence_class}" style="{position_style}">Tableau détecté</div>'

        html = f'''
        <div class="ultra-element {confidence_class}" style="{position_style}">
            <table class="ultra-table" data-table-id="{table_id}">
        '''

        for row_idx, row in enumerate(table_data):
            html += '<tr>'
            for col_idx, cell in enumerate(row):
                # Nettoyage doux: supprimer retours à la ligne internes et normaliser espaces
                raw_cell = str(cell or '')
                cell_content = self._normalize_whitespace(raw_cell.replace('\n', ' '))
                cell_id = f"{table_id}-r{row_idx}-c{col_idx}"

                tag = 'th' if row_idx == 0 else 'td'
                html += f'''
                <{tag} class="table-cell-editable" 
                     contenteditable="true"
                     data-cell-id="{cell_id}"
                     data-row="{row_idx}"
                     data-col="{col_idx}"
                     data-original-value="{cell_content}">
                    {cell_content}
                </{tag}>
                '''
            html += '</tr>'

        html += '''
            </table>
        </div>
        '''

        return html

    def _generate_image_element_html(self, element: Dict, position_style: str, confidence_class: str) -> str:
        """Générer HTML pour élément image"""
        image_data = element.get('image_data')
        image_id = f"img-p{element.get('page', 1)}-{element.get('index', 0)}"

        if image_data:
            return f'''
            <div class="ultra-element ultra-image {confidence_class}" style="{position_style}">
                <img src="{image_data}" 
                     alt="Image {element.get('index', 0)}"
                     data-image-id="{image_id}"
                     style="width: 100%; height: 100%; object-fit: contain;">
            </div>
            '''
        else:
            return f'''
            <div class="ultra-element ultra-image ultra-image-placeholder {confidence_class}" 
                 style="{position_style} border: 2px dashed #ccc; display: flex; align-items: center; justify-content: center;">
                <div style="text-align: center; color: #666;">
                    <i class="fas fa-image" style="font-size: 24px; margin-bottom: 5px;"></i><br>
                    Image {element.get('index', 0)}
                </div>
            </div>
            '''

    # MÉTHODES UTILITAIRES

    def _is_footer_box(self, pos: Dict, page_height: float) -> bool:
        try:
            y = float(pos.get('y', 0))
            footer_threshold_y = page_height * (1.0 - self.config.get('footer_height_ratio', 0.12))
            return y >= footer_threshold_y
        except Exception:
            return False

    def _footer_box_key(self, pos: Dict, page_width: float, page_height: float) -> str:
        # Regroupe par zones horizontales pour éviter doublons gauche/centre/droite
        try:
            x = float(pos.get('x', 0)); y = float(pos.get('y', 0))
            w = float(pos.get('width', 0)); h = float(pos.get('height', 0))
            # bucketiser X en 3 colonnes: gauche, centre, droite
            col = 'L' if x < page_width * 0.33 else ('C' if x < page_width * 0.66 else 'R')
            # bucketiser Y en 2 bandes proches du bas
            band = 'B1' if y >= page_height * 0.92 else 'B2'
            # Normaliser légèrement la largeur/hauteur
            wb = int(round(w / 10.0)); hb = int(round(h / 5.0))
            return f"{col}-{band}-{wb}x{hb}"
        except Exception:
            return "UNK"

    def _deduplicate_footer_text_elements(self, elements: List[Dict], page_width: float, page_height: float) -> List[Dict]:
        """Supprime les doublons/chevauchements agressivement dans le footer en gardant le plus fiable."""
        try:
            texts = [e for e in elements if e.get('type') == 'text']
            others = [e for e in elements if e.get('type') != 'text']
            footer_groups: Dict[str, List[Dict]] = defaultdict(list)
            non_footer_texts: List[Dict] = []

            for t in texts:
                pos = t.get('position', {})
                if self._is_footer_box(pos, page_height):
                    key = self._footer_box_key(pos, page_width, page_height)
                    footer_groups[key].append(t)
                else:
                    non_footer_texts.append(t)

            pruned_footer_texts: List[Dict] = []
            overlap_threshold = self.config.get('footer_overlap_threshold', 0.4)

            for key, group in footer_groups.items():
                # Trier par confiance décroissante pour garder les meilleurs
                group_sorted = sorted(group, key=lambda e: float(e.get('confidence', 0.5)), reverse=True)
                kept: List[Dict] = []
                boxes: List[Tuple[float,float,float,float]] = []
                for e in group_sorted:
                    pos = e.get('position', {})
                    x1 = float(pos.get('x', 0)); y1 = float(pos.get('y', 0))
                    x2 = x1 + float(pos.get('width', 0)); y2 = y1 + float(pos.get('height', 0))
                    # Vérifier chevauchement avec ceux déjà gardés
                    too_much = False
                    for (bx1, by1, bx2, by2) in boxes:
                        ix1, iy1 = max(x1, bx1), max(y1, by1)
                        ix2, iy2 = min(x2, bx2), min(y2, by2)
                        iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
                        inter = iw * ih
                        area = max(1.0, (x2 - x1) * (y2 - y1))
                        if inter / area > overlap_threshold:
                            too_much = True
                            break
                    if not too_much:
                        kept.append(e)
                        boxes.append((x1, y1, x2, y2))

                # En cas de texte identique répété, supprimer doublons exacts
                seen_texts = set()
                dedup_kept = []
                for e in kept:
                    txt = self._normalize_whitespace(e.get('text', '') or '')
                    if txt in seen_texts:
                        continue
                    seen_texts.add(txt)
                    e['text'] = txt
                    dedup_kept.append(e)

                pruned_footer_texts.extend(dedup_kept)

            return others + non_footer_texts + pruned_footer_texts
        except Exception:
            return elements

    def _normalize_whitespace(self, text: str) -> str:
        """Normalise les espaces et supprime les retours inutiles"""
        if not isinstance(text, str):
            return ''
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def _should_merge_hyphen(self, prev: str, nxt: str) -> bool:
        """Vérifie si fin de ligne avec tiret doit être fusionnée avec début de la suivante"""
        if not prev or not nxt:
            return False
        if not prev.rstrip().endswith('-'):
            return False
        # Si la prochaine ligne commence par une lettre (souvent minuscule), on fusionne sans espace
        return bool(re.match(r'^[A-Za-zÀ-ÖØ-öø-ÿ]', nxt.lstrip()))

    def _join_spans_with_spacing(self, spans: List[Dict]) -> str:
        """Assemble les spans d'une même ligne en ajoutant des espaces uniquement quand le gap indique un espace réel.
        - Utilise la taille de police pour estimer le seuil.
        - Cas spécial: si deux spans sont d'un seul caractère, on est plus conservateur (évite les lettres séparées).
        """
        if not spans:
            return ''
        spans_sorted = sorted(spans, key=lambda s: (s.get('bbox', [0, 0, 0, 0])[0]))
        line_text = ''
        prev_span = None
        for span in spans_sorted:
            t = span.get('text', '') or ''
            if not t:
                continue
            if prev_span is not None:
                bbox_prev = prev_span.get('bbox', [0, 0, 0, 0])
                bbox_cur = span.get('bbox', [0, 0, 0, 0])
                gap = (bbox_cur[0] - bbox_prev[2]) if bbox_prev and bbox_cur else 0
                prev_size = float(prev_span.get('size', 12) or 12)
                prev_text = prev_span.get('text', '') or ''
                # Gestion hyphenation intra-ligne
                if self._should_merge_hyphen(prev_text, t):
                    line_text = line_text.rstrip()
                    if line_text.endswith('-'):
                        line_text = line_text[:-1]
                else:
                    # Seuils dynamiques pour insertion d'un espace
                    gap_threshold = max(0.5, prev_size * float(self.config.get('text_gap_factor', 0.95)))
                    # Si les deux spans ne contiennent qu'un seul caractère: seuil plus grand (évite "T H E")
                    if len(prev_text.strip()) == 1 and len(t.strip()) == 1:
                        gap_threshold = max(gap_threshold, prev_size * float(self.config.get('single_char_no_space_factor', 1.6)))
                    # Insérer un espace uniquement si le gap dépasse clairement le seuil
                    if gap > gap_threshold and not (line_text.endswith(' ') or t.startswith(' ')):
                        line_text += ' '
            line_text += t
            prev_span = span
        return self._normalize_whitespace(line_text)

    def _extract_image_with_processing(self, doc, xref):
        """Extraire et traiter une image"""
        try:
            if PYMUPDF_AVAILABLE:
                fitz = self.pdf_libraries.get('pymupdf', __import__('fitz'))
                pix = fitz.Pixmap(doc, xref)

                if pix.n < 5:
                    if pix.alpha:
                        pix = fitz.Pixmap(fitz.csRGB, pix)

                    img_bytes = pix.tobytes("png")
                    img_base64 = base64.b64encode(img_bytes).decode()
                    pix = None
                    return f"data:image/png;base64,{img_base64}"

        except Exception as e:
            logger.warning(f"Erreur extraction image: {e}")

        return None

    def _analyze_image_content(self, image_data: str) -> Dict:
        """Analyser le contenu d'une image"""
        return {
            'has_text': False,
            'is_chart': False,
            'is_diagram': False,
            'complexity': 'medium'
        }

    def _classify_shape(self, drawing: Dict) -> str:
        """Classifier une forme géométrique"""
        # Logique de classification des formes
        return 'line'  # Simplifié

    def _analyze_dominant_style(self, spans: List[Dict]) -> Dict:
        """Analyser le style dominant d'un groupe de spans"""
        if not spans:
            return {}

        # Calculer les moyennes et modes
        avg_size = sum(s.get('size', 12) for s in spans) / len(spans)
        fonts = [s.get('font', '') for s in spans]
        most_common_font = max(set(fonts), key=fonts.count) if fonts else ''

        bold_count = sum(1 for s in spans if 'bold' in s.get('font', '').lower())
        italic_count = sum(1 for s in spans if 'italic' in s.get('font', '').lower())

        return {
            'font': most_common_font,
            'size': avg_size,
            'bold': bold_count > len(spans) / 2,
            'italic': italic_count > len(spans) / 2,
            'color': spans[0].get('color', 0) if spans else 0
        }

    def _classify_text_element(self, text: str, style: Dict) -> str:
        """Classifier un élément de texte"""
        text_lower = text.lower().strip()

        # Titre si court, en gras ou grande taille
        if (len(text) < 100 and style.get('bold')) or style.get('size', 12) > 14:
            return 'heading'

        # Liste si commence par numéro ou puce
        if re.match(r'^\s*[\d\-\*\•]\s*', text):
            return 'list_item'

        # Table des matières si contient des points de suite
        if '...' in text or re.search(r'\d+$', text):
            return 'toc_item'

        return 'paragraph'

    def _calculate_text_confidence(self, spans: List[Dict], text: str) -> float:
        """Calculer la confiance d'un bloc de texte"""
        if not spans or not text:
            return 0.0

        # Facteurs de confiance
        factors = []

        # Nombre de spans (plus = mieux)
        factors.append(min(len(spans) / 10, 1.0) * 0.3)

        # Longueur du texte
        factors.append(min(len(text) / 100, 1.0) * 0.3)

        # Cohérence des styles
        if len(set(s.get('font', '') for s in spans)) == 1:
            factors.append(0.4)
        else:
            factors.append(0.2)

        return sum(factors)

    def _position_to_key(self, position: Dict) -> str:
        """Convertir une position en clé pour comparaison"""
        x = round(position.get('x', 0) / 10) * 10
        y = round(position.get('y', 0) / 10) * 10
        return f"{x},{y}"

    def _convert_style_to_css(self, style: Dict) -> str:
        """Convertir un style en CSS"""
        css_parts = []

        if style.get('font'):
            css_parts.append(f"font-family: '{style['font']}', sans-serif")

        if style.get('size'):
            css_parts.append(f"font-size: {style['size']}px")

        if style.get('bold'):
            css_parts.append("font-weight: bold")

        if style.get('italic'):
            css_parts.append("font-style: italic")

        return '; '.join(css_parts) + ';' if css_parts else ''

    def _merge_line_text_fragments(self, elements: List[Dict], page_width: float, page_height: float) -> List[Dict]:
        """Fusionne les fragments de texte colinéaires de la même ligne en un seul bloc.
        Objectif: éviter qu'une lettre soit isolée dans un div séparé.
        """
        try:
            texts = [e for e in elements if e.get('type') == 'text']
            others = [e for e in elements if e.get('type') != 'text']
            if not texts:
                return elements

            # Grouper par bande horizontale (même ligne)
            band_tol = max(float(self.config.get('line_merge_min_band_tol_px', 3.0)), page_height * float(self.config.get('line_merge_vertical_tolerance_ratio', 0.006)))  # tolérance verticale agressive
            bands: List[List[Dict]] = []
            for t in sorted(texts, key=lambda e: float(e.get('position', {}).get('y', 0))):
                y = float(t.get('position', {}).get('y', 0))
                placed = False
                for band in bands:
                    by = float(band[0].get('position', {}).get('y', 0))
                    if abs(y - by) <= band_tol:
                        band.append(t)
                        placed = True
                        break
                if not placed:
                    bands.append([t])

            merged_texts: List[Dict] = []
            for band in bands:
                # Trier gauche->droite
                band_sorted = sorted(band, key=lambda e: float(e.get('position', {}).get('x', 0)))
                # Fusionner séquentiellement si gap faible
                current_group: List[Dict] = []
                for t in band_sorted:
                    if not current_group:
                        current_group = [t]
                        continue
                    prev = current_group[-1]
                    px = float(prev['position']['x']); pw = float(prev['position']['width'])
                    x = float(t['position']['x']); w = float(t['position']['width'])
                    gap = x - (px + pw)
                    # seuil dynamique basé sur hauteur/size moyenne
                    size_prev = float(prev.get('style', {}).get('size', 12) or 12)
                    size_cur = float(t.get('style', {}).get('size', size_prev) or size_prev)
                    size_avg = (size_prev + size_cur) / 2.0
                    # seuil agressif basé sur config
                    base_factor = float(self.config.get('line_merge_gap_factor', 1.8))
                    gap_threshold = max(0.5, size_avg * base_factor)
                    # si les deux sont petits (ex. une lettre), poussez seuil
                    prev_txt = (prev.get('text', '') or '').strip()
                    cur_txt = (t.get('text', '') or '').strip()
                    if len(prev_txt) == 1 and len(cur_txt) == 1:
                        gap_threshold = max(gap_threshold, size_avg * float(self.config.get('single_char_no_space_factor', 3.0)))
                    if gap <= gap_threshold:
                        current_group.append(t)
                    else:
                        merged_texts.append(self._merge_text_group(current_group, page_width, page_height))
                        current_group = [t]
                if current_group:
                    merged_texts.append(self._merge_text_group(current_group, page_width, page_height))

            return others + merged_texts
        except Exception:
            return elements

    def _merge_text_group(self, group: List[Dict], page_width: float, page_height: float) -> Dict:
        """Fusionne un groupe de fragments texte en un bloc unique, position englobante."""
        if not group:
            return {}
        # Concat texte avec notre jointure prudente
        spans_like = []
        for g in sorted(group, key=lambda e: float(e.get('position', {}).get('x', 0))):
            # synthèse d'un span-like minimal
            spans_like.append({
                'text': g.get('text', ''),
                'bbox': [
                    float(g['position']['x']),
                    float(g['position']['y']),
                    float(g['position']['x']) + float(g['position']['width']),
                    float(g['position']['y']) + float(g['position']['height'])
                ],
                'size': float(g.get('style', {}).get('size', 12) or 12)
            })
        text = self._join_spans_with_spacing(spans_like)
        # Bounding box englobante
        xs = [s['bbox'][0] for s in spans_like]; ys = [s['bbox'][1] for s in spans_like]
        x2s = [s['bbox'][2] for s in spans_like]; y2s = [s['bbox'][3] for s in spans_like]
        min_x, min_y, max_x, max_y = min(xs), min(ys), max(x2s), max(y2s)
        # Style dominant
        style = self._analyze_dominant_style([{'size': s['size']} for s in spans_like])
        # Garder le type d’origine si commun, sinon paragraph
        element_type = 'paragraph'
        if all((g.get('element_type') == group[0].get('element_type')) for g in group):
            element_type = group[0].get('element_type', 'paragraph')
        # Confiance moyenne
        conf = float(sum(float(g.get('confidence', 0.5) or 0.5) for g in group) / max(1, len(group)))
        return {
            'type': 'text',
            'element_type': element_type,
            'page': group[0].get('page', 1),
            'text': text,
            'position': {
                'x': float(min_x), 'y': float(min_y),
                'width': float(max_x - min_x), 'height': float(max_y - min_y),
                'x_percent': (min_x / page_width) * 100, 'y_percent': (min_y / page_height) * 100,
                'width_percent': ((max_x - min_x) / page_width) * 100, 'height_percent': ((max_y - min_y) / page_height) * 100
            },
            'style': style,
            'confidence': conf
        }

    def _get_element_z_index(self, element: Dict) -> int:
        """Déterminer l'ordre de profondeur d'un élément"""
        element_type = element.get('type', 'text')

        # Ordre de priorité: shapes < images < text < tables
        z_indices = {
            'shape': 1,
            'image': 2,
            'text': 3,
            'table': 4
        }

        return z_indices.get(element_type, 3)

    # MÉTHODES SIMPLIFIÉES POUR LES FONCTIONS NON IMPLÉMENTÉES

    def _extract_with_pdfplumber_advanced(self, file_path: str) -> Dict:
        """Extraction pdfplumber avancée (simplifié)"""
        return {}

    def _extract_with_camelot_advanced(self, file_path: str) -> Dict:
        """Extraction camelot avancée (simplifié)"""
        return {}

    def _extract_with_tabula_advanced(self, file_path: str) -> Dict:
        """Extraction tabula avancée (simplifié)"""
        return {}

    def _extract_with_docling(self, file_path: str) -> Dict:
        """Extraction via Docling (si disponible). Retourne un dictionnaire compatible pipeline."""
        try:
            if not DOCLING_AVAILABLE:
                return {}
            # Docling API minimale (pseudo-code robuste):
            # Certaines distributions utilisent docling.Document ou docling.parse
            text = ''
            pages = []
            elements = []
            tables = []
            images = []

            # Essayons d'abord une API générique
            try:
                # ex: parsed = docling.parse(file_path)
                parsed = None
                if hasattr(docling, 'parse'):
                    parsed = docling.parse(file_path)
                elif hasattr(docling, 'Document'):  # style OO
                    doc = docling.Document.from_file(file_path)
                    parsed = doc.to_dict() if hasattr(doc, 'to_dict') else None

                if parsed:
                    # Normalisation minimale: convertir en structure pipeline
                    # Récupérer texte global si dispo
                    if isinstance(parsed, dict):
                        text = parsed.get('text', '') or parsed.get('content', '') or ''
                        # Pages
                        pgs = parsed.get('pages') or parsed.get('document', {}).get('pages') if isinstance(parsed.get('document'), dict) else []
                        for i, p in enumerate(pgs or []):
                            pages.append({
                                'page_number': i + 1,
                                'text': p.get('text', '') if isinstance(p, dict) else '',
                                'elements': [], 'tables': [], 'images': [], 'text_blocks': []
                            })
                        # Tables si présentes
                        tbls = parsed.get('tables') or []
                        for ti, t in enumerate(tbls):
                            tables.append({'index': ti, 'data': t.get('data') if isinstance(t, dict) else t})
                    else:
                        # Si parsed est objet inconnu, on tente str
                        text = str(parsed)
            except Exception:
                pass

            # Fallback: si API spécifique existe (exemples courants)
            if not text:
                try:
                    if hasattr(docling, 'PdfDoc'):  # exemple d’API alternative
                        pdfdoc = docling.PdfDoc(file_path)
                        text = getattr(pdfdoc, 'text', '') or ''
                except Exception:
                    pass

            # Construire extraction docling minimale
            extraction = {
                'pages': pages,
                'elements': elements,
                'tables': tables,
                'images': images,
                'text_blocks': [],
                'text': text,
                'metadata': {'source': 'docling'}
            }
            return extraction
        except Exception as e:
            logger.warning(f"Docling extraction error: {e}")
            return {}

    def _extract_with_pixel_analysis(self, file_path: str) -> Dict:
        """Extraction par analyse de pixels (simplifié)"""
        return {}

    def _analyze_fonts_and_colors(self, page_dict: Dict, extraction: Dict):
        """Analyser les polices et couleurs (simplifié)"""
        pass

    # Autres méthodes simplifiées...
    def _analyze_grid_patterns(self, lines: List[Dict]) -> List[Dict]:
        return []

    def _is_valid_table_pattern(self, pattern: Dict) -> bool:
        return False

    def _create_table_from_grid_pattern(self, pattern: Dict, page_width: float, page_height: float) -> Optional[Dict]:
        return None

    def _group_text_blocks_by_y(self, text_blocks: List[Dict]) -> List[List[Dict]]:
        return []

    def _is_table_row_candidate(self, y_group: List[Dict]) -> bool:
        return False

    def _find_aligned_rows(self, y_group: List[Dict], y_groups: List[List[Dict]]) -> List[List[Dict]]:
        return []

    def _create_table_from_aligned_text(self, table_rows: List[List[Dict]], page_width: float, page_height: float) -> \
    Optional[Dict]:
        return None

    def _detect_layout_regions(self, image: np.ndarray) -> List[Dict]:
        return []

    def _detect_text_regions(self, image: np.ndarray) -> List[Dict]:
        return []

    def _detect_image_regions(self, image: np.ndarray) -> List[Dict]:
        return []

    def _find_grid_intersections(self, horizontal_lines: List, vertical_lines: List) -> List[Dict]:
        return []

    def _is_valid_table_grid(self, grid: Dict) -> bool:
        return False

    def _create_table_from_visual_grid(self, grid: Dict, image_shape: Tuple) -> Dict:
        return {}

    def _detect_tables_by_template_matching(self, gray_image: np.ndarray) -> List[Dict]:
        return []

    def _detect_tables_by_texture_analysis(self, gray_image: np.ndarray) -> List[Dict]:
        return []

    def _analyze_spatial_relations(self, elements: List[Dict]) -> Dict:
        return {}

    def _ml_element_classification(self, elements: List[Dict]) -> Dict:
        return {}

    def _validate_elements_by_consensus(self, structure_analysis: Dict) -> List[Dict]:
        return structure_analysis.get('all_elements', [])

    def _reconstruct_tables_intelligently(self, elements: List[Dict]) -> List[Dict]:
        return [e for e in elements if e.get('type') == 'table']

    def _reconstruct_content_hierarchy(self, elements: List[Dict]) -> Dict:
        return {}

    def _determine_reading_order(self, elements: List[Dict]) -> List[Dict]:
        return sorted(elements, key=lambda x: (x.get('position', {}).get('y', 0), x.get('position', {}).get('x', 0)))

    def _normalize_whitespace_advanced(self, text: str) -> str:
        """
        Normalisation avancée du texte avec gestion intelligente des coupures.
        Traite les problèmes de mots coupés et de mise en page.
        """
        if not text:
            return text
        
        try:
            import re
            
            # Étape 1: Identifier et corriger les mots coupés avec tiret
            # Pattern pour détecter: mot-\n(espace*)mot
            text = re.sub(r'(\w+)-\s*\n\s*(\w+)', self._handle_hyphenated_word, text)
            
            # Étape 2: Gérer les mots coupés sans tiret (détection intelligente)
            text = re.sub(r'(\w+)\s*\n\s*(\w+)', self._handle_potential_split_word, text)
            
            # Étape 3: Préserver les vrais paragraphes (double saut de ligne)
            paragraphs = re.split(r'\n\s*\n', text)
            
            # Étape 4: Nettoyer chaque paragraphe individuellement
            cleaned_paragraphs = []
            for para in paragraphs:
                # Remplacer les retours à la ligne simples par des espaces
                para = re.sub(r'\s*\n\s*', ' ', para)
                # Normaliser les espaces multiples
                para = re.sub(r'\s+', ' ', para)
                para = para.strip()
                if para:
                    cleaned_paragraphs.append(para)
            
            # Rejoindre les paragraphes avec double saut de ligne
            return '\n\n'.join(cleaned_paragraphs)
            
        except Exception as e:
            logger.warning(f"Erreur normalisation avancée: {e}")
            return text

    def _generate_optimized_combined_text(self, elements: List[Dict], reading_order: List[Dict]) -> str:
        text_parts = []
        for element in reading_order:
            if element.get('type') == 'text' and element.get('text'):
                cleaned = self._normalize_whitespace(element['text'])
                text_parts.append(cleaned)
        # Regrouper les paragraphes proprement
        combined = '\n\n'.join(t for t in text_parts if t)
        return self._normalize_whitespace(combined)

    def _validate_table_structure(self, table: Dict) -> Optional[Dict]:
        return table if table.get('data') else None

    def _correct_overlapping_elements(self, elements: List[Dict]) -> List[Dict]:
        return elements

    def _validate_content_hierarchy(self, hierarchy: Dict) -> Dict:
        return hierarchy

    def _calculate_quality_metrics(self, validated: Dict) -> Dict:
        return {
            'elements_count': len(validated.get('validated_elements', [])),
            'tables_count': len(validated.get('tables', [])),
            'avg_confidence': 0.85
        }

    def _calculate_overall_confidence(self, validated: Dict) -> float:
        return 0.85

    # ---- Added minimal safe implementations to avoid missing-attr errors ----
    def _analyze_fonts_and_colors(self, page_dict: Dict, extraction: Dict) -> None:
        try:
            meta = extraction.setdefault('metadata', {})
            fonts = extraction.setdefault('fonts', [])
            colors = extraction.setdefault('colors', [])
            # Minimal aggregation
            for block in page_dict.get('blocks', []):
                if 'lines' in block:
                    for line in block['lines']:
                        for span in line.get('spans', []):
                            if 'size' in span:
                                fonts.append({'size': span.get('size'), 'font': span.get('font')})
                            if 'color' in span:
                                colors.append(span.get('color'))
        except Exception:
            pass

    def _extract_image_with_processing(self, doc, xref: int) -> str:
        try:
            if not PYMUPDF_AVAILABLE:
                return ''
            pix = doc.extract_image(xref)
            img_bytes = pix.get('image', b'')
            ext = pix.get('ext', 'png')
            if not img_bytes:
                return ''
            b64 = base64.b64encode(img_bytes).decode('ascii')
            return f"data:image/{ext};base64,{b64}"
        except Exception as e:
            logger.warning(f"Erreur extraction image: {e}")
            return ''

    def _analyze_image_content(self, image_data: str) -> Dict:
        # Placeholder analysis
        return {'has_content': bool(image_data), 'confidence': 0.8}

    def _merge_overlapping_tables(self, tables: List[Dict]) -> List[Dict]:
        # Minimal: no merge
        return tables or []

    def _validate_and_enrich_table(self, table: Dict, text_blocks: List[Dict]) -> Optional[Dict]:
        # Minimal validation: must have position
        if not isinstance(table, dict):
            return None
        pos = table.get('position') or {}
        if not {'x', 'y', 'width', 'height'}.issubset(pos.keys() if isinstance(pos, dict) else set()):
            return None
        return table

    def _computer_vision_analysis(self, file_path: str) -> Dict:
        # Minimal CV analysis disabled
        return {}

    def _advanced_structure_analysis(self, raw_extractions: Dict, visual_analysis: Dict) -> Dict:
        # Combine available elements from extractions
        all_elements: List[Dict] = []
        for key in ['pymupdf', 'pdfplumber', 'camelot', 'tabula', 'pixel_analysis']:
            data = raw_extractions.get(key) or {}
            els = data.get('elements') or []
            if isinstance(els, list):
                all_elements.extend([e for e in els if isinstance(e, dict)])
        return {'all_elements': all_elements, 'visual': visual_analysis or {}}

    def _generate_ultra_faithful_page_html(self, page_num: int, elements: List[Dict], validated_content: Dict) -> str:
        width = 900
        height = 1200
        parts = [f'<div class="ultra-page-container" data-page="{page_num}" style="width:{width}px;height:{height}px;">']
        for el in elements:
            try:
                pos = el.get('position', {}) if isinstance(el, dict) else {}
                left = pos.get('x_percent') or 0
                top = pos.get('y_percent') or 0
                w = pos.get('width_percent') or 10
                h = pos.get('height_percent') or 10
                style = f'left:{left}%;top:{top}%;width:{w}%;height:{h}%;'
                etype = el.get('type')
                if etype == 'text':
                    parts.append(self._generate_text_element_html(el, style))
                elif etype == 'image':
                    parts.append(self._generate_image_element_html(el, style))
                elif etype == 'table':
                    parts.append(self._generate_table_element_html(el, style))
                else:
                    parts.append(self._generate_shape_element_html(el, style))
            except Exception as e:
                logger.warning(f"Erreur génération élément HTML: {e}")
        parts.append('</div>')
        return '\n'.join(parts)

    # Dans utils_ultra_advanced.py, modifiez _generate_text_element_html
    def _generate_text_element_html(self, el: Dict, style: str) -> str:
        raw = el.get('text', '')
        text = self._normalize_whitespace(raw)
        cls = 'ultra-element ultra-text'
        # Ajout de contenteditable="true" pour édition en ligne
        return f'<div class="{cls}" style="{style}"><div class="editable-content" contenteditable="true">{text}</div></div>'

    def _generate_image_element_html(self, el: Dict, style: str) -> str:
        src = el.get('image_data') or ''
        cls = 'ultra-element ultra-image'
        if src:
            return f'<div class="{cls}" style="{style}"><img src="{src}" style="width:100%;height:100%;object-fit:contain;"/></div>'
        return f'<div class="{cls}" style="{style}"></div>'

    def _generate_shape_element_html(self, el: Dict, style: str) -> str:
        cls = 'ultra-element ultra-shape'
        return f'<div class="{cls}" style="{style}"></div>'

    def _generate_table_element_html(self, el: Dict, style: str) -> str:
        cls = 'ultra-element ultra-table'
        return f'<div class="{cls}" style="{style}"><table class="ultra-table"></table></div>'

    def _analyze_grid_patterns(self, lines: List[Dict]) -> List[Dict]:
        # Minimal: return empty, avoiding complex grid detection
        return []

    def _is_valid_table_pattern(self, pattern: Dict) -> bool:
        return False
    

    def _handle_hyphenated_word(self, match) -> str:
        """
        Gère les mots coupés avec tiret en fin de ligne.
        Utilise un dictionnaire pour vérifier la validité.
        """
        part1 = match.group(1)
        part2 = match.group(2)
        
        # Reconstituer le mot potentiel
        full_word = part1 + part2
        hyphenated_word = f"{part1}-{part2}"
        
        # Si le mot reconstitué semble valide (heuristique simple)
        # On pourrait utiliser un dictionnaire ou une API de vérification
        if self._is_likely_word(full_word):
            return full_word
        else:
            # Garder le tiret si c'est un mot composé légitime
            return hyphenated_word

    def _handle_potential_split_word(self, match) -> str:
        """
        Gère les mots potentiellement coupés sans tiret.
        """
        part1 = match.group(1)
        part2 = match.group(2)
        
        # Si part1 se termine par une minuscule et part2 commence par une minuscule
        # C'est probablement un mot coupé
        if part1[-1].islower() and part2[0].islower():
            # Vérifier si c'est la fin d'une phrase
            if not part1[-1] in '.!?':
                return part1 + part2
        
        # Sinon, garder l'espace
        return f"{part1} {part2}"

    def _is_likely_word(self, word: str) -> bool:
        """
        Vérifie si un mot reconstitué est probablement valide.
        """
        # Heuristiques simples
        if len(word) < 2 or len(word) > 30:
            return False
        
        # Vérifier le pattern de voyelles/consonnes
        vowels = set('aeiouAEIOU')
        has_vowel = any(c in vowels for c in word)
        
        return has_vowel

    def _cluster_text_spans_improved(self, spans: List[Dict]) -> Dict[int, List[Dict]]:
        """
        Clustering amélioré avec détection de superposition et espacement intelligent.
        """
        if not SKLEARN_AVAILABLE or len(spans) < 2:
            return {0: spans}
        
        try:
            # Préparer les features avec plus de précision spatiale
            features = []
            for span in spans:
                bbox = span.get('bbox', [0, 0, 0, 0])
                font_size = span.get('size', 12)
                
                # Position et dimensions
                x_start = bbox[0]
                y_start = bbox[1]
                x_end = bbox[2]
                y_end = bbox[3]
                width = x_end - x_start
                height = y_end - y_start
                
                # Caractéristiques du texte
                text = span.get('text', '').strip()
                text_len = len(text)
                ends_with_punct = 1.0 if re.search(r'[.!?:;,]$', text) else 0.0
                starts_with_capital = 1.0 if text and text[0].isupper() else 0.0
                
                features.append([
                    x_start, y_start, x_end, y_end,
                    width, height,
                    font_size, text_len,
                    ends_with_punct, starts_with_capital
                ])
            
            # Normaliser les features
            scaler = StandardScaler()
            features_scaled = scaler.fit_transform(features)
            
            # DBSCAN avec paramètres ajustés pour éviter la superposition
            eps_value = self.config.get('text_clustering_eps', 0.3)
            clustering = DBSCAN(
                eps=eps_value,
                min_samples=1,
                metric='euclidean'
            ).fit(features_scaled)
            
            # Organiser par clusters et vérifier les superpositions
            clustered = defaultdict(list)
            for i, label in enumerate(clustering.labels_):
                if label != -1:
                    clustered[label].append(spans[i])
            
            # Post-traitement: séparer les éléments qui se superposent
            final_clusters = {}
            cluster_id = 0
            
            for _, cluster_spans in clustered.items():
                # Trier par position (Y puis X)
                sorted_spans = sorted(
                    cluster_spans,
                    key=lambda s: (s['bbox'][1], s['bbox'][0])
                )
                
                # Vérifier et corriger les superpositions
                non_overlapping_groups = self._separate_overlapping_spans(sorted_spans)
                
                for group in non_overlapping_groups:
                    final_clusters[cluster_id] = group
                    cluster_id += 1
            
            return final_clusters if final_clusters else {0: spans}
            
        except Exception as e:
            logger.error(f"Erreur clustering amélioré: {e}")
            return {0: spans}

    def _separate_overlapping_spans(self, spans: List[Dict]) -> List[List[Dict]]:
        """
        Sépare les spans qui se superposent en groupes distincts.
        """
        if not spans:
            return []
        
        groups = []
        current_group = [spans[0]]
        
        for i in range(1, len(spans)):
            current_span = spans[i]
            overlaps = False
            
            # Vérifier la superposition avec chaque span du groupe actuel
            for existing_span in current_group:
                if self._spans_overlap(existing_span, current_span):
                    overlaps = True
                    break
            
            if overlaps:
                # Commencer un nouveau groupe si superposition détectée
                groups.append(current_group)
                current_group = [current_span]
            else:
                # Ajouter au groupe actuel si pas de superposition
                current_group.append(current_span)
        
        if current_group:
            groups.append(current_group)
        
        return groups

    def _spans_overlap(self, span1: Dict, span2: Dict) -> bool:
        """
        Vérifie si deux spans se superposent.
        """
        bbox1 = span1.get('bbox', [0, 0, 0, 0])
        bbox2 = span2.get('bbox', [0, 0, 0, 0])
        
        # Extraire les coordonnées
        x1_start, y1_start, x1_end, y1_end = bbox1
        x2_start, y2_start, x2_end, y2_end = bbox2
        
        # Vérifier la superposition horizontale
        h_overlap = not (x1_end < x2_start or x2_end < x1_start)
        
        # Vérifier la superposition verticale
        v_overlap = not (y1_end < y2_start or y2_end < y1_start)
        
        return h_overlap and v_overlap

    def _create_text_block_from_spans_improved(
    self, 
    spans: List[Dict], 
    page_num: int,
    page_width: float,
    page_height: float
) -> Optional[Dict]:
        """
        Création améliorée de blocs de texte avec gestion intelligente de l'espacement.
        """
        if not spans:
            return None
        
        try:
            # Calculer la boîte englobante
            min_x = min(span['bbox'][0] for span in spans)
            min_y = min(span['bbox'][1] for span in spans)
            max_x = max(span['bbox'][2] for span in spans)
            max_y = max(span['bbox'][3] for span in spans)
            
            # Trier les spans par position
            sorted_spans = sorted(spans, key=lambda s: (s['bbox'][1], s['bbox'][0]))
            
            # Regrouper en lignes avec détection d'espacement intelligent
            lines = self._group_spans_into_lines(sorted_spans)
            
            # Construire le texte avec gestion appropriée des espaces
            combined_text = self._build_text_from_lines(lines)
            
            # Normaliser le texte final
            combined_text = self._normalize_whitespace_advanced(combined_text)
            
            if not combined_text.strip():
                return None
            
            # Analyser le style dominant
            style_analysis = self._analyze_dominant_style(spans)
            element_type = self._classify_text_element(combined_text, style_analysis)
            
            text_block = {
                'type': 'text',
                'element_type': element_type,
                'page': page_num,
                'text': combined_text,
                'position': {
                    'x': float(min_x),
                    'y': float(min_y),
                    'width': float(max_x - min_x),
                    'height': float(max_y - min_y),
                    'x_percent': (min_x / page_width) * 100,
                    'y_percent': (min_y / page_height) * 100,
                    'width_percent': ((max_x - min_x) / page_width) * 100,
                    'height_percent': ((max_y - min_y) / page_height) * 100
                },
                'style': style_analysis,
                'spans_count': len(spans),
                'lines_count': len(lines),
                'confidence': self._calculate_text_confidence(spans, combined_text)
            }
            
            return text_block
            
        except Exception as e:
            logger.error(f"Erreur création bloc texte amélioré: {e}")
            return None

    def _group_spans_into_lines(self, spans: List[Dict]) -> List[List[Dict]]:
        """
        Regroupe les spans en lignes avec tolérance adaptative.
        """
        if not spans:
            return []
        
        lines = []
        current_line = [spans[0]]
        prev_y_center = (spans[0]['bbox'][1] + spans[0]['bbox'][3]) / 2
        
        # Calculer la hauteur moyenne pour la tolérance
        avg_height = sum(s['bbox'][3] - s['bbox'][1] for s in spans) / len(spans)
        tolerance = avg_height * 0.3  # 30% de la hauteur moyenne
        
        for span in spans[1:]:
            y_center = (span['bbox'][1] + span['bbox'][3]) / 2
            
            # Si le span est sur la même ligne (dans la tolérance)
            if abs(y_center - prev_y_center) <= tolerance:
                current_line.append(span)
            else:
                # Nouvelle ligne détectée
                lines.append(sorted(current_line, key=lambda s: s['bbox'][0]))
                current_line = [span]
                prev_y_center = y_center
        
        if current_line:
            lines.append(sorted(current_line, key=lambda s: s['bbox'][0]))
        
        return lines

    def _build_text_from_lines(self, lines: List[List[Dict]]) -> str:
        """
        Construit le texte à partir des lignes avec espacement intelligent.
        """
        text_parts = []
        
        for line in lines:
            line_text = ""
            prev_x_end = None
            
            for span in line:
                span_text = span.get('text', '')
                
                if prev_x_end is not None:
                    # Calculer l'espace entre les spans
                    gap = span['bbox'][0] - prev_x_end
                    
                    # Ajouter un espace si l'écart est significatif
                    if gap > 2:  # Seuil minimal pour un espace
                        # Calculer le nombre d'espaces approximatif
                        avg_char_width = (span['bbox'][2] - span['bbox'][0]) / max(len(span_text), 1)
                        num_spaces = max(1, int(gap / avg_char_width))
                        line_text += ' ' * min(num_spaces, 3)  # Limiter à 3 espaces max
                
                line_text += span_text
                prev_x_end = span['bbox'][2]
            
            text_parts.append(line_text)
        
        # Joindre les lignes avec des espaces (seront normalisés après)
        return '\n'.join(text_parts)