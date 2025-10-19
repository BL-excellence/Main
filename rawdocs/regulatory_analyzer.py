# rawdocs/regulatory_analyzer.py - NOUVEAU FICHIER
"""
Analyseur réglementaire intelligent avec GROQ pour extraire et résumer
les informations réglementaires importantes de chaque page
"""

import os
import json
import requests
import time
from datetime import datetime
from typing import List, Dict, Any, Optional


class RegulatoryAnalyzer:
    """
    Analyseur spécialisé dans l'extraction d'informations réglementaires
    avec résumés intelligents par page et global
    """

    def __init__(self):
        self.api_url = "https://api.groq.com/openai/v1/chat/completions"
        self.model = "llama-3.3-70b-versatile"
        self.api_key = os.getenv("GROQ_API_KEY")

        if not self.api_key:
            raise ValueError("GROQ_API_KEY environment variable not set")

        print("[INFO] Analyseur reglementaire GROQ initialise")

    def analyze_page_regulatory_content(self, page_text: str, page_num: int, document_context: str = "") -> Dict[
        str, Any]:
        """
        Analyse complète du contenu réglementaire d'une page
        """
        print(f"🔍 Analyse réglementaire de la page {page_num}...")

        prompt = self.create_regulatory_analysis_prompt(page_text, page_num, document_context)

        try:
            response = self.call_groq_api(prompt, max_tokens=2000)
            if response:
                analysis = self.parse_regulatory_response(response, page_num)
                return analysis
            else:
                return self.create_empty_analysis()

        except Exception as e:
            print(f"❌ Erreur analyse page {page_num}: {e}")
            return self.create_empty_analysis()

    def create_regulatory_analysis_prompt(self, text: str, page_num: int, document_context: str) -> str:
        """Crée le prompt spécialisé pour l'analyse réglementaire"""

        return f"""Tu es un expert en affaires réglementaires pharmaceutiques et médicales. 
Analyse cette page de document réglementaire et extrais UNIQUEMENT les informations critiques.

**CONTEXTE DU DOCUMENT:** {document_context}

**TEXTE DE LA PAGE {page_num}:**
```
{text[:4000]}
```

**MISSION:** Fournir une analyse réglementaire structurée et un résumé concis.

**RETOURNE UNIQUEMENT UN JSON avec cette structure exacte:**
{{
    "page_summary": "Résumé en 2-3 phrases du contenu principal de cette page",
    "regulatory_importance_score": 85,
    "regulatory_obligations": [
        {{
            "obligation": "Description complète de l'obligation",
            "authority": "Autorité concernée",
            "deadline": "Délai si mentionné",
            "severity": "high|medium|low"
        }}
    ],
    "critical_deadlines": [
        {{
            "deadline": "Description du délai",
            "timeframe": "30 jours|6 mois|immediately|etc.",
            "trigger_event": "Événement déclencheur",
            "importance": "critical|high|medium"
        }}
    ],
    "authorities_mentioned": [
        {{
            "name": "EMA|FDA|ANSM|CHMP|etc.",
            "role": "Rôle dans le processus",
            "context": "Contexte de mention"
        }}
    ],
    "regulatory_procedures": [
        {{
            "procedure": "Type de procédure",
            "code": "IA|IB|II|etc.",
            "description": "Description de la procédure"
        }}
    ],
    "key_regulatory_points": [
        "Point clé 1: Description concise",
        "Point clé 2: Description concise",
        "Point clé 3: Description concise"
    ],
    "documents_required": [
        {{
            "document": "Nom du document requis",
            "when": "Quand le fournir",
            "to_whom": "À qui le fournir"
        }}
    ]
}}

**RÈGLES D'ANALYSE:**

1. **SCORE D'IMPORTANCE (0-100):**
   - 90-100: Page contenant des obligations critiques, deadlines fermes, procédures majeures
   - 70-89: Informations importantes mais non critiques
   - 50-69: Informations utiles, contexte réglementaire
   - 30-49: Contenu général, peu d'impact réglementaire
   - 0-29: Pas de contenu réglementaire significatif

2. **OBLIGATIONS:** Identifier UNIQUEMENT les obligations claires et actionnables, pas les descriptions générales

3. **DÉLAIS:** Extraire seulement les délais concrets avec timeframes spécifiques

4. **AUTORITÉS:** Mentionner seulement si elles ont un rôle actif dans le processus

5. **RÉSUMÉ:** Maximum 3 phrases, focus sur l'essentiel réglementaire

6. **POINTS CLÉS:** Maximum 5 points, formulés comme des actions ou des faits importants

**ATTENTION:** Si la page ne contient pas d'information réglementaire significative, 
retourne un score faible (0-30) et des listes vides, mais toujours un résumé du contenu.

Retourne UNIQUEMENT le JSON, aucun autre texte."""

    def call_groq_api(self, prompt: str, max_tokens: int = 2000) -> Optional[str]:
        """Appel à l'API GROQ avec gestion d'erreurs"""

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "Tu es un expert en affaires réglementaires. Réponds UNIQUEMENT en JSON valide."
                },
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.2,  # Basse pour la consistance
            "max_tokens": max_tokens,
            "top_p": 0.9
        }

        try:
            response = requests.post(
                self.api_url,
                headers=headers,
                json=payload,
                timeout=120
            )

            if response.status_code == 200:
                result = response.json()
                return result['choices'][0]['message']['content']
            elif response.status_code == 429:
                print("⚠️ Rate limit, attente...")
                time.sleep(60)
                return self.call_groq_api(prompt, max_tokens)
            else:
                print(f"❌ Erreur API GROQ {response.status_code}")
                return None

        except Exception as e:
            print(f"❌ Erreur requête: {e}")
            return None

    def parse_regulatory_response(self, response: str, page_num: int) -> Dict[str, Any]:
        """Parse la réponse JSON de GROQ"""

        try:
            # Nettoyer la réponse pour extraire le JSON
            response = response.strip()

            # Chercher le JSON dans la réponse
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                json_str = json_match.group()
                analysis = json.loads(json_str)

                # Validation et nettoyage
                return self.validate_and_clean_analysis(analysis)
            else:
                print(f"❌ Pas de JSON trouvé dans la réponse page {page_num}")
                return self.create_empty_analysis()

        except json.JSONDecodeError as e:
            print(f"❌ Erreur parsing JSON page {page_num}: {e}")
            return self.create_empty_analysis()
        except Exception as e:
            print(f"❌ Erreur traitement réponse page {page_num}: {e}")
            return self.create_empty_analysis()

    def validate_and_clean_analysis(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Valide et nettoie l'analyse reçue"""

        # Structure par défaut
        clean_analysis = {
            "page_summary": "",
            "regulatory_importance_score": 0,
            "regulatory_obligations": [],
            "critical_deadlines": [],
            "authorities_mentioned": [],
            "regulatory_procedures": [],
            "key_regulatory_points": [],
            "documents_required": []
        }

        # Nettoyer et valider chaque champ
        if isinstance(analysis.get('page_summary'), str):
            clean_analysis['page_summary'] = analysis['page_summary'][:500]  # Limiter

        if isinstance(analysis.get('regulatory_importance_score'), (int, float)):
            score = int(analysis['regulatory_importance_score'])
            clean_analysis['regulatory_importance_score'] = max(0, min(100, score))

        # Nettoyer les listes
        for list_field in ['regulatory_obligations', 'critical_deadlines', 'authorities_mentioned',
                           'regulatory_procedures', 'documents_required']:
            if isinstance(analysis.get(list_field), list):
                clean_analysis[list_field] = analysis[list_field][:10]  # Max 10 items

        if isinstance(analysis.get('key_regulatory_points'), list):
            clean_analysis['key_regulatory_points'] = [
                str(point)[:200] for point in analysis['key_regulatory_points'][:5]
            ]

        return clean_analysis

    def create_empty_analysis(self) -> Dict[str, Any]:
        """Crée une analyse vide par défaut"""
        return {
            "page_summary": "Contenu non analysable ou sans importance réglementaire",
            "regulatory_importance_score": 0,
            "regulatory_obligations": [],
            "critical_deadlines": [],
            "authorities_mentioned": [],
            "regulatory_procedures": [],
            "key_regulatory_points": [],
            "documents_required": []
        }

    def generate_document_global_summary(self, document, pages_analyses: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Génère un résumé global du document basé sur toutes les analyses de pages
        """
        print(f"📊 Génération du résumé global pour {len(pages_analyses)} pages...")

        # Consolidation des données
        all_obligations = []
        all_deadlines = []
        all_authorities = []
        all_procedures = []
        total_score = 0
        pages_with_content = 0

        for analysis in pages_analyses:
            if analysis.get('regulatory_importance_score', 0) > 30:
                pages_with_content += 1

            total_score += analysis.get('regulatory_importance_score', 0)
            all_obligations.extend(analysis.get('regulatory_obligations', []))
            all_deadlines.extend(analysis.get('critical_deadlines', []))
            all_authorities.extend(analysis.get('authorities_mentioned', []))
            all_procedures.extend(analysis.get('regulatory_procedures', []))

        # Créer le prompt pour le résumé global
        summary_prompt = self.create_global_summary_prompt(document, pages_analyses, {
            'total_pages': len(pages_analyses),
            'pages_with_content': pages_with_content,
            'avg_score': total_score / len(pages_analyses) if pages_analyses else 0
        })

        try:
            response = self.call_groq_api(summary_prompt, max_tokens=1500)
            if response:
                return self.parse_global_summary_response(response)
            else:
                return self.create_default_global_summary(document, pages_analyses)

        except Exception as e:
            print(f"❌ Erreur résumé global: {e}")
            return self.create_default_global_summary(document, pages_analyses)

    def create_global_summary_prompt(self, document, pages_analyses: List[Dict], stats: Dict) -> str:
        """Crée le prompt pour le résumé global du document"""

        # Extraire les résumés de pages importantes
        important_pages = [
            f"Page {i + 1}: {analysis.get('page_summary', '')}"
            for i, analysis in enumerate(pages_analyses)
            if analysis.get('regulatory_importance_score', 0) > 50
        ]

        return f"""Tu es un expert en affaires réglementaires. Analyse ce document complet et fournis un résumé global.

**INFORMATIONS DU DOCUMENT:**
- Titre: {getattr(document, 'title', 'Non défini')}
- Type: {getattr(document, 'doc_type', 'Non défini')}
- Source: {getattr(document, 'source', 'Non définie')}
- Pages totales: {stats['total_pages']}
- Pages avec contenu réglementaire: {stats['pages_with_content']}
- Score moyen d'importance: {stats['avg_score']:.1f}/100

**RÉSUMÉS DES PAGES IMPORTANTES:**
{chr(10).join(important_pages[:10])}

**RETOURNE UNIQUEMENT UN JSON:**
{{
    "global_summary": "Résumé complet du document en 4-6 phrases décrivant son objectif, contenu principal et implications réglementaires",
    "document_type_analysis": "Analyse du type de document et de son rôle dans le processus réglementaire",
    "main_regulatory_themes": [
        "Thème 1: Description",
        "Thème 2: Description", 
        "Thème 3: Description"
    ],
    "critical_compliance_requirements": [
        "Exigence critique 1",
        "Exigence critique 2",
        "Exigence critique 3"
    ],
    "key_deadlines_summary": [
        "Délai important 1",
        "Délai important 2"
    ],
    "regulatory_authorities_involved": [
        "Autorité 1: Rôle",
        "Autorité 2: Rôle"
    ],
    "impact_assessment": {{
        "compliance_complexity": "low|medium|high|critical",
        "business_impact": "low|medium|high|critical", 
        "timeline_criticality": "low|medium|high|critical"
    }},
    "recommended_actions": [
        "Action recommandée 1",
        "Action recommandée 2",
        "Action recommandée 3"
    ],
    "global_regulatory_score": 75
}}

**RÈGLES:**
- Résumé global: maximum 6 phrases, couvrir l'essentiel
- Thèmes: maximum 5, les plus importants
- Actions: maximum 5, concrètes et actionnables
- Score global: 0-100 basé sur l'importance réglementaire globale du document

Retourne UNIQUEMENT le JSON."""

    def parse_global_summary_response(self, response: str) -> Dict[str, Any]:
        """Parse la réponse du résumé global"""
        try:
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            return {}
        except:
            return {}

    def create_default_global_summary(self, document, pages_analyses: List[Dict]) -> Dict[str, Any]:
        """Crée un résumé global par défaut"""
        pages_with_content = sum(1 for a in pages_analyses if a.get('regulatory_importance_score', 0) > 30)
        avg_score = sum(a.get('regulatory_importance_score', 0) for a in pages_analyses) / len(
            pages_analyses) if pages_analyses else 0

        return {
            "global_summary": f"Document de {len(pages_analyses)} pages avec {pages_with_content} pages contenant du contenu réglementaire significatif.",
            "document_type_analysis": f"Document de type {getattr(document, 'doc_type', 'non défini')}",
            "main_regulatory_themes": [],
            "critical_compliance_requirements": [],
            "key_deadlines_summary": [],
            "regulatory_authorities_involved": [],
            "impact_assessment": {
                "compliance_complexity": "medium",
                "business_impact": "medium",
                "timeline_criticality": "medium"
            },
            "recommended_actions": [],
            "global_regulatory_score": int(avg_score)
        }