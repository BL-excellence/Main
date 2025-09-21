# Chemin d'intégration : ctd_submission/apps.py
# Configuration de l'application Django CTD submission

from django.apps import AppConfig
from django.db.models.signals import post_migrate
import logging

# Configuration du logger avec un niveau de logging plus élevé pour réduire les messages
logger = logging.getLogger(__name__)
logger.setLevel(logging.WARNING)  # Ne montrer que les warnings et erreurs


class CtdSubmissionConfig(AppConfig):
    """
    Configuration de l'application CTD Submission
    """
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'client.submissions.ctd_submission'
    # IMPORTANT: keep label 'ctd_submission' to match existing migration app_label references
    label = 'ctd_submission'
    verbose_name = 'CTD Submission System'

    def ready(self):
        """
        Méthode appelée lorsque l'application Django est prête
        Utilisée pour l'initialisation des signaux et des tâches de démarrage
        """
        # Importer les signaux
        try:
            from . import signals
            logger.info("Signaux CTD Submission chargés avec succès")
        except ImportError as e:
            logger.warning(f"Impossible de charger les signaux: {e}")

        # Connecter le signal post_migrate pour l'initialisation des données
        post_migrate.connect(self.initialize_default_data, sender=self)

        # Initialiser les analyseurs IA
        self.initialize_ai_components()

        logger.info("Application CTD Submission initialisée avec succès")

    def initialize_default_data(self, sender, **kwargs):
        """
        Initialise les données par défaut après les migrations
        """
        # Éviter les importations circulaires
        from django.contrib.auth.models import User, Group, Permission
        from django.contrib.contenttypes.models import ContentType

        try:
            # Créer les groupes d'utilisateurs par défaut
            self.create_default_groups()

            # Initialiser la structure CTD de base
            self.initialize_ctd_structure()

            # Créer un super utilisateur par défaut si aucun n'existe
            self.create_default_superuser()

            logger.info("Données par défaut initialisées avec succès")

        except Exception as e:
            logger.error(f"Erreur lors de l'initialisation des données par défaut: {e}")

    def create_default_groups(self):
        """
        Crée les groupes d'utilisateurs par défaut avec leurs permissions
        """
        from django.contrib.auth.models import Group, Permission
        from django.contrib.contenttypes.models import ContentType
        from .models import Submission, Document, CTDModule, CTDSection

        # Définir les groupes et leurs permissions
        groups_permissions = {
            'CTD_Administrators': [
                'add_submission', 'change_submission', 'delete_submission', 'view_submission',
                'add_document', 'change_document', 'delete_document', 'view_document',
                'add_ctdmodule', 'change_ctdmodule', 'delete_ctdmodule', 'view_ctdmodule',
                'add_ctdsection', 'change_ctdsection', 'delete_ctdsection', 'view_ctdsection',
            ],
            'CTD_Editors': [
                'add_submission', 'change_submission', 'view_submission',
                'add_document', 'change_document', 'view_document',
                'view_ctdmodule', 'view_ctdsection',
            ],
            'CTD_Viewers': [
                'view_submission', 'view_document', 'view_ctdmodule', 'view_ctdsection',
            ]
        }

        for group_name, permission_codenames in groups_permissions.items():
            group, created = Group.objects.get_or_create(name=group_name)

            if created:
                logger.info(f"Groupe '{group_name}' créé")

                # Ajouter les permissions au groupe
                for codename in permission_codenames:
                    try:
                        permission = Permission.objects.get(codename=codename)
                        group.permissions.add(permission)
                    except Permission.DoesNotExist:
                        logger.warning(f"Permission '{codename}' non trouvée pour le groupe '{group_name}'")

                logger.info(f"Permissions ajoutées au groupe '{group_name}'")

    def initialize_ctd_structure(self):
        """
        Initialise la structure CTD de base si elle n'existe pas
        """
        from .models import CTDModule, CTDSection
        from .utils import CTDStructureGenerator

        # Vérifier si la structure existe déjà
        if CTDModule.objects.exists():
            logger.info("Structure CTD déjà initialisée")
            return

        try:
            generator = CTDStructureGenerator()
            modules = generator.initialize_default_structure()
            logger.info(f"Structure CTD initialisée avec {len(modules)} modules")

        except Exception as e:
            logger.error(f"Erreur lors de l'initialisation de la structure CTD: {e}")

    def create_default_superuser(self):
        """
        Crée un super utilisateur par défaut si aucun n'existe
        (Utile pour le développement et les tests)
        """
        from django.contrib.auth.models import User
        from django.conf import settings

        # Ne créer un super utilisateur par défaut qu'en mode DEBUG
        if not settings.DEBUG:
            return

        if User.objects.filter(is_superuser=True).exists():
            return

        try:
            admin_user = User.objects.create_superuser(
                username='admin',
                email='admin@ctd-submission.local',
                password='admin123',
                first_name='Administrator',
                last_name='CTD System'
            )
            logger.info(f"Super utilisateur par défaut créé: {admin_user.username}")

        except Exception as e:
            logger.error(f"Erreur lors de la création du super utilisateur: {e}")

    def initialize_ai_components(self):
        """
        Initialise les composants d'analyse IA
        """
        try:
            # Charger les modèles d'analyse de texte
            self.load_nlp_models()

            # Initialiser le cache des analyseurs
            self.setup_analyzer_cache()

            logger.info("Composants IA initialisés avec succès")

        except Exception as e:
            logger.warning(f"Impossible d'initialiser les composants IA: {e}")

    def load_nlp_models(self):
        """
        Charge les modèles de traitement du langage naturel
        """
        try:
            # Essayer de charger NLTK
            import nltk
            nltk.download('punkt', quiet=True)
            nltk.download('stopwords', quiet=True)
            nltk.download('wordnet', quiet=True)

            logger.info("Modèles NLTK chargés")

        except ImportError:
            logger.warning("NLTK non disponible - analyse de texte limitée")

        try:
            # Essayer de charger spaCy (si disponible)
            import spacy
            # Tentative de chargement du modèle français
            try:
                nlp = spacy.load("fr_core_news_sm")
                logger.info("Modèle spaCy français chargé")
            except OSError:
                logger.info("Modèle spaCy français non disponible")

        except ImportError:
            logger.info("spaCy non disponible")

    def setup_analyzer_cache(self):
        """
        Configure le cache pour les analyseurs
        """
        from django.core.cache import cache

        # Initialiser les paramètres de cache pour l'analyse
        cache_config = {
            'ai_analysis_cache_timeout': 3600,  # 1 heure
            'document_extraction_cache_timeout': 1800,  # 30 minutes
            'template_cache_timeout': 600,  # 10 minutes
        }

        for key, value in cache_config.items():
            cache.set(f'ctd_config_{key}', value, timeout=None)

        logger.info("Cache des analyseurs configuré")

    def get_version(self):
        """
        Retourne la version de l'application
        """
        return "1.0.0"

    def get_info(self):
        """
        Retourne les informations sur l'application
        """
        return {
            'name': self.verbose_name,
            'version': self.get_version(),
            'description': 'Système de soumission CTD intelligent avec analyse IA',
            'author': 'CTD Submission Team',
            'features': [
                'Génération automatique de structure CTD',
                'Analyse IA des documents',
                'Templates dynamiques',
                'Support multi-régions (EMA, FDA, HC, MHRA)',
                'Interface utilisateur moderne',
                'Gestion collaborative'
            ]
        }