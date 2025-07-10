import os
import re
import json
import requests
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
import tabulate
import spacy
from PyPDF2 import PdfReader
from langdetect import detect
from dotenv import load_dotenv
import difflib
import pdfplumber
from collections import defaultdict
import camelot
import logging
# Configuration logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# Load environment variables
load_dotenv()

# Load spaCy models once
NLP_FR = spacy.load("fr_core_news_sm")
NLP_EN = spacy.load("en_core_web_sm")



class EMADocumentType(Enum):
    """Types spécifiques aux documents EMA"""
    COMMISSION_IMPLEMENTING_REGULATION = "commission_implementing_regulation"
    COMMISSION_REGULATION = "commission_regulation"
    COMMISSION_DIRECTIVE = "commission_directive"
    GUIDELINE = "guideline"
    SCIENTIFIC_ADVICE = "scientific_advice"
    ASSESSMENT_REPORT = "assessment_report"
    PRODUCT_INFORMATION = "product_information"
    REGULATORY_PROCEDURE = "regulatory_procedure"
    QUALITY_GUIDELINE = "quality_guideline"
    PHARMACOVIGILANCE = "pharmacovigilance"
    CLINICAL_GUIDELINE = "clinical_guideline"
    OTHER = "other"


@dataclass
class DocumentStructure:
    """Represents the hierarchical structure of a document"""
    sections: List[Dict] = None
    tables: List[Dict] = None
    figures: List[Dict] = None
    annexes: List[Dict] = None
    glossary: Dict = None
    
    def __post_init__(self):
        if self.sections is None:
            self.sections = []
        if self.tables is None:
            self.tables = []
        if self.figures is None:
            self.figures = []
        if self.annexes is None:
            self.annexes = []
        if self.glossary is None:
            self.glossary = {}

@dataclass
class EMASpecificMetadata:
    """Métadonnées spécifiques aux documents EMA"""
    celex_number: str = ""
    oj_reference: str = ""  # Official Journal reference
    legal_act_type: str = ""
    adoption_date: str = ""
    entry_into_force: str = ""
    legal_basis: str = ""
    addressees: List[str] = None
    committee_opinion: str = ""
    procedure_type: str = ""
    regulatory_framework: str = ""
    
    def __post_init__(self):
        if self.addressees is None:
            self.addressees = []

@dataclass
class EMATableStructure:
    """Structure spécialisée pour les tableaux EMA"""
    table_id: str = ""
    title: str = ""
    page_number: int = 0
    position: int = 0
    table_type: str = ""  # regulatory, scientific, administrative
    headers: List[str] = None
    rows: List[List[str]] = None
    column_mappings: Dict[str, str] = None
    is_regulatory_table: bool = False
    contains_dates: bool = False
    contains_references: bool = False
    
    def __post_init__(self):
        if self.headers is None:
            self.headers = []
        if self.rows is None:
            self.rows = []
        if self.column_mappings is None:
            self.column_mappings = {}

@dataclass
class QualityMetrics:
    """Enhanced quality metrics for extraction"""
    extraction_rate: int = 0
    field_scores: Dict[str, int] = None
    structure_completeness: float = 0.0
    content_coherence: float = 0.0
    regulatory_compliance: float = 0.0
    extracted_fields: int = 0
    total_fields: int = 0
    llm_powered: bool = False
    extraction_reasoning: Dict[str, str] = None
    
    def __post_init__(self):
        if self.field_scores is None:
            self.field_scores = {}
        if self.extraction_reasoning is None:
            self.extraction_reasoning = {}

@dataclass
class DocumentMetadata:
    """Enhanced metadata structure for EMA extractor"""
    title: str = ""
    type: str = ""
    publication_date: str = ""
    version: str = ""
    source: str = ""
    context: str = ""
    country: str = ""
    language: str = ""
    url_source: str = ""

    # EMA-specific or regulatory extensions
    ich_step: str = ""  # For ICH if reused
    regulatory_pathway: str = ""
    therapeutic_area: str = ""
    keywords: List[str] = None
    references: List[str] = None
    supersedes: str = ""
    effective_date: str = ""

    # Structure and quality
    structure: DocumentStructure = None
    quality: QualityMetrics = None

    def __post_init__(self):
        self.keywords = self.keywords or []
        self.references = self.references or []
        self.structure = self.structure or DocumentStructure()
        self.quality = self.quality or QualityMetrics()
        

