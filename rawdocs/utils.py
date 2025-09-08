# rawdocs/utils.py
import os
import re
import json
import requests
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse
import json
import requests
from groq import Groq

import spacy
from PyPDF2 import PdfReader
from langdetect import detect
from dotenv import load_dotenv

# Charger les variables d'environnement depuis .env
load_dotenv()

# Chargez une fois les modèles spaCy :
NLP_FR = spacy.load("fr_core_news_sm")
NLP_EN = spacy.load("en_core_web_sm")

# Stopwords FR/EN basiques pour nettoyage
STOPWORDS = {
    "le", "la", "les", "de", "des", "du", "un", "une", "et", "en", "à", "dans", "que", "qui",
    "pour", "par", "sur", "avec", "au", "aux", "ce", "ces", "se", "ses", "est",
    "the", "and", "of", "to", "in", "that", "it", "is", "was", "for", "on", "are", "with",
    "as", "i", "at", "be", "by", "this"
}


def call_mistral_with_confidence(text_chunk, document_url="", filename=""):
    """
    Get extraction + confidence scores from Mistral in one call.
    La clé API est lue depuis la variable d'environnement MISTRAL_API_KEY.
    """
    api_key = os.getenv(
        "MISTRAL_API_KEY") or "j2wOKpM86nlZhhlvkXXG7rFd4bhM4PN5"  # Fallback à la clé hardcodée si .env non disponible

    try:
        url = "https://api.mistral.ai/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }

        prompt = f"""
        You are an expert document analyzer. Analyze this document and extract metadata with confidence scores.

        DOCUMENT TEXT (first 5000 chars):
        {text_chunk[:5000]}

        SOURCE URL: {document_url}
        FILENAME: {filename}

        HINT: Look for version numbers in headers like "DTC_S006597_PF_R_FAB_17319_EN_15.0" where 15.0 is the version

        TASK: Return ONLY a JSON object with extracted metadata AND your confidence scores:

        {{
            "metadata": {{
                "title": "the MAIN document title (not technical headers)",
                "type": "guideline|regulation|directive|report|procedure|standard|manufacturer|certificate|authorization|specifications|other",
                "publication_date": "exact date (DD Month YYYY format)",
                "version": "document version/reference number",
                "source": "organization name",
                "context": "main domain (pharmaceutical, medical, legal, etc.)",
                "country": "country code (EU, US, FR, IE, PL, etc.)",
                "language": "language code (en, fr, etc.)"
            }},
            "confidence_scores": {{
                "title": 85,
                "type": 90,
                "publication_date": 95,
                "version": 20,
                "source": 90,
                "context": 80,
                "country": 95,
                "language": 98
            }},
            "extraction_reasoning": {{
                "title": "Found clear title in document header",
                "type": "Document explicitly mentions 'guideline' in title",
                "publication_date": "Detected header date indicating publication",
                "version": "No clear version number found",
                "source": "URL or internal org name used",
                "context": "Multiple pharmaceutical terms detected",
                "country": "URL domain or regulatory hints used",
                "language": "Detected by language model"
            }}
        }}

        INSTRUCTIONS FOR DOCUMENT TYPE DETECTION:
        - "manufacturer": Documents listing manufacturing sites, manufacturer information, production details
        - "specifications": Documents detailing product specifications, technical specifications, drug product specs
        - "guideline": Official guidance documents from regulatory agencies
        - "regulation": Legal regulatory texts, laws, regulations
        - "directive": EU directives and similar regulatory directives  
        - "report": Assessment reports, evaluation reports, inspection reports
        - "procedure": Standard operating procedures, process descriptions
        - "standard": Technical standards, quality standards
        - "certificate": Certificates, authorizations, approvals
        - "authorization": Marketing authorizations, permits, licenses
        - "other": Any other document type

                
        RULES FOR PUBLICATION DATE DETECTION:
                
        Use the date that appears:
        - At the top near the agency name (e.g. “EMA/CHMP/ICH/24235/2006 Corr.2 23 January 2025” → use 23 January 2025)
        - In the format “Published: ...” or “Publication date: ...”
        - Next to "Official Journal of the European Union" (this is official)

        DO NOT use:
        - “Adopted by CHMP on …”
        - “Date of coming into effect …”
        - “Finalization date”
        - References to old laws like “Directive 2008/57/EC of 15 July 2008”

        Examples:
        ✅ GOOD → “23 January 2025” near header  
        ✅ GOOD → “Published in Official Journal: 2 August 2013”  
        ❌ BAD → “Directive 2008/123/EC of 24 November 2008”  
        ❌ BAD → “Date for coming into effect: 26 July 2023”

        Additional Notes:
        - Prioritize clarity over completeness
        - Return no extra text outside JSON

        TYPE DETECTION KEYWORDS:
        - "SPECIFICATIONS OF" → type: "specifications"
        - "MANUFACTURERS" → type: "manufacturer"  
        - "GUIDELINE" → type: "guideline"
        - "PROCEDURE" → type: "procedure"
        - Look for explicit type indicators in document titles and headers

        INSTRUCTIONS FOR TITLE EXTRACTION:
        - Extract the MAIN document title from the body content, not technical headers
        - Ignore technical codes like "DTC_S006597_PF_R_FAB_17319_EN_15.0"
        - Look for the primary subject/topic in the document body
        - For manufacturer docs: "MANUFACTURERS" + product name + description
        - Combine logical title elements: "MANUFACTURERS S 6597 Film-coated tablet..."
        - Avoid including addresses, company names, or metadata in the title

        INSTRUCTIONS FOR VERSION DETECTION:

        
        1. If a regulatory code is present like:
        - EMA/CHMP/ICH/xxxxx/yyyy
        - ICH/yyyy/stepX
        → extract that full code as version

        2. If "Corr.2", "Rev.1", "(R1)", etc. appears after the code or title → append it

        3. If "Step 5", "Step 2b", etc. appears near the header → append it

        4. Accept also formats like:
        - M4Q(R2) → version = "M4Q(R2)"
        - CTD_QR_Rev.2 → version = "Rev.2"
        - EN_15.0 → version = "15.0"

        — EXAMPLES —
        ✅ EMA/CHMP/ICH/214732/2007 Step 5
        ✅ EMA/CHMP/ICH/24235/2006 Corr.2 Step 5
        ✅ M4Q(R2)
        ✅ Rev. 1
        ✅ Version 3.0

        — DO NOT EXTRACT —
        ❌ Directive 2008/57/EC
        ❌ IDs not linked to versioning


        If no clear version is found, return an empty string: `""`


        INSTRUCTIONS FOR SOURCE DETECTION:
        - Look for explicit organization names in the document
        - Check for regulatory agency indicators (EMA, FDA, ANSM, MHRA, etc.)
        - For manufacturer documents, use the company name mentioned
        - For specifications documents, look for regulatory authority context
        - Check for "European Pharmacopoeia" → likely EMA/European regulatory context
        - If from URL domain: .ema.europa.eu = "EMA", .fda.gov = "FDA", etc.
        - If unclear, analyze content to determine likely source organization
        - Do NOT default to EMA unless clearly an EMA document

        INSTRUCTIONS FOR COUNTRY DETECTION:
        - Look for country-specific indicators in text
        - Check addresses, phone numbers, regulatory codes
        - Analyze URL domain for country hints
        - For manufacturer docs, use country where facilities are located
        - Use specific country codes (FR, IE, PL) not just EU when possible

        CONFIDENCE SCORING:
        - 90-100: Explicitly stated in document
        - 70-89: Strong indicators/evidence  
        - 50-69: Reasonable inference from context
        - 30-49: Weak indicators, uncertain
        - 0-29: Not found or very unclear

        TITLE EXTRACTION EXAMPLES:
        ✅ GOOD: "MANUFACTURERS S 6597 Film-coated tablet containing 10 mg of perindopril arginine and 2.5 mg of indapamide"
        ✅ GOOD: "SPECIFICATIONS OF THE DRUG PRODUCT S 20098 Film-coated tablets containing 25 mg of drug substance"
        ❌ BAD: "DTC_S006597_PF_R_FAB_17319_EN_15.0 MANUFACTURERS S 6597..."
        ❌ BAD: Including addresses or company details in title

        Return ONLY the JSON, no other text.
        """


        data = {
            "model": "mistral-large-latest",
            "messages": [{"role": "user", "content": prompt + "\n\nReturn ONLY one JSON object or array. No markdown, no code fences, no explanations, no ellipses in values."}],
            "temperature": 0.1,
            "max_tokens": 1200
        }

        response = requests.post(url, headers=headers, json=data, timeout=30)
        response.raise_for_status()

        if response.status_code == 200:
            result = response.json()
            response_text = result['choices'][0]['message']['content']

            # Try to robustly parse JSON from the response
            def _sanitize_and_parse(candidate: str):
                original = candidate
                # Normalize smart quotes
                candidate = candidate.replace('\u201c', '"').replace('\u201d', '"').replace('\u2019', "'")
                # Remove trailing commas before } or ]
                candidate = re.sub(r',\s*([}\]])', r'\1', candidate)
                # Fix single-quoted keys: 'key': value -> "key": value
                candidate = re.sub(r"(?<=\{|,)\s*'([A-Za-z0-9_]+)'\s*:\s*", r'"\1": ', candidate)
                # Fix single-quoted string values: key: 'value' -> key: "value"
                candidate = re.sub(r":\s*'([^'\\]*(?:\\.[^'\\]*)*)'", r': "\1"', candidate)
                # Fix unquoted keys only when at object boundaries
                candidate = re.sub(r'(?<=\{|,)\s*([A-Za-z0-9_]+)\s*:', r'"\1":', candidate)
                try:
                    return json.loads(candidate)
                except Exception:
                    return None

            def _extract_balanced_block(text: str):
                # Support either object {..} or array [..]
                start_obj = text.find('{')
                start_arr = text.find('[')
                starts = [s for s in [start_obj, start_arr] if s != -1]
                if not starts:
                    return None
                start = min(starts)
                opener = text[start]
                closer = '}' if opener == '{' else ']'
                i = start
                depth = 0
                in_str = False
                esc = False
                while i < len(text):
                    ch = text[i]
                    if in_str:
                        if esc:
                            esc = False
                        elif ch == '\\':
                            esc = True
                        elif ch == '"':
                            in_str = False
                    else:
                        if ch == '"':
                            in_str = True
                        elif ch == opener:
                            depth += 1
                        elif ch == closer:
                            depth -= 1
                            if depth == 0:
                                return text[start:i+1]
                    i += 1
                return None

            def _try_parse_json(text: str):
                # 1) Direct parse
                try:
                    return json.loads(text)
                except Exception:
                    pass
                # 2) Fenced code block ```json ... ``` or ``` ... ``` (object or array)
                m = re.search(r"```(?:json|JSON)?\s*([\[{][\s\S]*?[\]}])\s*```", text)
                if m:
                    fragment = m.group(1)
                    try:
                        return json.loads(fragment)
                    except Exception:
                        parsed = _sanitize_and_parse(fragment)
                        if parsed is not None:
                            return parsed
                # 3) Balanced block extraction (object or array)
                candidate = _extract_balanced_block(text)
                if candidate:
                    try:
                        return json.loads(candidate)
                    except Exception:
                        parsed = _sanitize_and_parse(candidate)
                        if parsed is not None:
                            return parsed
                return None

            full_result = _try_parse_json(response_text)
            if not full_result:
                print("❌ No valid JSON found or parse failed")
                return None

            # Add quality metrics to metadata 
            if 'metadata' in full_result and 'confidence_scores' in full_result:
                confidence_scores = full_result.get('confidence_scores', {})
                overall_quality = calculate_overall_quality(confidence_scores)
                
                full_result['metadata']['quality'] = {
                    'extraction_rate': overall_quality,
                    'field_scores': confidence_scores,
                    'extraction_reasoning': full_result.get('extraction_reasoning', {}),
                    'extracted_fields': len([v for v in full_result['metadata'].values() if v]),
                    'total_fields': len(full_result['metadata']),
                    'llm_powered': True
                }
            
            print("✅ Mistral extraction with confidence successful!")
            return full_result
        else:
            print(f"❌ Mistral API error: {response.status_code}")
            return None

    except Exception as e:
        print(f"❌ Mistral API error: {e}")
        return None


