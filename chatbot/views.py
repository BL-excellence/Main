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




# Configuration du logger
logger = logging.getLogger(__name__)

def strip_accents(s: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFD', s or '') if unicodedata.category(c) != 'Mn')



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
    

    if question_type == "prod_to_doc":
        logger.info(f"[DEBUG] ➡️ Envoi dans get_document_linked_to_product()")
        response = get_document_linked_to_product(question, produits_qs)
        logger.info(f"[DEBUG] Réponse prod_to_doc : {response}")
        return JsonResponse({'response': response})


    elif question_type == "doc_to_prod":
        response = get_products_linked_to_document(question, docs_qs)
        return JsonResponse({'response': response})


    # ---------- Intent "library/documents" ----------
    # doc_keywords = ("document", "documents", "bibliothèque", "library", "notice", "fichier")
    is_doc_question = question_type == 'library'


    # mots-clés -> (champ RawDocument, label)
    attr_map = {
        "source": ("source", "Source"),
        "autorité": ("source", "Source"),
        "authority": ("source", "Source"),
        "contexte": ("context", "Contexte"),
        "context": ("context", "Contexte"),
        "langue": ("language", "Langue"),
        "language": ("language", "Langue"),
        "version": ("version", "Version"),
        "type": ("doc_type", "Type"),
        "pays": ("country", "Pays"),
        "date": ("publication_date", "Date de publication"),
        "url": ("url_source", "URL"),
        "lien": ("url_source", "URL"),
        "publication": ("publication_date", "Date de publication"),
        "date de publication": ("publication_date", "Date de publication"),
        "ajout": ("created_at", "Date d'ajout"),
        "date d'ajout": ("created_at", "Date d'ajout"),
        "validation": ("validated_at", "Statut de validation"),
        "validé": ("validated_at", "Statut de validation"),
        "statut de validation": ("validated_at", "Statut de validation"),
        "date de validation": ("validated_at", "Statut de validation"),
        "uploadé par": ("owner_username", "Uploadé par (Métadonneur)"),
        "qui a uploadé": ("owner_username", "Uploadé par (Métadonneur)"),
        "métadonneur": ("owner_username", "Uploadé par (Métadonneur)"),
    }

    # Mapping attributs produits
    attr_map_products = {
        "nom": ("name", "Nom du produit"),
        "type": ("form", "Type"),
        "forme": ("form", "Forme"),
        "principe actif": ("active_ingredient", "Principe actif"),
        "dosage": ("dosage", "Dosage"),
        "statut": ("get_status_display", "Statut"),
        "zone thérapeutique": ("therapeutic_area", "Zone thérapeutique"),
        "site": ("sites", "Sites de production"),
    }

    # ---- 1) Liste demandée -> tableau Markdown ----
    if is_doc_question and any(k in q_lower for k in ("liste", "tous", "toutes", "affiche", "montre", "montrez")):
        rows = []
        for d in docs_qs:
            rows.append({
                "Titre": clean(d.title),
                "Type": clean(getattr(d, 'doc_type', '')),
                "Langue": clean(getattr(d, 'language', '')),
                "Version": clean(getattr(d, 'version', '')),
                "Source": clean(getattr(d, 'source', '')),
                "Date de publication": format_date(getattr(d, 'publication_date', '')),
                "Pays": clean(getattr(d, 'country', '')),
            })
        cols = ["Titre", "Type", "Langue", "Version", "Source", "Date de publication", "Pays"]
        response = as_md(rows, cols)
        logger.info(f"Liste de documents retournée pour la question: '{question}'")
        return JsonResponse({"response": response})

    # ---- 2) Question sur un document ----
    if is_doc_question:
        asked_doc_keys = [k for k in attr_map if k in q_lower]
        # Trouver le document
        doc = find_best_doc(question, docs_qs)
        if not doc:
            logger.warning(f"Aucun document trouvé pour la question: '{question}'")
            return JsonResponse({'response': "Je n’ai pas trouvé ce document. Peux-tu préciser le titre ?"})

        # Si la question demande spécifiquement qui a uploadé
        if any(k in q_lower for k in ("uploadé par", "qui a uploadé", "métadonneur")):
            owner = getattr(getattr(doc, "owner", None), "username", "non spécifié")
            response = f"Uploadé par : {clean(owner)}"
            logger.info(f"Réponse pour métadonneur: '{response}' | Document: '{doc.title}'")
            return JsonResponse({'response': response})

        # Construire la liste (champ,label) sans doublons pour d'autres attributs
        asked_fields = []
        seen = set()
        for k in asked_doc_keys:
            field, label = attr_map[k]
            if field not in seen and field != "owner_username":
                asked_fields.append((field, label))
                seen.add(field)

        # Si aucun attribut n'est explicitement demandé -> fiche courte
        if not asked_fields:
            txt = (
                f"Titre : {clean(doc.title)}\n"
                f"Type : {clean(getattr(doc, 'doc_type', ''))}\n"
                f"Langue : {clean(getattr(doc, 'language', ''))}\n"
                f"Version : {clean(getattr(doc, 'version', ''))}\n"
                f"Source : {clean(getattr(doc, 'source', ''))}\n"
                f"Date de publication : {format_date(getattr(doc, 'publication_date', ''))}\n"
                f"Date d'ajout : {format_date(getattr(doc, 'created_at', ''))}\n"
                f"Date de validation : {format_date(getattr(doc, 'validated_at', ''))}\n"
                f"Pays : {clean(getattr(doc, 'country', ''))}\n"
                f"Uploadé par : {clean(getattr(getattr(doc, 'owner', None), 'username', None))}\n"
                f"URL : {clean(getattr(doc, 'url_source', ''))}"
            )
            logger.info(f"Fiche courte retournée pour le document: '{doc.title}'")
            return JsonResponse({'response': txt})

        # Normalisation simple des sources (EMA/FDA)
        def normalize_source(val: str) -> str:
            v = (val or "").strip().lower()
            if v in {"european medicines agency", "agence européenne des médicaments", "ema"}:
                return "EMA"
            if v in {"food and drug administration", "u.s. food and drug administration", "fda"}:
                return "FDA"
            return val or "non spécifié"

        parts = []
        for field, label in asked_fields:
            if field == "owner_username":
                value = getattr(getattr(doc, "owner", None), "username", None)
                value = clean(value)
            else:
                value = getattr(doc, field, "")
                if field in ("publication_date", "validated_at", "created_at"):
                    value = format_date(value)
                else:
                    value = clean(value)
            parts.append(f"{label} : {value}")

        response = f"{' ; '.join(parts)} du document « {doc.title} »."
        logger.info(f"Attributs retournés: '{response}' | Document: '{doc.title}'")
        return JsonResponse({'response': response})

    # ---- 3) Question sur un produit ----
    # product_keywords = ("produit", "principe actif", "forme", "dosage", "zone thérapeutique", "site", "statut")
    is_product_question = question_type == 'product'

    if is_product_question:
        asked_product_keys = [k for k in attr_map_products if k in q_lower]
        prod = find_best_product(question, produits_qs)
        if not prod:
            logger.warning(f"Aucun produit trouvé pour la question: '{question}'")
            return JsonResponse({'response': "Je n’ai pas trouvé ce produit. Peux-tu préciser le nom ?"})

        parts = []
        seen = set()
        for k in asked_product_keys:
            field, label = attr_map_products[k]
            if field not in seen:
                if field == "sites":
                    sites = prod.sites.all()
                    value = ', '.join([f"{s.site_name} ({s.city}, {s.country})" for s in sites]) if sites else "non spécifié"
                elif field == "get_status_display":
                    value = prod.get_status_display()
                else:
                    value = getattr(prod, field, "")
                parts.append(f"{label} : {clean(value)}")
                seen.add(field)

        # Si aucun attribut demandé → fiche courte
        if not parts:
            txt = (
                f"Nom du produit : {clean(prod.name)}\n"
                f"Type : {clean(getattr(prod, 'form', ''))}\n"
                f"Principe actif : {clean(getattr(prod, 'active_ingredient', ''))}\n"
                f"Dosage : {clean(getattr(prod, 'dosage', ''))}\n"
                f"Statut : {clean(prod.get_status_display())}\n"
                f"Zone thérapeutique : {clean(getattr(prod, 'therapeutic_area', ''))}\n"
            )
            sites = prod.sites.all()
            if sites:
                txt += f"Sites : " + ', '.join([f"{s.site_name} ({s.city}, {s.country})" for s in sites])
            logger.info(f"Fiche courte retournée pour le produit: '{prod.name}'")
            return JsonResponse({'response': txt})

        response = f"{' ; '.join(parts)} du produit « {prod.name} »."
        logger.info(f"Attributs retournés: '{response}' | Produit: '{prod.name}'")
        return JsonResponse({'response': response})

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