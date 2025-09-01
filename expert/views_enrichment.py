# expert/views_enrichment.py
# -*- coding: utf-8 -*-

import json
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone

from rawdocs.models import RawDocument
from .json_enrichment import JSONEnricher
from .views import expert_required


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
