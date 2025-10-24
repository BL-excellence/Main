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
import dateparser

# Safe import for spaCy to avoid failures during management commands
try:
    import spacy
except Exception:
    spacy = None
from PyPDF2 import PdfReader
from langdetect import detect
from dotenv import load_dotenv

import subprocess
import json
from pdfminer.high_level import extract_text
from langdetect import detect
# spaCy may be None if not installed or incompatible; avoid importing again
from pathlib import Path
from docx import Document
import pdfplumber
import fitz  # PyMuPDF pour l'extraction d'images
from PIL import Image
import io
import base64

# Charger les variables d'environnement depuis .env
load_dotenv()

# Charge spaCy models safely; tolerate missing/incompatible spaCy during management commands
try:
    NLP_FR = spacy.load("fr_core_news_sm") if spacy else None
    NLP_EN = spacy.load("en_core_web_sm") if spacy else None
except Exception:
    NLP_FR = None
    NLP_EN = None

# Stopwords FR/EN basiques pour nettoyage
STOPWORDS = {
    "le", "la", "les", "de", "des", "du", "un", "une", "et", "en", "à", "dans", "que", "qui",
    "pour", "par", "sur", "avec", "au", "aux", "ce", "ces", "se", "ses", "est",
    "the", "and", "of", "to", "in", "that", "it", "is", "was", "for", "on", "are", "with",
    "as", "i", "at", "be", "by", "this"
}


