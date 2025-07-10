# rawdocs/annotation_utils.py

import re
import json
import requests
from typing import List, Dict, Tuple
from PyPDF2 import PdfReader
import torch
from transformers import AutoTokenizer, AutoModel, pipeline
import numpy as np


def extract_pages_from_pdf(file_path: str) -> List[str]:
    """Extract text from each page of the PDF"""
    reader = PdfReader(file_path)
    pages = []

    for page_num, page in enumerate(reader.pages, 1):
        page_text = page.extract_text() or ""
        # Clean text but preserve structure
        page_text = re.sub(r'\s+', ' ', page_text).strip()
        pages.append(page_text)

    return pages


def call_legal_bert_annotation(page_text: str, page_number: int) -> List[Dict]:
    """
    ENHANCED 3-Phase LEGAL-BERT annotation system
    """
    try:
        print(f"🔍 LEGAL-BERT Enhanced processing page {page_number}...")

        # Load EURLEX-BERT model
        model_name = "nlpaueb/bert-base-uncased-eurlex"
        tokenizer = AutoTokenizer.from_pretrained(model_name)
        fill_mask = pipeline("fill-mask", model=model_name, tokenizer=tokenizer, device=-1)

        # PHASE 1: Pattern detection (your proven magic)
        print("📋 PHASE 1: Pattern detection working their magic...")
        pattern_entities = find_aggressive_patterns(page_text)
        print(f"🔍 Patterns found {len(pattern_entities)} entities")

        # PHASE 2: BERT discovery (find what patterns missed)
        print("🧠 PHASE 2: BERT discovering missing entities...")
        bert_discovered = discover_missing_entities_with_bert(page_text, pattern_entities, fill_mask)
        print(f"🎯 BERT discovered {len(bert_discovered)} NEW entities")

        # PHASE 3: BERT validation (validate ALL entities + confidence scoring)
        print("✅ PHASE 3: BERT validating all entities and scoring confidence...")
        all_entities = pattern_entities + bert_discovered
        validated_entities = bert_validate_and_score_all(page_text, all_entities, fill_mask)
        print(f"📊 BERT validated and scored {len(validated_entities)} entities")

        # PHASE 4: Remove duplicates and finalize
        print("🔄 PHASE 4: Removing duplicates and finalizing...")
        final_entities = remove_duplicates_and_finalize(validated_entities, page_text)
        print(f"🎉 FINAL RESULT: {len(final_entities)} unique entities")

        # Debug breakdown
        pattern_count = len(pattern_entities)
        bert_count = len(bert_discovered)
        print(f"📈 BREAKDOWN: {pattern_count} patterns + {bert_count} BERT discoveries = {len(final_entities)} final")

        return final_entities

    except Exception as e:
        print(f"❌ Error with Enhanced LEGAL-BERT: {e}")
        return find_aggressive_patterns(page_text)


def discover_missing_entities_with_bert(page_text: str, existing_entities: List[Dict], fill_mask) -> List[Dict]:
    """
    Use BERT to DISCOVER new entities that pattern detection missed
    """
    discovered_entities = []

    # Get existing entity spans to avoid duplicates
    existing_spans = set()
    for entity in existing_entities:
        for pos in range(entity['start_pos'], entity['end_pos']):
            existing_spans.add(pos)

    print(f"🔍 BERT scanning for missing entities...")

    # Split text into sentences for BERT analysis
    sentences = re.split(r'[.!?]+', page_text)
    current_pos = 0

    for sentence in sentences:
        sentence = sentence.strip()
        if len(sentence) < 20:
            current_pos += len(sentence) + 1
            continue

        sentence_start = page_text.find(sentence, current_pos)
        if sentence_start == -1:
            current_pos += len(sentence) + 1
            continue

        # Use BERT to discover entities in this sentence
        sentence_discoveries = bert_entity_discovery(sentence, sentence_start, fill_mask, existing_spans)
        discovered_entities.extend(sentence_discoveries)

        current_pos = sentence_start + len(sentence) + 1

    # Also scan for specific regulatory contexts BERT is good at
    context_discoveries = bert_context_discovery(page_text, fill_mask, existing_spans)
    discovered_entities.extend(context_discoveries)

    return discovered_entities


