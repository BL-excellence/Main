import os
from typing import List
from sentence_transformers import SentenceTransformer
from functools import lru_cache
from dotenv import load_dotenv

# Charger les variables d'environnement (si besoin, mais pas nécessaire pour sentence-transformers)
load_dotenv()

class EmbeddingService:
    """Service de génération d'embeddings local avec sentence-transformers"""
    
    def __init__(self, model: str = "all-MiniLM-L6-v2"):
        self.model = SentenceTransformer(model)
        self.dimension = self.model.get_sentence_embedding_dimension()  # 384 pour all-MiniLM-L6-v2
    
    # embeddings.py (extrait modifié)
    def embed_text(self, text: str) -> List[float]:
        try:
            emb = self.model.encode(text, normalize_embeddings=True)
            return emb.tolist()
        except Exception as e:
            raise Exception(f"Erreur lors de la génération de l'embedding: {str(e)}")

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        try:
            embs = self.model.encode(texts, normalize_embeddings=True)
            return embs.tolist()
        except Exception as e:
            raise Exception(f"Erreur lors de la génération des embeddings en batch: {str(e)}")
        
embedding_service = EmbeddingService()