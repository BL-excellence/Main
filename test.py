from pymongo import MongoClient

# ==============================
# Paramètres MongoDB
# ==============================
MONGO_URI = "mongodb://localhost:27017/"
MONGO_DB = "annotations_db"
MONGO_COLLECTION = "documents"

# Connexion à MongoDB
client = MongoClient(MONGO_URI)
db = client[MONGO_DB]
collection = db[MONGO_COLLECTION]

# ==============================
# Document JSON à insérer
# ==============================
"""
document = {
   "document": {
     "id": "288",
     "title": "Documentation Produit - Exemple Produit (Paracétamol 500 mg)",
     "doc_type": "specifications",
     "source": "Site Industriel A (Manufacturer)",
     "total_pages": 1,
     "total_annotations": 14
   },
   "metadata": {
     "enriched_at": "2025-09-30T10:25:15.270582+00:00",
     "schema": "semantic_generic",
     "version": "3.2",
     "ai_provider": "groq",
     "ai_model": None
   },
   "entities": {
     "Étape ou processus de validation": {
       "items": [
         {
           "value": "DocumentationProduit",
           "normalized_value": "documentationproduit",
           "confidence": 1,
           "properties": {},
           "context": {},
           "extracted_from": "auto"
         }
       ],
       "count": 1,
       "primary": {
         "value": "DocumentationProduit",
         "normalized_value": "documentationproduit",
         "confidence": 1,
         "properties": {},
         "context": {},
         "extracted_from": "auto"
       }
     },
     "Nom du produit pharmaceutique": {
       "items": [
         {
           "value": "Nom du produit",
           "normalized_value": "nom du produit",
           "confidence": 1,
           "properties": {},
           "context": {},
           "extracted_from": "auto"
         }
       ],
       "count": 1,
       "primary": {
         "value": "Nom du produit",
         "normalized_value": "nom du produit",
         "confidence": 1,
         "properties": {},
         "context": {},
         "extracted_from": "auto"
       }
     },
     "Dosage": {
       "items": [
         {
           "value": "500 mg",
           "normalized_value": "500 mg",
           "confidence": 1,
           "properties": {},
           "context": {},
           "extracted_from": "auto"
         }
       ],
       "count": 1,
       "primary": {
         "value": "500 mg",
         "normalized_value": "500 mg",
         "confidence": 1,
         "properties": {},
         "context": {},
         "extracted_from": "auto"
       }
     },
     "Principe actif": {
       "items": [
         {
           "value": "Paracétamol",
           "normalized_value": "paracétamol",
           "confidence": 1,
           "properties": {},
           "context": {},
           "extracted_from": "auto"
         }
       ],
       "count": 1,
       "primary": {
         "value": "Paracétamol",
         "normalized_value": "paracétamol",
         "confidence": 1,
         "properties": {},
         "context": {},
         "extracted_from": "auto"
       }
     },
     "Site de production": {
       "items": [
         {
           "value": "Site Industriel A",
           "normalized_value": "site industriel a",
           "confidence": 1,
           "properties": {},
           "context": {},
           "extracted_from": "auto"
         }
       ],
       "count": 1,
       "primary": {
         "value": "Site Industriel A",
         "normalized_value": "site industriel a",
         "confidence": 1,
         "properties": {},
         "context": {},
         "extracted_from": "auto"
       }
     },
     "Condition Requise": {
       "items": [
         {"value": "Respect des normes GMP (Good Manufacturing Practices)", "normalized_value": "respect des normes gmp (good manufacturing practices)", "confidence": 1, "properties": {}, "context": {}, "extracted_from": "auto"},
         {"value": "Validation des procédés de fabrication", "normalized_value": "validation des procédés de fabrication", "confidence": 1, "properties": {}, "context": {}, "extracted_from": "auto"},
         {"value": "Contrôle qualité rigoureux", "normalized_value": "contrôle qualité rigoureux", "confidence": 1, "properties": {}, "context": {}, "extracted_from": "auto"},
         {"value": "Autorisations réglementaires avant la mise sur le marché", "normalized_value": "autorisations réglementaires avant la mise sur le marché", "confidence": 1, "properties": {}, "context": {}, "extracted_from": "auto"}
       ],
       "count": 4,
       "primary": {
         "value": "Respect des normes GMP (Good Manufacturing Practices)",
         "normalized_value": "respect des normes gmp (good manufacturing practices)",
         "confidence": 1,
         "properties": {},
         "context": {},
         "extracted_from": "auto"
       }
     },
     "Document réglementaire ou technique": {
       "items": [
         {"value": "Dossier pharmaceutique complet (composition, stabilité, etc.)", "normalized_value": "dossier pharmaceutique complet (composition, stabilité, etc.)", "confidence": 1, "properties": {}, "context": {}, "extracted_from": "auto"},
         {"value": "Procédures opératoires normalisées (SOP)", "normalized_value": "procédures opératoires normalisées (sop)", "confidence": 1, "properties": {}, "context": {}, "extracted_from": "auto"},
         {"value": "Rapports de validation et contrôle qualité", "normalized_value": "rapports de validation et contrôle qualité", "confidence": 1, "properties": {}, "context": {}, "extracted_from": "auto"},
         {"value": "Certificats d’analyse des lot", "normalized_value": "certificats d’analyse des lot", "confidence": 1, "properties": {}, "context": {}, "extracted_from": "auto"},
         {"value": "Documents réglementaires soumis aux autorités compétentes", "normalized_value": "documents réglementaires soumis aux autorités compétentes", "confidence": 1, "properties": {}, "context": {}, "extracted_from": "auto"}
       ],
       "count": 5,
       "primary": {
         "value": "Dossier pharmaceutique complet (composition, stabilité, etc.)",
         "normalized_value": "dossier pharmaceutique complet (composition, stabilité, etc.)",
         "confidence": 1,
         "properties": {},
         "context": {},
         "extracted_from": "auto"
       }
     }
   },
   "relations": [
      {"id":"ac7bf665","source":{"type":"Nom du produit pharmaceutique","value":"Nom du produit"},"target":{"type":"Dosage","value":"500 mg"},"type":"has_dosage","description":"Nom du produit a pour dosage 500 mg"},
      {"id":"d40193ca","source":{"type":"Nom du produit pharmaceutique","value":"Nom du produit"},"target":{"type":"Principe actif","value":"Paracétamol"},"type":"composed_of","description":"Nom du produit composed of Paracétamol"}
   ],
   "contexts": {
     "pharmaceutical": {"type": "pharmaceutical_document"},
     "regulatory": {"type": "regulatory_information"},
     "manufacturing": {"type": "manufacturing_information"},
     "clinical": {"type": "clinical_information"}
   },
   "questions_answers": [],
   "semantic_summary": "Ce document contient des informations structurées sur « Étape ou processus de validation » : DocumentationProduit.",
   "tech_hints": {
     "suggested_schema": {
       "entity_types": [],
       "relation_types": []
     },
     "notes": []
   }
}
"""

