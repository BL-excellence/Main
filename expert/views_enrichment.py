# expert/views_enrichment.py
# -*- coding: utf-8 -*-

import json
import uuid

from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone

from rawdocs.models import RawDocument
from .json_enrichment import JSONEnricher
from .views import expert_required
from .llm_client import LLMClient

from .services import apply_expert_deltas
# ---------------------------------------------------------------------
#  ENRICHISSEMENT AUTOMATIQUE
# ---------------------------------------------------------------------
@expert_required
@csrf_exempt
def enrich_document_json(request, doc_id):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        doc = get_object_or_404(RawDocument, pk=doc_id)
        basic_json = doc.global_annotations_json or {}

        if not basic_json.get('entities'):
            return JsonResponse({
                'success': False,
                'error': "Aucune entité trouvée dans le document. Veuillez d'abord générer le JSON de base."
            })

        document_context = {
            "doc_type": getattr(doc, 'doc_type', None),
            "country": getattr(doc, 'country', None),
            "language": getattr(doc, 'language', None),
            "source": getattr(doc, 'source', None),
            "title": doc.title,
            "total_pages": doc.total_pages
        }
        document_summary = getattr(doc, 'global_annotations_summary', "") or ""

        # Relations expertes si vous en stockez ailleurs (optionnel)
        expert_relations = []
        if hasattr(doc, "expert_relations"):
            expert_relations = list(doc.expert_relations.all().values(
                "type", "source", "target", "description", "confidence"
            ))

        enricher = JSONEnricher()
        enriched = enricher.enrich_basic_json(
            basic_json,
            document_context,
            document_summary=document_summary,
            expert_relations=expert_relations,
            use_ai=True
        )

        enriched = enricher.ensure_relation_descriptions(
            enriched,
            document_context=document_context,
            document_summary=document_summary,  # << important
            prefer_fluent_ai=True
        )

        doc.enriched_annotations_json = enriched
        if hasattr(doc, 'enriched_generated_at'):
            doc.enriched_generated_at = timezone.now()
            doc.save(update_fields=["enriched_annotations_json", "enriched_generated_at"])
        else:
            doc.save(update_fields=["enriched_annotations_json"])

        # Log éventuel
        try:
            from expert.views import log_expert_action
            log_expert_action(
                user=request.user, action='json_enriched', annotation=None,
                document_id=doc.id, document_title=doc.title,
                reason="JSON enrichi automatiquement avec contexte sémantique"
            )
        except Exception:
            pass

        return JsonResponse({
            "success": True,
            "relations_count": len(enriched.get("relations", [])),
            "qa_pairs_count": len(enriched.get("questions_answers", [])),
            "contexts_count": len(enriched.get("contexts", {})),
            "message": "JSON enrichi avec succès"
        })

    except Exception as e:
        print(f"❌ Erreur lors de l'enrichissement: {e}")
        return JsonResponse({"success": False, "error": f"Erreur lors de l'enrichissement: {str(e)}"})


# ---------------------------------------------------------------------
#  TEST Q&A — génère une réponse à partir du JSON basic/enriched
# ---------------------------------------------------------------------
@expert_required
@csrf_exempt
def test_qa(request, doc_id):
    try:
        doc = get_object_or_404(RawDocument, pk=doc_id)

        if request.method != 'POST':
            return JsonResponse({"success": False, "error": "POST requis"})

        payload = json.loads(request.body.decode("utf-8"))
        question = (payload.get("question") or "").strip()
        source = (payload.get("source") or "enriched").lower()  # 'basic' | 'enriched'

        if not question:
            return JsonResponse({"success": False, "error": "Question manquante."})

        context_json = doc.global_annotations_json if source == "basic" else (doc.enriched_annotations_json or {})
        document_context = {
            "doc_type": getattr(doc, 'doc_type', None),
            "country": getattr(doc, 'country', None),
            "language": getattr(doc, 'language', None),
            "title": doc.title
        }
        document_summary = getattr(doc, 'global_annotations_summary', "") or ""

        enricher = JSONEnricher()
        result = enricher.answer_question_ai(question, context_json, document_context, document_summary)
        return JsonResponse({"success": True, **result})

    except Exception as e:
        print(f"Erreur test_qa: {e}")
        return JsonResponse({"success": False, "error": str(e)})