def extract_exif_metadata(file_path):
    """Extraction brute avec ExifTool, avec inférence si Title absent"""
    print(f"🔍 Tentative d'extraction ExifTool pour {file_path}")
    try:
        result = subprocess.run(
            ["exiftool", "-json", file_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        if result.returncode != 0:
            print(f"❌ Erreur ExifTool: {result.stderr}")
            text = extract_text_content(file_path).strip().split('\n')[0] if extract_text_content(file_path) else Path(
                file_path).stem
            return {'Title (inferred)': {'value': text, 'confidence': 50, 'method': 'text_inference'}}
        metadata = json.loads(result.stdout)[0]
        print(f"✅ ExifTool a extrait {len(metadata)} champs: {list(metadata.keys())}")
        if 'Title' in metadata and metadata['Title']:
            metadata['Title'] = {'value': metadata['Title'], 'confidence': 75, 'method': 'exif'}
        elif 'Title' not in metadata or not metadata['Title']:
            text = extract_text_content(file_path).strip().split('\n')[0] if extract_text_content(file_path) else Path(
                file_path).stem
            metadata['Title (inferred)'] = {'value': text, 'confidence': 50, 'method': 'text_inference'}
        return metadata
    except Exception as e:
        print(f"❌ Erreur ExifTool: {e}")
        print(f"PATH actuel: {os.environ['PATH']}")
        text = extract_text_content(file_path).strip().split('\n')[0] if extract_text_content(file_path) else Path(
            file_path).stem
        return {'Title (inferred)': {'value': text, 'confidence': 50, 'method': 'text_inference'}}


def extract_text_content(file_path):
    """Extraction du texte brut selon le type de fichier"""
    ext = Path(file_path).suffix.lower()
    text = ""
    print(f"📄 Début de l'extraction texte pour {file_path} (type: {ext})")
    if ext == ".pdf":
        try:
            text = extract_text(file_path)
            print(f"✅ Texte extrait avec succès ({len(text)} caractères): {text[:100]}...")
        except Exception as e:
            print(f"❌ Erreur extraction texte PDF: {e}")
    elif ext in [".docx"]:
        try:
            doc = Document(file_path)
            text = "\n".join([p.text for p in doc.paragraphs])
            print(f"✅ Texte extrait avec succès ({len(text)} caractères)")
        except Exception as e:
            print(f"❌ Erreur extraction texte DOCX: {e}")
    return text


def extract_source_from_text(text):
    """Extraction améliorée de la source/organisation"""
    text_lower = text.lower()
    text_sample = text[:3000]  # Analyser les 3000 premiers caractères
    
    # Dictionnaire étendu d'organisations avec patterns
    organizations = {
        'EMA': {
            'patterns': [
                r'European\s+Medicines\s+Agency',
                r'\bEMA\b',
                r'EMA/CHMP',
                r'Committee\s+for\s+Medicinal\s+Products',
                r'CHMP',
                r'www\.ema\.europa\.eu'
            ],
            'confidence': 95
        },
        'FDA': {
            'patterns': [
                r'Food\s+and\s+Drug\s+Administration',
                r'\bFDA\b',
                r'U\.?S\.?\s+FDA',
                r'www\.fda\.gov'
            ],
            'confidence': 95
        },
        'ANSM': {
            'patterns': [
                r'Agence\s+Nationale\s+de\s+Sécurité\s+du\s+Médicament',
                r'\bANSM\b',
                r'ansm\.sante\.fr'
            ],
            'confidence': 95
        },
        'WHO': {
            'patterns': [
                r'World\s+Health\s+Organization',
                r'\bWHO\b',
                r'Organisation\s+Mondiale\s+de\s+la\s+Santé'
            ],
            'confidence': 95
        },
        'ICH': {
            'patterns': [
                r'International\s+Council\s+for\s+Harmonisation',
                r'\bICH\b',
                r'ICH\s+Harmonised'
            ],
            'confidence': 90
        },
        'European Commission': {
            'patterns': [
                r'European\s+Commission',
                r'Commission\s+Européenne',
                r'ec\.europa\.eu'
            ],
            'confidence': 90
        },
        'MHRA': {
            'patterns': [
                r'Medicines\s+and\s+Healthcare\s+products\s+Regulatory\s+Agency',
                r'\bMHRA\b',
                r'www\.gov\.uk/mhra'
            ],
            'confidence': 95
        },
        'European Pharmacopoeia': {
            'patterns': [
                r'European\s+Pharmacopoeia',
                r'Pharmacopée\s+Européenne',
                r'\bPh\.?\s*Eur\.?',
                r'EDQM'
            ],
            'confidence': 90
        }
    }
    
    # Rechercher les organisations
    for org_name, org_data in organizations.items():
        for pattern in org_data['patterns']:
            if re.search(pattern, text_sample, re.IGNORECASE):
                print(f"✅ Source détectée: {org_name} (via pattern: {pattern})")
                return {
                    'value': org_name,
                    'confidence': org_data['confidence'],
                    'method': 'text_pattern_match'
                }
    
    # Recherche d'organisations dans les métadonnées PDF (Author)
    try:
        with pdfplumber.open(file_path) as pdf:
            metadata = pdf.metadata or {}
            if 'Author' in metadata and metadata['Author']:
                author = metadata['Author'].strip()
                if author and len(author) > 2:
                    print(f"✅ Source trouvée dans Author: {author}")
                    return {
                        'value': author,
                        'confidence': 80,
                        'method': 'pdf_metadata_author'
                    }
    except:
        pass
    
    print("⚠️ Source non détectée")
    return None


def extract_context_from_text(text):
    """Extraction du contexte/domaine du document"""
    text_lower = text.lower()
    text_sample = text[:5000]
    
    # Dictionnaire de contextes avec mots-clés pondérés
    contexts = {
        'pharmaceutical': {
            'keywords': ['pharmaceutical', 'medicinal', 'drug', 'medicine', 'API', 'active substance',
                        'excipient', 'formulation', 'dosage', 'tablet', 'capsule', 'injection',
                        'pharmaceutique', 'médicament', 'substance active'],
            'weight': 2,
            'min_score': 3
        },
        'regulatory': {
            'keywords': ['regulation', 'directive', 'compliance', 'authorization', 'approval',
                        'regulatory', 'legal requirement', 'legislation', 'law',
                        'réglementation', 'directive', 'conformité', 'autorisation'],
            'weight': 2,
            'min_score': 3
        },
        'quality_control': {
            'keywords': ['quality control', 'GMP', 'quality assurance', 'validation', 'testing',
                        'specification', 'analytical', 'method', 'stability',
                        'contrôle qualité', 'assurance qualité', 'validation'],
            'weight': 2,
            'min_score': 3
        },
        'manufacturing': {
            'keywords': ['manufacturing', 'production', 'facility', 'plant', 'process',
                        'fabrication', 'production', 'installation', 'processus'],
            'weight': 2,
            'min_score': 3
        },
        'clinical': {
            'keywords': ['clinical trial', 'patient', 'treatment', 'therapy', 'diagnosis',
                        'essai clinique', 'patient', 'traitement', 'thérapie'],
            'weight': 1.5,
            'min_score': 2
        },
        'safety': {
            'keywords': ['safety', 'adverse event', 'pharmacovigilance', 'risk', 'side effect',
                        'sécurité', 'effet indésirable', 'pharmacovigilance', 'risque'],
            'weight': 1.5,
            'min_score': 2
        }
    }
    
    # Calculer les scores pour chaque contexte
    scores = {}
    for context_name, context_data in contexts.items():
        score = 0
        for keyword in context_data['keywords']:
            count = text_sample.count(keyword.lower())
            score += count * context_data['weight']
        
        if score >= context_data['min_score']:
            scores[context_name] = score
    
    # Retourner le contexte avec le score le plus élevé
    if scores:
        best_context = max(scores, key=scores.get)
        confidence = min(70 + (scores[best_context] * 2), 95)
        print(f"✅ Contexte détecté: {best_context} (score: {scores[best_context]})")
        return {
            'value': best_context,
            'confidence': confidence,
            'method': 'keyword_scoring'
        }
    
    print("⚠️ Contexte non détecté")
    return None


def extract_country_from_text(text, file_path=""):
    """Extraction améliorée du pays"""
    text_sample = text[:3000]
    
    # Patterns pour détecter les pays
    country_patterns = {
        'EU': [
            r'European\s+Union',
            r'\bEU\b',
            r'Union\s+Européenne',
            r'EMA/CHMP',
            r'Official\s+Journal\s+of\s+the\s+European\s+Union'
        ],
        'FR': [
            r'\bFrance\b',
            r'French\s+Republic',
            r'République\s+Française',
            r'ANSM',
            r'\+33\s*\d',  # Code téléphone français
            r'\bF-\d{5}\b'  # Code postal français
        ],
        'US': [
            r'United\s+States',
            r'\bUSA\b',
            r'\bU\.?S\.?A\.?\b',
            r'FDA',
            r'Washington,?\s*DC'
        ],
        'UK': [
            r'United\s+Kingdom',
            r'\bUK\b',
            r'Great\s+Britain',
            r'MHRA',
            r'London,?\s*England'
        ],
        'DE': [
            r'\bGermany\b',
            r'\bDeutschland\b',
            r'BfArM',
            r'\+49\s*\d'
        ],
        'IE': [
            r'\bIreland\b',
            r'\bIrlande\b',
            r'Irish',
            r'Dublin,?\s*Ireland',
            r'\+353\s*\d'
        ],
        'PL': [
            r'\bPoland\b',
            r'\bPologne\b',
            r'Polish',
            r'Warsaw',
            r'\+48\s*\d'
        ]
    }
    
    # Rechercher les patterns de pays
    for country_code, patterns in country_patterns.items():
        for pattern in patterns:
            if re.search(pattern, text_sample, re.IGNORECASE):
                print(f"✅ Pays détecté: {country_code} (via pattern: {pattern})")
                return {
                    'value': country_code,
                    'confidence': 85,
                    'method': 'text_pattern_match'
                }
    
    # Analyser le nom de fichier pour des indices
    if file_path:
        filename = Path(file_path).stem.upper()
        for country_code in country_patterns.keys():
            if f"_{country_code}_" in filename or f"_{country_code}." in filename:
                print(f"✅ Pays détecté dans le nom de fichier: {country_code}")
                return {
                    'value': country_code,
                    'confidence': 75,
                    'method': 'filename_pattern'
                }
    
    print("⚠️ Pays non détecté")
    return None


def enhanced_nlp_analysis(text, file_path=""):
    """Analyse NLP renforcée sans LLM"""
    meta = {}
    if not text.strip():
        print("⚠️ Aucun texte à analyser pour NLP")
        return meta

    print("🔍 Lancement de l'analyse NLP renforcée")

    # DÉTECTION DU TYPE DE DOCUMENT
    doc_types = {
        'guideline': ['guideline', 'guidance', 'recommendations', 'best practices', 'guide', 'notice', 'instructions',
                      'ligne directrice', 'recommandations'],
        'regulation': ['regulation', 'directive', 'law', 'legal', 'article', 'decree', 'règlement', 'directive'],
        'report': ['report', 'assessment', 'evaluation', 'analysis', 'study', 'rapport', 'évaluation'],
        'procedure': ['procedure', 'protocol', 'method', 'process', 'operating', 'utilisation', 'précautions',
                      'procédure', 'protocole'],
        'specifications': ['specifications', 'specs', 'requirements', 'criteria', 'specification', 'spécifications',
                           'exigences'],
        'manufacturer': ['manufacturer', 'manufacturing', 'production', 'facility', 'plant', 'fabricant',
                         'manufacturier'],
        'certificate': ['certificate', 'certification', 'approval', 'authorization', 'certificat', 'approbation'],
        'standard': ['standard', 'norm', 'iso', 'quality standard', 'norme', 'standard qualité']
    }

    text_lower = text.lower()
    for doc_type, keywords in doc_types.items():
        if any(keyword in text_lower for keyword in keywords):
            meta['type'] = {
                'value': doc_type,
                'confidence': 85,
                'method': 'nlp_keyword_match'
            }
            print(f"✅ Type détecté: {doc_type}")
            break

    # EXTRACTION DE DATES AMÉLIORÉE
    date_candidates = []

    # Détection de langue
    language_info = detect_document_language(text, file_path)
    lang = language_info.get('value', 'en') if language_info else 'en'
    print(f"Langue détectée pour dates: {lang}")

    # Définir les noms de mois par langue
    month_names_by_lang = {
        'en': "(?:January|February|March|April|May|June|July|August|September|October|November|December)",
        'fr': "(?:janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre)"
    }
    month_names = month_names_by_lang.get(lang, month_names_by_lang['en'])

    # Pattern 1: Label explicite "Date de publication:" (priorité maximale)
    pub_label_pattern = rf'(?:Date\s+de\s+publication|Published\s+on)[:\s\|]+(\d{{1,2}}\s+{month_names}\s+\d{{4}})'
    for match in re.finditer(pub_label_pattern, text, re.IGNORECASE):
        date_str = match.group(1)
        parsed_date = dateparser.parse(date_str, languages=[lang])
        if parsed_date:
            normalized_date = parsed_date.strftime('%d %B %Y')
            date_candidates.append({
                'date': normalized_date,
                'priority': 99,
                'context': 'publication_date_label',
                'raw': date_str
            })
            print(f"📅 Date trouvée (Publication label): {date_str} → {normalized_date}")

    # Pattern 2: Date dans en-tête avec mois/année
    header_date_pattern = rf'^([A-Z][a-z]+\s+\d{{4}}|{month_names}\s+\d{{4}})'
    for match in re.finditer(header_date_pattern, text, re.MULTILINE | re.IGNORECASE):
        date_str = match.group(1)
        parsed_date = dateparser.parse(date_str, languages=[lang])
        if parsed_date and not any(c['context'] == 'publication_date_label' for c in date_candidates):
            normalized_date = parsed_date.strftime('1 %B %Y')
            date_candidates.append({
                'date': normalized_date,
                'priority': 93,
                'context': 'header_date',
                'raw': date_str
            })
            print(f"📅 Date trouvée (en-tête): {date_str} → {normalized_date}")

    # Pattern 3: Format DD Month YYYY (générique)
    generic_date_pattern = rf'\b(\d{{1,2}}\s+{month_names}\s+\d{{4}})\b'
    for match in re.finditer(generic_date_pattern, text, re.IGNORECASE):
        date_str = match.group(1)
        parsed_date = dateparser.parse(date_str, languages=[lang])
        if parsed_date and not any(c['context'] == 'publication_date_label' for c in date_candidates):
            normalized_date = parsed_date.strftime('%d %B %Y')
            start_pos = max(0, match.start() - 100)
            end_pos = min(len(text), match.end() + 100)
            context = text[start_pos:end_pos].lower()
            
            if 'coming into effect' in context or 'entrée en vigueur' in context:
                priority = 50
                ctx_type = 'effective_date'
            elif 'published' in context or 'publication' in context:
                priority = 94
                ctx_type = 'publication_date'
            elif 'adopted' in context or 'adoption' in context:
                priority = 90
                ctx_type = 'adoption_date'
            else:
                priority = 75
                ctx_type = 'generic_date'
            
            date_candidates.append({
                'date': normalized_date,
                'priority': priority,
                'context': ctx_type,
                'raw': date_str
            })
            print(f"📅 Date trouvée ({ctx_type}): {date_str}")

    # Sélection de la meilleure date
    if date_candidates:
        date_candidates.sort(key=lambda x: (-x['priority'], datetime.strptime(x['date'], '%d %B %Y') if '%d' in x['date'] else datetime.min), reverse=True)
        selected_date = date_candidates[0]['date']
        meta['publication_date'] = {
            'value': selected_date,
            'confidence': date_candidates[0]['priority'],
            'context': date_candidates[0]['context'],
            'method': 'nlp_pattern_match_multilingual'
        }
        print(f"✅ Date de publication sélectionnée: {selected_date}")

    # EXTRACTION DE VERSION
    version_patterns = [
        r'version\s*[:\-]?\s*(\d+\.?\d*)',
        r'v\.?\s*(\d+\.?\d*)',
        r'rev\.?\s*(\d+)',
        r'r(\d+)',
        r'step\s*(\d+)',
        r'corr\.?\s*(\d+)',
        r'EN_(\d+\.?\d*)',
        r'_(\d+\.?\d*)\.pdf'
    ]
    for pattern in version_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            meta['version'] = {
                'value': match.group(1),
                'confidence': 80,
                'method': 'regex_version'
            }
            print(f"✅ Version détectée: {match.group(1)}")
            break

    # EXTRACTION DE LA SOURCE
    source_info = extract_source_from_text(text)
    if source_info:
        meta['source'] = source_info
    
    # EXTRACTION DU CONTEXTE
    context_info = extract_context_from_text(text)
    if context_info:
        meta['context'] = context_info
    
    # EXTRACTION DU PAYS
    country_info = extract_country_from_text(text, file_path)
    if country_info:
        meta['country'] = country_info
    
    # EXTRACTION DE LA LANGUE
    language_info = detect_document_language(text, file_path)
    if language_info:
        meta['language'] = language_info

    return meta


def detect_document_language(text, file_path=""):
    """Détecte la langue du document avec plusieurs méthodes"""
    if not text or len(text.strip()) < 50:
        print("⚠️ Texte trop court pour détecter la langue")
        return None

    detected_langs = []

    # Méthode 1: langdetect sur le texte complet
    try:
        lang_full = detect(text[:5000])
        detected_langs.append(('langdetect_full', lang_full, 90))
        print(f"✅ Langue détectée (texte complet): {lang_full}")
    except Exception as e:
        print(f"⚠️ Erreur langdetect (texte complet): {e}")

    # Méthode 2: langdetect sur plusieurs échantillons
    try:
        samples = [
            text[:1000],
            text[len(text) // 2:len(text) // 2 + 1000] if len(text) > 2000 else text,
            text[-1000:] if len(text) > 1000 else text
        ]
        lang_counts = {}
        for sample in samples:
            if len(sample.strip()) > 50:
                try:
                    lang = detect(sample)
                    lang_counts[lang] = lang_counts.get(lang, 0) + 1
                except:
                    pass

        if lang_counts:
            most_common_lang = max(lang_counts, key=lang_counts.get)
            confidence = 85 + (lang_counts[most_common_lang] * 5)
            detected_langs.append(('langdetect_samples', most_common_lang, min(confidence, 98)))
            print(f"✅ Langue détectée (échantillons): {most_common_lang}")
    except Exception as e:
        print(f"⚠️ Erreur langdetect (échantillons): {e}")

    # Méthode 3: Analyse du nom de fichier
    if file_path:
        filename = Path(file_path).stem.upper()
        lang_indicators = {
            'en': ['_EN_', '_EN.', 'ENGLISH', '_ENG_'],
            'fr': ['_FR_', '_FR.', 'FRENCH', '_FRA_'],
            'de': ['_DE_', '_DE.', 'GERMAN', '_DEU_'],
            'es': ['_ES_', '_ES.', 'SPANISH', '_ESP_'],
            'it': ['_IT_', '_IT.', 'ITALIAN', '_ITA_'],
            'pl': ['_PL_', '_PL.', 'POLISH', '_POL_']
        }

        for lang_code, indicators in lang_indicators.items():
            if any(ind in filename for ind in indicators):
                detected_langs.append(('filename', lang_code, 80))
                print(f"✅ Langue détectée (nom de fichier): {lang_code}")
                break

    # Méthode 4: Analyse des mots-clés
    text_sample = text[:3000].lower()
    keyword_scores = {
        'en': sum([
            text_sample.count(' the ') * 2,
            text_sample.count(' and '),
            text_sample.count(' of '),
            text_sample.count(' to '),
            text_sample.count(' in ')
        ]),
        'fr': sum([
            text_sample.count(' le ') * 2,
            text_sample.count(' la ') * 2,
            text_sample.count(' les ') * 2,
            text_sample.count(' de '),
            text_sample.count(' du ')
        ]),
        'de': sum([
            text_sample.count(' der ') * 2,
            text_sample.count(' die ') * 2,
            text_sample.count(' das ') * 2,
            text_sample.count(' und ')
        ])
    }

    if keyword_scores:
        best_lang = max(keyword_scores, key=keyword_scores.get)
        if keyword_scores[best_lang] > 10:
            confidence = min(70 + (keyword_scores[best_lang] // 5), 85)
            detected_langs.append(('keywords', best_lang, confidence))
            print(f"✅ Langue détectée (mots-clés): {best_lang}")

    # Consolidation
    if not detected_langs:
        print("❌ Aucune langue détectée")
        return None

    detected_langs.sort(key=lambda x: x[2], reverse=True)
    best_method, best_lang, best_confidence = detected_langs[0]

    lang_votes = {}
    for method, lang, conf in detected_langs:
        lang_votes[lang] = lang_votes.get(lang, 0) + 1

    if lang_votes.get(best_lang, 0) >= 2:
        best_confidence = min(best_confidence + 10, 98)
        print(f"🎯 Consensus sur la langue: {best_lang}")

    return {
        'value': best_lang,
        'confidence': best_confidence,
        'method': f'language_detection_{best_method}'
    }


def extract_structured_metadata(file_path):
    """Extraction basée sur la structure du document"""
    try:
        with pdfplumber.open(file_path) as pdf:
            if not pdf.pages:
                print("⚠️ Aucune page trouvée dans le PDF")
                return {'title_structured': '', 'header_info': ''}

            first_page = pdf.pages[0]
            text_objects = first_page.extract_words()

            if not text_objects:
                print("⚠️ Aucun texte extrait de la première page")
                try:
                    text = extract_text(file_path)
                    first_line = text.split('\n')[0].strip() if text else ''
                    return {
                        'title_structured': first_line,
                        'header_info': first_line
                    }
                except Exception as e:
                    print(f"❌ Erreur fallback pdfminer: {e}")
                    return {'title_structured': '', 'header_info': ''}

            # Analyser les en-têtes
            header_text = []
            for obj in text_objects:
                if obj.get('top', float('inf')) < 100:
                    header_text.append(obj['text'])

            header_string = ' '.join(header_text) if header_text else ''

            # Extraire titre
            title_candidates = []
            sizes = [obj.get('size', 0) for obj in text_objects if obj.get('size') is not None]

            if not sizes:
                print("⚠️ Aucune taille de texte trouvée")
                return {
                    'title_structured': header_string or Path(file_path).stem,
                    'header_info': header_string
                }

            max_size = max(sizes)
            for obj in text_objects:
                if obj.get('size', 0) >= max_size - 2:  # Texte de taille importante
                    title_candidates.append(obj['text'])

            title = ' '.join(title_candidates[:15]) if title_candidates else header_string or Path(file_path).stem

            return {
                'title_structured': title,
                'header_info': header_string
            }
    except Exception as e:
        print(f"❌ Erreur extraction structurée: {e}")
        return {'title_structured': '', 'header_info': ''}


def extract_extended_pdf_properties(file_path):
    """Extraction propriétés PDF étendues"""
    try:
        with pdfplumber.open(file_path) as pdf:
            metadata = pdf.metadata or {}

            # Analyser les métadonnées XMP si disponibles
            xmp_metadata = {}
            try:
                if hasattr(pdf, 'doc') and hasattr(pdf.doc, 'xmp_metadata'):
                    xmp = pdf.doc.xmp_metadata
                    if xmp:
                        xmp_metadata = {
                            'creator': getattr(xmp, 'creator', ''),
                            'description': getattr(xmp, 'description', ''),
                            'subject': getattr(xmp, 'subject', ''),
                            'keywords': getattr(xmp, 'keywords', '')
                        }
            except Exception:
                pass

            return {**metadata, **xmp_metadata}
    except Exception as e:
        print(f"❌ Erreur propriétés PDF: {e}")
        return {}


def regex_metadata_extraction(text):
    """Extraction par regex spécialisées pour documents réglementaires"""
    patterns = {
        'ema_reference': r'EMA/[A-Z]+/[A-Z]+/\d+/\d+',
        'ich_reference': r'ICH/[A-Z0-9]+/\d+',
        'step_version': r'Step\s+(\d+[a-z]?)',
        'correction': r'Corr\.?\s*(\d+)',
        'european_directive': r'Directive\s+(\d{4}/\d+/EC)',
        'organization_regex': r'(European Medicines Agency|EMA|FDA|ANSM|MHRA)',
        'effective_date': r'effective\s+(?:from\s+)?(\d{1,2}\s+\w+\s+\d{4})',
        'published_date': r'published\s+(?:on\s+)?(\d{1,2}\s+\w+\s+\d{4})',
        'adoption_date': r'adopted\s+(?:on\s+)?(\d{1,2}\s+\w+\s+\d{4})'
    }

    extracted = {}
    for key, pattern in patterns.items():
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            extracted[key] = match.group(1) if match.groups() else match.group(0)

    return extracted


def merge_metadata_with_priority(metadata_sources):
    """Fusionner les métadonnées avec priorité"""
    merged = {}

    field_mapping = {
        'title': ['Title', 'title', 'title (inferred)', 'title_structured', 'Subject'],
        'type': ['type', 'DM_Category', 'doc_type'],
        'source': ['Author', 'Creator', 'organization', 'source_organization', 'ema_reference', 'organization_regex'],
        'version': ['version', 'DM_Version', 'step_version', 'correction'],
        'publication_date': ['CreateDate', 'publication_date', 'effective_date', 'published_date', 'date'],
        'language': ['Language', 'language', 'DM_Language'],
        'country': ['country'],
        'context': ['DM_Category', 'DM_Path', 'context']
    }

    for field, possible_keys in field_mapping.items():
        for source in metadata_sources:
            for key in possible_keys:
                if key in source and source[key] and not merged.get(field):
                    merged[field] = source[key]
                    break
            if merged.get(field):
                break

    return merged


def infer_additional_metadata(text):
    """Analyse NLP du contenu pour déduire d'autres métadonnées (version améliorée)"""
    return enhanced_nlp_analysis(text)


def extract_metadata_local_pipeline(file_path):
    """Point d'entrée principal pour l'extraction locale"""
    print(f"\n{'=' * 80}")
    print(f"🚀 EXTRACTION DYNAMIQUE PROFESSIONNELLE")
    print(f"📄 Fichier: {Path(file_path).name}")
    print(f"{'=' * 80}\n")

    # 1. Extraction du texte
    full_text = extract_text_content(file_path)

    # 2. Analyse NLP renforcée comme source principale
    nlp_meta = enhanced_nlp_analysis(full_text, file_path)

    # 3. Extraction complémentaire via Exif (si disponible)
    exif_meta = extract_exif_metadata(file_path)

    # 4. Normalisation : convertir toutes les données en format uniforme
    normalized_meta = {}

    # Traiter les données NLP
    for field, value in nlp_meta.items():
        if isinstance(value, dict) and 'value' in value:
            normalized_meta[field] = value
        elif value:
            normalized_meta[field] = {
                'value': value,
                'confidence': 80,
                'method': 'nlp_analysis'
            }

    # Ajouter les données Exif si elles améliorent la qualité
    if exif_meta:
        # Title depuis Exif (priorité si présent)
        if 'Title' in exif_meta and isinstance(exif_meta['Title'], dict) and exif_meta['Title'].get('value'):
            if 'title' not in normalized_meta or normalized_meta['title']['confidence'] < exif_meta['Title']['confidence']:
                normalized_meta['title'] = exif_meta['Title']
        # Title (inferred) comme fallback
        elif 'Title (inferred)' in exif_meta and isinstance(exif_meta['Title (inferred)'], dict) and exif_meta['Title (inferred)'].get('value'):
            if 'title' not in normalized_meta or normalized_meta['title']['confidence'] < exif_meta['Title (inferred)']['confidence']:
                normalized_meta['title'] = exif_meta['Title (inferred)']

        # Source depuis Author
        if 'Author' in exif_meta and exif_meta['Author']:
            if 'source' not in normalized_meta or normalized_meta['source']['confidence'] < 70:
                normalized_meta['source'] = {
                    'value': exif_meta['Author'],
                    'confidence': 70,
                    'method': 'exif'
                }

        # Language depuis Exif (priorité moyenne)
        if 'Language' in exif_meta and exif_meta['Language']:
            if 'language' not in normalized_meta or normalized_meta['language']['confidence'] < 75:
                normalized_meta['language'] = {
                    'value': exif_meta['Language'],
                    'confidence': 75,
                    'method': 'exif'
                }

    # 5. Consolidation finale
    final_metadata = {}
    confidence_scores = {}

    expected_fields = ['title', 'type', 'publication_date', 'version', 'source', 'context', 'country', 'language', 'url_source']

    for field in expected_fields:
        if field in normalized_meta:
            meta_obj = normalized_meta[field]
            final_metadata[field] = meta_obj['value']
            confidence_scores[field] = meta_obj['confidence']
            print(f"   • {field}: {meta_obj['value']} (confiance: {meta_obj['confidence']}% - {meta_obj['method']})")
        else:
            final_metadata[field] = ""
            confidence_scores[field] = 0
            print(f"   • {field}: (non détecté)")

    # 6. Calcul de qualité globale
    overall_quality = calculate_overall_quality(confidence_scores)

    # 7. Construire l'objet quality
    extraction_reasoning = {}
    for field in expected_fields:
        if field in normalized_meta:
            method = normalized_meta[field]['method']
            extraction_reasoning[field] = f"Detected via {method}"
        else:
            extraction_reasoning[field] = "Not detected"

    final_metadata['quality'] = {
        'extraction_rate': overall_quality,
        'field_scores': confidence_scores,
        'extraction_reasoning': extraction_reasoning,
        'extracted_fields': sum(1 for v in final_metadata.values() if v and v != ""),
        'total_fields': len(expected_fields),
        'llm_powered': False
    }

    print(f"\n{'=' * 80}")
    print(f"✅ EXTRACTION TERMINÉE")
    print(f"📊 Taux de remplissage: {final_metadata['quality']['extraction_rate']}%")
    print(f"📈 Champs extraits: {final_metadata['quality']['extracted_fields']}/{final_metadata['quality']['total_fields']}")
    print(f"{'=' * 80}\n")

    return final_metadata


def call_mistral_with_confidence(text_chunk, document_url="", filename=""):
    """
    Get extraction + confidence scores from Mistral in one call.
    """
    api_key = os.getenv("MISTRAL_API_KEY") or "j2wOKpM86nlZhhlvkXXG7rFd4bhM4PN5"

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

        TASK: Return ONLY a JSON object with extracted metadata AND your confidence scores:

        {{
            "metadata": {{
                "title": "the MAIN document title",
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
                "publication_date": "Detected header date",
                "version": "No clear version number found",
                "source": "URL or internal org name used",
                "context": "Multiple pharmaceutical terms detected",
                "country": "URL domain hints used",
                "language": "Detected by language model"
            }}
        }}

        Return ONLY the JSON, no other text.
        """

        data = {
            "model": "mistral-large-latest",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": 1200
        }

        response = requests.post(url, headers=headers, json=data, timeout=30)
        response.raise_for_status()

        if response.status_code == 200:
            result = response.json()
            response_text = result['choices'][0]['message']['content']

            def _sanitize_and_parse(candidate: str):
                candidate = candidate.replace('\u201c', '"').replace('\u201d', '"').replace('\u2019', "'")
                candidate = re.sub(r',\s*([}\]])', r'\1', candidate)
                candidate = re.sub(r"(?<=\{|,)\s*'([A-Za-z0-9_]+)'\s*:\s*", r'"\1": ', candidate)
                candidate = re.sub(r":\s*'([^'\\]*(?:\\.[^'\\]*)*)'", r': "\1"', candidate)
                candidate = re.sub(r'(?<=\{|,)\s*([A-Za-z0-9_]+)\s*:', r'"\1":', candidate)
                try:
                    return json.loads(candidate)
                except Exception:
                    return None

            def _extract_balanced_block(text: str):
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
                                return text[start:i + 1]
                    i += 1
                return None

            def _try_parse_json(text: str):
                try:
                    return json.loads(text)
                except Exception:
                    pass
                m = re.search(r"```(?:json|JSON)?\s*([\[{][\s\S]*?[\]}])\s*```", text)
                if m:
                    fragment = m.group(1)
                    try:
                        return json.loads(fragment)
                    except Exception:
                        parsed = _sanitize_and_parse(fragment)
                        if parsed is not None:
                            return parsed
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
                print("❌ No valid JSON found")
                return None

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

            print("✅ Mistral extraction successful!")
            return full_result
        else:
            print(f"❌ Mistral API error: {response.status_code}")
            return None

    except Exception as e:
        print(f"❌ Mistral API error: {e}")
        return None


def calculate_overall_quality(confidence_scores):
    """Calculate overall extraction quality"""
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


def extract_tables_from_pdf(file_path):
    """Extrait tous les tableaux du PDF avec pdfplumber"""
    tables_data = []

    try:
        with pdfplumber.open(file_path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                tables = page.extract_tables()

                for table_num, table in enumerate(tables, 1):
                    if table and len(table) > 1:
                        cleaned_table = []
                        for row in table:
                            cleaned_row = [cell.strip() if cell else "" for cell in row]
                            if any(cleaned_row):
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
        print(f"❌ Erreur extraction tableaux: {e}")

    return tables_data


def call_llm_with_learned_prompt(prompt):
    """Call LLM with the adaptive prompt"""
    try:
        api_key = os.getenv("GROQ_API_KEY") or "your_actual_groq_api_key_here"
        client = Groq(api_key=api_key)

        response = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama3-8b-8192",
            temperature=0.1,
            max_tokens=1500
        )

        result = response.choices[0].message.content

        def _sanitize_and_parse(candidate: str):
            candidate = candidate.replace('\u201c', '"').replace('\u201d', '"').replace('\u2019', "'")
            candidate = re.sub(r',\s*([}\]])', r'\1', candidate)
            candidate = re.sub(r"(?<=\{|,)\s*'([A-Za-z0-9_]+)'\s*:\s*", r'"\1": ', candidate)
            candidate = re.sub(r":\s*'([^'\\]*(?:\\.[^'\\]*)*)'", r': "\1"', candidate)
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
                            return text[start:i + 1]
                i += 1
            return None

        def _try_parse_json(text: str):
            try:
                return json.loads(text)
            except Exception:
                pass
            m = re.search(r"```(?:json|JSON)?\s*(\{[\s\S]*?\})\s*```", text)
            if m:
                try:
                    return json.loads(m.group(1))
                except Exception:
                    parsed = _sanitize_and_parse(m.group(1))
                    if parsed is not None:
                        return parsed
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
        return call_mistral_basic_extraction(prompt)


def call_mistral_basic_extraction(prompt):
    """Fallback to basic extraction"""
    return {}


def extract_images_from_pdf(file_path):
    """Extrait toutes les images du PDF avec PyMuPDF"""
    images_data = []

    try:
        pdf_document = fitz.open(file_path)

        for page_num in range(len(pdf_document)):
            page = pdf_document[page_num]
            image_list = page.get_images()

            for img_index, img in enumerate(image_list):
                try:
                    xref = img[0]
                    pix = fitz.Pixmap(pdf_document, xref)

                    if pix.n - pix.alpha < 4:
                        img_data = pix.tobytes("png")
                        pil_image = Image.open(io.BytesIO(img_data))
                        width, height = pil_image.size
                        img_base64 = base64.b64encode(img_data).decode()

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
                            'base64_data': img_base64[:100] + "..." if len(img_base64) > 100 else img_base64,
                            'preview_base64': preview_base64,
                            'full_base64': img_base64
                        })

                    pix = None

                except Exception as e:
                    print(f"❌ Erreur extraction image {img_index} page {page_num + 1}: {e}")
                    continue

        pdf_document.close()

    except Exception as e:
        print(f"❌ Erreur extraction images: {e}")

    return images_data


def extract_full_text(file_path):
    """Extraction de texte utilisant directement pdfplumber"""
    return _extract_full_text_fallback(file_path)


def _extract_full_text_fallback(file_path):
    """Fallback vers l'ancienne méthode pdfplumber"""
    text = ""
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages[:2]:
            page_text = page.extract_text() or ""
            text += "\n" + page_text
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages[2:]:
            text += "\n" + (page.extract_text() or "")
    return text


def extract_metadonnees(pdf_path, url=""):
    """Extract metadata with fallback to working system"""

    if url:
        print(f"📡 Utilisation du prompt LLM pour l'extraction des métadonnées (URL: {url})")
        try:
            learning_prompts = get_learned_field_improvements()

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

        try:
            result = call_mistral_with_confidence(extract_full_text(pdf_path), url, pdf_path)
            if result and 'metadata' in result:
                return result['metadata']
        except Exception as e:
            print(f"Mistral extraction failed: {e}")

        return extract_basic_fallback(pdf_path, url)
    else:
        return extract_metadata_local_pipeline(pdf_path)


def get_learned_field_improvements():
    """Get field-specific improvements from feedback data"""
    try:
        from .models import MetadataFeedback

        field_insights = {}

        for feedback in MetadataFeedback.objects.all():
            corrections = feedback.corrections_made

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
                common_errors = [m['wrong'] for m in mistakes[-3:]]
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
            latest_mistakes = data['mistakes'][-2:]
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