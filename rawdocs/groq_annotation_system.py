# rawdocs/groq_annotation_system.py
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.contrib import messages
from datetime import datetime
from .models import DocumentPage, Annotation, AnnotationType

import requests
import json
import time
from typing import List, Dict, Any, Optional
import re
import os


class GroqAnnotator:
    """
    FREE GROQ API + Llama 3.1 70B implementation for regulatory document annotation
    ZERO COST - Claude-level professional results!
    """

    def __init__(self):
        # GROQ settings - FREE 6000 requests/day
        self.api_url = "https://api.groq.com/openai/v1/chat/completions"
        self.model = "llama-3.3-70b-versatile"  # BEST FREE model!
        self.api_key = os.getenv("GROQ_API_KEY")

        if not self.api_key:
            raise ValueError("GROQ_API_KEY environment variable not set. Get free key from https://console.groq.com/")

        print("🚀 Using GROQ FREE API (Llama 3.3 70B - BEST!)")
        self.test_connection()

    def test_connection(self) -> bool:
        """Test GROQ API connection"""
        try:
            test_response = self.call_groq_api("Test connection", max_tokens=10)
            if test_response:
                print("✅ GROQ API connected successfully!")
                return True
            else:
                print("❌ GROQ API connection failed")
                return False
        except Exception as e:
            print(f"❌ GROQ connection error: {e}")
            return False


    def generate_random_color(self) -> str:
        """Generate a random color for new annotation types"""
        import random
        colors = [
            '#ff6b6b', '#4ecdc4', '#45b7d1', '#96ceb4', '#feca57', 
            '#ff9ff3', '#54a0ff', '#ff7675', '#fdcb6e', '#6c5ce7',
            '#a29bfe', '#fd79a8', '#00b894', '#00cec9', '#e84393',
            '#2d3436', '#636e72', '#b2bec3', '#ddd', '#74b9ff'
        ]
        return random.choice(colors)

    def annotate_page_with_groq(self, page_data: Dict[str, Any]) -> tuple:

        text = page_data['text']

        page_num = page_data['page_num']

        if len(text.strip()) < 50:

            return [], []

        print(f"🧠 Processing page {page_num} with GROQ ")

        # Step 1: Let AI analyze the document and suggest annotation types

        analysis_prompt = f"""Analyze this document text and suggest annotation types that would be most useful for this specific content.

    Document text: {text[:2000]}

    Based on the content, suggest 5-10 annotation types that would capture the key information in this document.

    Return JSON: {{"suggested_types": ["type1", "type2", "type3"]}}

    Focus on what's actually in the text, not generic categories."""

        analysis_response = self.call_groq_api(analysis_prompt, max_tokens=300)

        suggested_types = []

        

        if analysis_response:

            try:

                analysis_data = self.extract_json_from_response(analysis_response)

                suggested_types = analysis_data.get('suggested_types', []) if analysis_data else []

            except:

                pass

        # Step 2: Generate annotation schema for suggested types

        schema = []

        for annotation_type in suggested_types:

            schema.append({

                'name': annotation_type.lower().replace(' ', '_'),

                'color': self.get_color_for_type(annotation_type)

            })

        # Step 3: Create completely dynamic prompt

        if suggested_types:

            types_list = ', '.join(suggested_types)

            prompt = f"""Extract entities from this document. Look for these types of information: {types_list}

    Find EXACT text spans that match these categories. Only extract text that physically exists in the document.

    Document: {text}

    Return JSON array: [{{"text": "exact_text", "type": "type_name", "start_pos": 0, "end_pos": 10, "confidence": 0.9, "reasoning": "why"}}]"""

        else:

            # Fallback: completely open-ended extraction

            prompt = f"""Analyze this document and extract any important entities, data points, or key information.

    Determine what types of information are present and extract them with appropriate type names.

    Document: {text}

    Return JSON array: [{{"text": "exact_text", "type": "type_you_determine", "start_pos": 0, "end_pos": 10, "confidence": 0.9, "reasoning": "why"}}]"""

        # Step 4: Process with Groq

        response = self.call_groq_api(prompt)

        annotations = self.parse_groq_response(response, page_num) if response else []

        

        # Step 5: Generate schema for any types we didn't predict

        all_types = set(suggested_types)

        for ann in annotations:

            all_types.add(ann.get('type', ''))

        

        # Update schema with any new types found

        schema = []

        for annotation_type in all_types:

            if annotation_type:

                schema.append({

                    'name': annotation_type.lower().replace(' ', '_'),

                    'color': self.generate_random_color()

                })

        return annotations, schema

    def get_color_for_type(self, annotation_type: str) -> str:
        """Generate consistent color for annotation type"""
        import hashlib
        # Generate consistent color based on type name
        hash_object = hashlib.md5(annotation_type.encode())
        hex_dig = hash_object.hexdigest()
        return f"#{hex_dig[:6]}"

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
                    "content": "You are an expert regulatory document analyst. Extract entities with perfect precision, never hallucinate."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": 0.1,  # Low for consistency
            "max_tokens": max_tokens,
            "top_p": 0.9
        }

        try:
            response = requests.post(
                self.api_url,
                headers=headers,
                json=payload,
                timeout=120  # 2 minutes timeout
            )

            if response.status_code == 200:
                result = response.json()
                return result['choices'][0]['message']['content']
            elif response.status_code == 429:
                print("⚠️  Rate limit reached, waiting...")
                time.sleep(60)  # Wait 1 minute
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
                        # Clean up the annotation
                        item['page_num'] = page_num
                        item['source'] = 'groq_llama3.3_70b'

                        # Ensure confidence
                        if 'confidence' not in item:
                            item['confidence'] = 0.8
                        else:
                            item['confidence'] = float(item['confidence'])

                        # Ensure positions
                        if 'start_pos' not in item:
                            item['start_pos'] = 0
                        if 'end_pos' not in item:
                            item['end_pos'] = len(item['text'])

                        annotations.append(item)

                print(f"✅ Parsed {len(annotations)} annotations from GROQ")
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
            json_match = re.search(r'```json\s*(\[.*?\])\s*```', response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group(1))
        except:
            pass

        # Look for JSON array
        try:
            json_match = re.search(r'(\[.*?\])', response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group(1))
        except:
            pass

        return None

    def generate_summary(self, pdf_data: Dict[str, Any], annotations: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Generate processing summary"""

        # Analyze annotations
        type_counts = {}
        confidence_scores = []

        for ann in annotations:
            ann_type = ann.get('type', 'unknown')
            type_counts[ann_type] = type_counts.get(ann_type, 0) + 1
            confidence_scores.append(ann.get('confidence', 0.5))

        avg_confidence = sum(confidence_scores) / len(confidence_scores) if confidence_scores else 0
        high_confidence_count = len([c for c in confidence_scores if c > 0.8])

        return {
            'total_pages': pdf_data.get('total_pages', 0),
            'total_annotations': len(annotations),
            'annotation_breakdown': type_counts,
            'average_confidence': round(avg_confidence, 3),
            'high_confidence_annotations': high_confidence_count,
            'processing_model': self.model,
            'cost': 0.0,  # FREE!
            'quality_grade': 'A' if avg_confidence > 0.85 else 'B+' if avg_confidence > 0.75 else 'B'
        }

