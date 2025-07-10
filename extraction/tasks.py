# # extraction/tasks.py - Version nettoyée et optimisée


# extraction/tasks.py - Ajout de la fonction process_document_from_urls
import logging
from datetime import datetime
from typing import Dict, List, Optional

from django.core.files.storage import default_storage
from django.utils import timezone

from documents.models import Document
from .models import ExtractionResult
from .services import MistralAIService, DocumentTextExtractor, NLPAnnotationService
from .url_services import URLDocumentProcessor

logger = logging.getLogger(__name__)

# Import conditionnel de Celery
try:
    from celery import shared_task

    CELERY_AVAILABLE = True
except ImportError:
    CELERY_AVAILABLE = False


    def shared_task(func):
        return func


# [Toutes les autres classes et fonctions existantes restent inchangées...]
# DocumentProcessor, DocumentUpdater, ConfidenceCalculator, etc.

class DocumentProcessor:
    """Classe pour traiter les documents de manière cohérente"""

    def __init__(self):
        self.text_extractor = DocumentTextExtractor()
        self.metadata_service = MistralAIService()
        self.nlp_service = NLPAnnotationService()

    def validate_document(self, document: Document) -> Dict[str, any]:
        validation_result = {
            'valid': False,
            'error': None,
            'file_path': None,
            'file_size': 0,
            'has_urls': False
        }

        if document.file:
            try:
                file_path = document.file.path
                import os

                if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
                    validation_result.update({
                        'valid': True,
                        'file_path': file_path,
                        'file_size': os.path.getsize(file_path),
                        'has_urls': False
                    })
                    logger.info(f"📂 Fichier local valide détecté: {file_path}")
                    return validation_result
                else:
                    validation_result['error'] = "Fichier local introuvable ou vide"
                    return validation_result

            except Exception as e:
                validation_result['error'] = f"Erreur accès fichier local: {str(e)}"
                return validation_result

        elif document.direct_pdf_url and document.ema_page_url:
            validation_result.update({
                'valid': True,
                'has_urls': True
            })
            logger.info(f"🌐 URLs valides détectées pour le document {document.id}")
            return validation_result

        else:
            validation_result['error'] = "Aucun fichier local ni URLs valides"
            return validation_result