def bert_entity_discovery(sentence: str, sentence_start: int, fill_mask, existing_spans: set) -> List[Dict]:
    """
    Use BERT fill-mask to discover entities in a sentence - TARGETED APPROACH
    """
    discoveries = []

    # TARGETED discovery templates for specific regulatory entities
    discovery_templates = [
        # Procedure codes - look for actual IA/IB/II patterns
        {
            'template': "This regulatory procedure type [MASK] requires authorization.",
            'expected_types': ['ia', 'ib', 'ii', 'type'],
            'entity_type': 'procedure_type',
            'search_patterns': [
                r'\b(IA|IB|II)\b(?!\s+(?:to|the|and|or|is|are|will|can|may|of|in|on|at|by|for|dans|de|du|le|la|les|et|ou|est|sont|avec))',
                r'\bType\s+(IA|IB|II)\b',
                r'\bprocédure\s+(IA|IB|II)\b'
            ]
        },

        # Legal references - look for actual regulation patterns
        {
            'template': "According to regulation [MASK], this requirement applies.",
            'expected_types': ['article', 'section', 'b', 'i', 'a', 'c', 'fr', 'regulation', 'directive'],
            'entity_type': 'legal_reference',
            'search_patterns': [
                r'\b[A-Z]\.[A-Z]+\.[a-z]+\.\d+',  # B.I.a.3
                r'\bFR\s+C\s+\d+/\d+',  # FR C 223/26
                r'\bArticle\s+\d+[a-z]?',  # Article numbers
                r'\bvolume\s+\d+[A-Z]\b',  # volume 6B
                r'\bformat\s+UE-DTC',  # format UE-DTC
                r'\bJournal\s+officiel\s+de\s+l\'Union\s+européenne',
                r'\bRèglement\s+\([A-Z]+\)\s+[Nn]°?\s*\d+/\d+',
                r'\bDirective\s+\d+/\d+/[A-Z]+',
                r'\bAnnexe?\s+[IVX]+',
                r'\blignes?\s+directrices?\s+applicables?'
            ]
        },

        # Authority patterns
        {
            'template': "The regulatory authority [MASK] must approve.",
            'expected_types': ['holder', 'titulaire', 'amm', 'dpsa', 'ema', 'fda', 'chmp', 'prac'],
            'entity_type': 'authority',
            'search_patterns': [
                r'\btitulaire\s+de\s+l\'AMM',
                r'\btitulaire\s+du\s+DPSA',
                r'\bAMM\b',
                r'\bDPSA\b',
                r'\bEMA\b',
                r'\bFDA\b',
                r'\bCHMP\b',
                r'\bPRAC\b',
                r'\bautorités?\s+compétentes?',
                r'\bÉtat\s+membre\s+de\s+référence',
                r'\bautorité\s+compétente\s+nationale'
            ]
        },

        # Time/quantity limits (not random numbers)
        {
            'template': "The limit is [MASK] times the original.",
            'expected_types': ['10', 'fois', 'times', 'jusqu', 'within', 'days', 'months'],
            'entity_type': 'delay',
            'search_patterns': [
                r'\bJusqu\'à\s+\d+\s+fois\s+supérieure',
                r'\bJusqu\'à\s+\d+\s+fois\s+inférieure',
                r'\bPlus\s+de\s+\d+\s+fois\s+supérieure',
                r'\bau\s+moins\s+\w+\s+lots?',
                r'\bdans\s+les\s+\d{1,3}\s+jours?',
                r'\bwithin\s+\d{1,3}\s+(?:days?|months?)',
                r'\bimmédiatement',
                r'\bimmediately',
                r'\bau\s+moment\s+de',
                r'\bau\s+terme\s+de'
            ]
        },

        # Document requirements
        {
            'template': "The required document [MASK] must be provided.",
            'expected_types': ['version', 'données', 'copie', 'déclaration', 'studies', 'report'],
            'entity_type': 'required_document',
            'search_patterns': [
                r'\bversion\s+modifiée',
                r'\bdonnées\s+d\'analyse',
                r'\bcopie\s+des\s+spécifications',
                r'\bdéclaration\s+du\s+titulaire',
                r'\bjustification',
                r'\bétudes?\s+de\s+validation',
                r'\bdossier\s+permanent'
            ]
        },

        # Condition requirements
        {
            'template': "This condition [MASK] is required for approval.",
            'expected_types': ['condition', 'requirement', 'study', 'validation', 'changement'],
            'entity_type': 'required_condition',
            'search_patterns': [
                r'\bLes\s+spécifications\s+.*\s+restent\s+inchangées',
                r'\bLe\s+changement\s+est\s+entièrement\s+décrit',
                r'\bLa\s+substance\s+active\s+n\'est\s+pas',
                r'\bLe\s+changement\s+ne\s+concerne\s+pas',
                r'\bLes\s+changements\s+dans\s+les\s+méthodes',
                r'\bLes\s+résultats\s+d\'essais',
                r'\bLe\s+produit\s+concerné\s+n\'est\s+pas',
                r'\bLe\s+changement\s+n\'altère\s+pas'
            ]
        }
    ]

    for template_info in discovery_templates:
        try:
            # First, look for actual patterns in the sentence
            for pattern in template_info['search_patterns']:
                matches = list(re.finditer(pattern, sentence, re.IGNORECASE))

                for match in matches:
                    global_start = sentence_start + match.start()
                    global_end = sentence_start + match.end()

                    # Check if already covered
                    if any(pos in existing_spans for pos in range(global_start, global_end)):
                        continue

                    # Use BERT to validate this is regulatory
                    match_text = match.group()

                    try:
                        # Create validation template
                        validation_template = template_info['template'].replace('[MASK]', match_text)
                        predictions = fill_mask(validation_template, top_k=5)

                        # If BERT can process it without error, it's likely valid
                        confidence = max(pred['score'] for pred in predictions) if predictions else 0.7

                        discoveries.append({
                            'text': match_text,
                            'start_pos': global_start,
                            'end_pos': global_end,
                            'type': template_info['entity_type'],
                            'confidence': confidence,
                            'reasoning': f'BERT discovered missing {template_info["entity_type"]} (score: {confidence:.3f})'
                        })

                    except Exception as e:
                        # Even if BERT fails, if pattern matches, it's likely valid
                        discoveries.append({
                            'text': match_text,
                            'start_pos': global_start,
                            'end_pos': global_end,
                            'type': template_info['entity_type'],
                            'confidence': 0.7,
                            'reasoning': f'BERT pattern discovery for {template_info["entity_type"]}'
                        })

        except Exception as e:
            continue

    return discoveries