# ---------------------------------------------------------------------
#  FEEDBACK Q&A — enregistre la correction telle quelle (mémoire)
# ---------------------------------------------------------------------
@expert_required
@csrf_exempt
def qa_feedback(request, doc_id):
    try:
        doc = get_object_or_404(RawDocument, pk=doc_id)

        if request.method != 'POST':
            return JsonResponse({"success": False, "error": "POST requis"})

        payload = json.loads(request.body.decode("utf-8"))
        question = (payload.get("question") or "").strip()
        corrected = (payload.get("corrected_answer") or "").strip()
        source = (payload.get("source") or "enriched").lower()

        if not question or not corrected:
            return JsonResponse({"success": False, "error": "Question ou réponse corrigée manquante."})

        enriched = doc.enriched_annotations_json or {}
        qa_list = enriched.setdefault("questions_answers", [])
        qa_list.append({
            "question": question,
            "answer": corrected,
            "confidence": 1.0,
            "answer_type": "expert_correction",
            "source": source,
            "created_by": "expert",
            "created_at": timezone.now().isoformat()
        })
        doc.enriched_annotations_json = enriched
        doc.save(update_fields=["enriched_annotations_json"])
        return JsonResponse({"success": True})

    except Exception as e:
        print(f"Erreur qa_feedback: {e}")
        return JsonResponse({"success": False, "error": str(e)})


# ---------------------------------------------------------------------
#  ⬇️⬇️ NOUVEAU : AJOUT RELATION (auto-description IA)
#  front-end: POST /expert/annotation/document/<id>/add-relation/
#  body: {source_type, source_value, relation_type, target_type, target_value, description?}
# ---------------------------------------------------------------------
@expert_required
@csrf_exempt
def add_relation(request, doc_id):
    if request.method != 'POST':
        return JsonResponse({"success": False, "error": "POST requis"})

    try:
        doc = get_object_or_404(RawDocument, pk=doc_id)
        payload = json.loads(request.body.decode("utf-8"))

        source_type = (payload.get("source_type") or "").strip()
        source_value = (payload.get("source_value") or "").strip()
        relation_type = (payload.get("relation_type") or "").strip()
        target_type = (payload.get("target_type") or "").strip()
        target_value = (payload.get("target_value") or "").strip()
        description = (payload.get("description") or "").strip() or None

        if not (source_type and source_value and relation_type and target_type and target_value):
            return JsonResponse({"success": False, "error": "Champs requis manquants."})

        enriched = doc.enriched_annotations_json or (doc.global_annotations_json or {})
        document_context = {
            "doc_type": getattr(doc, 'doc_type', None),
            "country": getattr(doc, 'country', None),
            "language": getattr(doc, 'language', None),
            "title": doc.title
        }

        enricher = JSONEnricher()
        enricher = JSONEnricher()

        # ➊ Si pas de description fournie par l'expert, on la demande au LLM
        if not description:
            description = enricher.describe_relation_ai_fluent(
                {"type": source_type, "value": source_value},
                relation_type,
                {"type": target_type, "value": target_value},
                document_context=document_context,
                enriched=doc.enriched_annotations_json or {},  # tout le JSON enrichi en evidence
                document_summary=getattr(doc, 'global_annotations_summary', '') or ''  # résumé global
            )

        # ➋ On applique quand même le pipeline standard (dédup + merge)
        updated = enricher.add_relation_with_autodescription(
            enriched,
            source_type=source_type, source_value=source_value,
            relation_type=relation_type,
            target_type=target_type, target_value=target_value,
            description=description,  # << passe la phrase LLM ici
            document_context=document_context,
            created_by="expert"
        )

        doc.enriched_annotations_json = updated
        doc.save(update_fields=["enriched_annotations_json"])
        return JsonResponse({"success": True})

    except Exception as e:
        print(f"Erreur add_relation: {e}")
        return JsonResponse({"success": False, "error": str(e)})


# ---------------------------------------------------------------------
#  ⬇️⬇️ NOUVEAU : AJOUT Q&A → création de connaissance structurée
#  front-end: POST /expert/annotation/document/<id>/add-qa/
#  body: {question, answer, tags?:[], entity_refs?:[]}
# ---------------------------------------------------------------------
@expert_required
@csrf_exempt
def add_qa(request, doc_id):
    if request.method != 'POST':
        return JsonResponse({"success": False, "error": "POST requis"})

    try:
        doc = get_object_or_404(RawDocument, pk=doc_id)
        payload = json.loads(request.body.decode("utf-8"))

        question = (payload.get("question") or "").strip()
        answer = (payload.get("answer") or "").strip()
        tags = payload.get("tags") or []

        if not (question and answer):
            return JsonResponse({"success": False, "error": "Question et réponse requises."})

        current = doc.enriched_annotations_json or (doc.global_annotations_json or {})
        document_context = {
            "doc_type": getattr(doc, 'doc_type', None),
            "country": getattr(doc, 'country', None),
            "language": getattr(doc, 'language', None),
            "title": doc.title
        }

        enricher = JSONEnricher()
        patch = enricher.patch_from_expert_qa(
            question=question,
            answer=answer,
            current_json=current,
            document_context=document_context,
            tags=tags
        )
        updated = enricher.apply_patch(current, patch)

        doc.enriched_annotations_json = updated
        doc.save(update_fields=["enriched_annotations_json"])
        return JsonResponse({"success": True})

    except Exception as e:
        print(f"Erreur add_qa: {e}")
        return JsonResponse({"success": False, "error": str(e)})


