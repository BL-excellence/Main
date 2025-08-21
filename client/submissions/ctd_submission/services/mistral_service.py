# ctd_submission/services/mistral_service.py
# Service avancé d'intégration avec Mistral AI pour des analyses plus poussées

import asyncio
import aiohttp
import json
import logging
from typing import Dict, List, Optional, Union
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from datetime import timedelta

logger = logging.getLogger(__name__)


class MistralAIService:
    """
    Service avancé d'intégration avec Mistral AI
    Gère la communication asynchrone, le cache et les fallbacks
    """

    def __init__(self):
        self.api_key = getattr(settings, 'MISTRAL_API_KEY', None)
        self.base_url = getattr(settings, 'MISTRAL_BASE_URL', 'https://api.mistral.ai/v1')
        self.model = getattr(settings, 'MISTRAL_MODEL', 'mistral-large-latest')
        self.max_tokens = getattr(settings, 'MISTRAL_MAX_TOKENS', 4000)
        self.timeout = getattr(settings, 'MISTRAL_TIMEOUT', 30)
        self.cache_ttl = getattr(settings, 'MISTRAL_CACHE_TTL', 3600)  # 1 heure

        if not self.api_key:
            logger.warning("MISTRAL_API_KEY non configurée. Le service Mistral sera désactivé.")

    async def analyze_document_advanced(self, document_content: str,
                                        analysis_type: str = 'classification',
                                        context: Dict = None) -> Optional[Dict]:
        """
        Analyse avancée d'un document avec Mistral AI
        """
        if not self.api_key:
            return None

        # Vérifier le cache
        cache_key = self._get_cache_key(document_content, analysis_type, context)
        cached_result = cache.get(cache_key)
        if cached_result:
            logger.info(f"Résultat Mistral trouvé en cache pour {analysis_type}")
            return cached_result

        try:
            prompt = self._create_analysis_prompt(document_content, analysis_type, context)
            result = await self._call_mistral_async(prompt)

            if result:
                # Mettre en cache le résultat
                cache.set(cache_key, result, self.cache_ttl)
                logger.info(f"Analyse Mistral {analysis_type} réussie et mise en cache")
                return result

        except Exception as e:
            logger.error(f"Erreur lors de l'analyse Mistral {analysis_type}: {e}")

        return None

    async def batch_analyze_documents(self, documents: List[Dict],
                                      analysis_type: str = 'classification') -> List[Dict]:
        """
        Analyse en lot de plusieurs documents
        """
        if not self.api_key:
            return [None] * len(documents)

        tasks = []
        for doc in documents:
            task = self.analyze_document_advanced(
                doc['content'],
                analysis_type,
                doc.get('context', {})
            )
            tasks.append(task)

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Traiter les résultats et les exceptions
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Erreur pour le document {i}: {result}")
                processed_results.append(None)
            else:
                processed_results.append(result)

        return processed_results

    async def _call_mistral_async(self, prompt: str, retries: int = 3) -> Optional[Dict]:
        """
        Appel asynchrone à l'API Mistral avec gestion des erreurs
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "Tu es un expert en affaires réglementaires pharmaceutiques, spécialisé dans l'analyse de documents CTD."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "max_tokens": self.max_tokens,
            "temperature": 0.1,
            "response_format": {"type": "json_object"}
        }

        for attempt in range(retries):
            try:
                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=self.timeout)) as session:
                    async with session.post(
                            f"{self.base_url}/chat/completions",
                            headers=headers,
                            json=payload
                    ) as response:

                        if response.status == 200:
                            data = await response.json()
                            content = data['choices'][0]['message']['content']
                            return self._parse_json_response(content)

                        elif response.status == 429:  # Rate limit
                            wait_time = (2 ** attempt) * 1
                            logger.warning(f"Rate limit atteint, attente de {wait_time}s (tentative {attempt + 1})")
                            await asyncio.sleep(wait_time)
                            continue

                        else:
                            error_text = await response.text()
                            logger.error(f"Erreur API Mistral {response.status}: {error_text}")
                            break

            except asyncio.TimeoutError:
                logger.error(f"Timeout lors de l'appel Mistral (tentative {attempt + 1})")
                if attempt < retries - 1:
                    await asyncio.sleep(2 ** attempt)

            except Exception as e:
                logger.error(f"Erreur inattendue lors de l'appel Mistral: {e}")
                break

        return None

    def _create_analysis_prompt(self, content: str, analysis_type: str, context: Dict = None) -> str:
        """
        Crée un prompt optimisé selon le type d'analyse
        """
        if analysis_type == 'classification':
            return self._create_classification_prompt(content)
        elif analysis_type == 'quality_check':
            return self._create_quality_check_prompt(content, context)
        elif analysis_type == 'compliance_review':
            return self._create_compliance_prompt(content, context)
        elif analysis_type == 'content_suggestions':
            return self._create_suggestions_prompt(content, context)
        else:
            return self._create_generic_prompt(content, analysis_type, context)

    def _create_classification_prompt(self, content: str) -> str:
        """Prompt pour la classification CTD"""
        return f"""
