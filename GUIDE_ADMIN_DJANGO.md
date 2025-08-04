# 🔧 Guide d'Administration Django - RegX Platform

## 📋 Vue d'ensemble

L'interface d'administration Django a été entièrement configurée pour offrir une gestion complète et avancée de tous les modèles du système Library. Cette interface permet aux administrateurs de visualiser, créer, modifier et supprimer tous les éléments du système avec des fonctionnalités avancées de recherche, filtrage et visualisation.

## 🚀 Accès à l'Administration

### 1. Créer un superutilisateur (si pas déjà fait)
```bash
python manage.py createsuperuser
```

### 2. Accéder à l'admin
- URL: `http://localhost:8000/admin/`
- Connectez-vous avec vos identifiants superutilisateur

## 📊 Sections Disponibles

### 🗂️ RAWDOCS (Documents Bruts)

#### **RawDocuments** - Tous vos documents (métadonneurs + clients)
- **Vue liste** : ID, Titre, Source, Type, Propriétaire, Statut de validation
- **Filtres** : Source, Type, Validation, Pays, Langue, Date
- **Recherche** : Titre, Source, Type, Propriétaire
- **Actions** : Marquer comme validé, Prêt pour expert

**Colonnes importantes :**
- `Source` : EMA, FDA, ICH, **Client**, etc.
- `is_validated` : Document validé ou non
- `owner` : Utilisateur qui a uploadé le document

#### **Documents** - Documents traités avec métadonnées
- **Affichage** : Titre, organisation, type, statut, date de création
- **Filtres** : Organisation, type de document, statut de traitement
- **Recherche** : Titre, contenu, métadonnées
- **Fonctionnalités** : Visualisation des métadonnées extraites, liens vers documents sources

#### **Organizations** - Organisations/sources des documents
- **Affichage** : Nom, code, type, nombre de documents
- **Filtres** : Type d'organisation
- **Recherche** : Nom, code, description
- **Fonctionnalités** : Compteur de documents associés, codes couleur par type

#### **MetadonneursConfig** - Configuration des métadonneurs
- **Affichage** : Nom, statut, dernière exécution, succès
- **Filtres** : Statut actif, dernière exécution
- **Recherche** : Nom, description
- **Fonctionnalités** : Indicateurs visuels de statut, logs d'exécution

#### **Metadata Logs** - Historique des modifications
- Suivi de tous les changements de métadonnées
- Qui a modifié quoi et quand

#### **Document Pages** - Pages extraites des PDFs
- Pages individuelles avec annotations
- Statut d'annotation et validation

#### **Annotation Types** - Types d'annotations
- Gestion des catégories d'annotations
- Couleurs et descriptions

#### **Annotations** - Annotations sur les documents
- Annotations IA et manuelles
- Scores de confiance

#### **User Profiles** - Profils utilisateurs
- Rôles : Métadonneur, Annotateur, Expert, Client

### 📚 CLIENT LIBRARY (Bibliothèque Officielle)

#### **Documents** - Documents réglementaires officiels
- **Affichage** : Titre (tronqué), type, autorité, langue, statut de validation, date de publication, statistiques de vues, lien fichier
- **Filtres** : Type de document, autorité, langue, statut de validation, date de publication, catégorie
- **Recherche** : Titre, description, numéro de référence, tags
- **Fonctionnalités** : 
  - Hiérarchie par date de publication
  - Liens directs vers les fichiers
  - Calcul automatique de la taille des fichiers
  - Fieldsets organisés par sections logiques

#### **Document Categories** - Catégories de documents
- **Affichage** : Nom, code, aperçu couleur, nombre de documents
- **Recherche** : Nom, code, description
- **Fonctionnalités** : 
  - Aperçu visuel des couleurs
  - Compteur de documents par catégorie
  - Édition en ligne des couleurs

#### **Regulatory Authorities** - Autorités réglementaires
- **Affichage** : Nom, code, pays, lien site web, nombre de documents
- **Filtres** : Pays
- **Recherche** : Nom, code, pays
- **Fonctionnalités** : 
  - Liens cliquables vers les sites web
  - Compteur de documents par autorité
  - Tri par pays puis nom

#### **Document Versions** - Versions des documents
- **Affichage** : Document, version, date de création, créé par
- **Filtres** : Date de création
- **Recherche** : Titre du document, version, notes de version
- **Fonctionnalités** : Relations optimisées avec select_related

#### **Document Translations** - Traductions des documents
- **Affichage** : Document original, langue, méthode de traduction, validé, date de création
- **Filtres** : Langue, méthode de traduction, statut de validation
- **Recherche** : Titre du document original, titre traduit
- **Fonctionnalités** : 
  - Édition en ligne du statut de validation
  - Relations optimisées
  - Fieldsets organisés par sections

### 💊 PRODUCTS (Produits Pharmaceutiques)

