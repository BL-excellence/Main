import django
import os

# Initialiser Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ctd_project.settings')
django.setup()

from ctd_submission.models import Document, CTDSection
from ctd_submission.utils import CTDAnalyzer

# Récupérer le dernier document créé avec ce nom précis
doc = Document.objects.filter(name="DTC_S020098_PF_N_SPE_50520_EN_3.0").order_by('-created_at').first()

if not doc:
    print("❌ Aucun document trouvé.")
else:
    print("✅ Document trouvé avec ID :", doc.id)
    print("Section avant analyse :", doc.section)

    analyzer = CTDAnalyzer()
    result = analyzer.analyze_document(doc)

    if result and 'section' in result:
        doc.section = result['section']
        doc.save(update_fields=['section'])
        print("✅ Après analyse et sauvegarde :", doc.section)
    else:
        print("❌ Pas de section trouvée dans result")

    # Vérification finale
    doc.refresh_from_db()
    print("🟢 Section en DB après refresh :", doc.section)
