from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated

from rawdocs.models import RawDocument, DocumentPage
from rawdocs.groq_annotation_system import GroqAnnotator
from rawdocs.annotation_utils import extract_pages_from_pdf
from rawdocs.models import DocumentPage

import logging
import re

logger = logging.getLogger(__name__)

# ---- Helpers ----

def _ensure_document_pages(doc):
    """Ensure DocumentPage rows exist with cleaned_text for the document. Create them from PDF if missing/empty."""
    pages_qs = DocumentPage.objects.filter(document=doc).order_by('page_number')
    has_any = pages_qs.exists()
    has_text = has_any and any((p.cleaned_text or '').strip() for p in pages_qs)
    if not has_any or not has_text:
        try:
            texts = extract_pages_from_pdf(doc.file.path)
        except Exception as e:
            logger.exception("Extraction PDF échouée")
            texts = []
        if texts:
            # Clean existing empty pages to avoid duplicates
            if has_any:
                DocumentPage.objects.filter(document=doc).delete()
            for idx, t in enumerate(texts, start=1):
                t = (t or '').strip()
                DocumentPage.objects.create(
                    document=doc,
                    page_number=idx,
                    raw_text=t,
                    cleaned_text=t,
                )
            try:
                doc.total_pages = len(texts)
                doc.pages_extracted = True
                doc.save(update_fields=['total_pages', 'pages_extracted'])
            except Exception:
                pass
            pages_qs = DocumentPage.objects.filter(document=doc).order_by('page_number')
    return pages_qs


def _split_pages_to_chunks(pages, max_chars=16000):
    """Split pages queryset into text chunks under max_chars to satisfy Groq limits.
    Returns list[str].
    """
    chunks = []
    current = []
    current_len = 0
    for p in pages:
        txt = (p.cleaned_text or '').strip()
        if not txt:
            continue
        addition = ("\n\n" if current else "") + txt
        if current_len + len(addition) > max_chars and current:
            chunks.append("".join(current))
            current = [txt]
            current_len = len(txt)
        else:
            if current:
                current.append("\n\n")
            current.append(txt)
            current_len += len(addition)
    if current:
        chunks.append("".join(current))
    return chunks if chunks else [""]


def _normalize_bullets(text_section: str):
    """Convert a section text into list of bullet items, normalize and deduplicate order-preserving."""
    items = []
    for line in (text_section or '').splitlines():
        s = line.strip()
        if not s:
            continue
        if s[:1] in ['-', '*', '•']:
            s = s[1:].strip()
        items.append(s)
    seen = set()
    out = []
    for it in items:
        key = it.lower()
        if key not in seen:
            seen.add(key)
            out.append(it)
    return out