#### **Products** - Produits pharmaceutiques
- **Affichage** : Nom, principe actif, dosage, forme, zone thérapeutique, badge de statut, nombre de spécifications, nombre de variations, date de création
- **Filtres** : Statut, zone thérapeutique, forme, date de création
- **Recherche** : Nom, principe actif, zone thérapeutique
- **Fonctionnalités** : 
  - Badges colorés pour les statuts (Commercialisé=vert, Développement=jaune, Arrêté=rouge)
  - Compteurs de spécifications et variations
  - Hiérarchie par date de création
  - Fieldsets organisés par sections logiques

#### **Product Specifications** - Spécifications par pays
- **Affichage** : Produit, code pays, numéro AMM, date d'approbation, date de renouvellement, statut des documents, actif
- **Filtres** : Code pays, statut actif, dossier CTD complet, certificat GMP, date d'approbation
- **Recherche** : Nom du produit, numéro AMM, code pays
- **Fonctionnalités** : 
  - Indicateurs visuels pour le statut des documents (✓ CTD, ✓ GMP, ✓ Inspection, ✓ RCP)
  - Édition en ligne du statut actif
  - Hiérarchie par date d'approbation
  - Relations optimisées

#### **Manufacturing Sites** - Sites de fabrication
- **Affichage** : Nom du site, produit, pays, ville, statut GMP, dernier audit, statut d'audit
- **Filtres** : Pays, certification GMP, dernier audit
- **Recherche** : Nom du site, ville, pays, nom du produit
- **Fonctionnalités** : 
  - Indicateurs colorés pour le statut GMP (✓ Certifié=vert, ⚠️ Expiré=orange, ✗ Non certifié=rouge)
  - Calcul automatique du temps écoulé depuis le dernier audit
  - Alertes visuelles pour les certifications expirées
  - Relations optimisées

#### **Product Variations** - Variations réglementaires
- **Affichage** : Titre, produit, type de variation, badge de statut, date de soumission, date d'approbation, temps de traitement
- **Filtres** : Type de variation, statut, date de soumission
- **Recherche** : Titre, nom du produit, description
- **Fonctionnalités** : 
  - Badges colorés pour les statuts (Soumis=bleu, En cours=jaune, Approuvé=vert, Rejeté=rouge)
  - Calcul automatique du temps de traitement
  - Hiérarchie par date de soumission
  - Relations optimisées

## 🎨 Fonctionnalités Avancées

### Visualisations et indicateurs
- **Badges colorés** : Statuts visuellement distincts avec codes couleur cohérents
- **Compteurs dynamiques** : Nombre d'éléments associés calculé en temps réel
- **Indicateurs de santé** : Alertes automatiques pour les éléments expirés ou nécessitant une attention
- **Liens directs** : Accès rapide aux fichiers et sites web externes

### Optimisations de performance
- **Select_related** : Réduction des requêtes de base de données pour les relations
- **Pagination** : 25 éléments par page pour une navigation fluide
- **Index de base de données** : Recherche et tri optimisés sur les champs critiques

### Interface utilisateur améliorée
- **Fieldsets organisés** : Regroupement logique des champs par sections
- **Sections collapsibles** : Métadonnées et annotations masquables pour réduire l'encombrement
- **Hiérarchie temporelle** : Navigation par dates avec drill-down
- **Édition en ligne** : Modification rapide de certains champs directement dans la liste

## 🔍 Comment Voir Vos Documents Clients

### Dans l'Admin Django :
1. Allez dans **RAWDOCS** → **Raw documents**
2. **Filtrez par Source** → Sélectionnez "Client"
3. Vous verrez tous les documents uploadés par les clients

### Informations visibles :
- **Titre** : Titre extrait automatiquement par l'IA
- **Source** : "Client" 
- **Type** : Type de document détecté automatiquement
- **Propriétaire** : Utilisateur qui a uploadé le document
- **Validation** : Statut de validation du document
- **Métadonnées** : Pays, langue, date de publication, etc.

## 📈 Statistiques et Monitoring

### Tableaux de bord disponibles :
- **Nombre total de documents** par source (métadonneurs vs clients)
- **Documents en attente de validation**
- **Activité des utilisateurs** par rôle
- **Performance de l'IA** (métriques d'apprentissage et précision)
- **Statistiques d'usage** (vues, téléchargements)

## 🛠️ Actions Administratives

### Actions en lot disponibles :
- **Marquer comme validé** : Valider plusieurs documents simultanément
- **Prêt pour expert** : Marquer pour révision par un expert
- **Supprimer** : Supprimer des documents (avec confirmation)
- **Exporter** : Export des données en CSV/Excel

### Gestion des utilisateurs :
- **User Profiles** : Voir et modifier les rôles de chaque utilisateur
- **Permissions** : Gérer les accès granulaires par module

## 🎯 Cas d'Usage Pratiques

### 1. Voir tous les documents clients
```
Admin → RAWDOCS → Raw documents → Filtre "Source" = "Client"
```

### 2. Valider des documents en attente
```
Admin → RAWDOCS → Raw documents → Filtre "is_validated" = False
→ Sélectionner documents → Action "Marquer comme validé"
```

