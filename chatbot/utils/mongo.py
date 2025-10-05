from pymongo import MongoClient
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

_mongo_client = None
_mongo_collection = None

def get_mongo_collection():
    """Récupère la collection MongoDB (singleton)"""
    global _mongo_client, _mongo_collection
    
    if _mongo_collection is not None:
        return _mongo_collection
    
    try:
        MONGO_URI = getattr(settings, "MONGO_URI", "mongodb://localhost:27017/")
        MONGO_DB = getattr(settings, "MONGO_DB", "annotations_db")
        MONGO_COLLECTION = getattr(settings, "MONGO_COLLECTION", "documents")
        
        _mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        db = _mongo_client[MONGO_DB]
        _mongo_collection = db[MONGO_COLLECTION]
        
        # Test de connexion
        _mongo_client.admin.command('ping')
        logger.info("Connexion MongoDB établie")
        
        return _mongo_collection
    except Exception as e:
        logger.error(f"Erreur connexion MongoDB: {e}")
        return None