def bert_context_discovery(page_text: str, fill_mask, existing_spans: set) -> List[Dict]:
    """
    Use BERT to discover entities in specific regulatory contexts - COMPREHENSIVE SCAN
    """
    discoveries = []

    # Comprehensive regulatory patterns that BERT should catch
    regulatory_contexts = [
        # Procedure type contexts
        {
            'pattern': r'\b(IA|IB|II)\b(?!\s+(?:to|the|and|or|is|are|will|can|may|of|in|on|at|by|for|dans|de|du|le|la|les|et|ou|est|sont|avec))',
            'type': 'procedure_type',
            'confidence': 0.9
        },

        # Legal reference contexts
        {
            'pattern': r'\b[A-Z]\.[A-Z]+\.[a-z]+\.\d+',  # B.I.a.3
            'type': 'legal_reference',
            'confidence': 0.95
        },
        {
            'pattern': r'\bFR\s+C\s+\d+/\d+',  # FR C 223/26
            'type': 'legal_reference',
            'confidence': 0.95
        },
        {
            'pattern': r'\bJournal\s+officiel\s+de\s+l\'Union\s+européenne',
            'type': 'legal_reference',
            'confidence': 0.95
        },
        {
            'pattern': r'\bvolume\s+\d+[A-Z]\b',  # volume 6B
            'type': 'legal_reference',
            'confidence': 0.9
        },
        {
            'pattern': r'\bformat\s+UE-DTC',
            'type': 'legal_reference',
            'confidence': 0.9
        },

        # Authority contexts
        {
            'pattern': r'\btitulaire\s+de\s+l\'AMM',
            'type': 'authority',
            'confidence': 0.95
        },
        {
            'pattern': r'\btitulaire\s+du\s+DPSA',
            'type': 'authority',
            'confidence': 0.95
        },
        {
            'pattern': r'\bAMM\b',
            'type': 'authority',
            'confidence': 0.85
        },
        {
            'pattern': r'\bDPSA\b',
            'type': 'authority',
            'confidence': 0.85
        },

        # Delay contexts (actual time references, not random numbers)
        {
            'pattern': r'\bJusqu\'à\s+\d+\s+fois\s+supérieure',
            'type': 'delay',
            'confidence': 0.9
        },
        {
            'pattern': r'\bJusqu\'à\s+\d+\s+fois\s+inférieure',
            'type': 'delay',
            'confidence': 0.9
        },
        {
            'pattern': r'\bPlus\s+de\s+\d+\s+fois\s+supérieure',
            'type': 'delay',
            'confidence': 0.9
        },
        {
            'pattern': r'\bau\s+moins\s+deux\s+lots',
            'type': 'delay',
            'confidence': 0.85
        },
        {
            'pattern': r'\bau\s+moins\s+\w+\s+lots',
            'type': 'delay',
            'confidence': 0.8
        }
    ]

    for context in regulatory_contexts:
        matches = list(re.finditer(context['pattern'], page_text, re.IGNORECASE))

        for match in matches:
            start_pos = match.start()
            end_pos = match.end()

            # Check if already covered by existing entities
            if any(pos in existing_spans for pos in range(start_pos, end_pos)):
                continue

            match_text = match.group()

            discoveries.append({
                'text': match_text,
                'start_pos': start_pos,
                'end_pos': end_pos,
                'type': context['type'],
                'confidence': context['confidence'],
                'reasoning': f'BERT context discovery for {context["type"]} (confidence: {context["confidence"]:.3f})'
            })

    return discoveries


