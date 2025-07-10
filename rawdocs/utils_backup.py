import re
from pathlib import Path
from urllib.parse import urlparse

import spacy
from PyPDF2 import PdfReader
from langdetect import detect

# Chargez une fois :
#   python -m spacy download fr_core_news_sm
#   python -m spacy download en_core_web_sm
NLP_FR = spacy.load("fr_core_news_sm")
NLP_EN = spacy.load("en_core_web_sm")

# Stopwords FR/EN basiques pour nettoyage
STOPWORDS = {
    "le","la","les","de","des","du","un","une","et","en","à","dans","que","qui",
    "pour","par","sur","avec","au","aux","ce","ces","se","ses","est",
    "the","and","of","to","in","that","it","is","was","for","on","are","with",
    "as","i","at","be","by","this"
}

# Patterns réduits pour l'exemple (à enrichir si besoin)
TITLE_PATTERNS = [
    r'^(?:guideline|guide|procedure|regulation|directive|report)[^\n]{5,150}',
    r'^[A-Z][A-Za-z0-9\s\-–—(),]{20,150}\b'
]
DATE_PATTERNS = [
    r'(?i)(?:Publié\s+le|Publication\s*[:\-]?)\s*([0-3]?\d\s+\w+\s+\d{4})',
    r'\b(\d{4}-\d{2}-\d{2})\b'
]
VERSION_PATTERNS = [
    r'\bversion\s*[:\-]?\s*([\d\.]+)\b',
    r'\bv([\d\.]+)\b'
]
# Sources clés pour l'exemple
SOURCE_PATTERNS = {
    'EMA': [r'\bEMA\b', r'\beuropean medicines agency\b'],
    'FDA': [r'\bFDA\b', r'\bfood and drug administration\b'],
}
DOCUMENT_TYPE_PATTERNS = {
    'guideline': [r'\bguideline\b', r'\bguide\b'],
    'procedure': [r'\bprocedure\b'],
    'report':    [r'\breport\b']
}
COUNTRY_TLD = lambda url: urlparse(url).netloc.split('.')[-1].upper()

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
    reader = PdfReader(file_path)
    info    = reader.metadata or {}
    title   = info.title or ""
    version = getattr(reader, "pdf_header_version", "")

    full_text = extract_full_text(file_path)

    # 1) Langue & spaCy
    try:
        lang = detect(full_text)
    except:
        lang = "fr"
    nlp = NLP_EN if lang.startswith("en") else NLP_FR
    doc = nlp(full_text)

    # 2) Titre via patterns
    extracted_title = ""
    for pat in TITLE_PATTERNS:
        m = re.search(pat, full_text, re.IGNORECASE | re.MULTILINE)
        if m:
            extracted_title = m.group(0).strip()
            break
    if not extracted_title:
        extracted_title = title or Path(file_path).stem

    # 3) Date de publication via patterns
    publication_date = ""
    for pat in DATE_PATTERNS:
        m = re.search(pat, full_text, re.IGNORECASE)
        if m:
            publication_date = m.group(1) if m.groups() else m.group(0)
            break

    # 4) Version via patterns
    extracted_version = ""
    for pat in VERSION_PATTERNS:
        m = re.search(pat, full_text, re.IGNORECASE)
        if m:
            extracted_version = m.group(1)
            break

    # 5) Source interne via ORG ou patterns
    orgs = [ent.text for ent in doc.ents if ent.label_ == "ORG"]
    if orgs:
        source_interne = orgs[0]
    else:
        source_interne = ""
        for name, pats in SOURCE_PATTERNS.items():
            if any(re.search(p, full_text, re.IGNORECASE) for p in pats):
                source_interne = name
                break

    # 6) Type de document via patterns
    doc_type = "autres"
    for t, pats in DOCUMENT_TYPE_PATTERNS.items():
        if any(re.search(p, full_text, re.IGNORECASE) for p in pats):
            doc_type = t
            break

    # 7) Contexte : deux premières phrases spaCy
    sents = list(doc.sents)
    context = " ".join([s.text for s in sents[:2]]).strip()

    # 8) Pays via TLD
    tld = COUNTRY_TLD(source_url)
    country = tld if len(tld) == 2 else ""

    return {
        "title":            extracted_title,
        "type":             doc_type.capitalize(),
        "language":         lang,
        "version":          extracted_version,
        "url_source":       source_url,
        "source":           source_interne,
        "publication_date": publication_date,
        "context":          context,
        "country":          country,
    }
