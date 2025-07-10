from utils.utils import EnhancedDocumentExtractor
from dataclasses import asdict  # ✅ Import nécessaire
import logging
import os
from dataclasses import is_dataclass

logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(message)s')

# Initialise une seule fois l’extracteur
extractor = EnhancedDocumentExtractor()

def full_extraction_pipeline(file_path, source_url):
    """
    Pipeline : extraction via EnhancedDocumentExtractor
    + ajout des tableaux texte dans le champ "tables".
    """
    logging.info(f"🔍 Début extraction : {os.path.basename(file_path)}")

    # Utilise la classe d'extraction
    metadata_obj = extractor.extract_enhanced_metadata(file_path, source_url)

    # Convertit en dictionnaire (DocumentMetadata → dict)
    metadata_dict = {
        "title": getattr(metadata_obj, "title", ""),
        "type": getattr(metadata_obj, "type", ""),
        "publication_date": getattr(metadata_obj, "publication_date", ""),
        "version": getattr(metadata_obj, "version", ""),
        "source": getattr(metadata_obj, "source", ""),
        "context": getattr(metadata_obj, "context", ""),
        "country": getattr(metadata_obj, "country", ""),
        "language": getattr(metadata_obj, "language", ""),
        "url_source": getattr(metadata_obj, "url_source", ""),
        "ich_step": getattr(metadata_obj, "ich_step", ""),
        "regulatory_pathway": getattr(metadata_obj, "regulatory_pathway", ""),
        "therapeutic_area": getattr(metadata_obj, "therapeutic_area", ""),
        "supersedes": getattr(metadata_obj, "supersedes", ""),
        "effective_date": getattr(metadata_obj, "effective_date", ""),
        "keywords": getattr(metadata_obj, "keywords", []),
        "references": getattr(metadata_obj, "references", []),
        "structure": asdict(metadata_obj.structure) if hasattr(metadata_obj, "structure") and is_dataclass(metadata_obj.structure) else {},
        "quality": asdict(metadata_obj.quality) if hasattr(metadata_obj, "quality") and is_dataclass(metadata_obj.quality) else {},

    }


    # Ajout des tableaux texte dans un champ "tables"
    metadata_dict["tables"] = [
        table.get('content', f"(table {table.get('id', '?')})") 
        for table in metadata_obj.structure.tables
    ]

    return metadata_dict
