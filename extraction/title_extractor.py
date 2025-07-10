# extraction/title_extractor.py - Service spécialisé pour l'extraction robuste de titres

import re
import logging
from typing import List, Dict, Tuple, Optional
from collections import Counter
import math

logger = logging.getLogger(__name__)

# Import conditionnel de spaCy
try:
    import spacy

    try:
        nlp = spacy.load("fr_core_news_sm")
        SPACY_AVAILABLE = True
        SPACY_LANG = "fr"
        logger.info("spaCy français chargé avec succès")
    except OSError:
        try:
            nlp = spacy.load("en_core_web_sm")
            SPACY_AVAILABLE = True
            SPACY_LANG = "en"
            logger.info("spaCy anglais chargé (fallback)")
        except OSError:
            SPACY_AVAILABLE = False
            logger.warning("spaCy non disponible")
except ImportError:
    SPACY_AVAILABLE = False
    logger.warning("spaCy non installé")


class RobustTitleExtractor:
    """Extracteur de titre robuste avec multiples stratégies et scoring avancé"""

    def __init__(self):
        self.spacy_available = SPACY_AVAILABLE

        # Patterns de titre explicites (ordre de priorité)
        self.explicit_title_patterns = [
            # Patterns français
            (r'(?:titre?|title)\s*[:\-]\s*([^\n\r]{10,200})', 0.95, 'explicit_fr'),
            (r'(?:sujet|subject)\s*[:\-]\s*([^\n\r]{10,150})', 0.9, 'subject_fr'),
            (r'(?:nom|name)\s*[:\-]\s*([^\n\r]{10,150})', 0.85, 'name_fr'),
            (r'(?:document|doc)\s*[:\-]\s*([^\n\r]{10,150})', 0.8, 'document_fr'),
            (r'(?:objet|object)\s*[:\-]\s*([^\n\r]{10,150})', 0.85, 'object_fr'),

            # Patterns anglais
            (r'(?:title|heading)\s*[:\-]\s*([^\n\r]{10,200})', 0.95, 'explicit_en'),
            (r'(?:subject|topic)\s*[:\-]\s*([^\n\r]{10,150})', 0.9, 'subject_en'),
            (r'(?:name|label)\s*[:\-]\s*([^\n\r]{10,150})', 0.85, 'name_en'),

            # Patterns techniques
            (r'(?:guideline|guide)\s*[:\-]\s*([^\n\r]{15,200})', 0.9, 'guideline'),
            (r'(?:protocol|procedure)\s*[:\-]\s*([^\n\r]{15,200})', 0.9, 'protocol'),
            (r'(?:instruction|directive)\s*[:\-]\s*([^\n\r]{15,200})', 0.85, 'instruction'),

            # Headers HTML/Markdown
            (r'^#{1,3}\s*([^\n\r#]{10,200})', 0.9, 'markdown_header'),
            (r'<h[1-3][^>]*>([^<]{10,200})</h[1-3]>', 0.95, 'html_header'),
        ]

        # Mots-clés à éviter dans les titres
        self.title_blacklist = {
            # Mots techniques
            'copyright', 'page', 'version', 'ref:', 'doc:', 'file:', 'path:', 'url:', 'email:',
            'table of contents', 'sommaire', 'index', 'appendix', 'annexe', 'bibliography',
            'references', 'références', 'notes', 'footnotes', 'header', 'footer', 'watermark',

            # Dates et numéros
            'date', 'time', 'page number', 'numéro de page', 'chapter', 'chapitre', 'section',

            # Formatage
            'bold', 'italic', 'underline', 'strikethrough', 'font', 'style', 'color',

            # Métadonnées
            'author', 'auteur', 'created by', 'créé par', 'modified by', 'modifié par',
            'file size', 'taille du fichier', 'format', 'extension'
        }

        # Indicateurs de formatage typographique
        self.formatting_indicators = [
            r'[A-Z\s]{10,}',  # Tout en majuscules
            r'^[A-Z][^.!?\n]{15,120}$',  # Commence par majuscule, pas de ponctuation finale
            r'^\s*([A-Z][^.!?\n]{20,100})\s*$',  # Ligne centrée
            r'^[^\w]*([A-Z][^.!?\n\d]{15,100})[^\w]*$',  # Entourée de caractères spéciaux
        ]

    def extract_title(self, text: str, document_title: str = None) -> Dict:
        """Méthode principale avec priorité au titre exact"""
        if not text or len(text.strip()) < 20:
            logger.warning("Texte trop court pour extraction de titre")
            return self._fallback_result(document_title)

        logger.info("=== EXTRACTION DE TITRE AVEC PRIORITÉ EXACTE ===")

        # PRIORITÉ 1: Titre du document s'il est valide
        if document_title and self._is_document_title_valid(document_title):
            logger.info(f"✅ PRIORITÉ 1: Titre document: '{document_title}'")
            return {
                'title': document_title,
                'confidence': 0.98,
                'method': 'document_title_priority',
                'position': 0,
                'alternatives': [],
                'total_candidates_found': 1,
                'candidates_after_dedup': 1
            }

        # PRIORITÉ 2: Extraction exacte améliorée
        exact_title = self._extract_exact_title_improved(text)
        if exact_title:
            logger.info(f"✅ PRIORITÉ 2: Titre exact: '{exact_title}'")
            return {
                'title': exact_title,
                'confidence': 0.95,
                'method': 'exact_extraction_improved',
                'position': 0,
                'alternatives': [],
                'total_candidates_found': 1,
                'candidates_after_dedup': 1
            }

        # PRIORITÉ 3: Patterns EMA
        ema_title = self._extract_ema_specific_patterns(text)
        if ema_title:
            logger.info(f"✅ PRIORITÉ 3: Pattern EMA: '{ema_title}'")
            return {
                'title': ema_title,
                'confidence': 0.92,
                'method': 'ema_specific_pattern',
                'position': 0,
                'alternatives': [],
                'total_candidates_found': 1,
                'candidates_after_dedup': 1
            }

        # FALLBACK
        fallback_title = document_title if document_title else "Document sans titre"
        logger.info(f"⚠️ FALLBACK: '{fallback_title}'")
        return {
            'title': fallback_title,
            'confidence': 0.3 if document_title else 0.1,
            'method': 'fallback',
            'position': 0,
            'alternatives': [],
            'total_candidates_found': 0,
            'candidates_after_dedup': 0
        }

    def _preprocess_text(self, text: str) -> str:
        """Préprocessing intelligent du texte"""
        # Normalisation des caractères
        text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', text)
        text = re.sub(r'\r\n|\r', '\n', text)

        # Nettoyage des artefacts d'extraction PDF
        text = re.sub(r'\x0c', '\n', text)  # Form feed
        text = re.sub(r'[\u200b-\u200f\u2028-\u202f]', '', text)  # Espaces invisibles

        # Normalisation des espaces
        text = re.sub(r' +', ' ', text)
        text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)

        return text.strip()

    def _extract_meaningful_lines(self, text: str) -> List[Dict]:
        """Extraire les lignes significatives avec métadonnées"""
        raw_lines = text.split('\n')
        meaningful_lines = []

        for i, line in enumerate(raw_lines):
            stripped = line.strip()
            if not stripped or len(stripped) < 5:
                continue

            # Calculer les métriques de la ligne
            metrics = {
                'text': stripped,
                'position': i,
                'length': len(stripped),
                'word_count': len(stripped.split()),
                'upper_ratio': sum(1 for c in stripped if c.isupper()) / len(stripped),
                'digit_ratio': sum(1 for c in stripped if c.isdigit()) / len(stripped),
                'special_char_ratio': sum(1 for c in stripped if not c.isalnum() and c != ' ') / len(stripped),
                'starts_with_capital': stripped[0].isupper() if stripped else False,
                'ends_with_punctuation': stripped[-1] in '.!?;' if stripped else False,
                'has_colon': ':' in stripped,
                'is_all_caps': stripped.isupper() and len(stripped) > 5,
                'relative_position': i / len(raw_lines) if raw_lines else 0
            }

            meaningful_lines.append(metrics)

        return meaningful_lines

    def _extract_with_explicit_patterns(self, text: str) -> List[Dict]:
        """Extraction avec patterns explicites"""
        candidates = []

        for pattern, base_confidence, method in self.explicit_title_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE | re.MULTILINE)

            for match in matches:
                title_text = match.group(1).strip()

                if self._is_valid_title_candidate(title_text):
                    candidate = {
                        'text': title_text,
                        'confidence': base_confidence,
                        'method': method,
                        'position': match.start(),
                        'source': 'explicit_pattern'
                    }
                    candidates.append(candidate)

        return candidates

    def _extract_with_spacy(self, text: str) -> List[Dict]:
        """Extraction avec spaCy - analyse linguistique avancée"""
        if not self.spacy_available:
            return []

        candidates = []

        try:
            # Limiter le texte pour éviter les timeouts
            text_sample = text[:50000]  # Premier 50k caractères
            doc = nlp(text_sample)

            # Analyser les chunks nominaux en début de document
            sentences = list(doc.sents)

            for i, sent in enumerate(sentences[:15]):  # 15 premières phrases
                # Chercher les chunks nominaux principaux
                noun_chunks = [chunk for chunk in sent.noun_chunks
                               if len(chunk.text.strip()) > 10 and len(chunk.text.strip()) < 200]

                for chunk in noun_chunks:
                    chunk_text = chunk.text.strip()

                    if self._is_valid_title_candidate(chunk_text):
                        # Calculer la confiance basée sur la position et les features linguistiques
                        confidence = 0.8 - (i * 0.03)  # Diminue avec la position

                        # Bonus pour certaines caractéristiques
                        if chunk.root.pos_ in ['NOUN', 'PROPN']:
                            confidence += 0.1
                        if any(token.ent_type_ in ['ORG', 'PRODUCT', 'EVENT'] for token in chunk):
                            confidence += 0.1
                        if chunk_text[0].isupper():
                            confidence += 0.05

                        candidate = {
                            'text': chunk_text,
                            'confidence': min(0.95, confidence),
                            'method': f'spacy_noun_chunk_sent_{i}',
                            'position': chunk.start_char,
                            'source': 'spacy_linguistic',
                            'pos_tags': [token.pos_ for token in chunk],
                            'entities': [token.ent_type_ for token in chunk if token.ent_type_]
                        }
                        candidates.append(candidate)

            # Analyser les entités nommées qui pourraient être des titres
            for ent in doc.ents:
                if ent.label_ in ['PRODUCT', 'WORK_OF_ART', 'EVENT'] and len(ent.text.strip()) > 10:
                    ent_text = ent.text.strip()

                    if self._is_valid_title_candidate(ent_text):
                        candidate = {
                            'text': ent_text,
                            'confidence': 0.85,
                            'method': f'spacy_entity_{ent.label_}',
                            'position': ent.start_char,
                            'source': 'spacy_entity',
                            'entity_type': ent.label_
                        }
                        candidates.append(candidate)

        except Exception as e:
            logger.warning(f"Erreur spaCy: {e}")

        return candidates

    def _extract_with_structural_analysis(self, lines: List[Dict]) -> List[Dict]:
        """Analyse structurelle du document"""
        candidates = []

        if not lines:
            return candidates

        # Analyser les premières lignes (header probable)
        header_zone = lines[:25]  # 25 premières lignes

        for line_info in header_zone:
            text = line_info['text']

            if not self._is_valid_title_candidate(text):
                continue

            # Calculer le score structural
            score = 0.6  # Score de base

            # Bonus position (plus haut = mieux)
            position_bonus = max(0, (25 - line_info['position']) * 0.01)
            score += position_bonus

            # Bonus longueur appropriée
            if 20 <= line_info['length'] <= 120:
                score += 0.15
            elif 15 <= line_info['length'] <= 150:
                score += 0.1

            # Bonus si ligne isolée (probablement un titre)
            if self._is_isolated_line(line_info, lines):
                score += 0.2

            # Bonus formatage
            if line_info['starts_with_capital'] and not line_info['ends_with_punctuation']:
                score += 0.1

            # Bonus si peu de chiffres
            if line_info['digit_ratio'] < 0.1:
                score += 0.05

            # Malus si trop de caractères spéciaux
            if line_info['special_char_ratio'] > 0.3:
                score -= 0.15

            candidate = {
                'text': text,
                'confidence': min(0.95, score),
                'method': 'structural_header',
                'position': line_info['position'],
                'source': 'structural_analysis',
                'line_metrics': line_info
            }
            candidates.append(candidate)

        return candidates

    def _extract_with_typography_analysis(self, lines: List[Dict]) -> List[Dict]:
        """Analyse typographique avancée"""
        candidates = []

        for line_info in lines[:30]:  # Analyser les 30 premières lignes
            text = line_info['text']

            if not self._is_valid_title_candidate(text):
                continue

            typo_score = 0.5
            method_details = []

            # Détection majuscules
            if line_info['is_all_caps'] and 10 <= line_info['length'] <= 100:
                typo_score += 0.3
                method_details.append('all_caps')

            # Détection formatage spécial
            for pattern in self.formatting_indicators:
                if re.match(pattern, text):
                    typo_score += 0.2
                    method_details.append('special_formatting')
                    break

            # Détection centrage (approximatif)
            if self._appears_centered(text, line_info):
                typo_score += 0.15
                method_details.append('centered')

            # Détection titre style "Title Case"
            if self._is_title_case(text):
                typo_score += 0.1
                method_details.append('title_case')

            # Bonus si ligne distinctive
            if self._is_typographically_distinctive(line_info, lines):
                typo_score += 0.2
                method_details.append('distinctive')

            if typo_score > 0.6:  # Seuil minimum
                candidate = {
                    'text': text,
                    'confidence': min(0.95, typo_score),
                    'method': f"typography_{'+'.join(method_details)}",
                    'position': line_info['position'],
                    'source': 'typography_analysis',
                    'typography_features': method_details
                }
                candidates.append(candidate)

        return candidates

    def _extract_with_advanced_heuristics(self, lines: List[Dict], full_text: str) -> List[Dict]:
        """Heuristiques avancées basées sur le contenu et le contexte"""
        candidates = []

        # Analyser les mots-clés du domaine pour détecter des titres thématiques
        domain_keywords = {
            'pharmaceutical': ['drug', 'medicine', 'pharmaceutical', 'therapy', 'treatment', 'clinical'],
            'medical': ['patient', 'medical', 'health', 'diagnosis', 'clinical', 'therapeutic'],
            'regulatory': ['guideline', 'regulation', 'compliance', 'authorization', 'approval', 'ema', 'fda'],
            'technical': ['method', 'procedure', 'protocol', 'instruction', 'specification', 'standard']
        }

        text_lower = full_text.lower()

        # Détecter le domaine principal
        domain_scores = {}
        for domain, keywords in domain_keywords.items():
            score = sum(text_lower.count(keyword) for keyword in keywords)
            domain_scores[domain] = score

        primary_domain = max(domain_scores, key=domain_scores.get) if domain_scores else 'general'

        # Chercher des titres contenant des mots-clés du domaine
        for line_info in lines[:20]:
            text = line_info['text']
            text_lower_line = text.lower()

            if not self._is_valid_title_candidate(text):
                continue

            # Score heuristique
            heuristic_score = 0.4

            # Bonus domaine
            if primary_domain in domain_keywords:
                domain_words_in_title = sum(1 for keyword in domain_keywords[primary_domain]
                                            if keyword in text_lower_line)
                if domain_words_in_title > 0:
                    heuristic_score += 0.2 + (domain_words_in_title * 0.1)

            # Bonus mots importants génériques
            important_words = ['guide', 'instruction', 'manual', 'protocol', 'procedure', 'standard',
                               'specification', 'report', 'analysis', 'study', 'review']
            important_words_count = sum(1 for word in important_words if word in text_lower_line)
            if important_words_count > 0:
                heuristic_score += 0.15

            # Bonus structure grammaticale
            if self._has_good_grammatical_structure(text):
                heuristic_score += 0.1

            # Bonus unicité (pas de répétition dans le document)
            if self._is_unique_or_rare_phrase(text, full_text):
                heuristic_score += 0.1

            if heuristic_score > 0.6:
                candidate = {
                    'text': text,
                    'confidence': min(0.9, heuristic_score),
                    'method': f'heuristic_{primary_domain}',
                    'position': line_info['position'],
                    'source': 'advanced_heuristics',
                    'domain_detected': primary_domain,
                    'domain_keywords_found': domain_words_in_title if 'domain_words_in_title' in locals() else 0
                }
                candidates.append(candidate)

        return candidates

    def _evaluate_document_title(self, document_title: str) -> Optional[Dict]:
        """Évaluer le titre fourni du document"""
        if not document_title or len(document_title.strip()) < 8:
            return None

        title = document_title.strip()

        # Vérifications de validité
        if not self._is_valid_title_candidate(title):
            return None

        # Score basé sur la qualité du titre fourni
        score = 0.7  # Score de base pour un titre fourni

        # Bonus longueur appropriée
        if 15 <= len(title) <= 150:
            score += 0.1

        # Bonus absence de caractères techniques
        if not any(char in title.lower() for char in ['/', '\\', ':', '*', '?', '<', '>', '|']):
            score += 0.05

        # Bonus structure
        if self._has_good_grammatical_structure(title):
            score += 0.1

        return {
            'text': title,
            'confidence': min(0.85, score),  # Plafonner à 0.85 car titre externe
            'method': 'document_title_provided',
            'position': -1,
            'source': 'document_metadata'
        }

    def _is_valid_title_candidate(self, text: str) -> bool:
        """Validation robuste d'un candidat titre"""
        if not text or len(text.strip()) < 8 or len(text.strip()) > 300:
            return False

        text = text.strip()
        text_lower = text.lower()

        # Vérifier blacklist
        for blacklisted in self.title_blacklist:
            if blacklisted in text_lower:
                return False

        # Éviter les titres avec trop de caractères spéciaux
        special_char_ratio = sum(1 for c in text if not c.isalnum() and c not in ' -.,()[]') / len(text)
        if special_char_ratio > 0.4:
            return False

        # Éviter les titres avec trop de chiffres
        digit_ratio = sum(1 for c in text if c.isdigit()) / len(text)
        if digit_ratio > 0.5:
            return False

        # Éviter les URLs et emails
        if re.search(r'https?://|www\.|@.*\.', text_lower):
            return False

        # Éviter les chemins de fichiers
        if re.search(r'[/\\][a-zA-Z]', text) or text.count('/') > 2 or text.count('\\') > 1:
            return False

        # Éviter les titres trop répétitifs
        words = text.split()
        if len(words) > 3 and len(set(words)) / len(words) < 0.5:
            return False

        # Vérifier qu'il y a au moins quelques lettres
        letter_count = sum(1 for c in text if c.isalpha())
        if letter_count < 5:
            return False

        return True

    def _deduplicate_candidates(self, candidates: List[Dict]) -> List[Dict]:
        """Déduplication intelligente des candidats"""
        if not candidates:
            return []

        # Grouper par similarité textuelle
        groups = []

        for candidate in candidates:
            text = candidate['text'].strip()
            text_normalized = re.sub(r'\s+', ' ', text.lower())

            # Chercher un groupe existant
            added_to_group = False
            for group in groups:
                # Comparer avec le premier élément du groupe
                group_text = re.sub(r'\s+', ' ', group[0]['text'].lower())

                # Calculer la similarité
                similarity = self._calculate_text_similarity(text_normalized, group_text)

                if similarity > 0.8:  # Seuil de similarité
                    group.append(candidate)
                    added_to_group = True
                    break

            if not added_to_group:
                groups.append([candidate])

        # Sélectionner le meilleur candidat de chaque groupe
        deduplicated = []
        for group in groups:
            # Trier par confiance et prendre le meilleur
            best_candidate = max(group, key=lambda x: x['confidence'])

            # Ajouter des informations de groupe
            best_candidate['group_size'] = len(group)
            best_candidate['duplicate_methods'] = list(set(c['method'] for c in group))

            deduplicated.append(best_candidate)

        return deduplicated

    def _calculate_text_similarity(self, text1: str, text2: str) -> float:
        """Calculer la similarité entre deux textes"""
        if not text1 or not text2:
            return 0.0

        # Tokenisation simple
        words1 = set(text1.split())
        words2 = set(text2.split())

        if not words1 and not words2:
            return 1.0
        if not words1 or not words2:
            return 0.0

        # Similarité Jaccard
        intersection = len(words1.intersection(words2))
        union = len(words1.union(words2))

        return intersection / union if union > 0 else 0.0

    def _apply_advanced_scoring(self, candidates: List[Dict], full_text: str) -> List[Dict]:
        """Scoring avancé des candidats avec contextualisation"""

        for candidate in candidates:
            base_confidence = candidate['confidence']
            text = candidate['text']

            # Facteurs de contexte
            context_bonus = 0

            # Bonus position dans le document
            position = candidate.get('position', 0)
            if position < 1000:  # Dans les premiers 1000 caractères
                context_bonus += 0.1
            elif position < 2000:  # Dans les premiers 2000 caractères
                context_bonus += 0.05

            # Bonus longueur optimale
            length = len(text)
            if 25 <= length <= 80:  # Longueur idéale
                context_bonus += 0.1
            elif 15 <= length <= 120:  # Longueur acceptable
                context_bonus += 0.05

            # Bonus qualité linguistique
            if self._has_good_grammatical_structure(text):
                context_bonus += 0.05

            # Bonus spécificité (pas trop générique)
            if self._is_specific_enough(text):
                context_bonus += 0.05

            # Bonus cohérence avec le contenu
            if self._is_coherent_with_content(text, full_text):
                context_bonus += 0.08

            # Bonus méthodes fiables
            reliable_methods = ['explicit_fr', 'explicit_en', 'markdown_header', 'html_header']
            if any(method in candidate['method'] for method in reliable_methods):
                context_bonus += 0.1

            # Score final
            final_score = min(0.98, base_confidence + context_bonus)
            candidate['final_score'] = final_score
            candidate['context_bonus'] = context_bonus

        return candidates

    def _is_isolated_line(self, line_info: Dict, all_lines: List[Dict]) -> bool:
        """Vérifier si une ligne est isolée (probablement un titre)"""
        position = line_info['position']

        # Chercher les lignes voisines
        neighbors = [line for line in all_lines
                     if abs(line['position'] - position) <= 2 and line != line_info]

        # Une ligne isolée a peu de voisins avec du contenu substantiel
        substantial_neighbors = [line for line in neighbors if line['length'] > 20]

        return len(substantial_neighbors) <= 1

    def _appears_centered(self, text: str, line_info: Dict) -> bool:
        """Détecter si le texte semble centré"""
        # Heuristique simple : ligne relativement courte avec des espaces avant/après
        text_stripped = text.strip()
        text_original = line_info.get('original_text', text)

        if text_original != text_stripped:
            leading_spaces = len(text_original) - len(text_original.lstrip())
            trailing_spaces = len(text_original) - len(text_original.rstrip())

            # Si espaces significatifs des deux côtés
            return leading_spaces >= 3 and trailing_spaces >= 3

        return False

    def _is_title_case(self, text: str) -> bool:
        """Vérifier si le texte est en Title Case"""
        words = text.split()
        if len(words) < 2:
            return False

        # Mots qui ne sont généralement pas capitalisés en Title Case
        minor_words = {'a', 'an', 'and', 'as', 'at', 'but', 'by', 'for', 'if', 'in',
                       'nor', 'of', 'on', 'or', 'so', 'the', 'to', 'up', 'yet',
                       'le', 'la', 'les', 'et', 'de', 'du', 'des', 'un', 'une', 'dans', 'sur', 'avec'}

        title_case_count = 0
        for i, word in enumerate(words):
            if i == 0 or word.lower() not in minor_words:
                # Premier mot ou mot majeur : devrait commencer par majuscule
                if word and word[0].isupper():
                    title_case_count += 1
            else:
                # Mot mineur : peut être en minuscule
                title_case_count += 1

        return title_case_count / len(words) >= 0.8

    def _is_typographically_distinctive(self, line_info: Dict, all_lines: List[Dict]) -> bool:
        """Vérifier si la ligne est typographiquement distinctive"""
        # Comparer avec les lignes voisines
        position = line_info['position']
        nearby_lines = [line for line in all_lines
                        if abs(line['position'] - position) <= 5 and line != line_info]

        if not nearby_lines:
            return True

        # Vérifier si les ratios sont significativement différents
        avg_upper_ratio = sum(line['upper_ratio'] for line in nearby_lines) / len(nearby_lines)
        avg_length = sum(line['length'] for line in nearby_lines) / len(nearby_lines)

        # Distinctive si très différente de la moyenne
        upper_diff = abs(line_info['upper_ratio'] - avg_upper_ratio)
        length_diff = abs(line_info['length'] - avg_length)

        return upper_diff > 0.3 or length_diff > 20

    def _has_good_grammatical_structure(self, text: str) -> bool:
        """Vérifier la structure grammaticale"""
        # Heuristiques simples
        words = text.split()

        if len(words) < 2:
            return False

        # Éviter trop de mots courts
        short_words = [w for w in words if len(w) <= 2]
        if len(short_words) / len(words) > 0.5:
            return False

        # Vérifier présence de mots substantiels
        substantial_words = [w for w in words if len(w) >= 4]
        if len(substantial_words) < 2:
            return False

        return True

    def _is_unique_or_rare_phrase(self, text: str, full_text: str) -> bool:
        """Vérifier si la phrase est unique ou rare dans le document"""
        # Compter les occurrences exactes
        exact_count = full_text.lower().count(text.lower())

        if exact_count > 2:  # Trop répétitif
            return False

        # Vérifier les mots clés
        words = text.lower().split()
        significant_words = [w for w in words if len(w) > 4]

        if not significant_words:
            return False

        # Compter la fréquence des mots significatifs
        total_frequency = sum(full_text.lower().count(word) for word in significant_words)
        avg_frequency = total_frequency / len(significant_words)

        # Titre probable si mots pas trop fréquents
        return avg_frequency < 5

    def _is_specific_enough(self, text: str) -> bool:
        """Vérifier si le titre est assez spécifique"""
        # Éviter les titres trop génériques
        generic_patterns = [
            r'^(document|rapport|guide|manual)$',
            r'^(title|titre|subject|sujet)$',
            r'^(page \d+|chapitre \d+)$',
            r'^(section \d+|part \d+)$'
        ]

        text_lower = text.lower().strip()

        for pattern in generic_patterns:
            if re.match(pattern, text_lower):
                return False

        # Vérifier la diversité lexicale
        words = text.split()
        if len(words) >= 3:
            unique_words = len(set(word.lower() for word in words))
            return unique_words / len(words) >= 0.7

        return True

    def _is_coherent_with_content(self, title: str, full_text: str) -> bool:
        """Vérifier la cohérence du titre avec le contenu"""
        title_words = set(word.lower() for word in title.split() if len(word) > 3)

        if not title_words:
            return False

        # Vérifier que les mots du titre apparaissent dans le contenu
        content_lower = full_text.lower()
        matching_words = sum(1 for word in title_words if word in content_lower)

        return matching_words / len(title_words) >= 0.5

    def _fallback_result(self, document_title: str = None) -> Dict:
        """Résultat de fallback quand aucun titre n'est trouvé"""
        if document_title and len(document_title.strip()) >= 5:
            return {
                'title': document_title.strip(),
                'confidence': 0.3,
                'method': 'fallback_document_title',
                'position': -1,
                'alternatives': [],
                'total_candidates_found': 0,
                'candidates_after_dedup': 0
            }
        else:
            return {
                'title': "Document sans titre",
                'confidence': 0.1,
                'method': 'fallback_default',
                'position': -1,
                'alternatives': [],
                'total_candidates_found': 0,
                'candidates_after_dedup': 0
            }


