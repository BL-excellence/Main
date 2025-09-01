# # expert/json_enrichment.py
# """
# SystÃƒÂ¨me d'enrichissement des JSON pour l'expert
# Permet de crÃƒÂ©er des JSON sÃƒÂ©mantiques avec relations et contexte
# """
#
# import json
# import re
# from typing import Dict, List, Any, Optional, Union
# from django.utils import timezone
# from datetime import datetime
#
# from expert.llm_client import LLMClient
#
#
# class JSONEnricher:
#     """Enrichit les JSON basiques avec du contexte et des relations"""
#
#     def __init__(self):
#         self.entity_schemas = self._get_entity_schemas()
#         self.relation_types = self._get_relation_types()
#         self.llm = LLMClient()
#
#     def _get_entity_schemas(self) -> Dict[str, Dict]:
#         """DÃƒÂ©finit les schÃƒÂ©mas pour chaque type d'entitÃƒÂ©"""
#         return {
#             "Product": {
#                 "properties": ["name", "type", "category", "manufacturer", "approval_status"],
#                 "relations": ["contains", "manufactured_by", "approved_for", "contraindicated_with"]
#             },
#             "Dosage": {
#                 "properties": ["value", "unit", "frequency", "route", "population"],
#                 "relations": ["applies_to", "contraindicated_in"]
#             },
#             "Active_Ingredient": {
#                 "properties": ["name", "concentration", "therapeutic_class", "mechanism"],
#                 "relations": ["contained_in", "interacts_with", "metabolized_by"]
#             },
#             "Manufacturing_Site": {
#                 "properties": ["name", "location", "country", "certification", "capacity"],
#                 "relations": ["produces", "certified_by", "located_in"]
#             },
#             "Indication": {
#                 "properties": ["condition", "population", "severity", "duration"],
#                 "relations": ["treated_by", "requires_dosage", "contraindicated_with"]
#             },
#             "Contraindication": {
#                 "properties": ["condition", "severity", "population", "reason"],
#                 "relations": ["prohibits", "applies_to_product", "requires_monitoring"]
#             },
#             "Side_Effect": {
#                 "properties": ["effect", "frequency", "severity", "onset"],
#                 "relations": ["caused_by", "affects_population", "requires_action"]
#             }
#         }
#
#     def _get_relation_types(self) -> Dict[str, str]:
#         """Types de relations possibles entre entitÃƒÂ©s"""
#         return {
#             "contains": "contient",
#             "manufactured_by": "fabriquÃƒÂ© par",
#             "approved_for": "approuvÃƒÂ© pour",
#             "contraindicated_with": "contre-indiquÃƒÂ© avec",
#             "applies_to": "s'applique Ãƒ ",
#             "interacts_with": "interagit avec",
#             "treated_by": "traitÃƒÂ© par",
#             "produced_at": "produit Ãƒ ",
#             "requires": "nÃƒÂ©cessite",
#             "prohibits": "interdit",
#             "causes": "cause",
#             "monitors": "surveille"
#         }
#
#     def _normalize_entity_data(self, entity_data: Union[List, Dict, None]) -> List[str]:
#         """
#         Normalise les donnÃƒÂ©es d'entitÃƒÂ© en une liste de chaÃƒÂ®nes.
#         GÃƒÂ¨re les formats : ["item1", "item2"] ou {"items": [...], "count": n} ou None
#         """
#         if not entity_data:
#             return []
#
#         if isinstance(entity_data, list):
#             # Cas : ["item1", "item2"] ou [{"value": "item1"}, ...]
#             result = []
#             for item in entity_data:
#                 if isinstance(item, str):
#                     result.append(item)
#                 elif isinstance(item, dict) and item.get("value"):
#                     result.append(str(item["value"]))
#                 elif isinstance(item, dict) and item.get("name"):
#                     result.append(str(item["name"]))
#             return result
#
#         elif isinstance(entity_data, dict):
#             # Cas : {"items": [...], "count": n}
#             items = entity_data.get("items", [])
#             if isinstance(items, list):
#                 return self._normalize_entity_data(items)
#             return []
#
#         # Cas : string seule
#         elif isinstance(entity_data, str):
#             return [entity_data]
#
#         return []
#
#     def enrich_basic_json(
#             self,
#             basic_json: Dict,
#             document_context: Dict = None,
#             *,
#             document_summary: Optional[str] = None,
#             expert_relations: Optional[List[Dict]] = None,
#             use_ai: bool = True
#     ) -> Dict:
#         """Enrichit un JSON basique (rÃƒÂ¨gles) + ÃƒÂ©ventuellement IA, puis fusionne."""
#         try:
#             # 1) Enrichissement dÃƒÂ©terministe (ton code actuel)
#             enriched = {
#                 "document": basic_json.get("document", {}),
#                 "metadata": {
#                     "enriched_at": timezone.now().isoformat(),
#                     "version": "2.1",
#                     "schema": "semantic_pharmaceutical"
#                 },
#                 "entities": {},
#                 "relations": [],
#                 "contexts": {},
#                 "questions_answers": self._generate_qa_pairs(basic_json),
#                 "semantic_summary": ""
#             }
#
#             # Traitement sÃƒÂ©curisÃƒÂ© des entitÃƒÂ©s
#             entities_data = basic_json.get("entities", {})
#             if isinstance(entities_data, dict):
#                 for entity_type, values in entities_data.items():
#                     normalized_values = self._normalize_entity_data(values)
#                     enriched["entities"][entity_type] = self._enrich_entity(
#                         entity_type, normalized_values, document_context
#                     )
#
#             enriched["relations"] = self._extract_relations(enriched["entities"])
#
#             # Ajouter les relations dÃƒÂ©finies par l'expert si fournies
#             if expert_relations:
#                 enriched["relations"].extend(expert_relations)
#
#             enriched["contexts"] = self._generate_contexts(
#                 enriched["entities"], enriched["relations"]
#             )
#
#             # 2) IA : propose une version "expert" du JSON enrichi
#             ai_json = None
#             if use_ai:
#                 ai_json = self._enrich_with_ai(
#                     basic_json=basic_json,
#                     document_context=document_context or {},
#                     document_summary=document_summary or "",
#                     expert_relations=expert_relations or [],
#                 )
#
#             # 3) Fusion "smart" entre rÃƒÂ¨gles et IA (IA prioritaire sur les champs vides)
#             if ai_json:
#                 enriched = self._smart_merge(enriched, ai_json)
#
#             # 4) RÃƒÂ©sumÃƒÂ© sÃƒÂ©mantique (si IA dispo, rÃƒÂ©sumÃƒÂ© IA prioritaire)
#             if use_ai:
#                 ai_summary = self.generate_semantic_summary_ai(
#                     enriched=enriched,
#                     document_summary=document_summary or ""
#                 )
#                 if ai_summary:
#                     enriched["semantic_summary"] = ai_summary
#
#             if not enriched.get("semantic_summary"):
#                 enriched["semantic_summary"] = self._generate_semantic_summary(enriched)
#
#             return enriched
#
#         except Exception as e:
#             print(f"Ã¢ÂÅ’ Erreur lors de l'enrichissement: {e}")
#             # Retourner une version minimale en cas d'erreur
#             return {
#                 "document": basic_json.get("document", {}),
#                 "metadata": {
#                     "enriched_at": timezone.now().isoformat(),
#                     "version": "2.1",
#                     "schema": "semantic_pharmaceutical",
#                     "error": str(e)
#                 },
#                 "entities": basic_json.get("entities", {}),
#                 "relations": [],
#                 "contexts": {},
#                 "questions_answers": [],
#                 "semantic_summary": "Erreur lors de l'enrichissement automatique."
#             }
#
#     def _generate_qa_pairs(self, basic_json: Dict) -> List[Dict]:
#         """GÃƒÂ©nÃƒÂ¨re des paires question-rÃƒÂ©ponse automatiques"""
#         qa_pairs = []
#
#         try:
#             entities = basic_json.get("entities", {})
#
#             # Questions sur le produit
#             products = self._normalize_entity_data(entities.get("Product"))
#             if products:
#                 product = products[0]
#                 qa_pairs.extend([
#                     {
#                         "question": "Quel est le nom du produit ?",
#                         "answer": f"Le produit est {product}",
#                         "confidence": 1.0,
#                         "entity_refs": [{"type": "Product", "value": product}]
#                     },
#                     {
#                         "question": f"Qu'est-ce que {product} ?",
#                         "answer": f"{product} est un mÃƒÂ©dicament pharmaceutique",
#                         "confidence": 0.9,
#                         "entity_refs": [{"type": "Product", "value": product}]
#                     }
#                 ])
#
#             # Questions sur le dosage
#             dosages = self._normalize_entity_data(entities.get("Dosage"))
#             if dosages and products:
#                 dosage = dosages[0]
#                 product = products[0]
#                 qa_pairs.extend([
#                     {
#                         "question": f"Quel est le dosage de {product} ?",
#                         "answer": f"Le dosage de {product} est de {dosage}",
#                         "confidence": 0.95,
#                         "entity_refs": [
#                             {"type": "Product", "value": product},
#                             {"type": "Dosage", "value": dosage}
#                         ]
#                     },
#                     {
#                         "question": f"Ãƒâ‚¬ quelle dose prendre {product} ?",
#                         "answer": f"La dose recommandÃƒÂ©e est de {dosage}",
#                         "confidence": 0.9,
#                         "entity_refs": [
#                             {"type": "Product", "value": product},
#                             {"type": "Dosage", "value": dosage}
#                         ]
#                     }
#                 ])
#
#             # Questions sur le principe actif
#             ingredients = self._normalize_entity_data(entities.get("Active_Ingredient"))
#             if ingredients and products:
#                 ingredient = ingredients[0]
#                 product = products[0]
#                 qa_pairs.append({
#                     "question": f"Quel est le principe actif de {product} ?",
#                     "answer": f"Le principe actif de {product} est {ingredient}",
#                     "confidence": 0.95,
#                     "entity_refs": [
#                         {"type": "Product", "value": product},
#                         {"type": "Active_Ingredient", "value": ingredient}
#                     ]
#                 })
#
#         except Exception as e:
#             print(f"Ã¢ÂÅ’ Erreur gÃƒÂ©nÃƒÂ©ration Q&A: {e}")
#
#         return qa_pairs
#
#     # ---------- IA : construction du JSON enrichi -----------------------------
#     def _enrich_with_ai(
#             self,
#             *,
#             basic_json: Dict,
#             document_context: Dict,
#             document_summary: str,
#             expert_relations: List[Dict]
#     ) -> Optional[Dict]:
#         """
#         Demande au LLM de produire un JSON enrichi STRICT selon le schÃƒÂ©ma attendu.
#         """
#         try:
#             sys = (
#                 "Tu es un expert pharmaceutique qui gÃƒÂ©nÃƒÂ¨re un JSON sÃƒÂ©mantique strict. "
#                 "RÃƒÂ©ponds en JSON valide uniquement, conforme au schÃƒÂ©ma suivant: "
#                 "{document, metadata, entities, relations, contexts, questions_answers, semantic_summary}. "
#                 "N'invente pas d'entitÃƒÂ©s si les sources ne le justifient pas."
#             )
#             user = {
#                 "instruction": "GÃƒÂ©nÃƒÂ¨re un JSON enrichi expert.",
#                 "constraints": {
#                     "schema": {
#                         "document": "object",
#                         "metadata": "object",
#                         "entities": "object",
#                         "relations": "array",
#                         "contexts": "object",
#                         "questions_answers": "array",
#                         "semantic_summary": "string"
#                     },
#                     "language": "fr",
#                     "no_free_text_outside_json": True
#                 },
#                 "inputs": {
#                     "basic_json": basic_json,
#                     "document_context": document_context,
#                     "document_summary": document_summary,
#                     "expert_relations": expert_relations
#                 },
#                 "hints": [
#                     "ComplÃƒÂ¨te propriÃƒÂ©tÃƒÂ©s vides (type, category, route...) si infÃƒÂ©rable.",
#                     "Relie Product Ã¢â€ â€™ Active_Ingredient, Product Ã¢â€ â€™ Dosage, etc.",
#                     "CrÃƒÂ©e des Q&A utiles (5-10) avec champ 'confidence'.",
#                     "RÃƒÂ©dige 'semantic_summary' en 1-3 phrases claires en franÃƒÂ§ais."
#                 ]
#             }
#
#             messages = [
#                 {"role": "system", "content": sys},
#                 {"role": "user", "content": json.dumps(user, ensure_ascii=False)}
#             ]
#             ai_resp = self.llm.chat_json(messages, max_tokens=3500)
#             # ai_resp doit ÃƒÂªtre un dict dÃƒÂ©jÃƒ  bien formÃƒÂ©
#             if isinstance(ai_resp, dict):
#                 return ai_resp
#             return None
#         except Exception as e:
#             print(f"Ã¢ÂÅ’ Erreur IA enrichissement: {e}")
#             return None
#
#     # ---------- IA : rÃƒÂ©sumÃƒÂ© ---------------------------------------------------
#     def generate_semantic_summary_ai(self, enriched: Dict, document_summary: str) -> Optional[str]:
#         try:
#             sys = "Tu rÃƒÂ©diges un rÃƒÂ©sumÃƒÂ© sÃƒÂ©mantique pharmaceutique concis en franÃƒÂ§ais (1-3 phrases)."
#             user = {
#                 "task": "SynthÃƒÂ©tiser le rÃƒÂ©sumÃƒÂ© sÃƒÂ©mantique intelligent.",
#                 "inputs": {
#                     "enriched_json_light": {
#                         "entities": enriched.get("entities", {}),
#                         "relations": enriched.get("relations", [])
#                     },
#                     "document_summary": document_summary
#                 }
#             }
#             messages = [
#                 {"role": "system", "content": sys},
#                 {"role": "user", "content": json.dumps(user, ensure_ascii=False)}
#             ]
#             text = self.llm.chat_text(messages, max_tokens=400)
#             if text:
#                 return text.strip().strip('"')
#             return None
#         except Exception as e:
#             print(f"Ã¢ÂÅ’ Erreur IA rÃƒÂ©sumÃƒÂ©: {e}")
#             return None
#
#     # ---------- IA : Q&A ------------------------------------------------------
#     def answer_question_ai(self, question: str, context_json: Dict, document_context: Dict,
#                            document_summary: str) -> Dict:
#         """
#         RÃƒÂ©pond via IA avec contrainte : s'appuyer UNIQUEMENT sur le contexte fourni.
#         Retourne {answer, confidence, answer_type, suggestion}
#         """
#         try:
#             sys = (
#                 "Assistant Q&A pharmaceutique. RÃƒÂ©ponds briÃƒÂ¨vement en franÃƒÂ§ais, "
#                 "UNIQUEMENT avec le contexte fourni. Si non trouvÃƒÂ©, dis-le clairement."
#             )
#             user = {
#                 "question": question,
#                 "context": {
#                     "json": context_json,
#                     "document_context": document_context,
#                     "document_summary": document_summary
#                 }
#             }
#             messages = [
#                 {"role": "system", "content": sys},
#                 {"role": "user", "content": json.dumps(user, ensure_ascii=False)}
#             ]
#             raw = self.llm.chat_json(messages, max_tokens=800)
#             # On accepte aussi un texte libre si provider ne renvoie pas JSON strict
#             if isinstance(raw, dict) and "answer" in raw:
#                 return {
#                     "answer": raw.get("answer", ""),
#                     "confidence": float(raw.get("confidence", 0.6)),
#                     "answer_type": raw.get("answer_type", "ai"),
#                     "suggestion": raw.get("suggestion", "")
#                 }
#             # Fallback texte
#             text = self.llm.chat_text(messages,
#                                       max_tokens=500) or "Je ne trouve pas cette information dans le contexte."
#             return {"answer": text, "confidence": 0.6, "answer_type": "ai", "suggestion": ""}
#         except Exception as e:
#             print(f"Ã¢ÂÅ’ Erreur IA Q&A: {e}")
#             return {"answer": "Erreur lors de la gÃƒÂ©nÃƒÂ©ration de la rÃƒÂ©ponse.", "confidence": 0.0, "answer_type": "error",
#                     "suggestion": ""}
#
#     # ---------- Fusion --------------------------------------------------------
#     def _smart_merge(self, base: Dict, ai: Dict) -> Dict:
#         """
#         Fusion douce :
#         - conserve 'document', 'metadata' du base mais peut complÃƒÂ©ter depuis IA
#         - 'entities': merge par type -> concat unique sur items
#         - 'relations': concat unique (source/type/target)
#         - 'contexts': dict update (IA prioritaire pour valeurs non vides)
#         - 'questions_answers': concat (on ÃƒÂ©vite doublons question/answer)
#         - 'semantic_summary': si IA non vide, on prend IA
#         """
#         try:
#             out = json.loads(json.dumps(base))  # deep copy
#
#             # document/metadata
#             out.setdefault("document", {})
#             out.setdefault("metadata", {})
#             ai_doc = ai.get("document") or {}
#             ai_meta = ai.get("metadata") or {}
#
#             if isinstance(ai_doc, dict):
#                 for k, v in ai_doc.items():
#                     out["document"].setdefault(k, v)
#             if isinstance(ai_meta, dict):
#                 for k, v in ai_meta.items():
#                     out["metadata"].setdefault(k, v)
#
#             # entities - gestion sÃƒÂ©curisÃƒÂ©e
#             out.setdefault("entities", {})
#             ai_entities = ai.get("entities") or {}
#             if isinstance(ai_entities, dict):
#                 for etype, eblock in ai_entities.items():
#                     out["entities"].setdefault(etype, {"items": [], "count": 0, "primary": None})
#
#                     base_items = out["entities"][etype].get("items", [])
#                     if not isinstance(base_items, list):
#                         base_items = []
#
#                     # GÃƒÂ©rer eblock qui peut ÃƒÂªtre dict ou list
#                     if isinstance(eblock, dict):
#                         ai_items = eblock.get("items", [])
#                     elif isinstance(eblock, list):
#                         ai_items = eblock
#                     else:
#                         ai_items = []
#
#                     if isinstance(ai_items, list):
#                         # index par (normalized_value) pour ÃƒÂ©viter doublons
#                         seen = {}
#                         for i in base_items:
#                             if isinstance(i, dict):
#                                 key = i.get("normalized_value") or i.get("value")
#                                 seen[key] = i
#                             elif isinstance(i, str):
#                                 seen[i] = {"value": i}
#
#                         for it in ai_items:
#                             if isinstance(it, dict):
#                                 key = it.get("normalized_value") or it.get("value")
#                                 if key and key not in seen:
#                                     base_items.append(it)
#                                     seen[key] = it
#                             elif isinstance(it, str) and it not in seen:
#                                 item_dict = {"value": it, "normalized_value": it}
#                                 base_items.append(item_dict)
#                                 seen[it] = item_dict
#
#                     out["entities"][etype]["items"] = base_items
#                     out["entities"][etype]["count"] = len(base_items)
#                     if base_items and not out["entities"][etype]["primary"]:
#                         out["entities"][etype]["primary"] = base_items[0]
#
#             # relations (dÃƒÂ© duplication simple)
#             def rkey(r):
#                 if not isinstance(r, dict):
#                     return str(r)
#                 source = r.get('source', {})
#                 target = r.get('target', {})
#                 if isinstance(source, dict) and isinstance(target, dict):
#                     return f"{r.get('type')}|{source.get('type')}:{source.get('value')}|{target.get('type')}:{target.get('value')}"
#                 return str(r)
#
#             base_rel = out.get("relations", [])
#             if not isinstance(base_rel, list):
#                 base_rel = []
#                 out["relations"] = base_rel
#
#             keys = {rkey(r) for r in base_rel}
#             ai_relations = ai.get("relations", [])
#             if isinstance(ai_relations, list):
#                 for r in ai_relations:
#                     if isinstance(r, dict) and rkey(r) not in keys:
#                         base_rel.append(r)
#                         keys.add(rkey(r))
#
#             # contexts
#             out.setdefault("contexts", {})
#             ai_contexts = ai.get("contexts") or {}
#             if isinstance(ai_contexts, dict):
#                 for k, v in ai_contexts.items():
#                     if not out["contexts"].get(k) and v:
#                         out["contexts"][k] = v
#
#             # Q&A
#             def qakey(q):
#                 if not isinstance(q, dict):
#                     return str(q)
#                 return f"{(q.get('question') or '').strip().lower()}|{(q.get('answer') or '').strip().lower()}"
#
#             base_qa = out.get("questions_answers", [])
#             if not isinstance(base_qa, list):
#                 base_qa = []
#                 out["questions_answers"] = base_qa
#
#             qa_keys = {qakey(x) for x in base_qa}
#             ai_qa = ai.get("questions_answers", [])
#             if isinstance(ai_qa, list):
#                 for qa in ai_qa:
#                     if isinstance(qa, dict) and qakey(qa) not in qa_keys:
#                         base_qa.append(qa)
#                         qa_keys.add(qakey(qa))
#
#             # summary
#             ai_sum = ai.get("semantic_summary", "")
#             if isinstance(ai_sum, str) and ai_sum.strip():
#                 out["semantic_summary"] = ai_sum.strip()
#
#             return out
#
#         except Exception as e:
#             print(f"Ã¢ÂÅ’ Erreur lors de la fusion: {e}")
#             return base
#
#     def _enrich_entity(self, entity_type: str, values: List[str], context: Dict = None) -> Dict:
#         """Enrichit une entitÃƒÂ© avec des propriÃƒÂ©tÃƒÂ©s et du contexte"""
#
#         if not values:
#             return {"items": [], "count": 0}
#
#         enriched_items = []
#
#         for value in values:
#             if not isinstance(value, str):
#                 continue
#
#             item = {
#                 "value": value,
#                 "normalized_value": self._normalize_value(value),
#                 "confidence": 1.0,
#                 "properties": {},
#                 "context": {},
#                 "extracted_from": "expert_validation"
#             }
#
#             # Enrichir selon le type
#             try:
#                 if entity_type == "Product":
#                     item.update(self._enrich_product(value, context))
#                 elif entity_type == "Dosage":
#                     item.update(self._enrich_dosage(value, context))
#                 elif entity_type == "Active_Ingredient":
#                     item.update(self._enrich_active_ingredient(value, context))
#                 elif entity_type == "Manufacturing_Site":
#                     item.update(self._enrich_manufacturing_site(value, context))
#             except Exception as e:
#                 print(f"Ã¢ÂÅ’ Erreur enrichissement {entity_type}: {e}")
#
#             enriched_items.append(item)
#
#         return {
#             "items": enriched_items,
#             "count": len(enriched_items),
#             "primary": enriched_items[0] if enriched_items else None
#         }
#
#     def _enrich_product(self, product_name: str, context: Dict = None) -> Dict:
#         """Enrichit les informations sur un produit"""
#         return {
#             "properties": {
#                 "name": product_name,
#                 "type": self._infer_product_type(product_name),
#                 "category": self._infer_category(product_name),
#                 "regulatory_status": "approved",  # Par dÃƒÂ©faut
#             },
#             "context": {
#                 "therapeutic_area": self._infer_therapeutic_area(product_name, context),
#                 "administration_route": self._infer_route(context),
#                 "target_population": self._infer_population(context)
#             }
#         }
#
#     def _enrich_dosage(self, dosage: str, context: Dict = None) -> Dict:
#         """Enrichit les informations sur un dosage"""
#         parsed = self._parse_dosage(dosage)
#         return {
#             "properties": {
#                 "value": parsed.get("value"),
#                 "unit": parsed.get("unit"),
#                 "strength": parsed.get("strength"),
#                 "concentration": parsed.get("concentration")
#             },
#             "context": {
#                 "administration_frequency": self._infer_frequency(context),
#                 "population_specific": self._check_population_specific(dosage, context),
#                 "therapeutic_window": self._infer_therapeutic_window(dosage)
#             }
#         }
#
#     def _enrich_active_ingredient(self, ingredient: str, context: Dict = None) -> Dict:
#         """Enrichit les informations sur un principe actif"""
#         return {
#             "properties": {
#                 "name": ingredient,
#                 "therapeutic_class": self._classify_ingredient(ingredient),
#                 "mechanism_of_action": self._infer_mechanism(ingredient),
#                 "molecular_formula": None  # Ãƒâ‚¬ complÃƒÂ©ter manuellement
#             },
#             "context": {
#                 "pharmacokinetics": self._infer_pharmacokinetics(ingredient),
#                 "interactions": self._infer_interactions(ingredient),
#                 "monitoring_required": self._check_monitoring_required(ingredient)
#             }
#         }
#
#     def _enrich_manufacturing_site(self, site: str, context: Dict = None) -> Dict:
#         """Enrichit les informations sur un site de fabrication"""
#         return {
#             "properties": {
#                 "name": site,
#                 "type": "manufacturing_facility",
#                 "certification": "unknown"
#             },
#             "context": {
#                 "capacity": None,
#                 "certifications": []
#             }
#         }
#
#     def _extract_relations(self, entities: Dict) -> List[Dict]:
#         """Extrait les relations entre entitÃƒÂ©s"""
#         relations = []
#
#         try:
#             # Relation produit-principe actif
#             products = self._get_entity_items(entities, "Product")
#             ingredients = self._get_entity_items(entities, "Active_Ingredient")
#
#             for product in products:
#                 for ingredient in ingredients:
#                     relations.append({
#                         "type": "contains",
#                         "source": {"type": "Product", "value": product.get("value", "")},
#                         "target": {"type": "Active_Ingredient", "value": ingredient.get("value", "")},
#                         "confidence": 0.9,
#                         "description": f"{product.get('value', '')} contient {ingredient.get('value', '')}"
#                     })
#
#             # Relation produit-dosage
#             dosages = self._get_entity_items(entities, "Dosage")
#
#             for product in products:
#                 for dosage in dosages:
#                     relations.append({
#                         "type": "has_dosage",
#                         "source": {"type": "Product", "value": product.get("value", "")},
#                         "target": {"type": "Dosage", "value": dosage.get("value", "")},
#                         "confidence": 0.95,
#                         "description": f"{product.get('value', '')} est dosÃƒÂ© Ãƒ  {dosage.get('value', '')}"
#                     })
#
#             # Relation produit-site de fabrication
#             sites = self._get_entity_items(entities, "Manufacturing_Site")
#
#             for product in products:
#                 for site in sites:
#                     relations.append({
#                         "type": "manufactured_at",
#                         "source": {"type": "Product", "value": product.get("value", "")},
#                         "target": {"type": "Manufacturing_Site", "value": site.get("value", "")},
#                         "confidence": 0.8,
#                         "description": f"{product.get('value', '')} est fabriquÃƒÂ© Ãƒ  {site.get('value', '')}"
#                     })
#
#         except Exception as e:
#             print(f"Ã¢ÂÅ’ Erreur extraction relations: {e}")
#
#         return relations
#
#     def _get_entity_items(self, entities: Dict, entity_type: str) -> List[Dict]:
#         """RÃƒÂ©cupÃƒÂ¨re les items d'un type d'entitÃƒÂ© de maniÃƒÂ¨re sÃƒÂ©curisÃƒÂ©e"""
#         entity_data = entities.get(entity_type, {})
#         if isinstance(entity_data, dict):
#             items = entity_data.get("items", [])
#             if isinstance(items, list):
#                 return [item for item in items if isinstance(item, dict)]
#         return []
#
#     def _generate_contexts(self, entities: Dict, relations: List[Dict]) -> Dict:
#         """GÃƒÂ©nÃƒÂ¨re des contextes sÃƒÂ©mantiques"""
#         contexts = {
#             "pharmaceutical": self._build_pharma_context(entities),
#             "regulatory": self._build_regulatory_context(entities),
#             "manufacturing": self._build_manufacturing_context(entities),
#             "clinical": self._build_clinical_context(entities, relations)
#         }
#         return contexts
#
#     def _generate_semantic_summary(self, enriched_json: Dict) -> str:
#         """GÃƒÂ©nÃƒÂ¨re un rÃƒÂ©sumÃƒÂ© sÃƒÂ©mantique structurÃƒÂ©"""
#         try:
#             entities = enriched_json.get("entities", {})
#             relations = enriched_json.get("relations", [])
#
#             summary_parts = []
#
#             # Description du produit principal
#             products = self._get_entity_items(entities, "Product")
#             if products:
#                 product = products[0]
#                 product_name = product.get("value", "")
#                 summary_parts.append(f"Ce document concerne {product_name}")
#
#                 # Ajout du principe actif si disponible
#                 active_ingredient = self._find_related_entity(product, "Active_Ingredient", relations)
#                 if active_ingredient:
#                     summary_parts.append(f"dont le principe actif est {active_ingredient}")
#
#                 # Ajout du dosage si disponible
#                 dosage = self._find_related_entity(product, "Dosage", relations)
#                 if dosage:
#                     summary_parts.append(f"au dosage de {dosage}")
#
#             # Information sur la fabrication
#             sites = self._get_entity_items(entities, "Manufacturing_Site")
#             if sites:
#                 site_names = [site.get("value", "") for site in sites if site.get("value")]
#                 if len(site_names) == 1:
#                     summary_parts.append(f"Il est fabriquÃƒÂ© Ãƒ  {site_names[0]}")
#                 elif len(site_names) > 1:
#                     summary_parts.append(f"Il est fabriquÃƒÂ© sur les sites suivants : {', '.join(site_names)}")
#
#             # Jointure intelligente
#             if len(summary_parts) > 1:
#                 summary = summary_parts[0]
#                 for i, part in enumerate(summary_parts[1:], 1):
#                     if i == len(summary_parts) - 1:
#                         summary += f" et {part.lower()}"
#                     else:
#                         summary += f", {part.lower()}"
#                 summary += "."
#             elif summary_parts:
#                 summary = summary_parts[0] + "."
#             else:
#                 summary = "Ce document contient des informations pharmaceutiques."
#
#             return summary
#
#         except Exception as e:
#             print(f"Ã¢ÂÅ’ Erreur gÃƒÂ©nÃƒÂ©ration rÃƒÂ©sumÃƒÂ©: {e}")
#             return "Ce document contient des informations pharmaceutiques."
#
#     # MÃƒÂ©thodes utilitaires
#     def _normalize_value(self, value: str) -> str:
#         return re.sub(r'\s+', ' ', value.strip().lower())
#
#     def _parse_dosage(self, dosage: str) -> Dict:
#         # Parse "500 mg", "10mg/ml", etc.
#         match = re.search(r'(\d+(?:\.\d+)?)\s*(\w+)', dosage)
#         if match:
#             return {
#                 "value": float(match.group(1)),
#                 "unit": match.group(2),
#                 "strength": dosage
#             }
#         return {"value": None, "unit": None, "strength": dosage}
#
#     def _infer_product_type(self, product_name: str) -> str:
#         # Logique d'infÃƒÂ©rence basique
#         if any(word in product_name.lower() for word in ['comprimÃƒÂ©', 'tablet', 'pill']):
#             return "solid_oral"
#         elif any(word in product_name.lower() for word in ['sirop', 'syrup', 'solution']):
#             return "liquid_oral"
#         elif any(word in product_name.lower() for word in ['injectable', 'injection']):
#             return "injectable"
#         return "unknown"
#
#     def _find_related_entity(self, entity: Dict, target_type: str, relations: List[Dict]) -> Optional[str]:
#         """Trouve une entitÃƒÂ© liÃƒÂ©e"""
#         try:
#             entity_value = entity.get("value", "")
#             for relation in relations:
#                 if (isinstance(relation, dict) and
#                         isinstance(relation.get("source"), dict) and
#                         isinstance(relation.get("target"), dict) and
#                         relation["source"].get("value") == entity_value and
#                         relation["target"].get("type") == target_type):
#                     return relation["target"].get("value")
#         except Exception as e:
#             print(f"Ã¢ÂÅ’ Erreur recherche entitÃƒÂ© liÃƒÂ©e: {e}")
#         return None
#
#     # Autres mÃƒÂ©thodes d'infÃƒÂ©rence Ãƒ  implÃƒÂ©menter selon les besoins...
#     def _infer_category(self, product_name: str) -> str:
#         return "pharmaceutical"
#
#     def _infer_therapeutic_area(self, product_name: str, context: Dict = None) -> str:
#         return "general"
#
#     def _infer_route(self, context: Dict = None) -> str:
#         return "oral"
#
#     def _infer_population(self, context: Dict = None) -> str:
#         return "adult"
#
#     def _infer_frequency(self, context: Dict = None) -> str:
#         return "as_needed"
#
#     def _check_population_specific(self, dosage: str, context: Dict = None) -> bool:
#         return False
#
#     def _infer_therapeutic_window(self, dosage: str) -> Dict:
#         return {"min": None, "max": None}
#
#     def _classify_ingredient(self, ingredient: str) -> str:
#         return "unknown"
#
#     def _infer_mechanism(self, ingredient: str) -> str:
#         return "unknown"
#
#     def _infer_pharmacokinetics(self, ingredient: str) -> Dict:
#         return {}
#
#     def _infer_interactions(self, ingredient: str) -> List[str]:
#         return []
#
#     def _check_monitoring_required(self, ingredient: str) -> bool:
#         return False
#
#     def _build_pharma_context(self, entities: Dict) -> Dict:
#         return {"type": "pharmaceutical_document"}
#
#     def _build_regulatory_context(self, entities: Dict) -> Dict:
#         return {"type": "regulatory_information"}
#
#     def _build_manufacturing_context(self, entities: Dict) -> Dict:
#         return {"type": "manufacturing_information"}
#
#     def _build_clinical_context(self, entities: Dict, relations: List[Dict]) -> Dict:
#         return {"type": "clinical_information"}
#
#
# # Fonction pour intÃƒÂ©grer dans les vues expert
# def enrich_document_json_for_expert(document, basic_json: Dict) -> Dict:
#     """Enrichit le JSON d'un document pour l'expert"""
#
#     try:
#         enricher = JSONEnricher()
#
#         # Contexte du document
#         document_context = {
#             "doc_type": getattr(document, 'doc_type', None),
#             "country": getattr(document, 'country', None),
#             "language": getattr(document, 'language', None),
#             "source": getattr(document, 'source', None),
#             "title": getattr(document, 'title', ''),
#             "total_pages": getattr(document, 'total_pages', 0)
#         }
#
#         # Enrichissement
#         enriched_json = enricher.enrich_basic_json(basic_json, document_context)
#
#         return enriched_json
#
#     except Exception as e:
#         print(f"Ã¢ÂÅ’ Erreur lors de l'enrichissement: {e}")
#         # Retourner une version minimale en cas d'erreur
#         return {
#             "document": basic_json.get("document", {}),
#             "metadata": {
#                 "enriched_at": timezone.now().isoformat(),
#                 "version": "2.1",
#                 "schema": "semantic_pharmaceutical",
#                 "error": str(e)
#             },
#             "entities": basic_json.get("entities", {}),
#             "relations": [],
#             "contexts": {},
#             "questions_answers": [],
#             "semantic_summary": "Erreur lors de l'enrichissement automatique."
#         }
#
# # Fonction pour intÃƒÂ©grer dans les vues expert
# def enrich_document_json_for_expert(document, basic_json: Dict) -> Dict:
#     """Enrichit le JSON d'un document pour l'expert"""
#
#     enricher = JSONEnricher()
#
#     # Contexte du document
#     document_context = {
#         "doc_type": getattr(document, 'doc_type', None),
#         "country": getattr(document, 'country', None),
#         "language": getattr(document, 'language', None),
#         "source": getattr(document, 'source', None),
#         "title": document.title,
#         "total_pages": document.total_pages
#     }
#
#     # Enrichissement
#     enriched_json = enricher.enrich_basic_json(basic_json, document_context)
#
#     return enriched_json
#
# #############
# -*- coding: utf-8 -*-
from __future__ import annotations

