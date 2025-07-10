from django import template

register = template.Library()

@register.filter
def mul(value, arg):
    """Multiplie la valeur par l'argument"""
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return 0

@register.filter
def percentage(value):
    """Convertit une valeur décimale en pourcentage"""
    try:
        return int(float(value) * 100)
    except (ValueError, TypeError):
        return 0