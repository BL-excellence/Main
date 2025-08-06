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
- **Validez** : le document est envoyé dans la section _Library_ du Client

---

## 2. Parcours de l'Annotateur

### Accès & Interface

- Deux onglets principaux :  
  - Statistiques (sur les documents à annoter/améliorer)
  - Annotation

#### Fonctionnement

**a. Annotation d'un document**
- Liste des documents validés par le Métadonneur
- Cliquez sur **Annoter** pour ouvrir l'interface

**b. Modes d'annotation**
- **Annotation IA** : suggestions automatiques par l'IA (guidelines réglementaires)
  - Vous pouvez valider, corriger ou supprimer chaque annotation
- **Annotation manuelle** : sélectionnez un type (Substance, Dosage, etc.) ou créez-en un
  - Surlignez un texte pour annoter automatiquement

_Nouveautés_ :  
- Annotations visibles et surlignées dans le texte
- Visualisation du PDF original dans une nouvelle fenêtre

**c. Validation et envoi à l'Expert**
- Validez la page pour contribuer à l'amélioration de l'IA
- Une fois toutes les entités requises annotées (Product, Substance active, Adresse, etc.), soumettez le document à l'Expert

---

## 3. Parcours de l'Expert

### Accès & Interface

- Onglet **Statistiques** (suivi de l'activité & performance)
- Liste des documents à réviser

#### Fonctionnement

**a. Révision d'un document**
- Sélectionnez un document puis cliquez sur **Réviser**
- Interface : texte annoté, liste des annotations détaillées, PDF original consultable

**b. Actions de l'Expert**
- **Validez** une annotation correcte
- **Rejetez** une annotation erronée/incomplète (suppression possible)
- **Modifiez** le contenu ou type d'annotation si nécessaire  
Après validation :  
Le document apparaît dans la section **Product** côté Client (dossier "ctd"), avec sites de fabrication associés

---

## 4. Parcours Client (Consultation & Upload)

### Accès & Fonctionnalités

- Interface moderne avec onglets :
  - **Products**
  - **Submissions**
  - **Library** (bibliothèque documentaire)
  - **Reports** (rapports et analyses)

#### Library (Bibliothèque de documents)

- Tous les documents validés par le Métadonneur sont automatiquement publiés dans la Library
- Le client peut :  
  - Consulter toutes les métadonnées (titre, type, pays, langue, contexte, etc.)
  - Télécharger les PDF associés (recherche/filtrage)

#### **Upload de documents par le Client** 🆕

- Les clients peuvent uploader leurs propres documents PDF via une interface moderne (drag & drop)
- Extraction automatique des métadonnées via IA (pipeline Mistral AI)
- Source du document forcée à "Client" pour une séparation claire
- Validation automatique des documents uploadés
- Stockage organisé dans un dossier dédié :  
  `media/Client/YYYYMMDD_HHMMSS/document.pdf`
- Catégorie "Client" ajoutée au dashboard, avec icône et couleur spécifique
- Gestion complète : liste, détail, téléchargement et suppression sécurisée
- Filtrage et tri par organisation dans la vue Library
- Sécurité : chaque client ne voit que ses propres documents

#### Products

- Après annotation & validation Expert, les documents sont visibles dans **Products**
- Classés par catégorie (dossier CTD)
- Visualisation des sites de fabrication extraits, associés à chaque produit

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

**Bon usage de la plateforme PharmaLabs