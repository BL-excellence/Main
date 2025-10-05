import json
import logging
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .services.retriever import retriever
from .services.llm_service import llm_service
from .services.document_indexer import document_indexer
from .utils.mongo import get_mongo_collection
from datetime import datetime


logger = logging.getLogger(__name__)

@csrf_exempt
def chatbot_rag_api(request):
      """API principale du chatbot RAG"""
      if request.method != 'POST':
          return JsonResponse({'error': 'Méthode non autorisée'}, status=405)
      
      try:
          data = json.loads(request.body)
      except json.JSONDecodeError:
          return JsonResponse({'error': 'JSON invalide'}, status=400)
      
      question = (data.get('message') or '').strip()
      document_id = data.get('document_id')  # Optionnel: filtrer par document
      
      if not question:
          return JsonResponse({'error': 'Question vide'}, status=400)
      
      try:
          logger.info(f"Requête reçue: question='{question}', document_id={document_id}")
          # 1. Récupérer les chunks pertinents
          retrieved_chunks = retriever.retrieve(
              question=question,
              document_id=document_id,
              top_k=5
          )
          
          if not retrieved_chunks:
              return JsonResponse({
                  'ok': True,
                  'answer': "Je n'ai pas trouvé d'informations pertinentes pour répondre à cette question dans les documents disponibles.",
                  'sources': [],
                  'metadata': {'chunks_found': 0}
              })
          
          # 2. Générer la réponse avec le LLM
          result = llm_service.generate_answer(
              question=question,
              retrieved_chunks=retrieved_chunks
          )
          
          return JsonResponse({
              'ok': True,
              'answer': result['answer'],
              'sources': result['sources'],
              'metadata': result['metadata']
          })
          
      except Exception as e:
          logger.exception(f"Erreur dans chatbot_rag_api: {e}")
          return JsonResponse({
              'ok': False,
              'error': f"Erreur interne: {str(e)}"
          }, status=500)


@csrf_exempt
def index_document_api(request):
      """API pour indexer un document enrichi"""
      if request.method != 'POST':
          return JsonResponse({'error': 'Méthode non autorisée'}, status=405)
      
      try:
          data = json.loads(request.body)
          document_id = data.get('document_id')
          
          if not document_id:
              return JsonResponse({'error': 'document_id requis'}, status=400)
          
          # Récupérer le document depuis MongoDB
          mongo_coll = get_mongo_collection()
          if mongo_coll is None:
              return JsonResponse({'error': 'MongoDB indisponible'}, status=503)
          
          expert_json = mongo_coll.find_one({"document.id": str(document_id)}) # Ajusté ici si nécessaire
          
          if not expert_json:
              return JsonResponse({'error': 'Document non trouvé'}, status=404)
          
          # Indexer le document
          success = document_indexer.index_enriched_document(expert_json)
          
          if success:
              return JsonResponse({
                  'ok': True,
                  'message': f'Document {document_id} indexé avec succès'
              })
          else:
            return JsonResponse({
                'ok': False,
                'error': 'Erreur lors de l\'indexation'
            }, status=500)
              
      except Exception as e:
          logger.exception(f"Erreur dans index_document_api: {e}")
          return JsonResponse({
              'ok': False,
              'error': f"Erreur interne: {str(e)}"
          }, status=500)



@csrf_exempt
def health_check_api(request):
    """Vérifier l'état du système RAG"""
    if request.method != 'GET':
        return JsonResponse({'error': 'Méthode non autorisée'}, status=405)
    
    try:
        from .services.vector_store import vector_store
        from .utils.mongo import get_mongo_collection
        
        # Vérifier FAISS
        faiss_status = {
            'total_vectors': vector_store.index.ntotal,
            'dimension': vector_store.dimension,
            'healthy': vector_store.index.ntotal > 0
        }
        
        # Vérifier MongoDB
        mongo_coll = get_mongo_collection()
        mongo_status = {
            'connected': mongo_coll is not None,
            'total_documents': mongo_coll.count_documents({}) if mongo_coll else 0
        }
        
        # État global
        is_healthy = faiss_status['healthy'] and mongo_status['connected']
        
        return JsonResponse({
            'status': 'healthy' if is_healthy else 'unhealthy',
            'faiss': faiss_status,
            'mongodb': mongo_status,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.exception(f"Erreur health check: {e}")
        return JsonResponse({
            'status': 'unhealthy',
            'error': str(e)
        }, status=500)      