from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json
 
@csrf_exempt
def chatbot_api(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        question = data.get('message', '')
        # Récupérer les données locales
        from client.products.models import Product
        from client.library.models import Document
        from submissions.models import Submission
        produits = Product.objects.all()
        docs = Document.objects.all()
        subs = Submission.objects.all()
 
        # Construire le contexte pour le LLM
        produits_str = ''
        for p in produits:
            def clean(val):
                return val if val and val != 'N/A' else 'non spécifié'
            sites = p.sites.all()
            if sites:
                sites_str = ', '.join([f"{s.site_name} ({s.city}, {s.country})" for s in sites])
            else:
                sites_str = 'Aucun'
            produits_str += (
                f"- Nom: {clean(p.name)}\n"
                f"  Statut: {clean(p.get_status_display())}\n"
                f"  Principe actif: {clean(getattr(p, 'active_ingredient', None))}\n"
                f"  Dosage: {clean(getattr(p, 'dosage', None))}\n"
                f"  Forme: {clean(getattr(p, 'form', None))}\n"
                f"  Zone thérapeutique: {clean(getattr(p, 'therapeutic_area', None))}\n"
                f"  Sites: {sites_str}\n"
            )
        docs_str = '\n'.join([f"- {d.title}" for d in docs])
        subs_str = '\n'.join([f"- {s.name} ({s.get_status_display()})" for s in subs if hasattr(s, 'get_status_display')])
 
        contexte = f"Voici les données de l'application:\nProduits:\n{produits_str}\nDocuments:\n{docs_str}\nSoumissions:\n{subs_str}\n"
        prompt = contexte + f"\nQuestion utilisateur : {question}\nRéponds uniquement avec les données ci-dessus. Si la question concerne un produit, affiche la réponse sous forme de tableau Markdown avec les colonnes : Nom, Statut, Principe actif, Dosage, Forme, Zone thérapeutique, Sites."
 
        # 🔁 Appel API Mistral
        import requests
        mistral_url = "https://api.mistral.ai/v1/chat/completions"
        headers = {
            "Authorization": "Bearer j2wOKpM86nlZhhlvkXXG7rFd4bhM4PN5",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "mistral-small",  # Ou "mistral-medium" ou "mistral-large"
            "messages": [
                {"role": "system", "content": "Tu es un assistant expert et tu réponds uniquement selon les données fournies."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.4
        }
        try:
            mistral_response = requests.post(mistral_url, headers=headers, json=payload, timeout=60)
            if mistral_response.status_code == 200:
                data_llm = mistral_response.json()
                # La réponse est dans data_llm['choices'][0]['message']['content']
                response = data_llm.get('choices', [{}])[0].get('message', {}).get('content', "Je n'ai pas compris votre question.")
            else:
                response = f"Erreur Mistral API : {mistral_response.status_code} - {mistral_response.text}"
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            response = f"Erreur LLM : {str(e)}\nTraceback:\n{tb}"
        return JsonResponse({'response': response})
    return JsonResponse({'response': 'Méthode non autorisée.'}, status=405)