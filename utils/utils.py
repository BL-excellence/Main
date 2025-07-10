import os
import re
import json
import requests
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum

import spacy
from PyPDF2 import PdfReader
from langdetect import detect
from dotenv import load_dotenv
import difflib
import pdfplumber
from collections import defaultdict
import camelot
import logging
from utils.ema_document_extractor import EMADocumentExtractor


# Load environment variables
load_dotenv()

# Load spaCy models once
NLP_FR = spacy.load("fr_core_news_sm")
NLP_EN = spacy.load("en_core_web_sm")

class DocumentType(Enum):
    GUIDELINE = "guideline"
    REGULATION = "regulation"
    DIRECTIVE = "directive"
    REPORT = "report"
    PROCEDURE = "procedure"
    STANDARD = "standard"
    QUALITY_SYSTEM = "quality_system"
    DEVELOPMENT = "development"
    OTHER = "other"

class DocumentSource(Enum):
    ICH = "ICH"
    EMA = "EMA"
    FDA = "FDA"
    WHO = "WHO"
    ISO = "ISO"
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
    """Enhanced metadata structure"""
    title: str = ""
    type: str = ""
    publication_date: str = ""
    version: str = ""
    source: str = ""
    context: str = ""
    country: str = ""
    language: str = ""
    url_source: str = ""
    
    # Enhanced fields
    ich_step: str = ""  # For ICH documents
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
        if self.keywords is None:
            self.keywords = []
        if self.references is None:
            self.references = []
        if self.structure is None:
            self.structure = DocumentStructure()
        if self.quality is None:
            self.quality = QualityMetrics()