class DocumentUpdater:
    """Classe pour mettre à jour les documents avec les métadonnées extraites"""

    @staticmethod
    def safe_string_field(value: any, max_length: int) -> str:
        """Sécurise un champ string pour la base de données"""
        if not value:
            return ""
        value_str = str(value).strip()
        return value_str[:max_length - 3] + "..." if len(value_str) > max_length else value_str

    @staticmethod
    def parse_date(date_str: str) -> Optional[datetime]:
        """Parse une date de manière robuste"""
        if not date_str or not str(date_str).strip():
            return None

        date_str = str(date_str).strip()

        # Ignorer les valeurs spéciales
        special_values = ['YEAR_MISSING', 'DATE_MISSING', 'N/A', 'None', '', 'null']
        if date_str.lower() in [v.lower() for v in special_values]:
            return None

        try:
            # Essayer avec dateparser si disponible
            try:
                import dateparser
                parsed_date = dateparser.parse(date_str, languages=['fr', 'en'])
                if parsed_date:
                    return parsed_date
            except ImportError:
                pass

            # Formats manuels
            import re

            # ISO format
            if re.match(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}', date_str):
                return datetime.fromisoformat(date_str.rstrip('Z'))

            # Format simple ISO
            if re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
                return datetime.strptime(date_str, '%Y-%m-%d')

            # Format DD/MM/YYYY
            if re.match(r'^\d{1,2}/\d{1,2}/\d{4}$', date_str):
                return datetime.strptime(date_str, '%d/%m/%Y')

        except Exception as e:
            logger.warning(f"⚠️ Erreur parsing date '{date_str}': {e}")

        return None

    def update_document_metadata(self, document: Document, metadata: Dict) -> Dict[str, any]:
        """Met à jour un document avec les métadonnées extraites - VERSION CORRIGÉE"""
        update_result = {
            'fields_updated': [],
            'ema_data_found': False,
            'errors': []
        }

        try:
            # CORRECTION CRITIQUE : Traitement prioritaire du titre
            extracted_title = metadata.get('title', '').strip()
            logger.info(f"🔍 Titre à sauvegarder: '{extracted_title}'")

            if extracted_title and extracted_title.lower() not in ['document sans titre', 'untitled', '', 'none']:
                # Sauvegarder le titre extrait par l'IA
                old_title = getattr(document, 'extracted_title', '') or ''
                new_title = self.safe_string_field(extracted_title, 255)

                if new_title != old_title:
                    document.extracted_title = new_title
                    update_result['fields_updated'].append('extracted_title')
                    logger.info(f"✅ Titre sauvegardé dans document.extracted_title: '{new_title}'")
                else:
                    logger.info(f"📝 Titre déjà correct: '{new_title}'")
            else:
                logger.warning(f"⚠️ Titre invalide non sauvegardé: '{extracted_title}'")

            # Mise à jour des autres champs de base
            field_mappings = {
                'language': ('language', 10),
                'source': ('source', 255),
                'version': ('version', 50),
                'source_url': ('source_url', 500)
            }

            for doc_field, (meta_key, max_length) in field_mappings.items():
                if meta_key in metadata and metadata[meta_key]:
                    old_value = getattr(document, doc_field, '') or ''
                    new_value = self.safe_string_field(metadata[meta_key], max_length)

                    if new_value and new_value != old_value:
                        setattr(document, doc_field, new_value)
                        update_result['fields_updated'].append(doc_field)
                        logger.debug(f"📝 {doc_field} mis à jour: '{old_value}' -> '{new_value}'")

            # Date de publication
            if metadata.get('publication_date'):
                parsed_date = self.parse_date(metadata['publication_date'])
                if parsed_date:
                    old_date = document.publication_date
                    new_date = parsed_date.date()
                    if new_date != old_date:
                        document.publication_date = new_date
                        update_result['fields_updated'].append('publication_date')
                        logger.info(f"📅 Date de publication mise à jour: {new_date}")

            # Données EMA
            ema_result = self._update_ema_data(document, metadata.get('ema_data', {}))
            update_result.update(ema_result)

            # IMPORTANT : Sauvegarder les changements
            if update_result['fields_updated'] or update_result.get('ema_fields_updated', []):
                document.save()
                total_updates = len(update_result['fields_updated']) + len(update_result.get('ema_fields_updated', []))
                logger.info(f"💾 Document sauvegardé avec {total_updates} champs mis à jour")
                logger.info(f"   - Champs principaux: {update_result['fields_updated']}")
                logger.info(f"   - Champs EMA: {update_result.get('ema_fields_updated', [])}")
            else:
                logger.info("📝 Aucune modification à sauvegarder")

        except Exception as e:
            error_msg = f"Erreur mise à jour document: {str(e)}"
            logger.error(f"❌ {error_msg}")
            update_result['errors'].append(error_msg)

        return update_result

    def _update_ema_data(self, document: Document, ema_data: Dict) -> Dict[str, any]:
        """Met à jour les données EMA spécifiquement"""
        result = {
            'ema_data_found': False,
            'ema_fields_updated': []
        }

        if not isinstance(ema_data, dict):
            return result

        try:
            # Mapping des champs EMA
            ema_mappings = {
                'ema_title': ('ema_title', 255),
                'ema_source_url': ('ema_source_url', 500),
                'ema_reference': ('ema_reference', 100)
            }

            for doc_field, (ema_key, max_length) in ema_mappings.items():
                if ema_key in ema_data and ema_data[ema_key]:
                    setattr(document, doc_field, self.safe_string_field(ema_data[ema_key], max_length))
                    result['ema_fields_updated'].append(doc_field)

            # Dates EMA
            date_mappings = [
                ('original_publication_date', 'original_publication_date'),
                ('ema_publication_date', 'ema_publication_date')
            ]

            for doc_field, ema_key in date_mappings:
                if ema_key in ema_data and ema_data[ema_key]:
                    parsed_date = self.parse_date(ema_data[ema_key])
                    if parsed_date:
                        setattr(document, doc_field, parsed_date.date())
                        result['ema_fields_updated'].append(doc_field)

            # Métadonnées de recherche
            document.ema_search_performed = ema_data.get('search_performed', False)
            document.ema_similarity_score = float(ema_data.get('similarity_score', 0.0))

            if ema_data.get('search_timestamp'):
                document.ema_last_search_date = timezone.now()

            # Compter les résultats
            ema_content = any([
                ema_data.get('ema_source_url'),
                ema_data.get('ema_title'),
                ema_data.get('ema_reference')
            ])

            document.ema_search_results_count = 1 if ema_content else 0
            result['ema_data_found'] = ema_content

        except Exception as e:
            logger.warning(f"⚠️ Erreur mise à jour EMA: {e}")

        return result


