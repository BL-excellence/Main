from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json
import re
 
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
        def clean(val):
            return val if val and val != 'N/A' else 'non spécifié'
           
        produits_str = ''
        for p in produits:
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
 
        # Préparation du contexte généraliste pour le LLM
        q_lower = question.strip().lower()
        contexte = f"Voici les données de l'application :\nProduits :\n{produits_str}\nDocuments :\n{docs_str}\nSoumissions :\n{subs_str}\n"
        prompt_instruction = (
            "\nQuestion utilisateur : {question}\n"
            "Tu es un assistant intelligent et convivial capable de :\n"
            "1. Répondre aux salutations de manière naturelle (bonjour, salut, merci, au revoir, etc.)\n"
            "2. Consulter et analyser les données ci-dessus\n"
            "3. Effectuer des modifications sur les données (voir les fonctionnalités disponibles ci-dessous)\n\n"
            "Réponds précisément à la question en utilisant uniquement les données ci-dessus. "
            "Si la question porte sur une colonne ou une information spécifique, "
            "réponds uniquement sur cet aspect, sans afficher tout le tableau. "
            "Si l'utilisateur demande une modification, guide-le vers la syntaxe correcte. "
            "Si la question n'est pas claire, demande plus de précisions. "
            "Ne réponds jamais avec des informations extérieures.\n\n"
            "Fonctionnalités de modification disponibles :\n"
            "- Modification du pays d'un site : 'mettre à jour le pays du site [nom] par [nouveau_pays]'\n"
            "- Modification de la ville d'un site : 'mettre à jour la ville du site [nom] par [nouvelle_ville]'\n"
            "- Autres modifications : demande des détails spécifiques"
        )
        prompt = contexte + prompt_instruction.format(question=question)
 
        # Fonctionnalités d'agent : modification des données (généralisé)
        # Détection des commandes de mise à jour
        update_keywords = ["mettre à jour", "modifier", "changer", "remplacer", "update", "peux mettre", "peux modifier", "peux changer", "tu peux"]
       
        if any(k in q_lower for k in update_keywords):
            # Détection générale des modifications de sites
            if "site" in q_lower:
                import re
               
                # Extraire le nom du site, le champ à modifier et la nouvelle valeur
                site_match = re.search(r'site\s+([^,\s]+)', q_lower)
                pays_match = re.search(r'pays\s+(?:du\s+site\s+)?([^,\s]+)\s+par\s+([^,\s]+)', q_lower)
                ville_match = re.search(r'ville\s+(?:du\s+site\s+)?([^,\s]+)\s+par\s+([^,\s]+)', q_lower)
               
                # Patterns alternatifs plus flexibles
                if not pays_match:
                    pays_match = re.search(r'(?:avec|par)\s+(?:le\s+pays\s+)?([a-zA-Z\s]+)', q_lower)
                if not ville_match:
                    ville_match = re.search(r'(?:avec|par)\s+(?:la\s+ville\s+)?([a-zA-Z\s]+)', q_lower)
               
                site_name = None
                field_to_update = None
                new_value = None
               
                # Déterminer le site et le champ à modifier
                if site_match:
                    site_name = site_match.group(1).strip()
               
                # Détecter le type de modification
                if "pays" in q_lower and pays_match:
                    field_to_update = "country"
                    new_value = pays_match.group(1).strip().title() if pays_match.groups() else pays_match.group(0).strip().title()
                elif "ville" in q_lower and ville_match:
                    field_to_update = "city"
                    new_value = ville_match.group(1).strip().title() if ville_match.groups() else ville_match.group(0).strip().title()
               
                # Si on a identifié tous les éléments nécessaires
                if site_name and field_to_update and new_value:
                    from client.products.models import ManufacturingSite, Product
                    try:
                        # Rechercher le site par nom (recherche flexible)
                        sites_matches = ManufacturingSite.objects.filter(site_name__icontains=site_name)
                       
                        if sites_matches.exists():
                            site_to_update = sites_matches.first()
                            old_value = getattr(site_to_update, field_to_update)
                           
                            # Mettre à jour le champ
                            setattr(site_to_update, field_to_update, new_value)
                            site_to_update.save()
                           
                            field_name = "Pays" if field_to_update == "country" else "Ville"
                            response = f"✅ Mise à jour effectuée !\n\nSite : {site_to_update.site_name}\n{field_name} - Ancien : {old_value or 'Non défini'}\n{field_name} - Nouveau : {new_value}\n\nLa modification a été sauvegardée dans la base de données."
                            return JsonResponse({'response': response})
                        else:
                            # Proposer de créer un site si il n'existe pas
                            response = f"❌ Aucun site trouvé avec le nom '{site_name}'.\n\n💡 Voulez-vous créer un nouveau site ?\nUtilisez : 'créer le site {site_name} avec {field_to_update.replace('country', 'pays').replace('city', 'ville')} {new_value}'"
                            return JsonResponse({'response': response})
                   
                    except Exception as e:
                        response = f"❌ Erreur lors de la mise à jour : {str(e)}"
                        return JsonResponse({'response': response})
                else:
                    response = "❌ Informations manquantes pour la mise à jour.\n\n🔧 Formats acceptés :\n- 'mettre à jour le pays du site [nom] par [nouveau_pays]'\n- 'modifier la ville du site [nom] par [nouvelle_ville]'\n- 'changer le site [nom] avec le pays [nouveau_pays]'"
                    return JsonResponse({'response': response})
           
            # Création de nouveaux sites
            elif "créer" in q_lower and "site" in q_lower:
                import re
                create_match = re.search(r'créer\s+(?:le\s+)?site\s+([^,\s]+)', q_lower)
                if create_match:
                    new_site_name = create_match.group(1).strip()
                    # Logique de création sera ajoutée ici
                    response = f"🚧 Fonctionnalité de création de site en développement.\nSite à créer : {new_site_name}"
                    return JsonResponse({'response': response})
           
            # Autres types de mises à jour
            else:
                response = "🔧 Fonctionnalités de mise à jour disponibles :\n- Mise à jour du pays : 'mettre à jour le pays du site [nom] par [pays]'\n- Mise à jour de la ville : 'modifier la ville du site [nom] par [ville]'\n- Création de site : 'créer le site [nom] avec [détails]'\n\nD'autres fonctionnalités seront ajoutées prochainement."
                return JsonResponse({'response': response})
 
        # Appel API Mistral systématique pour toutes les questions
        import requests
        mistral_url = "https://api.mistral.ai/v1/chat/completions"
        headers = {
            "Authorization": "Bearer j2wOKpM86nlZhhlvkXXG7rFd4bhM4PN5",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "mistral-small",
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