# ---------------------------------------------------------------------
#  ⬇️⬇️ NOUVEAU : SAUVEGARDE DES ÉDITS MANUELS DU JSON ENRICHI (éditeur)
#  front-end: POST /expert/annotation/document/<id>/save-enriched-edits/
#  body: {manual_edits: <json>}
# ---------------------------------------------------------------------
@expert_required
@csrf_exempt
def paragraph_to_relations(request, doc_id):
    """
    Reçoit {text, hint?} et ajoute au JSON enrichi les entités/relations extraites par l'IA.
    """
    if request.method != 'POST':
        return JsonResponse({"success": False, "error": "POST requis"})

    try:
        doc = get_object_or_404(RawDocument, pk=doc_id)
        payload = json.loads(request.body.decode("utf-8"))
        text = (payload.get("text") or "").strip()
        hint = (payload.get("hint") or "").strip()
        if not text:
            return JsonResponse({"success": False, "error": "Paragraphe manquant."})

        # Contexte & JSON courant (on part du enrichi si dispo)
        current = doc.enriched_annotations_json or (doc.global_annotations_json or {})
        document_context = {
            "doc_type": getattr(doc, 'doc_type', None),
            "country": getattr(doc, 'country', None),
            "language": getattr(doc, 'language', None),
            "title": doc.title
        }
        document_summary = getattr(doc, 'global_annotations_summary', "") or ""

        enricher = JSONEnricher()
        patch = enricher.extract_relations_from_paragraph(
            text=text,
            current_json=current,
            document_context=document_context,
            document_summary=document_summary,
            hint=hint
        )

        updated = enricher.apply_patch(current, patch)
        # Sécurité : si qq relation n'a pas de description, on la rédige via le LLM (fluent)
        updated = enricher.ensure_relation_descriptions(
            updated,
            document_context=document_context,
            document_summary=document_summary,
            prefer_fluent_ai=True
        )

        # Save
        doc.enriched_annotations_json = updated
        if hasattr(doc, 'enriched_generated_at'):
            doc.enriched_generated_at = timezone.now()
            doc.save(update_fields=["enriched_annotations_json", "enriched_generated_at"])
        else:
            doc.save(update_fields=["enriched_annotations_json"])

        added_rel = len(patch.get("relations", []) or [])
        added_ent = sum(len((block.get("items") if isinstance(block, dict) else block) or [])
                        for block in (patch.get("entities") or {}).values())

        return JsonResponse({"success": True, "added_relations": added_rel, "added_entities": added_ent})

    except Exception as e:
        print(f"Erreur paragraph_to_relations: {e}")
        return JsonResponse({"success": False, "error": str(e)})


@expert_required
@csrf_exempt
def save_enriched_edits(request, doc_id):
    if request.method != 'POST':
        return JsonResponse({"success": False, "error": "POST requis"})

    try:
        doc = get_object_or_404(RawDocument, pk=doc_id)
        payload = json.loads(request.body.decode("utf-8"))
        manual = payload.get("manual_edits")
        if not isinstance(manual, dict):
            return JsonResponse({"success": False, "error": "JSON invalide."})
        doc.enriched_annotations_json = manual
        if hasattr(doc, 'enriched_generated_at'):
            doc.enriched_generated_at = timezone.now()
            doc.save(update_fields=["enriched_annotations_json", "enriched_generated_at"])
        else:
            doc.save(update_fields=["enriched_annotations_json"])
        return JsonResponse({"success": True})
    except Exception as e:
        print(f"Erreur save_enriched_edits: {e}")
        return JsonResponse({"success": False, "error": str(e)})


######ll

@expert_required
@csrf_exempt
def describe_relation(request, doc_id):
    """Génère une description IA pour une relation individuelle"""
    if request.method != 'POST':
        return JsonResponse({"success": False, "error": "POST requis"})

    try:
        doc = get_object_or_404(RawDocument, pk=doc_id)
        payload = json.loads(request.body.decode("utf-8"))

        source_type = payload.get("source_type")
        source_value = payload.get("source_value")
        relation_type = payload.get("relation_type")
        target_type = payload.get("target_type")
        target_value = payload.get("target_value")

        if not all([source_type, source_value, relation_type, target_type, target_value]):
            return JsonResponse({"success": False, "error": "Paramètres manquants"})

        document_context = {
            "doc_type": getattr(doc, 'doc_type', None),
            "country": getattr(doc, 'country', None),
            "language": getattr(doc, 'language', None),
            "title": doc.title
        }

        enricher = JSONEnricher()
        description = enricher.describe_relation_ai_fluent(
            {"type": source_type, "value": source_value},
            relation_type,
            {"type": target_type, "value": target_value},
            document_context=document_context,
            enriched=doc.enriched_annotations_json or {},
            document_summary=getattr(doc, 'global_annotations_summary', '') or ''
        )

        return JsonResponse({
            "success": True,
            "description": description
        })

    except Exception as e:
        print(f"Erreur describe_relation: {e}")
        return JsonResponse({"success": False, "error": str(e)})


