from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json
import os
import re
import difflib
import datetime
import unicodedata
import logging
import requests
from chatbot.utils.matching import find_best_product, find_best_document  # extract_product_name supprimé car non utilisé

# Configuration du logger
logger = logging.getLogger(__name__)

def strip_accents(s: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFD', s or '') if unicodedata.category(c) != 'Mn')

# Une seule définition globale
LIST_WORDS = ("tous", "toutes", "liste", "affiche", "afficher", "montre", "montrez", "voir", "lister")

DOC_FIELD_MAP = {
    "type": "doc_type",
    "source": "source",
    "autorité": "source",
    "authority": "source",
    "langue": "language",
    "language": "language",
    "version": "version",
    "pays": "country",
    "date de publication": "publication_date",
    "publication": "publication_date",
    "date": "publication_date",
    "url": "url_source",
    "lien": "url_source",
    "uploadé par": "owner_username",
    "qui a uploadé": "owner_username",
    "métadonneur": "owner_username",
}

PROD_FIELD_MAP = {
    "type": "form",
    "forme": "form",
    "statut": "status",
    "principe actif": "active_ingredient",
    "dosage": "dosage",
    "nom": "name",
}

def normalize_filter_value(field: str, value: str) -> str:
    v = strip_accents((value or "")).lower().strip()
    if field == "source":
        if v in {"fda", "food and drug administration", "u.s. food and drug administration"}:
            return "Food and Drug Administration"
        if v in {"ema", "european medicines agency", "agence europeenne des medicaments"}:
            return "European Medicines Agency"
    if field == "doc_type":
        alias = {"guidelines": "guideline", "guidline": "guideline", "guidance": "guideline"}
        return alias.get(v, v)  # renvoie la valeur normalisée

    return value


from rapidfuzz import process, fuzz

QUOTES_RE = r"[\"'«»“”‘’]"

def _extract_quoted(text: str) -> list[str]:
    # Récupère tout ce qui est entre guillemets simples/doubles/chevrons
    return re.findall(rf"{QUOTES_RE}([^\"'«»“”‘’]+){QUOTES_RE}", text)

def _guess_fields(q_lower: str, alias_map: dict, threshold: int = 85) -> list[str]:
    # alias_map: {"type": "doc_type", ...}
    fields = set()
    aliases = list(alias_map.keys())
    # On prend les tokens du message, + ngrams simples
    candidates = re.findall(r"\w{3,}", q_lower)
    # Ajoute aussi les bigrams/trigrams fréquents
    for n in (2, 3):
        for i in range(len(candidates) - n + 1):
            candidates.append(" ".join(candidates[i:i+n]))
    # Fuzzy matching alias ←→ candidats
    for cand in set(candidates):
        match = process.extractOne(cand, aliases, scorer=fuzz.token_set_ratio)
        if match and match[1] >= threshold:
            fields.add(alias_map[match[0]])
    return list(fields)

def _best_entity_for_name(name_hint: str, produits_qs, docs_qs):
    # Score du candidat contre produits et documents → choisit l’entité la + probable
    if not name_hint:
        return None, None
    best_prod = find_best_product(name_hint, produits_qs)
    best_doc  = find_best_document(name_hint, docs_qs)

    def _sim(a, b):
        if not a or not b:
            return 0.0
        return difflib.SequenceMatcher(None, str(a).lower(), str(b).lower()).ratio()

    sp = _sim(name_hint, getattr(best_prod, "name", ""))
    sd = _sim(name_hint, getattr(best_doc, "title", ""))
    if sp == 0 and sd == 0:
        return None, None
    return ("product", best_prod) if sp >= sd else ("library", best_doc)

# --- à placer avec les helpers, après _best_entity_for_name par ex. ---

# alias de déclencheurs "champ" → clé canonique (avant passage par DOC_FIELD_MAP/PROD_FIELD_MAP)
DOC_TRIGGER_MAP = {
    "type": "doc_type",
    "langue": "language",
    "source": "source",
    "pays": "country",
    "version": "version",
}
PROD_TRIGGER_MAP = {
    "type": "form", "forme": "form",
    "statut": "status",
    "principe actif": "active_ingredient", "pa": "active_ingredient",
    "dosage": "dosage",
}

# quelques patrons simples: "de type X", "type: X", "langue fr", "source EMA", ...
_QUOTED_VAL = r"['\"«»“”‘’]?([^'\"«»“”‘’;,]+)['\"«»“”‘’]?"
DOC_FILTER_PATTERNS = [
    (re.compile(rf"(?:de|du|d’|d')\s*type\s+{_QUOTED_VAL}", re.I), "type"),
    (re.compile(rf"type\s*[:=]\s*{_QUOTED_VAL}", re.I), "type"),
    (re.compile(rf"(?:en|de)\s*langue\s+{_QUOTED_VAL}", re.I), "langue"),
    (re.compile(rf"langue\s*[:=]\s*{_QUOTED_VAL}", re.I), "langue"),
    (re.compile(rf"(?:de|la)\s*source\s+{_QUOTED_VAL}", re.I), "source"),
    (re.compile(rf"source\s*[:=]\s*{_QUOTED_VAL}", re.I), "source"),
    (re.compile(rf"(?:au|du|de)\s*pays\s+{_QUOTED_VAL}", re.I), "pays"),
    (re.compile(rf"pays\s*[:=]\s*{_QUOTED_VAL}", re.I), "pays"),
    (re.compile(rf"(?:en|de)\s*version\s+{_QUOTED_VAL}", re.I), "version"),
    (re.compile(rf"version\s*[:=]\s*{_QUOTED_VAL}", re.I), "version"),
]

PROD_FILTER_PATTERNS = [
    (re.compile(rf"(?:de|du|d’|d')\s*(?:type|forme)\s+{_QUOTED_VAL}", re.I), "type"),
    (re.compile(rf"(?:type|forme)\s*[:=]\s*{_QUOTED_VAL}", re.I), "type"),
    (re.compile(rf"statut\s*[:=]?\s*{_QUOTED_VAL}", re.I), "statut"),
    (re.compile(rf"(?:principe\s+actif|pa)\s*[:=]?\s*{_QUOTED_VAL}", re.I), "principe actif"),
    (re.compile(rf"dosage\s*[:=]?\s*{_QUOTED_VAL}", re.I), "dosage"),
]

def _extract_filters(q: str, entity: str):
    """Retourne une liste [(field, value)] selon l'entité."""
    filters = []
    text = q or ""
    patterns = DOC_FILTER_PATTERNS if entity == "library" else PROD_FILTER_PATTERNS
    trigger_map = DOC_TRIGGER_MAP if entity == "library" else PROD_TRIGGER_MAP

    for rgx, key in patterns:
        m = rgx.search(text)
        if not m:
            continue
        raw_val = (m.group(1) or "").strip()
        # mappe le "key" déclencheur vers le champ canonique de l'entité
        field = trigger_map[key]
        filters.append((field, raw_val))

    return filters


def parse_request(question: str, intent: str, produits_qs, docs_qs):
    q = question or ""
    ql = q.lower()

    wants_list = any(w in ql for w in LIST_WORDS)
    fields_doc = _guess_fields(ql, DOC_FIELD_MAP)
    fields_prod = _guess_fields(ql, PROD_FIELD_MAP)

    quoted_candidates = _extract_quoted(q)
    name_or_title_hint = quoted_candidates[0].strip() if quoted_candidates else None
    if not name_or_title_hint:
        m = re.search(r"(?:de|du|des|la|le|l[’'])\s+(.+?)(?:\?|\.|,|;|$)", q, flags=re.IGNORECASE)
        if m:
            name_or_title_hint = m.group(1).strip()

    entity = None
    if fields_doc and not fields_prod:
        entity = "library"
    elif fields_prod and not fields_doc:
        entity = "product"
    else:
        entity, _ = _best_entity_for_name(name_or_title_hint, produits_qs, docs_qs)

    if not entity:
        entity = "library" if intent == "library" else "product" if intent == "product" else None

    # 🔴 ICI: on construit les FILTRES
    filters = _extract_filters(q, entity) if entity else []

    fields = fields_doc if entity == "library" else fields_prod if entity == "product" else []
    title = name = None
    if entity == "library":
        title = name_or_title_hint
    elif entity == "product":
        name = name_or_title_hint

    mode = "list" if wants_list else "detail"
    return {"entity": entity, "mode": mode, "filters": filters, "fields": fields, "title": title, "name": name}


def list_documents(qs, filters, clean, format_date, as_md):
    for field, value in filters:
        normalized_value = normalize_filter_value(field, value)
        q1 = qs.filter(**{f"{field}__iexact": normalized_value})
        qs = q1 if q1.exists() else qs.filter(**{f"{field}__icontains": normalized_value})
    cols = ["Titre", "Type", "Langue", "Version", "Source", "Date de publication", "Pays"]
    rows = [{
        "Titre": clean(d.title),
        "Type": clean(getattr(d, "doc_type", "")),
        "Langue": clean(d.language or ""),
        "Version": clean(d.version or ""),
        "Source": clean(d.source or ""),
        "Date de publication": format_date(d.publication_date),
        "Pays": clean(d.country or ""),
    } for d in qs]
    return as_md(rows, cols, empty_msg="Aucun document validé.")

def detail_document(qs, fields, title_hint, raw_q, clean, format_date):
    doc = find_best_document(title_hint or raw_q, qs)
    if not doc:
        return "Je n’ai pas trouvé ce document. Peux-tu préciser le titre ?"
    if not fields:
        return (
            f"Titre : {clean(doc.title)}\n"
            f"Type : {clean(getattr(doc, 'doc_type', ''))}\n"
            f"Langue : {clean(getattr(doc, 'language', ''))}\n"
            f"Version : {clean(getattr(doc, 'version', ''))}\n"
            f"Source : {clean(getattr(doc, 'source', ''))}\n"
            f"Date de publication : {format_date(getattr(doc, 'publication_date', ''))}\n"
            f"Pays : {clean(getattr(doc, 'country', ''))}\n"
            f"Uploadé par : {clean(getattr(getattr(doc, 'owner', None), 'username', 'non spécifié'))}"
        )
    parts = []
    for f in fields:
        if f == "owner_username":
            val = getattr(getattr(doc, "owner", None), "username", "non spécifié")
        else:
            val = getattr(doc, f, "")
            if f in ("publication_date", "validated_at", "created_at"):
                val = format_date(val)
        parts.append(f"{f.replace('_', ' ').title()} : {clean(val)}")
    return f"{' ; '.join(parts)} du document « {doc.title} »."

def list_products(qs, filters, clean, as_md):
    for field, value in filters:
        normalized_value = normalize_filter_value(field, value)
        q1 = qs.filter(**{f"{field}__iexact": normalized_value})
        qs = q1 if q1.exists() else qs.filter(**{f"{field}__icontains": normalized_value})
    cols = ["Nom", "Type", "Principe actif", "Dosage", "Statut"]
    rows = [{
        "Nom": clean(p.name),
        "Type": clean(p.form),
        "Principe actif": clean(p.active_ingredient or ""),
        "Dosage": clean(p.dosage or ""),
        "Statut": clean(p.get_status_display()),
    } for p in qs]
    return as_md(rows, cols, empty_msg="Aucun produit trouvé.")

def detail_product(qs, fields, name_hint, raw_q, clean):
    prod = find_best_product(name_hint or raw_q, qs)
    if not prod:
        return "Je n’ai pas trouvé ce produit. Peux-tu préciser le nom ?"
    if not fields:
        return (
            f"Nom : {clean(prod.name)}\n"
            f"Type : {clean(prod.form)}\n"
            f"Principe actif : {clean(prod.active_ingredient)}\n"
            f"Dosage : {clean(prod.dosage)}\n"
            f"Statut : {clean(prod.get_status_display())}"
        )
    parts = []
    for f in fields:
        if f == "status":
            val = prod.get_status_display()
        elif f == "sites":
            val = "; ".join(f"{s.site_name} ({s.country})" for s in prod.sites.all()) or "non spécifié"
        else:
            val = getattr(prod, f, "")
        parts.append(f"{f.replace('_', ' ').title()} : {clean(val)}")
    return f"{' ; '.join(parts)} du produit « {prod.name} »."

def as_md(rows, cols, empty_msg="Aucun résultat."):
    if not rows:
        return empty_msg
    head = "| " + " | ".join(cols) + " |"
    sep = "| " + " | ".join(["---"] * len(cols)) + " |"
    lines = [head, sep]
    for r in rows:
        lines.append("| " + " | ".join(r.get(c, "") for c in cols) + " |")
    return "\n".join(lines)

@csrf_exempt
def chatbot_api(request):
    """
    Chatbot avec priorité aux questions 'library' (RawDocument validés) ou 'product' (Product).
    - Utilise Mistral pour détecter si la question concerne un produit ou une bibliothèque (si clé dispo).
    - Réponse courte pour un/plusieurs attribut(s) d'un document/produit.
    - Tableau Markdown uniquement pour les listes.
    - Fallback LLM (Mistral) quand nécessaire.
    - Logs pour vérifier la détection du type de question.
    """
    if request.method != 'POST':
        return JsonResponse({'response': 'Méthode non autorisée.'}, status=405)

    # ---------- Lecture JSON ----------
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'response': 'Requête invalide (JSON mal formé).'}, status=400)

    question = (data.get('message') or '').strip()
    q_lower = question.lower()

    # ---------- Imports modèles ----------
    from client.products.models import Product
    from rawdocs.models import RawDocument
    from submissions.models import Submission

    produits_qs = Product.objects.all()
    docs_qs = RawDocument.objects.filter(is_validated=True).select_related('owner')
    subs_qs = Submission.objects.all()

    # ---------- Helpers ----------
    def clean(v):
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

    # ---------- Détection du type de question ----------
    from chatbot.utils.intents import detect_full_intent_type

    mistral_key = os.environ.get('MISTRAL_API_KEY')
    if not mistral_key:
        logger.warning("Clé Mistral manquante – fallback règles.")
        has_doc = bool(_guess_fields(q_lower, DOC_FIELD_MAP))
        has_prod = bool(_guess_fields(q_lower, PROD_FIELD_MAP))
        if has_doc and not has_prod:
            question_type = "library"
        elif has_prod and not has_doc:
            question_type = "product"
        else:
            question_type = "autre"
    else:
        question_type = detect_full_intent_type(question)

    logger.info(f"[DEBUG] ➕ Type final utilisé : '{question_type}' pour la question : '{question}'")

    from chatbot.utils.relations import get_products_linked_to_document, get_document_linked_to_product

    # ... parse de la requête (plus robuste)
    parsed = parse_request(question, question_type, produits_qs, docs_qs)
    logger.debug(f"[PARSED] {parsed}")

    # --- Relations explicites ---
    if question_type == "prod_to_doc":
        response = get_document_linked_to_product(question, produits_qs)
        return JsonResponse({'response': response})

    if question_type == "doc_to_prod":
        response = get_products_linked_to_document(question, docs_qs)
        return JsonResponse({'response': response})

    # --- Réponses directes ---
    if parsed["entity"] == "library":
        if parsed["mode"] == "list":
            table = list_documents(docs_qs, parsed["filters"], clean, format_date, as_md)
            return JsonResponse({"response": table})
        else:
            txt = detail_document(docs_qs, parsed["fields"], parsed["title"], question, clean, format_date)
            return JsonResponse({"response": txt})

    if parsed["entity"] == "product":
        if parsed["mode"] == "list":
            table = list_products(produits_qs, parsed["filters"], clean, as_md)
            return JsonResponse({"response": table})
        else:
            txt = detail_product(produits_qs, parsed["fields"], parsed["name"], question, clean)
            return JsonResponse({"response": txt})

    # ---------- Fallback: contexte + (Mistral si dispo) ----------
    produits_str = ''
    for p in produits_qs:
        sites = p.sites.all()
        sites_str = ', '.join([f"{s.site_name} ({s.city}, {s.country})" for s in sites]) if sites else 'Aucun'
        produits_str += (
            f"- Nom: {clean(p.name)} | Statut: {clean(p.get_status_display())} | "
            f"PA: {clean(getattr(p, 'active_ingredient', None))} | "
            f"Dosage: {clean(getattr(p, 'dosage', None))} | "
            f"Forme: {clean(getattr(p, 'form', None))} | "
            f"TA: {clean(getattr(p, 'therapeutic_area', None))} | "
            f"Sites: {sites_str}\n"
        )

    docs_str = ''
    for d in docs_qs:
        docs_str += (
            f"- {clean(d.title)} | {clean(getattr(d, 'doc_type', ''))} | "
            f"{clean(getattr(d, 'language', ''))} | Source: {clean(getattr(d, 'source', ''))}\n"
        )

    subs_str = '\n'.join([
        f"- {s.name} ({s.get_status_display()})" for s in subs_qs if hasattr(s, 'get_status_display')
    ])

    contexte = (
        f"Voici un résumé des données:\n\n"
        f"Produits:\n{produits_str}\n"
        f"Documents validés:\n{docs_str}\n"
        f"Soumissions:\n{subs_str}\n"
    )

    if mistral_key:
        content = call_mistral(question, contexte, mistral_key)
        logger.info(f"Fallback Mistral utilisé pour la question: '{question}' | Réponse: '{content}'")
        return JsonResponse({'response': content})
    else:
        # Dernier filet sans LLM
        logger.info("Pas de clé Mistral et pas d'entité claire → réponse générique.")
        return JsonResponse({'response': "Je n’ai pas bien compris la demande. Peux-tu préciser le nom du document ou du produit, ou les informations souhaitées ?"})


def call_mistral(question: str, contexte: str, api_key: str) -> str:
    prompt = (
        contexte
        + f"\n\nQuestion utilisateur : {question}\n"
        "Consignes : Réponds uniquement selon les données ci-dessus. "
        "Réponds brièvement, en texte. Utilise un tableau Markdown "
        "uniquement si la réponse comporte plusieurs lignes/éléments."
    )
    try:
        r = requests.post(
            "https://api.mistral.ai/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": "mistral-small",
                "messages": [
                    {"role": "system",
                     "content": "Tu es un assistant. Si la question porte sur des données, ne réponds que selon le contexte fourni. "
                                "Réponds brièvement, sans tableau sauf si la réponse est longue."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.4
            },
            timeout=60
        )
        if r.status_code == 200:
            return r.json().get('choices', [{}])[0].get('message', {}).get('content', '').strip() or "Je n'ai pas compris."
        logger.error(f"Erreur Mistral API pour la question '{question}': {r.status_code} - {r.text}")
        return f"Erreur Mistral API : {r.status_code} - {r.text}"
    except Exception as e:
        logger.exception(f"Erreur dans call_mistral pour la question '{question}': {str(e)}")
        return f"Erreur dans l'appel à Mistral : {str(e)}"
