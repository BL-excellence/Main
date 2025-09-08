# # rawdocs/groq_annotation_system.py
# from django.shortcuts import render, get_object_or_404
# from django.http import JsonResponse
# from django.contrib.auth.decorators import login_required
# from django.views.decorators.csrf import csrf_exempt
# from django.contrib import messages
# from datetime import datetime
# from .models import DocumentPage, Annotation, AnnotationType

# import requests
# import json
# import time
# from typing import List, Dict, Any, Optional
# import re
# import os


# class GroqAnnotator:
#     """
#     FREE GROQ API + Llama 3.1 70B implementation for regulatory document annotation
#     ZERO COST - Claude-level professional results!
#     """

#     def __init__(self):
#         # GROQ settings - FREE 6000 requests/day
#         self.api_url = "https://api.groq.com/openai/v1/chat/completions"
#         self.model = "llama-3.3-70b-versatile"  # BEST FREE model!
#         self.api_key = os.getenv("GROQ_API_KEY")

#         if not self.api_key:
#             raise ValueError("GROQ_API_KEY environment variable not set. Get free key from https://console.groq.com/")

#         print("🚀 Using GROQ FREE API (Llama 3.3 70B - BEST!)")
#         self.test_connection()

#     def test_connection(self) -> bool:
#         """Test GROQ API connection"""
#         try:
#             test_response = self.call_groq_api("Test connection", max_tokens=10)
#             if test_response:
#                 print("✅ GROQ API connected successfully!")
#                 return True
#             else:
#                 print("❌ GROQ API connection failed")
#                 return False
#         except Exception as e:
#             print(f"❌ GROQ connection error: {e}")
#             return False


#     def generate_random_color(self) -> str:
#         """Generate a random color for new annotation types"""
#         import random
#         colors = [
#             '#ff6b6b', '#4ecdc4', '#45b7d1', '#96ceb4', '#feca57', 
#             '#ff9ff3', '#54a0ff', '#ff7675', '#fdcb6e', '#6c5ce7',
#             '#a29bfe', '#fd79a8', '#00b894', '#00cec9', '#e84393',
#             '#2d3436', '#636e72', '#b2bec3', '#ddd', '#74b9ff'
#         ]
#         return random.choice(colors)

#     def annotate_page_with_groq(self, page_data: Dict[str, Any]) -> tuple:

#         text = page_data['text']

#         page_num = page_data['page_num']

#         if len(text.strip()) < 50:

#             return [], []

#         print(f"🧠 Processing page {page_num} with GROQ ")

#         # Step 1: Let AI analyze the document and suggest annotation types

#         analysis_prompt = f"""Analyze this document text and suggest annotation types that would be most useful for this specific content.

#     Document text: {text[:2000]}

#     Based on the content, suggest 5-10 annotation types that would capture the key information in this document.

#     Return JSON: {{"suggested_types": ["type1", "type2", "type3"]}}

#     Focus on what's actually in the text, not generic categories."""

#         analysis_response = self.call_groq_api(analysis_prompt, max_tokens=300)

#         suggested_types = []

        

#         if analysis_response:

#             try:

#                 analysis_data = self.extract_json_from_response(analysis_response)

#                 suggested_types = analysis_data.get('suggested_types', []) if analysis_data else []

#             except:

#                 pass

#         # Step 2: Generate annotation schema for suggested types

#         schema = []

#         for annotation_type in suggested_types:

#             schema.append({

#                 'name': annotation_type.lower().replace(' ', '_'),

#                 'color': self.get_color_for_type(annotation_type)

#             })

#         # Step 3: Create completely dynamic prompt

#         if suggested_types:

#             types_list = ', '.join(suggested_types)

#             prompt = f"""Extract entities from this document. Look for these types of information: {types_list}

#     Find EXACT text spans that match these categories. Only extract text that physically exists in the document.

#     Document: {text}

#     Return JSON array: [{{"text": "exact_text", "type": "type_name", "start_pos": 0, "end_pos": 10, "confidence": 0.9, "reasoning": "why"}}]"""

#         else:

#             # Fallback: completely open-ended extraction

#             prompt = f"""Analyze this document and extract any important entities, data points, or key information.