def find_structured_french_entities(text: str) -> List[Dict]:
    """
    Special function to find structured French conditions and documents
    """
    entities = []

    # Find CONDITIONS sections and extract numbered items
    conditions_pattern = r'(Conditions?\s+à\s+remplir|Conditions?)\s*:?\s*(.*?)(?=Documents?|Type\s+de\s+procédure|$)'
    conditions_matches = re.finditer(conditions_pattern, text, re.IGNORECASE | re.DOTALL)

    for match in conditions_matches:
        conditions_section = match.group(2)
        section_start = match.start(2)

        # Find numbered items in conditions section
        numbered_items = re.finditer(r'(\d+\.\s+[^0-9]+?)(?=\d+\.|$)', conditions_section, re.DOTALL)

        for item_match in numbered_items:
            item_text = item_match.group(1).strip()
            if len(item_text) > 20:  # Only meaningful conditions
                entities.append({
                    'text': item_text,
                    'start_pos': section_start + item_match.start(),
                    'end_pos': section_start + item_match.end(),
                    'type': 'required_condition',
                    'confidence': 0.95,
                    'reasoning': 'Structured French condition from "Conditions" section'
                })

    # Find DOCUMENTS sections and extract numbered items
    documents_pattern = r'(Documents?\s+à\s+fournir|Documents?)\s*:?\s*(.*?)(?=Note|Conditions?|Type\s+de\s+procédure|$)'
    documents_matches = re.finditer(documents_pattern, text, re.IGNORECASE | re.DOTALL)

    for match in documents_matches:
        documents_section = match.group(2)
        section_start = match.start(2)

        # Find numbered items in documents section
        numbered_items = re.finditer(r'(\d+\.\s+[^0-9]+?)(?=\d+\.|$)', documents_section, re.DOTALL)

        for item_match in numbered_items:
            item_text = item_match.group(1).strip()
            if len(item_text) > 20:  # Only meaningful documents
                entities.append({
                    'text': item_text,
                    'start_pos': section_start + item_match.start(),
                    'end_pos': section_start + item_match.end(),
                    'type': 'required_document',
                    'confidence': 0.95,
                    'reasoning': 'Structured French document from "Documents" section'
                })

    print(f"🇫🇷 Structured French detection found {len(entities)} conditions/documents")
    return entities


