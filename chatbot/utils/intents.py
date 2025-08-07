import requests
import os
import logging

logger = logging.getLogger(__name__)


def fallback_full_intent(question: str) -> str:
        q = question.lower()

        has_doc = any(k in q for k in ["document", "notice", "rapport", "fichier", "titre", "langue"])
        has_prod = any(k in q for k in ["produit", "médicament", "principe actif", "forme", "dosage", "statut"])

        if has_doc and has_prod:
            return "doc_to_prod" if "document" in q else "prod_to_doc"
        if has_doc:
            return "library"
        if has_prod:
            return "product"
        return "autre"

def detect_full_intent_type(question: str) -> str:
        mistral_key = os.getenv("MISTRAL_API_KEY")
        if not mistral_key:
            logger.warning(f"[FALLBACK] Utilisation du fallback local pour : '{question}'")
            return fallback_full_intent(question)

        prompt = f"""
    Tu es un assistant qui classe une question dans une seule des catégories suivantes :

    - library → la question parle d’un document (notice, fichier, rapport, etc.) ou de ses attributs (titre, langue, type…)
    - product → la question parle d’un médicament, produit ou principe actif et ses attributs (forme, dosage…)
    - prod_to_doc → la question demande à quels documents un produit est lié
    - doc_to_prod → la question demande à quels produits un document est lié
    - autre → la question ne concerne ni un produit ni un document

    Tu dois répondre uniquement avec : library, product, prod_to_doc, doc_to_prod, ou autre.

    Q : {question}  
    →
        """

        try:
            r = requests.post(
                "https://api.mistral.ai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {mistral_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "mistral-small",
                    "messages": [
                        {"role": "system", "content": "Tu es un classificateur d'intention. Réponds uniquement avec un mot parmi : library, product, prod_to_doc, doc_to_prod, autre."},
                        {"role": "user", "content": prompt.strip()}
                    ],
                    "temperature": 0.2
                },
                timeout=30
            )
            content = r.json()["choices"][0]["message"]["content"].strip().lower()
            ALLOWED_TYPES = {"library", "product", "prod_to_doc", "doc_to_prod", "autre"}

            if content in ALLOWED_TYPES:
                logger.info(f"[INTENT] ✅ Type détecté par Mistral : '{content}' pour la question : '{question}'")
                return content
            else:
                logger.warning(f"[INTENT] ❌ Type non reconnu par Mistral : '{content}' → Fallback utilisé.")
                return fallback_full_intent(question)

        except Exception as e:
            logger.exception(f"[INTENT] ⚠️ Erreur appel Mistral : {e}")
            return fallback_full_intent(question)
    