def calculate_overall_quality(confidence_scores):
    """
    Calculate overall extraction quality from LLM confidence scores
    """
    if not confidence_scores:
        return 0

    weights = {
        'title': 1.5,
        'type': 1.2,
        'publication_date': 1.3,
        'source': 1.2,
        'context': 1.0,
        'language': 0.8,
        'country': 0.8,
        'version': 0.7
    }

    total_weighted_score = 0
    total_weight = 0
    for field, score in confidence_scores.items():
        w = weights.get(field, 1.0)
        total_weighted_score += score * w
        total_weight += w

    return int(total_weighted_score / total_weight) if total_weight else 0


import pdfplumber
import fitz  # PyMuPDF pour l'extraction d'images
from PIL import Image
import io
import base64

def extract_tables_from_pdf(file_path):
    """
    Extrait tous les tableaux du PDF avec pdfplumber
    """
    tables_data = []
    
    try:
        with pdfplumber.open(file_path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                # Extraire les tableaux de la page
                tables = page.extract_tables()
                
                for table_num, table in enumerate(tables, 1):
                    if table and len(table) > 1:  # Au moins un header + une ligne
                        # Nettoyer le tableau (supprimer les cellules vides)
                        cleaned_table = []
                        for row in table:
                            cleaned_row = [cell.strip() if cell else "" for cell in row]
                            if any(cleaned_row):  # Garder seulement les lignes non vides
                                cleaned_table.append(cleaned_row)
                        
                        if len(cleaned_table) > 1:
                            tables_data.append({
                                'page': page_num,
                                'table_id': f"table_{page_num}_{table_num}",
                                'headers': cleaned_table[0],
                                'rows': cleaned_table[1:],
                                'total_rows': len(cleaned_table) - 1,
                                'total_columns': len(cleaned_table[0]) if cleaned_table else 0
                            })
    
    except Exception as e:
        print(f"❌ Erreur lors de l'extraction des tableaux: {e}")
    
    return tables_data


def call_llm_with_learned_prompt(prompt):
    """Call LLM with the adaptive prompt"""
    try:
        api_key = os.getenv("GROQ_API_KEY") or "your_actual_groq_api_key_here"
        client = Groq(api_key=api_key)
        
        response = client.chat.completions.create(
            messages=[{
                "role": "user", 
                "content": prompt + "\n\nReturn ONLY one JSON object or array. No markdown, no code fences, no explanations, no ellipses in values."
            }],
            model="llama3-8b-8192",
            temperature=0.1,
            max_tokens=1500
        )
        
        result = response.choices[0].message.content

        # Robust JSON parsing similar to Mistral path
        def _sanitize_and_parse(candidate: str):
            # Normalize smart quotes
            candidate = candidate.replace('\u201c', '"').replace('\u201d', '"').replace('\u2019', "'")
            # Remove trailing commas before } or ]
            candidate = re.sub(r',\s*([}\]])', r'\1', candidate)
            # Fix single-quoted keys: 'key': value -> "key": value
            candidate = re.sub(r"(?<=\{|,)\s*'([A-Za-z0-9_]+)'\s*:\s*", r'"\1": ', candidate)
            # Fix single-quoted string values: key: 'value' -> key: "value"
            candidate = re.sub(r":\s*'([^'\\]*(?:\\.[^'\\]*)*)'", r': "\1"', candidate)
            # Fix unquoted keys only when at object boundaries
            candidate = re.sub(r'(?<=\{|,)\s*([A-Za-z0-9_]+)\s*:', r'"\1":', candidate)
            try:
                return json.loads(candidate)
            except Exception:
                return None

        def _extract_balanced_json(text: str):
            start = text.find('{')
            if start == -1:
                return None
            i = start
            depth = 0
            in_str = False
            esc = False
            while i < len(text):
                ch = text[i]
                if in_str:
                    if esc:
                        esc = False
                    elif ch == '\\':
                        esc = True
                    elif ch == '"':
                        in_str = False
                else:
                    if ch == '"':
                        in_str = True
                    elif ch == '{':
                        depth += 1
                    elif ch == '}':
                        depth -= 1
                        if depth == 0:
                            return text[start:i+1]
                i += 1
            return None

        def _try_parse_json(text: str):
            # 1) Direct parse
            try:
                return json.loads(text)
            except Exception:
                pass
            # 2) Fenced code block ```json ... ``` or ``` ... ```
            m = re.search(r"```(?:json|JSON)?\s*(\{[\s\S]*?\})\s*```", text)
            if m:
                try:
                    return json.loads(m.group(1))
                except Exception:
                    parsed = _sanitize_and_parse(m.group(1))
                    if parsed is not None:
                        return parsed
            # 3) Balanced-brace extraction
            candidate = _extract_balanced_json(text)
            if candidate:
                try:
                    return json.loads(candidate)
                except Exception:
                    parsed = _sanitize_and_parse(candidate)
                    if parsed is not None:
                        return parsed
            return {}

        return _try_parse_json(result)
            
    except Exception as e:
        print(f"LLM call error: {e}")
        # Fallback to your existing Mistral extraction
        return call_mistral_basic_extraction(prompt)

def call_mistral_basic_extraction(prompt):
    """Fallback to basic extraction if Groq fails"""
    # Use your existing call_mistral_with_confidence logic here
    # or return empty dict to use fallback
    return {}

def extract_images_from_pdf(file_path):
    """
    Extrait toutes les images du PDF avec PyMuPDF
    """
    images_data = []
    
    try:
        pdf_document = fitz.open(file_path)
        
        for page_num in range(len(pdf_document)):
            page = pdf_document[page_num]
            image_list = page.get_images()
            
            for img_index, img in enumerate(image_list):
                try:
                    # Récupérer l'image
                    xref = img[0]
                    pix = fitz.Pixmap(pdf_document, xref)
                    
                    # Convertir en format utilisable
                    if pix.n - pix.alpha < 4:  # GRAY ou RGB
                        img_data = pix.tobytes("png")
                        
                        # Créer un objet PIL pour obtenir les dimensions
                        pil_image = Image.open(io.BytesIO(img_data))
                        width, height = pil_image.size
                        
                        # Encoder en base64 pour stockage/affichage
                        img_base64 = base64.b64encode(img_data).decode()
                        
                        # Créer une version preview (plus petite pour l'affichage dans la liste)
                        preview_image = pil_image.copy()
                        preview_image.thumbnail((300, 200), Image.Resampling.LANCZOS)
                        preview_buffer = io.BytesIO()
                        preview_image.save(preview_buffer, format='PNG')
                        preview_base64 = base64.b64encode(preview_buffer.getvalue()).decode()
                        
                        images_data.append({
                            'page': page_num + 1,
                            'image_id': f"img_{page_num + 1}_{img_index + 1}",
                            'width': width,
                            'height': height,
                            'format': 'PNG',
                            'size_bytes': len(img_data),
                            'base64_data': img_base64[:100] + "..." if len(img_base64) > 100 else img_base64,  # Tronquer pour l'affichage
                            'preview_base64': preview_base64,  # Version preview pour l'affichage
                            'full_base64': img_base64  # Données complètes
                        })
                    
                    pix = None  # Libérer la mémoire
                    
                except Exception as e:
                    print(f"❌ Erreur lors de l'extraction de l'image {img_index} page {page_num + 1}: {e}")
                    continue
        
        pdf_document.close()
    
    except Exception as e:
        print(f"❌ Erreur lors de l'extraction des images: {e}")
    
    return images_data


def extract_full_text(file_path):
    """
    Extraction de texte utilisant UltraAdvancedPDFExtractor pour obtenir
    le contenu structuré au lieu du texte brut pdfplumber
    """
    try:
        # Utiliser UltraAdvancedPDFExtractor pour obtenir le contenu structuré
        from client.submissions.ctd_submission.utils_ultra_advanced import UltraAdvancedPDFExtractor

        extractor = UltraAdvancedPDFExtractor()
        result = extractor.extract_ultra_structured_content(file_path)

        if result and result.get('extracted', False):
            # Retourner le texte structuré qui préserve la mise en forme
            structured_text = result.get('text', '')

            # Enrichir avec des informations sur la structure détectée
            structure = result.get('structure', {})
            if structure:
                structure_info = []
                if structure.get('tables'):
                    structure_info.append(f"📊 {len(structure['tables'])} tableau(x)")
                if structure.get('images'):
                    structure_info.append(f"🖼️ {len(structure['images'])} image(s)")
                if structure.get('text_blocks'):
                    structure_info.append(f"📝 {len(structure['text_blocks'])} bloc(s) de texte")

                if structure_info:
                    structured_text = f"[STRUCTURE DÉTECTÉE: {', '.join(structure_info)}]\n\n{structured_text}"

            return structured_text
        else:
            # Fallback vers pdfplumber en cas d'échec
            print(f"⚠️ UltraAdvancedPDFExtractor failed, falling back to pdfplumber for {file_path}")
            return _extract_full_text_fallback(file_path)

    except Exception as e:
        # En cas d'erreur, utiliser le fallback pdfplumber
        print(f"⚠️ Error with UltraAdvancedPDFExtractor: {e}, falling back to pdfplumber")
        return _extract_full_text_fallback(file_path)


def _extract_full_text_fallback(file_path):
    """Fallback vers l'ancienne méthode pdfplumber"""
    text = ""
    with pdfplumber.open(file_path) as pdf:
        # extraire en priorité les 1ères pages
        for page in pdf.pages[:2]:
            page_text = page.extract_text() or ""
            text += "\n" + page_text
    # ensuite le reste si besoin
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages[2:]:
            text += "\n" + (page.extract_text() or "")
    return text


def extract_metadonnees(pdf_path, url=""):
    """Extract metadata with fallback to working system"""
    
    # First try the learning-enhanced extraction
    try:
        # Get learning insights
        learning_prompts = get_learned_field_improvements()
        
        # If we have learning data, use adaptive extraction
        if learning_prompts:
            text = extract_full_text(pdf_path)
            if text:
                instructions = build_adaptive_field_instructions(learning_prompts)
                mistakes_prompt = get_common_mistakes_prompt(learning_prompts)
                
                prompt = f"""Extract metadata from this document:
{text[:2000]}

Fields to extract: {json.dumps(instructions, indent=2)}

Common mistakes to avoid: {mistakes_prompt}

Return ONLY JSON with keys: title, type, publication_date, version, source, context, country, language, url_source"""
                
                result = call_llm_with_learned_prompt(prompt)
                if result and isinstance(result, dict):
                    return result
    
    except Exception as e:
        print(f"Learning extraction failed: {e}")
    
    # Fallback to your working Mistral extraction
    try:
        result = call_mistral_with_confidence(extract_full_text(pdf_path), url, pdf_path)
        if result and 'metadata' in result:
            return result['metadata']
    except Exception as e:
        print(f"Mistral extraction failed: {e}")
    
    # Final fallback
    return extract_basic_fallback(pdf_path, url)

def get_learned_field_improvements():
    """Get field-specific improvements from feedback data"""
    try:
        from .models import MetadataFeedback
        
        field_insights = {}
        
        for feedback in MetadataFeedback.objects.all():
            corrections = feedback.corrections_made
            
            # Analyze wrong fields
            for wrong in corrections.get('corrected_fields', []):
                field = wrong.get('field')
                ai_value = wrong.get('ai_value', '')
                correct_value = wrong.get('human_value', '')
                
                if field not in field_insights:
                    field_insights[field] = {'mistakes': [], 'patterns': []}
                
                field_insights[field]['mistakes'].append({
                    'wrong': ai_value,
                    'correct': correct_value
                })
        
        return field_insights
        
    except Exception as e:
        print(f"Learning insights error: {e}")
        return {}
    

def build_adaptive_field_instructions(learning_prompts):
    """Build field instructions that incorporate learning"""
    instructions = {}
    
    base_fields = {
        'title': "Document title",
        'type': "Document type (guide, report, etc)",
        'publication_date': "Publication date",
        'source': "Source organization",
        'language': "Document language code (en, fr, etc.)",
        'context': "The field of the document content (pharmaceutical, legal, etc.) ",
    }
    
    for field, base_desc in base_fields.items():
        if field in learning_prompts:
            mistakes = learning_prompts[field]['mistakes']
            if mistakes:
                # Add specific guidance based on past mistakes
                common_errors = [m['wrong'] for m in mistakes[-3:]]  # Last 3 mistakes
                instructions[field] = f"{base_desc}. AVOID these patterns: {', '.join(common_errors)}"
            else:
                instructions[field] = base_desc
        else:
            instructions[field] = base_desc
    
    return instructions

def get_common_mistakes_prompt(learning_prompts):
    """Generate prompt section about common mistakes"""
    mistakes = []
    
    for field, data in learning_prompts.items():
        if data['mistakes']:
            latest_mistakes = data['mistakes'][-2:]  # Last 2 mistakes
            for mistake in latest_mistakes:
                mistakes.append(f"Don't confuse {field}: '{mistake['wrong']}' should be '{mistake['correct']}'")
    
    return "\n".join(mistakes[:5])  

def extract_basic_fallback(file_path: str, source_url: str) -> dict:
    """Basic fallback with honest low confidence scores"""
    reader = PdfReader(file_path)
    info = reader.metadata or {}
    title = info.title or Path(file_path).stem
    full_text = extract_full_text(file_path)

    try:
        lang = detect(full_text)
    except:
        lang = "en"

    basic_meta = {
        "title": title,
        "type": "unknown",
        "publication_date": "",
        "version": "",
        "source": "",
        "context": "",
        "country": "",
        "language": lang,
        "url_source": source_url
    }

    conf_scores = {
        'title': 30 if title else 0,
        'type': 0,
        'publication_date': 0,
        'version': 0,
        'source': 0,
        'context': 0,
        'country': 0,
        'language': 80 if lang else 0
    }

    overall_quality = calculate_overall_quality(conf_scores)

    basic_meta['quality'] = {
        'extraction_rate': overall_quality,
        'field_scores': conf_scores,
        'extraction_reasoning': {
            'title': 'Basic PDF metadata extraction',
            'type': 'Could not determine document type',
            'source': 'No source identification possible'
        },
        'extracted_fields': 1,
        'total_fields': len(conf_scores),
        'llm_powered': False
    }
    return basic_meta