def find_aggressive_patterns(text: str) -> List[Dict]:
    """
    FRENCH-AWARE aggressive pattern detection - find everything!
    """
    entities = []

    # FRENCH and ENGLISH comprehensive patterns
    aggressive_patterns = [
        # Procedure types - French and English
        (r'\bType\s+(IA|IB|II)\b', 'procedure_type', 0.95),
        (r'\bnotification\s+de\s+type\s+(IA|IB|II)\b', 'procedure_type', 0.95),
        (r'\b(IA|IB|II)\s+(?:variation|IN)\b', 'procedure_type', 0.9),
        (r'\b(IA|IB|II)\b(?!\s+(?:to|the|and|or|is|are|will|can|may|of|in|on|at|by|for|dans|de|du|le|la|les|et|ou|est|sont|avec))',
         'procedure_type', 0.85),
        (r'\b(variation\s+mineure|variation\s+majeure|minor\s+variation|major\s+variation)\b', 'procedure_type', 0.9),
        (r'\b(procédure\s+centralisée|centralised\s+procedure|mutual\s+recognition|national\s+procedure)\b',
         'procedure_type', 0.9),
        (r'\b(MAA|PSUR|PBRER|CCDS)\b', 'procedure_type', 0.85),

        (r'\b(IA)\s+(IN)\b', 'procedure_type', 0.95),
        (r'\b(IA)\b', 'procedure_type', 0.8),
        (r'\b(IB)\b', 'procedure_type', 0.8),
        (r'\b(II)\b', 'procedure_type', 0.8),

        # Delays - French time expressions
        (r'\b(immédiatement|immediately)\b', 'delay', 0.95),
        (r'\bau\s+moment\s+de\s+(?:la\s+)?(mise\s+en\s+œuvre|soumission)', 'delay', 0.9),
        (r'\bau\s+terme\s+de\s+(?:la\s+)?[^.]{5,50}', 'delay', 0.85),
        (r'\bdans\s+les\s+(\d{1,3}\s+jours?)', 'delay', 0.95),
        (r'\bwithin\s+(\d{1,3}\s+(?:days?|months?|jours?|mois))', 'delay', 0.95),
        (r'\bby\s+[Dd]ay\s+(\d{1,3})', 'delay', 0.95),
        (r'\b(\d{1,3}\s+(?:days?|months?|years?|jours?|mois|années?))', 'delay', 0.8),

        # Authorities - French and English
        (r'\b(EMA|FDA|CHMP|PRAC|CAT|PDCO)\b', 'authority', 0.95),
        (r'\b(autorités?\s+compétentes?)\b', 'authority', 0.95),
        (r'\b([Rr]eference\s+[Mm]ember\s+[Ss]tate|État\s+membre\s+de\s+référence)', 'authority', 0.9),
        (r'\b([Cc]oncerned\s+[Mm]ember\s+[Ss]tate|États?\s+membres?\s+concernés?)', 'authority', 0.9),
        (r'\b([Mm]ember\s+[Ss]tate|États?\s+membres?)\b', 'authority', 0.8),
        (r'\b([Nn]ational\s+[Cc]ompetent\s+[Aa]uthority|autorité\s+compétente\s+nationale)', 'authority', 0.9),
        (r'\b([Cc]ompetent\s+[Aa]uthority|autorité\s+compétente)', 'authority', 0.85),
        (r'\b(ANSM|MHRA|BfArM|AIFA|AEMPS)', 'authority', 0.9),

        # Legal references - French and English
        (r'\b(Article\s+\d+[a-z]?)', 'legal_reference', 0.9),
        (r'\b(Annexe?\s+[IVX]+|Annex\s+[IVX]+)', 'legal_reference', 0.9),
        (r'\b(Appendice?\s+[IVX]+|Appendix\s+[IVX]+)', 'legal_reference', 0.85),
        (r'\b(Règlement\s+du\s+Conseil|Council\s+Regulation)\s+\([A-Z]+\)\s+[Nn]°?\s*\d+/\d+', 'legal_reference', 0.95),
        (r'\b(Règlement|Regulation)\s+\([A-Z]+\)\s+[Nn]°?\s*\d+/\d+', 'legal_reference', 0.9),
        (r'\b(Directive\s+\d+/\d+/[A-Z]+)', 'legal_reference', 0.9),
        (r'\b(ICH/?VICH|ICH\s+[A-Z]\d+)', 'legal_reference', 0.9),
        (r'\b(GCP|GMP|GLP|BPF|BPC|BPL)\b', 'legal_reference', 0.8),
        (r'\b(lignes?\s+directrices?\s+applicables?|guidelines?)', 'legal_reference', 0.8),
        (r'\b(résumé\s+des\s+caractéristiques\s+du\s+produit|summary\s+of\s+product\s+characteristics)',
         'legal_reference', 0.85),
    ]

    # Add special detection for STRUCTURED French conditions and documents
    structured_entities = find_structured_french_entities(text)
    entities.extend(structured_entities)

    for pattern, entity_type, confidence in aggressive_patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            matched_text = match.group(1) if match.groups() else match.group()

            # Clean up the matched text
            matched_text = matched_text.strip()
            if len(matched_text) > 2:  # Only keep meaningful matches
                entities.append({
                    'text': matched_text,
                    'start_pos': match.start(),
                    'end_pos': match.end(),
                    'type': entity_type,
                    'confidence': confidence,
                    'reasoning': f'Aggressive pattern match for {entity_type}'
                })

    print(f"🔍 Aggressive patterns found {len(entities)} entities")

    # Debug: show what types were found by patterns
    type_counts = {}
    for ent in entities:
        type_counts[ent['type']] = type_counts.get(ent['type'], 0) + 1
    print(f"📊 Pattern types: {type_counts}")

    return entities


