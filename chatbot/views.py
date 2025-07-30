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
 
        # Filtrage dynamique du contexte selon la question
        q_lower = question.strip().lower()
        contexte = "Voici les données de l'application :\n"
        prompt_instruction = "\nQuestion utilisateur : {question}\nRéponds uniquement avec les données ci-dessus."
        if any(k in q_lower for k in ["produit", "products", "nom", "statut", "principe", "dosage", "forme", "thérapeutique", "sites"]):
            contexte += f"Produits :\n{produits_str}\n"
            prompt_instruction += " Si la question concerne un produit, affiche la réponse sous forme de tableau Markdown avec les colonnes : Nom, Statut, Principe actif, Dosage, Forme, Zone thérapeutique, Sites."
        elif any(k in q_lower for k in ["document", "doc", "titre", "type", "country", "pays"]):
            contexte += f"Documents :\n{docs_str}\n"
            prompt_instruction += " Si la question concerne un document, affiche la liste des documents correspondants."
        elif any(k in q_lower for k in ["soumission", "submission", "dossier", "statut de soumission"]):
            contexte += f"Soumissions :\n{subs_str}\n"
            prompt_instruction += " Si la question concerne une soumission, affiche la liste des soumissions correspondantes."
        else:
            # Par défaut, tout envoyer (comportement précédent)
            contexte += f"Produits :\n{produits_str}\nDocuments :\n{docs_str}\nSoumissions :\n{subs_str}\n"
            prompt_instruction += " Si la question concerne un produit, affiche la réponse sous forme de tableau Markdown avec les colonnes : Nom, Statut, Principe actif, Dosage, Forme, Zone thérapeutique, Sites."
        prompt = contexte + prompt_instruction.format(question=question)
 
        # Réponse humaine pour les questions générales (salutation, politesse, etc.)
        general_keywords = [
            "hi", "hello", "salut", "bonjour", "hey", "merci", "thanks", "au revoir", "bye", "coucou", "bonsoir", "good morning", "good evening", "ça va", "how are you", "thank you"
        ]
        q_lower = question.strip().lower()
        if any(k in q_lower for k in general_keywords):
            if any(k in q_lower for k in ["merci", "thanks", "thank you"]):
                response = "Avec plaisir ! N'hésitez pas si vous avez d'autres questions."
            elif any(k in q_lower for k in ["au revoir", "bye"]):
                response = "Au revoir ! Passez une bonne journée."
            elif any(k in q_lower for k in ["ça va", "how are you"]):
                response = "Je vais bien, merci ! Comment puis-je vous aider ?"
            else:
                response = "Bonjour ! Comment puis-je vous aider ?"
            return JsonResponse({'response': response})
 
        # Réponse directe pour les questions de comptage (nombre de produits, documents, soumissions)
        if ("nombre" in q_lower or "combien" in q_lower) and "produit" in q_lower:
            response = f"Il y a {produits.count()} produits dans la base."
            return JsonResponse({'response': response})
        if ("nombre" in q_lower or "combien" in q_lower) and ("document" in q_lower or "doc" in q_lower):
            response = f"Il y a {docs.count()} documents dans la base."
            return JsonResponse({'response': response})
        if ("nombre" in q_lower or "combien" in q_lower or "dossier" in q_lower) and ("soumission" in q_lower or "submission" in q_lower):
            response = f"Il y a {subs.count()} soumissions dans la base."
            return JsonResponse({'response': response})
 
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
                response = data_llm.get('choices', [{}])[0].get('message', {}).get('content', None)
                if not response or response.strip().lower() in ["je n'ai pas compris votre question.", "je ne sais pas.", "je ne peux pas répondre à cette question."]:
                    response = "Je n'ai pas bien compris votre question. Pouvez-vous préciser ou donner plus d'informations ?"
            else:
                response = f"Erreur Mistral API : {mistral_response.status_code} - {mistral_response.text}"
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            response = f"Erreur LLM : {str(e)}\nTraceback:\n{tb}"
        return JsonResponse({'response': response})
    return JsonResponse({'response': 'Méthode non autorisée.'}, status=405)