### 3. Voir l'activité d'un utilisateur
```
Admin → RAWDOCS → Raw documents → Recherche par nom d'utilisateur
```

### 4. Gérer les catégories de documents
```
Admin → CLIENT LIBRARY → Document categories → Ajouter/Modifier
```

### 5. Voir les logs de modifications
```
Admin → RAWDOCS → Metadata logs → Filtrer par document/utilisateur
```

### 6. Surveiller les produits en développement
```
Admin → PRODUCTS → Products → Filtre "Status" = "En développement"
```

### 7. Vérifier les certifications GMP expirées
```
Admin → PRODUCTS → Manufacturing sites → Filtre "GMP certified" = True
→ Trier par "GMP expiry" pour voir les expirations proches
```

### 8. Suivre les variations en cours
```
Admin → PRODUCTS → Product variations → Filtre "Status" = "En cours"
```

## 🔧 Utilisation Recommandée par Rôle

### Pour les administrateurs système
1. **Gestion des utilisateurs** et permissions Django
2. **Configuration des métadonneurs** et sources de données
3. **Maintenance des référentiels** (catégories, autorités, organisations)
4. **Surveillance des performances** et statistiques d'usage
5. **Sauvegarde et maintenance** de la base de données

### Pour les gestionnaires de contenu
1. **Validation des documents** uploadés par les clients
2. **Gestion des métadonnées** et classification automatique
3. **Organisation des catégories** et taxonomies
4. **Suivi des traductions** et versions de documents
5. **Contrôle qualité** des extractions automatiques

### Pour les analystes produits
1. **Gestion des produits** pharmaceutiques et pipeline
2. **Suivi des spécifications** réglementaires par pays
3. **Monitoring des sites** de fabrication et certifications
4. **Gestion des variations** et soumissions réglementaires
5. **Analyse des délais** d'approbation et tendances

### Pour les auditeurs et compliance
1. **Consultation des statistiques** d'usage et traçabilité
2. **Vérification des certifications** GMP et dates d'expiration
3. **Suivi des dates d'expiration** et renouvellements
4. **Analyse des tendances** et génération de rapports
5. **Audit des modifications** et logs système

## 🔒 Sécurité et Bonnes Pratiques

### Contrôle d'accès
- Accès restreint aux superutilisateurs Django uniquement
- Logs automatiques de toutes les modifications avec horodatage
- Traçabilité complète des actions utilisateur
- Sessions sécurisées avec timeout automatique

### Sauvegarde et maintenance
- **Sauvegarde obligatoire** avant toute modification importante
- Vérification régulière des liens et intégrité des fichiers
- Nettoyage périodique des documents obsolètes ou orphelins
- Monitoring de l'espace disque pour les uploads

### Performance et optimisation
- Utilisation systématique des filtres pour limiter les résultats
- Recherche ciblée plutôt que navigation exhaustive
- Surveillance de l'utilisation mémoire et CPU
- Optimisation des requêtes avec select_related/prefetch_related

## 🚨 Dépannage Courant

### Problèmes de fichiers
- **Fichiers manquants** : Vérifier les chemins dans MEDIA_ROOT et MEDIA_URL
- **Uploads échoués** : Contrôler les permissions de dossier (755 pour dossiers, 644 pour fichiers)
- **Taille de fichier** : Ajuster FILE_UPLOAD_MAX_MEMORY_SIZE et DATA_UPLOAD_MAX_MEMORY_SIZE
- **Types de fichiers** : Vérifier les extensions autorisées dans les validateurs

### Performance lente
- **Trop de résultats** : Utiliser les filtres pour réduire la liste affichée
- **Requêtes lentes** : Vérifier les index de base de données avec EXPLAIN
- **Mémoire insuffisante** : Réduire la pagination ou optimiser les requêtes
- **Timeout** : Augmenter les timeouts Django si nécessaire

### Erreurs de métadonnées
- **Extraction échouée** : Vérifier les logs Mistral AI et la connectivité
- **Métadonnées incohérentes** : Revalider les documents avec l'IA
- **Encodage de caractères** : Vérifier l'encodage UTF-8 des fichiers

## 📞 Support et Documentation

### Ressources disponibles
- **Documentation Django Admin** : https://docs.djangoproject.com/en/stable/ref/contrib/admin/
- **Logs système** : Consulter les logs Django dans `/logs/` pour les erreurs détaillées
- **Base de données** : Utiliser pgAdmin ou équivalent pour le monitoring SQL
- **Monitoring** : Tableaux de bord de performance et métriques système

### Contact support
- **Équipe technique** : Pour les problèmes de configuration et performance
- **Équipe produit** : Pour les questions fonctionnelles et workflows
- **Documentation** : Ce guide est maintenu à jour avec chaque évolution

---

**Dernière mise à jour** : Janvier 2025
**Version** : 2.0 - Configuration complète avec Products et Library avancée