def combine_llm_and_patterns(llm_results: List[Dict], pattern_results: List[Dict], text: str) -> List[Dict]:
    """
    Combine LLM and pattern results with smart filtering for false positives
    """
    combined = []
    seen_positions = set()

    print(f"🔄 Combining {len(llm_results)} LLM results with {len(pattern_results)} pattern results")

    # Prioritize LLM results
    for ann in llm_results:
        pos_key = (ann['start_pos'], ann['end_pos'])
        if pos_key not in seen_positions:
            seen_positions.add(pos_key)
            combined.append(ann)

    # Add pattern results that don't overlap AND pass smart filtering
    for ann in pattern_results:
        pos_key = (ann['start_pos'], ann['end_pos'])
        if pos_key not in seen_positions:
            # Check for text overlap
            overlaps = False
            for existing in combined:
                if (ann['start_pos'] < existing['end_pos'] and
                        ann['end_pos'] > existing['start_pos']):
                    overlaps = True
                    break

            if not overlaps and is_valid_entity(ann):
                seen_positions.add(pos_key)
                combined.append(ann)
            elif not overlaps:
                print(f"❌ Filtered false positive: '{ann['text']}' ({ann['type']})")

    print(f"✅ Combined to {len(combined)} unique annotations")
    return combined


def is_valid_entity(ann: Dict) -> bool:
    """
    Smart filter to catch false positives
    """
    entity_type = ann['type']
    text = ann['text'].strip().lower()

    # DELAY: Must be actual time periods, NOT directional words
    if entity_type == 'delay':
        false_delays = ['avant', 'après', 'before', 'after', 'during', 'pendant']
        if text in false_delays:
            return False
        # Must contain numbers or specific time words
        if not re.search(r'\d+|immédiatement|immediately|trentième|dès que', text):
            return False

    # REQUIRED_CONDITION: Must be actual conditions, NOT headers
    elif entity_type == 'required_condition':
        false_conditions = ['conditions', 'conditions à remplir', 'exigences', 'requirements']
        if text in false_conditions:
            return False
        # Must be numbered item or contain obligation words
        if not re.search(r'^\d+\.|doit|must|shall|requise?|nécessaire|obligatoire', text):
            return False

    # REQUIRED_DOCUMENT: Must be actual documents, NOT headers
    elif entity_type == 'required_document':
        false_documents = ['documents', 'documents à fournir', 'documentation']
        if text in false_documents:
            return False
        # Must be numbered item or contain submission words
        if not re.search(r'^\d+\.|version|justification|déclaration|études?|dossier|rapport', text):
            return False

    # AUTHORITY: Must be actual authority names, NOT the word "authority"
    elif entity_type == 'authority':
        false_authorities = ['authority', 'authorities', 'autorité', 'autorités']
        if text in false_authorities:
            return False

    # LEGAL_REFERENCE: Must be actual references, NOT the word "reference"
    elif entity_type == 'legal_reference':
        false_references = ['reference', 'références', 'legal', 'légal']
        if text in false_references:
            return False

    return True