class PharmaDocumentAnalyzer:
    """Enhanced document analyzer with structure detection"""
    
    def __init__(self):
        self.patterns = self._initialize_patterns()
        self.stopwords = self._load_stopwords()
        
    def _initialize_ema_patterns(self) -> Dict:
        """Initialise les patterns spécifiques aux documents EMA"""
        return {
            'celex_number': r'CELEX[:\s]*(\d{4}[A-Z]{1,2}\d{4}(?:\(\d{2}\))?)',
            'oj_reference': r'OJ\s+[A-Z]\s+\d+,\s+\d+\.\d+\.\d+,\s+p\.\s+\d+',
            'commission_regulation': r'COMMISSION\s+(?:IMPLEMENTING\s+)?REGULATION\s+\((?:EU|EC)\)\s+No\s+(\d+/\d+)',
            'commission_directive': r'COMMISSION\s+DIRECTIVE\s+(\d+/\d+/(?:EU|EC))',
            'article_pattern': r'Article\s+(\d+(?:\.\d+)?)',
            'annex_pattern': r'ANNEX\s+([IVX]+|\d+)',
            'date_patterns': [
                r'(\d{1,2}\s+\w+\s+\d{4})',
                r'(\d{1,2}\.\d{1,2}\.\d{4})',
                r'(\d{4}-\d{2}-\d{2})'
            ],
            'legal_references': r'(?:Directive|Regulation|Decision)\s+(?:\d+/\d+/(?:EU|EC|EEC)|\((?:EU|EC)\)\s+No\s+\d+/\d+)',
            'pharmaceutical_terms': r'(?:medicinal product|marketing authorisation|pharmacovigilance|clinical trial|GMP|GCP)',
            'procedural_elements': r'(?:centralised procedure|mutual recognition|decentralised procedure|national procedure)'
        }   
    
    def _load_stopwords(self) -> set:
        """Load multilingual stopwords"""
        return {
            "le", "la", "les", "de", "des", "du", "un", "une", "et", "en", "à", "dans",
            "que", "qui", "pour", "par", "sur", "avec", "au", "aux", "ce", "ces",
            "the", "and", "of", "to", "in", "that", "it", "is", "was", "for", "on",
            "are", "with", "as", "i", "at", "be", "by", "this", "have", "from"
        }
    
    def extract_document_structure(self, text: str) -> DocumentStructure:
        """Extract hierarchical document structure"""
        structure = DocumentStructure()
        
        # Extract sections
        structure.sections = self._extract_sections(text)
        
        # Extract tables
        structure.tables = self._extract_table_references(text)
        
        # Extract figures
        structure.figures = self._extract_figure_references(text)
        
        # Extract annexes
        structure.annexes = self._extract_annex_references(text)
        
        # Extract glossary
        structure.glossary = self._extract_glossary(text)
        
        return structure
    
    def _extract_sections(self, text: str) -> List[Dict]:
        """Extract document sections with hierarchy"""
        sections = []
        lines = text.split('\n')
        
        for i, line in enumerate(lines):
            line = line.strip()
            
            # Match section headers
            match = re.match(self.patterns['section_header'], line)
            if match:
                section_num = match.group(1)
                section_title = match.group(2).strip()
                
                # Determine hierarchy level
                level = len(section_num.split('.'))
                
                # Extract content (next few lines until next section)
                content = self._extract_section_content(lines, i + 1)
                
                sections.append({
                    'number': section_num,
                    'title': section_title,
                    'level': level,
                    'content': content,
                    'line_number': i + 1
                })
        
        return sections
    
    def _extract_section_content(self, lines: List[str], start_idx: int) -> str:
        """Extract content between sections"""
        content = []
        for i in range(start_idx, len(lines)):
            line = lines[i].strip()
            
            # Stop at next section header
            if re.match(self.patterns['section_header'], line):
                break
            
            # Skip empty lines and page markers
            if line and not line.startswith('---'):
                content.append(line)
        
        return ' '.join(content)
    
    def _extract_table_references(self, text: str) -> List[Dict]:
        """Extract table references and metadata"""
        tables = []
        matches = re.finditer(self.patterns['table_title'], text, re.IGNORECASE)
        
        for match in matches:
            tables.append({
                'id': match.group(1),
                'title': match.group(2).strip(),
                'position': match.start()
            })
        
        return tables
    
    def _extract_figure_references(self, text: str) -> List[Dict]:
        """Extract figure references"""
        figures = []
        matches = re.finditer(self.patterns['figure_title'], text, re.IGNORECASE)
        
        for match in matches:
            figures.append({
                'id': match.group(1),
                'title': match.group(2).strip(),
                'position': match.start()
            })
        
        return figures
    
    def _extract_annex_references(self, text: str) -> List[Dict]:
        """Extract annex references"""
        annexes = []
        matches = re.finditer(self.patterns['annex_title'], text, re.IGNORECASE)
        
        for match in matches:
            annexes.append({
                'id': match.group(1),
                'title': match.group(2).strip(),
                'position': match.start()
            })
        
        return annexes
    
    def _extract_glossary(self, text: str) -> Dict:
        """Extract glossary terms and definitions"""
        glossary = {}
        
        # Look for glossary section
        glossary_match = re.search(r'GLOSSARY.*?(?=\n\n|\Z)', text, re.DOTALL | re.IGNORECASE)
        if not glossary_match:
            return glossary
        
        glossary_text = glossary_match.group()
        
        # Extract term definitions
        definition_pattern = r'([A-Z][^:\n]+):\s*([^A-Z]+?)(?=\n[A-Z][^:\n]+:|\Z)'
        matches = re.finditer(definition_pattern, glossary_text, re.DOTALL)
        
        for match in matches:
            term = match.group(1).strip()
            definition = match.group(2).strip()
            glossary[term] = definition
        
        return glossary
    
    def analyze_document_type(self, text: str, url: str = "") -> Tuple[EMADocumentType, float]:
        """Analyze document type with confidence"""
        type_indicators = {
            EMADocumentType.GUIDELINE: ['guideline', 'guidance', 'guide'],
            EMADocumentType.REGULATION: ['regulation', 'regulatory', 'rule'],
            EMADocumentType.DIRECTIVE: ['directive', 'direction'],
            EMADocumentType.REPORT: ['report', 'assessment', 'evaluation'],
            EMADocumentType.PROCEDURE: ['procedure', 'process', 'method'],
            EMADocumentType.STANDARD: ['standard', 'specification'],
            EMADocumentType.QUALITY_SYSTEM: ['quality system', 'QMS', 'pharmaceutical quality'],
            EMADocumentType.DEVELOPMENT: ['development', 'developmental', 'R&D']
        }
        
        text_lower = text.lower()
        url_lower = url.lower()
        
        scores = {}
        for doc_type, indicators in type_indicators.items():
            score = 0
            for indicator in indicators:
                # Count in text (weighted)
                score += text_lower.count(indicator) * 1
                # Count in URL (higher weight)
                score += url_lower.count(indicator) * 3
            scores[doc_type] = score
        
        # Find best match
        best_type = max(scores, key=scores.get)
        confidence = min(scores[best_type] / 10, 1.0)  # Normalize to 0-1
        
        return best_type, confidence
    
    def extract_keywords(self, text: str, max_keywords: int = 20) -> List[str]:
        """Extract relevant keywords using NLP"""
        try:
            # Detect language
            lang = detect(text)
            nlp = NLP_FR if lang == 'fr' else NLP_EN
            
            # Process text
            doc = nlp(text[:10000])  # Limit for performance
            
            # Extract keywords (nouns, proper nouns, adjectives)
            keywords = []
            for token in doc:
                if (token.pos_ in ['NOUN', 'PROPN', 'ADJ'] and 
                    len(token.text) > 3 and 
                    token.text.lower() not in self.stopwords and
                    token.is_alpha):
                    keywords.append(token.lemma_.lower())
            
            # Count frequency and return top keywords
            from collections import Counter
            keyword_freq = Counter(keywords)
            return [kw for kw, _ in keyword_freq.most_common(max_keywords)]
            
        except Exception as e:
            print(f"⚠️ Keyword extraction failed: {e}")
            return []

