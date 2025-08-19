import logging
import re
from functools import reduce
from operator import or_ as OR
from typing import List

from django.db.models import Q
from rapidfuzz import process, fuzz

from client.products.models import Product
from rawdocs.models import RawDocument
from chatbot.utils.matching import find_best_product, find_best_document, extract_product_name

logger = logging.getLogger(__name__)

# -----------------------------
# Helpers
# -----------------------------

def _model_field_names(model) -> set[str]:
    return {f.name for f in model._meta.get_fields()}


def _best_product_from_question(question: str, produits_qs):
    """Robustly identify a product from a free‑text question.
    1) existing extract_product_name()
    2) quoted text
    3) fuzzy full‑question → product names (partial & token_set)
    """
    # 1) existing helper
    name = (extract_product_name(question, produits_qs) or "").strip()
    prod = find_best_product(name, produits_qs) if name else None
    if prod:
        return prod

    # 2) quoted candidate(s)
    quoted = re.findall(r'[\"'"'"'«»“”‘’]([^\"'"'"'«»“”‘’]+)[\"'"'"'«»“”‘’]', question or "")
    for q in quoted:
        p = find_best_product(q.strip(), produits_qs)
        if p:
            return p

    # 3) fuzzy against all names (tolerates extra words/typos like "tabaco")
    names: List[str] = [p.name for p in produits_qs]
    if not names:
        return None
    cand1 = process.extractOne(question, names, scorer=fuzz.partial_ratio)
    cand2 = process.extractOne(question, names, scorer=fuzz.token_set_ratio)
    best = None
    for c in (cand1, cand2):
        if c and (best is None or c[1] > best[1]):
            best = c
    if best and best[1] >= 60:
        return produits_qs.filter(name__iexact=best[0]).first()
    return None

# -----------------------------
# Public API
# -----------------------------

def get_products_linked_to_document(question: str, docs_qs) -> str:
    """Répond : "À quels produits ce document est‑il lié ?"

    Handles both schemas:
    - RawDocument has FK/M2M → Product (fields: product / products)
    - Product has FK → RawDocument (field: source_document)
    """
    doc = find_best_document(question, docs_qs)
    if not doc:
        return "Je n’ai pas trouvé ce document. Peux-tu préciser le titre ?"

    product_fields = _model_field_names(Product)
    document_fields = _model_field_names(RawDocument)

    # 1) Direct relation from RawDocument → Product
    prods = Product.objects.none()
    if 'product' in document_fields:
        # One product per document
        p = getattr(doc, 'product', None)
        if p:
            prods = Product.objects.filter(pk=p.pk)
    if not prods.exists() and 'products' in document_fields:
        try:
            prods = getattr(doc, 'products').all()
        except Exception:
            pass

    # 2) Reverse relation from Product → RawDocument via FK
    if not prods.exists() and 'source_document' in product_fields:
        prods = Product.objects.filter(source_document=doc)

    if not prods.exists():
        return f"Aucun produit n’est associé au document « {doc.title} »."

    noms = ", ".join(p.name for p in prods)
    return f"Produits associés au document « {doc.title} » : {noms}."


def get_document_linked_to_product(question: str, produits_qs) -> str:
    """Questions du type : "<produit> est‑il lié à/avec un document ?"

    Supports schemas:
    - RawDocument has FK/M2M → Product (fields: product / products)
    - Product has FK → RawDocument (field: source_document)
    """
    logger.info(f"[Relation] Question reçue pour produit→document : {question}")

    product = _best_product_from_question(question, produits_qs)
    logger.info(f"[Relation] Produit identifié : {getattr(product, 'name', None)}")

    if not product:
        return "Je n’ai pas trouvé ce produit. Peux-tu préciser le nom ?"

    document_fields = _model_field_names(RawDocument)
    product_fields = _model_field_names(Product)

    # 1) Product has FK → RawDocument (e.g., Product.source_document)
    if 'source_document' in product_fields:
        doc = getattr(product, 'source_document', None)
        if doc:
            dtype = getattr(doc, 'doc_type', None) or 'Type inconnu'
            return f"Le produit « {product.name} » est lié au document « {doc.title} » ({dtype})."

    # 2) RawDocument has FK/M2M → Product
    qs = RawDocument.objects.filter(is_validated=True)
    filters = []
    if 'product' in document_fields:
        filters.append(Q(product=product) | Q(product__id=product.id))
    if 'products' in document_fields:
        filters.append(Q(products=product) | Q(products__id=product.id))

    if filters:
        qs = qs.filter(reduce(OR, filters)).distinct()
    else:
        # 3) Fallback: textual match on title/context when no relation fields
        qs = qs.filter(Q(title__icontains=product.name) | Q(context__icontains=product.name)).distinct()

    if not qs.exists():
        return f"Aucun document validé n’est associé au produit « {product.name} »."

    lines = [f"Le produit « {product.name} » est lié aux documents suivants :"]
    for d in qs:
        dtype = getattr(d, 'doc_type', None) or 'Type inconnu'
        lines.append(f"- {d.title} ({dtype})")
    return "\n".join(lines)
