from typing import List, Dict, Any, Optional
import logging
from .embeddings import embedding_service
from .vector_store import vector_store
from chatbot.utils.mongo import get_mongo_collection

logger = logging.getLogger(__name__)

class HybridRetriever:
    """Récupération hybride: vectorielle + MongoDB"""
    
    def __init__(self):
        self.mongo_collection = get_mongo_collection()
    
    def retrieve(
        self,
        question: str,
        document_id: Optional[str] = None,
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """Récupère les chunks pertinents pour une question"""
        
        # 1. Générer l'embedding de la question
        query_embedding = embedding_service.embed_text(question)
        
        # 2. Recherche vectorielle
        vector_results = vector_store.search(
            query_vector=query_embedding,
            limit=top_k * 2,
            document_id=document_id
        )
        
        logger.info(f"Vector results: {len(vector_results)} chunks found")
        
        # 3. Enrichir avec les données MongoDB complètes
        enriched_results = []
        seen_docs = set()
        
        for result in vector_results:
            payload = result["payload"]
            doc_id = payload["document_id"]
            
            if doc_id in seen_docs:
                continue
            seen_docs.add(doc_id)
            
            mongo_doc = self.mongo_collection.find_one(
                {"document.id": str(doc_id)}
            )
            
            if mongo_doc:
                enriched_results.append({
                    "score": float(result["score"]),  # ✅ CORRECTION ICI : convertir en float Python
                    "chunk": payload,
                    "document": {
                        "id": doc_id,
                        "title": mongo_doc.get("document", {}).get("title", ""),
                        "doc_type": mongo_doc.get("document", {}).get("doc_type", ""),
                        "source": mongo_doc.get("document", {}).get("source", ""),
                        "entities": mongo_doc.get("entities", {}),
                        "relations": mongo_doc.get("relations", [])
                    }
                })
            
            if len(enriched_results) >= top_k:
                break
        
        logger.info(f"Enriched results: {len(enriched_results)} chunks")
        return enriched_results

retriever = HybridRetriever()