Analyze this pharmaceutical regulatory document and classify it according to CTD (Common Technical Document) structure.

Document Content:
{content[:3000]}

Please provide a JSON response with the following structure:
{{
    "module_code": "M1|M2|M3|M4|M5",
    "section_code": "X.Y",
    "confidence": 0.0-1.0,
    "reasoning": "Brief explanation of your classification decision",
    "keywords_identified": ["keyword1", "keyword2", "keyword3"],
    "document_type": "cover_letter|summary|quality_document|nonclinical_report|clinical_report|other",
    "regulatory_region": "EU|US|CANADA|JAPAN|ICH|OTHER",
    "suggested_improvements": ["improvement1", "improvement2"]
}}

Focus on identifying regulatory keywords, document structure, and content patterns specific to pharmaceutical submissions.
"""

    def _create_quality_check_prompt(self, content: str, context: Dict = None) -> str:
        """Prompt pour la vérification qualité"""
        region = context.get('region', 'EU') if context else 'EU'

        return f"""
Perform a comprehensive quality check on this pharmaceutical regulatory document for {region} submission.

Document Content:
{content[:3000]}

Check for:
1. Regulatory compliance requirements
2. Required information completeness
3. Format and structure adherence
4. Language and terminology consistency
5. Data integrity and accuracy indicators

Provide a JSON response:
{{
    "overall_quality_score": 0.0-1.0,
    "compliance_issues": [
        {{
            "severity": "critical|major|minor",
            "category": "content|format|regulatory",
            "description": "Issue description",
            "suggested_fix": "How to fix this issue"
        }}
    ],
    "missing_elements": ["element1", "element2"],
    "strengths": ["strength1", "strength2"],
    "recommendations": ["recommendation1", "recommendation2"]
}}
"""

    def _create_compliance_prompt(self, content: str, context: Dict = None) -> str:
        """Prompt pour la revue de conformité réglementaire"""
        region = context.get('region', 'EU') if context else 'EU'
        submission_type = context.get('submission_type', 'MAA') if context else 'MAA'

        return f"""
Review this document for regulatory compliance with {region} requirements for {submission_type} submissions.

Document Content:
{content[:3000]}

Analyze compliance with:
- Regional regulatory guidelines ({region})
- ICH guidelines where applicable
- Current regulatory updates and changes
- Industry best practices

