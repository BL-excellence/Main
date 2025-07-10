import os
from django import template

register = template.Library()

@register.filter
def basename(value):
    """Renvoie le nom de fichier à partir d’un chemin."""
    return os.path.basename(value)

@register.filter
def get_item(dictionary, key):
    """Get item from dictionary by key"""
    if isinstance(dictionary, dict):
        return dictionary.get(key, '')
    return ''