def _extract_sections(text: str):
    """Extract 'Résumé', 'Points clés', 'Obligations', 'Délais', 'Autorités' from model answer text."""
    def sec(lbl):
        m = re.search(rf"{lbl}:\s*(.*?)(?:\n\s*(Résumé|Points clés|Obligations|Délais|Autorités):|$)", text, re.DOTALL | re.IGNORECASE)
        return (m.group(1).strip() if m else '')

    summary = sec('Résumé')
    key_points = _normalize_bullets(sec('Points clés'))
    obligations = _normalize_bullets(sec('Obligations'))
    deadlines = _normalize_bullets(sec('Délais'))
    authorities = _normalize_bullets(sec('Autorités'))
    return summary, key_points, obligations, deadlines, authorities


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def analyze_document_groq(request, pk):
    """Retourne l'analyse réglementaire existante (expert). Ne lance pas Groq."""
    doc = get_object_or_404(RawDocument, pk=pk, is_validated=True)

    # 1) Tenter de renvoyer l'analyse réglementaire experte déjà enregistrée
    try:
        regulatory = doc.regulatory_analysis  # OneToOne: DocumentRegulatoryAnalysis
    except Exception:
        regulatory = None

    if regulatory:
        consolidated = regulatory.consolidated_analysis or {}
        analysis = {
            # Préférer le résumé expert; sinon fallback au résumé global d'annotations
            "summary": (regulatory.global_summary or consolidated.get("global_summary") or doc.global_annotations_summary or ""),
            # Points clés: privilégier des champs communs si présents
            "key_points": consolidated.get("key_regulatory_points") or consolidated.get("main_regulatory_themes") or [],
            # Listes consolidées déjà présentes dans le modèle
            "obligations": list(regulatory.main_obligations or []),
            "deadlines": list(regulatory.critical_deadlines_summary or []),
            "authorities": list(regulatory.relevant_authorities or []),
        }
        return Response({
            "document_id": doc.id,
            "analysis": analysis,
        })

    # 2) Pas d'analyse experte disponible → renvoyer une réponse vide et un message clair (200)
    return Response({
        "document_id": doc.id,
        "analysis": {
            "summary": "Aucune analyse réglementaire créée.",
            "key_points": [],
            "obligations": [],
            "deadlines": [],
            "authorities": []
        }
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def document_raw_text(request, pk):
    """Retourne le texte brut concaténé (cleaned_text) des pages du document, en s'assurant de l'extraction."""
    doc = get_object_or_404(RawDocument, pk=pk)
    # Sécurité: un client ne doit voir que ses documents client ou documents publics selon votre logique.
    # Ici on reste minimal: seulement documents validés ou appartenant au user si vous avez besoin (à adapter si nécessaire).

    pages = _ensure_document_pages(doc)
    texts = [(p.cleaned_text or '').strip() for p in pages]
    full_text = "\n\n".join([t for t in texts if t])
    if not full_text:
        return Response({"error": "Aucun texte disponible pour ce document."}, status=status.HTTP_404_NOT_FOUND)
    return Response({
        "document_id": doc.id,
        "text": full_text[:200000]  # limiter si très gros
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def document_summary(request, pk):
    """Résumé IA stocké, en TEXTE, avec chunking et agrégation pour grands documents."""
    doc = get_object_or_404(RawDocument, pk=pk, is_validated=True)
    force = request.data.get('force') in (True, 'true', '1', 1)

    if doc.global_annotations_summary and not force:
        return Response({
            "document_id": doc.id,
            "summary": doc.global_annotations_summary,
            "generated_at": doc.global_annotations_summary_generated_at,
            "cached": True,
        })

    pages = _ensure_document_pages(doc)
    chunks = _split_pages_to_chunks(pages, max_chars=16000)

    if len(chunks) == 1 and not chunks[0].strip():
        return Response({"error": "Aucun texte extrait pour ce document."}, status=status.HTTP_400_BAD_REQUEST)

    summary_prompt_tpl = (
        "Tu es un expert en analyse réglementaire. Rédige un RÉSUMÉ en TEXTE CLAIR (pas de JSON). "
        "Objectif: fournir une synthèse actionnable du document en français (≤ 10 points si nécessaire). "
        "Inclure: objet, portée, obligations majeures, délais, autorités, et toute note critique. "
        "Ne fabrique rien, n'utilise que le texte fourni. Pas de balises, pas de JSON.\n\nTEXTE:\n{body}"
    )

    try:
        annotator = GroqAnnotator()

        partial_summaries = []
        for body in chunks:
            if not body.strip():
                continue
            prompt = summary_prompt_tpl.format(body=body)
            resp = annotator.call_groq_api(prompt, max_tokens=500)
            if not resp:
                continue
            text = str(resp).strip()
            m = re.search(r"Résumé:\s*(.*)$", text, re.DOTALL | re.IGNORECASE)
            summary_text = m.group(1).strip() if m else text
            partial_summaries.append(summary_text)

        if not partial_summaries:
            return Response({"error": "Aucune réponse de Groq."}, status=status.HTTP_502_BAD_GATEWAY)

        final_summary = "\n\n".join(s for s in partial_summaries if s).strip()

        if len(final_summary) > 4500:
            consolidation_prompt = (
                "Synthétise les sous-résumés suivants en un résumé unique, concis et actionnable (français), "
                "en gardant les obligations/délais/autorités. Ne dépasse pas 4500 caractères.\n\n"
                + final_summary[:15000]
            )
            resp2 = annotator.call_groq_api(consolidation_prompt, max_tokens=600)
            if resp2:
                text2 = str(resp2).strip()
                m2 = re.search(r"Résumé:\s*(.*)$", text2, re.DOTALL | re.IGNORECASE)
                final_summary = (m2.group(1).strip() if m2 else text2)[:5000]

        doc.global_annotations_summary = final_summary[:5000]
        doc.global_annotations_summary_generated_at = timezone.now()
        doc.save(update_fields=['global_annotations_summary', 'global_annotations_summary_generated_at'])

        return Response({
            "document_id": doc.id,
            "summary": doc.global_annotations_summary,
            "generated_at": doc.global_annotations_summary_generated_at,
            "cached": False,
        })
    except Exception as e:
        logger.exception("Erreur de génération de résumé Groq")
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)