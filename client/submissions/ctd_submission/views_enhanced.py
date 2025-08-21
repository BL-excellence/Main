
# ctd_submission/views_enhanced.py
# Vues améliorées pour l'éditeur avancé avec table des matières

from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, HttpResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.db import transaction
import json
import logging
import re
from typing import Dict, List, Optional

from .models import Document, TemplateField, DocumentVersion, AIAnalysisResult
from .utils import DocumentProcessor, CTDAnalyzer, IntelligentCopilot

logger = logging.getLogger(__name__)


@login_required
def document_advanced_editor_enhanced(request, document_id):
    """
    Vue améliorée pour l'éditeur avancé avec génération automatique de table des matières
    """
    document = get_object_or_404(Document, id=document_id, submission__created_by=request.user)

    # Extraire le contenu si nécessaire
    if not document.content_extracted:
        processor = DocumentProcessor()
        extracted_content = processor.extract_content(document)
        if extracted_content:
            document.content_extracted = extracted_content
            document.save()

    # Préparer le contenu avec amélioration de la structure
    content = document.content_extracted or {}
    enhanced_content = enhance_content_structure(content, document.document_type)

    # Générer la table des matières
    toc_data = generate_document_toc(enhanced_content, document.document_type)

    # Récupérer les métadonnées du document
    document_stats = get_document_statistics(document)

    context = {
        'document': document,
        'content': enhanced_content,
        'toc_data': toc_data,
        'document_stats': document_stats,
        'template_fields': TemplateField.objects.filter(document=document),
        'copilot_enabled': True,
        'has_extracted_content': bool(enhanced_content and enhanced_content.get('extracted', False)),
        'editing_modes': get_available_editing_modes(document.document_type),
    }

    return render(request, 'ctd_submission/document_advanced_editor.html', context)


def enhance_content_structure(content: Dict, document_type: str) -> Dict:
    """
    Améliore la structure du contenu pour un meilleur affichage
    """
    if not content or not content.get('extracted'):
        return content

    enhanced = content.copy()

    if document_type == 'pdf':
        enhanced = enhance_pdf_structure(enhanced)
    elif document_type == 'docx':
        enhanced = enhance_docx_structure(enhanced)
    elif document_type == 'xlsx':
        enhanced = enhance_xlsx_structure(enhanced)

    return enhanced


def enhance_pdf_structure(content: Dict) -> Dict:
    """
    Améliore la structure des documents PDF
    """
    if 'text' in content:
        text = content['text']

        # Détecter les titres et sections
        lines = text.split('\n')
        structured_content = []
        current_section = None

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Détecter les titres (heuristiques)
            if is_likely_heading(line):
                if current_section:
                    structured_content.append(current_section)

                level = detect_heading_level(line)
                current_section = {
                    'type': 'heading',
                    'level': level,
                    'text': line,
                    'content': []
                }
            elif current_section:
                current_section['content'].append({
                    'type': 'paragraph',
                    'text': line
                })

        if current_section:
            structured_content.append(current_section)

        content['structured'] = structured_content

        # Générer le HTML amélioré
        content['html'] = generate_enhanced_pdf_html(structured_content)

    return content


def enhance_docx_structure(content: Dict) -> Dict:
    """
    Améliore la structure des documents Word
    """
    if 'paragraphs' in content:
        paragraphs = content['paragraphs']
        structured_content = []

        for i, para in enumerate(paragraphs):
            para_data = {
                'type': 'paragraph',
                'text': para,
                'id': f'word-para-{i}',
                'level': detect_paragraph_level(para)
            }

            # Détecter si c'est un titre
            if is_likely_heading(para):
                para_data['type'] = 'heading'
                para_data['level'] = detect_heading_level(para)

            structured_content.append(para_data)

        content['structured'] = structured_content
        content['html'] = generate_enhanced_docx_html(structured_content)

    return content


def enhance_xlsx_structure(content: Dict) -> Dict:
    """
    Améliore la structure des documents Excel
    """
    if 'sheets' in content:
        for sheet_idx, sheet in enumerate(content['sheets']):
            if 'data' in sheet:
                # Analyser la structure des données
                sheet['structure'] = analyze_excel_structure(sheet['data'])
                sheet['html'] = generate_enhanced_excel_html(sheet, sheet_idx)

    return content


