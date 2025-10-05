# chatbot/services/document_service.py
"""
Service centralisé pour gérer les documents
Sauvegarde + Indexation automatique
"""

from typing import Dict, Any, Optional
from pymongo import MongoClient
from django.conf import settings
import logging

from .document_indexer import document_indexer
from ..utils.mongo import get_mongo_collection

logger = logging.getLogger(__name__)

class DocumentService:
    """Service professionnel de gestion des documents"""
    
    def __init__(self):
        self.collection = get_mongo_collection()
    
    def create_document(self, expert_json: Dict[str, Any]) -> Dict[str, Any]:
        """
        Crée un nouveau document et l'indexe automatiquement
        
        Args:
            expert_json: Document enrichi validé par l'expert
            
        Returns:
            Dict avec success, document_id, indexed
        """
        try:
            doc_id = expert_json.get("document", {}).get("id")
            
            if not doc_id:
                return {
                    "success": False,
                    "error": "Document ID manquant"
                }
            
            # 1. Sauvegarder dans MongoDB
            result = self.collection.insert_one(expert_json)
            logger.info(f"✅ Document {doc_id} sauvegardé dans MongoDB")
            
            # 2. Indexer automatiquement dans FAISS
            indexed = document_indexer.index_enriched_document(expert_json)
            
            if indexed:
                logger.info(f"✅ Document {doc_id} indexé dans FAISS")
            else:
                logger.warning(f"⚠️ Document {doc_id} sauvegardé mais non indexé")
            
            return {
                "success": True,
                "document_id": doc_id,
                "mongo_id": str(result.inserted_id),
                "indexed": indexed
            }
            
        except Exception as e:
            logger.exception(f"❌ Erreur create_document: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def update_document(self, document_id: str, expert_json: Dict[str, Any]) -> Dict[str, Any]:
        """
        Met à jour un document existant et réindexe automatiquement
        
        Args:
            document_id: ID du document à mettre à jour
            expert_json: Nouvelles données du document
            
        Returns:
            Dict avec success, updated, reindexed
        """
        try:
            # 1. Mettre à jour dans MongoDB
            result = self.collection.replace_one(
                {"document.id": str(document_id)},
                expert_json,
                upsert=True
            )
            
            logger.info(f"✅ Document {document_id} mis à jour dans MongoDB")
            
            # 2. Réindexer dans FAISS
            reindexed = document_indexer.index_enriched_document(expert_json)
            
            if reindexed:
                logger.info(f"✅ Document {document_id} réindexé dans FAISS")
            
            return {
                "success": True,
                "document_id": document_id,
                "updated": result.modified_count > 0 or result.upserted_id is not None,
                "reindexed": reindexed
            }
            
        except Exception as e:
            logger.exception(f"❌ Erreur update_document: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def delete_document(self, document_id: str) -> Dict[str, Any]:
        """
        Supprime un document de MongoDB et de FAISS
        
        Args:
            document_id: ID du document à supprimer
            
        Returns:
            Dict avec success, deleted_from_mongo, deleted_from_faiss
        """
        try:
            from .vector_store import vector_store
            
            # 1. Supprimer de MongoDB
            result = self.collection.delete_one({"document.id": str(document_id)})
            deleted_from_mongo = result.deleted_count > 0
            
            # 2. Supprimer de FAISS
            try:
                vector_store.delete_document(document_id)
                deleted_from_faiss = True
                logger.info(f"✅ Document {document_id} supprimé de FAISS")
            except Exception as e:
                logger.warning(f"⚠️ Erreur suppression FAISS: {e}")
                deleted_from_faiss = False
            
            logger.info(f"✅ Document {document_id} supprimé de MongoDB")
            
            return {
                "success": True,
                "document_id": document_id,
                "deleted_from_mongo": deleted_from_mongo,
                "deleted_from_faiss": deleted_from_faiss
            }
            
        except Exception as e:
            logger.exception(f"❌ Erreur delete_document: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def get_document(self, document_id: str) -> Optional[Dict[str, Any]]:
        """Récupère un document par son ID"""
        return self.collection.find_one({"document.id": str(document_id)})
    
    def list_documents(self, skip: int = 0, limit: int = 20) -> list:
        """Liste tous les documents avec pagination"""
        return list(self.collection.find().skip(skip).limit(limit))
    
    def reindex_all(self) -> Dict[str, Any]:
        """
        Réindexe tous les documents MongoDB dans FAISS
        Utile pour la maintenance ou après une mise à jour
        """
        try:
            documents = list(self.collection.find())
            total = len(documents)
            success_count = 0
            error_count = 0
            
            logger.info(f"🔄 Réindexation de {total} documents...")
            
            for doc in documents:
                try:
                    if document_indexer.index_enriched_document(doc):
                        success_count += 1
                    else:
                        error_count += 1
                except Exception as e:
                    logger.error(f"Erreur indexation: {e}")
                    error_count += 1
            
            logger.info(f"✅ Réindexation terminée: {success_count} succès, {error_count} erreurs")
            
            return {
                "success": True,
                "total": total,
                "indexed": success_count,
                "errors": error_count
            }
            
        except Exception as e:
            logger.exception(f"❌ Erreur reindex_all: {e}")
            return {
                "success": False,
                "error": str(e)
            }

# Instance singleton
document_service = DocumentService()