class ConfidenceCalculator:
    """Calculateur de scores de confiance"""

    @staticmethod
    def calculate_global_confidence(confidence_scores: Dict) -> float:
        """Calcule le score de confiance global"""
        if not confidence_scores or not isinstance(confidence_scores, dict):
            return 0.1

        weights = {
            'title': 0.25,
            'document_type': 0.15,
            'context': 0.15,
            'language': 0.15,
            'publication_date': 0.10,
            'source': 0.10,
            'version': 0.05,
            'source_url': 0.05
        }

        weighted_sum = 0
        total_weight = 0

        for field, score in confidence_scores.items():
            if field in weights:
                try:
                    score_float = float(score)
                    if 0 <= score_float <= 1:
                        weighted_sum += score_float * weights[field]
                        total_weight += weights[field]
                except (ValueError, TypeError):
                    continue

        return min(weighted_sum / total_weight, 1.0) if total_weight > 0 else 0.1


# ===== NOUVELLE FONCTION POUR TRAITER LES DOCUMENTS VIA URLs =====

@shared_task if CELERY_AVAILABLE else lambda f: f
def process_document_from_urls(document_id: int, direct_pdf_url: str, ema_page_url: str):
    """Traite un document à partir des URLs PDF et EMA"""
    processor = URLDocumentProcessor()
    updater = DocumentUpdater()

    try:
        document = Document.objects.get(id=document_id)
        logger.info(f"🔗 Début traitement URLs pour document {document_id}: '{document.title}'")
        logger.info(f"   PDF: {direct_pdf_url}")
        logger.info(f"   EMA: {ema_page_url}")

        # Mise à jour du statut
        document.status = 'extracting'
        document.extraction_started_at = timezone.now()
        document.save()

        # === TRAITEMENT PRINCIPAL ===
        processing_result = processor.process_document_from_urls(direct_pdf_url, ema_page_url)

        if not processing_result['success']:
            document.status = 'refused'
            document.save()
            return {
                'success': False,
                'error': processing_result['error'],
                'document_id': document_id
            }

        # === EXTRACTION DES MÉTADONNÉES COMPLÈTES ===
        title_extraction = processing_result['title_extraction']
        ema_metadata = processing_result['ema_metadata']
        temp_file_path = processing_result['temp_file_path']

        # IMPORTANT : Ne PAS sauvegarder le titre basique de l'URL maintenant
        # Le vrai titre sera extrait par Mistral depuis le contenu du PDF
        url_based_title = title_extraction['title']  # Garder pour fallback seulement
        logger.info(f"📝 Titre basique depuis URL: '{url_based_title}' (en attente du titre Mistral)")

        # Si le fichier temporaire existe, faire l'extraction complète
        full_metadata = None
        mistral_title = None

        if temp_file_path:
            try:
                text_extractor = DocumentTextExtractor()
                full_text = text_extractor.extract_text_from_file(temp_file_path, 'pdf')

                if full_text and len(full_text.strip()) > 50:
                    # Extraction complète des métadonnées avec Mistral
                    metadata_service = MistralAIService()
                    full_metadata = metadata_service.extract_metadata_with_confidence(
                        text=full_text,
                        file_type='pdf',
                        document_title=url_based_title,  # Passer le titre URL comme hint
                        source_url=direct_pdf_url
                    )

                    # CORRECTION CRITIQUE : Récupérer le titre extrait par Mistral
                    mistral_title = full_metadata.get('title', '').strip()
                    logger.info(f"🤖 Titre extrait par Mistral: '{mistral_title}'")

                    # Remplacer les données EMA par celles extraites de la page
                    if ema_metadata['success']:
                        full_metadata['ema_data'] = ema_metadata

                    logger.info(f"📊 Métadonnées complètes extraites")
                else:
                    logger.warning("⚠️ Texte insuffisant pour extraction complète")

            except Exception as e:
                logger.warning(f"⚠️ Erreur extraction métadonnées complètes: {e}")
            finally:
                # Nettoyer le fichier temporaire
                processor.cleanup_processing_files(temp_file_path)

        # === MISE À JOUR DU DOCUMENT ===
        update_result = {'fields_updated': [], 'ema_data_found': False}

        # Déterminer le titre final à utiliser
        final_title = ''
        if mistral_title and mistral_title.lower() not in ['document sans titre', 'untitled', '', 'none']:
            final_title = mistral_title
            logger.info(f"✅ Utilisation du titre Mistral: '{final_title}'")
        else:
            final_title = url_based_title
            logger.warning(f"⚠️ Fallback vers titre URL: '{final_title}'")

        if full_metadata:
            # S'assurer que le titre correct est dans les métadonnées
            full_metadata['title'] = final_title
            logger.info(f"📝 Titre dans full_metadata avant update: '{full_metadata.get('title', '')}'")
            update_result = updater.update_document_metadata(document, full_metadata)
        else:
            # Mise à jour minimale avec les données extraites
            document.extracted_title = final_title
            update_result['fields_updated'].append('extracted_title')

            # Données EMA si disponibles
            if ema_metadata['success']:
                ema_result = updater._update_ema_data(document, ema_metadata)
                update_result.update(ema_result)

            # Sauvegarder manuellement si pas de full_metadata
            document.save()

        # === FINALISATION ===
        document.status = 'extracted'
        document.extraction_completed_at = timezone.now()
        document.save()

        # === CRÉATION RÉSULTAT EXTRACTION ===
        processing_time = (timezone.now() - document.extraction_started_at).total_seconds()

        # Scores de confiance
        confidence_scores = {}
        global_confidence = 0.6  # Score par défaut pour traitement URLs

        if full_metadata and 'confidence_scores' in full_metadata:
            confidence_scores = full_metadata['confidence_scores']
            global_confidence = ConfidenceCalculator.calculate_global_confidence(confidence_scores)

        # Métadonnées enrichies - UTILISER LE BON TITRE
        if full_metadata:
            enriched_metadata = full_metadata.copy()
            enriched_metadata['title'] = final_title  # S'assurer que le bon titre est utilisé
            logger.info(f"✅ Métadonnées enrichies avec titre Mistral: '{enriched_metadata['title']}'")
        else:
            enriched_metadata = {
                'title': final_title,
                'source': 'EMA',
                'language': 'en',
                'extraction_method': 'url_processing'
            }
            logger.info(f"📝 Métadonnées minimales avec titre: '{enriched_metadata['title']}'")

        enriched_metadata['extraction_stats'] = {
            'processing_time_seconds': processing_time,
            'fields_updated': update_result['fields_updated'],
            'ema_data_found': update_result['ema_data_found'],
            'extraction_method': 'url_processing_v1',
            'title_extraction_confidence': title_extraction.get('confidence', 0.0),
            'ema_similarity_score': ema_metadata.get('similarity_score', 0.0),
            'direct_pdf_url': direct_pdf_url,
            'ema_page_url': ema_page_url,
            'mistral_title_extracted': bool(mistral_title)
        }

        try:
            extraction_result_obj = ExtractionResult.objects.create(
                document=document,
                extracted_data=enriched_metadata,
                confidence_scores=confidence_scores,
                confidence_score=global_confidence,
                status='completed',
                extraction_method='url_processing_v1',
                model_version='v1.0'
            )
            logger.info(f"📊 ExtractionResult créé (ID: {extraction_result_obj.id})")

            # Vérification finale
            saved_title = extraction_result_obj.extracted_data.get('title', 'NON TROUVÉ')
            logger.info(f"🔍 Titre sauvegardé dans ExtractionResult: '{saved_title}'")

        except Exception as e:
            logger.warning(f"⚠️ Erreur création ExtractionResult: {e}")

        # === ANNOTATION AUTOMATIQUE ===
        try:
            if CELERY_AVAILABLE:
                auto_annotate_document.delay(document_id)
            else:
                auto_annotate_document(document_id)
        except Exception as e:
            logger.warning(f"⚠️ Erreur annotation automatique: {e}")

        # === RÉSUMÉ ===
        logger.info(f"🎉 Traitement URLs terminé avec succès pour document {document_id}")
        logger.info(f"   - Titre final: '{final_title}'")
        logger.info(f"   - Titre Mistral extrait: {'✅' if mistral_title else '❌'}")
        logger.info(f"   - Données EMA: {'✅' if update_result['ema_data_found'] else '❌'}")
        logger.info(f"   - Score confiance: {global_confidence:.3f}")
        logger.info(f"   - Temps de traitement: {processing_time:.2f}s")

        return {
            'success': True,
            'document_id': document_id,
            'title_extracted': final_title,  # Retourner le titre final (Mistral ou fallback)
            'ema_data_found': update_result['ema_data_found'],
            'confidence_score': global_confidence,
            'processing_time': processing_time,
            'fields_updated': update_result['fields_updated']
        }

    except Document.DoesNotExist:
        logger.error(f"❌ Document {document_id} non trouvé")
        return {'success': False, 'error': f'Document {document_id} non trouvé'}

    except Exception as e:
        logger.error(f"❌ Erreur critique traitement URLs document {document_id}: {e}")

        try:
            document = Document.objects.get(id=document_id)
            document.status = 'refused'
            document.extraction_completed_at = timezone.now()
            document.save()
        except:
            pass

        return {'success': False, 'error': str(e)}