def generate_document_toc(content: Dict, document_type: str) -> List[Dict]:
    """
    Génère une table des matières pour le document
    """
    toc_items = []

    if not content or not content.get('structured'):
        return generate_basic_toc(document_type)

    if document_type == 'pdf':
        toc_items = generate_pdf_toc(content['structured'])
    elif document_type == 'docx':
        toc_items = generate_docx_toc(content['structured'])
    elif document_type == 'xlsx':
        toc_items = generate_xlsx_toc(content)

    return toc_items


def generate_pdf_toc(structured_content: List[Dict]) -> List[Dict]:
    """
    Génère la TOC pour un PDF
    """
    toc_items = []

    for i, section in enumerate(structured_content):
        if section['type'] == 'heading':
            toc_items.append({
                'id': f'pdf-section-{i}',
                'text': section['text'],
                'level': section['level'],
                'type': 'heading',
                'icon': 'fas fa-bookmark' if section['level'] == 1 else 'fas fa-chevron-right'
            })

    return toc_items


def generate_docx_toc(structured_content: List[Dict]) -> List[Dict]:
    """
    Génère la TOC pour un document Word
    """
    toc_items = []

    for item in structured_content:
        if item['type'] == 'heading':
            toc_items.append({
                'id': item['id'],
                'text': item['text'],
                'level': item['level'],
                'type': 'heading',
                'icon': get_heading_icon(item['level'])
            })

    return toc_items


def generate_xlsx_toc(content: Dict) -> List[Dict]:
    """
    Génère la TOC pour un fichier Excel
    """
    toc_items = []

    if 'sheets' in content:
        for i, sheet in enumerate(content['sheets']):
            toc_items.append({
                'id': f'sheet-{i}',
                'text': sheet['name'],
                'level': 1,
                'type': 'sheet',
                'icon': 'fas fa-table'
            })

            # Ajouter les sections importantes dans la feuille
            if 'structure' in sheet:
                for section in sheet['structure'].get('sections', []):
                    toc_items.append({
                        'id': f'sheet-{i}-section-{section["row"]}',
                        'text': section['title'],
                        'level': 2,
                        'type': 'section',
                        'icon': 'fas fa-list'
                    })

    return toc_items


def generate_basic_toc(document_type: str) -> List[Dict]:
    """
    Génère une TOC basique quand la structure n'est pas détectée
    """
    basic_items = {
        'pdf': [
            {'id': 'start', 'text': 'Début du document', 'level': 1, 'icon': 'fas fa-play'},
            {'id': 'content', 'text': 'Contenu principal', 'level': 1, 'icon': 'fas fa-file-text'}
        ],
        'docx': [
            {'id': 'document', 'text': 'Document Word', 'level': 1, 'icon': 'fas fa-file-word'},
            {'id': 'content', 'text': 'Contenu', 'level': 2, 'icon': 'fas fa-paragraph'}
        ],
        'xlsx': [
            {'id': 'workbook', 'text': 'Classeur Excel', 'level': 1, 'icon': 'fas fa-file-excel'},
            {'id': 'sheets', 'text': 'Feuilles de calcul', 'level': 2, 'icon': 'fas fa-table'}
        ]
    }

    return basic_items.get(document_type, [])


def is_likely_heading(text: str) -> bool:
    """
    Détermine si un texte est probablement un titre
    """
    text = text.strip()

    # Heuristiques pour détecter les titres
    heading_indicators = [
        len(text) < 100,  # Titres généralement courts
        text.isupper(),  # Tout en majuscules
        re.match(r'^\d+\.', text),  # Commence par un numéro
        re.match(r'^[IVX]+\.', text),  # Numérotation romaine
        any(word in text.lower() for word in [
            'chapitre', 'chapter', 'partie', 'part', 'section',
            'annexe', 'appendix', 'figure', 'tableau', 'table'
        ])
    ]

    return sum(heading_indicators) >= 2


def detect_heading_level(text: str) -> int:
    """
    Détermine le niveau d'un titre (1-6)
    """
    text = text.strip()

    # Détecter par numérotation
    if re.match(r'^\d+\.', text):
        parts = text.split('.')
        return min(len([p for p in parts if p.strip().isdigit()]), 6)

    # Détecter par longueur et style
    if len(text) < 30 and text.isupper():
        return 1
    elif len(text) < 50:
        return 2
    else:
        return 3


