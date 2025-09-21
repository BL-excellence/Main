# rawdocs/groq_annotation_system.py
import os
import re
import json
import time
import random
import hashlib
import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Any, Optional, Tuple
from django.conf import settings


class GroqAnnotator:
    """
    Enhanced GROQ (OpenAI-compatible API) integration for regulatory document annotation.
    Now supports structured HTML content for more accurate annotations.
    """

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_url = getattr(settings, "GROQ_API_URL", "https://api.groq.com/openai/v1/chat/completions")
        self.model = model or getattr(settings, "GROQ_MODEL", os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"))
        self.api_key = api_key or getattr(settings, "GROQ_API_KEY", os.getenv("GROQ_API_KEY", ""))

        self.enabled = bool(self.api_key)
        self.last_schema: List[Dict[str, str]] = []
        self._api_healthy: Optional[bool] = None

        if self.enabled:
            print(f"🔍 GROQ Analyzer initialized (model: {self.model})")
            try:
                self.test_connection()
            except Exception as e:
                print(f"⚠️ GROQ test failed: {e}")
        else:
            print("ℹ️ GROQ disabled (no API key)")

    def annotate_structured_content(self, html_content: str, document_context: str = "") -> Dict[int, List[Dict[str, Any]]]:
        """
        Process structured HTML content and generate annotations with correct positioning.
        Returns annotations organized by page number.
        
        Args:
            html_content: HTML string with structured document content
            document_context: Additional context about the document
        
        Returns:
            Dict[page_number, List[annotation_data]]
        """
        try:
            # Parse HTML
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Extract text by page while preserving structure
            pages_content = {}
            page_elements = soup.find_all(class_='page')
            
            for page_el in page_elements:
                try:
                    page_num = int(page_el.get('data-page-number', 0))
                    if not page_num:
                        continue
                        
                    # Get clean text while preserving positions
                    text_chunks = []
                    offset = 0
                    chunk_positions = {}
                    
                    # Process text elements while tracking positions
                    for el in page_el.find_all(class_='text-chunk'):
                        chunk_text = el.get_text(strip=True)
                        if not chunk_text:
                            continue
                            
                        # Track element position
                        chunk_positions[offset] = {
                            'text': chunk_text,
                            'element': el
                        }
                        text_chunks.append(chunk_text)
                        offset += len(chunk_text) + 1
                    
                    # Store page content with position mapping
                    pages_content[page_num] = {
                        'text': ' '.join(text_chunks),
                        'positions': chunk_positions
                    }
                    
                except Exception as e:
                    print(f"Error processing page {page_num}: {e}")
                    continue
            
            # Process each page for annotations
            results = {}
            for page_num, content in pages_content.items():
                print(f"🔍 Processing page {page_num} content")
                
                # Build prompt with document context
                prompt = self._build_structured_annotation_prompt(
                    content['text'],
                    document_context,
                    page_num
                )
                
                # Get annotations from GROQ
                annotations = self._extract_annotations_from_structured_content(
                    prompt,
                    content['text'],
                    content['positions']
                )
                
                if annotations:
                    results[page_num] = annotations
                    print(f"✅ Generated {len(annotations)} annotations for page {page_num}")
                
            print(f"✅ Processed {len(pages_content)} pages")
            return results
            
        except Exception as e:
            print(f"❌ Error processing structured content: {e}")
            return {}

    def _build_structured_annotation_prompt(self, text: str, context: str, page_num: int) -> str:
        """Create optimized prompt for structured content annotation"""
        return f"""Analyze this document text and identify key entities. This is page {page_num}.

Document Context:
{context}

Document Text:
{text[:3000]}

Find EXACT text spans for relevant entity types. Focus on:
- Legal references (laws, directives, regulations)
- Regulatory authorities
- Required documents
- Compliance requirements
- Deadlines and timeframes
- Procedural steps
- Technical specifications
- Safety/quality requirements

Return ONLY a JSON array like:
[{{"text":"exact_text","type":"entity_type","start_pos":0,"end_pos":10,"confidence":0.9,"reasoning":"brief_explanation"}}]

CRITICAL:
1. text MUST be exact matches from the document
2. positions MUST be correct character offsets
3. DO NOT paraphrase or modify the text"""

    def _extract_annotations_from_structured_content(
        self,
        prompt: str,
        text: str,
        positions: Dict[int, Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Extract and validate annotations from structured content response.
        Maps annotations to correct positions in the original HTML.
        """
        try:
            # Get raw annotations from GROQ
            response = self.complete_text(prompt, max_tokens=1000)
            if not response:
                return []

            data = self._extract_json_from_text(response)
            if not isinstance(data, list):
                print("❌ Invalid annotation format (expected array)")
                return []

            # Process and validate each annotation
            validated_annotations = []
            for item in data:
                if not isinstance(item, dict):
                    continue

                try:
                    # Normalize the annotation data
                    ann = self._coerce_annotation_item(item)
                    if not ann:
                        continue

                    # Verify text exists in document
                    found = self._find_text_position(ann['text'], text)
                    if not found:
                        continue

                    start_pos, end_pos, actual_text = found

                    # Map positions to HTML elements
                    element_positions = []
                    for pos, chunk in positions.items():
                        if pos <= start_pos < pos + len(chunk['text']):
                            element_positions.append(chunk)

                    if not element_positions:
                        print(f"⚠️ Could not map annotation to HTML elements: {ann['text'][:30]}")
                        continue

                    # Add validated annotation with HTML context
                    validated_annotations.append({
                        'text': actual_text,
                        'type': ann['type'],
                        'start_pos': start_pos,
                        'end_pos': end_pos,
                        'confidence': ann['confidence'],
                        'reasoning': ann['reasoning'],
                        'elements': element_positions
                    })

                except Exception as e:
                    print(f"Error validating annotation: {e}")
                    continue

            return validated_annotations

        except Exception as e:
            print(f"❌ Error extracting annotations: {e}")
            return []
            
    # [... Rest of the GroqAnnotator class methods remain unchanged ...]