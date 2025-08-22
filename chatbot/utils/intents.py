import os
import re
import logging
from functools import lru_cache

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

CATEGORIES = [
    "library",      # questions sur les documents
    "product",      # questions sur les produits
    "site",         # questions sur les sites de fabrication
    "prod_to_doc",  # "<produit> est-il lié à un document ?"
    "doc_to_prod",  # "<document> est-il lié à un produit ?"
    "autre",        # tout le reste
]

REL_WORDS = r"li[eé]|associ[eé]|rattach[eé]|lier|associer|relier"


def _norm(text: str) -> str:
    text = (text or "").lower()
    text = re.sub(r"[\s_]+", " ", text).strip()
    return text


def _local_guess_intent(question: str) -> str:
    """Heuristiques locales quand l'API Mistral est indisponible.
    Rapides et robustes pour les mots-clés FR/EN.
    """
    q = _norm(question)

    # relations produit <-> document
    if re.search(rf"\bproduit\b.*\b({REL_WORDS})\b.*\bdocument\b", q):
        return "prod_to_doc"
    if re.search(rf"\bdocument\b.*\b({REL_WORDS})\b.*\bproduit\b", q):
        return "doc_to_prod"

    # entités simples
    # prioriser les requêtes annotations si mots-clés détectés
    if re.search(r"\b(annotations?|entit[eé]s?|labels?)\b", q):
        return "library"  # on route vers handler library mais interception annotations s'applique
    if re.search(r"\b(documents?|guidances?|guidelines?)\b", q):
        return "library"
    if re.search(r"\b(produits?|products?)\b", q):
        return "product"
    if re.search(r"\b(sites?|usines?|manufacturing\s*sites?)\b", q):
        return "site"

    return "autre"


def _session_with_retries(total: int = 2, backoff: float = 0.5) -> requests.Session:
    """Requests session with urllib3 retries for transient network issues."""
    s = requests.Session()
    retry = Retry(
        total=total,
        backoff_factor=backoff,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["POST", "GET"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    return s


@lru_cache(maxsize=256)
def detect_full_intent_type(question: str) -> str:
    """
    Retourne une des catégories: library | product | site | prod_to_doc | doc_to_prod | autre
    Tente Mistral d'abord (si clé dispo), sinon tombe sur l'heuristique locale.
    Toujours *retourne* une catégorie (ne lève pas d'exception).
    """
    q = (question or "").strip()

    # 1) Désactivation explicite ou clé absente -> heuristique locale
    if os.environ.get("INTENT_USE_MISTRAL", "1") != "1":
        cat = _local_guess_intent(q)
        logger.info(f"[INTENT] (local) → {cat} pour la question : {q!r}")
        return cat

    api_key = os.environ.get("MISTRAL_API_KEY")
    if not api_key:
        cat = _local_guess_intent(q)
        logger.info(f"[INTENT] (no-key local) → {cat} pour la question : {q!r}")
        return cat

    # 2) Appel Mistral avec retries et timeouts
    model = os.environ.get("MISTRAL_MODEL", "mistral-small")
    timeout = int(os.environ.get("MISTRAL_TIMEOUT", "12"))

    system = (
        "Tu catégorises l'intention de l'utilisateur.\n"
        "Réponds *uniquement* par l'une de ces étiquettes, sans ponctuation ni texte additionnel :\n"
        f"{', '.join(CATEGORIES)}\n\n"
        "Règles :\n"
        "- prod_to_doc si la question demande si/un lien du produit vers un document (ex: 'X est-il lié à un document ?').\n"
        "- doc_to_prod si la question demande les produits liés à un document.\n"
        "- library pour les questions sur les documents en général.\n"
        "- product pour les questions sur les produits en général.\n"
        "- site pour les sites de fabrication.\n"
        "- autre sinon.\n"
    )

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": q},
        ],
        "temperature": 0.0,
    }

    try:
        sess = _session_with_retries(total=int(os.environ.get("INTENT_RETRY", "2")), backoff=0.5)
        r = sess.post(
            "https://api.mistral.ai/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=timeout,
        )
        r.raise_for_status()
        txt = r.json()["choices"][0]["message"]["content"].strip().lower()
        # Normalise toute sortie inattendue vers une catégorie valide
        txt = re.sub(r"[^a-z_]+", "", txt)
        cat = txt if txt in CATEGORIES else _local_guess_intent(q)
        logger.info(f"[INTENT] ✅ Type détecté par Mistral : {cat!r} pour la question : {q!r}")
        return cat
    except requests.RequestException as e:
        # Erreurs réseau typiques (ex: WinError 10054 -> reset par l'hôte)
        logger.warning(f"[INTENT] ⚠️ Erreur appel Mistral : {e!r}")
        cat = _local_guess_intent(q)
        logger.info(f"[INTENT] (fallback local) → {cat} pour la question : {q!r}")
        return cat
    except Exception as e:  # défense en profondeur
        logger.exception("[INTENT] ❌ Exception inattendue dans detect_full_intent_type")
        return _local_guess_intent(q)