#     Determine what types of information are present and extract them with appropriate type names.

#     Document: {text}

#     Return JSON array: [{{"text": "exact_text", "type": "type_you_determine", "start_pos": 0, "end_pos": 10, "confidence": 0.9, "reasoning": "why"}}]"""

#         # Step 4: Process with Groq

#         response = self.call_groq_api(prompt)

#         annotations = self.parse_groq_response(response, page_num) if response else []

        

#         # Step 5: Generate schema for any types we didn't predict

#         all_types = set(suggested_types)

#         for ann in annotations:

#             all_types.add(ann.get('type', ''))

        

#         # Update schema with any new types found

#         schema = []

#         for annotation_type in all_types:

#             if annotation_type:

#                 schema.append({

#                     'name': annotation_type.lower().replace(' ', '_'),

#                     'color': self.generate_random_color()

#                 })

#         return annotations, schema

#     def get_color_for_type(self, annotation_type: str) -> str:
#         """Generate consistent color for annotation type"""
#         import hashlib
#         # Generate consistent color based on type name
#         hash_object = hashlib.md5(annotation_type.encode())
#         hex_dig = hash_object.hexdigest()
#         return f"#{hex_dig[:6]}"

#     def call_groq_api(self, prompt: str, max_tokens: int = 4000) -> Optional[str]:
#         """Call GROQ API with optimized settings"""

#         headers = {
#             "Authorization": f"Bearer {self.api_key}",
#             "Content-Type": "application/json"
#         }

#         payload = {
#             "model": self.model,
#             "messages": [
#                 {
#                     "role": "system",
#                     "content": "You are an expert regulatory document analyst. Extract entities with perfect precision, never hallucinate."
#                 },
#                 {
#                     "role": "user",
#                     "content": prompt
#                 }
#             ],
#             "temperature": 0.1,  # Low for consistency
#             "max_tokens": max_tokens,
#             "top_p": 0.9
#         }

#         try:
#             response = requests.post(
#                 self.api_url,
#                 headers=headers,
#                 json=payload,
#                 timeout=120  # 2 minutes timeout
#             )

#             if response.status_code == 200:
#                 result = response.json()
#                 return result['choices'][0]['message']['content']
#             elif response.status_code == 429:
#                 print("⚠️  Rate limit reached, waiting...")
#                 time.sleep(60)  # Wait 1 minute
#                 return self.call_groq_api(prompt, max_tokens)
#             else:
#                 print(f"❌ GROQ API error {response.status_code}: {response.text}")
#                 return None

#         except requests.RequestException as e:
#             print(f"❌ Request error: {e}")
#             return None

#     def parse_groq_response(self, response: str, page_num: int) -> List[Dict[str, Any]]:
#         """Parse GROQ response to extract annotations"""

#         try:
#             # Extract JSON from response
#             json_match = self.extract_json_from_response(response)

#             if json_match and isinstance(json_match, list):
#                 annotations = []

#                 for item in json_match:
#                     if isinstance(item, dict) and all(k in item for k in ['text', 'type']):
#                         # Clean up the annotation
#                         item['page_num'] = page_num
#                         item['source'] = 'groq_llama3.3_70b'

#                         # Ensure confidence
#                         if 'confidence' not in item:
#                             item['confidence'] = 0.8
#                         else:
#                             item['confidence'] = float(item['confidence'])

#                         # Ensure positions
#                         if 'start_pos' not in item:
#                             item['start_pos'] = 0
#                         if 'end_pos' not in item:
#                             item['end_pos'] = len(item['text'])

#                         annotations.append(item)

#                 print(f"✅ Parsed {len(annotations)} annotations from GROQ")
#                 return annotations
#             else:
#                 print("❌ Invalid JSON format in GROQ response")
#                 return []

#         except Exception as e:
#             print(f"❌ Parse error: {e}")
#             return []

#     def extract_json_from_response(self, response: str) -> Optional[Any]:
#         """Extract JSON from GROQ response"""

#         # Try direct JSON parse
#         try:
#             return json.loads(response.strip())
#         except:
#             pass