def process_metadata_extraction(self, text: str, file_type: str, document_title: str, document=None) -> Dict:
    """Traite l'extraction des métadonnées avec fallback - AVEC URL EMA"""
    try:
        # Récupérer l'URL EMA si disponible
        ema_page_url = None
        if document and hasattr(document, 'ema_page_url'):
            ema_page_url = document.ema_page_url
            logger.info(f"🔗 URL EMA disponible: {ema_page_url}")

        metadata = self.metadata_service.extract_metadata_with_ema(
            text=text,
            file_type=file_type,
            document_title=document_title,
            ema_page_url=ema_page_url
        )

        # Vérification du titre
        extracted_title = metadata.get('title', '').strip()
        logger.info(f"🔍 Titre dans metadata après extraction: '{extracted_title}'")

        if extracted_title and extracted_title.lower() not in ['document sans titre', 'untitled', '', 'none']:
            logger.info(f"✅ Titre valide préservé: '{extracted_title}'")
        else:
            logger.warning(f"⚠️ Titre invalide après extraction: '{extracted_title}'")
            if document_title and document_title.lower() not in ['document sans titre', 'untitled', '']:
                metadata['title'] = document_title
                logger.info(f"🔄 Fallback titre document: '{document_title}'")

        return metadata

    except Exception as e:
        logger.warning(f"⚠️ Échec extraction métadonnées, utilisation fallback: {e}")
        return self._get_fallback_metadata(document_title, str(e))