import json, re, logging
from typing import Any, Dict, List, Optional, Union
from django.utils import timezone

from expert.llm_client import LLMClient

logger = logging.getLogger(__name__)

Json = Dict[str, Any]


import logging
logger = logging.getLogger(__name__)

def _deepcopy(x):
    return json.loads(json.dumps(x))

def _norm(s: Optional[str]) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())



class JSONEnricher:
    """
    - Enrichit dynamiquement un JSON basique en JSON sémantique (entités, relations, contextes, Q&A, résumé)
    - Génère des descriptions sémantiques pour les relations
    - Convertit des Q&A d'expert en connaissance structurée (patch JSON)
    """
    def __init__(self) -> None:
        self.llm = LLMClient()

    # ---------------------------------------------------------------------
    #  PUBLIC: ENRICHISSEMENT DE BASE
    # ---------------------------------------------------------------------
    def enrich_basic_json(
        self,
        basic_json: Json,
        document_context: Optional[Json] = None,
        *,
        document_summary: Optional[str] = None,
        expert_relations: Optional[List[Json]] = None,
        use_ai: bool = True,
    ) -> Json:
        document_context = document_context or {}
        expert_relations = expert_relations or []

        enriched: Json = {
            "document": (basic_json.get("document") or {}) if isinstance(basic_json, dict) else {},
            "metadata": {
                "enriched_at": timezone.now().isoformat(),
                "schema": "semantic_generic",
                "version": "3.2",
                "ai_provider": "groq",
                "ai_model": getattr(self.llm, "model", None),
            },
            "entities": {},
            "relations": [],
            "contexts": {},
            "questions_answers": [],
            "semantic_summary": "",
            "tech_hints": {"suggested_schema": None, "notes": []},
        }

        # 1) ingestion d’entités existantes (tolérant aux formats)
        self._ingest_entities(enriched, basic_json)

        # 2) règles simples (si Product/Dosage/Active_Ingredient)
        enriched["relations"] = self._infer_relations(enriched["entities"])

        # 3) Q&A de base copiées
        for qa in (basic_json.get("questions_answers") or []):
            if isinstance(qa, dict):
                enriched["questions_answers"].append(qa)

        # 4) relations ajoutées par expert (si présentes)
        for r in (expert_relations or []):
            if isinstance(r, dict):
                enriched["relations"].append(r)

        # 5) contextes minimaux
        enriched["contexts"] = self._generate_contexts()

        # 6) IA : compléter entités/relations/Q&A + schéma suggéré
        ai_json = None
        if use_ai:
            ai_json = self._ai_enrich(
                basic_json=basic_json,
                document_context=document_context,
                document_summary=document_summary or "",
                expert_relations=expert_relations or [],
            )

        if ai_json:
            enriched = self._smart_merge(enriched, ai_json)

        # 7) schéma suggéré si l’IA n’a rien renvoyé
        if not (enriched.get("tech_hints") or {}).get("suggested_schema"):
            enriched["tech_hints"]["suggested_schema"] = self._suggest_schema_heuristic(basic_json, document_context)

        # 8) résumé sémantique
        if use_ai:
            ai_sum = self._ai_summary(enriched, document_summary or "")
            if ai_sum:
                enriched["semantic_summary"] = ai_sum
        if not enriched.get("semantic_summary"):
            enriched["semantic_summary"] = self._rule_summary(enriched)

        return enriched

    def extract_relations_from_paragraph(
            self,
            *,
            text: str,
            current_json: Dict[str, Any],
            document_context: Optional[Dict[str, Any]] = None,
            document_summary: str = "",
            hint: str = "",
    ) -> Dict[str, Any]:
        """
        Convertit un paragraphe libre en PATCH JSON {entities, relations}.
        - Entités: dict {Type: {items: [{value, normalized_value}]}}
        - Relations: [{type, source:{type,value}, target:{type,value}, description?}]
        Ajoute/complète la description via le LLM (fluent) en s'appuyant sur le contexte courant.
        """
        # 1) Appel LLM → JSON brut
        try:
            evidence = self._build_evidence_pack(current_json or {}, document_context or {}, document_summary or "")

            sys = (
                "Extrait du texte des ENTITÉS et RELATIONS MÉTIER pertinentes pour la pharmaco/réglementaire. "
                "Retourne STRICTEMENT un JSON {entities, relations}. "
                "entities est un objet {EntityType: {items: [{value, normalized_value}]}}. "
                "relations est une liste d'objets {type, source:{type,value}, target:{type,value}}. "
                "N'invente pas de données ; base-toi sur le texte et, si utile, l'évidence fournie. "
                "Types métier suggérés: Product, Active_Ingredient, Dosage, Procedure, Regulation, Organization, Date, "
                "Product Category, Modification Type, Manufacturing_Site. "
                "Types de relation suggérés: contains, has_dosage, manufactured_at, manufactured_by, approved_for, "
                "applies_to, defines, issued_by, effective_on, used_for, contraindicated_with, interacts_with, related_to."
            )

            user = {
                "text": text,
                "hint": hint,
                "document_context": {
                    "title": (document_context or {}).get("title", ""),
                    "country": (document_context or {}).get("country", ""),
                    "language": (document_context or {}).get("language", ""),
                },
                "evidence": evidence,
                "constraints": {
                    "json_only": True,
                    "entity_item_format": {"value": "string", "normalized_value": "string"},
                    "relation_format": {"type": "string", "source": {"type": "string", "value": "string"},
                                        "target": {"type": "string", "value": "string"}}
                }
            }
            msgs = [{"role": "system", "content": sys},
                    {"role": "user", "content": json.dumps(user, ensure_ascii=False)}]
            raw = self.llm.chat_json(msgs, max_tokens=1400) or {}
        except Exception:
            raw = {}

        # 2) Normalisation
        patch: Dict[str, Any] = {"entities": {}, "relations": []}

        # Entities → dict {Type: {items:[...]}}
        ents = raw.get("entities")
        if isinstance(ents, dict):
            for et, block in ents.items():
                items = []
                if isinstance(block, dict) and isinstance(block.get("items"), list):
                    items = block["items"]
                elif isinstance(block, list):
                    items = block
                norm_items = []
                for it in (items or []):
                    if isinstance(it, dict):
                        v = (it.get("value") or "").strip()
                    else:
                        v = str(it).strip()
                    if v:
                        norm_items.append({"value": v, "normalized_value": _norm(v)})
                patch["entities"][et] = {"items": norm_items, "count": len(norm_items),
                                         "primary": (norm_items[0] if norm_items else None)}

        # Relations → liste + descriptions
        relations = raw.get("relations") if isinstance(raw.get("relations"), list) else []
        out_rels = []
        for r in relations:
            if not isinstance(r, dict):
                continue
            s, t, rt = r.get("source"), r.get("target"), r.get("type")
            if not (isinstance(s, dict) and isinstance(t, dict) and isinstance(rt, str) and s.get("type") and t.get(
                    "type")):
                continue
            # Description via LLM (fluent) avec evidence (current_json + summary)
            desc = self.describe_relation_ai_fluent(
                s, rt, t,
                document_context=document_context,
                enriched=current_json or {},
                document_summary=document_summary or ""
            )
            out_rels.append({
                "type": rt.strip(),
                "source": {"type": s.get("type", ""), "value": s.get("value", "")},
                "target": {"type": t.get("type", ""), "value": t.get("value", "")},
                "description": desc,
                "confidence": r.get("confidence", 0.9),
                "created_by": "expert_paragraph",
                "created_at": timezone.now().isoformat()
            })
        patch["relations"] = out_rels

        return patch

    # NEW
    def _relation_evidence(self,
                           enriched: Dict[str, Any],
                           source: Dict[str, Any],
                           rtype: str,
                           target: Dict[str, Any],
                           document_summary: str = "") -> Dict[str, Any]:
        """Construit un mini 'evidence pack' centré sur (source, rtype, target)."""
        rels = enriched.get("relations") if isinstance(enriched.get("relations"), list) else []
        neighbors = []
        s_val, t_val = (source or {}).get("value", ""), (target or {}).get("value", "")
        s_typ, t_typ = (source or {}).get("type", ""), (target or {}).get("type", "")

        # voisins: même source/target ou même type
        for r in rels:
            if not isinstance(r, dict):
                continue
            S, T = r.get("source") or {}, r.get("target") or {}
            if not (isinstance(S, dict) and isinstance(T, dict)):
                continue
            cond = (
                    (S.get("value") == s_val and S.get("type") == s_typ) or
                    (T.get("value") == t_val and T.get("type") == t_typ) or
                    (r.get("type") == rtype)
            )
            if cond:
                neighbors.append({
                    "type": r.get("type"),
                    "source": f"{S.get('type', '')}::{S.get('value', '')}",
                    "target": f"{T.get('type', '')}::{T.get('value', '')}",
                    "description": r.get("description", "")
                })
            if len(neighbors) >= 8:
                break

        stored_qa = []
        for x in (enriched.get("questions_answers") or []):
            if isinstance(x, dict) and x.get("question") and x.get("answer"):
                stored_qa.append({"q": x["question"], "a": x["answer"]})
            if len(stored_qa) >= 5:
                break

        return {
            "summary": document_summary or "",
            "neighbors": neighbors,
            "stored_qa": stored_qa
        }

    # CHANGE SIGNATURE (ajout enriched + document_summary)
    def describe_relation_ai_fluent(
            self,
            source: Dict[str, Any],
            rtype: str,
            target: Dict[str, Any],
            document_context: Optional[Dict[str, Any]] = None,
            enriched: Optional[Dict[str, Any]] = None,
            document_summary: str = "",
    ) -> str:
        """
        Génère UNE phrase FR naturelle via LLM, basée sur un evidence pack local.
        Fallback: phrase déterministe.
        """
        try:
            rel = {
                "type": (rtype or "").strip().lower(),
                "source": {"type": (source or {}).get("type", ""), "value": (source or {}).get("value", "")},
                "target": {"type": (target or {}).get("type", ""), "value": (target or {}).get("value", "")},
            }
            ev = self._relation_evidence(enriched or {}, source, rtype, target, document_summary=document_summary)

            sys = (
                "Tu rédiges UNE phrase en français qui décrit précisément la relation MÉTIER ci-dessous, "
                "en t'appuyant UNIQUEMENT sur le résumé/voisins/Q&A fournis. "
                "La phrase doit être claire, naturelle et informative (niveau expert), sans guillemets, sans puces."
            )
            user = {
                "relation": rel,
                "document": {
                    "title": (document_context or {}).get("title", ""),
                    "country": (document_context or {}).get("country", ""),
                    "language": (document_context or {}).get("language", "")
                },
                "evidence": ev,
                "style": {
                    "avoid": ["phrases génériques", "traduction littérale des labels", "doublons"],
                    "prefer": ["vocabulaire réglementaire/pharma", "accords corrects", "concision (<30 mots)"]
                }
            }
            msgs = [{"role": "system", "content": sys},
                    {"role": "user", "content": json.dumps(user, ensure_ascii=False)}]
            text = self.llm.chat_text(msgs, max_tokens=120)
            if text:
                return text.strip().strip('"')
        except Exception as e:
            logger.warning("describe_relation_ai_fluent failed: %s", e)
        # Fallback déterministe
        return self.describe_relation_ai(source, rtype, target, document_context)

    # CHANGE SIGNATURE: + document_summary
    def ensure_relation_descriptions(
            self, enriched: Dict[str, Any],
            document_context: Optional[Dict[str, Any]] = None,
            document_summary: str = "",
            prefer_fluent_ai: bool = True
    ) -> Dict[str, Any]:
        try:
            rels = enriched.get("relations")
            if not isinstance(rels, list):
                return enriched
            for r in rels:
                if not isinstance(r, dict):
                    continue
                if (r.get("description") or "").strip():
                    continue
                src, tgt = r.get("source") or {}, r.get("target") or {}
                rtype = (r.get("type") or "").strip().lower()
                r["description"] = (
                    self.describe_relation_ai_fluent(src, rtype, tgt,
                                                     document_context=document_context,
                                                     enriched=enriched,
                                                     document_summary=document_summary)
                    if prefer_fluent_ai else
                    self.describe_relation_ai(src, rtype, tgt, document_context)
                )
            return enriched
        except Exception as e:
            logger.warning("ensure_relation_descriptions failed: %s", e)
            return enriched

    # ---------------------------------------------------------------------
    #  PUBLIC: Q&A — RÉPONSE À UNE QUESTION (recherche dans le contexte)
    # ---------------------------------------------------------------------
    def answer_question_ai(
        self,
        question: str,
        context_json: Union[Json, List[Json]],
        document_context: Optional[Json],
        document_summary: str,
    ) -> Json:
        """
        Répond en utilisant UNIQUEMENT les évidences extraites des JSON fournis (tolérant à basic/enriched/list).
        """
        sources: List[Json] = []
        if isinstance(context_json, list):
            sources = [s for s in context_json if isinstance(s, dict)]
        elif isinstance(context_json, dict):
            sources = [context_json]

        evidences: List[str] = []
        mem: List[Dict[str, Any]] = []  # corrections expert

        def add_ev(s: str):
            s = (s or "").strip()
            if s:
                evidences.append(s)

        for js in sources:
            # entités
            for et, block in (js.get("entities") or {}).items():
                items = block.get("items") if isinstance(block, dict) else (block if isinstance(block, list) else [])
                for it in (items or []):
                    val = it.get("value") if isinstance(it, dict) else str(it)
                    if val:
                        add_ev(f"{et} : {val}")
            # relations
            for r in (js.get("relations") or []):
                if isinstance(r, dict):
                    s, t = r.get("source"), r.get("target")
                    if isinstance(s, dict) and isinstance(t, dict):
                        add_ev(f"{s.get('type')}:{s.get('value')} --{r.get('type')}--> {t.get('type')}:{t.get('value')}")
                else:
                    add_ev(str(r))
            # résumés
            for k in ("semantic_summary", "summary", "resume", "résumé"):
                txt = js.get(k) or (js.get("document") or {}).get(k)
                if isinstance(txt, str):
                    add_ev(txt)
            # Q&A existantes (mémoire)
            for qa in (js.get("questions_answers") or []):
                if isinstance(qa, dict) and qa.get("question") and qa.get("answer"):
                    is_exp = qa.get("answer_type") == "expert_correction" or qa.get("created_by") == "expert"
                    mem.append({"q": qa["question"], "a": qa["answer"], "is_exp": is_exp})
                    add_ev(f"Q: {qa['question']} | R: {qa['answer']}")

        # similarité simple pour mémorisation prioritaire
        def jaccard(a: str, b: str) -> float:
            A = set(re.findall(r"[a-zA-ZÀ-ÿ0-9]+", _norm(a)))
            B = set(re.findall(r"[a-zA-ZÀ-ÿ0-9]+", _norm(b)))
            if not A or not B:
                return 0.0
            return len(A & B) / float(len(A | B))

        best = None
        best_score = 0.0
        for it in mem:
            sc = jaccard(question, it["q"]) + (0.05 if it["is_exp"] else 0.0)
            if sc > best_score:
                best, best_score = it, sc
        if best and best_score >= 0.90:
            return {"answer": best["a"], "confidence": 0.95, "answer_type": "expert_memory", "suggestion": ""}

        # on limite les évidences
        scored = sorted([(jaccard(question, s), s) for s in evidences], key=lambda x: x[0], reverse=True)
        pack = [s for _, s in scored[:50]]

        sys = (
            "Assistant Q&A basé sur contexte. Réponds uniquement avec les 'evidences'. "
            "Si impossible, renvoie un JSON: {answer:'Information introuvable dans le contexte fourni.', confidence:0.4, answer_type:'no_match', suggestion:'…'}"
        )
        user = {
            "question": question,
            "document_context": document_context or {},
            "document_summary": document_summary or "",
            "evidences": pack,
            "few_shots": [m for m in mem if m.get("is_exp")][:4],
            "constraints": {"json_only": True, "language": "fr"},
        }
        msgs = [{"role": "system", "content": sys}, {"role": "user", "content": json.dumps(user, ensure_ascii=False)}]
        raw = self.llm.chat_json(msgs, max_tokens=900)
        if isinstance(raw, dict) and "answer" in raw:
            conf = raw.get("confidence", 0.6)
            try:
                conf = float(conf)
                if not (conf == conf and conf >= 0):
                    conf = 0.6
            except Exception:
                conf = 0.6
            return {
                "answer": raw.get("answer", "") or "",
                "confidence": conf,
                "answer_type": raw.get("answer_type", "ai") or "ai",
                "suggestion": raw.get("suggestion", "") or "",
            }
        txt = self.llm.chat_text(msgs, max_tokens=500) or "Information introuvable dans le contexte fourni."
        return {"answer": txt, "confidence": 0.6, "answer_type": "ai", "suggestion": ""}

    # ---------------------------------------------------------------------
    #  PUBLIC: DESCRIPTION SÉMANTIQUE D’UNE RELATION
    # ---------------------------------------------------------------------
    def _iter_entity_items(self, entities: Any) -> Dict[str, List[Dict[str, Any]]]:
        """Retourne {etype: [items...]} de manière tolérante (dict ou list)."""
        if isinstance(entities, dict):
            out = {}
            for et, block in entities.items():
                if isinstance(block, dict):
                    items = block.get("items") if isinstance(block.get("items"), list) else []
                elif isinstance(block, list):
                    items = block
                else:
                    items = []
                # normalise en dicts
                norm_items = []
                for it in items:
                    if isinstance(it, dict):
                        norm_items.append(it)
                    elif isinstance(it, str):
                        norm_items.append({"value": it, "normalized_value": _norm(it)})
                out[et] = norm_items
            return out
        elif isinstance(entities, list):
            out = {}
            for e in entities:
                if isinstance(e, dict) and e.get("type"):
                    items = e.get("items") if isinstance(e.get("items"), list) else []
                    out[e["type"]] = [it if isinstance(it, dict) else {"value": it, "normalized_value": _norm(it)} for
                                      it in items]
            return out
        return {}

    def _build_evidence_pack(self, context_json: Dict[str, Any], document_context: Dict[str, Any],
                             document_summary: str) -> Dict[str, Any]:
        """
        Construit un 'evidence pack' lisible par le LLM à partir du JSON (entities, relations, Q&A, résumé).
        """
        entities = self._iter_entity_items(context_json.get("entities"))
        relations = context_json.get("relations") if isinstance(context_json.get("relations"), list) else []
        qa = context_json.get("questions_answers") if isinstance(context_json.get("questions_answers"), list) else []

        triples = []
        for r in relations:
            if not isinstance(r, dict):
                continue
            s, t, rt = r.get("source"), r.get("target"), r.get("type")
            if isinstance(s, dict) and isinstance(t, dict) and isinstance(rt, str):
                triples.append({
                    "type": rt,
                    "source": f"{s.get('type', '')}::{s.get('value', '')}",
                    "target": f"{t.get('type', '')}::{t.get('value', '')}",
                    "description": r.get("description", "")
                })

        entity_facts = []
        for et, items in entities.items():
            for it in items:
                props = it.get("properties") if isinstance(it.get("properties"), dict) else {}
                val = it.get("value") or ""
                if props:
                    entity_facts.append({"entity": f"{et}::{val}", "properties": props})

        stored_qa = []
        for x in qa:
            if isinstance(x, dict) and x.get("question") and x.get("answer"):
                stored_qa.append({"q": x["question"], "a": x["answer"]})

        return {
            "summary": document_summary or "",
            "doc_context": document_context or {},
            "triples": triples,
            "entity_facts": entity_facts,
            "stored_qa": stored_qa,
        }

    def describe_relation_ai(self, source: Dict[str, Any], rtype: str, target: Dict[str, Any],
                             document_context: Optional[Dict[str, Any]] = None) -> str:
        rel_label = {
            "contains": "contient",
            "has_dosage": "a pour dosage",
            "manufactured_at": "est fabriqué à",
            "manufactured_by": "est fabriqué par",
            "approved_for": "est approuvé pour",
            "applies_to": "s'applique à",
            "defines": "définit",
            "issued_by": "est émis par",
            "effective_on": "est effectif le",
            "used_for": "est utilisé pour",
            "contraindicated_with": "est contre-indiqué avec",
            "interacts_with": "interagit avec",
            "related_to": "est lié à",
        }.get(rtype, rtype.replace("_", " "))
        s_val = (source or {}).get("value") or ""
        t_val = (target or {}).get("value") or ""
        s_typ = (source or {}).get("type") or ""
        t_typ = (target or {}).get("type") or ""
        if s_val and t_val: return f"{s_val} {rel_label} {t_val}"
        if s_typ and t_val: return f"{s_typ} {rel_label} {t_val}"
        if s_val and t_typ: return f"{s_val} {rel_label} {t_typ}"
        return rel_label.strip()

    # ---------------------------------------------------------------------
    #  PUBLIC: CONSTRUIRE UNE CONNAISSANCE À PARTIR D’UNE Q&A D’EXPERT
    # ---------------------------------------------------------------------
    def patch_from_expert_qa(
        self,
        question: str,
        answer: str,
        current_json: Json,
        document_context: Optional[Json] = None,
        tags: Optional[List[str]] = None,
    ) -> Json:
        """
        Utilise le LLM pour extraire les entités et relations pertinentes de la Q&A.
        Retourne un PATCH JSON (à fusionner dans le JSON enrichi courant).
        """
        tags = tags or []
        try:
            sys = (
                "Extrait du couple (question, réponse) les entités et relations METIER. "
                "Ne crée pas d’entités fantômes: base-toi sur la sémantique de la réponse. "
                "Retourne un JSON STRICT avec clés: {entities, relations, qa}."
            )
            user = {
                "question": question,
                "answer": answer,
                "current_entities_light": (current_json or {}).get("entities", {}),
                "document_context": document_context or {},
                "constraints": {
                    "language": "fr",
                    "json_only": True,
                    "entity_item_format": {"value": "string", "normalized_value": "string"},
                    "relation_format": {"type": "string", "source": {"type": "string", "value": "string"}, "target": {"type": "string", "value": "string"}},
                },
                "hints": [
                    "Si la réponse parle de dosage: crée une relation has_dosage Product→Dosage.",
                    "Si c’est réglementaire: Regulation→Procedure (defines), Regulation→Product Category (applies_to).",
                ],
            }
            msgs = [{"role": "system", "content": sys}, {"role": "user", "content": json.dumps(user, ensure_ascii=False)}]
            out = self.llm.chat_json(msgs, max_tokens=1200) or {}
        except Exception:
            out = {}

        # Normalisation/Défaut si IA vide
        patch: Json = {"entities": {}, "relations": [], "qa": {}}

        # Entities
        if isinstance(out.get("entities"), dict):
            patch["entities"] = out["entities"]

        # Relations + descriptions générées
        rels = []
        for r in (out.get("relations") or []):
            if not isinstance(r, dict):
                continue
            src, tgt = r.get("source"), r.get("target")
            if not (isinstance(src, dict) and isinstance(tgt, dict) and r.get("type")):
                continue
            desc = self.describe_relation_ai(src, r["type"], tgt, document_context=document_context)
            r = {**r, "description": desc, "confidence": r.get("confidence", 0.9), "created_by": "expert_qa"}
            rels.append(r)
        patch["relations"] = rels

        # Q&A enrichie
        patch["qa"] = {
            "question": question,
            "answer": answer,
            "confidence": 1.0,
            "answer_type": "expert_correction",
            "created_by": "expert",
            "created_at": timezone.now().isoformat(),
            "tags": tags,
            # optionnel: l’IA peut renvoyer entity_refs; sinon on infère grossièrement
            "entity_refs": out.get("qa", {}).get("entity_refs", []),
        }

        # Fallback: si aucune ref IA -> on linke par mentions exactes connues
        if not patch["qa"]["entity_refs"]:
            try:
                ent = (current_json or {}).get("entities", {}) or {}
                for et, block in ent.items():
                    items = block.get("items") if isinstance(block, dict) else []
                    for it in (items or []):
                        val = (it.get("value") or "").strip()
                        if val and (val.lower() in (question.lower() + " " + answer.lower())):
                            patch["qa"]["entity_refs"].append({"type": et, "value": val})
            except Exception:
                pass

        return patch

    # ---------------------------------------------------------------------
    #  HELPERS: appliquer un patch & ajouter relation avec auto-description
    # ---------------------------------------------------------------------
    def apply_patch(self, enriched: Json, patch: Json) -> Json:
        out = _deepcopy(enriched)
        out.setdefault("entities", {})
        out.setdefault("relations", [])
        out.setdefault("questions_answers", [])

        # merge entities
        for et, block in (patch.get("entities") or {}).items():
            out["entities"].setdefault(et, {"items": [], "count": 0, "primary": None})
            base_items = out["entities"][et]["items"] or []
            seen = {_norm(i.get("normalized_value") or i.get("value", "")): True for i in base_items if isinstance(i, dict)}
            items = block.get("items") if isinstance(block, dict) else (block if isinstance(block, list) else [])
            for it in (items or []):
                if isinstance(it, dict):
                    key = _norm(it.get("normalized_value") or it.get("value") or "")
                    if key and key not in seen:
                        base_items.append(it); seen[key] = True
                elif isinstance(it, str):
                    key = _norm(it)
                    if key and key not in seen:
                        base_items.append({"value": it, "normalized_value": key}); seen[key] = True
            out["entities"][et]["items"] = base_items
            out["entities"][et]["count"] = len(base_items)
            if base_items and not out["entities"][et]["primary"]:
                out["entities"][et]["primary"] = base_items[0]

        # merge relations (dedupe)
        def rkey(r: Any) -> str:
            if not isinstance(r, dict):
                return str(r)
            s, t = r.get("source", {}), r.get("target", {})
            if isinstance(s, dict) and isinstance(t, dict):
                return f"{r.get('type')}|{s.get('type')}:{s.get('value')}|{t.get('type')}:{t.get('value')}"
            return str(r)

        base_rel = out.get("relations", []) or []
        keys = {rkey(r) for r in base_rel if isinstance(r, dict)}
        for r in (patch.get("relations") or []):
            if isinstance(r, dict):
                k = rkey(r)
                if k not in keys:
                    base_rel.append(r); keys.add(k)
        out["relations"] = base_rel

        # append QA
        qa = patch.get("qa")
        if isinstance(qa, dict) and qa.get("question") and qa.get("answer"):
            out["questions_answers"].append(qa)

        return out

    def add_relation_with_autodescription(
        self,
        enriched: Json,
        *,
        source_type: str,
        source_value: str,
        relation_type: str,
        target_type: str,
        target_value: str,
        description: Optional[str],
        document_context: Optional[Json] = None,
        created_by: str = "expert",
    ) -> Json:
        src = {"type": source_type, "value": source_value}
        tgt = {"type": target_type, "value": target_value}

        desc = description or self.describe_relation_ai(src, relation_type, tgt, document_context=document_context)
        rel = {
            "type": relation_type,
            "source": src,
            "target": tgt,
            "description": desc,
            "confidence": 0.95,
            "created_by": created_by,
            "created_at": timezone.now().isoformat(),
        }
        patch = {"entities": {}, "relations": [rel], "qa": {}}
        return self.apply_patch(enriched, patch)

    def _coerce_ai_json(self, ai: Any) -> Dict[str, Any]:
        """
        Normalise la sortie LLM pour garantir les bons types :
        - document, metadata, contexts : dict
        - entities : dict (convertit une éventuelle liste [{type, items}] -> dict)
        - relations, questions_answers : list
        - semantic_summary : str (si fourni)
        - suggested_schema : déplacé sous tech_hints.suggested_schema
        """
        if not isinstance(ai, dict):
            return {}

        out: Dict[str, Any] = {}

        # document / metadata
        out["document"] = ai.get("document") if isinstance(ai.get("document"), dict) else {}
        out["metadata"] = ai.get("metadata") if isinstance(ai.get("metadata"), dict) else {}

        # entities: dict attendu ; si list -> {type: {items:[...]}}
        ents = ai.get("entities")
        if isinstance(ents, dict):
            out["entities"] = ents
        elif isinstance(ents, list):
            conv: Dict[str, Any] = {}
            for e in ents:
                if isinstance(e, dict) and e.get("type"):
                    items = e.get("items")
                    if isinstance(items, list):
                        conv[e["type"]] = {
                            "items": items,
                            "count": len(items),
                            "primary": items[0] if items else None,
                        }
            out["entities"] = conv
        else:
            out["entities"] = {}

        # relations / Q&A / contexts
        out["relations"] = ai.get("relations") if isinstance(ai.get("relations"), list) else []
        out["questions_answers"] = ai.get("questions_answers") if isinstance(ai.get("questions_answers"), list) else []
        out["contexts"] = ai.get("contexts") if isinstance(ai.get("contexts"), dict) else {}

        # résumé
        if isinstance(ai.get("semantic_summary"), str):
            out["semantic_summary"] = ai["semantic_summary"]

        # suggested_schema -> tech_hints.suggested_schema
        tech = ai.get("tech_hints") if isinstance(ai.get("tech_hints"), dict) else {}
        sug = ai.get("suggested_schema") if isinstance(ai.get("suggested_schema"), dict) else tech.get(
            "suggested_schema")
        if isinstance(sug, dict):
            out.setdefault("tech_hints", {})["suggested_schema"] = sug

        return out

    # ---------------------------------------------------------------------
    #  IA ENRICH — entités/relations/Q&A + suggested_schema
    # ---------------------------------------------------------------------
    def _ai_enrich(
            self,
            *,
            basic_json: Dict[str, Any],
            document_context: Dict[str, Any],
            document_summary: str,
            expert_relations: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        try:
            sys = (
                "Tu renvoies un JSON STRICT avec {document, metadata, entities, relations, contexts, "
                "questions_answers, semantic_summary, suggested_schema}. "
                "Les relations doivent être MÉTIER (pas techniques)."
            )
            user = {
                "instruction": "Compléter/Augmenter le JSON pour exploitation graphe et lecture humaine.",
                "inputs": {
                    "basic_json": basic_json or {},
                    "document_context": document_context or {},
                    "document_summary": document_summary or "",
                    "expert_relations": expert_relations or [],
                },
                "constraints": {
                    "language": "fr",
                    "json_only": True,
                    "entity_format": {"items": [{"value": "string", "normalized_value": "string"}]},
                    "relation_format": {
                        "type": "string",
                        "source": {"type": "string", "value": "string"},
                        "target": {"type": "string", "value": "string"},
                        "description": "string",
                    },
                    "suggested_schema_format": {
                        "entity_types": [
                            {"name": "string", "description": "string", "example_values": ["string"],
                             "properties": ["string"]}
                        ],
                        "relation_types": [
                            {"name": "string", "description": "string", "source_types": ["string"],
                             "target_types": ["string"]}
                        ],
                    },
                },
                "hints": [
                    "Réglementaire: Regulation→Procedure (defines), Regulation→Product Category (applies_to), Regulation→Organization (issued_by), Regulation→Date (effective_on).",
                    "Produit: Product→Active_Ingredient (contains), Product→Dosage (has_dosage), Product→Manufacturing_Site (manufactured_at).",
                    "Ajoute des 'description' naturelles en français pour chaque relation.",
                ],
            }

            msgs = [
                {"role": "system", "content": sys},
                {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
            ]
            raw = self.llm.chat_json(msgs, max_tokens=3200)

            # Normalisation stricte des types (clé contre les 'list has no attribute items/get')
            out = self._coerce_ai_json(raw)

            # Génère une description sémantique si manquante
            for r in (out.get("relations") or []):
                if isinstance(r, dict) and not r.get("description"):
                    s, t = r.get("source"), r.get("target")
                    if isinstance(s, dict) and isinstance(t, dict):
                        r["description"] = self.describe_relation_ai(s, r.get("type", "related_to"), t,
                                                                     document_context=document_context)

            # Déplace suggested_schema éventuel sous tech_hints.suggested_schema (déjà fait par _coerce_ai_json)
            return out if out else None

        except Exception as e:
            logger.warning("AI enrich failed: %s", e)
            return None

    # ---------------------------------------------------------------------
    #  RÉSUMÉS
    # ---------------------------------------------------------------------
    def _ai_summary(self, enriched: Json, document_summary: str) -> Optional[str]:
        try:
            sys = "Rédige un résumé (1-3 phrases) en français, fidèle au JSON et orienté métier."
            user = {"enriched_light": {"entities": enriched.get("entities", {}), "relations": enriched.get("relations", [])},
                    "document_summary": document_summary or ""}
            msgs = [{"role": "system", "content": sys}, {"role": "user", "content": json.dumps(user, ensure_ascii=False)}]
            txt = self.llm.chat_text(msgs, max_tokens=250)
            return (txt or "").strip().strip('"') or None
        except Exception:
            return None

    def _rule_summary(self, enriched: Json) -> str:
        ents = enriched.get("entities", {}) or {}
        any_type = next(iter(ents.keys()), None)
        if any_type:
            v = ""
            block = ents.get(any_type, {})
            items = block.get("items", []) if isinstance(block, dict) else []
            if items and isinstance(items[0], dict):
                v = items[0].get("value", "")
            return f"Ce document contient des informations structurées sur « {any_type} »{(' : ' + v) if v else ''}."
        return "Ce document contient des informations structurées."

    # ---------------------------------------------------------------------
    #  INGESTION / RELATIONS RÈGLES
    # ---------------------------------------------------------------------
    def _ingest_entities(self, enriched: Json, basic_json: Json) -> None:
        enriched["entities"] = {}
        ent_block = (basic_json or {}).get("entities", {}) if isinstance(basic_json, dict) else {}
        if not isinstance(ent_block, dict):
            return
        for etype, payload in ent_block.items():
            values = self._normalize_values(payload)
            items = [{"value": v, "normalized_value": _norm(v), "confidence": 1.0, "properties": {}, "context": {}, "extracted_from": "auto"} for v in values]
            enriched["entities"][etype] = {"items": items, "count": len(items), "primary": items[0] if items else None}

    @staticmethod
    def _normalize_values(payload: Union[List, Dict, str, None]) -> List[str]:
        if not payload:
            return []
        if isinstance(payload, str):
            return [payload]
        if isinstance(payload, list):
            out = []
            for it in payload:
                if isinstance(it, str):
                    out.append(it)
                elif isinstance(it, dict):
                    out.append(str(it.get("value") or it.get("name") or ""))
            return [x for x in out if x]
        if isinstance(payload, dict):
            return JSONEnricher._normalize_values(payload.get("items", []) or [])
        return []

    def _infer_relations(self, entities: Json) -> List[Json]:
        rels: List[Json] = []
        prod = self._entity_items(entities, "Product")
        ingr = self._entity_items(entities, "Active_Ingredient")
        dos = self._entity_items(entities, "Dosage")
        for p in prod:
            for a in ingr:
                rels.append({
                    "type": "contains",
                    "source": {"type": "Product", "value": p["value"]},
                    "target": {"type": "Active_Ingredient", "value": a["value"]},
                    "confidence": 0.85,
                    "description": f"{p['value']} contient {a['value']}."
                })
            for d in dos:
                rels.append({
                    "type": "has_dosage",
                    "source": {"type": "Product", "value": p["value"]},
                    "target": {"type": "Dosage", "value": d["value"]},
                    "confidence": 0.9,
                    "description": f"{p['value']} est dosé à {d['value']}."
                })
        return rels

    @staticmethod
    def _entity_items(entities: Json, etype: str) -> List[Json]:
        block = entities.get(etype, {})
        if isinstance(block, dict):
            items = block.get("items", []) or []
            return [i for i in items if isinstance(i, dict) and i.get("value")]
        return []

    @staticmethod
    def _generate_contexts() -> Json:
        return {
            "pharmaceutical": {"type": "pharmaceutical_document"},
            "regulatory": {"type": "regulatory_information"},
            "manufacturing": {"type": "manufacturing_information"},
            "clinical": {"type": "clinical_information"},
        }

    def _suggest_schema_heuristic(self, basic_json: Json, document_context: Json) -> Json:
        title = (document_context or {}).get("title") or (basic_json.get("document", {}) if isinstance(basic_json, dict) else {}).get("title") or ""
        title_l = _norm(title)
        present_types = list((basic_json.get("entities", {}) or {}).keys()) if isinstance(basic_json, dict) else []

        entity_types = []
        relation_types = []

        if any(k in title_l for k in ["règlement", "regulation", "directive", "lignes directrices", "guidelines"]):
            base_entities = [
                ("Regulation", "Texte juridique (ex: Règlement (CE) n° 1234/2008)."),
                ("Procedure", "Procédure réglementaire (centralisée, MR, nationale)."),
                ("Modification Type", "Catégories IA/IB/II."),
                ("Organization", "Agence/Institution émettrice."),
                ("Date", "Dates clés (entrée en vigueur, publication)."),
                ("Product Category", "Humain / Vétérinaire."),
            ]
            for name, desc in base_entities:
                entity_types.append({"name": name, "description": desc, "example_values": [], "properties": []})
            relation_types = [
                {"name": "defines", "description": "Le règlement définit des procédures ou catégories", "source_types": ["Regulation"], "target_types": ["Procedure", "Modification Type"]},
                {"name": "applies_to", "description": "Le règlement s’applique à une catégorie de produits", "source_types": ["Regulation"], "target_types": ["Product Category"]},
                {"name": "issued_by", "description": "Le règlement est émis par une organisation", "source_types": ["Regulation"], "target_types": ["Organization"]},
                {"name": "effective_on", "description": "Date d’entrée en vigueur", "source_types": ["Regulation"], "target_types": ["Date"]},
                {"name": "used_for_modification", "description": "Une procédure est utilisée pour une catégorie de modification", "source_types": ["Procedure"], "target_types": ["Modification Type"]},
            ]
        else:
            for t in present_types:
                entity_types.append({"name": t, "description": f"Entité détectée « {t} ».", "example_values": [], "properties": []})
            relation_types = [{"name": "related_to", "description": "Relation générique", "source_types": present_types or ["*"], "target_types": present_types or ["*"]}]

        return {"entity_types": entity_types, "relation_types": relation_types}

    # ---------------------------------------------------------------------
    #  FUSION DOUCE
    # ---------------------------------------------------------------------
    def _smart_merge(self, base: Dict[str, Any], ai: Dict[str, Any]) -> Dict[str, Any]:
        out = _deepcopy(base)

        # document (type-safe)
        out.setdefault("document", {})
        ai_doc = ai.get("document")
        if isinstance(ai_doc, dict):
            for k, v in ai_doc.items():
                if out["document"].get(k) in (None, "", [], {}):
                    out["document"][k] = v

        # metadata (type-safe)
        out.setdefault("metadata", {})
        ai_meta = ai.get("metadata")
        if isinstance(ai_meta, dict):
            for k, v in ai_meta.items():
                if out["metadata"].get(k) in (None, "", [], {}):
                    out["metadata"][k] = v

        # entities
        out.setdefault("entities", {})
        ai_entities = ai.get("entities")
        if isinstance(ai_entities, dict):
            for et, block in ai_entities.items():
                out["entities"].setdefault(et, {"items": [], "count": 0, "primary": None})
                base_items = out["entities"][et].get("items") or []
                if not isinstance(base_items, list):
                    base_items = []
                seen = {_norm(i.get("normalized_value") or i.get("value", "")): True for i in base_items if
                        isinstance(i, dict)}

                ai_items = []
                if isinstance(block, dict):
                    ai_items = block.get("items") or []
                elif isinstance(block, list):
                    ai_items = block

                if isinstance(ai_items, list):
                    for it in ai_items:
                        if isinstance(it, dict):
                            key = _norm(it.get("normalized_value") or it.get("value", ""))
                            if key and key not in seen:
                                base_items.append(it);
                                seen[key] = True
                        elif isinstance(it, str):
                            key = _norm(it)
                            if key and key not in seen:
                                base_items.append({"value": it, "normalized_value": key});
                                seen[key] = True

                out["entities"][et]["items"] = base_items
                out["entities"][et]["count"] = len(base_items)
                if base_items and not out["entities"][et].get("primary"):
                    out["entities"][et]["primary"] = base_items[0]

        # relations
        def rkey(r: Any) -> str:
            if not isinstance(r, dict):
                return str(r)
            s, t = r.get("source", {}), r.get("target", {})
            if isinstance(s, dict) and isinstance(t, dict):
                return f"{r.get('type')}|{s.get('type')}:{s.get('value')}|{t.get('type')}:{t.get('value')}"
            return str(r)

        base_rel = out.get("relations") or []
        if not isinstance(base_rel, list):
            base_rel = []
        keys = {rkey(r) for r in base_rel if isinstance(r, dict)}

        for r in (ai.get("relations") or []):
            if isinstance(r, dict):
                # Assure une phrase lisible si absente
                if not r.get("description") and isinstance(r.get("source"), dict) and isinstance(r.get("target"), dict):
                    r["description"] = self.describe_relation_ai(r["source"], r.get("type", "related_to"), r["target"])
                k = rkey(r)
                if k not in keys:
                    base_rel.append(r);
                    keys.add(k)
        out["relations"] = base_rel

        # contexts (type-safe)
        out.setdefault("contexts", {})
        ai_ctx = ai.get("contexts")
        if isinstance(ai_ctx, dict):
            for k, v in ai_ctx.items():
                if out["contexts"].get(k) in (None, "", [], {}):
                    out["contexts"][k] = v

        # Q&A
        def qkey(qa: Any) -> str:
            if not isinstance(qa, dict):
                return str(qa)
            return f"{_norm(qa.get('question') or '')}|{_norm(qa.get('answer') or '')}"

        base_qa = out.get("questions_answers") or []
        if not isinstance(base_qa, list):
            base_qa = []
        seenq = {qkey(x) for x in base_qa}

        for qa in (ai.get("questions_answers") or []):
            if isinstance(qa, dict):
                k = qkey(qa)
                if k not in seenq:
                    base_qa.append(qa);
                    seenq.add(k)
        out["questions_answers"] = base_qa

        # résumé
        if isinstance(ai.get("semantic_summary"), str) and ai["semantic_summary"].strip():
            out["semantic_summary"] = ai["semantic_summary"].strip()

        # tech_hints.suggested_schema
        sug = (ai.get("tech_hints") or {}).get("suggested_schema") or ai.get("suggested_schema")
        if isinstance(sug, dict):
            out.setdefault("tech_hints", {})["suggested_schema"] = sug

        return out


def enrich_document_json_for_expert(document, basic_json: Dict) -> Dict:
    """Enrichit le JSON d'un document pour l'expert"""

    enricher = JSONEnricher()

    # Contexte du document
    document_context = {
        "doc_type": getattr(document, 'doc_type', None),
        "country": getattr(document, 'country', None),
        "language": getattr(document, 'language', None),
        "source": getattr(document, 'source', None),
        "title": document.title,
        "total_pages": document.total_pages
    }

    # Enrichissement
    enriched_json = enricher.enrich_basic_json(basic_json, document_context)

    return enriched_json