def detect_paragraph_level(text: str) -> int:
    """
    Détermine le niveau d'indentation d'un paragraphe
    """
    leading_spaces = len(text) - len(text.lstrip())
    return min(leading_spaces // 4, 4)  # 4 espaces = 1 niveau


def analyze_excel_structure(data: List[List]) -> Dict:
    """
    Analyse la structure d'une feuille Excel
    """
    if not data:
        return {'sections': []}

    sections = []
    current_section = None

    for row_idx, row in enumerate(data):
        if not any(cell for cell in row if str(cell).strip()):
            continue  # Ligne vide

        # Détecter les en-têtes de section
        first_cell = str(row[0]).strip() if row else ""
        if first_cell and is_likely_heading(first_cell):
            if current_section:
                sections.append(current_section)

            current_section = {
                'title': first_cell,
                'row': row_idx,
                'data_rows': []
            }
        elif current_section:
            current_section['data_rows'].append(row_idx)

    if current_section:
        sections.append(current_section)

    return {'sections': sections}


def generate_enhanced_pdf_html(structured_content: List[Dict]) -> str:
    """
    Génère du HTML amélioré pour le PDF
    """
    html_parts = ['<div class="pdf-content-enhanced">']

    for i, section in enumerate(structured_content):
        if section['type'] == 'heading':
            level = section['level']
            html_parts.append(f'''
                <h{level} id="pdf-section-{i}" class="editable-element heading-{level}" 
                          contenteditable="true" data-element-id="pdf-heading-{i}">
                    {section['text']}
                </h{level}>
            ''')

            # Ajouter le contenu de la section
            for j, content_item in enumerate(section['content']):
                if content_item['type'] == 'paragraph':
                    html_parts.append(f'''
                        <p class="editable-element" contenteditable="true" 
                           data-element-id="pdf-para-{i}-{j}">
                            {content_item['text']}
                        </p>
                    ''')

    html_parts.append('</div>')
    return '\n'.join(html_parts)


def generate_enhanced_docx_html(structured_content: List[Dict]) -> str:
    """
    Génère du HTML amélioré pour Word
    """
    html_parts = ['<div class="word-content-enhanced">']

    for item in structured_content:
        if item['type'] == 'heading':
            level = item['level']
            html_parts.append(f'''
                <h{level} id="{item['id']}" class="editable-element heading-{level}" 
                          contenteditable="true" data-element-id="{item['id']}">
                    {item['text']}
                </h{level}>
            ''')
        else:
            html_parts.append(f'''
                <p id="{item['id']}" class="editable-element" 
                   contenteditable="true" data-element-id="{item['id']}">
                    {item['text']}
                </p>
            ''')

    html_parts.append('</div>')
    return '\n'.join(html_parts)


def generate_enhanced_excel_html(sheet: Dict, sheet_idx: int) -> str:
    """
    Génère du HTML amélioré pour Excel
    """
    html_parts = [f'<div class="excel-sheet-enhanced" data-sheet="{sheet_idx}">']

    # Titre de la feuille
    html_parts.append(f'''
        <h5 class="sheet-title" id="sheet-{sheet_idx}">
            <i class="fas fa-table me-2"></i>{sheet['name']}
        </h5>
    ''')

    # Structure des données
    if 'structure' in sheet and sheet['structure']['sections']:
        for section in sheet['structure']['sections']:
            html_parts.append(f'''
                <h6 id="sheet-{sheet_idx}-section-{section['row']}" 
                    class="section-title">
                    {section['title']}
                </h6>
            ''')

    # Tableau des données
    html_parts.append('<div class="table-responsive">')
    html_parts.append('<table class="editable-table excel-table">')

    for row_idx, row in enumerate(sheet.get('data', [])):
        html_parts.append('<tr>')
        for col_idx, cell in enumerate(row):
            tag = 'th' if row_idx == 0 else 'td'
            cell_value = str(cell) if cell is not None else ''
            html_parts.append(f'''
                <{tag} class="editable-cell" contenteditable="true"
                       data-row="{row_idx}" data-col="{col_idx}" 
                       data-sheet="{sheet_idx}">
                    {cell_value}
                </{tag}>
            ''')
        html_parts.append('</tr>')

    html_parts.extend(['</table>', '</div>', '</div>'])
    return '\n'.join(html_parts)


def get_heading_icon(level: int) -> str:
    """
    Retourne l'icône appropriée selon le niveau de titre
    """
    icons = {
        1: 'fas fa-bookmark',
        2: 'fas fa-chevron-right',
        3: 'fas fa-circle',
        4: 'fas fa-dot-circle',
        5: 'fas fa-minus',
        6: 'fas fa-minus'
    }
    return icons.get(level, 'fas fa-circle')


def get_document_statistics(document) -> Dict:
    """
    Calcule les statistiques du document
    """
    stats = {
        'word_count': 0,
        'character_count': 0,
        'paragraph_count': 0,
        'heading_count': 0,
        'table_count': 0
    }

    if document.content_extracted:
        content = document.content_extracted

        if 'text' in content:
            text = content['text']
            stats['word_count'] = len(text.split())
            stats['character_count'] = len(text)
            stats['paragraph_count'] = len([p for p in text.split('\n\n') if p.strip()])

        if 'structured' in content:
            structured = content['structured']
            stats['heading_count'] = len([s for s in structured if s.get('type') == 'heading'])

        if 'tables' in content:
            stats['table_count'] = len(content['tables'])

    return stats


def get_available_editing_modes(document_type: str) -> List[Dict]:
    """
    Retourne les modes d'édition disponibles selon le type de document
    """
    base_modes = [
        {'id': 'text', 'name': 'Texte', 'icon': 'fas fa-edit', 'description': 'Édition du texte'},
        {'id': 'visual', 'name': 'Visuel', 'icon': 'fas fa-paint-brush', 'description': 'Mise en forme visuelle'},
        {'id': 'structure', 'name': 'Structure', 'icon': 'fas fa-sitemap', 'description': 'Organisation du document'}
    ]

    # Modes spécifiques selon le type
    if document_type == 'xlsx':
        base_modes.append({
            'id': 'data', 'name': 'Données', 'icon': 'fas fa-table',
            'description': 'Analyse des données'
        })
    elif document_type == 'pdf':
        base_modes.append({
            'id': 'annotation', 'name': 'Annotation', 'icon': 'fas fa-comment',
            'description': 'Annotations et commentaires'
        })

    return base_modes


@csrf_exempt
@login_required
def get_document_toc(request, document_id):
    """
    API pour récupérer la table des matières d'un document
    """
    if request.method == 'GET':
        try:
            document = get_object_or_404(Document, id=document_id, submission__created_by=request.user)

            if not document.content_extracted:
                return JsonResponse({
                    'success': False,
                    'message': 'Contenu non extrait'
                })

            toc_data = generate_document_toc(document.content_extracted, document.document_type)

            return JsonResponse({
                'success': True,
                'toc': toc_data,
                'document_type': document.document_type
            })

        except Exception as e:
            logger.error(f"Erreur génération TOC: {e}")
            return JsonResponse({
                'success': False,
                'message': str(e)
            })

    return JsonResponse({'success': False, 'message': 'Méthode non autorisée'})


@csrf_exempt
@login_required
def update_document_structure(request, document_id):
    """
    Met à jour la structure du document après modifications
    """
    if request.method == 'POST':
        try:
            document = get_object_or_404(Document, id=document_id, submission__created_by=request.user)
            data = json.loads(request.body)

            # Mettre à jour la structure
            new_structure = data.get('structure', {})

            if document.content_extracted:
                document.content_extracted['user_structure'] = new_structure
                document.content_extracted['structure_updated_at'] = timezone.now().isoformat()
                document.save()

            return JsonResponse({
                'success': True,
                'message': 'Structure mise à jour'
            })

        except Exception as e:
            logger.error(f"Erreur mise à jour structure: {e}")
            return JsonResponse({
                'success': False,
                'message': str(e)
            })

    return JsonResponse({'success': False, 'message': 'Méthode non autorisée'})


@csrf_exempt
@login_required
def smart_suggestions_enhanced(request, document_id):
    """
    Génère des suggestions intelligentes basées sur le contexte
    """
    if request.method == 'POST':
        try:
            document = get_object_or_404(Document, id=document_id, submission__created_by=request.user)
            data = json.loads(request.body)

            element_id = data.get('element_id')
            content = data.get('content')
            context = data.get('context', {})

            # Utiliser le Copilot intelligent
            copilot = IntelligentCopilot()
            suggestions = copilot.get_enhanced_suggestions(
                document, element_id, content, context
            )

            return JsonResponse({
                'success': True,
                'suggestions': suggestions,
                'timestamp': timezone.now().isoformat()
            })

        except Exception as e:
            logger.error(f"Erreur suggestions: {e}")
            return JsonResponse({
                'success': False,
                'message': str(e)
            })

    return JsonResponse({'success': False, 'message': 'Méthode non autorisée'})