Provide a JSON response:
{{
    "compliance_status": "compliant|partially_compliant|non_compliant",
    "regulatory_requirements_met": ["req1", "req2"],
    "regulatory_gaps": [
        {{
            "requirement": "Specific requirement",
            "gap_description": "What's missing or incorrect",
            "regulatory_reference": "Guideline or regulation reference",
            "priority": "high|medium|low"
        }}
    ],
    "guideline_adherence": {{
        "ich_guidelines": 0.0-1.0,
        "regional_guidelines": 0.0-1.0,
        "format_compliance": 0.0-1.0
    }}
}}
"""

    def _create_suggestions_prompt(self, content: str, context: Dict = None) -> str:
        """Prompt pour suggestions d'amélioration du contenu"""
        return f"""
Analyze this pharmaceutical regulatory document and provide intelligent suggestions for improvement.

Document Content:
{content[:3000]}

Context: {json.dumps(context) if context else 'No additional context'}

Provide suggestions for:
1. Content enhancement
2. Clarity improvements
3. Regulatory strengthening
4. Structure optimization
5. Missing information identification

JSON response format:
{{
    "content_suggestions": [
        {{
            "type": "addition|modification|deletion|restructure",
            "section": "Where to apply",
            "current_text": "Existing text (if applicable)",
            "suggested_text": "Improved version",
            "rationale": "Why this improves the document",
            "impact": "high|medium|low"
        }}
    ],
    "structural_improvements": ["improvement1", "improvement2"],
    "terminology_enhancements": [
        {{
            "current_term": "existing term",
            "suggested_term": "better term",
            "context": "when to use"
        }}
    ],
    "regulatory_enhancements": ["enhancement1", "enhancement2"]
}}
"""

    def _create_generic_prompt(self, content: str, analysis_type: str, context: Dict = None) -> str:
        """Prompt générique pour types d'analyse personnalisés"""
        return f"""
Perform a {analysis_type} analysis on this pharmaceutical regulatory document.

Document Content:
{content[:3000]}

Context: {json.dumps(context) if context else 'No additional context'}

Please provide a detailed JSON analysis appropriate for the requested analysis type.
Include relevant insights, recommendations, and actionable items.
"""

    def _parse_json_response(self, response_text: str) -> Optional[Dict]:
        """Parse et valide la réponse JSON de Mistral"""
        try:
            # Nettoyer la réponse
            cleaned_text = response_text.strip()
            if cleaned_text.startswith('```json'):
                cleaned_text = cleaned_text[7:]
            if cleaned_text.endswith('```'):
                cleaned_text = cleaned_text[:-3]

            return json.loads(cleaned_text)

        except json.JSONDecodeError as e:
            logger.error(f"Erreur de parsing JSON Mistral: {e}")
            logger.debug(f"Réponse reçue: {response_text}")
            return None

    def _get_cache_key(self, content: str, analysis_type: str, context: Dict = None) -> str:
        """Génère une clé de cache unique pour la requête"""
        import hashlib

        content_hash = hashlib.md5(content.encode()).hexdigest()[:16]
        context_hash = hashlib.md5(json.dumps(context or {}, sort_keys=True).encode()).hexdigest()[:8]

        return f"mistral:{analysis_type}:{content_hash}:{context_hash}"

    def get_service_status(self) -> Dict:
        """Retourne le statut du service Mistral"""
        return {
            'available': bool(self.api_key),
            'model': self.model,
            'max_tokens': self.max_tokens,
            'cache_enabled': True,
            'cache_ttl': self.cache_ttl,
            'last_check': timezone.now().isoformat()
        }