document = {
  "document": {
    "id": "289",
    "title": "Documentation Produit - Exemple Produit (Ibuprofène 200 mg)",
    "doc_type": "specifications",
    "source": "Site Industriel B (Manufacturer)",
    "total_pages": 1,
    "total_annotations": 12
  },
  "metadata": {
    "enriched_at": "2025-09-30T11:05:42.173Z",
    "schema": "semantic_generic",
    "version": "3.2",
    "ai_provider": "groq",
    "ai_model": None
  },
  "entities": {
    "Étape ou processus de validation": {
      "items": [
        {
          "value": "Fiche Produit",
          "normalized_value": "fiche produit",
          "confidence": 1,
          "properties": {},
          "context": {},
          "extracted_from": "auto"
        }
      ],
      "count": 1,
      "primary": {
        "value": "Fiche Produit",
        "normalized_value": "fiche produit",
        "confidence": 1,
        "properties": {},
        "context": {},
        "extracted_from": "auto"
      }
    },
    "Nom du produit pharmaceutique": {
      "items": [
        {
          "value": "Ibuprofène",
          "normalized_value": "ibuprofène",
          "confidence": 1,
          "properties": {},
          "context": {},
          "extracted_from": "auto"
        }
      ],
      "count": 1,
      "primary": {
        "value": "Ibuprofène",
        "normalized_value": "ibuprofène",
        "confidence": 1,
        "properties": {},
        "context": {},
        "extracted_from": "auto"
      }
    },
    "Dosage": {
      "items": [
        {
          "value": "200 mg",
          "normalized_value": "200 mg",
          "confidence": 1,
          "properties": {},
          "context": {},
          "extracted_from": "auto"
        }
      ],
      "count": 1,
      "primary": {
        "value": "200 mg",
        "normalized_value": "200 mg",
        "confidence": 1,
        "properties": {},
        "context": {},
        "extracted_from": "auto"
      }
    },
    "Principe actif": {
      "items": [
        {
          "value": "Ibuprofène",
          "normalized_value": "ibuprofène",
          "confidence": 1,
          "properties": {},
          "context": {},
          "extracted_from": "auto"
        }
      ],
      "count": 1,
      "primary": {
        "value": "Ibuprofène",
        "normalized_value": "ibuprofène",
        "confidence": 1,
        "properties": {},
        "context": {},
        "extracted_from": "auto"
      }
    },
    "Site de production": {
      "items": [
        {
          "value": "Site Industriel B",
          "normalized_value": "site industriel b",
          "confidence": 1,
          "properties": {},
          "context": {},
          "extracted_from": "auto"
        }
      ],
      "count": 1,
      "primary": {
        "value": "Site Industriel B",
        "normalized_value": "site industriel b",
        "confidence": 1,
        "properties": {},
        "context": {},
        "extracted_from": "auto"
      }
    },
    "Condition Requise": {
      "items": [
        {
          "value": "Respect des normes GMP",
          "normalized_value": "respect des normes gmp",
          "confidence": 1,
          "properties": {},
          "context": {},
          "extracted_from": "auto"
        },
        {
          "value": "Stabilité du produit validée",
          "normalized_value": "stabilité du produit validée",
          "confidence": 1,
          "properties": {},
          "context": {},
          "extracted_from": "auto"
        },
        {
          "value": "Essais cliniques documentés",
          "normalized_value": "essais cliniques documentés",
          "confidence": 1,
          "properties": {},
          "context": {},
          "extracted_from": "auto"
        }
      ],
      "count": 3,
      "primary": {
        "value": "Respect des normes GMP",
        "normalized_value": "respect des normes gmp",
        "confidence": 1,
        "properties": {},
        "context": {},
        "extracted_from": "auto"
      }
    },
    "Document réglementaire ou technique": {
      "items": [
        {
          "value": "Notice patient",
          "normalized_value": "notice patient",
          "confidence": 1,
          "properties": {},
          "context": {},
          "extracted_from": "auto"
        },
        {
          "value": "Rapports cliniques",
          "normalized_value": "rapports cliniques",
          "confidence": 1,
          "properties": {},
          "context": {},
          "extracted_from": "auto"
        },
        {
          "value": "Certificat d’analyse du lot",
          "normalized_value": "certificat d’analyse du lot",
          "confidence": 1,
          "properties": {},
          "context": {},
          "extracted_from": "auto"
        }
      ],
      "count": 3,
      "primary": {
        "value": "Notice patient",
        "normalized_value": "notice patient",
        "confidence": 1,
        "properties": {},
        "context": {},
        "extracted_from": "auto"
      }
    }
  },
  "relations": [
    {
      "id": "rel-001",
      "source": {
        "type": "Nom du produit pharmaceutique",
        "value": "Ibuprofène"
      },
      "target": {
        "type": "Dosage",
        "value": "200 mg"
      },
      "type": "has_dosage",
      "description": "Ibuprofène a pour dosage 200 mg"
    },
    {
      "id": "rel-002",
      "source": {
        "type": "Nom du produit pharmaceutique",
        "value": "Ibuprofène"
      },
      "target": {
        "type": "Principe actif",
        "value": "Ibuprofène"
      },
      "type": "composed_of",
      "description": "Ibuprofène composé de Ibuprofène"
    }
  ],
  "contexts": {
    "pharmaceutical": {
      "type": "pharmaceutical_document"
    },
    "regulatory": {
      "type": "regulatory_information"
    },
    "manufacturing": {
      "type": "manufacturing_information"
    },
    "clinical": {
      "type": "clinical_information"
    }
  },
  "questions_answers": [],
  "semantic_summary": "Ce document contient des informations structurées sur l’Ibuprofène 200 mg produit sur le site industriel B.",
  "tech_hints": {
    "suggested_schema": {
      "entity_types": [],
      "relation_types": []
    },
    "notes": []
  }
}

# ==============================
# Insertion dans MongoDB
# ==============================
result = collection.insert_one(document)

print("✅ Document inséré avec l'ID :", result.inserted_id)
