# 📊 Extraction Avancée de Tableaux et Images

## 🎯 Vue d'ensemble

Cette nouvelle fonctionnalité permet d'extraire et d'afficher les tableaux et images depuis les documents PDF avec une présentation moderne et interactive, en préservant la structure originale des tableaux.

## 🚀 Fonctionnalités

### ✨ Extraction de Tableaux
- **Structure préservée** : Les tableaux gardent leur format original avec bordures et cellules
- **HTML stylisé** : Affichage avec CSS moderne et responsive
- **Export Excel** : Conversion automatique vers format Excel (.xlsx)
- **Métadonnées** : Informations sur le nombre de lignes/colonnes par tableau

### 🖼️ Extraction d'Images  
- **Format optimisé** : Conversion automatique en PNG
- **Téléchargement direct** : Boutons de téléchargement pour chaque image
- **Métadonnées** : Dimensions, taille, page d'origine
- **Affichage responsive** : Adaptation automatique à la taille d'écran

### 🎨 Interface Utilisateur
- **Design moderne** : Interface avec gradients et animations
- **Organisation par page** : Regroupement logique des éléments extraits
- **Statistiques temps réel** : Résumé visuel des éléments trouvés
- **Navigation intuitive** : Boutons d'action clairs et accessibles

## 🛠️ Installation

### Dépendances requises

Ajoutez ces packages à votre `requirements.txt` :

```txt
pandas>=1.3.0
PyMuPDF>=1.20.0
openpyxl>=3.0.0
pdfplumber
```

### Installation automatique

```bash
pip install -r requirements.txt
```

## 📝 Utilisation

### 1. Via l'interface Web

1. **Accédez à la liste de documents** dans le module Métadonneur
2. **Cliquez sur l'icône tableau** (🏷️) à côté d'un document
3. **Consultez les éléments extraits** organisés par page
4. **Exportez en Excel** si des tableaux sont présents
5. **Téléchargez les images** individuellement

### 2. Via l'API Python

```python
from rawdocs.table_image_extractor import TableImageExtractor

# Créer l'extracteur
extractor = TableImageExtractor('chemin/vers/document.pdf')

# Extraire les tableaux
tables = extractor.extract_tables_with_structure()

# Extraire les images
images = extractor.extract_images()

# Obtenir le HTML combiné
html_content = extractor.get_combined_html()

# Export Excel
extractor.export_tables_to_excel('output.xlsx')
```

## 🔧 Architecture Technique

### Classe `TableImageExtractor`

```python
class TableImageExtractor:
    def __init__(self, pdf_path: str)
    def extract_tables_with_structure() -> List[Dict]
    def extract_images() -> List[Dict]
    def get_combined_html() -> str
    def export_tables_to_excel(output_path: str) -> bool
```

### Structure des données

#### Tableau extrait
```python
{
    'page': 1,
    'table_number': 1,
    'html': '<div class="table-container">...</div>',
    'raw_data': [['Header1', 'Header2'], ['Data1', 'Data2']],
    'dataframe': pandas.DataFrame,
    'rows': 10,
    'columns': 3
}
```

#### Image extraite
```python
{
    'page': 1,
    'image_number': 1,
    'width': 800,
    'height': 600,
    'base64': 'iVBORw0KGgoAAAANSUhEUgAA...',
    'format': 'PNG',
    'size_kb': 45,
    'html': '<div class="image-container">...</div>'
}
```

## 🎨 Personnalisation CSS

### Variables CSS disponibles

```css
:root {
    --table-border-color: #dee2e6;
    --table-header-bg: #343a40;
    --table-hover-bg: #f1f3f4;
    --table-stripe-bg: #f8f9fa;
    --image-border-color: #dee2e6;
    --gradient-start: #667eea;
    --gradient-end: #764ba2;
}
```

### Classes CSS principales

- `.table-container` : Conteneur principal des tableaux
- `.image-container` : Conteneur principal des images  
- `.extracted-table` : Styles des tableaux extraits
- `.extracted-image` : Styles des images extraites
- `.page-section` : Section regroupant les éléments par page

## 🚦 Test et Validation

### Script de test automatique

```bash
python test_extraction.py
```

Ce script :
- ✅ Vérifie les dépendances
- ✅ Teste l'extraction sur un document existant
- ✅ Génère un fichier HTML d'exemple
- ✅ Teste l'export Excel
- ✅ Affiche les statistiques détaillées

### Validation manuelle

1. **Tableaux** : Vérifiez que les bordures et la structure sont préservées
2. **Images** : Testez le téléchargement et la qualité
3. **Responsive** : Testez sur mobile et desktop
4. **Performance** : Vérifiez les temps de traitement

## 🔍 Résolution de problèmes

### Erreurs communes

#### ❌ "PyMuPDF not found"
```bash
pip install PyMuPDF
```

#### ❌ "pandas not found"  
```bash
pip install pandas
```

#### ❌ "openpyxl not found"
```bash
pip install openpyxl
```

#### ❌ Tableaux non détectés
- Vérifiez que le PDF contient des tableaux structurés
- Les tableaux scannés (images) ne sont pas supportés
- Utilisez des PDF avec du texte sélectionnable

#### ❌ Images non extraites
- Certains PDF ont des images vectorielles non supportées
- Les images doivent être intégrées (pas liées)
- Format supporté : PNG, JPEG converti en PNG

### Optimisation des performances

```python
# Pour de gros documents, limitez l'extraction
extractor = TableImageExtractor('document.pdf')

# Extraire seulement les 5 premières pages
tables = extractor.extract_tables_with_structure(max_pages=5)
```

## 📈 Métriques et Statistiques

### Données collectées
- Nombre de tableaux par page
- Nombre d'images par page
- Taille totale des données extraites
- Temps de traitement
- Taux de réussite d'extraction

### Exemple de rapport
```
📊 RÉSULTATS D'EXTRACTION
────────────────────────────
✅ Tableaux trouvés: 3
✅ Images trouvées: 2  
✅ Total lignes de données: 45
✅ Taille totale images: 127 KB

📋 Répartition par page:
   Page 1: 2 tableaux, 1 image
   Page 2: 1 tableau, 1 image
```

## 🔮 Améliorations futures

### Fonctionnalités prévues
- [ ] Reconnaissance OCR pour tableaux scannés
- [ ] Support des graphiques et diagrammes
- [ ] Export PDF des éléments extraits
- [ ] API REST complète
- [ ] Cache des extractions
- [ ] Extraction batch de multiple documents

### Contributions

Pour contribuer aux améliorations :
1. Forkez le repository
2. Créez une branche feature
3. Implémentez votre amélioration
4. Ajoutez des tests
5. Soumettez une pull request

## 📞 Support

Pour toute question ou problème :
- 📧 Contact : équipe technique IABlockLabs
- 📖 Documentation : Ce fichier
- 🐛 Bugs : Utilisez le système d'issues

---

**✨ Profitez de l'extraction avancée de tableaux et d'images !**