# expert/views_enrichment.py
@expert_required
@csrf_exempt
def add_relations_batch(request, doc_id):
    """Ajoute plusieurs relations en batch avec descriptions IA"""
    if request.method != 'POST':
        return JsonResponse({"success": False, "error": "POST requis"})

    try:
        doc = get_object_or_404(RawDocument, pk=doc_id)
        payload = json.loads(request.body.decode("utf-8"))
        relations_data = payload.get("relations", [])

        if not relations_data:
            return JsonResponse({"success": False, "error": "Aucune relation fournie"})

        enriched = doc.enriched_annotations_json or {}
        existing_relations = enriched.setdefault("relations", [])

        document_context = {
            "doc_type": getattr(doc, 'doc_type', None),
            "country": getattr(doc, 'country', None),
            "language": getattr(doc, 'language', None),
            "title": doc.title
        }

        enricher = JSONEnricher()
        added_count = 0

        for rel_data in relations_data:
            # Vérifier les doublons
            exists = any(
                existing["source"]["value"] == rel_data["source_value"] and
                existing["target"]["value"] == rel_data["target_value"] and
                existing["type"] == rel_data["relation_type"]
                for existing in existing_relations
            )

            if not exists:
                # Générer description si manquante
                description = rel_data.get("description")
                if not description:
                    description = enricher.describe_relation_ai_fluent(
                        {"type": rel_data["source_type"], "value": rel_data["source_value"]},
                        rel_data["relation_type"],
                        {"type": rel_data["target_type"], "value": rel_data["target_value"]},
                        document_context=document_context,
                        enriched=enriched,
                        document_summary=getattr(doc, 'global_annotations_summary', '') or ''
                    )

                new_relation = {
                    "id": str(uuid.uuid4())[:8],
                    "source": {"type": rel_data["source_type"], "value": rel_data["source_value"]},
                    "target": {"type": rel_data["target_type"], "value": rel_data["target_value"]},
                    "type": rel_data["relation_type"],
                    "description": description,
                    "created_by": "expert",
                    "created_at": timezone.now().isoformat()
                }

                existing_relations.append(new_relation)
                added_count += 1

        doc.enriched_annotations_json = enriched
        doc.save(update_fields=["enriched_annotations_json"])

        return JsonResponse({
            "success": True,
            "added_count": added_count,
            "message": f"{added_count} relations ajoutées"
        })

    except Exception as e:
        print(f"Erreur add_relations_batch: {e}")
        return JsonResponse({"success": False, "error": str(e)})


# expert/views_enrichment.py
@expert_required
@csrf_exempt
def describe_relations_batch(request, doc_id):
    """Génère des descriptions pour plusieurs relations"""
    if request.method != 'POST':
        return JsonResponse({"success": False, "error": "POST requis"})

    try:
        doc = get_object_or_404(RawDocument, pk=doc_id)
        payload = json.loads(request.body.decode("utf-8"))
        relations_data = payload.get("relations", [])

        document_context = {
            "doc_type": getattr(doc, 'doc_type', None),
            "country": getattr(doc, 'country', None),
            "language": getattr(doc, 'language', None),
            "title": doc.title
        }

        enricher = JSONEnricher()
        descriptions = []

        for rel_data in relations_data:
            description = enricher.describe_relation_ai_fluent(
                {"type": rel_data["source_type"], "value": rel_data["source_value"]},
                rel_data["relation_type"],
                {"type": rel_data["target_type"], "value": rel_data["target_value"]},
                document_context=document_context,
                enriched=doc.enriched_annotations_json or {},
                document_summary=getattr(doc, 'global_annotations_summary', '') or ''
            )
            descriptions.append(description)

        return JsonResponse({
            "success": True,
            "descriptions": descriptions
        })

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)})


# expert/views_enrichment.py

# expert/views_enrichment.py

# expert/views_enrichment.py

from expert.llm_client import LLMClient  # Ajouter cet import
import uuid
from django.utils import timezone