#         # Look for JSON in code blocks
#         try:
#             json_match = re.search(r'```json\s*(\[.*?\])\s*```', response, re.DOTALL)
#             if json_match:
#                 return json.loads(json_match.group(1))
#         except:
#             pass

#         # Look for JSON array
#         try:
#             json_match = re.search(r'(\[.*?\])', response, re.DOTALL)
#             if json_match:
#                 return json.loads(json_match.group(1))
#         except:
#             pass

#         return None

#     def generate_summary(self, pdf_data: Dict[str, Any], annotations: List[Dict[str, Any]]) -> Dict[str, Any]:
#         """Generate processing summary"""

#         # Analyze annotations
#         type_counts = {}
#         confidence_scores = []

#         for ann in annotations:
#             ann_type = ann.get('type', 'unknown')
#             type_counts[ann_type] = type_counts.get(ann_type, 0) + 1
#             confidence_scores.append(ann.get('confidence', 0.5))

#         avg_confidence = sum(confidence_scores) / len(confidence_scores) if confidence_scores else 0
#         high_confidence_count = len([c for c in confidence_scores if c > 0.8])

#         return {
#             'total_pages': pdf_data.get('total_pages', 0),
#             'total_annotations': len(annotations),
#             'annotation_breakdown': type_counts,
#             'average_confidence': round(avg_confidence, 3),
#             'high_confidence_annotations': high_confidence_count,
#             'processing_model': self.model,
#             'cost': 0.0,  # FREE!
#             'quality_grade': 'A' if avg_confidence > 0.85 else 'B+' if avg_confidence > 0.75 else 'B'
#         }

# rawdocs/groq_annotation_system.py
import os
import re
import json
import time
import random
import hashlib
import requests
from typing import List, Dict, Any, Optional, Tuple

from django.conf import settings


