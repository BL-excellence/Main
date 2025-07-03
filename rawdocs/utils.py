import os
import re
import json
import requests
from pathlib import Path
from datetime import datetime

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


def call_mistral_with_confidence(text_chunk, document_url=""):
    """
    Get extraction + confidence scores from Mistral in one call.
    La clé API est lue depuis la variable d'environnement MISTRAL_API_KEY.
    """
    api_key = os.getenv("MISTRAL_API_KEY")
    if not api_key:
        raise RuntimeError("La variable d'environnement MISTRAL_API_KEY n'est pas définie.")

    url = "https://api.mistral.ai/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }

    prompt = f"""
    You are an expert document analyzer. Analyze this document and extract metadata with confidence scores.

    DOCUMENT TEXT (first 2000 chars):
    {text_chunk[:2000]}

    SOURCE URL: {document_url}

    TASK: Return ONLY a JSON object with extracted metadata AND your confidence scores:

    {{
        "metadata": {{
            "title": "the ACTUAL document title",
            "type": "guideline|regulation|directive|report|procedure|standard|other",
            "publication_date": "exact date (DD Month YYYY format)",
            "version": "document version/reference number",
            "source": "EMA for European docs, FDA for US docs, or actual organization",
            "context": "main domain (pharmaceutical, medical, legal, etc.)",
            "country": "country code (EU, US, etc.)",
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
            "publication_date": "Date '24 November 2008' found in document text",
            "version": "No clear version number found",
            "source": "URL indicates European source, using EMA",
            "context": "Multiple pharmaceutical terms detected",
            "country": "URL domain .eu indicates European Union",
            "language": "Text is clearly in English"
        }}
    }}

    INSTRUCTIONS:
    - Confidence scores: 0-100 (0=not found, 50=uncertain, 100=completely certain)
    - Give HONEST confidence scores based on text evidence
    - If you're unsure about something, give it a low score (20-40)
    - If clearly found in text, give high score (80-100)
    - Provide reasoning for each extraction
    - For SOURCE: Use EMA for European, FDA for US
    - Return ONLY the JSON, no other text
    """

    data = {
        "model": "mistral-large-latest",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "max_tokens": 800
    }

    response = requests.post(url, headers=headers, json=data, timeout=30)
    response.raise_for_status()

    content = response.json()['choices'][0]['message']['content']
    match = re.search(r'\{.*\}', content, re.DOTALL)
    if not match:
        print("❌ No JSON found in Mistral response")
        return None

    try:
        return json.loads(match.group())
    except json.JSONDecodeError as e:
        print(f"❌ JSON parse error: {e}")
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


def extract_full_text(file_path: str) -> str:
    """Lit tout le PDF, nettoie et enlève les stopwords."""
    reader = PdfReader(file_path)
    pages = [p.extract_text() or "" for p in reader.pages]
    text = " ".join(pages)
    text = re.sub(r"[^0-9A-Za-zÀ-ÖØ-öø-ÿ\s\.,;:\-'\(\)]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    words = text.split()
    return " ".join(w for w in words if w.lower() not in STOPWORDS)


def extract_metadonnees(file_path: str, source_url: str) -> dict:
    """
    Main extraction function with REAL LLM confidence metrics
    """
    full_text = extract_full_text(file_path)
    llm_result = call_mistral_with_confidence(full_text, source_url)

    if llm_result and 'metadata' in llm_result and 'confidence_scores' in llm_result:
        metadata = llm_result['metadata']
        conf_scores = llm_result['confidence_scores']
        reasoning = llm_result.get('extraction_reasoning', {})

        metadata['url_source'] = source_url
        metadata['quality'] = {
            'extraction_rate': calculate_overall_quality(conf_scores),
            'field_scores':    conf_scores,
            'extraction_reasoning': reasoning,
            'extracted_fields': sum(1 for s in conf_scores.values() if s >= 50),
            'total_fields':     len(conf_scores),
            'llm_powered':      True
        }
        return metadata

    # Fallback basic extraction
    return extract_basic_fallback(file_path, source_url)


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
        "type": "",
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

    basic_meta['quality'] = {
        'extraction_rate': calculate_overall_quality(conf_scores),
        'field_scores':    conf_scores,
        'extraction_reasoning': {
            'title': 'Basic PDF metadata extraction',
            'type': 'Could not determine type',
            'source': 'No source identification possible'
        },
        'extracted_fields': 1,
        'total_fields':     len(conf_scores),
        'llm_powered':      False
    }
    return basic_meta