@expert_required
@csrf_exempt
def analyze_paragraph(request, doc_id):
    """Analyse un paragraphe et retourne les relations trouvées sans les sauvegarder"""
    if request.method != 'POST':
        return JsonResponse({"success": False, "error": "POST requis"})

    try:
        doc = get_object_or_404(RawDocument, pk=doc_id)
        payload = json.loads(request.body.decode("utf-8"))

        text = payload.get("text", "").strip()
        hint = payload.get("hint", "").strip()

        if not text:
            return JsonResponse({"success": False, "error": "Texte requis"})

        # Créer une instance du client LLM
        llm_client = LLMClient()

        if not llm_client.enabled:
            return JsonResponse({"success": False, "error": "LLM non disponible"})

        # Construire le prompt pour l'analyse
        context_info = f"Document: {doc.title}"
        if hint:
            context_info += f"\nContexte: {hint}"

        prompt = f"""Analysez ce paragraphe médical/pharmaceutique et identifiez toutes les relations entre entités.

{context_info}

Texte à analyser:
{text}

Votre tâche:
1. Identifier les entités (produits, ingrédients, dosages, indications, contre-indications, etc.)
2. Identifier les relations entre ces entités
3. Retourner un JSON avec la structure exacte suivante:

{{
    "relations": [
        {{
            "source": {{"type": "product", "value": "nom_entité_source"}},
            "target": {{"type": "ingredient", "value": "nom_entité_cible"}},
            "type": "contains",
            "description": "Description claire de la relation"
        }}
    ]
}}

Types de relations possibles:
- contains: contient (produit contient ingrédient)
- manufactured_by: fabriqué par
- has_dosage: a pour dosage
- used_for: utilisé pour (indication)
- contraindicated_with: contre-indiqué avec
- interacts_with: interagit avec
- composed_of: composé de
- has_side_effect: a pour effet secondaire

Types d'entités possibles:
- product: produit/médicament
- ingredient: ingrédient actif
- dosage: dosage/concentration
- indication: indication thérapeutique
- contraindication: contre-indication
- organization: organisation/laboratoire
- regulation: réglementation
- date: date
- custom: autre type

Retournez uniquement le JSON, sans texte supplémentaire."""

        messages = [
            {
                "role": "system",
                "content": "Vous êtes un expert en analyse pharmaceutique. Analysez le texte et retournez uniquement un JSON valide."
            },
            {
                "role": "user",
                "content": prompt
            }
        ]

        # Appel au LLM
        try:
            result = llm_client.chat_json(messages=messages, max_tokens=2000)

            if not result:
                return JsonResponse({"success": False, "error": "Aucune réponse du LLM"})

            # Valider et nettoyer les relations
            relations = []
            for rel in result.get("relations", []):
                if all(key in rel for key in ["source", "target", "type"]):
                    # Valider la structure source/target
                    if (isinstance(rel["source"], dict) and "type" in rel["source"] and "value" in rel["source"] and
                            isinstance(rel["target"], dict) and "type" in rel["target"] and "value" in rel["target"]):

                        # Nettoyer et valider
                        clean_relation = {
                            "id": str(uuid.uuid4())[:8],
                            "source": {
                                "type": str(rel["source"]["type"]).strip(),
                                "value": str(rel["source"]["value"]).strip()
                            },
                            "target": {
                                "type": str(rel["target"]["type"]).strip(),
                                "value": str(rel["target"]["value"]).strip()
                            },
                            "type": str(rel["type"]).strip(),
                            "description": str(rel.get("description", "")).strip() or None
                        }

                        # Éviter les relations vides
                        if (clean_relation["source"]["value"] and
                                clean_relation["target"]["value"] and
                                clean_relation["type"]):
                            relations.append(clean_relation)

            return JsonResponse({
                "success": True,
                "relations": relations,
                "message": f"{len(relations)} relations trouvées"
            })

        except Exception as llm_error:
            print(f"Erreur LLM: {llm_error}")
            return JsonResponse({"success": False, "error": f"Erreur lors de l'analyse IA: {str(llm_error)}"})

    except Exception as e:
        print(f"Erreur analyze_paragraph: {e}")
        return JsonResponse({"success": False, "error": str(e)})