class MistralEnhancedCopilot:
    """
    Version améliorée du Copilot utilisant Mistral AI pour des analyses plus poussées
    """

    def __init__(self):
        self.mistral_service = MistralAIService()
        self.fallback_analyzer = None  # Analyseur de fallback si Mistral indisponible

    async def enhanced_document_analysis(self, document: 'Document') -> Dict:
        """
        Analyse enrichie d'un document avec Mistral AI
        """
        content = self._extract_document_content(document)
        context = {
            'region': document.submission.region,
            'submission_type': document.submission.submission_type,
            'document_type': document.document_type,
            'section': document.section.name if document.section else None
        }

        # Analyses parallèles avec Mistral
        tasks = {
            'classification': self.mistral_service.analyze_document_advanced(
                content, 'classification', context
            ),
            'quality_check': self.mistral_service.analyze_document_advanced(
                content, 'quality_check', context
            ),
            'compliance_review': self.mistral_service.analyze_document_advanced(
                content, 'compliance_review', context
            )
        }

        results = {}
        try:
            # Exécuter toutes les analyses en parallèle
            analysis_results = await asyncio.gather(
                *tasks.values(),
                return_exceptions=True
            )

            # Mapper les résultats
            for i, (analysis_type, task) in enumerate(tasks.items()):
                result = analysis_results[i]
                if isinstance(result, Exception):
                    logger.error(f"Erreur analyse {analysis_type}: {result}")
                    results[analysis_type] = None
                else:
                    results[analysis_type] = result

        except Exception as e:
            logger.error(f"Erreur lors des analyses Mistral: {e}")
            results = {key: None for key in tasks.keys()}

        return self._consolidate_analysis_results(results, document)

    async def get_intelligent_suggestions(self, document: 'Document',
                                          change_context: Dict) -> List[Dict]:
        """
        Génère des suggestions intelligentes basées sur les modifications
        """
        content = self._extract_document_content(document)

        # Enrichir le contexte avec les informations du document
        enhanced_context = {
            **change_context,
            'document_metadata': {
                'name': document.name,
                'type': document.document_type,
                'section': document.section.name if document.section else None,
                'submission_region': document.submission.region,
                'submission_type': document.submission.submission_type
            }
        }

        # Demander des suggestions à Mistral
        suggestions_result = await self.mistral_service.analyze_document_advanced(
            content, 'content_suggestions', enhanced_context
        )

        if suggestions_result:
            return self._format_suggestions_for_ui(suggestions_result)

        # Fallback vers l'analyseur traditionnel
        return self._get_fallback_suggestions(document, change_context)

    def _extract_document_content(self, document: 'Document') -> str:
        """Extrait le contenu du document pour analyse"""
        if document.content_extracted:
            if isinstance(document.content_extracted, dict):
                return document.content_extracted.get('modified_content') or \
                    document.content_extracted.get('text', '')
            return str(document.content_extracted)
        return document.name

    def _consolidate_analysis_results(self, results: Dict, document: 'Document') -> Dict:
        """Consolide les résultats de différentes analyses"""
        consolidated = {
            'document_id': document.id,
            'analysis_timestamp': timezone.now().isoformat(),
            'mistral_available': self.mistral_service.api_key is not None,
            'analyses': results
        }

        # Extraire les informations les plus importantes
        if results.get('classification'):
            classification = results['classification']
            consolidated['suggested_classification'] = {
                'module': classification.get('module_code'),
                'section': classification.get('section_code'),
                'confidence': classification.get('confidence', 0)
            }

        if results.get('quality_check'):
            quality = results['quality_check']
            consolidated['quality_score'] = quality.get('overall_quality_score', 0)
            consolidated['critical_issues'] = [
                issue for issue in quality.get('compliance_issues', [])
                if issue.get('severity') == 'critical'
            ]

        if results.get('compliance_review'):
            compliance = results['compliance_review']
            consolidated['compliance_status'] = compliance.get('compliance_status')

        return consolidated

    def _format_suggestions_for_ui(self, mistral_suggestions: Dict) -> List[Dict]:
        """Formate les suggestions Mistral pour l'UI"""
        formatted_suggestions = []

        # Suggestions de contenu
        for suggestion in mistral_suggestions.get('content_suggestions', []):
            formatted_suggestions.append({
                'type': 'content_improvement',
                'title': f"Amélioration {suggestion.get('type', 'contenu')}",
                'message': suggestion.get('rationale', ''),
                'confidence': 0.8,  # Confiance élevée pour Mistral
                'action': 'apply_suggestion',
                'data': {
                    'section': suggestion.get('section'),
                    'current_text': suggestion.get('current_text'),
                    'suggested_text': suggestion.get('suggested_text'),
                    'impact': suggestion.get('impact', 'medium')
                }
            })

        # Améliorations structurelles
        for improvement in mistral_suggestions.get('structural_improvements', []):
            formatted_suggestions.append({
                'type': 'structural_improvement',
                'title': 'Amélioration structurelle',
                'message': improvement,
                'confidence': 0.7,
                'action': 'review_structure'
            })

        return formatted_suggestions

    def _get_fallback_suggestions(self, document: 'Document',
                                  change_context: Dict) -> List[Dict]:
        """Suggestions de fallback si Mistral n'est pas disponible"""
        return [
            {
                'type': 'fallback',
                'title': 'Service IA temporairement indisponible',
                'message': 'Les suggestions avancées ne sont pas disponibles actuellement. Utilisez les suggestions de base.',
                'confidence': 0.5,
                'action': 'use_basic_suggestions'
            }
        ]


# Configuration Django pour Mistral AI
class MistralSettings:
    """
    Classe de configuration pour les paramètres Mistral
    """

    @staticmethod
    def get_default_settings():
        """Retourne les paramètres par défaut pour Mistral"""
        return {
            'MISTRAL_API_KEY': None,
            'MISTRAL_BASE_URL': 'https://api.mistral.ai/v1',
            'MISTRAL_MODEL': 'mistral-large-latest',
            'MISTRAL_MAX_TOKENS': 4000,
            'MISTRAL_TIMEOUT': 30,
            'MISTRAL_CACHE_TTL': 3600,
            'MISTRAL_BATCH_SIZE': 5,
            'MISTRAL_RATE_LIMIT': 100,  # Requêtes par minute
            'MISTRAL_FALLBACK_ENABLED': True
        }

    @staticmethod
    def validate_settings():
        """Valide la configuration Mistral"""
        required_settings = ['MISTRAL_API_KEY']
        missing_settings = []

        for setting in required_settings:
            if not getattr(settings, setting, None):
                missing_settings.append(setting)

        if missing_settings:
            logger.warning(f"Paramètres Mistral manquants: {', '.join(missing_settings)}")
            return False

        return True


# Utilitaires pour l'intégration
def run_async_analysis(coro):
    """
    Utilitaire pour exécuter des analyses asynchrones dans un contexte synchrone
    """
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    return loop.run_until_complete(coro)


def get_mistral_service():
    """Factory pour obtenir une instance du service Mistral"""
    return MistralAIService()


def get_enhanced_copilot():
    """Factory pour obtenir un Copilot amélioré"""
    return MistralEnhancedCopilot()