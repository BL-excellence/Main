# PharmaLabs – Plateforme Documentaire Réglementaire

Bienvenue sur **PharmaLabs**, la plateforme collaborative dédiée à la gestion, à l'extraction, à l'annotation et à la révision de documents réglementaires (PDF).

Selon votre rôle (_Métadonneur_, _Annotateur_, _Expert_, ou _Client_), vous bénéficiez de fonctionnalités spécifiques qui optimisent l'ensemble du cycle de vie documentaire.

> **Nouveauté :**  
> Les clients peuvent désormais uploader leurs propres documents PDF dans la Library, avec extraction automatique des métadonnées et gestion dédiée.

---

## 🚀 Accès à la Plateforme

- **Lien d'accès :** [https://myprojectiablcoklabs.onrender.com](https://myprojectiablcoklabs.onrender.com)
- **Lien d'accès :** [https://iablocklabs-zh6i.onrender.com](https://iablocklabs-zh6i.onrender.com)

> **Note importante**  
> L'hébergement gratuit peut occasionner une attente initiale (5-6 min) lors de la première connexion.  
> N'hésitez pas à rafraîchir la page en cas d'erreur.

---

## 👤 Comptes de Démonstration

| Rôle         | Username    | Password   |
|--------------|-------------|------------|
| Métadonneur  | Metadonneur | meta@12345 |
| Annotateur   | Annotateur  | anno@12345 |
| Expert       | Expert      | exp@12345  |
| Client       | Client      | cli@12345  |

---

## 🧭 Vue d’ensemble du Workflow

1) **Métadonneur**
   - Upload du PDF (fichier ou URL) → extraction IA des métadonnées → correction/validation → extraction des pages et texte → document marqué « validé ».
2) **Annotateur**
   - Accède aux documents validés → annotations IA (GROQ) + manuelles → validation des pages (RLHF) → une fois toutes les pages validées: document auto-marqué « prêt pour expert ».
3) **Expert**
   - Révision complète → consolidation et validation (analyse réglementaire experte et résumé global) → publication vers les espaces consultés côté Client.
4) **Client / Library**
   - Consulte, filtre, télécharge → bouton « Résumé » (texte IA stocké) et « Régénérer le résumé » (ne modifie pas l’analyse experte) → « Analyser » affiche l’analyse experte consolidée (sans régénération IA).

---

## 1. Parcours du Métadonneur

### Accès & Dashboard

- Dashboard personnalisé
- Onglet **Upload** pour déposer de nouveaux documents PDF
- Validation des métadonnées extraites

#### Fonctionnement

**a. Upload d'un document**
- Cliquez sur **Upload**
- Chargez un document PDF ou renseignez une URL
- Les métadonnées sont extraites automatiquement (_via LLM_)
- ⚠️ Corrigez les éventuelles erreurs d'extraction lors de la validation

**b. Validation des métadonnées**
- Accédez à la fenêtre de validation
- Visualisez, modifiez, sauvegardez les métadonnées, consultez l'historique (logs)
- Supprimez un document si nécessaire
- **Validez** : le document devient « validé » et les pages sont extraites (texte nettoyé par page)
  - Champs mis à jour (modèle `RawDocument`) : `is_validated`, `validated_at`, `pages_extracted`, `total_pages`
  - Les **pages** (`DocumentPage`) contiennent `cleaned_text` pour alimenter l’annotation et les résumés

> Une fois validé par le Métadonneur, le document devient disponible pour l’**Annotateur**.

---

## 2. Parcours de l'Annotateur

### Accès & Interface

- Deux onglets principaux :  
  - Statistiques (sur les documents à annoter/améliorer)  
  - Annotation

#### Fonctionnement

**a. Annotation d'un document**
- Liste des documents **validés** par le Métadonneur
- Cliquez sur **Annoter** pour ouvrir l'interface

**b. Modes d'annotation**
- **Annotation IA (GROQ)** : suggestions automatiques (entités/segments) avec justification
  - Endpoint côté serveur: `rawdocs:ai_annotate_page_groq` (POST)
  - Les annotations sont persistées (modèle `Annotation`), types dynamiques (`AnnotationType`)
- **Annotation manuelle** : sélectionnez un type (ex: Substance, Dosage…) ou créez-en un
  - Surlignez du texte → l’annotation est créée et liée à la page

