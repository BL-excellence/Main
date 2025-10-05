# vector_store.py
from typing import List, Dict, Any
import faiss
import numpy as np
import uuid
import os
import logging
import pickle

logger = logging.getLogger(__name__)

class VectorStore:
    def __init__(self, dimension: int = 384, index_file: str = "faiss_index.index", metadata_file: str = "metadata_list.pkl", metadata_dict_file: str = "metadata_dict.pkl"):
        self.dimension = dimension
        self.index_file = index_file
        self.metadata_file = metadata_file
        self.metadata_dict_file = metadata_dict_file
        self.index = self._load_or_create_index()
        self.metadata = self._load_metadata()
        self.metadata_list = self._load_metadata_list()
        self._check_and_fix_inconsistency()

    def _load_or_create_index(self):
        if os.path.exists(self.index_file):
            logger.info(f"Chargement de l'index FAISS existant depuis {self.index_file}")
            return faiss.read_index(self.index_file)
        else:
            logger.info("Création d'un nouvel index FAISS")
            return faiss.IndexFlatL2(self.dimension)

    def _load_metadata(self):
        if os.path.exists(self.metadata_dict_file):
            with open(self.metadata_dict_file, 'rb') as f:
                metadata = pickle.load(f)
            logger.info(f"Metadata dict chargé: {len(metadata)} éléments")
            return metadata
        return {}

    def _load_metadata_list(self):
        if os.path.exists(self.metadata_file):
            with open(self.metadata_file, 'rb') as f:
                metadata_list = pickle.load(f)
            logger.info(f"Metadata list chargée: {len(metadata_list)} éléments")
            return metadata_list
        return []

    def _check_and_fix_inconsistency(self):
        ntotal = self.index.ntotal
        if len(self.metadata_list) != ntotal:
            logger.error(f"Incohérence détectée: metadata_list ({len(self.metadata_list)}) != index.ntotal ({ntotal}). Recommandation: Supprimez {self.index_file}, {self.metadata_file}, {self.metadata_dict_file} et réindexez.")
            # Option: reset to empty if files corrupted
            # self.metadata_list = []
            # self.metadata = {}
            # faiss.write_index(self.index, '/dev/null')  # Not possible, but warn user

    def _save_index(self):
        faiss.write_index(self.index, self.index_file)
        with open(self.metadata_file, 'wb') as f:
            pickle.dump(self.metadata_list, f)
        with open(self.metadata_dict_file, 'wb') as f:
            pickle.dump(self.metadata, f)
        logger.info(f"Index FAISS et metadata sauvegardés")

    def upsert_chunks(self, chunks: List[Dict[str, Any]]):
        vectors = []
        local_chunk_ids = []
        for chunk in chunks:
            chunk_id = chunk.get("chunk_id", str(uuid.uuid4()))
            vector = np.ascontiguousarray(np.array(chunk["embedding"], dtype=np.float32).reshape(1, -1))
            faiss.normalize_L2(vector)
            vectors.append(vector)
            self.metadata[chunk_id] = {
                "document_id": chunk["document_id"],
                "chunk_id": chunk_id,
                "content": chunk["content"],
                "type": chunk["type"],
                "metadata": chunk.get("metadata", {})
            }
            local_chunk_ids.append(chunk_id)
        
        if vectors:
            vectors_np = np.vstack(vectors)
            self.index.add(vectors_np)
            self.metadata_list.extend(local_chunk_ids)
            self._save_index()
            logger.info(f"Chunks indexés: {len(chunks)} - Total vecteurs: {self.index.ntotal}, metadata_list: {len(self.metadata_list)}")

    def search(self, query_vector: List[float], limit: int = 10, document_id: str = None, chunk_type: str = None) -> List[Dict[str, Any]]:
        if self.index.ntotal == 0 or len(self.metadata_list) == 0:
            logger.warning("Index ou metadata vide, pas de recherche possible")
            return []
        
        query_np = np.ascontiguousarray(np.array(query_vector, dtype=np.float32).reshape(1, -1))
        faiss.normalize_L2(query_np)
        search_limit = min(limit * 2, self.index.ntotal)
        distances, indices = self.index.search(query_np, search_limit)
        
        logger.info(f"Raw FAISS distances: {distances[0][:5]}...")
        logger.info(f"Raw FAISS indices: {indices[0][:5]}...")
        logger.info(f"Metadata list length: {len(self.metadata_list)}")
        
        results = []
        for i, (dist, idx) in enumerate(zip(distances[0], indices[0])):
            if idx == -1 or idx >= len(self.metadata_list):
                logger.warning(f"Invalid idx {idx} at position {i} (list len: {len(self.metadata_list)})")
                continue
            chunk_id = self.metadata_list[idx]
            payload = self.metadata.get(chunk_id)
            if payload:
                score = float(1 - dist / 2)
                logger.info(f"Chunk {chunk_id}: dist={dist:.4f}, score={score:.4f}, content preview: {payload['content'][:50]}...")
                if document_id and payload["document_id"] != document_id:
                    continue
                if chunk_type and payload["type"] != chunk_type:
                    continue
                results.append({
                    "score": score,
                    "payload": payload
                })
            if len(results) >= limit:
                break
        
        logger.info(f"Recherche: {len(results)} chunks trouvés sur {self.index.ntotal} vecteurs")
        return results

    def delete_document(self, document_id: str):
        if len(self.metadata_list) != self.index.ntotal:
            logger.error("Incohérence metadata/index, suppression ignorée")
            return
        keep_mask = np.array([self.metadata.get(self.metadata_list[i], {}).get("document_id", "") != document_id for i in range(self.index.ntotal)])
        keep_vectors = self.index.reconstruct_n(0, self.index.ntotal)[keep_mask]
        self.index = faiss.IndexFlatL2(self.dimension)
        if len(keep_vectors) > 0:
            self.index.add(keep_vectors)
        self.metadata_list = [self.metadata_list[i] for i in range(len(self.metadata_list)) if keep_mask[i]]
        self.metadata = {k: v for k, v in self.metadata.items() if v["document_id"] != document_id}
        self._save_index()

vector_store = VectorStore()