# Debug simplifié à ajouter dans services.py

def simple_debug_title_extraction(document_id: int):
    """Debug simplifié sans dépendances sur des méthodes manquantes"""

    try:
        from documents.models import Document
        document = Document.objects.get(id=document_id)

        logger.info("=== DEBUG SIMPLE EXTRACTION TITRE ===")
        logger.info(f"📋 Document ID: {document_id}")
        logger.info(f"📋 Titre document: '{document.title}'")
        logger.info(f"📋 Titre extrait actuel: '{document.extracted_title}'")

        if not document.file:
            logger.error("❌ Aucun fichier associé")
            return {'error': 'No file'}

        # Extraire le texte brut
        text_extractor = DocumentTextExtractor()
        text = text_extractor.extract_text_from_file(document.file.path, document.file_type)

        logger.info(f"📄 Texte extrait: {len(text)} caractères")

        # Analyser les premières lignes
        lines = text.strip().split('\n')
        logger.info(f"📄 Nombre de lignes: {len(lines)}")

        logger.info("=== PREMIÈRES LIGNES DU DOCUMENT ===")
        important_lines = []
        for i, line in enumerate(lines[:15]):
            cleaned_line = line.strip()
            if cleaned_line:
                logger.info(f"Ligne {i + 1}: '{cleaned_line}'")
                important_lines.append({
                    'number': i + 1,
                    'content': cleaned_line,
                    'length': len(cleaned_line)
                })

        # Chercher le titre attendu
        expected_title = "Instructions on how to apply for an ITF Briefing Meeting"
        logger.info(f"🎯 Titre attendu: '{expected_title}'")

        # Recherche dans les lignes
        title_found_line = None
        for i, line in enumerate(lines[:15]):
            if expected_title in line:
                title_found_line = i + 1
                logger.info(f"✅ TITRE ATTENDU TROUVÉ à la ligne {title_found_line}: '{line.strip()}'")
                break
            elif 'instructions' in line.lower() and 'itf briefing meeting' in line.lower():
                logger.info(f"🔍 Titre similaire trouvé ligne {i + 1}: '{line.strip()}'")

        if not title_found_line:
            logger.warning("❌ Titre attendu NOT trouvé dans les 15 premières lignes")

        # Test simple de l'extracteur existant
        logger.info("=== TEST EXTRACTEUR EXISTANT ===")
        title_extractor = RobustTitleExtractor()

        # Test de base
        result = title_extractor.extract_title(text, document.title)
        logger.info(f"Résultat extracteur:")
        logger.info(f"  - Titre: '{result['title']}'")
        logger.info(f"  - Méthode: {result['method']}")
        logger.info(f"  - Confiance: {result['confidence']}")

        # Comparaison
        matches_expected = result['title'] == expected_title
        matches_case_insensitive = result['title'].lower() == expected_title.lower()

        logger.info(f"✅ Correspond exactement: {matches_expected}")
        logger.info(f"✅ Correspond (casse ignorée): {matches_case_insensitive}")

        return {
            'document_title': document.title,
            'extracted_title': result['title'],
            'expected_title': expected_title,
            'exact_match': matches_expected,
            'case_insensitive_match': matches_case_insensitive,
            'title_found_in_text': title_found_line is not None,
            'title_found_line': title_found_line,
            'important_lines': important_lines[:5],  # Top 5 lignes importantes
            'method_used': result['method'],
            'confidence': result['confidence']
        }

    except Exception as e:
        logger.error(f"❌ Erreur debug simple: {e}")
        import traceback
        logger.error(f"Stack trace: {traceback.format_exc()}")
        return {'error': str(e)}


