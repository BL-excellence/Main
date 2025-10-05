from typing import Dict, Any, List
import logging
from .embeddings import embedding_service
from .vector_store import vector_store

logger = logging.getLogger(__name__)

class DocumentIndexer:
    """Indexe les documents JSON enrichis dans le vector store"""
    
    def index_enriched_document(self, expert_json: Dict[str, Any]) -> bool:
        """Indexe un document validé par l'expert"""
        try:
            document_id = str(expert_json["document"]["id"])
            
            # 1. Générer les chunks sémantiques
            chunks = self._generate_semantic_chunks(expert_json)
            
            # 2. Générer les embeddings en batch
            contents = [chunk["content"] for chunk in chunks]
            embeddings = embedding_service.embed_batch(contents)
            
            # 3. Associer embeddings aux chunks
            for chunk, embedding in zip(chunks, embeddings):
                chunk["embedding"] = embedding
                chunk["document_id"] = document_id
            
            # 4. Upsert dans FAISS
            vector_store.upsert_chunks(chunks)
            
            logger.info(f"Document {document_id} indexé avec {len(chunks)} chunks")
            return True
            
        except Exception as e:
            logger.error(f"Erreur lors de l'indexation du document: {e}")
            return False
    
    def _generate_semantic_chunks(self, expert_json: Dict[str, Any]) -> List[Dict]:
        """Génère des chunks sémantiques à partir du JSON enrichi"""
        chunks = []
        doc_id = expert_json["document"]["id"]
        metadata = expert_json["document"]
        
        # CHUNK 1: Métadonnées du document
        meta_content = f"""
        Document: {metadata.get('title', 'N/A')}
        Type: {metadata.get('doc_type', 'N/A')}
        Source: {metadata.get('source', 'N/A')}
        Total pages: {metadata.get('total_pages', 0)}
        Total annotations: {metadata.get('total_annotations', 0)}
        """.strip()
        
        chunks.append({
            "chunk_id": f"{doc_id}_meta",
            "type": "metadata",
            "content": meta_content,
            "metadata": {"section": "document_info"}
        })
        
        # CHUNK 2-N: Un chunk par type d'entité
        for entity_type, entity_data in expert_json.get("entities", {}).items():
            if not entity_data or entity_data.get("count", 0) == 0:
                continue
            
            items = entity_data.get("items", [])
            if not items:
                continue
            
            # Construire le contenu du chunk
            if len(items) == 1:
                content = f"{entity_type}: {items[0]['value']}"
            else:
                values_list = "\n".join([f"- {item['value']}" for item in items])
                content = f"{entity_type} ({len(items)} éléments):\n{values_list}"
            
            chunks.append({
                "chunk_id": f"{doc_id}_entity_{len(chunks)}",
                "type": "entity",
                "content": content,
                "metadata": {
                    "entity_type": entity_type,
                    "entity_count": len(items),
                    "entity_category": self._categorize_entity(entity_type)
                }
            })
        
        # CHUNK N+1: Relations
        relations = expert_json.get("relations", [])
        if relations:
            # Grouper par type de relation
            rel_groups = {}
            for rel in relations:
                rel_type = rel.get("type", "unknown")
                if rel_type not in rel_groups:
                    rel_groups[rel_type] = []
                rel_groups[rel_type].append(rel)
            
            for rel_type, rels in rel_groups.items():
                descriptions = []
                for rel in rels[:10]:  # Limiter à 10 par groupe
                    desc = rel.get("description", "")
                    if desc:
                        descriptions.append(desc)
                
                if descriptions:
                    content = f"Relations de type '{rel_type}':\n" + "\n".join(descriptions)
                    chunks.append({
                        "chunk_id": f"{doc_id}_relation_{rel_type}",
                        "type": "relation",
                        "content": content,
                        "metadata": {
                            "relation_type": rel_type,
                            "relation_count": len(rels)
                        }
                    })
        
        # CHUNK FINAL: Résumé sémantique
        summary = expert_json.get("semantic_summary", "")
        if summary:
            chunks.append({
                "chunk_id": f"{doc_id}_summary",
                "type": "summary",
                "content": f"Résumé du document: {summary}",
                "metadata": {"section": "summary"}
            })
        logger.info(f"Chunks générés pour document {doc_id}: {chunks}")
        return chunks
    
    def _categorize_entity(self, entity_type: str) -> str:
        """Catégorise une entité pour faciliter le filtrage"""
        entity_lower = entity_type.lower()
        
        # Mappings basés sur les mots-clés
        if any(word in entity_lower for word in ["produit", "nom", "dosage", "principe", "actif"]):
            return "product_info"
        elif any(word in entity_lower for word in ["document", "rapport", "certificat", "requis", "obligatoire"]):
            return "documentation"
        elif any(word in entity_lower for word in ["condition", "requis", "norme", "gmp", "validation"]):
            return "requirements"
        elif any(word in entity_lower for word in ["site", "production", "fabrication", "usine"]):
            return "manufacturing"
        elif any(word in entity_lower for word in ["autorité", "authority", "agence", "compétent"]):
            return "regulatory"
        elif any(word in entity_lower for word in ["délai", "delay", "deadline"]):
            return "timeline"
        else:
            return "other"

document_indexer = DocumentIndexer()