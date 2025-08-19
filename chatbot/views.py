# views.py — Version finale pro (drop-in)

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.db.models import Q

import json
import os
import re
import datetime
import unicodedata
import logging
import requests
import sqlite3
from typing import List, Tuple, Dict, Any

# Local utils (conservés)
from chatbot.utils.matching import find_best_product, find_best_document
from chatbot.utils.intents import detect_full_intent_type
from chatbot.utils.relations import (
    get_products_linked_to_document,
    get_document_linked_to_product,
)

logger = logging.getLogger(__name__)

# =============================
# Normalization helpers
# =============================

def strip_accents(s: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFD', s or '') if unicodedata.category(c) != 'Mn')

def normalize_space(s: str) -> str:
    return re.sub(r"\s+", " ", (s or '').strip())

def _norm_txt(s: str) -> str:
    return normalize_space(strip_accents(s).lower())

def clean(v: Any) -> str:
    v = '' if v is None else str(v).strip()
    return v if v and v != 'N/A' else 'non spécifié'

def format_date(val):
    if not val:
        return 'non spécifiée'
    if isinstance(val, (datetime.date, datetime.datetime)):
        return val.strftime('%Y-%m-%d')
    s = str(val).strip()
    for f in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y', '%Y/%m/%d'):
        try:
            return datetime.datetime.strptime(s, f).strftime('%Y-%m-%d')
        except Exception:
            continue
    return s

# =============================
# Field aliases & keywords
# =============================

LIST_WORDS = (
    "tous", "toutes", "liste", "affiche", "afficher", "montre", "montrez", "voir", "lister",
    "montre-moi", "donne", "donne-moi", "quels", "quelles", "quel", "combien",
)

# Intent liste robuste
LIST_PAT = re.compile(
    r"\b(quels?|quelles?|liste|lister|affiche(?:r)?|montre(?:-moi)?|donne(?:-moi)?|voir|combien)\b", re.I
)
def is_list_intent_text(q: str) -> bool:
    return bool(LIST_PAT.search(_norm_txt(q)))
def mentions_plural_entity(q: str) -> bool:
    return bool(re.search(r"\b(produits|documents|sites)\b", _norm_txt(q)))
def has_any_filter_detected(prod_filters: list, doc_filters: list) -> bool:
    return bool(prod_filters or doc_filters)

DOC_ALIAS_TO_FIELD = {
    "type": "doc_type",
    "source": "source",
    "langue": "language",
    "language": "language",
    "pays": "country",
    "version": "version",
    "uploadé par": "owner__username",
    "owner": "owner__username",
}

PROD_ALIAS_TO_FIELD = {
    "type": "form",
    "forme": "form",
    "statut": "status",
    "principe actif": "active_ingredient",
    "principe": "active_ingredient",
    "actif": "active_ingredient",
    "dosage": "dosage",
    "nom": "name",
}

DOC_FIELD_MAP = DOC_ALIAS_TO_FIELD
PROD_FIELD_MAP = PROD_ALIAS_TO_FIELD

# =============================
# Fuzzy helpers
# =============================
from rapidfuzz import process, fuzz

QUOTES_RE = r"[\"'«»“”‘’]"

def _extract_quoted(text: str) -> List[str]:
    return re.findall(rf"{QUOTES_RE}([^\"'«»“”‘’]+){QUOTES_RE}", text or '')

def _guess_fields(q_lower: str, alias_map: dict, threshold: int = 85) -> List[str]:
    fields = set()
    aliases = list(alias_map.keys())
    tokens = re.findall(r"[a-zA-Zéèêàù0-9]+(?:\s+[a-zA-Zéèêàù0-9]+)?", q_lower or '')
    for cand in set(tokens):
        match = process.extractOne(cand, aliases, scorer=fuzz.token_set_ratio)
        if match and match[1] >= threshold:
            fields.add(alias_map[match[0]])
    return list(fields)

# =============================
# Explicit attribute question patterns
# =============================

DOC_ATTR_RE = re.compile(
    r"\b(?:donner|donne|afficher|affiche)\s+(?:le|la|les)?\s*(?P<fields>.+?)\s+de\s+(?:du|de\s+la|des)?\s*document\s+(?P<title>.+)$",
    re.IGNORECASE
)
PROD_ATTR_RE = re.compile(
    r"\b(?:donner|donne|afficher|affiche)\s+(?:le|la|les)?\s*(?P<fields>.+?)\s+de\s+(?:du|de\s+la|des)?\s*produit\s+(?P<name>.+)$",
    re.IGNORECASE
)
FIELD_SPLIT_RE = re.compile(r"\s*(?:,|\bet\b|\&|\+|/|;)+\s*", re.IGNORECASE)

def _normalize_target(s: str) -> str:
    s = (s or '').strip().strip("?!.;: ")
    if len(s) >= 2 and s[0] in '\"' and s[-1] in '\"':
        s = s[1:-1]
    return s.strip()

def _map_fields(raw_fields: str, entity: str) -> List[str]:
    parts = [p.strip() for p in FIELD_SPLIT_RE.split(strip_accents(raw_fields or '')) if p.strip()]
    mapped: List[str] = []
    alias_map = DOC_ALIAS_TO_FIELD if entity == 'library' else PROD_ALIAS_TO_FIELD
    for p in parts:
        if p in alias_map:
            f = alias_map[p]
            if f not in mapped:
                mapped.append(f)
            continue
        m = process.extractOne(p, alias_map.keys(), scorer=fuzz.token_set_ratio)
        if m and m[1] >= 85:
            f = alias_map[m[0]]
            if f not in mapped:
                mapped.append(f)
    return mapped

# =============================
# Robust status detection & mapping to DB code
# =============================

STATUS_PATTERNS = [
    # ARRET / RETRAIT
    (r"\ben\s+cours\s+d[’' ]arr[ée]?t\b", "arrete"),
    (r"\barr[ée]?t[ée]?s?\b", "arrete"),
    (r"\bretir[ée]?s?\b", "arrete"),
    (r"\bretir[ée] du march[ée]\b", "arrete"),
    (r"\bwithdrawn\b|\bdiscontinued\b", "arrete"),
    # COMMERCIALISÉ / AUTORISÉ / APPROUVÉ / MARKETED
    (r"\bcommercialis[ée]s?\b", "commercialise"),
    (r"\bautoris[ée]s?\b|\bapprouv[ée]s?\b", "commercialise"),
    (r"\bmis(?:\s+|-)sur(?:\s+|-)le(?:\s+|-)march[ée]\b|\bmarketed\b", "commercialise"),
    # EN DÉVELOPPEMENT
    (r"\ben\s+d[ée]velopp?ement\b", "developpement"),
    (r"\bd[ée]velopp[ée]s?\b|\bdevelopment\b|\bdev\b", "developpement"),
]

SYNONYMS_STATUS = {
    "arrete": {"arrêt", "arrêtés", "retiré", "retirés", "retirée", "retirées", "retiré du marché"},
    "commercialise": {"commercialisé", "commercialisés", "autorisé", "approuvé", "sur le marché", "marketed"},
    "developpement": {"en dev", "phase de dev", "development"},
}

def _status_to_code(Product, canonical: str) -> str | None:
    try:
        status_field = Product._meta.get_field("status")
        choices = getattr(status_field, "choices", []) or []
        n = lambda s: _norm_txt(str(s))
        by_code = {n(code): code for code, _ in choices}
        by_label = {n(label): code for code, label in choices}
        if canonical in by_code:
            return by_code[canonical]
        if canonical in by_label:
            return by_label[canonical]
        best = process.extractOne(canonical, list(by_label.keys()), scorer=fuzz.token_set_ratio)
        if best and best[1] >= 85:
            return by_label[best[0]]
    except Exception:
        pass
    return None

def _detect_canonical_status(text: str) -> str | None:
    t = _norm_txt(text)
    for pat, key in STATUS_PATTERNS:
        if re.search(pat, t, flags=re.I):
            return key
    cands = []
    for key, syns in SYNONYMS_STATUS.items():
        for s in syns | {key}:
            cands.append((fuzz.token_set_ratio(t, _norm_txt(s)), key))
    if not cands:
        return None
    score, key = max(cands)
    return key if score >= 80 else None

def _infer_status_filter(q_lower: str, Product):
    canonical = _detect_canonical_status(q_lower)
    if not canonical:
        return None
    code = _status_to_code(Product, canonical)
    return ("status", code or canonical)

# =============================
# Inferencers for product/site filters
# =============================

def _infer_form_filter(q_lower: str):
    mapping = {
        "comprime": "Comprimé", "comprimé": "Comprimé",
        "sirop": "Sirop",
        "gelule": "Gélule", "gélule": "Gélule",
        "capsule": "Capsule",
        "solution": "Solution",
        "pommade": "Pommade",
        "creme": "Crème", "crème": "Crème",
        "suspension": "Suspension",
    }
    txt = _norm_txt(q_lower)
    for k, label in mapping.items():
        if re.search(rf"\b{k}s?\b", txt):
            return ("form", label)
    return None

def _infer_active_ingredient_filter(q_lower: str):
    txt = _norm_txt(q_lower)
    m = re.search(r"(?:principe\s+actif\s+(?:est|=|de|:)?\s*|contien(?:t|nent)\s+|avec\s+du\s+|avec\s+de\s+)([a-z0-9\-\s]+)", txt, re.I)
    if m:
        val = m.group(1).strip()
        if len(val) >= 3:
            return ("active_ingredient", val)
    if "principe actif non specifie" in txt or "principe actif non precise" in txt:
        return ("active_ingredient", "__NULL__")
    return None

def _infer_dosage_filter(q_lower: str):
    txt = _norm_txt(q_lower).replace(",", ".")
    m = re.search(r"\b(\d+(?:\.\d+)?)\s*(mg|g|ml)\b", txt)
    if m:
        val, unit = m.group(1), m.group(2)
        return ("dosage", f"{val} {unit}")
    if "dosage non specifie" in txt or "dosage non precise" in txt:
        return ("dosage", "__NULL__")
    return None

def _infer_country_filter_for_products(q_lower: str):
    txt = _norm_txt(q_lower)
    m = re.search(r"\ben\s+([a-z\-]+)\b|\bau[x]?\s+([a-z\-]+)\b", txt)
    if m:
        c = (m.group(1) or m.group(2) or "").strip()
        if c:
            return ("__site_country__", c)
    return None

def _infer_country_filter_for_sites(q_lower: str) -> Tuple[str, str] | None:
    txt = _norm_txt(q_lower)
    # ex: "en france", "aux etats unis", "au maroc"
    m = re.search(r"\b(?:en|au|aux)\s+([a-z\-\s]+)\b", txt)
    if m:
        country = m.group(1).strip()
        aliases = {
            "france": "france",
            "etat unis": "united states", "etats unis": "united states",
            "royaume uni": "united kingdom", "angleterre": "united kingdom",
            "tunisie": "tunisia",
        }
        country = aliases.get(country, country)
        return ("country", country)
    if "pays non specifie" in txt or "pays non precise" in txt:
        return ("country", "__NULL__")
    return None

def _infer_owner_filter_for_docs(q_lower: str):
    txt = _norm_txt(q_lower)
    m = re.search(r"\b(?:depuis|par)\s+([a-z0-9_\- ]{2,})\b", txt)
    if m:
        return ("owner__username", m.group(1).strip())
    return None

# =============================
# Parse user request
# =============================

def parse_request(question: str, intent: str, produits_qs, docs_qs):
    q_raw = question or ""
    ql = strip_accents(q_raw).strip()

    # 0) Explicit “donner … de document/produit …” patterns
    md = DOC_ATTR_RE.search(ql)
    if md:
        title = _normalize_target(md.group('title'))
        fields = _map_fields(md.group('fields'), 'library') or ['doc_type']
        return {"entity":"library","mode":"detail","filters":[], "fields":fields, "title":title, "name":None, "site_name":None}

    mp = PROD_ATTR_RE.search(ql)
    if mp:
        name = _normalize_target(mp.group('name'))
        fields = _map_fields(mp.group('fields'), 'product') or ['form']
        return {"entity":"product","mode":"detail","filters":[], "fields":fields, "title":None, "name":name, "site_name":None}

    # 1) Keyword entity detection
    is_prod = bool(re.search(r"\bproduits?\b", ql))
    is_doc  = bool(re.search(r"\bdocuments?\b|\bguidances?\b|\bguidelines?\b", ql))
    is_site = bool(re.search(r"\bsites?\b", ql))
    entity = "product" if is_prod else "library" if is_doc else "site" if is_site else None

    # Intent liste robuste
    wants_list = is_list_intent_text(q_raw) or mentions_plural_entity(q_raw)

    # Named target via quotes
    quoted = _extract_quoted(q_raw)
    name_or_title_hint = quoted[0].strip() if quoted else None

    if not entity and name_or_title_hint:
        best_prod = find_best_product(name_or_title_hint, produits_qs)
        best_doc  = find_best_document(name_or_title_hint, docs_qs)
        if best_prod and not best_doc:
            entity = 'product'
        elif best_doc and not best_prod:
            entity = 'library'

    # Fuzzy fields (attribute asks on detail)
    fields_doc = _guess_fields(ql, DOC_FIELD_MAP)
    fields_prod = _guess_fields(ql, PROD_FIELD_MAP)

    # ========== Build filters ==========
    prod_filters: List[Tuple[str, str]] = []
    doc_filters:  List[Tuple[str, str]] = []
    site_filters: List[Tuple[str, str]] = []

    # product filters
    f = _infer_status_filter(ql, produits_qs.model)
    if f: prod_filters.append(f)
    f = _infer_form_filter(ql)
    if f: prod_filters.append(f)
    f = _infer_active_ingredient_filter(ql)
    if f: prod_filters.append(f)
    f = _infer_dosage_filter(ql)
    if f: prod_filters.append(f)
    f = _infer_country_filter_for_products(ql)
    if f: prod_filters.append(f)

    # document filters
    if m := re.search(r"\btype\s+([a-z0-9\-\s]+)", ql, re.I):
        doc_filters.append(("doc_type", m.group(1).strip()))
    if m := re.search(r"\bsource\s+([a-z0-9\-\s]+)", ql, re.I):
        doc_filters.append(("source", m.group(1).strip()))
    if m := re.search(r"\blang(?:ue|age)\s+([a-z0-9\-\s]+)", ql, re.I):
        doc_filters.append(("language", m.group(1).strip()))
    f = _infer_owner_filter_for_docs(ql)
    if f: doc_filters.append(f)

    # site filters
    f = _infer_country_filter_for_sites(ql)
    if f: site_filters.append(f)

    # Forcer list si un filtre (prod/doc/site) est détecté
    if not wants_list and (prod_filters or doc_filters or site_filters):
        wants_list = True

    # ======== Retours par entité ========
    if entity == 'product':
        fields  = fields_prod
        filters = prod_filters if wants_list else []
        return {
            "entity": 'product',
            "mode": "list" if wants_list else "detail",
            "filters": filters,
            "fields": fields,
            "title": None,
            "name": name_or_title_hint if not wants_list else None,
            "site_name": None,
        }

    if entity == 'library':
        fields  = fields_doc
        filters = doc_filters if wants_list else []
        return {
            "entity": 'library',
            "mode": "list" if wants_list else "detail",
            "filters": filters,
            "fields": fields,
            "title": name_or_title_hint if not wants_list else None,
            "name": None,
            "site_name": None,
        }

    if entity == 'site':
        filters = site_filters if wants_list else []
        return {
            "entity": 'site',
            "mode": "list" if wants_list else "detail",
            "filters": filters,
            "fields": [],
            "title": None,
            "name": None,
            "site_name": name_or_title_hint if not wants_list else None,
        }

    # ======== Default ========
    fields = fields_doc if entity == 'library' else fields_prod if entity == 'product' else []
    ent_or_intent = entity or intent
    return {
        "entity": ent_or_intent or 'library',
        "mode": "list" if wants_list else "detail",
        "filters": (
            prod_filters if ent_or_intent == 'product'
            else doc_filters  if ent_or_intent == 'library'
            else site_filters if ent_or_intent == 'site'
            else []
        ),
        "fields": fields,
        "title": name_or_title_hint if ent_or_intent == 'library' else None,
        "name":  name_or_title_hint if ent_or_intent == 'product' else None,
        "site_name": None,
    }


# =============================
# Renderers (Markdown tables) + JSON structuré
# =============================

def as_md(rows: List[Dict[str, Any]], cols: List[str], empty_msg: str = "Aucun résultat.") -> str:
    if not rows:
        return empty_msg
    head = "| " + " | ".join(cols) + " |"
    sep = "| " + " | ".join(["---"] * len(cols)) + " |"
    lines = [head, sep]
    for r in rows:
        lines.append("| " + " | ".join(str(r.get(c, "")) for c in cols) + " |")
    return "\n".join(lines)

def _json_table(rows: List[Dict[str, Any]], cols: List[str]) -> Dict[str, Any]:
    return {"cols": cols, "rows": rows}

# =============================
# Pagination helper
# =============================

def paginate(qs, page: int, page_size: int, max_page_size: int = 100):
    page = max(int(page or 1), 1)
    page_size = min(max(int(page_size or 50), 1), max_page_size)
    total = qs.count()
    items = qs[(page-1)*page_size : page*page_size]
    meta = {"page": page, "page_size": page_size, "total": total}
    return items, meta

# =============================
# Documents
# =============================

def list_documents(qs, filters, clean, format_date, as_md, page=1, page_size=50):
    q_all = Q()
    for field, value in filters:
        if field == "owner__username":
            v = _norm_txt(value)
            q_all &= Q(owner__username__iexact=v) | Q(owner__username__icontains=v)
            continue
        if value == "__NULL__":
            q_all &= Q(**{f"{field}__isnull": True}) | Q(**{f"{field}": ""})
        else:
            q_all &= Q(**{f"{field}__iexact": value}) | Q(**{f"{field}__icontains": value})

    if q_all:
        qs = qs.filter(q_all)

    items, meta = paginate(qs, page, page_size)

    cols = ["Titre", "Type", "Langue", "Version", "Source", "Date de publication", "Pays"]
    rows = [{
        "Titre": clean(d.title),
        "Type": clean(getattr(d, "doc_type", "")),
        "Langue": clean(getattr(d, 'language', '')),
        "Version": clean(getattr(d, 'version', '')),
        "Source": clean(getattr(d, 'source', '')),
        "Date de publication": format_date(getattr(d, 'publication_date', '')),
        "Pays": clean(getattr(d, 'country', '')),
    } for d in items]

    return {
        "ok": True,
        "entity": "library",
        "mode": "list",
        "data": _json_table(rows, cols),
        "render": {"markdown": as_md(rows, cols, empty_msg="Aucun document validé.")},
        "meta": meta,
    }

# =============================
# Produits
# =============================

def _apply_product_filters(qs, filters):
    # Normalise les codes de statut si besoin
    for i, (field, value) in enumerate(filters):
        if field == "status" and value:
            code = _status_to_code(qs.model, _norm_txt(value))
            if code:
                filters[i] = ("status", code)

    q_all = Q()
    site_country = None
    for field, value in filters:
        if field == "__site_country__":
            site_country = value
            continue
        if value == "__NULL__":
            q_all &= Q(**{f"{field}__isnull": True}) | Q(**{f"{field}": ""})
        else:
            q_all &= Q(**{f"{field}__iexact": value}) | Q(**{f"{field}__icontains": value})

    if q_all:
        qs = qs.filter(q_all)

    if site_country:
        qs = qs.filter(Q(sites__country__iexact=site_country) | Q(sites__country__icontains=site_country)).distinct()

    return qs

def list_products(qs, filters, clean, as_md, page=1, page_size=50):
    qs = _apply_product_filters(qs, filters)
    items, meta = paginate(qs, page, page_size)

    cols = ["Nom", "Type", "Principe actif", "Dosage", "Statut"]
    rows = [{
        "Nom": clean(p.name),
        "Type": clean(p.form),
        "Principe actif": clean(getattr(p, 'active_ingredient', '')),
        "Dosage": clean(getattr(p, 'dosage', '')),
        "Statut": clean(p.get_status_display()),
    } for p in items]

    return {
        "ok": True,
        "entity": "product",
        "mode": "list",
        "data": _json_table(rows, cols),
        "render": {"markdown": as_md(rows, cols, empty_msg="Aucun produit trouvé.")},
        "meta": meta,
    }

# =============================
# Detail product/document
# =============================

def _choose_product(qs, query_text: str):
    """Priorité: égalité normalisée > startswith normalisé > icontains > fuzzy."""
    want = _norm_txt(query_text or "")
    if not want:
        return None

    items = list(qs)

    for p in items:
        if _norm_txt(p.name) == want:
            return p

    for p in items:
        if _norm_txt(p.name).startswith(want):
            return p

    p = qs.filter(name__icontains=query_text).first()
    if p:
        return p

    return find_best_product(query_text, qs)

def detail_document(qs, fields, title_hint, raw_q, clean, format_date):
    doc = find_best_document(title_hint or raw_q, qs)
    if not doc:
        return {"ok": False, "entity":"library", "mode":"detail",
                "render":{"markdown":"Je n’ai pas trouvé ce document. Peux-tu préciser le titre ?"}}

    if not fields:
        fields = ["doc_type", "language", "version", "source", "publication_date", "country"]
    parts = []
    for f in fields:
        if f == "owner_username":
            val = getattr(getattr(doc, "owner", None), "username", "non spécifié")
        else:
            val = getattr(doc, f, "")
            if f in ("publication_date", "validated_at", "created_at"):
                val = format_date(val)
        parts.append(f"{f.replace('_', ' ').title()} : {val if val not in (None, '') else 'non spécifié'}")
    md = f"{'; '.join(parts)} du document « {doc.title} »."
    return {"ok": True, "entity":"library", "mode":"detail", "render":{"markdown": md}}

def detail_product(qs, fields, name_hint, raw_q, clean):
    name_q = name_hint or raw_q
    prod = _choose_product(qs, name_q)

    if not prod:
        m = re.search(r"\b[A-Z]{1,3}\s*\d{2,}\b", name_q or '')
        if m:
            token = re.sub(r"\s+", " ", m.group(0)).strip()
            prod = qs.filter(name__istartswith=token).first()

    if not prod:
        return {"ok": False, "entity":"product", "mode":"detail",
                "render":{"markdown":"Je n’ai pas trouvé ce produit. Peux-tu préciser le nom ?"}}

    if not fields:
        fields = ["form", "active_ingredient", "dosage", "status"]

    parts = []
    for f in fields:
        if f == "status":
            val = prod.get_status_display()
        elif f == "sites":
            val = "; ".join(f"{s.site_name} ({s.country})" for s in prod.sites.all()) or "non spécifié"
        else:
            val = getattr(prod, f, "")
        parts.append(f"{f.replace('_', ' ').title()} : {val if val not in (None, '') else 'non spécifié'}")

    md = f"{'; '.join(parts)} du produit « {prod.name} »."
    return {"ok": True, "entity":"product", "mode":"detail", "render":{"markdown": md}}

# =============================
# Sites
# =============================

def list_sites(qs, filters, clean, as_md, page=1, page_size=50):
    q_all = Q()
    wanted_country = None

    for field, value in filters:
        if field == "country":
            wanted_country = _norm_txt(value)
            q_all &= Q(country__icontains=value) | Q(country__iexact=value)
        elif value == "__NULL__":
            q_all &= Q(**{f"{field}__isnull": True}) | Q(**{f"{field}": ""})
        else:
            q_all &= Q(**{f"{field}__iexact": value}) | Q(**{f"{field}__icontains": value})

    if q_all:
        qs = qs.filter(q_all)

    items, meta = paginate(qs, page, page_size)

    cols = ["Nom", "Ville", "Pays"]
    rows = []
    for s in items:
        city = clean(getattr(s, 'city', ''))
        country = clean(getattr(s, 'country', ''))
        if wanted_country and wanted_country not in _norm_txt(country):
            continue
        rows.append({
            "Nom": clean(s.site_name),
            "Ville": city,
            "Pays": country,
        })

    md = as_md(rows, cols, empty_msg="Aucun site trouvé.")
    return {
        "ok": True,
        "entity": "site",
        "mode": "list",
        "data": {"cols": cols, "rows": rows},
        "render": {"markdown": md},
        "meta": meta,
    }

# =============================
# SQL Agent (NL → SQL for SQLite) — sécurisé
# =============================

SAFE_SQL_PREFIX = re.compile(r"^\s*select\b", re.I)
FORCE_SQL_PREFIXES = ("sql:", "sql ")
FORBIDDEN_SQL = re.compile(r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|ATTACH|PRAGMA|REINDEX|VACUUM|WITH\s+RECURSIVE)\b", re.I)
DEFAULT_LIMIT = 100
LIMIT_CAP = 200

def _db_path_from_settings() -> str:
    try:
        return settings.DATABASES["default"]["NAME"]
    except Exception:
        return "example.db"  # fallback

def _sanitize_sql(sql_query: str) -> str:
    sql = re.sub(r";.*$", "", (sql_query or "").strip())
    if not SAFE_SQL_PREFIX.match(sql or ""):
        raise ValueError("Seules les requêtes SELECT sont autorisées.")
    if FORBIDDEN_SQL.search(sql):
        raise ValueError("Mots-clés SQL interdits détectés.")
    m = re.search(r"\blimit\s+(\d+)", sql, re.I)
    if m:
        n = min(int(m.group(1)), LIMIT_CAP)
        sql = re.sub(r"\blimit\s+\d+", f"LIMIT {n}", sql, flags=re.I)
    else:
        sql += f" LIMIT {DEFAULT_LIMIT}"
    return sql

def run_sql_query(sql_query: str) -> Tuple[List[tuple], List[str]]:
    sql_query = _sanitize_sql(sql_query)
    db_path = _db_path_from_settings()
    conn = sqlite3.connect(db_path, timeout=3.0)
    try:
        conn.execute("PRAGMA query_only=ON;")
        conn.execute("PRAGMA busy_timeout=2000;")
        cur = conn.cursor()
        cur.execute(sql_query)
        rows = cur.fetchall()
        cols = [c[0] for c in (cur.description or [])]
        return rows, cols
    finally:
        conn.close()

def sqlite_schema_text() -> str:
    db_path = _db_path_from_settings()
    conn = sqlite3.connect(db_path, timeout=3.0)
    try:
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
        tables = [t[0] for t in cur.fetchall()]
        schema = []
        for t in tables:
            cur.execute(f"PRAGMA table_info({t});")
            cols = [row[1] for row in cur.fetchall()]
            cur.execute(f"PRAGMA foreign_key_list({t});")
            fks = [f"{t}.{r[3]} -> {r[2]}.{r[4]}" for r in cur.fetchall()]
            fk_txt = (" | FKs: " + ", ".join(fks)) if fks else ""
            schema.append(f"Table {t} (" + ", ".join(cols) + ")" + fk_txt)
        return "\n".join(schema)
    finally:
        conn.close()

def nl_to_sql(user_question: str, schema_description: str, mistral_key: str) -> str:
    if not mistral_key:
        raise RuntimeError("MISTRAL_API_KEY manquant pour la traduction NL→SQL.")
    url = "https://api.mistral.ai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {mistral_key}", "Content-Type": "application/json"}
    system_prompt = (
        "Tu es un expert SQLite.\n"
        "CONTRAINTES:\n"
        "- Réponds UNIQUEMENT par une requête SQL SQLite valide.\n"
        "- SELECT UNIQUEMENT. INTERDIT: INSERT/UPDATE/DELETE/ATTACH/PRAGMA/CTE récursifs.\n"
        "- Utilise UNIQUEMENT les tables/colonnes listées ci-dessous.\n"
        "- Ajoute TOUJOURS un LIMIT <= 200.\n"
        "- Si la question est ambiguë, choisis l'interprétation la plus simple.\n\n"
        f"Schéma de la base :\n{schema_description}\n"
        "\nExemples:\n"
        "-- Lister produits arrêtés\nSELECT name, form, status FROM Product WHERE status IN ('ARRET','ARRETE','STOP') LIMIT 100\n"
        "-- Produits commercialisés en france\nSELECT DISTINCT p.name, p.form, p.status "
        "FROM Product p JOIN Product_sites ps ON ps.product_id=p.id "
        "JOIN ManufacturingSite s ON s.id=ps.manufacturingsite_id "
        "WHERE p.status IN ('COMMERCIALISE','MARKETED','APPROUVE') AND lower(s.country) LIKE '%france%' LIMIT 100"
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_question},
    ]
    r = requests.post(url, headers=headers, json={"model": os.environ.get("MISTRAL_MODEL", "mistral-small"),
                                                  "messages": messages, "temperature": 0.2},
                      timeout=int(os.environ.get("MISTRAL_TIMEOUT", "12")))
    r.raise_for_status()
    sql = r.json()["choices"][0]["message"]["content"].strip()
    sql = re.sub(r"^```sql\s*|```$", "", sql, flags=re.I).strip()
    return _sanitize_sql(sql)