class EMADocumentExtractor:
    """Extracteur spécialisé pour les documents EMA"""
    
    def __init__(self):
        self.analyzer = PharmaDocumentAnalyzer()
        self.patterns = self._initialize_ema_patterns()
        self.regulatory_keywords = self._load_regulatory_keywords()
        
        # Charger les modèles spaCy
        try:
            self.nlp_en = spacy.load("en_core_web_sm")
        except:
            logger.warning("Modèle spaCy anglais non disponible")
            self.nlp_en = None
            
        try:
            self.nlp_fr = spacy.load("fr_core_news_sm")
        except:
            logger.warning("Modèle spaCy français non disponible")
            self.nlp_fr = None
    
    def _initialize_ema_patterns(self) -> Dict:
        """Initialise les patterns spécifiques aux documents EMA"""
        return {
            'celex_number': r'CELEX[:\s]*(\d{4}[A-Z]{1,2}\d{4}(?:\(\d{2}\))?)',
            'oj_reference': r'OJ\s+[A-Z]\s+\d+,\s+\d+\.\d+\.\d+,\s+p\.\s+\d+',
            'commission_regulation': r'COMMISSION\s+(?:IMPLEMENTING\s+)?REGULATION\s+\((?:EU|EC)\)\s+No\s+(\d+/\d+)',
            'commission_directive': r'COMMISSION\s+DIRECTIVE\s+(\d+/\d+/(?:EU|EC))',
            'article_pattern': r'Article\s+(\d+(?:\.\d+)?)',
            'annex_pattern': r'ANNEX\s+([IVX]+|\d+)',
            'date_patterns': [
                r'(\d{1,2}\s+\w+\s+\d{4})',
                r'(\d{1,2}\.\d{1,2}\.\d{4})',
                r'(\d{4}-\d{2}-\d{2})'
            ],
            'legal_references': r'(?:Directive|Regulation|Decision)\s+(?:\d+/\d+/(?:EU|EC|EEC)|\((?:EU|EC)\)\s+No\s+\d+/\d+)',
            'pharmaceutical_terms': r'(?:medicinal product|marketing authorisation|pharmacovigilance|clinical trial|GMP|GCP)',
            'procedural_elements': r'(?:centralised procedure|mutual recognition|decentralised procedure|national procedure)'
        }
    
    def _load_regulatory_keywords(self) -> Dict[str, List[str]]:
        """Charge les mots-clés réglementaires EMA"""
        return {
            'quality': ['GMP', 'quality system', 'pharmaceutical quality', 'manufacturing', 'batch'],
            'clinical': ['clinical trial', 'GCP', 'clinical study', 'efficacy', 'safety'],
            'regulatory': ['marketing authorisation', 'centralised procedure', 'mutual recognition', 'pharmacovigilance'],
            'legal': ['directive', 'regulation', 'implementing regulation', 'legal basis'],
            'dates': ['entry into force', 'adoption', 'publication', 'effective date'],
            'pharmaceutical': ['medicinal product', 'active substance', 'excipient', 'dosage form']
        }
    
    def extract_metadata_and_structure(self, file_path: str, source_url: str = "") -> 'DocumentMetadata':
        
        """
        Extraction principale des métadonnées et structure pour documents EMA
        """
        from utils.utils import DocumentMetadata, DocumentStructure, QualityMetrics
        
        logger.info(f"🔍 Début extraction EMA pour: {Path(file_path).name}")
        
        # Initialiser les métadonnées
        metadata = DocumentMetadata()
        metadata.url_source = source_url
        metadata.source = "EMA"
        metadata.structure = DocumentStructure()
        
        # Extraire le texte complet avec tableaux
        full_text = self._extract_full_text(file_path, metadata.structure)
 
        metadata = DocumentMetadata()
        metadata.url_source = source_url

               
        # Extract document structure
        metadata.structure = self.analyzer.extract_document_structure(full_text)
        
        # Analyze document type
        doc_type, type_confidence = self.analyzer.analyze_document_type(full_text, source_url)
        metadata.type = doc_type.value
        
        # Extract keywords
        metadata.keywords = self.analyzer.extract_keywords(full_text)
        
        # Try LLM extraction
        try:
            llm_result = self._call_mistral_enhanced(full_text, source_url, metadata.structure)
            if llm_result:
                metadata = self._merge_llm_results(metadata, llm_result)
        except Exception as e:
            print(f"⚠️ LLM extraction failed: {e}")
            metadata = self._fallback_extraction(metadata, full_text, file_path)
        
        # Calculate quality metrics
        metadata.quality = self._calculate_quality_metrics(metadata)
        
        return metadata

    
    
    def _extract_full_text(self, file_path: str, structure: 'DocumentStructure') -> str:
        """
        Extraction du texte complet avec traitement spécialisé des tableaux EMA
        """
        full_text = ""
        all_pages_blocks = []
        
        logger.info(f"📄 Traitement du PDF: {Path(file_path).name}")
        
        with pdfplumber.open(file_path) as pdf:
            total_pages = len(pdf.pages)
            logger.info(f"📊 Nombre total de pages: {total_pages}")
            
            for page_index, page in enumerate(pdf.pages):
                logger.info(f"🔄 Traitement page {page_index + 1}/{total_pages}")
                
                blocks = []
                table_blocks = []
                
                # Détection des tableaux avec PDFPlumber
                pdf_tables = page.find_tables()
                logger.info(f"📋 Page {page_index + 1}: {len(pdf_tables)} tableau(x) détecté(s)")
                
                table_bboxes = []
                for table_idx, table in enumerate(pdf_tables):
                    try:
                        data = table.extract()
                        if self._is_valid_ema_table(data):
                            # Créer une structure de tableau EMA
                            ema_table = self._create_ema_table_structure(
                                data, page_index + 1, table_idx + 1, table.bbox
                            )
                            
                            # Ajouter à la structure du document
                            structure.tables.append(ema_table.__dict__)
                            
                            # Formater pour le texte
                            table_text = self._format_ema_table_for_text(ema_table)
                            table_blocks.append({
                                "type": "table",
                                "top": table.bbox[1],
                                "content": table_text
                            })
                            
                            table_bboxes.append(table.bbox)
                            
                    except Exception as e:
                        logger.warning(f"⚠️ Erreur traitement tableau page {page_index + 1}, table {table_idx + 1}: {e}")
                
                # Extraction du texte hors tableaux
                words = [w for w in page.extract_words() 
                        if not any(self._is_inside_bbox(w, bbox) for bbox in table_bboxes)]
                
                paragraphs = self._group_words_into_paragraphs(words)
                for para in paragraphs:
                    blocks.append({"type": "text", "top": para["top"], "content": para["text"]})
                
                # Fusion et tri des blocs
                all_blocks = table_blocks + blocks
                all_blocks.sort(key=lambda b: b["top"])
                all_pages_blocks.append(all_blocks)
        
        # Détection et suppression des en-têtes/pieds de page
        header_common, footer_common = self._detect_common_headers_footers(all_pages_blocks)
        
        # Reconstruction du texte final
        for page_index, blocks in enumerate(all_pages_blocks):
            full_text += f"\n\n=== PAGE {page_index + 1} ===\n"
            
            for block in blocks:
                content = block["content"].strip()
                if content in header_common or content in footer_common:
                    continue
                
                if block["type"] == "table":
                    full_text += f"\n{content}\n"
                else:
                    full_text += f"{content}\n"
        
        logger.info(f"📝 Texte extrait: {len(full_text)} caractères")
        return full_text
    
    def _group_words_into_paragraphs(self, words: List[Dict]) -> List[Dict]:
        """
        Regroupe des mots extraits (via pdfplumber.extract_words)
        en paragraphes en se basant sur leur position verticale (top).
        
        Retourne une liste de dictionnaires :
        [{'top': position_moyenne, 'text': 'contenu du paragraphe'}, ...]
        """
        if not words:
            return []

        from collections import defaultdict

        # Grouper les mots par ligne verticale arrondie
        lines_by_top = defaultdict(list)
        for word in words:
            top_rounded = round(float(word["top"]))
            lines_by_top[top_rounded].append(word["text"])

        # Trier les lignes par position du haut vers le bas
        sorted_tops = sorted(lines_by_top.keys())

        paragraphs = []
        current_para = []
        current_top = None

        for top in sorted_tops:
            line_text = " ".join(lines_by_top[top])

            # Nouvelle ligne proche = même paragraphe
            if current_top is None or abs(top - current_top) <= 8:
                current_para.append((top, line_text))
            else:
                # Fin d’un paragraphe : le stocker
                if current_para:
                    para_text = " ".join([t[1] for t in current_para])
                    avg_top = sum(t[0] for t in current_para) / len(current_para)
                    paragraphs.append({"top": avg_top, "text": para_text.strip()})
                current_para = [(top, line_text)]

            current_top = top

        # Ajouter le dernier paragraphe
        if current_para:
            para_text = " ".join([t[1] for t in current_para])
            avg_top = sum(t[0] for t in current_para) / len(current_para)
            paragraphs.append({"top": avg_top, "text": para_text.strip()})

        return paragraphs

    def extract_keywords(self, text: str, max_keywords: int = 20) -> List[str]:
        """Extract relevant keywords using NLP"""
        try:
            # Detect language
            lang = detect(text)
            nlp = NLP_FR if lang == 'fr' else NLP_EN
            
            # Process text
            doc = nlp(text[:10000])  # Limit for performance
            
            # Extract keywords (nouns, proper nouns, adjectives)
            keywords = []
            for token in doc:
                if (token.pos_ in ['NOUN', 'PROPN', 'ADJ'] and 
                    len(token.text) > 3 and 
                    token.text.lower() not in self.stopwords and
                    token.is_alpha):
                    keywords.append(token.lemma_.lower())
            
            # Count frequency and return top keywords
            from collections import Counter
            keyword_freq = Counter(keywords)
            return [kw for kw, _ in keyword_freq.most_common(max_keywords)]
            
        except Exception as e:
            print(f"⚠️ Keyword extraction failed: {e}")
            return []
        
    def _is_valid_ema_table(self, data: List[List]) -> bool:
        """
        Validation spécifique pour les tableaux EMA
        """
        if not data or len(data) < 2:
            return False
        
        # Calculer le taux de remplissage
        total_cells = sum(len(row) for row in data)
        filled_cells = sum(1 for row in data for cell in row if cell and str(cell).strip())
        
        if total_cells == 0:
            return False
        
        fill_rate = filled_cells / total_cells
        
        # Critères spécifiques EMA
        # - Au moins 25% de cellules remplies
        # - Au moins 2 colonnes
        # - Pas de ligne complètement vide
        
        min_fill_rate = 0.25
        min_columns = 2
        
        if fill_rate < min_fill_rate:
            return False
        
        if len(data[0]) < min_columns:
            return False
        
        # Vérifier qu'il n'y a pas que des lignes vides
        non_empty_rows = sum(1 for row in data if any(cell and str(cell).strip() for cell in row))
        if non_empty_rows < 2:
            return False
        
        return True
    
    def _create_ema_table_structure(self, data: List[List], page_num: int, table_id: int, bbox: Tuple) -> EMATableStructure:
        """
        Crée une structure de tableau spécialisée EMA
        """
        table_structure = EMATableStructure()
        table_structure.table_id = f"ema_table_{page_num}_{table_id}"
        table_structure.page_number = page_num
        table_structure.position = int(bbox[1])
        
        # Nettoyer les données
        clean_data = []
        for row in data:
            clean_row = [str(cell).strip() if cell else "" for cell in row]
            clean_data.append(clean_row)
        
        # Identifier les en-têtes
        if clean_data:
            potential_headers = clean_data[0]
            # Vérifier si la première ligne semble être un en-tête
            if self._is_header_row(potential_headers):
                table_structure.headers = potential_headers
                table_structure.rows = clean_data[1:]
            else:
                # Créer des en-têtes génériques
                table_structure.headers = [f"Column_{i+1}" for i in range(len(clean_data[0]))]
                table_structure.rows = clean_data
        
        # Classification du type de tableau
        table_structure.table_type = self._classify_table_type(table_structure)
        
        # Détection de contenu spécifique
        table_structure.contains_dates = self._contains_dates(table_structure)
        table_structure.contains_references = self._contains_references(table_structure)
        table_structure.is_regulatory_table = self._is_regulatory_table(table_structure)
        
        # Extraction du titre si possible
        table_structure.title = self._extract_table_title(table_structure)
        
        return table_structure
    
    def _is_header_row(self, row: List[str]) -> bool:
        """
        Détermine si une ligne est un en-tête
        """
        if not row:
            return False
        
        # Critères pour identifier un en-tête
        non_empty_cells = [cell for cell in row if cell]
        if len(non_empty_cells) == 0:
            return False
        
        # Vérifier la longueur moyenne des cellules
        avg_length = sum(len(cell) for cell in non_empty_cells) / len(non_empty_cells)
        
        # Vérifier la présence de mots-clés typiques d'en-têtes
        header_keywords = {
            'date', 'name', 'type', 'number', 'reference', 'description', 
            'article', 'section', 'title', 'status', 'country', 'regulation',
            'directive', 'procedure', 'medicinal', 'product', 'substance'
        }
        
        text_combined = " ".join(row).lower()
        has_header_keywords = any(keyword in text_combined for keyword in header_keywords)
        
        # Un en-tête a généralement:
        # - Des cellules de longueur modérée (10-50 caractères)
        # - Des mots-clés d'en-tête
        # - Pas de dates spécifiques
        
        return (5 <= avg_length <= 50) and (has_header_keywords or len(non_empty_cells) >= 2)
    
    def _classify_table_type(self, table: EMATableStructure) -> str:
        """
        Classifie le type de tableau EMA
        """
        headers_text = " ".join(table.headers).lower()
        rows_text = " ".join([" ".join(row) for row in table.rows]).lower()
        combined_text = headers_text + " " + rows_text
        
        # Patterns de classification
        if any(keyword in combined_text for keyword in ['regulation', 'directive', 'legal', 'article']):
            return "regulatory"
        elif any(keyword in combined_text for keyword in ['clinical', 'study', 'trial', 'efficacy']):
            return "clinical"
        elif any(keyword in combined_text for keyword in ['quality', 'manufacturing', 'gmp']):
            return "quality"
        elif any(keyword in combined_text for keyword in ['procedure', 'timeline', 'step']):
            return "procedural"
        elif any(keyword in combined_text for keyword in ['country', 'member state', 'national']):
            return "administrative"
        else:
            return "general"
    
    def _contains_dates(self, table: EMATableStructure) -> bool:
        """
        Détecte si le tableau contient des dates
        """
        date_patterns = [
            r'\d{1,2}\.\d{1,2}\.\d{4}',
            r'\d{1,2}/\d{1,2}/\d{4}',
            r'\d{4}-\d{2}-\d{2}',
            r'\d{1,2}\s+\w+\s+\d{4}'
        ]
        
        all_text = " ".join(table.headers + [" ".join(row) for row in table.rows])
        
        for pattern in date_patterns:
            if re.search(pattern, all_text):
                return True
        
        return False
    
    def _contains_references(self, table: EMATableStructure) -> bool:
        """
        Détecte si le tableau contient des références réglementaires
        """
        ref_patterns = [
            r'(?:Directive|Regulation|Decision)\s+\d+/\d+',
            r'CELEX:\d{4}[A-Z]{1,2}\d{4}',
            r'OJ\s+[A-Z]\s+\d+',
            r'Article\s+\d+',
            r'Annex\s+[IVX]+',
            r'ICH\s+[A-Z]\d+'
        ]
        
        all_text = " ".join(table.headers + [" ".join(row) for row in table.rows])
        
        for pattern in ref_patterns:
            if re.search(pattern, all_text, re.IGNORECASE):
                return True
        
        return False
    
    def _is_regulatory_table(self, table: EMATableStructure) -> bool:
        """
        Détermine si le tableau est de nature réglementaire
        """
        regulatory_indicators = [
            'regulation', 'directive', 'legal basis', 'article', 'annex',
            'implementing', 'commission', 'member state', 'compliance',
            'authorization', 'procedure', 'regulatory'
        ]
        
        all_text = " ".join(table.headers + [" ".join(row) for row in table.rows]).lower()
        
        regulatory_count = sum(1 for indicator in regulatory_indicators if indicator in all_text)
        
        return regulatory_count >= 2
    
    def _extract_table_title(self, table: EMATableStructure) -> str:
        """
        Extrait le titre du tableau si possible
        """
        # Le titre peut être déduit des en-têtes ou du contenu
        if table.headers:
            # Si les en-têtes sont descriptifs, les utiliser comme titre
            meaningful_headers = [h for h in table.headers if len(h) > 5]
            if meaningful_headers:
                return " - ".join(meaningful_headers[:3])
        
        # Titre générique basé sur le type
        type_titles = {
            "regulatory": "Tableau Réglementaire",
            "clinical": "Données Cliniques",
            "quality": "Informations Qualité",
            "procedural": "Procédures",
            "administrative": "Informations Administratives",
            "general": "Tableau"
        }
        
        return type_titles.get(table.table_type, "Tableau")
    
    def _format_ema_table_for_text(self, table: EMATableStructure) -> str:
        """
        Formate un tableau EMA pour l'insertion dans le texte
        """
        result = f"\n🔷 {table.title} (Page {table.page_number})\n"
        result += f"📋 Type: {table.table_type.upper()}\n"
        
        if table.is_regulatory_table:
            result += "⚖️ Tableau réglementaire\n"
        
        if table.contains_dates:
            result += "📅 Contient des dates\n"
        
        if table.contains_references:
            result += "📖 Contient des références\n"
        
        result += "=" * 60 + "\n"
        
        # Formater le tableau avec pandas/tabulate
        try:
            if table.headers and table.rows:
                df = pd.DataFrame(table.rows, columns=table.headers)
                
                # Nettoyer les données
                df = df.fillna("")
                
                # Supprimer les colonnes vides
                df = df.loc[:, (df != "").any(axis=0)]
                
                # Limiter la largeur des colonnes pour l'affichage
                for col in df.columns:
                    df[col] = df[col].astype(str).str[:100]
                
                # Générer le tableau formaté
                table_formatted = tabulate(df, headers='keys', tablefmt='grid', showindex=False)
                result += table_formatted
                
            else:
                result += "⚠️ Tableau sans structure claire\n"
                for i, row in enumerate(table.rows):
                    result += f"Ligne {i+1}: {' | '.join(row)}\n"
                    
        except Exception as e:
            logger.warning(f"⚠️ Erreur formatage tableau {table.table_id}: {e}")
            result += "⚠️ Erreur de formatage du tableau\n"
        
        result += "\n" + "=" * 60 + "\n"
        
        return result
    
    def _extract_ema_specific_metadata(self, text: str, url: str) -> EMASpecificMetadata:
        """
        Extrait les métadonnées spécifiques aux documents EMA
        """
        ema_metadata = EMASpecificMetadata()
        
        # Extraction du numéro CELEX
        celex_match = re.search(self.patterns['celex_number'], text)
        if celex_match:
            ema_metadata.celex_number = celex_match.group(1)
        elif 'CELEX:' in url:
            # Extraire depuis l'URL
            url_celex = re.search(r'CELEX:(\d{4}[A-Z]{1,2}\d{4}(?:\(\d{2}\))?)', url)
            if url_celex:
                ema_metadata.celex_number = url_celex.group(1)
        
        # Extraction de la référence Official Journal
        oj_match = re.search(self.patterns['oj_reference'], text)
        if oj_match:
            ema_metadata.oj_reference = oj_match.group(0)
        
        # Type d'acte légal
        if re.search(self.patterns['commission_regulation'], text):
            ema_metadata.legal_act_type = "Commission Regulation"
        elif re.search(self.patterns['commission_directive'], text):
            ema_metadata.legal_act_type = "Commission Directive"
        elif "GUIDELINE" in text.upper():
            ema_metadata.legal_act_type = "Guideline"
        
        # Dates importantes
        for date_pattern in self.patterns['date_patterns']:
            matches = re.findall(date_pattern, text)
            if matches:
                # Logique pour différencier les types de dates
                if "adoption" in text.lower():
                    ema_metadata.adoption_date = matches[0]
                elif "entry into force" in text.lower():
                    ema_metadata.entry_into_force = matches[0]
        
        # Base légale
        legal_basis_match = re.search(r'Having regard to ([^,]+)', text)
        if legal_basis_match:
            ema_metadata.legal_basis = legal_basis_match.group(1)
        
        # Destinataires
        addressee_patterns = [
            r'addressed to the Member States',
            r'addressed to ([^.]+)',
            r'This (?:Regulation|Directive) shall be binding.*?([^.]+)'
        ]
        
        for pattern in addressee_patterns:
            match = re.search(pattern, text)
            if match:
                ema_metadata.addressees.append(match.group(1) if match.lastindex else "Member States")
        
        return ema_metadata
    
    def _extract_basic_metadata(self, metadata: 'DocumentMetadata', text: str, file_path: str) -> 'DocumentMetadata':
        """
        Extrait les métadonnées de base
        """
        # Titre du document
        title_patterns = [
            r'COMMISSION\s+(?:IMPLEMENTING\s+)?REGULATION\s+\([^)]+\)\s+No\s+[^\n]+',
            r'COMMISSION\s+DIRECTIVE\s+[^\n]+',
            r'GUIDELINE\s+[^\n]+',
            r'^([A-Z][^.]+)(?:\.|$)'
        ]
        
        for pattern in title_patterns:
            match = re.search(pattern, text, re.MULTILINE)
            if match:
                metadata.title = match.group(0).strip()
                break
        
        # Si pas de titre trouvé, utiliser le nom du fichier
        if not metadata.title:
            metadata.title = Path(file_path).stem
        
        # Version/numéro
        version_match = re.search(r'(?:No|Version)\s+(\d+/\d+|\d+\.\d+)', text)
        if version_match:
            metadata.version = version_match.group(1)
        
        # Date de publication
        pub_date_patterns = [
            r'(\d{1,2}\.\d{1,2}\.\d{4})',
            r'(\d{1,2}\s+\w+\s+\d{4})',
            r'(\d{4}-\d{2}-\d{2})'
        ]
        
        for pattern in pub_date_patterns:
            match = re.search(pattern, text)
            if match:
                metadata.publication_date = match.group(1)
                break
        
        # Contexte
        metadata.context = "pharmaceutical"
        metadata.country = "EU"
        
        return metadata
    
    def _classify_ema_document_type(self, text: str, url: str) -> str:
        """
        Classifie le type de document EMA
        """
        text_lower = text.lower()
        url_lower = url.lower()
        
        # Patterns spécifiques EMA
        if re.search(r'commission\s+implementing\s+regulation', text_lower):
            return "commission_implementing_regulation"
        elif re.search(r'commission\s+regulation', text_lower):
            return "commission_regulation"
        elif re.search(r'commission\s+directive', text_lower):
            return "commission_directive"
        elif 'guideline' in text_lower:
            return "guideline"
        elif 'assessment report' in text_lower:
            return "assessment_report"
        elif 'scientific advice' in text_lower:
            return "scientific_advice"
        elif 'pharmacovigilance' in text_lower:
            return "pharmacovigilance"
        elif 'clinical' in text_lower and 'guideline' in text_lower:
            return "clinical_guideline"
        elif 'quality' in text_lower and 'guideline' in text_lower:
            return "quality_guideline"
        elif 'procedure' in text_lower:
            return "regulatory_procedure"
        elif 'product information' in text_lower:
            return "product_information"
        else:
            return "other"
    
    def _extract_enhanced_structure(self, text: str, structure: 'DocumentStructure') -> 'DocumentStructure':
        """
        Extrait la structure améliorée du document
        """
        # Extraction des articles
        articles = []
        article_matches = re.finditer(r'Article\s+(\d+)', text, re.IGNORECASE)
        for match in article_matches:
            articles.append({
                'number': match.group(1),
                'title': f"Article {match.group(1)}",
                'position': match.start()
            })
        
        # Extraction des annexes
        annexes = []
        annex_matches = re.finditer(r'ANNEX\s+([IVX]+|\d+)', text, re.IGNORECASE)
        for match in annexes:
            annexes.append({
                'id': match.group(1),
                'title': f"Annex {match.group(1)}",
                'position': match.start()
            })
        
        # Mise à jour de la structure
        structure.sections.extend(articles)
        structure.annexes.extend(annexes)
        
        return structure
    
    def _is_inside_bbox(self, word: Dict, bbox: Tuple[float, float, float, float]) -> bool:
        """
        Vérifie si un mot est à l'intérieur d'une boîte englobante (bbox)
        fournie par un tableau PDFPlumber.

        `word` est un dictionnaire contenant les positions 'x0', 'x1', 'top', 'bottom'
        `bbox` est une tuple (x0, top, x1, bottom)
        """
        x0, top, x1, bottom = bbox
        return (
            float(word["x0"]) >= x0 and
            float(word["x1"]) <= x1 and
            float(word["top"]) >= top and
            float(word["bottom"]) <= bottom
        )
    def _detect_and_remove_headers_footers(self, all_pages_blocks: List[List[Dict]]) -> List[List[Dict]]:
        """
        Supprime dynamiquement les en-têtes/pieds de page en détectant les textes répétitifs
        dans les mêmes zones verticales (haut/bas) sur plusieurs pages.
        """
        from collections import defaultdict, Counter

        header_candidates = defaultdict(list)
        footer_candidates = defaultdict(list)

        for page_blocks in all_pages_blocks:
            for block in page_blocks:
                content = block["content"].strip()
                top = block["top"]

                if top < 100:  # en-tête probable
                    header_candidates[content].append(top)
                elif top > 700:  # bas de page probable (selon hauteur moyenne)
                    footer_candidates[content].append(top)

        # Texte vu sur au moins 70% des pages = probable header/footer
        total_pages = len(all_pages_blocks)
        header_freq = {k for k, v in header_candidates.items() if len(v) >= total_pages * 0.7}
        footer_freq = {k for k, v in footer_candidates.items() if len(v) >= total_pages * 0.7}

        # Supprimer ces blocs
        cleaned_pages = []
        for blocks in all_pages_blocks:
            cleaned = []
            for block in blocks:
                text = block["content"].strip()
                if text in header_freq or text in footer_freq:
                    continue
                cleaned.append(block)
            cleaned_pages.append(cleaned)

        return cleaned_pages

    def _detect_common_headers_footers(self, all_pages_blocks: List[List[Dict]]) -> Tuple[set, set]:
        """
        Détecte les en-têtes et pieds de page répétitifs (haut/bas) sur la majorité des pages.
        """
        from collections import defaultdict

        header_texts = defaultdict(int)
        footer_texts = defaultdict(int)
        total_pages = len(all_pages_blocks)

        for blocks in all_pages_blocks:
            for block in blocks:
                text = block["content"].strip()
                top = block["top"]

                if top < 100:
                    header_texts[text] += 1
                elif top > 700:
                    footer_texts[text] += 1

        header_common = {txt for txt, count in header_texts.items() if count >= total_pages * 0.7}
        footer_common = {txt for txt, count in footer_texts.items() if count >= total_pages * 0.7}
        return header_common, footer_common
 