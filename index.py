#!/usr/bin/env python
"""
Script pour indexer tous les documents MongoDB dans FAISS
Usage: python index_all_documents.py
"""

import os
import sys
import django
from pathlib import Path

# Configuration Django
BASE_DIR = Path(__file__).resolve().parent
sys.path.append(str(BASE_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'MyProject.settings')
django.setup()

from pymongo import MongoClient
from chatbot.services.document_indexer import document_indexer
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration MongoDB
MONGO_URI = "mongodb://localhost:27017/"
MONGO_DB = "annotations_db"
MONGO_COLLECTION = "documents"

def index_all_documents():
    """Indexe tous les documents de MongoDB dans FAISS"""
    
    try:
        # Connexion MongoDB
        client = MongoClient(MONGO_URI)
        db = client[MONGO_DB]
        collection = db[MONGO_COLLECTION]
        
        # Comptage des documents
        total_docs = collection.count_documents({})
        logger.info(f"📊 {total_docs} documents trouvés dans MongoDB")
        
        if total_docs == 0:
            logger.warning("⚠️ Aucun document à indexer")
            return
        
        # Indexation
        success_count = 0
        error_count = 0
        
        for idx, doc in enumerate(collection.find(), 1):
            doc_id = doc.get("document", {}).get("id")
            doc_title = doc.get("document", {}).get("title", "Sans titre")
            
            logger.info(f"\n{'='*60}")
            logger.info(f"📄 [{idx}/{total_docs}] Indexation: {doc_title} (ID: {doc_id})")
            
            try:
                # Indexer le document
                success = document_indexer.index_enriched_document(doc)
                
                if success:
                    success_count += 1
                    logger.info(f"✅ Document {doc_id} indexé avec succès")
                else:
                    error_count += 1
                    logger.error(f"❌ Échec indexation document {doc_id}")
                    
            except Exception as e:
                error_count += 1
                logger.error(f"❌ Erreur lors de l'indexation du document {doc_id}: {e}")
        
        # Résumé
        logger.info(f"\n{'='*60}")
        logger.info(f"📊 RÉSUMÉ DE L'INDEXATION")
        logger.info(f"{'='*60}")
        logger.info(f"✅ Documents indexés avec succès: {success_count}")
        logger.info(f"❌ Erreurs: {error_count}")
        logger.info(f"📦 Total traité: {success_count + error_count}/{total_docs}")
        
        client.close()
        
    except Exception as e:
        logger.error(f"❌ Erreur critique: {e}")
        sys.exit(1)

if __name__ == "__main__":
    logger.info("🚀 Démarrage de l'indexation...")
    index_all_documents()
    logger.info("✅ Indexation terminée!")