class PharmaDocumentAnalyzer:
    """Enhanced document analyzer with structure detection"""
    
    def __init__(self):
        self.patterns = self._initialize_patterns()
        self.stopwords = self._load_stopwords()
        
    def _initialize_patterns(self) -> Dict:
        """Initialize regex patterns for different document elements"""
        return {
            'ich_reference': r'ICH\s+[A-Z]\d+(?:\([A-Z]\d+\))?',
            'section_header': r'^\s*(\d+\.?\d*\.?\d*)\s+([A-Z][^.]+)',
            'table_title': r'Table\s+(\d+|[IVX]+)[:\s]+(.*)',
            'figure_title': r'Figure\s+(\d+|[IVX]+)[:\s]+(.*)',
            'annex_title': r'Annex\s+(\d+|[IVX]+)[:\s]+(.*)',
            'date_patterns': [
                r'(\d{1,2}\s+\w+\s+\d{4})',
                r'(\w+\s+\d{1,2},?\s+\d{4})',
                r'(\d{4}-\d{2}-\d{2})',
                r'(\d{1,2}/\d{1,2}/\d{4})'
            ],
            'version_patterns': [
                r'Version\s+(\d+\.?\d*)',
                r'Step\s+(\d+)',
                r'Revision\s+(\d+)',
                r'Draft\s+(\d+)'
            ]
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
    
    def analyze_document_type(self, text: str, url: str = "") -> Tuple[DocumentType, float]:
        """Analyze document type with confidence"""
        type_indicators = {
            DocumentType.GUIDELINE: ['guideline', 'guidance', 'guide'],
            DocumentType.REGULATION: ['regulation', 'regulatory', 'rule'],
            DocumentType.DIRECTIVE: ['directive', 'direction'],
            DocumentType.REPORT: ['report', 'assessment', 'evaluation'],
            DocumentType.PROCEDURE: ['procedure', 'process', 'method'],
            DocumentType.STANDARD: ['standard', 'specification'],
            DocumentType.QUALITY_SYSTEM: ['quality system', 'QMS', 'pharmaceutical quality'],
            DocumentType.DEVELOPMENT: ['development', 'developmental', 'R&D']
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
        
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
    
class EnhancedDocumentExtractor:
    """Main extractor with enhanced capabilities"""
    
    def __init__(self):
        self.analyzer = PharmaDocumentAnalyzer()
        self.api_key = os.getenv("MISTRAL_API_KEY")
    
    def extract_enhanced_metadata(self, file_path: str, source_url: str = "") -> DocumentMetadata:
        """Extract comprehensive metadata with structure analysis"""

        if "EMA" in source_url or "eur-lex.europa.eu" in source_url:
            logger.info("🧭 Redirection vers EMA handler basée sur source = EMA")
            from utils.ema_document_extractor import EMADocumentExtractor
            ema_extractor = EMADocumentExtractor()
            ema_meta = ema_extractor.extract_metadata_and_structure(file_path, source_url)
            return ema_meta
 
        metadata = DocumentMetadata()
        metadata.url_source = source_url

        # Extraire texte et remplir les tableaux dans structure
        full_text = self.extract_full_text(file_path, structure=metadata.structure)
        
        # Initialize metadata
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
    

    def extract_full_text(self, file_path: str, structure: Optional[DocumentStructure] = None) -> str:
        """
        Extraction du texte brut et des tableaux structurés.
        Remplit aussi structure.tables si un objet structure est fourni.
        """
        full_text = ""
        all_pages_blocks = []

        with pdfplumber.open(file_path) as pdf:
            for page_index, page in enumerate(pdf.pages):
                blocks = []
                table_text_blocks = []

                # Camelot log/debug uniquement
                try:
                    camelot_tables = camelot.read_pdf(file_path, pages=str(page_index + 1), flavor='lattice')
                    if camelot_tables.n == 0:
                        camelot_tables = camelot.read_pdf(file_path, pages=str(page_index + 1), flavor='stream')
                    logger.info(f"[Camelot] Page {page_index + 1} - {camelot_tables.n} table(s) detected")
                except Exception as e:
                    logger.warning(f"[Camelot] Error on page {page_index + 1}: {e}")

                # PDFPlumber pour extraction
                pdf_tables = page.find_tables()
                logger.info(f"[PDFPlumber] Page {page_index + 1} - {len(pdf_tables)} table(s) detected")

                table_bboxes = []
                for idx, table in enumerate(pdf_tables):
                    data = table.extract()
                    if self._is_valid_table(data):
                        structured_table = self._extract_table_as_structured(data, page_index + 1, idx + 1)

                        # ➕ Enrichir structure si fourni
                        if structure is not None and structured_table:
                            structure.tables.append(structured_table)

                        from tabulate import tabulate
                        import pandas as pd

                        if "columns" in structured_table and structured_table["columns"]:
                            df = pd.DataFrame(structured_table["rows"], columns=structured_table["columns"])
                            use_headers = True
                        else:
                            df = pd.DataFrame(structured_table["rows"])
                            use_headers = False

                        # df = pd.DataFrame(structured_table["rows"], columns=structured_table["columns"])

                        # 🔥 Supprimer première colonne si elle est inutile (ex : contient uniquement 0, 1, vide)
                        def is_useless(col):
                            values = col.dropna().astype(str).str.strip()
                            return values.isin(["", "0", "1"]).all()

                        if not df.empty:
                            first_col = df.columns[0]
                            col = df.iloc[:, 0]  # Première colonne en tant que Series
                            if is_useless(col):                            
                                df = df.drop(columns=[first_col])

                        
                        # 🔥 Nettoyage lignes vides
                        df = df.dropna(how="all")
                        df.reset_index(drop=True, inplace=True)

                        # Génération du tableau propre
                        table_str = f"\n TABLEAU {idx + 1} (Page {page_index + 1})\n"
                        # table_str += tabulate(df, headers="keys", tablefmt="grid", showindex=False)
                        if use_headers:
                            table_str += tabulate(df, headers="keys", tablefmt="grid", showindex=False)
                        else:
                            table_str += tabulate(df.values.tolist(), tablefmt="grid", showindex=False)


                        table_text_blocks.append({
                            "type": "table",
                            "top": table.bbox[1],
                            "content": table_str
                        })


                        table_bboxes.append(table.bbox)

                # Extraction de texte hors tableaux
                words = [w for w in page.extract_words() if not any(self._is_inside_bbox(w, bbox) for bbox in table_bboxes)]
                paragraphs = self._group_into_paragraphs(words)
                for para in paragraphs:
                    blocks.append({"type": "text", "top": para["top"], "content": para["text"]})

                # Fusion et tri
                all_blocks = table_text_blocks + blocks
                all_blocks.sort(key=lambda b: b["top"])
                all_pages_blocks.append(all_blocks)

        # Détection headers/footers
        header_common, footer_common = self._detect_common_headers_footers(all_pages_blocks)

        # Reconstruction finale du texte
        for page_index, blocks in enumerate(all_pages_blocks):
            full_text += f"\n\n--- Page {page_index + 1} ---\n"
            for block in blocks:
                text = block["content"].strip()
                if text in header_common or text in footer_common:
                    continue
                full_text += text + "\n"

        return full_text

    
    def _call_mistral_enhanced(self, text: str, url: str, structure: DocumentStructure) -> Optional[Dict]:
        """Enhanced LLM call with structure context"""
        if not self.api_key:
            return None
        
        # Create enhanced prompt with structure context
        prompt = self._create_enhanced_prompt(text, url, structure)
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        
        data = {
            "model": "mistral-large-latest",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": 1500
        }
        
        try:
            response = requests.post(
                "https://api.mistral.ai/v1/chat/completions",
                headers=headers,
                json=data,
                timeout=30
            )
            response.raise_for_status()
            
            content = response.json()['choices'][0]['message']['content']
            match = re.search(r'\{.*\}', content, re.DOTALL)
            if match:
                return json.loads(match.group())
        except Exception as e:
            print(f"❌ LLM API error: {e}")
        
        return None
    
    def _create_enhanced_prompt(self, text: str, url: str, structure: DocumentStructure) -> str:
        """Create enhanced prompt with structure information"""
        
        structure_info = f"""
        Document has {len(structure.sections)} sections, {len(structure.tables)} tables, 
        {len(structure.figures)} figures, {len(structure.annexes)} annexes.
        Main sections: {[s['title'] for s in structure.sections[:5]]}
        """
        
        return f"""
        You are an expert pharmaceutical document analyzer. Extract comprehensive metadata from this regulatory document.

        DOCUMENT STRUCTURE:
        {structure_info}

        DOCUMENT TEXT (first 3000 chars):
        {text[:3000]}

        SOURCE URL: {url}

        Return ONLY a JSON object with complete metadata and confidence scores:

        {{
            "metadata": {{
                "title": "exact document title",
                "type": "guideline|regulation|directive|report|procedure|standard|quality_system|development|other",
                "publication_date": "exact date (DD Month YYYY)",
                "version": "version/step/revision number",
                "source": "ICH|EMA|FDA|WHO|ISO|other",
                "context": "pharmaceutical|medical|regulatory|quality|development",
                "country": "country/region code",
                "language": "language code",
                "ich_step": "ICH step if applicable",
                "regulatory_pathway": "regulatory pathway",
                "therapeutic_area": "therapeutic area if applicable",
                "supersedes": "document this supersedes",
                "effective_date": "effective date if different from publication"
            }},
            "confidence_scores": {{
                "title": 0-100,
                "type": 0-100,
                "publication_date": 0-100,
                "version": 0-100,
                "source": 0-100,
                "context": 0-100,
                "country": 0-100,
                "language": 0-100,
                "ich_step": 0-100,
                "regulatory_pathway": 0-100,
                "therapeutic_area": 0-100,
                "supersedes": 0-100,
                "effective_date": 0-100
            }},
            "extraction_reasoning": {{
                "title": "reasoning for title extraction",
                "type": "reasoning for type classification",
                "source": "reasoning for source identification",
                "version": "reasoning for version identification"
            }}
        }}

        INSTRUCTIONS:
        - Be precise and honest with confidence scores
        - Use document structure context to improve extraction
        - For ICH documents, identify the step (1-5) and specific guideline
        - Extract regulatory pathway (CTD, quality by design, etc.)
        - Identify therapeutic area if mentioned
        - Return ONLY the JSON, no other text
        """
    
    def _merge_llm_results(self, metadata: DocumentMetadata, llm_result: Dict) -> DocumentMetadata:
        """Merge LLM results with existing metadata"""
        if 'metadata' in llm_result:
            llm_metadata = llm_result['metadata']
            
            # Update metadata fields
            for key, value in llm_metadata.items():
                if hasattr(metadata, key) and value:
                    setattr(metadata, key, value)
        
        # Update quality metrics
        if 'confidence_scores' in llm_result:
            metadata.quality.field_scores = llm_result['confidence_scores']
            metadata.quality.llm_powered = True
        
        if 'extraction_reasoning' in llm_result:
            metadata.quality.extraction_reasoning = llm_result['extraction_reasoning']
        
        return metadata
    
    def _calculate_quality_metrics(self, metadata: DocumentMetadata) -> QualityMetrics:
        """Calculate comprehensive quality metrics"""
        quality = metadata.quality
        
        # Calculate extraction rate
        if quality.field_scores:
            total_score = sum(quality.field_scores.values())
            field_count = len(quality.field_scores)
            quality.extraction_rate = int(total_score / field_count) if field_count > 0 else 0
            quality.extracted_fields = sum(1 for score in quality.field_scores.values() if score >= 50)
            quality.total_fields = field_count
        
        # Calculate structure completeness
        structure = metadata.structure
        structure_score = 0
        if structure.sections:
            structure_score += 25
        if structure.tables:
            structure_score += 25
        if structure.glossary:
            structure_score += 25
        if structure.annexes:
            structure_score += 25
        
        quality.structure_completeness = structure_score / 100
        
        # Calculate content coherence (based on extracted elements)
        coherence_score = 0
        if metadata.title:
            coherence_score += 20
        if metadata.type:
            coherence_score += 20
        if metadata.source:
            coherence_score += 20
        if metadata.keywords:
            coherence_score += 20
        if metadata.publication_date:
            coherence_score += 20
        
        quality.content_coherence = coherence_score / 100
        
        # Calculate regulatory compliance (based on document type and structure)
        compliance_score = 0
        if metadata.type in ['guideline', 'regulation', 'directive']:
            compliance_score += 30
        if metadata.source in ['ICH', 'EMA', 'FDA']:
            compliance_score += 30
        if structure.sections:
            compliance_score += 20
        if structure.glossary:
            compliance_score += 20
        
        quality.regulatory_compliance = compliance_score / 100
        
        return quality
    
    def _fallback_extraction(self, metadata: DocumentMetadata, text: str, file_path: str) -> DocumentMetadata:
        """Enhanced fallback extraction"""
        # Basic PDF metadata
        try:
            reader = PdfReader(file_path)
            info = reader.metadata or {}
            if not metadata.title and info.title:
                metadata.title = info.title
        except:
            pass
        
        # If no title, use filename
        if not metadata.title:
            metadata.title = Path(file_path).stem
        
        # Detect language
        try:
            metadata.language = detect(text)
        except:
            metadata.language = "en"
        
        # Set basic confidence scores
        metadata.quality.field_scores = {
            'title': 30 if metadata.title else 0,
            'language': 80 if metadata.language else 0,
            'type': 0,
            'source': 0,
            'publication_date': 0
        }
        
        metadata.quality.llm_powered = False
        
        return metadata
    
    def _extract_table_as_structured(self, data: List[List], page_num: int, table_id: int) -> Optional[Dict]:
        """
        Retourne une table au format structuré (colonnes + lignes) pour JSON/export.
        """
        if not data or not any(any(cell for cell in row) for row in data):
            return None

        # Déterminer les en-têtes
        headers = [cell.strip() if cell else "" for cell in data[0]]


        rows = data[1:]

        structured_rows = []
        for row in rows:
            clean_row = [cell.strip() if cell else "" for cell in row]
            # Compléter avec des cellules vides si nécessaire
            while len(clean_row) < len(headers):
                clean_row.append("")
            structured_rows.append(clean_row)

        return {
            "page": page_num,
            "table_id": f"table_{page_num}_{table_id}",
            "columns": headers,
            "rows": structured_rows
        }

    def _is_valid_table(self, data: List[List]) -> bool:
        """Check if table data is valid (tolérance élevée pour ne rien rater)"""
        if not data:
            return False

        if len(data) < 2:
            # S'il y a une seule ligne, elle doit avoir plusieurs cellules remplies
            filled_cells = sum(1 for cell in data[0] if cell and cell.strip())
            return filled_cells >= 2  # une ligne ok si au moins 2 colonnes ont du contenu

        # Cas classique (2+ lignes) → 20% de cellules remplies suffit
        total_cells = sum(len(row) for row in data)
        filled_cells = sum(1 for row in data for cell in row if cell and cell.strip())

        logger.debug(f"🚫 Table rejetée : {len(data)} lignes, {filled_cells}/{total_cells} cellules remplies")

        return filled_cells / total_cells >= 0.2 if total_cells > 0 else False


    def _format_table_enhanced(self, data: List[List], table_id: int, page_num: int) -> str:
        """Enhanced table formatting — affiche même sans en-tête"""
        if not data or not any(any(cell for cell in row) for row in data):
            return f"\n📊 TABLEAU {table_id} (Page {page_num})\n⚠️ Tableau vide ou illisible\n"

        result = f"\n📊 TABLEAU {table_id} (Page {page_num})\n"

        # Si une seule ligne : on considère que ce n’est pas un header mais une entrée
        if len(data) == 1:
            row = data[0]
            result += f"\n🔸 ENTRÉE 1\n" + "-" * 30 + "\n"
            for j, cell in enumerate(row):
                result += f"▪ col_{j+1}:\n  {cell.strip() if cell else ''}\n"
            return result

        # S'il n'y a pas de "vrai" en-tête (trop vide ou trop verbeux), on utilise col_1, col_2...
        first_row = data[0]
        header_is_empty = all(not cell or not cell.strip() for cell in first_row)
        header_is_long_text = any(len(cell.strip()) > 100 for cell in first_row if cell)

        if header_is_empty or header_is_long_text:
            headers = [f"col_{j+1}" for j in range(len(first_row))]
            start_idx = 0
        else:
            headers = [cell.strip() if cell else f"col_{j+1}" for j, cell in enumerate(first_row)]
            start_idx = 1

        for i, row in enumerate(data[start_idx:], 1):
            result += f"\n🔸 ENTRÉE {i}\n" + "-" * 30 + "\n"
            for j, cell in enumerate(row):
                if j < len(headers):
                    result += f"▪ {headers[j]}:\n  {cell.strip() if cell else ''}\n"

        return result


    
    def _is_inside_bbox(self, word: Dict, bbox: Tuple) -> bool:
        """Check if word is inside bounding box"""
        x0, top, x1, bottom = bbox
        return (float(word["x0"]) >= x0 and float(word["x1"]) <= x1 and
                float(word["top"]) >= top and float(word["bottom"]) <= bottom)
    
    def _group_into_paragraphs(self, words: List[Dict]) -> List[Dict]:
        """Group words into paragraphs"""
        if not words:
            return []
        
        from collections import defaultdict
        
        lines_by_top = defaultdict(list)
        for word in words:
            top = round(float(word["top"]))
            lines_by_top[top].append(word["text"])
        
        paragraphs = []
        sorted_tops = sorted(lines_by_top.keys())
        
        current_para = []
        current_top = None
        
        for top in sorted_tops:
            line_text = " ".join(lines_by_top[top])
            
            if current_top is None or abs(top - current_top) <= 5:
                current_para.append((top, line_text))
            else:
                if current_para:
                    para_text = " ".join(line for _, line in current_para)
                    avg_top = sum(t for t, _ in current_para) / len(current_para)
                    paragraphs.append({"top": avg_top, "text": para_text})
                
                current_para = [(top, line_text)]
            
            current_top = top
        
        # Add last paragraph
        if current_para:
            para_text = " ".join(line for _, line in current_para)
            avg_top = sum(t for t, _ in current_para) / len(current_para)
            paragraphs.append({"top": avg_top, "text": para_text})
        
        return paragraphs
    
    def export_results(self, metadata: DocumentMetadata, output_file: str = None) -> Dict:
        """Export results in structured format"""
        result = {
            "document_metadata": asdict(metadata),
            "extraction_summary": {
                "total_sections": len(metadata.structure.sections),
                "total_tables": len(metadata.structure.tables),
                "total_figures": len(metadata.structure.figures),
                "total_annexes": len(metadata.structure.annexes),
                "glossary_terms": len(metadata.structure.glossary),
                "keywords_extracted": len(metadata.keywords),
                "overall_quality": metadata.quality.extraction_rate,
                "structure_completeness": metadata.quality.structure_completeness,
                "content_coherence": metadata.quality.content_coherence,
                "regulatory_compliance": metadata.quality.regulatory_compliance
            },
            "extraction_timestamp": datetime.now().isoformat()
        }
        
        if output_file:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
        
        return result
    
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