@expert_required
@csrf_exempt
def save_paragraph_relations(request, doc_id):
    """Sauvegarde les relations validées par l'expert depuis l'analyse de paragraphe"""
    if request.method != 'POST':
        return JsonResponse({"success": False, "error": "POST requis"})

    try:
        doc = get_object_or_404(RawDocument, pk=doc_id)
        payload = json.loads(request.body.decode("utf-8"))

        relations_data = payload.get("relations", [])
        if not relations_data:
            return JsonResponse({"success": False, "error": "Aucune relation fournie"})

        enriched = doc.enriched_annotations_json or {}
        existing_relations = enriched.setdefault("relations", [])

        saved_count = 0

        for rel_data in relations_data:
            # Vérifier les doublons
            exists = any(
                existing["source"]["value"] == rel_data["source"]["value"] and
                existing["target"]["value"] == rel_data["target"]["value"] and
                existing["type"] == rel_data["type"]
                for existing in existing_relations
            )

            if not exists:
                new_relation = {
                    "id": rel_data.get("id", str(uuid.uuid4())[:8]),
                    "source": rel_data["source"],
                    "target": rel_data["target"],
                    "type": rel_data["type"],
                    "description": rel_data.get("description"),
                    "created_by": "expert",
                    "created_at": timezone.now().isoformat(),
                    "source_method": "paragraph_analysis"
                }

                existing_relations.append(new_relation)
                saved_count += 1

        doc.enriched_annotations_json = enriched
        doc.save(update_fields=["enriched_annotations_json"])

        return JsonResponse({
            "success": True,
            "saved_count": saved_count,
            "message": f"{saved_count} relations sauvegardées"
        })

    except Exception as e:
        print(f"Erreur save_paragraph_relations: {e}")
        return JsonResponse({"success": False, "error": str(e)})


# ---------------------------------------------------------------------
#  NOUVEAU : RÉCUPÉRATION DES DOCUMENTS VALIDÉS PAR MÉTADONNEURS
# ---------------------------------------------------------------------
@expert_required
def get_validated_documents(request):
    """
    Récupère tous les documents validés par les métadonneurs
    pour l'analyse expert page par page
    """
    try:
        # Récupérer tous les documents validés par les métadonneurs
        validated_docs = RawDocument.objects.filter(
            is_validated=True
        ).select_related('owner').order_by('-validated_at')

        documents_data = []
        for doc in validated_docs:
            # Compter les pages analysées
            pages_analyzed = doc.pages.filter(is_regulatory_analyzed=True).count()
            pages_with_annotations = doc.pages.filter(is_annotated=True).count()

            # Vérifier si le fichier PDF existe physiquement
            import os
            pdf_file_exists = False
            if doc.file:
                try:
                    pdf_file_exists = os.path.exists(doc.file.path)
                except Exception:
                    pdf_file_exists = False

            doc_data = {
                'id': doc.id,
                'title': doc.title or f"Document #{doc.id}",
                'doc_type': doc.doc_type,
                'source': doc.source,
                'country': doc.country,
                'language': doc.language,
                'validated_at': doc.validated_at.isoformat() if doc.validated_at else None,
                'is_expert_validated': doc.is_expert_validated,
                'expert_validated_at': doc.expert_validated_at.isoformat() if doc.expert_validated_at else None,
                'total_pages': doc.total_pages,
                'pages_analyzed': pages_analyzed,
                'pages_with_annotations': pages_with_annotations,
                'has_enriched_json': bool(doc.enriched_annotations_json),
                'owner': doc.owner.username if doc.owner else None,
                'summary': doc.global_annotations_summary[:200] if doc.global_annotations_summary else None,
                'pdf_file_exists': pdf_file_exists  # NOUVEAU: Indique si le fichier PDF existe
            }
            documents_data.append(doc_data)

        return JsonResponse({
            'success': True,
            'documents': documents_data,
            'total_count': len(documents_data)
        })

    except Exception as e:
        print(f"Erreur get_validated_documents: {e}")
        return JsonResponse({'success': False, 'error': str(e)})


# ---------------------------------------------------------------------
#  NOUVEAU : ANALYSE DES RELATIONS PAGE PAR PAGE
# ---------------------------------------------------------------------
@expert_required
@csrf_exempt
def analyze_document_pages_relations(request, doc_id):
    """
    Analyse toutes les pages d'un document validé pour trouver
    les relations sémantiques possibles page par page
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST requis'})

    try:
        doc = get_object_or_404(RawDocument, pk=doc_id)

        # Vérifier que le document est validé
        if not doc.is_validated:
            return JsonResponse({
                'success': False,
                'error': 'Ce document n\'est pas encore validé par un métadonneur'
            })

        payload = json.loads(request.body.decode('utf-8'))
        page_numbers = payload.get('page_numbers', [])  # Si vide, analyse toutes les pages
        force_reanalyze = payload.get('force_reanalyze', False)

        # Récupérer les pages à analyser
        pages_query = doc.pages.all()
        if page_numbers:
            pages_query = pages_query.filter(page_number__in=page_numbers)

        pages_relations = []
        llm_client = LLMClient()

        if not llm_client.enabled:
            return JsonResponse({'success': False, 'error': 'LLM non disponible'})

        document_context = {
            'doc_type': doc.doc_type,
            'country': doc.country,
            'language': doc.language,
            'title': doc.title,
            'source': doc.source
        }

        # Analyser chaque page
        for page in pages_query.order_by('page_number'):
            # Skip si déjà analysé (sauf si force_reanalyze)
            if page.regulatory_analysis and not force_reanalyze:
                # Utiliser l'analyse existante
                page_data = {
                    'page_number': page.page_number,
                    'relations': page.regulatory_analysis.get('relations', []),
                    'entities': page.regulatory_analysis.get('entities', {}),
                    'already_analyzed': True
                }
                pages_relations.append(page_data)
                continue

            # Analyser la page pour trouver les relations
            page_text = page.cleaned_text or page.raw_text

            if not page_text.strip():
                continue

            prompt = f"""Analysez cette page de document pharmaceutique/réglementaire et identifiez:
