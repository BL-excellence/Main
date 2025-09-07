# rawdocs/groq_annotation_system.py

import os
import re
import json
import time
import random
import hashlib
import requests
from typing import List, Dict, Any, Optional
from datetime import datetime

from django.conf import settings


class GroqAnnotator:
    """
    Intégration GROQ (API OpenAI-compatible) pour l'annotation réglementaire.
    - Modèle par défaut : llama-3.3-70b-versatile
    - Gestion robuste des erreurs (401, 429, 500)
    - Fallback silencieux si API indisponible
    """

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        # Configuration de l'API
        self.api_url = getattr(settings, "GROQ_API_URL", "https://api.groq.com/openai/v1/chat/completions")
        self.model = model or getattr(settings, "GROQ_MODEL", os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"))
        self.api_key = api_key or getattr(settings, "GROQ_API_KEY", os.getenv("GROQ_API_KEY", ""))

        # État de l'annotateur
        self.enabled = bool(self.api_key)
        self.last_schema: List[Dict[str, str]] = []
        self._api_healthy = None  # Cache du statut API

        if self.enabled:
            print("🔍 Analyseur réglementaire GROQ initialisé")
            try:
                self._test_connection()
            except Exception as e:
                print(f"⚠️ Test GROQ échoué: {e}")
        else:
            print("ℹ️ GROQ désactivé (clé API absente)")

    # ============================================================================
    # API PRINCIPALES UTILISÉES DANS LE PROJET
    # ============================================================================

    def complete_text(
            self,
            prompt: str,
            max_tokens: int = 800,
            temperature: float = 0.1,
            model: Optional[str] = None,
            system: Optional[str] = "You are a helpful assistant.",
            json_mode: bool = False,
            timeout: int = 120
    ) -> Optional[str]:
        """
        Complétion de texte avec gestion d'erreur robuste.

        Args:
            prompt: Texte d'entrée
            max_tokens: Limite de tokens de réponse
            temperature: Créativité (0.0 = déterministe)
            model: Modèle à utiliser (optionnel)
            system: Message système
            json_mode: Force le format JSON si supporté
            timeout: Timeout en secondes

        Returns:
            Texte de réponse ou None si erreur/indisponible
        """
        if not self.enabled:
            return None

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt}
        ]

        return self._chat(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=json_mode,
            timeout=timeout
        )

    def chat_json(
            self,
            system: str,
            user: str,
            model: Optional[str] = None,
            temperature: float = 0.1,
            max_tokens: int = 400,
    ) -> Optional[str]:
        """
        Chat avec format JSON forcé.
        Utilisé par certains modules du projet.
        """
        if not self.enabled:
            return None

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user}
        ]

        return self._chat(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=True
        )

    # Alias pour compatibilité
    complete_json = chat_json
    ask_json = chat_json

    def check_api_health(self) -> bool:
        """
        Vérification rapide du statut de l'API GROQ.
        Utilise un cache pour éviter les appels répétés.
        """
        if not self.enabled:
            return False

        if self._api_healthy is not None:
            return self._api_healthy

        try:
            test_response = self.complete_text("test", max_tokens=5, timeout=10)
            self._api_healthy = bool(test_response)
            return self._api_healthy
        except Exception as e:
            print(f"⚠️ API GROQ indisponible: {e}")
            self._api_healthy = False
            return False

    def annotate_page_with_groq(self, page_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Annotation d'une page avec GROQ.

        Args:
            page_data: {'page_num': int, 'text': str, 'char_count': int, ...}

        Returns:
            Liste d'annotations au format:
            [
                {
                    "text": "texte_extrait",
                    "type": "TypeEntite",
                    "start_pos": int,
                    "end_pos": int,
                    "confidence": float,
                    "reasoning": "explication",
                    "page_num": int,
                    "source": "groq_llama3.3_70b"
                },
                ...
            ]

        Side Effect:
            Met à jour self.last_schema avec les types détectés
        """
        text = (page_data or {}).get("text", "").strip()
        page_num = int((page_data or {}).get("page_num", 1))

        # Réinitialiser le schéma
        self.last_schema = []

        # Vérifications préalables
        if len(text) < 50:
            print(f"⚠️ Texte trop court page {page_num} ({len(text)} chars)")
            return []

        if not self.enabled:
            print("ℹ️ GROQ désactivé - pas d'annotation")
            return []

        # Vérifier la santé de l'API avant traitement
        if not self.check_api_health():
            print("❌ API GROQ indisponible - annotation impossible")
            return []

        # Limiter la taille pour éviter les dépassements de tokens
        max_chars = 10000
        text_truncated = text[:max_chars]

        print(f"🧠 Processing page {page_num} with GROQ - model={self.model}")

        try:
            # Étape 1: Analyse et suggestion de types d'entités
            suggested_types = self._analyze_content_for_types(text_truncated)

            # Étape 2: Extraction des entités
            annotations = self._extract_entities(text_truncated, suggested_types, page_num)

            # Étape 3: Construction du schéma
            self._build_schema(suggested_types, annotations)

            return annotations

        except Exception as e:
            print(f"❌ Erreur annotation GROQ page {page_num}: {e}")
            return []

    def generate_summary(self, pdf_data: Dict[str, Any], annotations: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Génère un résumé statistique du traitement.
        """
        type_counts = {}
        confidence_scores = []

        for ann in annotations or []:
            ann_type = ann.get("type", "unknown")
            type_counts[ann_type] = type_counts.get(ann_type, 0) + 1

            try:
                confidence_scores.append(float(ann.get("confidence", 0.5)))
            except (ValueError, TypeError):
                confidence_scores.append(0.5)

        avg_confidence = sum(confidence_scores) / len(confidence_scores) if confidence_scores else 0.0
        high_confidence_count = len([c for c in confidence_scores if c >= 0.8])

        # Calcul du grade de qualité
        if avg_confidence > 0.85:
            quality_grade = 'A'
        elif avg_confidence > 0.75:
            quality_grade = 'B+'
        else:
            quality_grade = 'B'

        return {
            'total_pages': int(pdf_data.get('total_pages', 0) or 0),
            'total_annotations': len(annotations or []),
            'annotation_breakdown': type_counts,
            'average_confidence': round(avg_confidence, 3),
            'high_confidence_annotations': high_confidence_count,
            'processing_model': self.model,
            'cost': 0.0,  # GROQ facturé séparément
            'quality_grade': quality_grade
        }

    # ============================================================================
    # MÉTHODES INTERNES
    # ============================================================================

    def _test_connection(self) -> bool:
        """Test de connexion non bloquant."""
        if not self.enabled:
            return False

        try:
            messages = [
                {"role": "system", "content": "You are a connection tester."},
                {"role": "user", "content": "ping"}
            ]
            response = self._chat(messages, max_tokens=5, temperature=0.0, timeout=15)

            if response:
                print("✅ GROQ API connectée avec succès")
                self._api_healthy = True
                return True
            else:
                print("⚠️ Connexion GROQ non confirmée")
                self._api_healthy = False
                return False

        except Exception as e:
            print(f"❌ Erreur connexion GROQ: {e}")
            self._api_healthy = False
            return False

    def _chat(
            self,
            messages: List[Dict[str, str]],
            model: Optional[str] = None,
            temperature: float = 0.1,
            max_tokens: int = 800,
            json_mode: bool = False,
            timeout: int = 120
    ) -> Optional[str]:
        """
        Méthode de base pour communiquer avec l'API GROQ.
        Gère les erreurs 401, 429, 500 et les retries.
        """
        if not self.enabled:
            return None

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": model or self.model,
            "messages": messages,
            "temperature": float(temperature),
            "max_tokens": int(max_tokens),
            "top_p": 0.9
        }

        # Format JSON si demandé et supporté
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        try:
            response = requests.post(
                self.api_url,
                headers=headers,
                json=payload,
                timeout=timeout
            )

            # Gestion des codes de statut
            if response.status_code == 200:
                try:
                    result = response.json()
                    return result["choices"][0]["message"]["content"]
                except (KeyError, IndexError, json.JSONDecodeError) as e:
                    print(f"⚠️ Format réponse GROQ inattendu: {e}")
                    return None

            elif response.status_code == 401:
                print("❌ Erreur API GROQ 401 (clé invalide ou expirée)")
                self.enabled = False  # Désactiver pour éviter les tentatives répétées
                self._api_healthy = False
                return None

            elif response.status_code == 429:
                print("⚠️ Rate limit GROQ - attente 60s puis retry")
                time.sleep(60)
                return self._chat(messages, model, temperature, max_tokens, json_mode, timeout)

            elif response.status_code >= 500:
                print(f"❌ Erreur serveur GROQ {response.status_code}")
                self._api_healthy = False
                return None

            else:
                error_text = response.text[:1000]
                print(f"❌ Erreur API GROQ {response.status_code}: {error_text}")
                return None

        except requests.exceptions.Timeout:
            print(f"⏱️ Timeout GROQ après {timeout}s")
            return None
        except requests.exceptions.ConnectionError:
            print("❌ Erreur de connexion GROQ")
            self._api_healthy = False
            return None
        except requests.RequestException as e:
            print(f"❌ Erreur réseau GROQ: {e}")
            return None

    def _analyze_content_for_types(self, text: str) -> List[str]:
        """
        Première étape: analyser le contenu pour suggérer des types d'entités pertinents.
        """
        prompt = f"""Analyze this regulatory/pharmaceutical document text and suggest 5-10 entity types that would capture the key information actually present in the text.

Text sample:
{text[:1500]}

Focus only on information types that are clearly present in this specific text, not generic pharmaceutical categories.

Return JSON format: {{"suggested_types": ["Type1", "Type2", ...]}}"""

        try:
            response = self.complete_text(
                prompt=prompt,
                max_tokens=300,
                temperature=0.1,
                json_mode=True,
                system="You are an expert document analyst. Only suggest entity types for information that actually exists in the provided text."
            )

            if not response:
                return []

            data = self._extract_json_from_text(response)
            if isinstance(data, dict) and "suggested_types" in data:
                types = data["suggested_types"]
                if isinstance(types, list):
                    # Nettoyer et dédupliquer
                    clean_types = []
                    seen = set()
                    for t in types:
                        if isinstance(t, str) and t.strip():
                            clean_type = t.strip()
                            if clean_type.lower() not in seen:
                                seen.add(clean_type.lower())
                                clean_types.append(clean_type)
                    return clean_types[:10]  # Limiter à 10 types max

            return []

        except Exception as e:
            print(f"⚠️ Erreur analyse des types: {e}")
            return []

    def _extract_entities(self, text: str, suggested_types: List[str], page_num: int) -> List[Dict[str, Any]]:
        """
        Deuxième étape: extraction des entités basée sur les types suggérés.
        """
        if suggested_types:
            types_list = ", ".join(suggested_types)
            prompt = f"""Extract entities from this document focusing on these types: {types_list}

Find EXACT text spans that physically appear in the document. Do not paraphrase or modify the text.

Document:
{text}

Return ONLY a JSON array like this:
[{{"text":"exact_text_from_document","type":"EntityType","start_pos":0,"end_pos":10,"confidence":0.9,"reasoning":"brief explanation"}}]"""
        else:
            prompt = f"""Analyze this regulatory/pharmaceutical document and extract important entities, data points, and key information.

Determine appropriate entity types and extract exact text spans only.

Document:
{text}

Return ONLY a JSON array like this:
[{{"text":"exact_text_from_document","type":"EntityType","start_pos":0,"end_pos":10,"confidence":0.9,"reasoning":"brief explanation"}}]"""

        try:
            response = self.complete_text(
                prompt=prompt,
                max_tokens=1500,
                temperature=0.1,
                json_mode=True,
                system="You are a precise entity extraction specialist. Extract only text that physically exists in the document. Never hallucinate or paraphrase."
            )

            if not response:
                return []

            return self._parse_annotation_response(response, page_num, text)

        except Exception as e:
            print(f"⚠️ Erreur extraction entités: {e}")
            return []

    def _parse_annotation_response(self, response: str, page_num: int, original_text: str) -> List[Dict[str, Any]]:
        """
        Parse la réponse JSON d'extraction et normalise les annotations.
        """
        try:
            data = self._extract_json_from_text(response)
            if not isinstance(data, list):
                print("❌ Réponse d'extraction non-JSON array")
                return []

            annotations = []
            text_lower = original_text.lower()

            for item in data:
                if not isinstance(item, dict):
                    continue

                # Extraction des champs requis
                text_val = (item.get("text") or "").strip()
                type_val = (item.get("type") or "").strip()

                if not text_val or not type_val:
                    continue

                # Gestion des positions
                start_pos = item.get("start_pos")
                end_pos = item.get("end_pos")

                # Validation et recherche des positions si nécessaire
                if not isinstance(start_pos, int) or not isinstance(end_pos,
                                                                    int) or start_pos < 0 or end_pos <= start_pos:
                    # Recherche du texte dans le document original
                    pos_result = self._find_text_position(text_val, original_text)
                    if pos_result:
                        start_pos, end_pos, actual_text = pos_result
                        text_val = actual_text  # Utiliser le texte trouvé
                    else:
                        # Pas trouvé - ignorer cette annotation
                        continue
                else:
                    # Valider que les positions sont cohérentes
                    if start_pos >= len(original_text) or end_pos > len(original_text):
                        continue

                # Gestion de la confiance
                try:
                    confidence = float(item.get("confidence", 0.8))
                    confidence = max(0.0, min(confidence, 1.0))  # Borner entre 0 et 1
                except (ValueError, TypeError):
                    confidence = 0.8

                # Construction de l'annotation finale
                annotation = {
                    "text": text_val,
                    "type": type_val,
                    "start_pos": int(start_pos),
                    "end_pos": int(end_pos),
                    "confidence": confidence,
                    "reasoning": (item.get("reasoning") or "").strip(),
                    "page_num": page_num,
                    "source": "groq_llama3.3_70b"
                }

                annotations.append(annotation)

            print(f"✅ Parsed {len(annotations)} annotations from GROQ")
            return annotations

        except Exception as e:
            print(f"❌ Erreur parsing annotations: {e}")
            return []

    def _find_text_position(self, search_text: str, document_text: str) -> Optional[tuple]:
        """
        Recherche intelligente de position de texte dans le document.

        Returns:
            Tuple (start_pos, end_pos, actual_text) ou None si non trouvé
        """
        if not search_text or not document_text:
            return None

        text_lower = document_text.lower()
        search_lower = search_text.lower().strip()

        # Recherche exacte d'abord
        pos = text_lower.find(search_lower)
        if pos >= 0:
            end_pos = pos + len(search_text)
            actual_text = document_text[pos:end_pos]
            return (pos, end_pos, actual_text)

        # Recherche par mots-clés significatifs
        words = search_text.split()
        for word in words:
            if len(word) >= 4:  # Mots d'au moins 4 caractères
                word_lower = word.lower()
                pos = text_lower.find(word_lower)
                if pos >= 0:
                    end_pos = pos + len(word)
                    actual_text = document_text[pos:end_pos]
                    return (pos, end_pos, actual_text)

        return None

    def _build_schema(self, suggested_types: List[str], annotations: List[Dict[str, Any]]):
        """
        Construction du schéma de types avec couleurs cohérentes.
        Met à jour self.last_schema.
        """
        all_types = set(suggested_types)

        # Ajouter les types trouvés dans les annotations
        for ann in annotations:
            ann_type = ann.get("type", "").strip()
            if ann_type:
                all_types.add(ann_type)

        # Construire le schéma avec couleurs déterministes
        schema = []
        for type_name in sorted(all_types):
            schema.append({
                "name": type_name.lower().replace(" ", "_").replace("-", "_"),
                "color": self._get_consistent_color(type_name)
            })

        self.last_schema = schema
        print(f"📋 Schéma construit: {len(schema)} types")

    # ============================================================================
    # UTILITAIRES
    # ============================================================================

    @staticmethod
    def _extract_json_from_text(text: str) -> Any:
        """
        Extraction robuste de JSON depuis une réponse de modèle.
        """
        if not text:
            return None

        # Nettoyer le texte
        text = text.strip()

        # 1. JSON direct
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # 2. JSON dans des blocs de code
        patterns = [
            r'```json\s*(\{.*?\}|\[.*?\])\s*```',
            r'```\s*(\{.*?\}|\[.*?\])\s*```',
            r'`(\{.*?\}|\[.*?\])`'
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
            if match:
                try:
                    return json.loads(match.group(1))
                except json.JSONDecodeError:
                    continue

        # 3. Premier objet/array JSON trouvé
        json_patterns = [
            r'(\{[^{}]*\})',  # Objet simple
            r'(\[.*?\])',  # Array
            r'(\{.*\})'  # Objet complexe (dernier recours)
        ]

        for pattern in json_patterns:
            match = re.search(pattern, text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(1))
                except json.JSONDecodeError:
                    continue

        return None

    @staticmethod
    def _get_consistent_color(type_name: str) -> str:
        """
        Génère une couleur cohérente pour un type d'entité (basé sur hash MD5).
        """
        if not type_name:
            return "#cccccc"

        # Hash MD5 pour couleur déterministe
        hash_obj = hashlib.md5(type_name.encode('utf-8'))
        hex_hash = hash_obj.hexdigest()

        # Utiliser les 6 premiers caractères comme couleur hex
        color = f"#{hex_hash[:6]}"

        return color

    @staticmethod
    def _get_random_color() -> str:
        """Couleur aléatoire pour les cas de fallback."""
        colors = [
            "#ff6b6b", "#4ecdc4", "#45b7d1", "#96ceb4", "#feca57",
            "#ff9ff3", "#54a0ff", "#ff7675", "#fdcb6e", "#6c5ce7",
            "#a29bfe", "#fd79a8", "#00b894", "#00cec9", "#e84393"
        ]
        return random.choice(colors)