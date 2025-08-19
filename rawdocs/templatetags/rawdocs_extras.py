import os
import json
from django import template
from django.utils.safestring import mark_safe

register = template.Library()

@register.filter
def basename(value):
    """Renvoie le nom de fichier à partir d'un chemin."""
    return os.path.basename(value)

@register.filter
def format_json(value):
    """
    Formate un JSON pour un affichage lisible avec indentation.
    Utilisé pour afficher les JSON d'annotations de manière structurée.
    """
    if not value:
        return ""
    
    try:
        # Si c'est déjà un objet Python, le convertir en JSON
        if isinstance(value, (dict, list)):
            formatted_json = json.dumps(value, indent=2, ensure_ascii=False)
        else:
            # Si c'est une chaîne, la parser puis la reformater
            parsed_json = json.loads(str(value))
            formatted_json = json.dumps(parsed_json, indent=2, ensure_ascii=False)
        
        return mark_safe(formatted_json)
    except (json.JSONDecodeError, TypeError, ValueError):
        # En cas d'erreur, retourner la valeur originale
        return value