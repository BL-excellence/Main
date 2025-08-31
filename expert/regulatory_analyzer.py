
import os
import json
import requests
from typing import Dict, List, Any
from datetime import datetime

class ExpertRegulatoryAnalyzer:
    """
    Expert Regulatory Analysis System - Self-contained version for expert module
    """
    
    def __init__(self):
        self.groq_api_key = os.getenv('GROQ_API_KEY')
        self.groq_api_url = "https://api.groq.com/openai/v1/chat/completions"
        
    def call_groq_api(self, prompt: str, max_tokens: int = 1000) -> str:
        """Call Groq API for regulatory analysis"""
        if not self.groq_api_key:
            print("Warning: GROQ_API_KEY not found")
            return ""
            
        headers = {
            'Authorization': f'Bearer {self.groq_api_key}',
            'Content-Type': 'application/json'
        }
        
        payload = {
            "model": "llama-3.3-70b-versatile",
            "messages": [
                {"role": "system", "content": "You are an expert regulatory analyst. Always return ONLY valid JSON with no extra text."},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": max_tokens,
            "temperature": 0.2,
            "response_format": {"type": "json_object"}
        }
        
        try:
            response = requests.post(self.groq_api_url, headers=headers, json=payload, timeout=60)
            if response.status_code == 200:
                return response.json()['choices'][0]['message']['content']
            # If 400, retry without response_format and simpler messages
            if response.status_code == 400:
                fallback_payload = {
                    "model": "llama-3.3-70b-versatile",
                    "messages": [
                        {"role": "user", "content": prompt}
                    ],
                    "max_tokens": max_tokens,
                    "temperature": 0.2
                }
                fallback_resp = requests.post(self.groq_api_url, headers=headers, json=fallback_payload, timeout=60)
                if fallback_resp.status_code == 200:
                    return fallback_resp.json()['choices'][0]['message']['content']
                else:
                    print(f"Groq API Error (fallback): {fallback_resp.status_code} {fallback_resp.text}")
                    return ""
            else:
                print(f"Groq API Error {response.status_code}: {response.text}")
                return ""
        except Exception as e:
            print(f"Groq API Error: {e}")
            return ""
    
    def analyze_page_regulatory_content(self, page_text: str, page_num: int, document_context: str) -> Dict[str, Any]:
        """Analyze regulatory content of a single page"""
        
        if not page_text or len(page_text.strip()) < 50:
            return self.create_empty_analysis()
        
        prompt = f"""Tu es un expert en affaires réglementaires pharmaceutiques. Analyse cette page de document.

**CONTEXTE DU DOCUMENT:** {document_context}
**PAGE:** {page_num}

**CONTENU:**
{page_text[:4000]}

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
        "Point clé 2: Description concise"
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
   - 90-100: Page contenant des obligations critiques, deadlines fermes
   - 70-89: Informations importantes mais non critiques
   - 50-69: Informations utiles, contexte réglementaire
   - 30-49: Contenu général, peu d'impact réglementaire
   - 0-29: Pas de contenu réglementaire significatif

2. **OBLIGATIONS:** Identifier UNIQUEMENT les obligations claires et actionnables
3. **DÉLAIS:** Extraire seulement les délais concrets avec timeframes spécifiques
4. **AUTORITÉS:** Mentionner seulement si elles ont un rôle actif
5. **RÉSUMÉ:** Maximum 3 phrases, focus sur l'essentiel réglementaire

Retourne UNIQUEMENT le JSON, aucun autre texte."""

        try:
            response = self.call_groq_api(prompt, max_tokens=1200)
            if response:
                return self.parse_analysis_response(response)
            else:
                return self.create_empty_analysis()
        except Exception as e:
            print(f"Error analyzing page {page_num}: {e}")
            return self.create_empty_analysis()

    def parse_analysis_response(self, response: str) -> Dict[str, Any]:
        """Parse and clean the analysis response"""
        try:
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                analysis = json.loads(json_match.group())
                return self.clean_analysis_data(analysis)
            return self.create_empty_analysis()
        except:
            return self.create_empty_analysis()

    def clean_analysis_data(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Clean and validate analysis data"""
        clean_analysis = {}
        
        # Ensure required fields exist
        clean_analysis['page_summary'] = str(analysis.get('page_summary', ''))[:500]
        clean_analysis['regulatory_importance_score'] = max(0, min(100, int(analysis.get('regulatory_importance_score', 0))))
        
        # Clean list fields
        for list_field in ['regulatory_obligations', 'critical_deadlines', 'authorities_mentioned',
                           'regulatory_procedures', 'documents_required']:
            if isinstance(analysis.get(list_field), list):
                clean_analysis[list_field] = analysis[list_field][:10]

        if isinstance(analysis.get('key_regulatory_points'), list):
            clean_analysis['key_regulatory_points'] = [
                str(point)[:200] for point in analysis['key_regulatory_points'][:5]
            ]

        return clean_analysis

    def create_empty_analysis(self) -> Dict[str, Any]:
        """Create empty analysis"""
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
        """Generate global document regulatory summary"""
        print(f"Generating global summary for {len(pages_analyses)} pages...")

        # Consolidate data
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

        # Create global summary prompt
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
            print(f"Error generating global summary: {e}")
            return self.create_default_global_summary(document, pages_analyses)

    def create_global_summary_prompt(self, document, pages_analyses: List[Dict], stats: Dict) -> str:
        """Create prompt for global summary"""
        
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

Retourne UNIQUEMENT le JSON."""

    def parse_global_summary_response(self, response: str) -> Dict[str, Any]:
        """Parse global summary response"""
        try:
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            return {}
        except:
            return {}

    def create_default_global_summary(self, document, pages_analyses: List[Dict]) -> Dict[str, Any]:
        """Create default global summary"""
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