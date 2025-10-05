from typing import List, Dict, Any

SYSTEM_PROMPT = """Tu es un assistant expert en documentation pharmaceutique et réglementaire.

RÈGLES STRICTES:
1. Réponds UNIQUEMENT basé sur les informations fournies dans le contexte
2. Si l'information n'est pas disponible, dis explicitement: "Cette information n'est pas disponible dans les documents consultés"
3. Cite TOUJOURS tes sources en utilisant le format [Document ID: XXX]
4. Pour les informations réglementaires critiques (dosages, conditions GMP, documents requis, délais), sois EXTRÊMEMENT précis
5. Structure ta réponse clairement avec des sections si nécessaire
6. Utilise des listes à puces pour améliorer la lisibilité
7. N'invente JAMAIS d'informations
8. Si plusieurs documents contiennent des informations pertinentes, synthétise-les

TYPES D'ENTITÉS À RECONNAÎTRE:
- Produits pharmaceutiques (nom, dosage, principe actif, forme galénique)
- Documents réglementaires (requis, obligatoires, SOPs, certificats)
- Conditions requises (GMP, validation, contrôle qualité, autorisations)
- Sites de production (nom, localisation)
- Autorités compétentes
- Délais et échéances
- Références légales

FORMAT DE RÉPONSE ATTENDU:
- Réponse directe et concise
- Détails pertinents avec citations [Document ID: XXX]
- Si applicable, liste structurée
"""

def build_context(retrieved_chunks: List[Dict[str, Any]]) -> str:
    """Construit le contexte pour le LLM à partir des chunks récupérés"""
    context_parts = []
    
    for idx, item in enumerate(retrieved_chunks, 1):
        chunk = item["chunk"]
        doc = item["document"]
        score = item["score"]
        
        context_parts.append(f"\n{'='*60}")
        context_parts.append(f"SOURCE {idx} [Document ID: {doc['id']}]")
        context_parts.append(f"Titre: {doc['title']}")
        context_parts.append(f"Type: {doc['doc_type']}")
        context_parts.append(f"Pertinence: {score:.3f}")
        context_parts.append(f"{'='*60}\n")
        
        # Contenu du chunk
        context_parts.append(f"[{chunk['type'].upper()}]")
        context_parts.append(chunk['content'])
        context_parts.append("")
        
        # Ajouter quelques entités clés si pertinentes
        if chunk['type'] == 'entity' and doc.get('entities'):
            entity_type = chunk.get('metadata', {}).get('entity_type')
            if entity_type and entity_type in doc['entities']:
                context_parts.append(f"[Contexte additionnel - Entité: {entity_type}]")
                entity_data = doc['entities'][entity_type]
                primary = entity_data.get('primary', {})
                if primary:
                    context_parts.append(f"Valeur principale: {primary.get('value', 'N/A')}")
                context_parts.append("")
    
    return "\n".join(context_parts)