**c. Validation avec apprentissage (RLHF)**
- Bouton « Valider la page » → la page est marquée `is_validated_by_human = True`
- Un processeur RLHF compare annotations IA vs annotations humaines pour améliorer les performances
- Quand toutes les pages du document sont validées :  
  → le document est automatiquement marqué `is_ready_for_expert = True` (et `expert_ready_at` renseigné)

### Visualisation JSON & Résumés (Annotateur)

- Les vues « JSON » permettent de consulter le JSON d’annotations page par page ou global document, avec un résumé calculé:
  - `rawdocs:view_page_annotation_json` (GET)
  - `rawdocs:view_document_annotation_json` (GET)
- Régénération (si activée dans l’UI d’annotation) :
  - `rawdocs:generate_page_annotation_summary` (POST)
  - `rawdocs:generate_document_annotation_summary` (POST)

> Côté Annotateur, ces générateurs peuvent recalculer un résumé basé sur le texte nettoyé et/ou les annotations.  
> Cela n’écrase pas l’analyse réglementaire experte.

---

## 3. Parcours de l'Expert

### Accès & Interface

- Onglet **Statistiques** (suivi de l'activité & performance)
- Liste des documents **prêts pour expert** (`is_ready_for_expert = True`)

#### Fonctionnement

**a. Révision d'un document**
- Sélectionnez un document puis cliquez sur **Réviser**
- Interface : texte annoté, liste des annotations détaillées, PDF original consultable

**b. Actions de l'Expert**
- **Validez** les annotations correctes / **Rejetez** les annotations erronées
- **Modifiez** le contenu ou le type d’annotation si nécessaire
- Rédigez / consolidez l’**analyse réglementaire experte** (ex: obligations, délais, autorités)
- Le système stocke l’analyse experte consolidée (modèle `DocumentRegulatoryAnalysis` liée au document)  
  et peut conserver un **résumé global validé par l’expert**.

> Après validation Expert, le document et ses informations consolidées deviennent accessibles côté **Client** (Products / Library).

---

## 4. Parcours Client (Consultation & Upload)

### Accès & Fonctionnalités

- Interface moderne avec onglets :
  - **Products**
  - **Submissions**
  - **Library** (bibliothèque documentaire)
  - **Reports** (rapports et analyses)

#### Library (Bibliothèque de documents)

- Tous les documents validés apparaissent dans la **Library** (y compris ceux uploadés par les clients)
- Le client peut :  
  - Consulter toutes les métadonnées (titre, type, pays, langue, contexte, etc.)
  - Télécharger les PDF associés (recherche/filtrage)
  - Ouvrir le **Résumé** ou **Régénérer le résumé**
  - Voir le **Texte brut**

#### Boutons et API (Library)

- **Analyser** (icône psychologie)  
  Affiche l’**analyse réglementaire experte** existante (si disponible).  
  - Endpoint: `POST /client/library/api/documents/<pk>/analyze/`  
  - N’utilise pas l’IA, ne modifie rien.

- **Résumé**  
  Affiche le **résumé texte** stocké pour le document (`RawDocument.global_annotations_summary`).  
  - Endpoint: `POST /client/library/api/documents/<pk>/summary/` (avec `{ force: false }`)  
  - Si un résumé est déjà stocké, il est renvoyé tel quel (cached = true).

- **Régénérer le résumé**  
  Régénère uniquement le **résumé texte** (stocké dans `RawDocument.global_annotations_summary`).  
  - Endpoint: `POST /client/library/api/documents/<pk>/summary/` (avec `{ force: true }`)  
  - Met à jour les champs: `global_annotations_summary`, `global_annotations_summary_generated_at`  
  - ⚠️ Ne modifie pas l’**analyse experte**.

- **Texte brut**  
  Retourne la concaténation du texte nettoyé par page.  
  - Endpoint: `GET /client/library/api/documents/<pk>/raw-text/`

#### Upload de documents par le Client 🆕

- Interface d’upload moderne (drag & drop)
- Extraction automatique des métadonnées (pipeline IA)
- **Source** du document forcée à "Client" pour séparation claire
- Validation et extraction de pages automatiques
- Stockage organisé: `media/Client/YYYYMMDD_HHMMSS/document.pdf`
- Sécurité: chaque client ne voit que ses documents

> Les documents uploadés par le Client suivent le même **flux d’annotation**: une fois toutes les pages validées, ils basculent automatiquement en « prêt pour expert ».

---

## 5. Module Reporting (Analyses & Tableaux de Bord)

### Accès & Vue d'ensemble

Le module **Reports** offre aux clients un système complet de génération de rapports et d'analyses de données réglementaires avec tableaux de bord interactifs.

#### Interface Principale

- **Dashboard moderne** avec vue temps réel des KPIs
- **Générateur de rapports** avec templates prédéfinis
- **Export de données** (CSV, PDF)
- **Filtres avancés** par période, autorité, type de document

### Fonctionnalités Clés

#### **a. Tableaux de Bord KPI**

Visualisation en temps réel des indicateurs de performance :

- **Documents traités** : Nombre de documents validés sur la période
- **Annotations créées** : Volume d'annotations générées
- **Exports PDF** : Nombre d'exports effectués
- **Produits créés** : Nouveaux produits dans le système

#### **b. Générateur de Rapports**

**Templates disponibles :**
- **Rapport Mensuel de Conformité** : Vue d'ensemble des activités réglementaires
- **Tableau de Bord KPI** : Indicateurs de performance hebdomadaires
- **Rapport d'Audit Réglementaire** : Synthèse trimestrielle des audits
- **Analyse des Variations** : Suivi mensuel des variations produits/autorités

**Filtres personnalisables :**
- Période (7 jours, 30 jours, 3 mois, année)
- Type de document
- Autorité réglementaire
- Pays/région

#### **c. Données et Analyses**

**Graphiques interactifs :**
- Évolution quotidienne des documents traités
- Répartition par type de document
- Distribution par autorité réglementaire
- Tendances de performance

**Activité récente :**
- Liste des 10 derniers documents validés
- 5 derniers produits créés
- Historique des actions

#### **d. Export et Partage**

**Formats d'export :**
- **CSV** : Données brutes pour analyse externe
- **PDF** : Rapports formatés pour présentation

**Fonctionnalités avancées :**
- Sauvegarde de vues personnalisées
- Planification automatique de rapports
- Partage sécurisé avec équipes

### Comment Utiliser le Reporting

#### **Étape 1 : Accès au Module**
- Connectez-vous avec un compte Client
- Cliquez sur l'onglet **Reports** dans le menu principal

#### **Étape 2 : Consultation des KPIs**
- Le dashboard affiche automatiquement les indicateurs du mois en cours
- Utilisez les filtres pour ajuster la période d'analyse
- Observez les tendances via les graphiques

#### **Étape 3 : Génération de Rapport**
- Sélectionnez un **template** dans le générateur
- Choisissez votre **période** et **filtres**
- Cliquez sur **Générer** pour créer le rapport

#### **Étape 4 : Export et Partage**
- Utilisez **Export CSV** pour les données brutes
- **Sauvegarder Vue** pour conserver vos filtres favoris
- **Nouveau Report** pour créer des templates personnalisés

### Cas d'Usage Types

**Pour le suivi mensuel :**
- Générez un "Rapport Mensuel de Conformité"
- Filtrez par autorité spécifique (EMA, FDA, etc.)
- Exportez en PDF pour les réunions équipe

**Pour l'analyse de performance :**
- Consultez le "Tableau de Bord KPI" hebdomadaire
- Comparez les périodes via les graphiques
- Identifiez les goulots d'étranglement

**Pour les audits trimestriels :**
- Utilisez le "Rapport d'Audit Réglementaire"
- Exportez les données CSV pour analyse détaillée
- Sauvegardez la vue pour le prochain trimestre

> **💡 Conseil**  
> Sauvegardez vos vues les plus utilisées pour un accès rapide aux rapports récurrents. Le système conserve vos préférences de filtrage.

---

## 💡 Conseils & Remarques

- **Erreurs d'accès :**  
  Attendez 5 minutes puis réessayez (limites serveur gratuit)
- **Navigation :**  
  Menus adaptés à chaque rôle pour éviter toute confusion
- **Actualisation :**  
  Rafraîchissez la page si une fonctionnalité ne s'affiche pas
- **Sécurité :**  
  Ne partagez pas vos accès

---

## 📞 Support & Documentation

Pour toute question, suggestion ou bug :  
Contactez l'équipe PharmaLabs — _réponse rapide assurée_ !

---

**Bon usage de la plateforme PharmaLabs**