@shared_task if CELERY_AVAILABLE else lambda f: f
def extract_document_metadata(document_id: int):
    """Extraction de métadonnées - FLUX DE DONNÉES CORRIGÉ AVEC EMA"""
    processor = DocumentProcessor()
    updater = DocumentUpdater()

    try:
        document = Document.objects.get(id=document_id)
        logger.info(f"🚀 Début extraction classique pour document {document_id}: '{document.title}'")

        # Vérifier si on a une URL EMA
        if hasattr(document, 'ema_page_url') and document.ema_page_url:
            logger.info(f"🔗 URL EMA disponible: {document.ema_page_url}")

        # === VALIDATION ===
        validation = processor.validate_document(document)
        if not validation['valid']:
            document.status = 'refused'
            document.save()
            return {'success': False, 'error': validation['error']}

        # Si le document a des URLs mais pas de fichier, rediriger vers traitement URLs
        if validation['has_urls'] and not validation['file_path']:
            logger.info(f"🔗 Redirection vers traitement URLs pour document {document_id}")
            return process_document_from_urls(document_id, document.direct_pdf_url, document.ema_page_url)

        # Mise à jour du statut
        document.status = 'extracting'
        document.extraction_started_at = timezone.now()
        document.save()

        logger.info(f"📁 Fichier validé: {validation['file_size']} bytes")

        # === EXTRACTION TEXTE ===
        text_result = processor.extract_text_with_validation(
            validation['file_path'],
            document.file_type or 'unknown'
        )

        if not text_result['success']:
            document.status = 'refused'
            document.save()
            return {'success': False, 'error': text_result['error']}

        logger.info(f"✅ Texte extrait: {text_result['length']} caractères")

        # === EXTRACTION MÉTADONNÉES AVEC DOCUMENT ===
        metadata = processor.process_metadata_extraction(
            text_result['text'],
            document.file_type or 'unknown',
            document.title,
            document=document  # IMPORTANT: Passer l'objet document pour accéder à ema_page_url
        )

        logger.info(f"📊 Métadonnées extraites: {metadata.get('title', 'N/A')[:50]}...")

        # Log des données EMA extraites
        if 'ema_data' in metadata:
            logger.info(f"📊 Données EMA extraites: {metadata['ema_data']}")

        # CORRECTION CRITIQUE : Vérifier le titre extrait par le LLM
        llm_title = metadata.get('title', '').strip()
        logger.info(f"🔍 Titre LLM dans metadata: '{llm_title}'")

        # === MISE À JOUR DOCUMENT ===
        update_result = updater.update_document_metadata(document, metadata)

        # === FINALISATION ===
        document.status = 'extracted'
        document.extraction_completed_at = timezone.now()
        document.save()

        # === CRÉATION RÉSULTAT EXTRACTION - STRUCTURE PLATE CORRIGÉE ===
        confidence_scores = metadata.get('confidence_scores', {})
        global_confidence = ConfidenceCalculator.calculate_global_confidence(confidence_scores)

        processing_time = (timezone.now() - document.extraction_started_at).total_seconds()

        # CORRECTION CRITIQUE : Inclure TOUTES les données EMA dans la structure plate
        extracted_data_flat = {
            'title': llm_title,  # UTILISER DIRECTEMENT le titre du LLM
            'document_type': metadata.get('document_type', ''),
            'context': metadata.get('context', ''),
            'language': metadata.get('language', 'fr'),
            'publication_date': metadata.get('publication_date', ''),
            'source': metadata.get('source', ''),
            'version': metadata.get('version', ''),
            'source_url': metadata.get('source_url', ''),
            'country': metadata.get('country', ''),
            # IMPORTANT : Inclure TOUTES les données EMA
            'ema_data': metadata.get('ema_data', {}),
            # ET AUSSI les champs EMA individuellement pour compatibilité avec l'interface
            'original_publication_date': metadata.get('ema_data', {}).get('original_publication_date'),
            'ema_publication_date': metadata.get('ema_data', {}).get('ema_publication_date'),
            'ema_source_url': metadata.get('ema_data', {}).get('ema_source_url', ''),
            'ema_title': metadata.get('ema_data', {}).get('ema_title', ''),
            'ema_reference': metadata.get('ema_data', {}).get('ema_reference', ''),
            # Stats d'extraction
            'extraction_stats': {
                'text_length': text_result['length'],
                'processing_time_seconds': processing_time,
                'fields_updated': update_result['fields_updated'],
                'ema_data_found': update_result['ema_data_found'],
                'extraction_method': 'file_processing_v1',
                'extraction_reasoning': metadata.get('extraction_reasoning', {}),
                'ema_page_url_used': document.ema_page_url if hasattr(document, 'ema_page_url') else None
            }
        }

        # LOGS DE VÉRIFICATION EMA
        logger.info(f"📊 Données EMA dans extracted_data_flat:")
        logger.info(f"   - ema_data complet: {extracted_data_flat.get('ema_data', {})}")
        logger.info(f"   - ema_title: '{extracted_data_flat.get('ema_title', '')}'")
        logger.info(f"   - ema_source_url: '{extracted_data_flat.get('ema_source_url', '')}'")
        logger.info(f"   - ema_reference: '{extracted_data_flat.get('ema_reference', '')}'")
        logger.info(f"   - original_publication_date: {extracted_data_flat.get('original_publication_date')}")
        logger.info(f"   - ema_publication_date: {extracted_data_flat.get('ema_publication_date')}")

        logger.info(f"💾 Titre dans extracted_data_flat: '{extracted_data_flat['title']}'")

        # VÉRIFICATION FINALE avant sauvegarde
        if not extracted_data_flat['title'] or extracted_data_flat['title'].lower() in ['document sans titre',
                                                                                        'untitled', '']:
            logger.warning(f"⚠️ Titre invalide détecté avant sauvegarde: '{extracted_data_flat['title']}'")
            # Essayer d'utiliser le titre du document comme fallback
            fallback_title = document.extracted_title or document.title
            if fallback_title and fallback_title.lower() not in ['document sans titre', 'untitled']:
                extracted_data_flat['title'] = fallback_title
                logger.info(f"🔄 Fallback titre appliqué: '{fallback_title}'")

        logger.info(f"✅ Titre final pour sauvegarde: '{extracted_data_flat['title']}'")

        try:
            extraction_result_obj = ExtractionResult.objects.create(
                document=document,
                extracted_data=extracted_data_flat,  # Structure plate avec le bon titre ET les données EMA
                confidence_scores=confidence_scores,
                confidence_score=global_confidence,
                status='completed',
                extraction_method='file_processing_v1',
                model_version='v1.0'
            )
            logger.info(f"📊 ExtractionResult créé (ID: {extraction_result_obj.id})")
            logger.info(f"✅ Titre sauvegardé dans ExtractionResult: '{extracted_data_flat['title']}'")

            # VÉRIFICATION POST-SAUVEGARDE incluant EMA
            saved_data = extraction_result_obj.extracted_data
            saved_title = saved_data.get('title', 'NON TROUVÉ') if isinstance(saved_data, dict) else 'ERREUR TYPE'
            saved_ema_title = saved_data.get('ema_title', 'NON TROUVÉ') if isinstance(saved_data,
                                                                                      dict) else 'ERREUR TYPE'
            logger.info(f"🔍 Vérification post-sauvegarde:")
            logger.info(f"   - Titre: '{saved_title}'")
            logger.info(f"   - Titre EMA: '{saved_ema_title}'")

        except Exception as e:
            logger.warning(f"⚠️ Erreur création ExtractionResult: {e}")

        # === ANNOTATION AUTOMATIQUE ===
        try:
            if CELERY_AVAILABLE:
                auto_annotate_document.delay(document_id)
            else:
                auto_annotate_document(document_id)
        except Exception as e:
            logger.warning(f"⚠️ Erreur annotation automatique: {e}")

        # === RÉSUMÉ ===
        logger.info(f"🎉 Extraction classique terminée avec succès pour document {document_id}")
        logger.info(f"   - Score confiance: {global_confidence:.3f}")
        logger.info(f"   - Données EMA: {'✅' if update_result['ema_data_found'] else '❌'}")
        logger.info(f"   - Temps de traitement: {processing_time:.2f}s")

        return {
            'success': True,
            'metadata': extracted_data_flat,
            'confidence_score': global_confidence,
            'ema_data_found': update_result['ema_data_found'],
            'document_id': document_id,
            'processing_time': processing_time
        }

    except Document.DoesNotExist:
        logger.error(f"❌ Document {document_id} non trouvé")
        return {'success': False, 'error': f'Document {document_id} non trouvé'}

    except Exception as e:
        logger.error(f"❌ Erreur critique extraction document {document_id}: {e}")

        try:
            document = Document.objects.get(id=document_id)
            document.status = 'refused'
            document.extraction_completed_at = timezone.now()
            document.save()
        except:
            pass

        return {'success': False, 'error': str(e)}


