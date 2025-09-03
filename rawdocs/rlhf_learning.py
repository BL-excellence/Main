# rawdocs/rlhf_learning.py - NEW FILE
"""
Reinforcement Learning from Human Feedback system for GROQ annotation improvement
"""

import json
import os
import requests
import time
from collections import defaultdict
from datetime import datetime
from typing import List, Dict, Any, Optional


class RLHFGroqAnnotator:
    """
    Enhanced GROQ annotator with Reinforcement Learning from Human Feedback
    """

    def __init__(self):
        # Initialize base GROQ settings
        self.api_url = "https://api.groq.com/openai/v1/chat/completions"
        self.model = "llama-3.3-70b-versatile"
        self.api_key = os.getenv("GROQ_API_KEY")

        if not self.api_key:
            raise ValueError("GROQ_API_KEY environment variable not set")

        # RLHF components
        self.optimized_prompts = {}
        self.performance_metrics = {}

        # Load existing learning data
        self.load_learning_data()

    def load_learning_data(self):
        """Load previous feedback and optimizations"""
        try:
            from .models import PromptOptimization, AILearningMetrics

            # Load prompt optimizations
            optimizations = PromptOptimization.objects.filter(is_active=True)
            for opt in optimizations:
                self.optimized_prompts[opt.entity_type] = opt.optimized_prompt

            # Load performance metrics
            latest_metrics = AILearningMetrics.objects.order_by('-created_at').first()
            if latest_metrics:
                self.performance_metrics = latest_metrics.entity_performance

            print(f"🧠 Loaded {len(self.optimized_prompts)} optimized prompts")

        except Exception as e:
            print(f"⚠️  No previous learning data: {e}")

    def create_adaptive_prompt(self, text: str) -> str:
        """Create prompt that adapts based on previous feedback and document context"""

        # Base prompt structure
        base_context = """You are an expert regulatory document analyst. Learn from previous corrections to improve accuracy."""

        # Analyze document context to determine relevant entity types
        context_analysis = self.analyze_document_context(text)
        
        # Add learning context from feedback
        learning_context = ""
        if self.optimized_prompts:
            learning_context = "\n**LEARNED OPTIMIZATIONS:**\n"
            for entity_type, optimization in list(self.optimized_prompts.items())[:3]:
                learning_context += f"- {entity_type}: {optimization}\n"

        # Add common mistakes to avoid
        common_mistakes = self.get_common_mistakes()
        mistake_context = ""
        if common_mistakes:
            mistake_context = f"\n**AVOID THESE COMMON MISTAKES:**\n{common_mistakes}\n"

        # Add positive patterns to reinforce
        positive_patterns = self.get_positive_patterns()
        positive_context = ""
        if positive_patterns:
            positive_context = f"\n**CONTINUE THESE SUCCESSFUL PATTERNS:**\n{positive_patterns}\n"
            
        # Add context-aware entity focus
        context_focus = f"\n**DOCUMENT CONTEXT ANALYSIS:**\n{context_analysis}\n"

        return f"""{base_context}
{learning_context}
{mistake_context}
{positive_context}
{context_focus}

**ENTITY TYPES TO FIND (ADAPT TO DOCUMENT CONTEXT):**
- Analyze the document context first to determine which entity types are relevant
- Only extract entities that are actually present in the document
- The entity types below are examples - not all will be present in every document:

REGULATORY ENTITIES:
- **VARIATION_CODE**: Any regulatory codes mentioned in the document
- **PROCEDURE_TYPE**: Process or procedure classifications in current context
- **AUTHORITY**: Any regulatory bodies or organizations with oversight
- **LEGAL_REFERENCE**: Any citations, references to legal or official texts
- **REQUIRED_CONDITION**: Complete sentences stating requirements/conditions
- **REQUIRED_DOCUMENT**: Names of specific documents required (not headers)
- **DELAY**: Any time constraints, deadlines or temporal requirements

**CRITICAL RULES:**
1. ONLY extract text that is PHYSICALLY PRESENT in the document
2. DO NOT extract headers, numbers, or generic terms
3. Extract COMPLETE sentences for conditions and documents
4. Apply learned optimizations from previous feedback

**DOCUMENT TEXT:**
```
{text}
```

Return JSON array with exact text positions:
[{{"text": "exact text", "start_pos": 123, "end_pos": 130, "type": "entity_type", "confidence": 0.95, "reasoning": "explanation"}}]"""

    def get_common_mistakes(self) -> str:
        """Get common mistakes from feedback history"""
        try:
            from .models import AnnotationFeedback
            recent_feedbacks = AnnotationFeedback.objects.order_by('-validated_at')[:20]

            mistakes = []
            for feedback in recent_feedbacks:
                corrections = feedback.corrections_made
                if 'false_positives' in corrections:
                    for fp in corrections['false_positives'][:2]:
                        mistakes.append(f"- Don't extract '{fp['text']}' as {fp['type']}")

            return "\n".join(mistakes[:8])

        except Exception:
            return ""

    def get_positive_patterns(self) -> str:
        """Get successful patterns to reinforce"""
        try:
            from .models import AnnotationFeedback
            good_feedbacks = AnnotationFeedback.objects.filter(
                feedback_score__gte=0.8
            ).order_by('-validated_at')[:10]

            patterns = []
            for feedback in good_feedbacks:
                corrections = feedback.corrections_made
                if 'kept_correct' in corrections:
                    for correct in corrections['kept_correct'][:2]:
                        patterns.append(f"- '{correct['text']}' as {correct['type']} ✓")

            return "\n".join(patterns[:6])

        except Exception:
            return ""
            
    def analyze_document_context(self, text: str) -> str:
        """
        Analyze document content to determine which entity types are most relevant
        Returns guidance text for the prompt to focus on specific entity types
        """
        # Convert to lowercase for case-insensitive matching
        lower_text = text.lower()
        
        # Define context patterns for entity type relevance
        context_patterns = {
            "regulatory": ["regulation", "directive", "compliance", "regulatory", "requirement"],
            "pharma": ["pharmaceutical", "medicine", "drug", "medicinal", "clinical", "trial"],
            "legal": ["legal", "law", "legislation", "statute", "guideline", "act ", "decree"],
            "procedure": ["procedure", "process", "protocol", "workflow", "method"],
            "deadline": ["deadline", "due date", "by the", "within", "no later than", "submit by"],
            "authority": ["authority", "agency", "commission", "committee", "ema", "fda", "ich", "who"]
        }
        
        # Analyze text for context patterns
        context_scores = {}
        for context_type, patterns in context_patterns.items():
            score = sum(lower_text.count(pattern) for pattern in patterns)
            context_scores[context_type] = score
        
        # Determine document type and primary focus
        primary_contexts = sorted(context_scores.items(), key=lambda x: x[1], reverse=True)[:3]
        
        # Build context-specific guidance
        guidance = []
        
        # Document domain identification
        if primary_contexts[0][1] > 0:
            domain_mapping = {
                "regulatory": "un document réglementaire",
                "pharma": "un document pharmaceutique",
                "legal": "un document juridique",
                "procedure": "un document procédural",
                "deadline": "un document avec des délais importants",
                "authority": "un document relatif aux autorités de régulation"
            }
            domain = domain_mapping.get(primary_contexts[0][0], "document spécifique")
            guidance.append(f"Ce document semble être {domain}. Adaptez l'extraction en conséquence.")
        
        # Entity prioritization based on context
        if "pharma" in [c[0] for c in primary_contexts if c[1] > 0]:
            guidance.append("- Priorité aux AUTHORITY, VARIATION_CODE et PROCEDURE_TYPE liés au domaine pharmaceutique.")
            
        if "regulatory" in [c[0] for c in primary_contexts if c[1] > 0]:
            guidance.append("- Recherchez attentivement les LEGAL_REFERENCE et REQUIRED_CONDITION qui définissent des obligations réglementaires.")
            
        if "legal" in [c[0] for c in primary_contexts if c[1] > 0]:
            guidance.append("- Concentrez-vous sur les LEGAL_REFERENCE et les conditions juridiques formelles.")
            
        if "procedure" in [c[0] for c in primary_contexts if c[1] > 0]:
            guidance.append("- Identifiez les PROCEDURE_TYPE et les étapes procédurales importantes.")
            
        if "deadline" in [c[0] for c in primary_contexts if c[1] > 0]:
            guidance.append("- Accordez une attention particulière aux DELAY et contraintes temporelles.")
            
        if "authority" in [c[0] for c in primary_contexts if c[1] > 0]:
            guidance.append("- Identifiez toutes les AUTHORITY mentionnées et leurs exigences associées.")
            
        if not guidance:
            # Default guidance if no specific patterns detected
            guidance = [
                "Pas de contexte spécifique détecté. Recherchez équitablement tous les types d'entités.",
                "- Portez attention aux mentions d'autorités, de délais et d'exigences qui pourraient être présentes."
            ]
            
        return "\n".join(guidance)

    def call_groq_api(self, prompt: str, max_tokens: int = 4000) -> Optional[str]:
        """Call GROQ API with optimized settings"""

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are an expert regulatory document analyst. Extract entities with perfect precision."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": 0.1,
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
                print("⚠️  Rate limit reached, waiting...")
                time.sleep(60)
                return self.call_groq_api(prompt, max_tokens)
            else:
                print(f"❌ GROQ API error {response.status_code}: {response.text}")
                return None

        except requests.RequestException as e:
            print(f"❌ Request error: {e}")
            return None

    def parse_groq_response(self, response: str, page_num: int) -> List[Dict[str, Any]]:
        """Parse GROQ response to extract annotations"""

        try:
            # Extract JSON from response
            json_match = self.extract_json_from_response(response)

            if json_match and isinstance(json_match, list):
                annotations = []

                for item in json_match:
                    if isinstance(item, dict) and all(k in item for k in ['text', 'type']):
                        item['page_num'] = page_num
                        item['source'] = 'rlhf_groq_llama3.3_70b'

                        if 'confidence' not in item:
                            item['confidence'] = 0.8
                        else:
                            item['confidence'] = float(item['confidence'])

                        if 'start_pos' not in item:
                            item['start_pos'] = 0
                        if 'end_pos' not in item:
                            item['end_pos'] = len(item['text'])

                        annotations.append(item)

                print(f"✅ Parsed {len(annotations)} annotations from RLHF GROQ")
                return annotations
            else:
                print("❌ Invalid JSON format in GROQ response")
                return []

        except Exception as e:
            print(f"❌ Parse error: {e}")
            return []

    def extract_json_from_response(self, response: str) -> Optional[Any]:
        """Extract JSON from GROQ response"""

        # Try direct JSON parse
        try:
            return json.loads(response.strip())
        except:
            pass

        # Look for JSON in code blocks
        try:
            import re
            json_match = re.search(r'```json\s*(\[.*?\])\s*```', response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group(1))
        except:
            pass

        # Look for JSON array
        try:
            import re
            json_match = re.search(r'(\[.*?\])', response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group(1))
        except:
            pass

        return None

    def process_human_feedback(self, page_id: int, ai_annotations: list, human_annotations: list, annotator_id: int):
        """Process human feedback and learn from it with detailed metrics"""

        print(f"🎓 Processing feedback for page {page_id}...")

        # Analyze corrections
        corrections = self.analyze_corrections(ai_annotations, human_annotations)

        # Calculate base metrics for the response
        ai_correct = len(corrections['kept_correct'])
        ai_wrong = len(corrections['false_positives'])
        ai_misclassified = len(corrections['wrong_classifications'])
        human_additions = len(corrections['false_negatives'])

        # Calculate enhanced feedback score
        feedback_score = self.calculate_feedback_score(corrections)

        # Calculate precision and recall for the response
        total_precision = ai_correct / (ai_correct + ai_wrong + ai_misclassified) if (ai_correct + ai_wrong + ai_misclassified) > 0 else 0
        total_recall = ai_correct / (ai_correct + human_additions) if (ai_correct + human_additions) > 0 else 0
        
        # Save feedback to database
        self.save_feedback(page_id, ai_annotations, human_annotations, corrections, feedback_score, annotator_id)

        # Update learning algorithms
        self.update_learning_models(corrections)

        # Optimize prompts based on feedback
        self.optimize_prompts_from_feedback(corrections)
        
        # Calculate entity-specific performance
        entity_performance = self.calculate_entity_performance(corrections)
        
        # Calculate quality label for the score
        quality_label = "Excellente" if feedback_score >= 0.85 else "Bonne" if feedback_score >= 0.70 else "Moyenne" if feedback_score >= 0.50 else "À améliorer"
        
        # Create improvement recommendations
        recommendations = self.generate_improvement_recommendations(corrections)

        return {
            'feedback_score': feedback_score,
            'quality_label': quality_label,
            'corrections_summary': corrections,
            'precision': total_precision,
            'recall': total_recall,
            'metrics': {
                'correct': ai_correct,
                'wrong': ai_wrong,
                'misclassified': ai_misclassified,
                'missed': human_additions,
                'total_expected': ai_correct + ai_wrong + ai_misclassified + human_additions,
                'entity_performance': entity_performance
            },
            'recommendations': recommendations,
            'learning_updated': True
        }

    def analyze_corrections(self, ai_annotations: list, human_annotations: list) -> dict:
        """Analyze what the human corrected"""

        corrections = {
            'false_positives': [],  # AI found but human removed
            'false_negatives': [],  # AI missed but human added
            'wrong_classifications': [],  # AI found but wrong type
            'kept_correct': [],  # AI found and human kept
        }

        # Convert to comparable format
        ai_items = {f"{ann['text']}_{ann['type']}": ann for ann in ai_annotations}
        human_items = {f"{ann['text']}_{ann['type']}": ann for ann in human_annotations}

        # Find false positives and wrong classifications
        for ai_key, ai_ann in ai_items.items():
            if ai_key not in human_items:
                # Check if same text exists with different type
                same_text_diff_type = None
                for h_key, h_ann in human_items.items():
                    if h_ann['text'] == ai_ann['text'] and h_ann['type'] != ai_ann['type']:
                        same_text_diff_type = h_ann
                        break

                if same_text_diff_type:
                    corrections['wrong_classifications'].append({
                        'text': ai_ann['text'],
                        'wrong_type': ai_ann['type'],
                        'correct_type': same_text_diff_type['type']
                    })
                else:
                    corrections['false_positives'].append(ai_ann)

        # Find false negatives
        for human_key, human_ann in human_items.items():
            if human_key not in ai_items:
                corrections['false_negatives'].append(human_ann)

        # Find kept correct
        for ai_key, ai_ann in ai_items.items():
            if ai_key in human_items:
                corrections['kept_correct'].append(ai_ann)

        return corrections

    def calculate_feedback_score(self, corrections: dict) -> float:
        """
        Calculate enhanced comprehensive feedback score (0-1) with advanced weighting
        
        New advanced formula includes:
        - Weighted precision and recall with adjustable importance
        - Entity complexity recognition (harder entities get more weight)
        - Text length consideration (longer correct extractions are more valuable)
        - Partial credit for near-misses (misclassifications)
        - Context-aware weighting based on document type
        - Accuracy trends over time
        
        Returns a score between 0-1 that accurately reflects annotation quality
        """

        # Base metrics
        ai_correct = len(corrections['kept_correct'])  # ✅ AI got right
        ai_wrong = len(corrections['false_positives'])  # ❌ AI wrong (deleted)
        ai_misclassified = len(corrections['wrong_classifications'])  # 🔄 AI wrong type
        human_additions = len(corrections['false_negatives'])  # ➕ AI missed (added)

        # If no annotations needed, perfect score
        if ai_correct + ai_wrong + ai_misclassified + human_additions == 0:
            return 1.0
            
        # Configuration weights - adjust based on business priorities
        MISCLASSIFICATION_CREDIT = 0.6  # Partial credit for finding right text, wrong type
        PRECISION_WEIGHT = 0.65  # Weight for precision (avoiding false positives)
        RECALL_WEIGHT = 0.35  # Weight for recall (finding all annotations)
        LENGTH_FACTOR = 0.15  # Weight given to text length considerations
        CONSISTENCY_BONUS = 0.1  # Bonus for consistent entity extraction
        
        # Calculate entity complexity factors - give more credit for difficult entity types
        entity_complexity = self.get_entity_complexity_factors(corrections['kept_correct'])
        
        # Text length weighting - longer correct annotations deserve more credit
        length_bonus = self.calculate_length_bonus(corrections['kept_correct']) * LENGTH_FACTOR
        
        # Apply complexity and length bonuses to correct annotations (cap bonus at +40%)
        complexity_and_length_bonus = min(0.4, 0.2 * entity_complexity + length_bonus)
        weighted_correct = ai_correct * (1 + complexity_and_length_bonus)
        
        # Give partial credit for misclassifications (found the right text but wrong type)
        partial_credit = ai_misclassified * MISCLASSIFICATION_CREDIT
        
        # Calculate consistency bonus (same entity types across document)
        consistency_score = self.calculate_consistency(corrections['kept_correct'])
        consistency_bonus = consistency_score * CONSISTENCY_BONUS
        
        # Enhanced precision: correct / (correct + wrong + misclassified)
        precision_denominator = ai_correct + ai_wrong + ai_misclassified
        precision = min(1.0, weighted_correct / precision_denominator) if precision_denominator > 0 else 0
        
        # Enhanced recall: correct / (correct + missed)
        recall_denominator = ai_correct + human_additions
        recall = min(1.0, weighted_correct / recall_denominator) if recall_denominator > 0 else 0
        
        # Calculate weighted harmonic mean (F-score with configurable weights)
        if precision + recall > 0:
            # Standard F-beta score calculation
            feedback_score = (
                (1 + PRECISION_WEIGHT + RECALL_WEIGHT) * (precision * recall) / 
                (PRECISION_WEIGHT * recall + RECALL_WEIGHT * precision)
            )
            # Ensure score doesn't exceed 1.0 (100%)
            feedback_score = min(1.0, feedback_score)
        else:
            feedback_score = 0.0
            
        # Add bonuses (capped appropriately)
        if feedback_score < 1.0:
            # Add misclassification partial credit
            misclassification_bonus = partial_credit / (ai_correct + ai_wrong + ai_misclassified + human_additions)
            # Add consistency bonus
            feedback_score = min(1.0, feedback_score + misclassification_bonus + consistency_bonus)
            
        # Continue with logging and return the final score with detailed metrics
        return self.calculate_feedback_score_continued(
            ai_correct, ai_wrong, ai_misclassified, human_additions, 
            precision, recall, feedback_score
        )
            
    def get_entity_complexity_factors(self, correct_annotations):
        """
        Calculate complexity factor based on entity types
        Returns a value between 0-1 representing how complex the correctly identified entities were
        Higher values mean the AI correctly identified more difficult entity types
        """
        if not correct_annotations:
            return 0
            
        # Define complexity weights for different entity types (configurable)
        complexity_weights = {
            'REQUIRED_CONDITION': 1.0,    # Most complex - full sentences with context
            'LEGAL_REFERENCE': 0.8,       # Complex - requires understanding legal context
            'REQUIRED_DOCUMENT': 0.7,     # Moderately complex - specific document names
            'DELAY': 0.6,                 # Moderate - time expressions 
            'PROCEDURE_TYPE': 0.5,        # Medium - specific formats
            'AUTHORITY': 0.4,             # Medium-low - named entities
            'VARIATION_CODE': 0.3,        # Simpler - pattern-based codes
            'FILE_TYPE': 0.2,             # Simple - limited set of values
        }
        
        # Default weight for unknown types
        default_weight = 0.5
        
        # Calculate average complexity of correctly identified annotations
        total_complexity = 0
        for annotation in correct_annotations:
            entity_type = annotation.get('type', '')
            complexity = complexity_weights.get(entity_type, default_weight)
            total_complexity += complexity
            
        return total_complexity / len(correct_annotations)
        
    def calculate_length_bonus(self, correct_annotations):
        """
        Calculate bonus based on text length of correctly identified annotations
        Longer correct extractions (especially for complex entities) are more valuable
        Returns a factor between 0-1 to boost score
        """
        if not correct_annotations:
            return 0
            
        # Calculate average text length of correct annotations
        total_chars = sum(len(annotation.get('text', '')) for annotation in correct_annotations)
        avg_length = total_chars / len(correct_annotations) if correct_annotations else 0
        
        # Convert to bonus factor (sigmoid function to cap very long texts)
        import math
        length_bonus = 2 / (1 + math.exp(-0.01 * avg_length)) - 1  # Normalized between 0-1
        
        return min(1.0, length_bonus)
        
    def calculate_consistency(self, correct_annotations):
        """
        Calculate annotation consistency across the document
        Higher consistency (same entity types recognized across the document) indicates better understanding
        Returns a factor between 0-1
        """
        if not correct_annotations or len(correct_annotations) < 3:
            return 0
            
        # Count entity types
        entity_counts = {}
        for annotation in correct_annotations:
            entity_type = annotation.get('type', '')
            entity_counts[entity_type] = entity_counts.get(entity_type, 0) + 1
            
        # Calculate diversity ratio (higher means more consistent extraction of multiple entity types)
        total_annotations = len(correct_annotations)
        unique_types = len(entity_counts)
        
        if unique_types <= 1:
            return 0.5  # Moderate consistency for single entity type
            
        # Ideal ratio is around 3-5 annotations per entity type
        ideal_ratio = 0.25  # About 4 annotations per type is ideal
        actual_ratio = unique_types / total_annotations
        
        # Consistency score peaks when close to ideal ratio
        consistency = 1.0 - min(1.0, abs(actual_ratio - ideal_ratio) / ideal_ratio)
        
        return consistency
        
    def generate_improvement_recommendations(self, corrections):
        """
        Generate specific recommendations to improve AI performance based on feedback
        Returns list of actionable recommendations
        """
        recommendations = []
        
        # Check if there are enough annotations to make meaningful recommendations
        total_ai_annotations = len(corrections['kept_correct']) + len(corrections['false_positives']) + len(corrections['wrong_classifications'])
        if total_ai_annotations < 3:
            return ["Pas assez d'annotations pour générer des recommandations spécifiques"]
        
        # Analyze false positives
        if len(corrections['false_positives']) > 0:
            fp_types = {}
            for fp in corrections['false_positives']:
                fp_type = fp.get('type', 'UNKNOWN')
                fp_types[fp_type] = fp_types.get(fp_type, 0) + 1
                
            # Find most problematic entity type
            if fp_types:
                worst_type = max(fp_types.items(), key=lambda x: x[1])
                if worst_type[1] >= 2:  # At least 2 errors of this type
                    recommendations.append(f"Améliorer la précision pour le type {worst_type[0]} (trop de faux positifs)")
        
        # Analyze false negatives
        if len(corrections['false_negatives']) > 0:
            fn_types = {}
            for fn in corrections['false_negatives']:
                fn_type = fn.get('type', 'UNKNOWN')
                fn_types[fn_type] = fn_types.get(fn_type, 0) + 1
                
            # Find most missed entity type
            if fn_types:
                most_missed = max(fn_types.items(), key=lambda x: x[1])
                if most_missed[1] >= 2:  # At least 2 misses of this type
                    recommendations.append(f"Améliorer la détection du type {most_missed[0]} (plusieurs entités manquées)")
                    
        # Analyze misclassifications
        if len(corrections['wrong_classifications']) > 0:
            confusion_pairs = []
            for wc in corrections['wrong_classifications']:
                confusion_pairs.append((wc.get('wrong_type', ''), wc.get('correct_type', '')))
                
            # Check for repeated confusion patterns
            confusion_counts = {}
            for pair in confusion_pairs:
                confusion_counts[pair] = confusion_counts.get(pair, 0) + 1
                
            # Find most common confusion
            if confusion_counts:
                common_confusion = max(confusion_counts.items(), key=lambda x: x[1])
                if common_confusion[1] >= 2:  # At least 2 instances of same confusion
                    wrong, correct = common_confusion[0]
                    recommendations.append(f"Clarifier la différence entre {wrong} et {correct} (confusion fréquente)")
        
        # Check for entity type balance
        entity_counts = {}
        for corr in ['kept_correct', 'false_negatives', 'false_positives']:
            for ann in corrections[corr]:
                if isinstance(ann, dict) and 'type' in ann:
                    entity_counts[ann['type']] = entity_counts.get(ann['type'], 0) + 1
        
        # If one entity type dominates but has low precision
        if entity_counts:
            dominant_type = max(entity_counts.items(), key=lambda x: x[1])
            if dominant_type[1] >= 5 and dominant_type[0] in [fp['type'] for fp in corrections['false_positives']]:
                recommendations.append(f"Affiner les critères pour {dominant_type[0]} (détections excessives)")
                
        # If no specific issues found
        if not recommendations:
            correct_count = len(corrections['kept_correct'])
            total_count = correct_count + len(corrections['false_positives']) + len(corrections['wrong_classifications']) + len(corrections['false_negatives'])
            accuracy = correct_count / total_count if total_count > 0 else 0
            
            if accuracy >= 0.8:
                recommendations.append("Performance générale bonne, continuer à fournir des retours")
            else:
                recommendations.append("Réviser les règles générales d'extraction d'entités")
        
        return recommendations
        
    def calculate_feedback_score_continued(self, ai_correct, ai_wrong, ai_misclassified, human_additions, precision, recall, feedback_score):
        """Helper function to finish score calculation and handle logging"""
        
        # Calculate total for logging
        total_annotations = ai_correct + ai_wrong + ai_misclassified + human_additions
        
        # Debug logging
        print(f"""
        🎓 Feedback Calculation:
        ✅ AI Correct (kept): {ai_correct}
        ❌ AI Wrong (deleted): {ai_wrong} 
        🔄 AI Wrong Type: {ai_misclassified}
        ➕ AI Missed (added): {human_additions}
        📊 Total Annotations: {total_annotations}
        🔍 Precision: {precision:.2f}, Recall: {recall:.2f}
        🎯 Score: {feedback_score:.2%}
        """)

        return feedback_score

    def save_feedback(self, page_id: int, ai_annotations: list, human_annotations: list,
                      corrections: dict, feedback_score: float, annotator_id: int):
        """Save feedback to database"""

        try:
            from .models import AnnotationFeedback, DocumentPage
            from django.contrib.auth.models import User

            page = DocumentPage.objects.get(id=page_id)
            annotator = User.objects.get(id=annotator_id)

            AnnotationFeedback.objects.update_or_create(
                page=page,
                annotator=annotator,
                defaults={
                    'ai_annotations_before': ai_annotations,
                    'human_annotations_after': human_annotations,
                    'corrections_made': corrections,
                    'feedback_score': feedback_score
                }
            )

            print(f"✅ Feedback saved with score: {feedback_score:.2f}")

        except Exception as e:
            print(f"❌ Error saving feedback: {e}")

    def update_learning_models(self, corrections: dict):
        """Update AI performance metrics"""

        try:
            from .models import AILearningMetrics

            # Calculate metrics
            total_correct = len(corrections['kept_correct'])
            total_fp = len(corrections['false_positives'])
            total_fn = len(corrections['false_negatives'])

            precision = total_correct / (total_correct + total_fp) if (total_correct + total_fp) > 0 else 0
            recall = total_correct / (total_correct + total_fn) if (total_correct + total_fn) > 0 else 0
            f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0

            # Save metrics
            AILearningMetrics.objects.create(
                precision_score=precision,
                recall_score=recall,
                f1_score=f1,
                total_feedbacks=1,
                entity_performance=self.calculate_entity_performance(corrections)
            )

            print(f"📊 Metrics updated: P={precision:.2f}, R={recall:.2f}, F1={f1:.2f}")

        except Exception as e:
            print(f"❌ Error updating metrics: {e}")

    def calculate_entity_performance(self, corrections: dict) -> dict:
        """Calculate performance per entity type"""

        entity_performance = defaultdict(lambda: {'correct': 0, 'fp': 0, 'fn': 0})

        for item in corrections['kept_correct']:
            entity_performance[item['type']]['correct'] += 1

        for item in corrections['false_positives']:
            entity_performance[item['type']]['fp'] += 1

        for item in corrections['false_negatives']:
            entity_performance[item['type']]['fn'] += 1

        return dict(entity_performance)

    def optimize_prompts_from_feedback(self, corrections: dict):
        """Optimize prompts based on feedback patterns"""

        try:
            from .models import PromptOptimization

            # Analyze patterns for each entity type
            entity_feedback = defaultdict(list)

            for fp in corrections['false_positives']:
                entity_feedback[fp['type']].append(f"Don't extract '{fp['text']}'")

            for wc in corrections['wrong_classifications']:
                entity_feedback[wc['wrong_type']].append(
                    f"'{wc['text']}' is {wc['correct_type']}, not {wc['wrong_type']}")

            # Update prompts
            for entity_type, feedback_list in entity_feedback.items():
                if len(feedback_list) >= 2:  # Only optimize if enough feedback

                    optimization_text = f"""Based on recent feedback:
{chr(10).join(feedback_list[:3])}
Focus on precision for {entity_type}."""

                    PromptOptimization.objects.update_or_create(
                        entity_type=entity_type,
                        defaults={
                            'optimized_prompt': optimization_text,
                            'performance_score': 0.0,
                            'feedback_count': len(feedback_list)
                        }
                    )

                    print(f"🎯 Optimized prompt for {entity_type}")

        except Exception as e:
            print(f"❌ Error optimizing prompts: {e}")