class GroqAnnotator:
    """
    Intégration GROQ (API OpenAI-compatible) pour l'annotation réglementaire.

    ✅ Robuste au format de réponse:
       - Accepte JSON array OU objet {entities:[...]} / {annotations:[...]} / {items:[...]} / etc.
       - Normalise les champs (label→type, value→text, start→start_pos, end→end_pos, length→start+length)
       - Tolère la faute 'confidencce'
       - Re-localise les positions si absentes/invalides
    """

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_url = getattr(settings, "GROQ_API_URL", "https://api.groq.com/openai/v1/chat/completions")
        self.model = model or getattr(settings, "GROQ_MODEL", os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"))
        self.api_key = api_key or getattr(settings, "GROQ_API_KEY", os.getenv("GROQ_API_KEY", ""))

        self.enabled = bool(self.api_key)
        self.last_schema: List[Dict[str, str]] = []
        self._api_healthy: Optional[bool] = None

        if self.enabled:
            print(f"🔍 Analyseur réglementaire GROQ initialisé (model: {self.model})")
            try:
                self.test_connection()
            except Exception as e:
                print(f"⚠️ Test GROQ échoué: {e}")
        else:
            print("ℹ️ GROQ désactivé (clé API absente)")

    # -------------------------------------------------------------------------
    # API publiques
    # -------------------------------------------------------------------------

    def test_connection(self) -> bool:
        """Ping simple de l'API pour renseigner _api_healthy."""
        try:
            content = self.complete_text("ping", max_tokens=20, timeout=15)
            ok = bool(content)
            self._api_healthy = ok
            if ok:
                print("✅ GROQ API connectée avec succès!")
            else:
                print("⚠️ Connexion GROQ non confirmée")
            return ok
        except Exception as e:
            print(f"❌ GROQ connection error: {e}")
            self._api_healthy = False
            return False

    def check_api_health(self) -> bool:
        if not self.enabled:
            return False
        if self._api_healthy is not None:
            return self._api_healthy
        return self.test_connection()

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
        """Appel chat/completions avec gestion d'erreurs et retries 429."""
        if not self.enabled:
            return None

        messages = [
            {"role": "system", "content": system or "You are a helpful assistant."},
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
        """Chat en mode JSON forcé."""
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

    # Alias de compat
    complete_json = chat_json
    ask_json = chat_json

    # -------------------------------------------------------------------------
    # Pipeline d'annotation (retourne annotations + schema)
    # -------------------------------------------------------------------------

    def annotate_page_with_groq(self, page_data: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[Dict[str, str]]]:
        """
        Args:
            page_data: {'page_num': int, 'text': str, ...}

        Returns:
            (annotations, schema)
        """
        text = (page_data or {}).get("text", "") or ""
        text = text.strip()
        page_num = int((page_data or {}).get("page_num", 1))

        self.last_schema = []

        if len(text) < 50:
            print(f"⚠️ Texte trop court page {page_num} ({len(text)} chars)")
            return [], []

        if not self.check_api_health():
            print("❌ API GROQ indisponible - annotation impossible")
            return [], []

        max_chars = 10000
        text_trunc = text[:max_chars]
        print(f"🧠 Processing page {page_num} with GROQ - model={self.model}")

        # 1) types suggérés
        suggested_types = self._analyze_content_for_types(text_trunc)

        # 2) extraction entités
        annotations = self._extract_entities(text_trunc, suggested_types, page_num)

        # 3) schéma couleurs déterministes
        self._build_schema(suggested_types, annotations)
        print(f"📋 Schéma construit: {len(self.last_schema)} types")

        return annotations, self.last_schema

    # -------------------------------------------------------------------------
    # Compat (appel externe possible)
    # -------------------------------------------------------------------------

    def call_groq_api(self, prompt: str, max_tokens: int = 4000) -> Optional[str]:
        """Alias compat."""
        return self.complete_text(
            prompt=prompt,
            max_tokens=max_tokens,
            system="You are an expert regulatory document analyst. Extract entities with perfect precision, never hallucinate."
        )

    def parse_groq_response(self, response: str, page_num: int, original_text: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Compat: parseur large spectre.
        - si original_text fourni: validation/recherche de positions
        - accepte array direct ou objet {entities:[...]} etc.
        """
        if not response:
            return []

        try:
            data = self._extract_json_from_text(response)
            array = self._pluck_annotation_array(data)
            if not isinstance(array, list):
                preview = repr((response or "")[:200])
                print(f"❌ Invalid JSON format in GROQ response (no list found). Preview: {preview}")
                return []

            anns: List[Dict[str, Any]] = []
            for raw in array:
                norm = self._coerce_annotation_item(raw) if isinstance(raw, dict) else None
                if not norm:
                    continue

                text_val = norm["text"]
                type_val = norm["type"]
                start_pos = norm["start_pos"]
                end_pos = norm["end_pos"]
                confidence = norm["confidence"]
                reasoning = norm["reasoning"]

                # positions: valider / retrouver
                if original_text:
                    if (not isinstance(start_pos, int) or not isinstance(end_pos, int)
                        or start_pos < 0 or end_pos <= start_pos
                        or start_pos >= len(original_text) or end_pos > len(original_text)):
                        found = self._find_text_position(text_val, original_text)
                        if found:
                            start_pos, end_pos, actual = found
                            text_val = actual
                        else:
                            # on ignore si introuvable dans le document
                            continue
                else:
                    # fallback permissif si pas de texte original
                    if not isinstance(start_pos, int) or not isinstance(end_pos, int) or end_pos <= start_pos:
                        start_pos, end_pos = 0, len(text_val)

                anns.append({
                    "text": text_val,
                    "type": type_val,
                    "start_pos": int(start_pos),
                    "end_pos": int(end_pos),
                    "confidence": confidence,
                    "reasoning": reasoning,
                    "page_num": page_num,
                    "source": "groq_llama3.3_70b"
                })

            print(f"✅ Parsed {len(anns)} annotations from GROQ")
            return anns

        except Exception as e:
            print(f"❌ Parse error: {e}")
            return []

    # -------------------------------------------------------------------------
    # Résumé statistique
    # -------------------------------------------------------------------------

    def generate_summary(self, pdf_data: Dict[str, Any], annotations: List[Dict[str, Any]]) -> Dict[str, Any]:
        type_counts: Dict[str, int] = {}
        scores: List[float] = []

        for ann in annotations or []:
            t = ann.get("type", "unknown")
            type_counts[t] = type_counts.get(t, 0) + 1
            try:
                scores.append(float(ann.get("confidence", 0.5)))
            except (TypeError, ValueError):
                scores.append(0.5)

        avg = sum(scores) / len(scores) if scores else 0.0
        hi = len([s for s in scores if s >= 0.8])

        grade = "A" if avg > 0.85 else "B+" if avg > 0.75 else "B"

        return {
            "total_pages": int(pdf_data.get("total_pages", 0) or 0),
            "total_annotations": len(annotations or []),
            "annotation_breakdown": type_counts,
            "average_confidence": round(avg, 3),
            "high_confidence_annotations": hi,
            "processing_model": self.model,
            "cost": 0.0,
            "quality_grade": grade,
        }

    # -------------------------------------------------------------------------
    # Internes: prompts + API + parsing
    # -------------------------------------------------------------------------

    def _chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: int = 800,
        json_mode: bool = False,
        timeout: int = 120
    ) -> Optional[str]:
        if not self.enabled:
            return None

        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        payload: Dict[str, Any] = {
            "model": model or self.model,
            "messages": messages,
            "temperature": float(temperature),
            "max_tokens": int(max_tokens),
            "top_p": 0.9,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        try:
            print(f"🌐 Calling GROQ API with {len(messages)} messages, max_tokens={max_tokens}")
            r = requests.post(self.api_url, headers=headers, json=payload, timeout=timeout)
            print(f"🌐 GROQ response status: {r.status_code}")

            if r.status_code == 200:
                try:
                    body = r.json()
                    content = body["choices"][0]["message"]["content"]
                    print(f"✅ GROQ response received (length: {len(content)})")
                    print(f"✅ First 200 chars: {repr(content[:200])}")

                    if body["choices"][0].get("finish_reason") == "length" and max_tokens < 2000:
                        print(f"⚠️ Response was truncated due to max_tokens limit")
                        print(f"🔄 Retrying with increased max_tokens: {max_tokens * 2}")
                        return self._chat(messages, model, temperature, max_tokens * 2, json_mode, timeout)

                    return content
                except Exception as e:
                    print(f"⚠️ Unexpected GROQ payload format: {e}")
                    print(f"⚠️ Raw: {r.text[:500]}")
                    return None

            if r.status_code == 401:
                print("❌ GROQ 401 (clé invalide/expirée) — désactivation")
                self.enabled = False
                self._api_healthy = False
                return None
            if r.status_code == 429:
                print("⚠️ GROQ 429 — pause 60s puis retry")
                time.sleep(60)
                return self._chat(messages, model, temperature, max_tokens, json_mode, timeout)
            if r.status_code >= 500:
                print(f"❌ GROQ {r.status_code} — erreur serveur")
                self._api_healthy = False
                return None

            print(f"❌ GROQ {r.status_code}: {r.text[:800]}")
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
        prompt = f"""Analyze this document and suggest 5-10 entity types that capture key information actually present.

Text sample:
{text[:1500]}

Return JSON: {{"suggested_types": ["Type1","Type2", "..."]}}"""
        resp = self.complete_text(
            prompt=prompt,
            max_tokens=300,
            temperature=0.1,
            json_mode=True,
            system="You are an expert document analyst. Only suggest entity types that clearly exist in the provided text."
        )
        if not resp:
            return []

        data = self._extract_json_from_text(resp)
        types = []
        if isinstance(data, dict):
            raw = data.get("suggested_types", [])
            if isinstance(raw, list):
                seen = set()
                for t in raw:
                    if isinstance(t, str):
                        s = t.strip()
                        if s and s.lower() not in seen:
                            seen.add(s.lower())
                            types.append(s)
        return types[:10]

    def _extract_entities(self, text: str, suggested_types: List[str], page_num: int) -> List[Dict[str, Any]]:
        if suggested_types:
            types_list = ", ".join(suggested_types)
            prompt = f"""Extract entities focusing on these types: {types_list}

Find EXACT text spans that physically appear in the document (no paraphrase).

Document:
{text}

Return ONLY a JSON array like:
[{{"text":"exact","type":"EntityType","start_pos":0,"end_pos":10,"confidence":0.9,"reasoning":"brief"}}]"""
        else:
            prompt = f"""Analyze this document and extract important entities as EXACT text spans.

Document:
{text}

Return ONLY a JSON array like:
[{{"text":"exact","type":"EntityType","start_pos":0,"end_pos":10,"confidence":0.9,"reasoning":"brief"}}]"""

        resp = self.complete_text(
            prompt=prompt,
            max_tokens=1500,
            temperature=0.1,
            json_mode=True,
            system="You are a precise entity extraction specialist. Extract only text that physically exists in the document."
        )
        if not resp:
            return []

        # Utilise le parseur robuste avec texte original pour validation/recherche positions
        return self._parse_annotation_response(resp, page_num, text)

    # -------------------------------------------------------------------------
    # Parsing robuste + normalisation
    # -------------------------------------------------------------------------

    def _parse_annotation_response(self, response: str, page_num: int, original_text: str) -> List[Dict[str, Any]]:
        try:
            data = self._extract_json_from_text(response)
            array = self._pluck_annotation_array(data)
            if not isinstance(array, list):
                preview = repr((response or "")[:200])
                print(f"❌ Réponse d'extraction non-JSON array. Preview: {preview}")
                return []

            annotations: List[Dict[str, Any]] = []
            for raw in array:
                norm = self._coerce_annotation_item(raw) if isinstance(raw, dict) else None
                if not norm:
                    continue

                txt = norm["text"]
                typ = norm["type"]
                s = norm["start_pos"]
                e = norm["end_pos"]
                conf = norm["confidence"]
                why = norm["reasoning"]

                # (Re)validation/recherche positions
                if (not isinstance(s, int) or not isinstance(e, int)
                    or s < 0 or e <= s
                    or s >= len(original_text) or e > len(original_text)):
                    found = self._find_text_position(txt, original_text)
                    if found:
                        s, e, actual = found
                        txt = actual
                    else:
                        continue

                annotations.append({
                    "text": txt,
                    "type": typ,
                    "start_pos": int(s),
                    "end_pos": int(e),
                    "confidence": conf,
                    "reasoning": why,
                    "page_num": page_num,
                    "source": "groq_llama3.3_70b"
                })

            print(f"✅ Parsed {len(annotations)} annotations from GROQ")
            return annotations

        except Exception as e:
            print(f"❌ Erreur parsing annotations: {e}")
            return []

    def _pluck_annotation_array(self, data: Any) -> Optional[list]:
        """
        Retourne la liste d'items d'annotation depuis différentes formes:
          - list
          - dict: keys candidates → ["entities","annotations","items","results","spans","data","predictions","outputs"]
          - dict avec 1 valeur liste
          - dict indexé "0","1",... → liste dans l'ordre
        """
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ["entities", "annotations", "items", "results", "spans", "data", "predictions", "outputs"]:
                v = data.get(key)
                if isinstance(v, list):
                    return v
            lists = [v for v in data.values() if isinstance(v, list)]
            if len(lists) == 1:
                return lists[0]
            if all(isinstance(k, str) and k.isdigit() for k in data.keys()):
                out = []
                i = 0
                while str(i) in data:
                    out.append(data[str(i)])
                    i += 1
                if out:
                    return out
        return None

    def _coerce_annotation_item(self, item: dict) -> Optional[dict]:
        """
        Normalise un item → {text, type, start_pos, end_pos, confidence, reasoning}
        Gère alias + faute 'confidencce'.
        """
        if not isinstance(item, dict):
            return None

        pick = lambda keys: next((item[k] for k in keys if k in item and item[k] is not None), None)

        text = pick(["text", "value", "span", "content", "exact_text"])
        if isinstance(text, str):
            text = text.strip()
        if not text:
            return None

        etype = pick(["type", "label", "entity", "category", "name", "class"])
        if isinstance(etype, str):
            etype = etype.strip()
        if not etype:
            return None

        start_pos = pick(["start_pos", "start", "begin", "offset_start", "char_start", "from"])
        end_pos   = pick(["end_pos", "end", "offset_end", "char_end", "to"])
        length    = pick(["length", "len"])
        try:
            start_pos = int(start_pos) if start_pos is not None else None
        except Exception:
            start_pos = None
        try:
            end_pos = int(end_pos) if end_pos is not None else None
        except Exception:
            end_pos = None
        try:
            length = int(length) if length is not None else None
        except Exception:
            length = None
        if start_pos is not None and end_pos is None and length is not None:
            end_pos = start_pos + length

        conf = pick(["confidence", "score", "prob", "probability", "confidencce"])  # ← tolère la faute
        try:
            conf = float(conf) if conf is not None else 0.8
        except Exception:
            conf = 0.8
        conf = max(0.0, min(1.0, conf))

        why = pick(["reasoning", "explanation", "why", "notes", "comment"])
        if isinstance(why, str):
            why = why.strip()
        why = why or ""

        return {
            "text": text,
            "type": etype,
            "start_pos": start_pos,
            "end_pos": end_pos,
            "confidence": conf,
            "reasoning": why
        }

    @staticmethod
    def _extract_json_from_text(text: str) -> Any:
        """Extrait du JSON depuis texte brut ou dans des blocs ```json ...```."""
        if not text:
            return None
        t = text.strip()

        # 1) JSON direct
        try:
            return json.loads(t)
        except json.JSONDecodeError:
            pass

        # 2) Blocs de code
        for pattern in [r'```json\s*(\{.*?\}|\[.*?\])\s*```',
                        r'```\s*(\{.*?\}|\[.*?\])\s*```',
                        r'`(\{.*?\}|\[.*?\])`']:
            m = re.search(pattern, t, re.DOTALL | re.IGNORECASE)
            if m:
                try:
                    return json.loads(m.group(1))
                except json.JSONDecodeError:
                    continue

        # 3) Premier objet/array plausible
        for pattern in [r'(\[.*?\])', r'(\{[^{}]*\})', r'(\{.*\})']:
            m = re.search(pattern, t, re.DOTALL)
            if m:
                try:
                    return json.loads(m.group(1))
                except json.JSONDecodeError:
                    continue

        return None

    def _find_text_position(self, search_text: str, document_text: str) -> Optional[tuple]:
        """
        Recherche intelligente des positions dans le texte original.
        Retourne (start_pos, end_pos, actual_text) ou None.
        """
        if not search_text or not document_text:
            return None

        text_lower = document_text.lower()
        search_lower = search_text.lower().strip()

        # Essai exact (insensible casse)
        pos = text_lower.find(search_lower)
        if pos >= 0:
            end_pos = pos + len(search_lower)
            actual = document_text[pos:end_pos]
            return (pos, end_pos, actual)

        # Essai par mot significatif (>=4 chars)
        for w in search_lower.split():
            if len(w) >= 4:
                p = text_lower.find(w)
                if p >= 0:
                    end_pos = p + len(w)
                    actual = document_text[p:end_pos]
                    return (p, end_pos, actual)

        return None

    def _build_schema(self, suggested_types: List[str], annotations: List[Dict[str, Any]]):
        all_types = set(suggested_types or [])
        for ann in annotations or []:
            t = (ann.get("type") or "").strip()
            if t:
                all_types.add(t)

        schema: List[Dict[str, str]] = []
        for t in sorted(all_types):
            schema.append({
                "name": t.lower().replace(" ", "_").replace("-", "_"),
                "color": self._get_consistent_color(t)
            })
        self.last_schema = schema

    # -------------------------------------------------------------------------
    # Couleurs
    # -------------------------------------------------------------------------

    def get_color_for_type(self, annotation_type: str) -> str:
        return self._get_consistent_color(annotation_type)

    @staticmethod
    def generate_random_color() -> str:
        colors = [
            "#ff6b6b", "#4ecdc4", "#45b7d1", "#96ceb4", "#feca57",
            "#ff9ff3", "#54a0ff", "#ff7675", "#fdcb6e", "#6c5ce7",
            "#a29bfe", "#fd79a8", "#00b894", "#00cec9", "#e84393",
            "#2d3436", "#636e72", "#b2bec3", "#dddddd", "#74b9ff"
        ]
        return random.choice(colors)

    @staticmethod
    def _get_consistent_color(type_name: str) -> str:
        if not type_name:
            return "#cccccc"
        h = hashlib.md5(type_name.encode("utf-8")).hexdigest()
        return f"#{h[:6]}"