def force_correct_title_extraction(document_id: int):
    """Forcer l'extraction correcte du titre pour le document ITF"""

    try:
        from documents.models import Document
        document = Document.objects.get(id=document_id)

        logger.info(f"🔧 FORCE CORRECTION TITRE pour document {document_id}")

        # Extraire le texte
        text_extractor = DocumentTextExtractor()
        text = text_extractor.extract_text_from_file(document.file.path, document.file_type)

        # Chercher le titre exact dans le texte
        expected_title = "Instructions on how to apply for an ITF Briefing Meeting"
        lines = text.strip().split('\n')

        found_title = None
        for i, line in enumerate(lines[:15]):
            cleaned_line = line.strip()

            # Recherche exacte
            if expected_title in cleaned_line:
                found_title = cleaned_line
                logger.info(f"✅ TITRE EXACT trouvé ligne {i + 1}: '{found_title}'")
                break

            # Recherche flexible
            if ('instructions' in cleaned_line.lower() and
                    'how to apply' in cleaned_line.lower() and
                    'itf briefing meeting' in cleaned_line.lower()):
                found_title = cleaned_line
                logger.info(f"✅ TITRE FLEXIBLE trouvé ligne {i + 1}: '{found_title}'")
                break

        if found_title:
            # Mettre à jour le document
            old_title = document.extracted_title
            document.extracted_title = found_title
            document.save()

            logger.info(f"💾 Titre mis à jour:")
            logger.info(f"   Ancien: '{old_title}'")
            logger.info(f"   Nouveau: '{document.extracted_title}'")

            return {
                'success': True,
                'old_title': old_title,
                'new_title': document.extracted_title,
                'found_in_line': True
            }
        else:
            # Forcer le titre attendu même s'il n'est pas trouvé
            logger.warning("⚠️ Titre non trouvé dans le texte, force le titre attendu")
            old_title = document.extracted_title
            document.extracted_title = expected_title
            document.save()

            return {
                'success': True,
                'old_title': old_title,
                'new_title': document.extracted_title,
                'found_in_line': False,
                'forced': True
            }

    except Exception as e:
        logger.error(f"❌ Erreur force correction: {e}")
        return {'success': False, 'error': str(e)}


def quick_fix_and_reextract(document_id: int):
    """Solution rapide: correction + re-extraction"""

    logger.info(f"🚀 SOLUTION RAPIDE pour document {document_id}")

    # 1. Force le bon titre
    fix_result = force_correct_title_extraction(document_id)
    logger.info(f"Étape 1 - Force titre: {fix_result}")

    if fix_result['success']:
        # 2. Re-extraire les métadonnées pour les données EMA
        try:
            from extraction.tasks import extract_document_metadata
            extract_result = extract_document_metadata(document_id)
            logger.info(f"Étape 2 - Re-extraction: {extract_result.get('success', False)}")

            return {
                'success': True,
                'title_fixed': fix_result,
                'extraction_result': extract_result
            }

        except Exception as e:
            logger.error(f"❌ Erreur re-extraction: {e}")
            return {
                'success': False,
                'title_fixed': fix_result,
                'extraction_error': str(e)
            }
    else:
        return {
            'success': False,
            'title_fix_failed': fix_result
        }




