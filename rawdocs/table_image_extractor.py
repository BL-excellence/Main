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
                <div class="header-content">
                    <div class="title-section">
                        <div class="icon-wrapper">
                            <i class="fas fa-table"></i>
                        </div>
                        <div class="title-text">
                            <h3 class="table-title">Tableau {table_num}</h3>
                            <p class="table-subtitle">Page {page_num} • Extraction automatique</p>
                        </div>
                    </div>
                    <div class="stats-section">
                        <div class="stat-item">
                            <div class="stat-number">{len(df)}</div>
                            <div class="stat-label">Lignes</div>
                        </div>
                        <div class="stat-divider"></div>
                        <div class="stat-item">
                            <div class="stat-number">{len(df.columns)}</div>
                            <div class="stat-label">Colonnes</div>
                        </div>
                    </div>
                </div>
            </div>
            <div class="table-responsive">
                <table class="extracted-table">
                    <thead>
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
                <div class="header-content">
                    <div class="title-section">
                        <div class="icon-wrapper">
                            <i class="fas fa-image"></i>
                        </div>
                        <div class="title-text">
                            <h3 class="image-title">Image {img_num}</h3>
                            <p class="image-subtitle">Page {page_num} • {width}×{height}px • {len(img_base64)//1024}KB</p>
                        </div>
                    </div>
                    <div class="actions-section">
                        <button class="download-btn" data-image="{img_base64}" data-filename="image_p{page_num}_n{img_num}.png">
                            <i class="fas fa-download"></i>
                            <span>Télécharger</span>
                        </button>
                    </div>
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
                    <div class="page-header">
                        <div class="page-icon">
                            <i class="fas fa-file-pdf"></i>
                        </div>
                        <div class="page-info">
                            <h2 class="page-title">Page {current_page}</h2>
                            <p class="page-subtitle">Contenu extrait automatiquement</p>
                        </div>
                    </div>
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
        /* Variables CSS pour la cohérence */
        :root {
            --primary-color: #2563eb;
            --primary-dark: #1d4ed8;
            --secondary-color: #64748b;
            --success-color: #059669;
            --warning-color: #d97706;
            --danger-color: #dc2626;
            --light-bg: #f8fafc;
            --white: #ffffff;
            --gray-50: #f9fafb;
            --gray-100: #f3f4f6;
            --gray-200: #e5e7eb;
            --gray-300: #d1d5db;
            --gray-600: #4b5563;
            --gray-700: #374151;
            --gray-800: #1f2937;
            --gray-900: #111827;
            --shadow-sm: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
            --shadow-md: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
            --shadow-lg: 0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05);
            --shadow-xl: 0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04);
        }

        /* Reset et base */
        * {
            box-sizing: border-box;
        }

        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            line-height: 1.6;
            color: var(--gray-800);
            background: var(--light-bg);
        }

        /* Page Section */
        .page-section {
            margin-bottom: 3rem;
            background: var(--white);
            border-radius: 16px;
            box-shadow: var(--shadow-lg);
            overflow: hidden;
            border: 1px solid var(--gray-200);
        }

        .page-header {
            background: linear-gradient(135deg, var(--primary-color) 0%, var(--primary-dark) 100%);
            color: white;
            padding: 2rem;
            display: flex;
            align-items: center;
            gap: 1.5rem;
        }

        .page-icon {
            width: 60px;
            height: 60px;
            background: rgba(255, 255, 255, 0.2);
            border-radius: 16px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.5rem;
            backdrop-filter: blur(10px);
        }

        .page-info h2 {
            margin: 0;
            font-size: 2rem;
            font-weight: 700;
            letter-spacing: -0.025em;
        }

        .page-subtitle {
            margin: 0.5rem 0 0 0;
            opacity: 0.9;
            font-size: 1rem;
            font-weight: 400;
        }

        /* Container styles */
        .table-container, .image-container {
            background: var(--white);
            border-radius: 12px;
            box-shadow: var(--shadow-md);
            margin: 2rem;
            overflow: hidden;
            border: 1px solid var(--gray-200);
            transition: all 0.3s ease;
        }

        .table-container:hover, .image-container:hover {
            box-shadow: var(--shadow-xl);
            transform: translateY(-2px);
        }

        /* Header styles */
        .table-header, .image-header {
            background: linear-gradient(135deg, var(--gray-700) 0%, var(--gray-800) 100%);
            color: white;
            padding: 1.5rem;
        }

        .header-content {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 1rem;
        }

        .title-section {
            display: flex;
            align-items: center;
            gap: 1rem;
        }

        .icon-wrapper {
            width: 48px;
            height: 48px;
            background: rgba(255, 255, 255, 0.15);
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.25rem;
            backdrop-filter: blur(10px);
        }

        .title-text h3 {
            margin: 0;
            font-size: 1.25rem;
            font-weight: 700;
            letter-spacing: -0.025em;
        }

        .table-subtitle, .image-subtitle {
            margin: 0.25rem 0 0 0;
            opacity: 0.8;
            font-size: 0.875rem;
            font-weight: 400;
        }

        /* Stats section */
        .stats-section {
            display: flex;
            align-items: center;
            gap: 1rem;
        }

        .stat-item {
            text-align: center;
        }

        .stat-number {
            font-size: 1.5rem;
            font-weight: 700;
            line-height: 1;
        }

        .stat-label {
            font-size: 0.75rem;
            opacity: 0.8;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-top: 0.25rem;
        }

        .stat-divider {
            width: 1px;
            height: 32px;
            background: rgba(255, 255, 255, 0.3);
        }

        /* Actions section */
        .actions-section {
            display: flex;
            gap: 0.75rem;
        }

        .download-btn {
            background: rgba(255, 255, 255, 0.15);
            border: 1px solid rgba(255, 255, 255, 0.3);
            color: white;
            padding: 0.75rem 1rem;
            border-radius: 8px;
            font-size: 0.875rem;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.3s ease;
            display: flex;
            align-items: center;
            gap: 0.5rem;
            backdrop-filter: blur(10px);
        }

        .download-btn:hover {
            background: rgba(255, 255, 255, 0.25);
            border-color: rgba(255, 255, 255, 0.5);
            transform: translateY(-1px);
        }

        /* Table styles */
        .table-responsive {
            padding: 0;
            overflow-x: auto;
        }

        .extracted-table {
            width: 100%;
            border-collapse: collapse;
            font-size: 0.875rem;
            background: var(--white);
        }

        .extracted-table th {
            background: linear-gradient(135deg, var(--gray-700) 0%, var(--gray-800) 100%);
            color: white;
            font-weight: 600;
            padding: 1rem 0.75rem;
            text-align: left;
            border: none;
            font-size: 0.8rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            position: sticky;
            top: 0;
            z-index: 10;
        }

        .extracted-table td {
            padding: 0.875rem 0.75rem;
            border-bottom: 1px solid var(--gray-200);
            vertical-align: top;
            background: var(--white);
            transition: background-color 0.2s ease;
        }

        .extracted-table tbody tr:hover td {
            background: var(--gray-50);
        }

        .extracted-table tbody tr:nth-child(even) td {
            background: var(--gray-50);
        }

        .extracted-table tbody tr:nth-child(even):hover td {
            background: var(--gray-100);
        }

        /* Image styles */
        .image-content {
            padding: 2rem;
            text-align: center;
            background: var(--gray-50);
        }

        .extracted-image {
            max-width: 100%;
            height: auto;
            border-radius: 12px;
            box-shadow: var(--shadow-lg);
            transition: transform 0.3s ease;
        }

        .extracted-image:hover {
            transform: scale(1.02);
        }

        /* Responsive design */
        @media (max-width: 768px) {
            .page-header {
                padding: 1.5rem;
                flex-direction: column;
                text-align: center;
                gap: 1rem;
            }

            .page-info h2 {
                font-size: 1.5rem;
            }

            .header-content {
                flex-direction: column;
                gap: 1rem;
            }

            .title-section {
                flex-direction: column;
                text-align: center;
                gap: 0.75rem;
            }

            .stats-section {
                justify-content: center;
            }

            .table-container, .image-container {
                margin: 1rem;
            }

            .extracted-table {
                font-size: 0.75rem;
            }

            .extracted-table th,
            .extracted-table td {
                padding: 0.5rem 0.375rem;
            }
        }

        /* Animations */
        @keyframes fadeInUp {
            from {
                opacity: 0;
                transform: translateY(20px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }

        .table-container, .image-container {
            animation: fadeInUp 0.6s ease-out;
        }

        /* Scrollbar styling */
        .table-responsive::-webkit-scrollbar {
            height: 8px;
        }

        .table-responsive::-webkit-scrollbar-track {
            background: var(--gray-100);
            border-radius: 4px;
        }

        .table-responsive::-webkit-scrollbar-thumb {
            background: var(--gray-300);
            border-radius: 4px;
        }

        .table-responsive::-webkit-scrollbar-thumb:hover {
            background: var(--gray-400);
        }
        </style>
        """
    
    def _get_javascript(self) -> str:
        """
        Retourne le JavaScript pour les fonctionnalités interactives modernes
        """
        return """
        <script>
        document.addEventListener('DOMContentLoaded', function() {
            // Fonction de téléchargement d'images (nouveau sélecteur)
            document.querySelectorAll('.download-btn').forEach(button => {
                button.addEventListener('click', function() {
                    const imageData = this.getAttribute('data-image');
                    const filename = this.getAttribute('data-filename');
                    
                    // Animation du bouton
                    this.style.transform = 'scale(0.95)';
                    setTimeout(() => {
                        this.style.transform = 'scale(1)';
                    }, 150);
                    
                    // Créer un lien de téléchargement
                    const link = document.createElement('a');
                    link.href = 'data:image/png;base64,' + imageData;
                    link.download = filename;
                    link.click();
                    
                    // Feedback visuel
                    const originalText = this.innerHTML;
                    this.innerHTML = '<i class="fas fa-check"></i><span>Téléchargé!</span>';
                    setTimeout(() => {
                        this.innerHTML = originalText;
                    }, 2000);
                });
            });
            
            // Animation d'apparition progressive des éléments
            const observerOptions = {
                threshold: 0.1,
                rootMargin: '0px 0px -50px 0px'
            };
            
            const observer = new IntersectionObserver(function(entries) {
                entries.forEach(entry => {
                    if (entry.isIntersecting) {
                        entry.target.style.opacity = '1';
                        entry.target.style.transform = 'translateY(0)';
                    }
                });
            }, observerOptions);
            
            // Observer tous les containers
            document.querySelectorAll('.table-container, .image-container').forEach(container => {
                container.style.opacity = '0';
                container.style.transform = 'translateY(20px)';
                container.style.transition = 'opacity 0.6s ease, transform 0.6s ease';
                observer.observe(container);
            });
            
            // Amélioration des interactions avec les tableaux
            document.querySelectorAll('.extracted-table tbody tr').forEach(row => {
                row.addEventListener('mouseenter', function() {
                    this.style.transform = 'translateX(4px)';
                    this.style.transition = 'transform 0.2s ease';
                });
                
                row.addEventListener('mouseleave', function() {
                    this.style.transform = 'translateX(0)';
                });
            });
            
            // Effet de parallaxe léger sur les en-têtes
            window.addEventListener('scroll', function() {
                const scrolled = window.pageYOffset;
                const headers = document.querySelectorAll('.page-header');
                
                headers.forEach(header => {
                    const rate = scrolled * -0.5;
                    header.style.transform = `translateY(${rate}px)`;
                });
            });
            
            // Animation des statistiques au chargement
            document.querySelectorAll('.stat-number').forEach(stat => {
                const finalValue = parseInt(stat.textContent);
                let currentValue = 0;
                const increment = finalValue / 30;
                
                const timer = setInterval(() => {
                    currentValue += increment;
                    if (currentValue >= finalValue) {
                        stat.textContent = finalValue;
                        clearInterval(timer);
                    } else {
                        stat.textContent = Math.floor(currentValue);
                    }
                }, 50);
            });
        });
        </script>
        """