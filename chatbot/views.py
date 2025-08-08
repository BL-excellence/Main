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
from chatbot.utils.matching import find_best_product,find_best_document,extract_product_name



# Configuration du logger
logger = logging.getLogger(__name__)

def strip_accents(s: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFD', s or '') if unicodedata.category(c) != 'Mn')

LIST_WORDS = ("tous", "toutes", "liste", "affiche", "montre", "montrez")  # PAS 'donner'
STOP_TAIL = r"(?:\s+(?:dans|en)\s+(?:la\s+)?base(?:\s+de\s+donn[ée]es)?\b|[?,.;]|$)"

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
}

PROD_FIELD_MAP = {
    "type": "form",
    "forme": "form",
    "statut": "status",                # pour détail; pour les filtres on pourra mapper le texte → code si besoin
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
        return alias.get(v, value)
    return value


def parse_request(question: str, intent: str):
    q = question
    ql = q.lower()

    # 1) list vs detail (sans 'donner')
    wants_list = any(w in ql for w in LIST_WORDS) and ("document" in ql or "documents" in ql or "produit" in ql or "produits" in ql)

    # 2) entity
    entity = "library" if intent == "library" else ("product" if intent == "product" else None)

    # 3) si LISTE → extraire les filtres alias: valeur
    filters = []
    field_map = DOC_FIELD_MAP if entity == "library" else PROD_FIELD_MAP if entity == "product" else {}
    for alias, field in field_map.items():
        if alias in ql:
            m = re.search(
                rf"\b{re.escape(alias)}\b(?:\s+de\s+(?:document|produit))?\s*[:=]?\s*(.+?){STOP_TAIL}",
                q, flags=re.IGNORECASE
            )
            if m:
                value = m.group(1).strip()
                if value:
                    filters.append((field, value))

    # 4) si DÉTAIL → récupérer titre/nom et champs demandés
    fields = []
    title = name = None
    if not wants_list:
        if entity == "library" and re.search(r"\bde\s+document\b", ql):
            title = re.split(r"\bde\s+document\b", q, flags=re.IGNORECASE, maxsplit=1)[1].strip()
            for alias, field in DOC_FIELD_MAP.items():
                if re.search(rf"\b{re.escape(alias)}\b", ql):
                    fields.append(field)
        if entity == "product" and re.search(r"\bde\s+produit\b", ql):
            name = re.split(r"\bde\s+produit\b", q, flags=re.IGNORECASE, maxsplit=1)[1].strip()
            for alias, field in PROD_FIELD_MAP.items():
                if re.search(rf"\b{re.escape(alias)}\b", ql):
                    fields.append(field)

    mode = "list" if wants_list else "detail"
    return {"entity": entity, "mode": mode, "filters": filters, "fields": fields, "title": title, "name": name}

def list_documents(qs, filters, clean, format_date, as_md):
    for field, value in filters:
        q1 = qs.filter(**{f"{field}__iexact": value})
        qs = q1 if q1.exists() else qs.filter(**{f"{field}__icontains": value})
    cols = ["Titre","Type","Langue","Version","Source","Date de publication","Pays"]
    rows = [{
        "Titre": clean(d.title),
        "Type": clean(getattr(d,"doc_type","")),
        "Langue": clean(d.language or ""),
        "Version": clean(d.version or ""),
        "Source": clean(d.source or ""),
        "Date de publication": format_date(d.publication_date),
        "Pays": clean(d.country or ""),
    } for d in qs]
    return as_md(rows, cols)

def detail_document(qs, fields, title_hint, raw_q, clean, format_date):
    doc = find_best_document(title_hint or raw_q, qs)
    if not doc:
        return "Je n’ai pas trouvé ce document. Peux-tu préciser le titre ?"
    if not fields:
        return (
            f"Titre : {clean(doc.title)}\n"
            f"Type : {clean(getattr(doc,'doc_type',''))}\n"
            f"Langue : {clean(getattr(doc,'language',''))}\n"
            f"Version : {clean(getattr(doc,'version',''))}\n"
            f"Source : {clean(getattr(doc,'source',''))}\n"
            f"Date de publication : {format_date(getattr(doc,'publication_date',''))}\n"
            f"Pays : {clean(getattr(doc,'country',''))}"
        )
    parts=[]
    for f in fields:
        val = getattr(doc, f, "")
        if f in ("publication_date","validated_at","created_at"):
            val = format_date(val)
        parts.append(f"{f.replace('_',' ').title()} : {clean(val)}")
    return f"{' ; '.join(parts)} du document « {doc.title} »."

def list_products(qs, filters, clean, as_md):
    for field, value in filters:
        q1 = qs.filter(**{f"{field}__iexact": value})
        qs = q1 if q1.exists() else qs.filter(**{f"{field}__icontains": value})
    cols = ["Nom","Type","Principe actif","Dosage","Statut"]
    rows = [{
        "Nom": clean(p.name),
        "Type": clean(p.form),
        "Principe actif": clean(p.active_ingredient or ""),
        "Dosage": clean(p.dosage or ""),
        "Statut": clean(p.get_status_display()),
    } for p in qs]
    return as_md(rows, cols)

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
    parts=[]
    for f in fields:
        if f=="status":
            val = prod.get_status_display()
        elif f=="sites":
            val = "; ".join(f"{s.site_name} ({s.country})" for s in prod.sites.all()) or "non spécifié"
        else:
            val = getattr(prod, f, "")
        parts.append(f"{f.replace('_',' ').title()} : {clean(val)}")
    return f"{' ; '.join(parts)} du produit « {prod.name} »."

@csrf_exempt
def chatbot_api(request):
    """
    Chatbot avec priorité aux questions 'library' (RawDocument validés) ou 'product' (Product).
    - Utilise Mistral pour détecter si la question concerne un produit ou une bibliothèque.
    - Réponse courte pour un/plusieurs attribut(s) d'un document/produit.
    - Tableau Markdown uniquement pour les listes de documents.
    - Fallback LLM (Mistral) pour les questions non spécifiques.
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
    q_norm = strip_accents(q_lower)

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

    def as_md(rows, cols):
        if not rows:
            return "Aucun document validé."
        head = "| " + " | ".join(cols) + " |"
        sep = "| " + " | ".join(["---"] * len(cols)) + " |"
        lines = [head, sep]
        for r in rows:
            lines.append("| " + " | ".join(r.get(c, "") for c in cols) + " |")
        return "\n".join(lines)

    def _normalize(s: str) -> str:
        return " ".join(re.findall(r"\w+", (s or "").lower()))

    def find_best_doc(query: str, queryset):
        """Trouve un RawDocument validé depuis la question (icontains puis fuzzy)."""
        m = re.search(r"(?:\bde|\bdu|\bdes|d['’])\s+(.+)", query, re.I)
        if m:
            cand = m.group(1).strip(" ?!.,'\"")
            hit = queryset.filter(title__icontains=cand).first()
            if hit:
                return hit
        hit = queryset.filter(title__icontains=query).first()
        if hit:
            return hit
        qn = _normalize(query)
        best, best_score = None, 0.0
        for d in queryset:
            score = difflib.SequenceMatcher(None, qn, _normalize(d.title)).ratio()
            if score > best_score:
                best, best_score = d, score
        return best if best_score >= 0.45 else None  # seuil empirique

    def find_best_product(query: str, queryset):
        # 1. Tentative stricte : cherche tous les mots du query dans le nom
        qn = _normalize(query)

        for p in queryset:
            if all(word in _normalize(p.name) for word in qn.split()):
                return p

        # 2. Tentative simple : name__icontains mot potentiellement utile
        words = qn.split()
        for word in reversed(words):  # Essaye d’abord les derniers mots (ex: "S 9999")
            hit = queryset.filter(name__icontains=word).first()
            if hit:
                return hit

        # 3. Fallback fuzzy
        best, best_score = None, 0.0
        for p in queryset:
            score = difflib.SequenceMatcher(None, qn, _normalize(p.name)).ratio()
            if score > best_score:
                best, best_score = p, score
        return best if best_score >= 0.45 else None
 
        
    
    # ---------- Détection du type de question via Mistral ----------
    from chatbot.utils.intents import detect_full_intent_type
                

    # Vérifier la clé Mistral
    mistral_key = os.environ.get('MISTRAL_API_KEY')
    if not mistral_key:
        logger.error("Clé Mistral manquante")
        return JsonResponse({'response': "Clé Mistral manquante pour la détection."})

    # Détecter le type de question
    question_type = detect_full_intent_type(question)
    logger.info(f"[DEBUG] ➕ Type final utilisé : '{question_type}' pour la question : '{question}'")

    
    from chatbot.utils.relations import get_products_linked_to_document, get_document_linked_to_product
    
    # ... après detection intent & relations ...
    parsed = parse_request(question, question_type)
    logger.debug(f"[PARSED] {parsed}")
    if question_type == "prod_to_doc":
        response = get_document_linked_to_product(question, produits_qs)
        return JsonResponse({'response': response})

    elif question_type == "doc_to_prod":
        response = get_products_linked_to_document(question, docs_qs)
        return JsonResponse({'response': response})

    if parsed["entity"] == "library":
        if parsed["mode"] == "list":
            table = list_documents(docs_qs, parsed["filters"], clean, format_date, as_md)
            return JsonResponse({"response": table})
        else:
            txt = detail_document(docs_qs, parsed["fields"], parsed["title"], question, clean, format_date)
            return JsonResponse({"response": txt})

    elif parsed["entity"] == "product":
        if parsed["mode"] == "list":
            table = list_products(produits_qs, parsed["filters"], clean, as_md)
            return JsonResponse({"response": table})
        else:
            txt = detail_product(produits_qs, parsed["fields"], parsed["name"], question, clean)
            return JsonResponse({"response": txt})   

    # ---------- Fallback: contexte + Mistral ----------
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

    content = call_mistral(question, contexte, mistral_key)
    logger.info(f"Fallback Mistral utilisé pour la question: '{question}' | Réponse: '{content}'")
    return JsonResponse({'response': content})

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