@shared_task if CELERY_AVAILABLE else lambda f: f
def re_extract_document_metadata(document_id: int):
    """Ré-extraction avec reset complet - FORCE RESET EMA"""
    try:
        document = Document.objects.get(id=document_id)
        logger.info(f"🔄 Ré-extraction FORCÉE pour document {document_id}")

        # === SUPPRESSION COMPLÈTE DES ANCIENNES DONNÉES ===
        old_results_count = document.extraction_results.count()
        document.extraction_results.all().delete()
        logger.info(f"🗑️ {old_results_count} anciens résultats d'extraction supprimés")

        # === RESET COMPLET ET FORCÉ ===
        _reset_document_data(document)

        # === VÉRIFICATION POST-RESET ===
        document.refresh_from_db()
        logger.info(f"🔍 Vérification post-reset:")
        logger.info(f"  - ema_search_performed: {document.ema_search_performed}")
        logger.info(f"  - ema_title: '{document.ema_title}'")
        logger.info(f"  - ema_source_url: '{document.ema_source_url}'")
        logger.info(f"  - Extraction results count: {document.extraction_results.count()}")

        # === RELANCER EXTRACTION AVEC DONNÉES PROPRES ===
        logger.info(f"🚀 Lancement nouvelle extraction avec données propres")
        result = extract_document_metadata(document_id)

        if result.get('success'):
            logger.info(f"✅ Ré-extraction réussie pour document {document_id}")

            # Vérifier les NOUVELLES données EMA
            new_metadata = result.get('metadata', {})
            new_ema_data = new_metadata.get('ema_data', {})
            new_title = new_metadata.get('title', 'N/A')

            logger.info(f"📊 NOUVELLES données après ré-extraction:")
            logger.info(f"  - Nouveau titre: '{new_title}'")
            logger.info(f"  - Nouvelles données EMA: {new_ema_data}")

            # Vérification finale des données sauvegardées
            document.refresh_from_db()
            logger.info(f"📊 Données EMA finales dans la DB:")
            logger.info(f"  - ema_title: '{document.ema_title}'")
            logger.info(f"  - ema_source_url: '{document.ema_source_url}'")
            logger.info(f"  - original_publication_date: {document.original_publication_date}")

        else:
            logger.error(f"❌ Ré-extraction échouée: {result.get('error')}")

        return result

    except Document.DoesNotExist:
        logger.error(f"❌ Document {document_id} non trouvé pour ré-extraction")
        return {'success': False, 'error': f'Document {document_id} non trouvé'}
    except Exception as e:
        logger.error(f"❌ Erreur ré-extraction: {e}")
        return {'success': False, 'error': str(e)}


