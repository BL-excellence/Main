import os
from typing import List, Dict, Any
from groq import Groq
from chatbot.prompts import SYSTEM_PROMPT, build_context
from dotenv import load_dotenv

# Charger les variables d'environnement
load_dotenv()

class LLMService:
    """Service d'interaction avec le LLM Grok"""
    
    def __init__(self, model: str = "llama-3.3-70b-versatile"):
        self.model = model
        self.client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    
    def generate_answer(
        self,
        question: str,
        retrieved_chunks: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Génère une réponse basée sur les chunks récupérés"""
        
        # 1. Construire le contexte
        context = build_context(retrieved_chunks)
        
        # 2. Appeler le LLM
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"""CONTEXTE:
{context}

QUESTION: {question}

Réponds de manière professionnelle et précise, en citant tes sources."""}
        ]
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.1,
                max_tokens=2000
            )
            answer = response.choices[0].message.content
        except Exception as e:
            raise Exception(f"Erreur lors de l'appel à l'API Grok: {str(e)}")
        
        # 3. Formater la réponse avec les sources
        return {
            "answer": answer,
            "sources": [
                {
                    "document_id": chunk["document"]["id"],
                    "title": chunk["document"]["title"],
                    "score": chunk["score"],
                    "chunk_type": chunk["chunk"]["type"]
                }
                for chunk in retrieved_chunks
            ],
            "metadata": {
                "model": self.model,
                "chunks_used": len(retrieved_chunks)
            }
        }

llm_service = LLMService()