import pdfplumber
import pandas as pd
from PIL import Image
import fitz  # PyMuPDF for image extraction
import io
import base64
import os
from typing import List, Dict, Tuple, Optional
import re


class TableImageExtractor:
    """
    Extracteur avancé pour tableaux et images depuis PDF
    Préserve la structure des tableaux et extrait les images
    """
    
    def __init__(self, pdf_path: str):
        self.pdf_path = pdf_path
        self.tables = []
        self.images = []
        
    def extract_tables_with_structure(self) -> List[Dict]:
        """
        Extrait les tableaux en préservant leur structure HTML
        """
        tables_data = []
        
        with pdfplumber.open(self.pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                # Extraire les tableaux de la page
                page_tables = page.extract_tables()
                
                for table_num, table in enumerate(page_tables, 1):
                    if table and len(table) > 1:  # Vérifier qu'il y a au moins 2 lignes
                        # Convertir en DataFrame pour faciliter la manipulation
                        df = pd.DataFrame(table[1:], columns=table[0])
                        
                        # Nettoyer les données
                        df = df.fillna('')
                        
                        # Générer HTML stylisé
                        html_table = self._generate_styled_html_table(df, page_num, table_num)
                        
                        table_info = {
                            'page': page_num,
                            'table_number': table_num,
                            'html': html_table,
                            'raw_data': table,
                            'dataframe': df,
                            'rows': len(df),
                            'columns': len(df.columns)
                        }
                        
                        tables_data.append(table_info)
                        
        self.tables = tables_data
        return tables_data
    
    def _generate_styled_html_table(self, df: pd.DataFrame, page_num: int, table_num: int) -> str:
        """
        Génère un tableau HTML stylisé avec CSS moderne
        """
        table_id = f"table_page_{page_num}_num_{table_num}"
        
        html = f"""
        <div class="table-container" id="{table_id}">
            <div class="table-header">
                <h4 class="table-title">
                    <i class="fas fa-table"></i> Tableau {table_num} (Page {page_num})
                </h4>
                <div class="table-info">
                    <span class="badge badge-info">{len(df)} lignes</span>
                    <span class="badge badge-secondary">{len(df.columns)} colonnes</span>
                </div>
            </div>
            <div class="table-responsive">
                <table class="table table-bordered table-hover table-striped extracted-table">
                    <thead class="table-dark">
                        <tr>
        """
        
        # En-têtes
        for col in df.columns:
            html += f'<th class="table-header-cell">{self._clean_cell_text(str(col))}</th>'
        
        html += """
                        </tr>
                    </thead>
                    <tbody>
        """
        
        # Lignes de données
        for _, row in df.iterrows():
            html += '<tr>'
            for cell in row:
                cleaned_cell = self._clean_cell_text(str(cell))
                html += f'<td class="table-data-cell">{cleaned_cell}</td>'
            html += '</tr>'
        
        html += """
                    </tbody>
                </table>
            </div>
        </div>
        """
        
        return html
    
    def _clean_cell_text(self, text: str) -> str:
        """
        Nettoie le texte des cellules
        """
        if not text or text == 'nan':
            return ''
        
        # Supprimer les espaces multiples
        text = re.sub(r'\s+', ' ', text.strip())
        
        # Remplacer les caractères spéciaux
        text = text.replace('\n', '<br>')
        
        return text
    
    def extract_images(self) -> List[Dict]:
        """
        Extrait les images du PDF avec métadonnées
        """
        images_data = []
        
        try:
            # Utiliser PyMuPDF pour l'extraction d'images
            doc = fitz.open(self.pdf_path)
            
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                image_list = page.get_images()
                
                for img_index, img in enumerate(image_list):
                    try:
                        # Extraire l'image
                        xref = img[0]
                        pix = fitz.Pixmap(doc, xref)
                        
                        if pix.n - pix.alpha < 4:  # GRAY ou RGB
                            # Convertir en PNG
                            img_data = pix.tobytes("png")
                            
                            # Encoder en base64 pour l'affichage web
                            img_base64 = base64.b64encode(img_data).decode()
                            
                            # Métadonnées de l'image
                            img_info = {
                                'page': page_num + 1,
                                'image_number': img_index + 1,
                                'width': pix.width,
                                'height': pix.height,
                                'base64': img_base64,
                                'format': 'PNG',
                                'size_kb': len(img_data) // 1024,
                                'html': self._generate_image_html(img_base64, page_num + 1, img_index + 1, pix.width, pix.height)
                            }
                            
                            images_data.append(img_info)
                        
                        pix = None
                        
                    except Exception as e:
                        print(f"Erreur extraction image {img_index} page {page_num + 1}: {e}")
                        continue
            
            doc.close()
            
        except Exception as e:
            print(f"Erreur lors de l'extraction des images: {e}")
        
        self.images = images_data
        return images_data
    
    def _generate_image_html(self, img_base64: str, page_num: int, img_num: int, width: int, height: int) -> str:
        """
        Génère le HTML pour afficher une image extraite
        """
        image_id = f"image_page_{page_num}_num_{img_num}"
        
        html = f"""
        <div class="image-container" id="{image_id}">
            <div class="image-header">
                <h4 class="image-title">
                    <i class="fas fa-image"></i> Image {img_num} (Page {page_num})
                </h4>
                <div class="image-info">
                    <span class="badge badge-info">{width}x{height}px</span>
                    <button class="btn btn-sm btn-outline-primary download-image" data-image="{img_base64}" data-filename="image_p{page_num}_n{img_num}.png">
                        <i class="fas fa-download"></i> Télécharger
                    </button>
                </div>
            </div>
            <div class="image-content">
                <img src="data:image/png;base64,{img_base64}" 
                     alt="Image {img_num} de la page {page_num}" 
                     class="extracted-image img-fluid"
                     style="max-width: 100%; height: auto; border: 1px solid #ddd; border-radius: 4px;">
            </div>
        </div>
        """
        
        return html
    
    def get_extraction_summary(self) -> Dict:
        """
        Retourne un résumé de l'extraction
        """
        return {
            'total_tables': len(self.tables),
            'total_images': len(self.images),
            'tables_by_page': self._group_by_page(self.tables),
            'images_by_page': self._group_by_page(self.images),
            'total_table_rows': sum(table['rows'] for table in self.tables),
            'total_image_size_kb': sum(img['size_kb'] for img in self.images)
        }
    
    def _group_by_page(self, items: List[Dict]) -> Dict[int, int]:
        """
        Groupe les éléments par page
        """
        grouped = {}
        for item in items:
            page = item['page']
            grouped[page] = grouped.get(page, 0) + 1
        return grouped
    
    def export_tables_to_excel(self, output_path: str) -> bool:
        """
        Exporte tous les tableaux vers un fichier Excel
        """
        try:
            with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
                for table in self.tables:
                    sheet_name = f"Page_{table['page']}_Table_{table['table_number']}"
                    table['dataframe'].to_excel(writer, sheet_name=sheet_name, index=False)
            
            return True
        except Exception as e:
            print(f"Erreur lors de l'export Excel: {e}")
            return False
    
    def get_combined_html(self) -> str:
        """
        Retourne le HTML combiné de tous les tableaux et images
        """
        html_parts = []
        
        # Ajouter le CSS
        html_parts.append(self._get_css_styles())
        
        # Combiner tableaux et images par page
        all_items = []
        
        for table in self.tables:
            all_items.append({
                'type': 'table',
                'page': table['page'],
                'number': table['table_number'],
                'html': table['html']
            })
        
        for image in self.images:
            all_items.append({
                'type': 'image',
                'page': image['page'],
                'number': image['image_number'],
                'html': image['html']
            })
        
        # Trier par page puis par numéro
        all_items.sort(key=lambda x: (x['page'], x['number']))
        
        # Générer le HTML final
        current_page = None
        for item in all_items:
            if item['page'] != current_page:
                if current_page is not None:
                    html_parts.append('</div>')  # Fermer la page précédente
                
                current_page = item['page']
                html_parts.append(f"""
                <div class="page-section">
                    <h3 class="page-title">
                        <i class="fas fa-file-alt"></i> Page {current_page}
                    </h3>
                """)
            
            html_parts.append(item['html'])
        
        if current_page is not None:
            html_parts.append('</div>')  # Fermer la dernière page
        
        # Ajouter le JavaScript
        html_parts.append(self._get_javascript())
        
        return '\n'.join(html_parts)
    
    def _get_css_styles(self) -> str:
        """
        Retourne les styles CSS pour l'affichage
        """
        return """
        <style>
        .page-section {
            margin-bottom: 2rem;
            padding: 1rem;
            background: #f8f9fa;
            border-radius: 8px;
            border-left: 4px solid #007bff;
        }
        
        .page-title {
            color: #495057;
            margin-bottom: 1.5rem;
            font-size: 1.5rem;
            border-bottom: 2px solid #dee2e6;
            padding-bottom: 0.5rem;
        }
        
        .table-container, .image-container {
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            margin-bottom: 1.5rem;
            overflow: hidden;
        }
        
        .table-header, .image-header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 1rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        .table-title, .image-title {
            margin: 0;
            font-size: 1.1rem;
            font-weight: 600;
        }
        
        .table-info, .image-info {
            display: flex;
            gap: 0.5rem;
        }
        
        .badge {
            padding: 0.3rem 0.6rem;
            border-radius: 12px;
            font-size: 0.75rem;
            font-weight: 500;
        }
        
        .badge-info {
            background-color: #17a2b8;
            color: white;
        }
        
        .badge-secondary {
            background-color: #6c757d;
            color: white;
        }
        
        .table-responsive {
            padding: 1rem;
        }
        
        .extracted-table {
            margin-bottom: 0;
            font-size: 0.9rem;
        }
        
        .extracted-table th {
            background-color: #343a40 !important;
            color: white;
            font-weight: 600;
            border: 1px solid #454d55;
            padding: 0.75rem;
            text-align: center;
            vertical-align: middle;
        }
        
        .extracted-table td {
            border: 1px solid #dee2e6;
            padding: 0.75rem;
            vertical-align: middle;
            background-color: white;
        }
        
        .extracted-table tbody tr:hover {
            background-color: #f1f3f4;
        }
        
        .extracted-table tbody tr:nth-child(even) {
            background-color: #f8f9fa;
        }
        
        .image-content {
            padding: 1rem;
            text-align: center;
        }
        
        .extracted-image {
            max-width: 100%;
            height: auto;
            border: 2px solid #dee2e6;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }
        
        .download-image {
            color: white;
            border-color: rgba(255,255,255,0.3);
            transition: all 0.3s ease;
        }
        
        .download-image:hover {
            background-color: rgba(255,255,255,0.1);
            border-color: white;
            color: white;
        }
        
        @media (max-width: 768px) {
            .table-header, .image-header {
                flex-direction: column;
                gap: 0.5rem;
                text-align: center;
            }
            
            .table-info, .image-info {
                justify-content: center;
            }
        }
        </style>
        """
    
    def _get_javascript(self) -> str:
        """
        Retourne le JavaScript pour les fonctionnalités interactives
        """
        return """
        <script>
        document.addEventListener('DOMContentLoaded', function() {
            // Fonction de téléchargement d'images
            document.querySelectorAll('.download-image').forEach(button => {
                button.addEventListener('click', function() {
                    const imageData = this.getAttribute('data-image');
                    const filename = this.getAttribute('data-filename');
                    
                    // Créer un lien de téléchargement
                    const link = document.createElement('a');
                    link.href = 'data:image/png;base64,' + imageData;
                    link.download = filename;
                    link.click();
                });
            });
            
            // Ajout d'animations au survol des tableaux
            document.querySelectorAll('.extracted-table tbody tr').forEach(row => {
                row.addEventListener('mouseenter', function() {
                    this.style.transform = 'scale(1.01)';
                    this.style.transition = 'transform 0.2s ease';
                });
                
                row.addEventListener('mouseleave', function() {
                    this.style.transform = 'scale(1)';
                });
            });
        });
        </script>
        """