def _reset_document_data(document: Document):
    """Reset toutes les données d'un document - VERSION DÉFINITIVE"""
    logger.info(f"🔄 Reset COMPLET des données pour document {document.id}")

    # Reset EXPLICITE de tous les champs EMA
    document.ema_title = ''
    document.ema_source_url = ''
    document.ema_reference = ''
    document.original_publication_date = None
    document.ema_publication_date = None
    document.ema_search_performed = False
    document.ema_similarity_score = 0.0
    document.ema_search_results_count = 0
    document.ema_last_search_date = None

    # Reset autres champs métadonnées
    document.extracted_title = ''
    document.language = ''
    document.source = ''
    document.version = ''
    document.source_url = ''
    document.publication_date = None

    # Reset statut
    document.status = 'pending'
    document.extraction_started_at = None
    document.extraction_completed_at = None

    document.save()

    # Vérification immédiate
    document.refresh_from_db()
    logger.info(f"✅ Reset terminé pour document {document.id}")
    logger.info(f"  Vérifications post-reset:")
    logger.info(f"    - ema_title: '{document.ema_title}'")
    logger.info(f"    - ema_source_url: '{document.ema_source_url}'")
    logger.info(f"    - ema_search_performed: {document.ema_search_performed}")


@shared_task if CELERY_AVAILABLE else lambda f: f
def auto_annotate_document(document_id: int):
    """Annotation automatique optimisée"""
    processor = DocumentProcessor()

    try:
        document = Document.objects.get(id=document_id)
        logger.info(f"📝 Annotation automatique pour document {document_id}")

        validation = processor.validate_document(document)
        if not validation['valid']:
            return {'success': False, 'error': validation['error']}

        # Extraction de texte selon le mode
        if validation['file_path']:
            # Mode fichier local
            text_result = processor.extract_text_with_validation(
                validation['file_path'],
                document.file_type or 'unknown',
                min_length=50
            )
        elif validation['has_urls']:
            # Mode URLs - télécharger temporairement
            from .url_services import URLDocumentExtractor
            url_extractor = URLDocumentExtractor()
            temp_file = url_extractor.download_pdf_from_url(document.direct_pdf_url)

            if temp_file:
                text_result = processor.extract_text_with_validation(temp_file, 'pdf', min_length=50)
                url_extractor.cleanup_temp_file(temp_file)
            else:
                return {'success': False, 'error': 'Impossible de télécharger le PDF pour annotation'}
        else:
            return {'success': False, 'error': 'Aucune source de texte disponible'}

        if not text_result['success']:
            return {'success': False, 'error': text_result['error']}

        annotations = processor.nlp_service.auto_annotate_document(text_result['text'])
        saved_count = _save_annotations(document, annotations)

        logger.info(f"✅ {saved_count}/{len(annotations)} annotations sauvegardées")

        return {
            'success': True,
            'annotations_count': saved_count,
            'annotations_detected': len(annotations)
        }

    except Document.DoesNotExist:
        return {'success': False, 'error': f'Document {document_id} non trouvé'}
    except Exception as e:
        logger.error(f"❌ Erreur annotation: {e}")
        return {'success': False, 'error': str(e)}


