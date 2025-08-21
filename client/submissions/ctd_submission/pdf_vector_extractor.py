import fitz  # PyMuPDF
import html

def drawings_to_svg_path(drawings):
    path = ""

    for drawing in drawings:
        for item in drawing['items']:
            op = item[0]
            points = item[1:]

            if op == 'm':  # moveTo
                x, y = points
                path += f"M {x} {y} "
            elif op == 'l':  # lineTo
                x, y = points
                path += f"L {x} {y} "
            elif op == 'c':  # curveTo
                x1, y1, x2, y2, x3, y3 = points
                path += f"C {x1} {y1}, {x2} {y2}, {x3} {y3} "
            elif op == 'h':  # closePath
                path += "Z "

    return path.strip()


def extract_page_drawings_as_svg(page, stroke_color="#000000", stroke_width=1):
    """
    Extrait les dessins d'une page PyMuPDF et les convertit en SVG.
    """
    drawings = page.get_drawings()
    svg_paths = []

    for drawing in drawings:
        path_data = drawings_to_svg_path([drawing])
        if path_data:
            svg_paths.append(f'<path d="{html.escape(path_data)}" stroke="{stroke_color}" stroke-width="{stroke_width}" fill="none"/>')

    # Dimensions de la page
    rect = page.rect
    svg = f'''
    <svg width="{rect.width}" height="{rect.height}" viewBox="0 0 {rect.width} {rect.height}" xmlns="http://www.w3.org/2000/svg">
        {"".join(svg_paths)}
    </svg>
    '''
    return svg

def extract_pdf_vector_drawings(file_path):
    """
    Ouvre un PDF, extrait les dessins vectoriels page par page en SVG.
    Retourne un dict : {page_number: svg_string}
    """
    doc = fitz.open(file_path)
    svg_pages = {}

    for i in range(len(doc)):
        page = doc.load_page(i)
        svg = extract_page_drawings_as_svg(page)
        svg_pages[i + 1] = svg

    doc.close()
    return svg_pages