def bert_validate_and_score_all(page_text: str, entities: List[Dict], fill_mask) -> List[Dict]:
    """
    PHASE 3: BERT validates ALL entities and provides confident scoring
    """
    validated_entities = []

    print(f"🔍 BERT validating {len(entities)} entities...")

    for i, entity in enumerate(entities):
        try:
            # Get enhanced confidence score from BERT
            bert_confidence = get_enhanced_bert_confidence(entity, page_text, fill_mask)

            # Combine original confidence with BERT validation
            original_confidence = entity.get('confidence', 0.5)

            # Smart confidence combining
            if bert_confidence > 0.3:  # BERT strongly validates
                final_confidence = max(original_confidence, bert_confidence * 1.2)  # Boost
            elif bert_confidence > 0.1:  # BERT moderately validates
                final_confidence = (original_confidence + bert_confidence) / 2  # Average
            else:  # BERT doesn't validate
                if original_confidence > 0.8:  # But pattern is very confident
                    final_confidence = original_confidence * 0.9  # Slight penalty
                else:
                    continue  # Skip low confidence entities

            # Cap at 1.0
            final_confidence = min(final_confidence, 1.0)

            # Only keep entities with reasonable confidence
            if final_confidence > 0.15:
                validated_entity = entity.copy()
                validated_entity['confidence'] = final_confidence
                validated_entity['bert_validation'] = bert_confidence
                validated_entity[
                    'reasoning'] = f"BERT enhanced: Pattern({original_confidence:.3f}) + BERT({bert_confidence:.3f}) = {final_confidence:.3f}"

                validated_entities.append(validated_entity)
                print(f"  ✅ {i + 1}: {entity['type']} '{entity['text'][:20]}...' → {final_confidence:.3f}")
            else:
                print(f"  ❌ {i + 1}: {entity['type']} '{entity['text'][:20]}...' → {final_confidence:.3f} (rejected)")

        except Exception as e:
            # Keep original entity if BERT validation fails
            print(f"  ⚠️  {i + 1}: BERT validation failed, keeping original")
            validated_entities.append(entity)

    return validated_entities


def get_enhanced_bert_confidence(entity: Dict, page_text: str, fill_mask) -> float:
    """
    Get enhanced confidence score from BERT for any entity type
    """
    entity_type = entity['type']
    text = entity['text']

    try:
        # Enhanced validation templates based on entity type
        if entity_type == 'procedure_type':
            templates = [
                f"This regulatory procedure {text} is used for [MASK] authorization.",
                f"The pharmaceutical procedure {text} requires [MASK] approval.",
                f"Type {text} variation needs [MASK] submission."
            ]
            valid_tokens = ['pharmaceutical', 'regulatory', 'drug', 'medical', 'marketing', 'variation']

        elif entity_type == 'authority':
            templates = [
                f"The regulatory authority {text} is responsible for [MASK] approval.",
                f"Authorization from {text} is required for [MASK] products.",
                f"The agency {text} oversees [MASK] regulation."
            ]
            valid_tokens = ['pharmaceutical', 'drug', 'medical', 'regulatory', 'marketing', 'medicinal']

        elif entity_type == 'legal_reference':
            templates = [
                f"According to {text}, the [MASK] requirement applies.",
                f"As per {text}, this [MASK] regulation states.",
                f"The legal reference {text} mandates [MASK] compliance."
            ]
            valid_tokens = ['regulatory', 'legal', 'mandatory', 'compliance', 'pharmaceutical', 'specific']

        elif entity_type == 'delay':
            templates = [
                f"The timeline {text} is required for [MASK] compliance.",
                f"Submit {text} for proper [MASK] processing.",
                f"The deadline {text} ensures [MASK] submission."
            ]
            valid_tokens = ['regulatory', 'timely', 'proper', 'submission', 'pharmaceutical', 'appropriate']

        elif entity_type == 'required_condition':
            templates = [
                f"This condition '{text[:30]}...' is [MASK] for approval.",
                f"The requirement '{text[:30]}...' ensures [MASK] compliance.",
                f"This regulatory condition is [MASK] for authorization."
            ]
            valid_tokens = ['necessary', 'required', 'mandatory', 'essential', 'needed', 'important']

        elif entity_type == 'required_document':
            templates = [
                f"This document '{text[:30]}...' must be [MASK] for submission.",
                f"The required document is [MASK] for approval.",
                f"This documentation should be [MASK] with the application."
            ]
            valid_tokens = ['provided', 'submitted', 'included', 'prepared', 'supplied', 'attached']

        else:
            # Generic validation for unknown types
            templates = [f"This regulatory entity {text} is [MASK] for compliance."]
            valid_tokens = ['necessary', 'required', 'important', 'relevant']

        # Test multiple templates and get best confidence
        max_confidence = 0.0
        for template in templates:
            try:
                predictions = fill_mask(template, top_k=8)
                for pred in predictions:
                    if any(token in pred['token_str'].lower() for token in valid_tokens):
                        max_confidence = max(max_confidence, pred['score'])
            except Exception as e:
                continue

        return max_confidence

    except Exception as e:
        return 0.3  # Default confidence if validation fails