def _save_annotations(document: Document, annotations: List[Dict]) -> int:
    """Sauvegarde les annotations avec gestion d'erreurs"""
    saved_count = 0

    try:
        from annotation.models import Annotation, EntityType
        from accounts.models import User

        # Utilisateur système
        system_user = User.objects.filter(username='system').first()
        if not system_user:
            system_user = User.objects.filter(is_superuser=True).first()

        if not system_user:
            logger.warning("⚠️ Aucun utilisateur système pour annotations")
            return 0

        # Supprimer anciennes annotations automatiques
        Annotation.objects.filter(document=document, is_automatic=True).delete()

        for ann_data in annotations:
            try:
                if not ann_data.get('text') or not ann_data.get('entity_type'):
                    continue

                entity_type, _ = EntityType.objects.get_or_create(
                    name=ann_data['entity_type'],
                    defaults={
                        'color': '#007bff',
                        'description': f'Entité {ann_data["entity_type"]} détectée automatiquement'
                    }
                )

                Annotation.objects.create(
                    document=document,
                    entity_type=entity_type,
                    text=ann_data['text'][:255],
                    start_position=ann_data.get('start_position', 0),
                    end_position=ann_data.get('end_position', 0),
                    confidence_score=min(ann_data.get('confidence_score', 0.7), 1.0),
                    created_by=system_user,
                    is_automatic=True
                )
                saved_count += 1

            except Exception as e:
                logger.warning(f"⚠️ Erreur annotation '{ann_data.get('text', '')}': {e}")
                continue

    except ImportError:
        logger.warning("⚠️ Module annotation non disponible")
    except Exception as e:
        logger.error(f"❌ Erreur générale annotations: {e}")

    return saved_count