def rows_to_md(rows: List[tuple], cols: List[str]) -> str:
    dict_rows = [{col: ("" if v is None else v) for col, v in zip(cols, row)} for row in rows]
    return as_md(dict_rows, cols or ["Résultat"], empty_msg="Aucun résultat.")

# =============================
# Generic LLM fallback
# =============================

def call_mistral(question: str, contexte: str, api_key: str) -> str:
    prompt = (
        contexte
        + f"\n\nQuestion utilisateur : {question}\n"
        "Consignes : Réponds uniquement selon les données ci-dessus. "
        "Réponds brièvement, en texte. Utilise un tableau Markdown uniquement si la réponse comporte plusieurs lignes/éléments."
    )
    try:
        r = requests.post(
            "https://api.mistral.ai/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": os.environ.get("MISTRAL_MODEL", "mistral-small"),
                "messages": [
                    {"role": "system", "content": "Tu es un assistant. Si la question porte sur des données, ne réponds que selon le contexte fourni. Réponds brièvement, sans tableau sauf si la réponse est longue."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.4
            },
            timeout=int(os.environ.get("MISTRAL_TIMEOUT", "12"))
        )
        if r.status_code == 200:
            return r.json().get('choices', [{}])[0].get('message', {}).get('content', '').strip() or "Je n'ai pas compris."
        logger.error(f"Erreur Mistral API pour la question '{question}': {r.status_code} - {r.text}")
        return f"Erreur Mistral API : {r.status_code}"
    except requests.RequestException as e:
        logger.warning(f"[LLM] ⚠️ Erreur Mistral : {e!r}")
        return "Je n’ai pas compris. Peux-tu préciser ?"
    except Exception as e:
        logger.exception(f"Erreur dans call_mistral : {str(e)}")
        return "Je n’ai pas compris. Peux-tu préciser ?"

# =============================
# Main view
# =============================

@csrf_exempt
def chatbot_api(request):
    if request.method != 'POST':
        return JsonResponse({'response': 'Méthode non autorisée.'}, status=405)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'response': 'Requête invalide (JSON mal formé).'}, status=400)

    question = (data.get('message') or '').strip()
    q_lower = strip_accents(question.lower())
    page = data.get('page') or 1
    page_size = data.get('page_size') or 50

    # Models
    from client.products.models import Product, ManufacturingSite
    from rawdocs.models import RawDocument
    from submissions.models import Submission

    produits_qs = Product.objects.all().prefetch_related('sites')
    docs_qs = RawDocument.objects.filter(is_validated=True).select_related('owner')
    subs_qs = Submission.objects.all()
    sites_qs = ManufacturingSite.objects.all()

    # Intent
    try:
        question_type = detect_full_intent_type(question)
    except Exception:
        logger.exception("Intent detection crashed, fallback to 'autre'")
        question_type = 'autre'

    # Agent SQL forcé ?
    mistral_key = os.environ.get('MISTRAL_API_KEY')
    force_sql = any(q_lower.startswith(pfx) for pfx in FORCE_SQL_PREFIXES)
    default_sql_for_autre = os.environ.get('ENABLE_SQL_AGENT_DEFAULT') == '1'
    if force_sql or (question_type == 'autre' and default_sql_for_autre):
        try:
            natural = question
            for pfx in FORCE_SQL_PREFIXES:
                if natural.lower().startswith(pfx):
                    natural = natural[len(pfx):].strip()
                    break
            schema = sqlite_schema_text()
            sql_stmt = nl_to_sql(natural, schema, mistral_key)
            rows, cols = run_sql_query(sql_stmt)
            table_md = rows_to_md(rows, cols)
            return JsonResponse({
                "ok": True, "mode": "sql",
                "sql": sql_stmt,
                "data": {"cols": cols, "rows": rows},
                "render": {"markdown": table_md},
                "meta": {"page": 1, "page_size": len(rows), "total": len(rows)},
                "response": table_md,
            })
        except Exception as e:
            logger.exception("Échec agent SQL")
            return JsonResponse({'response': f"Erreur agent SQL : {e}"}, status=400)

    # Parse
    try:
        parsed = parse_request(question, question_type, produits_qs, docs_qs)
    except Exception as e:
        logger.exception(f"parse_request a levé une exception: {e}")
        parsed = {}

    entity = parsed.get('entity')
    mode = parsed.get('mode', 'detail')
    filters = parsed.get('filters', [])
    fields = parsed.get('fields', [])
    title = parsed.get('title')
    name = parsed.get('name')

    # Contexte fallback LLM
    produits_str = ''
    for p in produits_qs:
        sites = p.sites.all()
        sites_str = ', '.join([f"{s.site_name} ({s.city}, {s.country})" for s in sites]) if sites else 'Aucun'
        produits_str += (
            f"- Nom: {clean(p.name)} | Statut: {clean(p.get_status_display())} | "
            f"PA: {clean(getattr(p, 'active_ingredient', None))} | Dosage: {clean(getattr(p, 'dosage', None))} | "
            f"Forme: {clean(getattr(p, 'form', None))} | TA: {clean(getattr(p, 'therapeutic_area', None))} | Sites: {sites_str}\n"
        )

    docs_str = ''
    for d in docs_qs:
        docs_str += (
            f"- {clean(d.title)} | {clean(getattr(d, 'doc_type', ''))} | {clean(getattr(d, 'language', ''))} | Source: {clean(getattr(d, 'source', ''))}\n"
        )

    subs_str = '\n'.join([
        f"- {s.name} ({s.get_status_display()})" for s in subs_qs if hasattr(s, 'get_status_display')
    ])

    contexte = (
        f"Voici un résumé des données:\n\nProduits:\n{produits_str}\nDocuments validés:\n{docs_str}\nSoumissions:\n{subs_str}\n"
    )

    # Raccourcis relationnels
    if question_type == 'prod_to_doc':
        response = get_document_linked_to_product(question, produits_qs)
        return JsonResponse({'response': response, "ok": True, "mode":"relation", "entity":"product→library",
                             "render":{"markdown":response}})
    if question_type == 'doc_to_prod':
        response = get_products_linked_to_document(question, docs_qs)
        return JsonResponse({'response': response, "ok": True, "mode":"relation", "entity":"library→product",
                             "render":{"markdown":response}})

    # Aucun entity → heuristiques simples
    if not entity:
        if re.search(r"\bproduits?\b", q_lower):
            ProductModel = produits_qs.model
            imp_filters = []
            f = _infer_status_filter(q_lower, ProductModel)
            if f: imp_filters.append(f)
            f = _infer_form_filter(q_lower)
            if f: imp_filters.append(f)
            f = _infer_active_ingredient_filter(q_lower)
            if f: imp_filters.append(f)
            f = _infer_dosage_filter(q_lower)
            if f: imp_filters.append(f)
            f = _infer_country_filter_for_products(q_lower)
            if f: imp_filters.append(f)
            payload = list_products(produits_qs, imp_filters, clean, as_md, page, page_size)
            payload["response"] = payload["render"]["markdown"]
            return JsonResponse(payload)
        if re.search(r"\bdocuments?\b", q_lower):
            payload = list_documents(docs_qs, [], clean, format_date, as_md, page, page_size)
            payload["response"] = payload["render"]["markdown"]
            return JsonResponse(payload)
        if re.search(r"\bsites?\b", q_lower):
            site_filters = []
            f = _infer_country_filter_for_sites(q_lower)
            if f: site_filters.append(f)
            payload = list_sites(sites_qs, site_filters, clean, as_md, page, page_size)
            payload["response"] = payload["render"]["markdown"]
            return JsonResponse(payload)
        if os.environ.get('MISTRAL_API_KEY'):
            content = call_mistral(question, contexte, os.environ['MISTRAL_API_KEY'])
            return JsonResponse({'response': content, "ok": True, "mode": "fallback",
                                 "render":{"markdown":content}})
        return JsonResponse({'response': "Je n’ai pas bien compris la demande. Peux-tu préciser ?", "ok": False}, status=200)

    # Entity-specific handling
    if entity == 'library':
        if mode == 'list':
            payload = list_documents(docs_qs, filters, clean, format_date, as_md, page, page_size)
            payload["response"] = payload["render"]["markdown"]
            return JsonResponse(payload)
        else:
            payload = detail_document(docs_qs, fields, title, question, clean, format_date)
            payload["response"] = payload["render"]["markdown"]
            return JsonResponse(payload)

    if entity == 'product':
        if mode == 'list':
            payload = list_products(produits_qs, filters, clean, as_md, page, page_size)
            payload["response"] = payload["render"]["markdown"]
            return JsonResponse(payload)
        else:
            payload = detail_product(produits_qs, fields, name, question, clean)
            payload["response"] = payload["render"]["markdown"]
            return JsonResponse(payload)

    if entity == 'site':
        if mode == 'list':
            payload = list_sites(sites_qs, filters, clean, as_md, page, page_size)
            payload["response"] = payload["render"]["markdown"]
            return JsonResponse(payload)
        else:
            name_hint = parsed.get('site_name') if 'parsed' in locals() else None
            name_hint = name_hint or title or name or question
            s = sites_qs.filter(site_name__icontains=name_hint).first()
            if not s:
                return JsonResponse({'response': 'Site introuvable. Peux-tu préciser le nom ?',
                                     "ok": False, "render":{"markdown":'Site introuvable. Peux-tu préciser le nom ?'}})
            md = f"Nom : {clean(s.site_name)}\nVille : {clean(getattr(s, 'city', ''))}\nPays : {clean(getattr(s, 'country', ''))}"
            return JsonResponse({'response': md, "ok": True, "entity":"site", "mode":"detail", "render":{"markdown": md}})

    # Final fallback
    if os.environ.get('MISTRAL_API_KEY'):
        content = call_mistral(question, contexte, os.environ['MISTRAL_API_KEY'])
        return JsonResponse({'response': content, "ok": True, "mode":"fallback", "render":{"markdown":content}})
    return JsonResponse({'response': "Je n’ai pas bien compris la demande. Peux-tu préciser ?", "ok": False})