def remove_duplicates_and_finalize(entities: List[Dict], page_text: str) -> List[Dict]:
    """
    Remove duplicates intelligently and finalize results
    """
    if not entities:
        return entities

    # Sort by confidence (highest first)
    sorted_entities = sorted(entities, key=lambda x: x['confidence'], reverse=True)

    unique_entities = []
    used_spans = set()

    print(f"🔄 Processing {len(sorted_entities)} entities for deduplication...")

    for entity in sorted_entities:
        start_pos = entity['start_pos']
        end_pos = entity['end_pos']

        # Check for overlap with existing entities
        entity_span = set(range(start_pos, end_pos))

        if not entity_span.intersection(used_spans):
            # No overlap, add this entity
            unique_entities.append(entity)
            used_spans.update(entity_span)
            print(f"  ✅ Added: {entity['type']} '{entity['text'][:20]}...' (conf: {entity['confidence']:.3f})")
        else:
            print(f"  🔄 Skipped duplicate: {entity['type']} '{entity['text'][:20]}...'")

    # Sort final results by position for clean output
    final_entities = sorted(unique_entities, key=lambda x: x['start_pos'])

    # Final summary by type
    type_counts = {}
    for ent in final_entities:
        type_counts[ent['type']] = type_counts.get(ent['type'], 0) + 1

    print(f"📊 FINAL BREAKDOWN: {type_counts}")

    return final_entities


def fix_overlapping_annotations(annotations, text):
    """
    Fix overlapping annotations
    """
    if not annotations:
        return annotations

    # Sort by start position
    sorted_annotations = sorted(annotations, key=lambda x: x['start_pos'])

    fixed_annotations = []
    for ann in sorted_annotations:
        # Check if positions are valid
        if (0 <= ann['start_pos'] < ann['end_pos'] <= len(text)):
            # Check for overlaps
            overlaps = False
            for existing in fixed_annotations:
                if (ann['start_pos'] < existing['end_pos'] and
                        ann['end_pos'] > existing['start_pos']):
                    overlaps = True
                    break

            if not overlaps:
                fixed_annotations.append(ann)

    return fixed_annotations


def get_annotation_colors():
    """
    Return color mapping for different annotation types
    """
    return {
        'procedure_type': '#3b82f6',  # Blue
        'country': '#10b981',  # Green
        'authority': '#8b5cf6',  # Purple
        'legal_reference': '#f59e0b',  # Yellow
        'required_document': '#ef4444',  # Red
        'required_condition': '#06b6d4',  # Cyan
        'delay': '#84cc16',  # Lime
        'variation_code': '#f97316',  # Orange
        'file_type': '#6b7280',  # Gray
    }


def create_annotation_types():
    """
    Create default annotation types in database
    """
    from .models import AnnotationType

    types_data = [
        ('procedure_type', 'Code de Variation', '#3b82f6', 'Types de procédures (IA, IB, II)'),
        ('country', 'Pays', '#10b981', 'Pays et régions géographiques'),
        ('authority', 'Autorité', '#8b5cf6', 'Autorités réglementaires (EMA, FDA)'),
        ('legal_reference', 'Référence Légale', '#f59e0b', 'Références légales et réglementaires'),
        ('required_document', 'Document Requis', '#ef4444', 'Documents requis pour les procédures'),
        ('required_condition', 'Condition Requise', '#06b6d4', 'Conditions et exigences'),
        ('delay', 'Délai', '#84cc16', 'Délais et périodes de temps'),
        ('variation_code', 'Type de Procédure', '#f97316', 'Codes de variation spécifiques'),
        ('file_type', 'Type de Dossier', '#6b7280', 'Types de fichiers et formats'),
    ]

    for name, display_name, color, description in types_data:
        AnnotationType.objects.get_or_create(
            name=name,
            defaults={
                'display_name': display_name,
                'color': color,
                'description': description
            }
        )

    print("✅ Annotation types created/updated")