1. Toutes les entités importantes (produits, autorités, dates, procédures, etc.)
2. Les relations entre ces entités
3. Les obligations réglementaires

Contexte du document:
- Titre: {document_context.get('title', 'N/A')}
- Type: {document_context.get('doc_type', 'N/A')}
- Source: {document_context.get('source', 'N/A')}
- Pays: {document_context.get('country', 'N/A')}

Page {page.page_number}/{doc.total_pages}:
{page_text[:3000]}  # Limiter à 3000 caractères

Retournez un JSON structuré avec:
{{
    "entities": {{
        "products": [],
        "authorities": [],
        "procedures": [],
        "dates": [],
        "regulations": [],
        "other": []
    }},
    "relations": [
        {{
            "source": {{"type": "type_entité", "value": "valeur"}},
            "target": {{"type": "type_entité", "value": "valeur"}},
            "type": "type_relation",
            "description": "Description de la relation",
            "confidence": 0.9
        }}
    ],
    "obligations": [
        {{
            "description": "Description de l'obligation",
            "deadline": "délai si mentionné",
            "authority": "autorité concernée"
        }}
    ],
    "summary": "Résumé de la page en 2 phrases max"
}}"""

            messages = [
                {
                    "role": "system",
                    "content": "Vous êtes un expert en analyse réglementaire pharmaceutique. Analysez précisément et retournez uniquement du JSON valide."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ]

            try:
                result = llm_client.chat_json(messages=messages, max_tokens=2000)

                if result:
                    # Sauvegarder l'analyse dans la page
                    page.regulatory_analysis = result
                    page.is_regulatory_analyzed = True
                    page.regulatory_analyzed_at = timezone.now()
                    page.regulatory_analyzed_by = request.user

                    # Calculer le score d'importance
                    importance_score = 0
                    if result.get('obligations'):
                        importance_score += len(result['obligations']) * 20
                    if result.get('relations'):
                        importance_score += len(result['relations']) * 10
                    if result.get('entities'):
                        total_entities = sum(len(v) for v in result['entities'].values() if isinstance(v, list))
                        importance_score += total_entities * 5

                    page.regulatory_importance_score = min(100, importance_score)
                    page.page_summary = result.get('summary', '')
                    page.regulatory_obligations = result.get('obligations', [])
                    page.critical_deadlines = [
                        ob for ob in result.get('obligations', [])
                        if ob.get('deadline')
                    ]

                    page.save()

                    page_data = {
                        'page_number': page.page_number,
                        'relations': result.get('relations', []),
                        'entities': result.get('entities', {}),
                        'obligations': result.get('obligations', []),
                        'summary': result.get('summary', ''),
                        'importance_score': page.regulatory_importance_score,
                        'newly_analyzed': True
                    }
                    pages_relations.append(page_data)

            except Exception as llm_error:
                print(f"Erreur LLM pour page {page.page_number}: {llm_error}")
                pages_relations.append({
                    'page_number': page.page_number,
                    'error': str(llm_error)
                })

        # Mettre à jour le JSON enrichi global avec toutes les relations trouvées
        all_relations = []
        all_entities = {}

        for page_data in pages_relations:
            if 'relations' in page_data:
                for rel in page_data['relations']:
                    rel['page_number'] = page_data['page_number']
                    all_relations.extend(page_data['relations'])

            if 'entities' in page_data:
                for entity_type, entities in page_data['entities'].items():
                    if entity_type not in all_entities:
                        all_entities[entity_type] = []
                    all_entities[entity_type].extend(entities)

        # Dédupliquer les entités
        for entity_type in all_entities:
            all_entities[entity_type] = list(set(all_entities[entity_type]))

        # Mettre à jour le JSON enrichi du document
        if not doc.enriched_annotations_json:
            doc.enriched_annotations_json = {}

        doc.enriched_annotations_json['page_by_page_analysis'] = {
            'analyzed_at': timezone.now().isoformat(),
            'analyzed_by': request.user.username,
            'pages_analyzed': len(pages_relations),
            'total_relations_found': len(all_relations),
            'all_entities': all_entities,
            'all_relations': all_relations
        }

        doc.save(update_fields=['enriched_annotations_json'])

        return JsonResponse({
            'success': True,
            'pages_analyzed': len(pages_relations),
            'total_relations': len(all_relations),
            'pages_data': pages_relations,
            'message': f"Analyse terminée: {len(all_relations)} relations trouvées sur {len(pages_relations)} pages"
        })

    except Exception as e:
        print(f"Erreur analyze_document_pages_relations: {e}")
        return JsonResponse({'success': False, 'error': str(e)})


# ---------------------------------------------------------------------
#  NOUVEAU : RÉCUPÉRATION DES RELATIONS D'UN DOCUMENT PAGE PAR PAGE
# ---------------------------------------------------------------------
@expert_required
def get_document_page_relations(request, doc_id):
    """
    Récupère toutes les relations analysées page par page pour un document
    """
    try:
        doc = get_object_or_404(RawDocument, pk=doc_id)

        if not doc.is_validated:
            return JsonResponse({
                'success': False,
                'error': 'Document non validé'
            })

        pages_data = []
        for page in doc.pages.all().order_by('page_number'):
            if page.regulatory_analysis:
                page_info = {
                    'page_number': page.page_number,
                    'summary': page.page_summary,
                    'importance_score': page.regulatory_importance_score,
                    'relations': page.regulatory_analysis.get('relations', []),
                    'entities': page.regulatory_analysis.get('entities', {}),
                    'obligations': page.regulatory_analysis.get('obligations', []),
                    'analyzed_at': page.regulatory_analyzed_at.isoformat() if page.regulatory_analyzed_at else None
                }
                pages_data.append(page_info)

        # Récupérer aussi l'analyse globale si elle existe
        global_analysis = None
        if doc.enriched_annotations_json and 'page_by_page_analysis' in doc.enriched_annotations_json:
            global_analysis = doc.enriched_annotations_json['page_by_page_analysis']

        return JsonResponse({
            'success': True,
            'document': {
                'id': doc.id,
                'title': doc.title,
                'total_pages': doc.total_pages,
                'validated_at': doc.validated_at.isoformat() if doc.validated_at else None
            },
            'pages': pages_data,
            'global_analysis': global_analysis,
            'total_pages_analyzed': len([p for p in pages_data if p.get('relations') or p.get('entities')])
        })

    except Exception as e:
        print(f"Erreur get_document_page_relations: {e}")
        return JsonResponse({'success': False, 'error': str(e)})


@expert_required
def get_single_page_relations(request, doc_id, page_num):
    """
    Récupère les relations sémantiques d'une seule page spécifique
    """
    try:
        doc = get_object_or_404(RawDocument, pk=doc_id)
        page = doc.pages.filter(page_number=page_num).first()

        if not page:
            return JsonResponse({
                'success': False,
                'error': f'Page {page_num} non trouvée'
            })

        relations = []
        is_analyzed = page.is_regulatory_analyzed

        if page.regulatory_analysis and 'relations' in page.regulatory_analysis:
            relations = page.regulatory_analysis['relations']

        return JsonResponse({
            'success': True,
            'page_number': page_num,
            'is_analyzed': is_analyzed,
            'relations': relations,
            'entities': page.regulatory_analysis.get('entities', {}) if page.regulatory_analysis else {},
            'summary': page.page_summary or '',
            'analyzed_at': page.regulatory_analyzed_at.isoformat() if page.regulatory_analyzed_at else None
        })

    except Exception as e:
        print(f"Erreur get_single_page_relations: {e}")
        return JsonResponse({'success': False, 'error': str(e)})


@expert_required
@csrf_exempt
def delete_page_relation(request, doc_id, page_num, relation_index):
    """
    Supprime une relation spécifique d'une page
    """
    if request.method != 'DELETE':
        return JsonResponse({'error': 'DELETE required'}, status=405)

    try:
        doc = get_object_or_404(RawDocument, pk=doc_id)
        page = doc.pages.filter(page_number=page_num).first()

        if not page:
            return JsonResponse({
                'success': False,
                'error': f'Page {page_num} non trouvée'
            })

        if not page.regulatory_analysis or 'relations' not in page.regulatory_analysis:
            return JsonResponse({
                'success': False,
                'error': 'Aucune relation trouvée pour cette page'
            })

        relations = page.regulatory_analysis['relations']

        if relation_index < 0 or relation_index >= len(relations):
            return JsonResponse({
                'success': False,
                'error': 'Index de relation invalide'
            })

        # Supprimer la relation
        deleted_relation = relations.pop(relation_index)

        # Sauvegarder
        page.save()

        return JsonResponse({
            'success': True,
            'message': 'Relation supprimée avec succès',
            'deleted_relation': deleted_relation
        })

    except Exception as e:
        print(f"Erreur delete_page_relation: {e}")
        return JsonResponse({'success': False, 'error': str(e)})