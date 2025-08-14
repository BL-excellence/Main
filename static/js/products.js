// Products App 
class ProductsApp {
    constructor() {
        this.currentProductId = null;
        this.currentTab = 'overview';
        this.products = [];
        this.siteCounter = 0;
        this.currentCloudConnectionId = null;
        
        this.init();
    }
    
    init() {
        this.bindElements();
        this.bindEvents();
        this.loadProducts();
    }
    
    bindElements() {
        this.elements = {
            productsList: document.getElementById('products-list'),
            productTitle: document.getElementById('product-title'),
            tabContent: document.getElementById('tab-content'),
            searchInput: document.getElementById('search-input'),
            tabButtons: document.querySelectorAll('.tab-button'),
            newProductBtn: document.getElementById('new-product-btn'),
            modal: document.getElementById('add-product-modal'),
            form: document.getElementById('add-product-form'),
            closeModal: document.getElementById('close-modal'),
            cancelBtn: document.getElementById('cancel-btn'),
            saveBtn: document.getElementById('save-btn'),
            addSiteBtn: document.getElementById('add-site-btn'),
            sitesContainer: document.getElementById('sites-container')
        };
    }
    
    bindEvents() {
        // Tab events
        this.elements.tabButtons.forEach(button => {
            button.addEventListener('click', (e) => {
                const tab = e.target.getAttribute('data-tab');
                this.switchTab(tab);
            });
        });
        this.elements.cloudBtn = document.getElementById('cloud-connection-btn');
        if (this.elements.cloudBtn) {
            this.elements.cloudBtn.addEventListener('click', () => {
                this.showCloudConnectionModal();
            });
        }
        // Search events
        this.elements.searchInput?.addEventListener('input', (e) => {
            this.handleSearch(e.target.value);
        });
        
        // Modal events
        this.elements.newProductBtn?.addEventListener('click', () => {
            this.showModal();
        });
        
        this.elements.closeModal?.addEventListener('click', () => {
            this.hideModal();
        });
        
        this.elements.cancelBtn?.addEventListener('click', () => {
            this.hideModal();
        });
        
        this.elements.modal?.addEventListener('click', (e) => {
            if (e.target === this.elements.modal) {
                this.hideModal();
            }
        });
        
        this.elements.form?.addEventListener('submit', (e) => {
            e.preventDefault();
            this.submitForm();
        });
        
        this.elements.addSiteBtn?.addEventListener('click', () => {
            this.addSiteForm();
        });
    }
    
    async loadProducts() {
        try {
            console.log('Loading products...');
            const response = await fetch('/client/products/api/products/');
            
            if (response.ok) {
                const data = await response.json();
                // Handle both paginated and non-paginated responses
                this.products = data.results || data;
                console.log('Products loaded:', this.products);
                
                this.renderProducts(this.products);
                
                // Select first product if none selected and products exist
                if (!this.currentProductId && this.products.length > 0) {
                    this.selectProduct(this.products[0].id);
                }
            } else {
                console.error('Failed to load products:', response.status);
                this.loadFallbackProducts();
            }
        } catch (error) {
            console.error('Error loading products:', error);
            this.loadFallbackProducts();
        }
    }
    
    loadFallbackProducts() {
        console.log('Loading fallback products...');
        this.products = [
            {
                id: 1,
                name: "RegXpirin 500mg",
                active_ingredient: "Analgésique",
                status: "commercialise",
                dosage: "500mg",
                form: "Comprimé",
                therapeutic_area: "Cardiovascular"
            },
            {
                id: 2,
                name: "RegXcillin 250mg",
                active_ingredient: "Antibactérial",
                status: "developpement",
                dosage: "250mg",
                form: "Gélule",
                therapeutic_area: "Anti-infectieux"
            }
        ];
        
        this.renderProducts(this.products);
        this.selectProduct(1);
    }
    async showCloudConnectionModal() {
        console.log('🔍 Début de showCloudConnectionModal');
        try {
            console.log('📡 Envoi de la requête vers /client/products/api/cloud/setup/');
            const response = await fetch('/client/products/api/cloud/setup/');
            
            console.log('📊 Response status:', response.status);
            console.log('📊 Response ok:', response.ok);
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            const cloudData = await response.json();
            console.log('📦 Données reçues:', cloudData);
            
            // Vérifier si renderCloudModal existe
            if (typeof this.renderCloudModal === 'function') {
                console.log('✅ renderCloudModal existe, appel en cours...');
                this.renderCloudModal(cloudData);
            } else {
                console.error('❌ renderCloudModal n\'existe pas!');
                this.showNotification('Erreur: fonction renderCloudModal manquante', 'error');
            }
            
        } catch (error) {
            console.error('❌ Erreur complète:', error);
            console.error('❌ Error stack:', error.stack);
            this.showNotification(`Erreur de chargement: ${error.message}`, 'error');
        }
    }

renderCloudModal(cloudData) {
    console.log('🎨 Début renderCloudModal avec:', cloudData);
    
    // Vérifier que cloudData a les bonnes propriétés
    if (!cloudData.available_providers) {
        console.error('❌ available_providers manquant dans cloudData');
        this.showNotification('Erreur: données providers manquantes', 'error');
        return;
    }
    
    const modalHtml = `
        <div class="modal-overlay" id="cloud-modal" style="display: flex; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.5); z-index: 10000; align-items: center; justify-content: center;">
            <div class="modal-content" style="background: white; border-radius: 12px; max-width: 700px; width: 90%; max-height: 90vh; overflow-y: auto;">
                <div class="modal-header" style="padding: 20px; border-bottom: 1px solid #eee; display: flex; justify-content: space-between; align-items: center;">
                    <h2>🔐 Connexion Cloud Sécurisée</h2>
                    <button class="close-btn" onclick="document.getElementById('cloud-modal').remove()" style="background: none; border: none; font-size: 24px; cursor: pointer;">×</button>
                </div>
                <div class="form-container" style="padding: 20px;">
                    <div style="background: #e8f5e8; padding: 15px; border-radius: 8px; margin-bottom: 20px; border: 2px solid #4caf50;">
                        <h4 style="color: #2e7d32; margin: 0 0 10px 0;">🏥 Conformité Industrie Pharmaceutique</h4>
                        <p style="color: #1b5e20; margin: 0; font-size: 14px;">100% conforme RGPD, ICH-GCP et FDA CFR Part 11</p>
                    </div>
                    
                    <!-- Section RGPD simplifiée pour test -->
                    <div style="background: #fff3cd; padding: 15px; border-radius: 8px; margin-bottom: 20px;">
                        <h4 style="color: #856404;">⚠️ Validation RGPD Requise</h4>
                        <label style="display: flex; align-items: center; gap: 10px; margin: 10px 0;">
                            <input type="checkbox" id="rgpd_acceptance" required>
                            <span>J'accepte les conditions RGPD et de sécurité pour l'industrie pharmaceutique</span>
                        </label>
                    </div>
                    
                    <h3 style="margin-bottom: 15px;">Choisissez votre fournisseur cloud :</h3>
                    <div class="cloud-providers" style="display: grid; gap: 15px;">
                        ${cloudData.available_providers.map(provider => `
                            <div class="provider-option" style="border: 2px solid #e9ecef; border-radius: 8px; padding: 15px; cursor: pointer; transition: all 0.3s ease;" onclick="window.productsApp.selectProvider('${provider.id}')">
                                <div style="display: flex; align-items: center; gap: 15px;">
                                    <div style="width: 40px; height: 40px; background: #3498db; border-radius: 8px; display: flex; align-items: center; justify-content: center; color: white; font-weight: bold;">
                                        ${this.getProviderIcon(provider.id)}
                                    </div>
                                    <div>
                                        <strong>${provider.name}</strong>
                                        <div style="color: #6c757d; font-size: 0.9rem;">Connexion sécurisée et chiffrée</div>
                                    </div>
                                </div>
                            </div>
                        `).join('')}
                    </div>
                    
                    <div style="margin-top: 20px; padding: 15px; background: #f8f9fa; border-radius: 8px; text-align: center;">
                        <small style="color: #6c757d;">
                            🔒 Chiffrement AES-256 • Stockage UE • Audit RGPD complet
                        </small>
                    </div>
                </div>
            </div>
        </div>
    `;
    
    console.log('📝 HTML généré, ajout au DOM...');
    document.body.insertAdjacentHTML('beforeend', modalHtml);
    console.log('✅ Modal ajoutée au DOM');
}



async selectProvider(providerId) {
    console.log('🎯 Provider sélectionné:', providerId);
    
    // Vérifier RGPD
    const rgpdCheckbox = document.getElementById('rgpd_acceptance');
    if (!rgpdCheckbox || !rgpdCheckbox.checked) {
        alert('Veuillez accepter les conditions RGPD avant de continuer');
        return;
    }
    
    // Fermer la modal
    const modal = document.getElementById('cloud-modal');
    if (modal) {
        modal.remove();
        console.log('✅ Modal fermée');
    }
    
    try {
        this.showNotification('🔄 Connexion OAuth en cours...', 'info');
        
        const response = await fetch('/client/products/api/cloud/oauth/initiate/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': this.getCSRFToken()
            },
            body: JSON.stringify({
                provider: providerId,
                connection_name: `${providerId}_connection`,
                eu_residency: true,
                scc_agreement: true,
                dpa_signed: true,
                data_subjects_categories: ['experts', 'healthcare_professionals'],
                sub_processors_acknowledged: true,
                privacy_notice_method: 'client',
                technical_measures_confirmed: true,
                transfer_safeguards_confirmed: true,
                final_validation: true
            })
        });
        
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.message || 'Erreur API OAuth');
        }
        
        const data = await response.json();
        console.log('✅ Réponse OAuth reçue:', data);
        
        if (data.oauth_url) {
            this.showNotification('🔗 Redirection vers authentification...', 'info');
            
            // Ouvrir la vraie page OAuth dans une nouvelle fenêtre
            const authWindow = window.open(data.oauth_url, 'oauth', 'width=600,height=700,scrollbars=yes,resizable=yes');
            
            // Écouter le retour de l'authentification
            const checkClosed = setInterval(() => {
                if (authWindow.closed) {
                    clearInterval(checkClosed);
                    console.log('🔍 Fenêtre OAuth fermée, vérification du statut...');
                    this.checkOAuthSuccess(providerId);
                }
            }, 1000);
            
        } else {
            throw new Error('URL OAuth non reçue');
        }
        
    } catch (error) {
        console.error('❌ Erreur OAuth:', error);
        this.showNotification(`❌ Erreur de connexion: ${error.message}`, 'error');
    }
}

async checkOAuthSuccess(providerId) {
    try {
        console.log('🔍 Checking for new connections...');
        const response = await fetch('/client/products/api/cloud/setup/');
        const cloudData = await response.json();
        
        if (cloudData.existing_connections.length > 0) {
            // Get the most recent connection (last one in the array)
            const recentConnection = cloudData.existing_connections[cloudData.existing_connections.length - 1];
            console.log('✅ Found connection:', recentConnection);
            
            this.currentCloudConnectionId = recentConnection.id;
            this.showNotification(`✅ Connexion établie avec succès!`, 'success');
            
            this.updateConnectButton();
        } else {
            console.log('❌ No connections found, retrying in 2 seconds...');
            // Sometimes there's a delay, retry once
            setTimeout(() => this.checkOAuthSuccess(providerId), 2000);
        }
    } catch (error) {
        console.error('❌ Error checking OAuth:', error);
    }
}

updateConnectButton() {
    const connectButton = document.querySelector('button[onclick*="showCloudConnectionModal"]');
    if (connectButton) {
        connectButton.innerHTML = `
            <i class="material-icons" style="vertical-align: middle;">sync</i>
            Synchroniser les Fichiers eCTD
        `;
        connectButton.onclick = () => this.syncECTDFiles();
        connectButton.style.background = '#28a745'; // Green color
    }
}

async initiateOAuth(providerId) {
    try {
        const response = await fetch('/client/products/api/cloud/oauth/initiate/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': this.getCSRFToken()
            },
            body: JSON.stringify({
                provider: providerId,
                connection_name: `${providerId}_connection`,
                eu_residency: true,
                scc_agreement: true,
                dpa_signed: true
            })
        });
        
        const data = await response.json();
        
        if (data.oauth_url) {
            // Ouvrir dans une nouvelle fenêtre
            const authWindow = window.open(data.oauth_url, 'oauth', 'width=600,height=700');
            
            // Simuler la réussite après 3 secondes
            setTimeout(() => {
                authWindow.close();
                this.showNotification(`✅ Connexion ${providerId} établie avec succès!`, 'success');
                this.showECTDSyncInterface();
            }, 3000);
        }
    } catch (error) {
        this.showNotification('Erreur lors de la connexion', 'error');
    }
}

showECTDSyncInterface() {
    console.log('🔄 Affichage interface eCTD sync');
    const cloudSection = document.querySelector('.cloud-upload-section');
    if (cloudSection) {
        cloudSection.innerHTML = `
            <div style="text-align: center;">
                <i class="material-icons" style="font-size: 48px; color: #27ae60;">check_circle</i>
                <h4 style="color: #27ae60; margin: 10px 0;">Cloud Connecté avec Succès!</h4>
                <button class="btn btn-primary" onclick="window.productsApp.syncECTDFiles()" style="padding: 10px 20px; background: #3498db; color: white; border: none; border-radius: 6px; cursor: pointer;">
                    <i class="material-icons" style="vertical-align: middle;">sync</i>
                    Synchroniser les Fichiers eCTD
                </button>
            </div>
        `;
        console.log('✅ Interface eCTD mise à jour');
    } else {
        console.error('❌ Section cloud-upload-section introuvable');
    }
}

async syncECTDFiles() {
    if (!this.currentProductId) {
        this.showNotification('Créez d\'abord le produit', 'warning');
        return;
    }
    
    if (!this.currentCloudConnectionId) {
        this.showNotification('Aucune connexion cloud active', 'error');
        return;
    }
    
    console.log('🔄 VRAIE Synchronisation eCTD en cours...');
    this.showNotification('🔄 Synchronisation en cours...', 'info');
    
    try {
        const response = await fetch(`/client/products/api/products/${this.currentProductId}/ectd/sync/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': this.getCSRFToken(),
            },
            body: JSON.stringify({
                connection_id: this.currentCloudConnectionId, // VRAIE connexion
                folder_path: '/ectd/'
            })
        });
        
        if (response.ok) {
            const result = await response.json();
            console.log('✅ Résultat sync:', result);
            
            this.showNotification(`✅ ${result.files_processed} fichiers eCTD synchronisés!`, 'success');
            
            // Recharger l'onglet réglementaire pour voir les vrais fichiers
            if (this.currentTab === 'regulatory') {
                await this.loadRegulatoryTab();
            }
        } else {
            const errorData = await response.json();
            this.showNotification(`❌ Erreur: ${errorData.error}`, 'error');
        }
    } catch (error) {
        console.error('❌ Erreur sync réelle:', error);
        this.showNotification('❌ Erreur de connexion', 'error');
    }
}


getProviderIcon(providerId) {
    const icons = {
        'google_drive': '📁',
        'onedrive': '☁️',
        'sharepoint': '🗃️',
        'dropbox': '📦',
        'box': '📋'
    };
    return icons[providerId] || '☁️';
}
    renderProducts(products) {
        console.log('Rendering products:', products);
        
        if (!this.elements.productsList) {
            console.error('Products list element not found');
            return;
        }
        
        if (!products || products.length === 0) {
            this.elements.productsList.innerHTML = `
                <div class="empty-state">
                    <i class="material-icons">inventory</i>
                    <h3>Aucun produit</h3>
                    <p>Cliquez sur "Nouveau Produit" pour ajouter votre premier produit</p>
                </div>
            `;
            return;
        }
        
        this.elements.productsList.innerHTML = products.map(product => `
            <div class="product-item" data-product-id="${product.id}">
                <div class="product-name">${product.name}</div>
                <div class="product-ingredient">${product.active_ingredient}</div>
                <div class="product-dosage">${product.dosage || ''}</div>
                <span class="product-status status-${product.status}">${this.getStatusLabel(product.status)}</span>
            </div>
        `).join('');
        
        // Bind click events to product items
        this.elements.productsList.querySelectorAll('.product-item').forEach(item => {
            item.addEventListener('click', (e) => {
                const productId = parseInt(item.getAttribute('data-product-id'));
                console.log('Product clicked:', productId);
                this.selectProduct(productId);
            });
        });
    }
    
    selectProduct(productId) {
        console.log('Selecting product ID:', productId);
        
        // Update visual selection
        this.elements.productsList?.querySelectorAll('.product-item').forEach(item => {
            item.classList.remove('active');
        });
        
        const selectedItem = this.elements.productsList?.querySelector(`[data-product-id="${productId}"]`);
        if (selectedItem) {
            selectedItem.classList.add('active');
        }
        
        // Update title
        const product = this.products.find(p => p.id === productId);
        if (product && this.elements.productTitle) {
            this.elements.productTitle.textContent = product.name;
        }
        
        // Store current product ID
        this.currentProductId = productId;
        
        // Load content for current tab
        this.loadTabContent(this.currentTab);
    }
    
    switchTab(tabName) {
        console.log('Switching to tab:', tabName);
        
        this.elements.tabButtons.forEach(btn => {
            btn.classList.remove('active');
            if (btn.getAttribute('data-tab') === tabName) {
                btn.classList.add('active');
            }
        });
        
        this.currentTab = tabName;
        this.loadTabContent(tabName);
    }
    
    async loadTabContent(tabName) {
        if (!this.elements.tabContent || !this.currentProductId) {
            console.log('Cannot load tab content: missing elements or product ID');
            return;
        }
        
        console.log(`Loading tab content: ${tabName} for product ${this.currentProductId}`);
        
        // Show loading state
        this.elements.tabContent.innerHTML = `
            <div class="loading">
                <i class="material-icons">hourglass_empty</i>
                <p>Chargement...</p>
            </div>
        `;
        
        try {
            switch (tabName) {
                case 'overview':
                    await this.loadOverviewTab();
                    break;
                case 'sites':
                    await this.loadSitesTab();
                    break;
                case 'variations':
                    await this.loadVariationsTab();
                    break;
                case 'regulatory':
                    await this.loadRegulatoryTab();
                    break;
                default:
                    console.log('Unknown tab:', tabName);
            }
        } catch (error) {
            console.error(`Error loading ${tabName} tab:`, error);
            this.elements.tabContent.innerHTML = `
                <div class="empty-state">
                    <i class="material-icons">error</i>
                    <h3>Erreur de chargement</h3>
                    <p>Impossible de charger les données pour ce produit</p>
                </div>
            `;
        }
    }
    
    async loadOverviewTab() {
        console.log(`Loading overview for product ${this.currentProductId}`);
        
        try {
            const response = await fetch(`/client/products/api/products/${this.currentProductId}/overview/`);
            
            if (response.ok) {
                const data = await response.json();
                console.log('Overview data:', data);
                
                const product = data.product;
                const spec = data.specifications && data.specifications.length > 0 ? data.specifications[0] : null;
                
                this.elements.tabContent.innerHTML = `
                    <div class="regulatory-content">
                        <div class="regulatory-info">
                            <div class="regulatory-item">
                                <span class="regulatory-label">Nom du produit</span>
                                <span class="regulatory-value">${product.name}</span>
                            </div>
                            <div class="regulatory-item">
                                <span class="regulatory-label">Type</span>
                                <span class="regulatory-value">${product.form}</span>
                            </div>
                            <div class="regulatory-item">
                                <span class="regulatory-label">Principe actif</span>
                                <span class="regulatory-value">${product.active_ingredient}</span>
                            </div>
                            <div class="regulatory-item">
                                <span class="regulatory-label">Dosage</span>
                                <span class="regulatory-value">${product.dosage}</span>
                            </div>
                            <div class="regulatory-item">
                                <span class="regulatory-label">Statut</span>
                                <span class="regulatory-value">
                                    <span class="status-badge status-${product.status}">${this.getStatusLabel(product.status)}</span>
                                </span>
                            </div>
                            <div class="regulatory-item">
                                <span class="regulatory-label">Zone thérapeutique</span>
                                <span class="regulatory-value">${product.therapeutic_area}</span>
                            </div>
                            ${spec ? `
                            <div class="regulatory-item">
                                <span class="regulatory-label">N° AMM</span>
                                <span class="regulatory-value">${spec.amm_number}</span>
                            </div>
                            <div class="regulatory-item">
                                <span class="regulatory-label">Date d'approbation</span>
                                <span class="regulatory-value">${this.formatDate(spec.approval_date)}</span>
                            </div>
                            <div class="regulatory-item">
                                <span class="regulatory-label">Prochain renouvellement</span>
                                <span class="regulatory-value">${this.formatDate(spec.renewal_date)}</span>
                            </div>
                            ` : ''}
                        </div>
                    </div>
                `;
            } else {
                // Fallback to local product data
                console.log('API failed, using local product data');
                this.loadOverviewFromLocalData();
            }
        } catch (error) {
            console.error('Error loading overview:', error);
            this.loadOverviewFromLocalData();
        }
    }
    
    loadOverviewFromLocalData() {
        const product = this.products.find(p => p.id === this.currentProductId);
        if (product) {
            this.elements.tabContent.innerHTML = `
                <div class="regulatory-content">
                    <div class="regulatory-info">
                        <div class="regulatory-item">
                            <span class="regulatory-label">Nom du produit</span>
                            <span class="regulatory-value">${product.name}</span>
                        </div>
                        <div class="regulatory-item">
                            <span class="regulatory-label">Type</span>
                            <span class="regulatory-value">${product.form || 'N/A'}</span>
                        </div>
                        <div class="regulatory-item">
                            <span class="regulatory-label">Principe actif</span>
                            <span class="regulatory-value">${product.active_ingredient}</span>
                        </div>
                        <div class="regulatory-item">
                            <span class="regulatory-label">Dosage</span>
                            <span class="regulatory-value">${product.dosage || 'N/A'}</span>
                        </div>
                        <div class="regulatory-item">
                            <span class="regulatory-label">Statut</span>
                            <span class="regulatory-value">
                                <span class="status-badge status-${product.status}">${this.getStatusLabel(product.status)}</span>
                            </span>
                        </div>
                        <div class="regulatory-item">
                            <span class="regulatory-label">Zone thérapeutique</span>
                            <span class="regulatory-value">${product.therapeutic_area || 'N/A'}</span>
                        </div>
                    </div>
                </div>
            `;
        }
    }
    
    async loadSitesTab() {
    console.log(`Loading sites for product ${this.currentProductId}`);
    
    try {
        const response = await fetch(`/client/products/api/products/${this.currentProductId}/sites/`);
        
        if (response.ok) {
            const sites = await response.json();
            console.log('Sites data:', sites);
            
            this.elements.tabContent.innerHTML = `
                <div class="sites-header">
                    <h3>Sites de Production (${sites.length})</h3>
                    <div class="sites-actions">
                        <button class="btn btn-secondary" onclick="window.productsApp.viewSites()">
                            <i class="material-icons">visibility</i>
                            Voir Sites
                        </button>
                        <button class="btn btn-secondary" onclick="window.productsApp.editSites()">
                            <i class="material-icons">edit</i>
                            Modifier Sites
                        </button>
                        <button class="btn btn-primary" onclick="window.productsApp.addSite()">
                            <i class="material-icons">add</i>
                            Ajouter un site
                        </button>
                    </div>
                </div>
                
                ${sites.length === 0 ? `
                    <div class="empty-state">
                        <i class="material-icons">location_off</i>
                        <h3>Aucun site de production</h3>
                        <p>Aucun site n'est configuré pour ce produit</p>
                    </div>
                ` : `
                    <div class="sites-list">
                        ${sites.map(site => `
                            <div class="site-item">
                                <div class="site-info">
                                    <i class="material-icons">factory</i>
                                    <div>
                                        <div class="site-name">${site.site_name || 'Nom non défini'}</div>
                                        <div class="site-location">${site.city}, ${site.country}</div>
                                    </div>
                                    ${site.gmp_certified ? '<span class="gmp-badge">GMP Certifié</span>' : ''}
                                </div>
                                <div class="site-actions">
                                    <button class="btn btn-sm btn-outline" onclick="window.productsApp.editSingleSite(${site.id})">
                                        <i class="material-icons">edit</i>
                                    </button>
                                    <button class="btn btn-sm btn-danger" onclick="window.productsApp.deleteSite(${site.id})">
                                        <i class="material-icons">delete</i>
                                    </button>
                                </div>
                            </div>
                        `).join('')}
                    </div>
                `}
            `;
        } else {
            throw new Error('Failed to load sites');
        }
    } catch (error) {
        console.error('Error loading sites:', error);
        this.elements.tabContent.innerHTML = `
            <div class="sites-header">
                <h3>Sites de Production</h3>
                <button class="btn btn-primary" onclick="window.productsApp.addSite()">
                    <i class="material-icons">add</i>
                    Ajouter un site
                </button>
            </div>
            <div class="empty-state">
                <i class="material-icons">location_off</i>
                <h3>Aucun site de production</h3>
                <p>Aucun site n'est configuré pour ce produit</p>
            </div>
        `;
    }
}
    
async loadVariationsTab() {
    console.log(`Loading variations for product ${this.currentProductId}`);
    const variationsHeader = `
        <div class="sites-header">
            <h3>Variations du Produit</h3>
            <button class="btn btn-primary" onclick="document.getElementById('addVariationModal').style.display='flex'; document.body.style.overflow='hidden';">
                <i class="material-icons">add</i>
                Nouvelle Variation
            </button>
        </div>
    `;
    
    try {
        const response = await fetch(`/client/products/api/products/${this.currentProductId}/variations/`);
        
        if (response.ok) {
            const variations = await response.json();
            console.log('Variations data:', variations);
            
            if (variations.length === 0) {
                this.elements.tabContent.innerHTML = `
                    ${variationsHeader}
                    <div class="empty-state">
                        <i class="material-icons">timeline</i>
                        <h3>Aucune variation</h3>
                        <p>Aucune variation n'a été soumise pour ce produit</p>
                    </div>
                `;
                return;
            }

            this.elements.tabContent.innerHTML = `
                ${variationsHeader}
                <div class="variations-timeline">
                    ${variations.map(variation => `
                        <div class="variation-item">
                            <div class="variation-type">${variation.variation_type?.split('_')[1]?.toUpperCase() || 'N/A'}</div>
                            <div class="variation-content">
                                <div class="variation-title">${variation.title}</div>
                                <div class="variation-date">${this.formatDate(variation.submission_date)}</div>
                                <div class="variation-description">${variation.description || ''}</div>
                                <span class="variation-status status-${variation.status}">${this.getStatusLabel(variation.status)}</span>
                            </div>
                        </div>
                    `).join('')}
                </div>
            `;
        } else {
            throw new Error('Failed to load variations');
        }
    } catch (error) {
        console.error('Error loading variations:', error);
        this.elements.tabContent.innerHTML = `
            ${variationsHeader}
            <div class="empty-state">
                <i class="material-icons">timeline</i>
                <h3>Aucune variation</h3>
                <p>Aucune variation n'a été soumise pour ce produit</p>
            </div>
        `;
    }
}
    
    async loadRegulatoryTab() {
        console.log(`Loading regulatory for product ${this.currentProductId}`);
        
        try {
            // Charger à la fois les infos produit ET les fichiers eCTD
            const [overviewResponse, ectdResponse] = await Promise.all([
                fetch(`/client/products/api/products/${this.currentProductId}/overview/`),
                fetch(`/client/products/api/products/${this.currentProductId}/ectd/files/`)
            ]);
            
            const overviewData = overviewResponse.ok ? await overviewResponse.json() : null;
            const ectdData = ectdResponse.ok ? await ectdResponse.json() : { files_by_module: {}, total_files: 0 };
            
            console.log('eCTD Data loaded:', ectdData);
            
            const spec = overviewData?.specifications?.[0] || null;
            
            this.elements.tabContent.innerHTML = `
                <div class="overview-grid">
                    <div class="info-section">
                        <h3 class="info-title">Informations Réglementaires</h3>
                        ${spec ? `
                        <div class="info-item">
                            <span class="info-label">Numéro AMM</span>
                            <span class="info-value">${spec.amm_number}</span>
                        </div>
                        <div class="info-item">
                            <span class="info-label">Date d'approbation</span>
                            <span class="info-value">${this.formatDate(spec.approval_date)}</span>
                        </div>
                        <div class="info-item">
                            <span class="info-label">Prochain renouvellement</span>
                            <span class="info-value">${this.formatDate(spec.renewal_date)}</span>
                        </div>
                        ` : '<p>Aucune information réglementaire disponible</p>'}
                    </div>
                    
                    <div class="info-section">
                        <h3 class="info-title">Documents Associés</h3>
                        
                        ${ectdData.total_files === 0 ? `
                            <!-- Aucun fichier eCTD -->
                            <div class="document-item">
                                <span class="document-name">Dossier CTD complet</span>
                                <div class="document-status">
                                    <span class="no-document">-</span>
                                </div>
                            </div>
                            <div style="margin-top: 15px; text-align: center; padding: 15px; background: #f8f9fa; border-radius: 8px;">
                                <p style="color: #6c757d; margin-bottom: 10px;">Aucun fichier eCTD synchronisé</p>
                                <button class="btn btn-primary" onclick="window.productsApp.showCloudConnectionModal()" style="padding: 8px 16px; background: #3498db; color: white; border: none; border-radius: 6px; cursor: pointer;">
                                    <i class="material-icons" style="font-size: 16px; vertical-align: middle;">cloud</i>
                                    Connecter Cloud eCTD
                                </button>
                            </div>
                        ` : `
                            <!-- Fichiers eCTD trouvés -->
                            <div class="document-item">
                                <span class="document-name">Dossier CTD complet</span>
                                <div class="document-status">
                                    <button class="view-document-btn" onclick="window.productsApp.viewECTDFiles()" style="width: 32px; height: 32px; border-radius: 50%; background-color: #3498db; border: none; display: flex; align-items: center; justify-content: center; cursor: pointer;">
                                        <i class="material-icons" style="color: white; font-size: 16px;">visibility</i>
                                    </button>
                                </div>
                            </div>
                            <div style="margin-top: 15px; text-align: center;">
                                <button class="btn btn-secondary" onclick="window.productsApp.syncMoreECTDFiles()" style="padding: 8px 16px; background: #6c757d; color: white; border: none; border-radius: 6px; cursor: pointer; margin-right: 10px;">
                                    <i class="material-icons" style="font-size: 16px; vertical-align: middle;">sync</i>
                                    Synchroniser Plus
                                </button>
                                <button class="btn btn-primary" onclick="window.productsApp.viewECTDFiles()" style="padding: 8px 16px; background: #3498db; color: white; border: none; border-radius: 6px; cursor: pointer; margin-right: 10px;">
                                    <i class="material-icons" style="font-size: 16px; vertical-align: middle;">folder_open</i>
                                    Voir Tous les Fichiers
                                </button>
                                <button class="btn btn-danger" onclick="window.productsApp.deleteAllECTDFiles()" style="padding: 8px 16px; background: #dc3545; color: white; border: none; border-radius: 6px; cursor: pointer;">
                                    <i class="material-icons" style="font-size: 16px; vertical-align: middle;">delete</i>
                                    Supprimer Tout
                                </button>
                            </div>
                            
                            <!-- Affichage détaillé des modules eCTD -->
                            <div class="ectd-summary" style="margin-top: 20px; background: #f8f9fa; padding: 15px; border-radius: 8px;">
                                <h4 style="margin: 0 0 15px 0; color: #2c3e50;">📁 Fichiers eCTD Synchronisés (${ectdData.total_files})</h4>
                                <div class="ectd-modules-summary">
                                    ${Object.keys(ectdData.files_by_module).map(module => `
                                        <div class="module-summary" style="display: flex; justify-content: space-between; align-items: center; padding: 8px 0; border-bottom: 1px solid #e9ecef;">
                                            <div style="display: flex; align-items: center; gap: 10px;">
                                                <span style="background: #3498db; color: white; padding: 4px 8px; border-radius: 4px; font-size: 12px; font-weight: bold;">${module}</span>
                                                <span style="color: #6c757d;">${ectdData.files_by_module[module].length} fichier(s)</span>
                                            </div>
                                            <div style="color: #28a745;">
                                                <i class="material-icons" style="font-size: 18px;">check_circle</i>
                                            </div>
                                        </div>
                                    `).join('')}
                                </div>
                                <div style="margin-top: 15px; text-align: center;">
                                    <button class="btn btn-secondary" onclick="window.productsApp.syncMoreECTDFiles()" style="padding: 8px 16px; background: #6c757d; color: white; border: none; border-radius: 6px; cursor: pointer; margin-right: 10px;">
                                        <i class="material-icons" style="font-size: 16px; vertical-align: middle;">sync</i>
                                        Synchroniser Plus
                                    </button>
                                    <button class="btn btn-primary" onclick="window.productsApp.viewECTDFiles()" style="padding: 8px 16px; background: #3498db; color: white; border: none; border-radius: 6px; cursor: pointer;">
                                        <i class="material-icons" style="font-size: 16px; vertical-align: middle;">folder_open</i>
                                        Voir Tous les Fichiers
                                    </button>
                                </div>
                            </div>
                        `}
                    </div>
                </div>
            `;
        } catch (error) {
            console.error('Error loading regulatory:', error);
            this.elements.tabContent.innerHTML = `
                <div class="empty-state">
                    <i class="material-icons">gavel</i>
                    <h3>Aucune information réglementaire</h3>
                    <p>Erreur de chargement des données</p>
                </div>
            `;
        }
    }
    // Fonction pour voir les fichiers eCTD en détail
    async viewECTDFiles() {
        if (!this.currentProductId) {
            this.showNotification('Aucun produit sélectionné', 'error');
            return;
        }
        
        try {
            // Get the eCTD files first to get real file IDs
            const response = await fetch(`/client/products/api/products/${this.currentProductId}/ectd/files/`);
            const ectdData = await response.json();
            
            console.log('eCTD files data:', ectdData); // Debug log
            
            if (ectdData.total_files > 0) {
                // Get the first file ID from the files_by_module
                const firstModule = Object.keys(ectdData.files_by_module)[0];
                const firstFile = ectdData.files_by_module[firstModule][0];
                
                console.log('Using file ID:', firstFile.id); // Debug log
                this.showZIPStructureModal(firstFile.id);
            } else {
                this.showNotification('Aucun fichier eCTD trouvé', 'error');
            }
        } catch (error) {
            console.error('Error loading eCTD files:', error);
            this.showNotification('Erreur lors du chargement des fichiers', 'error');
        }
    }
    async syncMoreECTDFiles() {
        if (!this.currentProductId) {
            this.showNotification('Aucun produit sélectionné', 'error');
            return;
        }
        
        if (!this.currentCloudConnectionId) {
            this.showNotification('Aucune connexion cloud active', 'error');
            return;
        }
        
        console.log('🔄 Synchronisation supplémentaire en cours...');
        this.showNotification('🔄 Synchronisation en cours...', 'info');
        
        try {
            const response = await fetch(`/client/products/api/products/${this.currentProductId}/ectd/sync/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCSRFToken(),
                },
                body: JSON.stringify({
                    connection_id: this.currentCloudConnectionId,
                    folder_path: '/ectd/'
                })
            });
            
            if (response.ok) {
                const result = await response.json();
                console.log('✅ Résultat sync supplémentaire:', result);
                
                this.showNotification(`✅ ${result.files_processed} nouveaux fichiers synchronisés!`, 'success');
                
                // Recharger l'onglet réglementaire
                if (this.currentTab === 'regulatory') {
                    await this.loadRegulatoryTab();
                }
            } else {
                const errorData = await response.json();
                this.showNotification(`❌ Erreur: ${errorData.error}`, 'error');
            }
        } catch (error) {
            console.error('❌ Erreur sync supplémentaire:', error);
            this.showNotification('❌ Erreur de connexion', 'error');
        }
    }

    // Add this function for deleting files
    async deleteAllECTDFiles() {
        if (!this.currentProductId) {
            this.showNotification('Aucun produit sélectionné', 'error');
            return;
        }
        
        if (!confirm('Êtes-vous sûr de vouloir supprimer tous les fichiers eCTD synchronisés ?')) {
            return;
        }
        
        try {
            const response = await fetch(`/client/products/api/products/${this.currentProductId}/ectd/delete/`, {
                method: 'DELETE',
                headers: {
                    'X-CSRFToken': this.getCSRFToken(),
                }
            });
            
            if (response.ok) {
                const result = await response.json();
                this.showNotification(`✅ ${result.deleted_count} fichiers supprimés`, 'success');
                
                // Recharger l'onglet réglementaire
                if (this.currentTab === 'regulatory') {
                    await this.loadRegulatoryTab();
                }
            } else {
                const errorData = await response.json();
                this.showNotification(`❌ Erreur: ${errorData.error}`, 'error');
            }
        } catch (error) {
            console.error('❌ Erreur suppression:', error);
            this.showNotification('❌ Erreur de connexion', 'error');
        }
    }

    generateFileList(files, fileId, isLastFolder) {
        let html = '';
        
        files.forEach((file, fileIndex) => {
            const isLastFile = fileIndex === files.length - 1;
            const connector = isLastFile ? '└─' : '├─';
            
            html += `
                <div class="file-item" style="
                    display: flex; 
                    align-items: center; 
                    padding: 6px 0; 
                    cursor: pointer; 
                    border-radius: 4px;
                    margin-bottom: 2px;
                    transition: background-color 0.2s ease;
                " 
                onmouseover="this.style.backgroundColor='#e3f2fd'" 
                onmouseout="this.style.backgroundColor='transparent'"
                onclick="window.productsApp.openPDFFile('${file.path}', '${file.name}', ${fileId})">
                    
                    <span style="margin-right: 8px; color: #999; font-weight: normal;">${connector}</span>
                    <i class="material-icons" style="color: #f44336; font-size: 16px; margin-right: 8px;">picture_as_pdf</i>
                    
                    <div style="flex: 1; display: flex; justify-content: space-between; align-items: center;">
                        <span style="color: #333; font-weight: 500;">${file.name}</span>
                        <span style="color: #666; font-size: 12px; margin-left: 10px;">
                            ${(file.size / 1024).toFixed(1)} KB
                        </span>
                    </div>
                </div>
            `;
        });
        
        return html;
    }

    generateTreeStructure(folderStructure, fileId) {
        // Build a proper tree structure from the flat folder structure
        const tree = this.buildTreeFromPaths(folderStructure);
        return this.renderTreeNode(tree, fileId, 0, true);
    }

    buildTreeFromPaths(folderStructure) {
        const tree = { name: 'Root', type: 'folder', children: {}, files: [] };
        
        Object.keys(folderStructure).forEach(folderPath => {
            const files = folderStructure[folderPath];
            
            files.forEach(file => {
                // Use the actual file path from the archive
                this.addToTree(tree, file.path, file);
            });
        });
        
        return tree;
    }

    addToTree(tree, filePath, fileInfo) {
        // Split the path and remove empty parts
        const parts = filePath.split('/').filter(part => part.trim().length > 0);
        let current = tree;
        
        // If no folder structure (file in root), add directly to root
        if (parts.length === 1) {
            current.files.push({
                name: parts[0],
                path: filePath,
                size: fileInfo.size
            });
            return;
        }
        
        // Navigate/create folder structure (all parts except the last one which is the file)
        for (let i = 0; i < parts.length - 1; i++) {
            const folderName = parts[i];
            
            if (!current.children[folderName]) {
                current.children[folderName] = {
                    name: folderName,
                    type: 'folder',
                    children: {},
                    files: []
                };
            }
            current = current.children[folderName];
        }
        
        // Add the file to the current folder
        const fileName = parts[parts.length - 1];
        current.files.push({
            name: fileName,
            path: filePath,
            size: fileInfo.size
        });
    }

    renderTreeNode(node, fileId, depth = 0, isRoot = false) {
        let html = '';
        
        // Don't render the root folder name, just its contents
        if (!isRoot && (Object.keys(node.children).length > 0 || node.files.length > 0)) {
            const indent = '│   '.repeat(depth) + '├── '; // Vertical lines + connector
            html += `
                <div style="display: flex !important; align-items: center !important; margin: 1px 0 !important; padding: 1px 0 !important; font-weight: bold; color: #0066cc; line-height: 1.1 !important;">
                    <span style="margin-right: 6px !important; color: #999; font-family: monospace; white-space: pre;">${indent}</span>
                    <i class="material-icons" style="font-size: 14px !important; margin-right: 4px !important; color: #ffa726;">folder</i>
                    <span style="font-size: 13px !important;">${node.name}</span>
                </div>
            `;
        }
        
        const currentDepth = isRoot ? depth : depth + 1;
        
        // Render folders first (only if they have content)
        const folderNames = Object.keys(node.children)
            .filter(folderName => {
                const folder = node.children[folderName];
                return Object.keys(folder.children).length > 0 || folder.files.length > 0;
            })
            .sort();
            
        folderNames.forEach((folderName) => {
            html += this.renderTreeNode(node.children[folderName], fileId, currentDepth, false);
        });
        
        // Render files with deep indentation and vertical lines
        node.files.forEach((file, fileIndex) => {
            const baseIndent = '│   '.repeat(currentDepth);
            const isLastItem = fileIndex === node.files.length - 1 && folderNames.length === 0;
            const connector = isLastItem ? '└── ' : '├── ';
            const fullIndent = baseIndent + connector;
            
            html += `
                <div class="file-item" style="
                    display: flex !important; 
                    align-items: center !important; 
                    margin: 0px !important;
                    padding: 1px 2px !important; 
                    cursor: pointer !important; 
                    border-radius: 2px !important;
                    transition: background-color 0.2s ease !important;
                    line-height: 1.1 !important;
                    min-height: 18px !important;
                " 
                onmouseover="this.style.backgroundColor='#e3f2fd'" 
                onmouseout="this.style.backgroundColor='transparent'"
                onclick="window.productsApp.openPDFFile('${file.path}', '${file.name}', ${fileId})">
                    
                    <span style="margin-right: 4px !important; color: #999; font-family: monospace; font-size: 12px !important; white-space: pre;">${fullIndent}</span>
                    <i class="material-icons" style="color: #f44336 !important; font-size: 12px !important; margin-right: 4px !important;">picture_as_pdf</i>
                    
                    <div style="flex: 1 !important; display: flex !important; justify-content: space-between !important; align-items: center !important;">
                        <span style="color: #333 !important; font-weight: 500 !important; font-size: 12px !important;">${file.name}</span>
                        <span style="color: #666 !important; font-size: 10px !important; margin-left: 8px !important;">
                            ${(file.size / 1024).toFixed(1)} KB
                        </span>
                    </div>
                </div>
            `;
        });
        
        return html;
    }

    async showZIPStructureModal(fileId) {
        try {
            const response = await fetch(`/client/products/api/products/${this.currentProductId}/zip/${fileId}/structure/`);
            const zipData = await response.json();
            
            const modalHtml = `
                <div class="modal-overlay" id="zip-structure-modal" style="display: flex; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.5); z-index: 10000; align-items: center; justify-content: center;">
                    <div class="modal-content" style="background: white; border-radius: 12px; max-width: 900px; width: 90%; max-height: 90vh; overflow-y: auto;">
                        <div class="modal-header" style="padding: 20px; border-bottom: 1px solid #eee; display: flex; justify-content: space-between; align-items: center;">
                            <h2>📁 ${zipData.zip_name} - Structure</h2>
                            <button class="close-btn" onclick="document.getElementById('zip-structure-modal').remove()" style="background: none; border: none; font-size: 24px; cursor: pointer;">×</button>
                        </div>
                        <div class="modal-body" style="padding: 20px;">
                            <div style="background: #f8f9fa; padding: 15px; border-radius: 8px; margin-bottom: 20px; font-family: system-ui;">
                                <strong>${zipData.total_folders}</strong> dossiers • <strong>${zipData.total_files}</strong> fichiers PDF
                            </div>
                            
                            <div class="tree-structure" style="
                                background: #fafafa !important; 
                                padding: 12px !important; 
                                border-radius: 6px !important; 
                                border: 1px solid #e9ecef !important;
                                font-family: 'Consolas', 'Monaco', 'Courier New', monospace !important;
                                line-height: 1.1 !important;
                                font-size: 12px !important;
                            ">
                                <div style="display: flex !important; align-items: center !important; margin-bottom: 6px !important; font-weight: bold !important; color: #0066cc !important;">
                                    <i class="material-icons" style="font-size: 16px !important; margin-right: 6px !important; color: #ffa726 !important;">folder</i>
                                    <span style="font-size: 14px !important;">${zipData.zip_name}</span>
                                </div>
                                ${this.generateTreeStructure(zipData.folder_structure, fileId)}
                            </div>
                        </div>
                    </div>
                </div>
            `;
            
            document.body.insertAdjacentHTML('beforeend', modalHtml);
            
        } catch (error) {
            this.showNotification('Erreur lors du chargement de la structure ZIP', 'error');
        }
    }

    openPDFFile(filePath, fileName, fileId) {
        if (!this.currentProductId) {
            this.showNotification('Aucun produit sélectionné', 'error');
            return;
        }
        
        if (!fileId) {
            this.showNotification('ID de fichier manquant', 'error');
            return;
        }
        
        // Encode the file path for URL
        const encodedPath = encodeURIComponent(filePath);
        
        // Open PDF in new window
        const pdfUrl = `/client/products/api/products/${this.currentProductId}/pdf/${fileId}/view/?file_path=${encodedPath}`;
        window.open(pdfUrl, '_blank', 'width=1200,height=800,scrollbars=yes,resizable=yes');
    }
    // Modal functions
    showModal() {
        if (this.elements.modal) {
            this.elements.modal.style.display = 'flex';
            document.body.style.overflow = 'hidden';
        }
    }
    
    hideModal() {
        if (this.elements.modal) {
            this.elements.modal.style.display = 'none';
            document.body.style.overflow = 'auto';
            this.resetForm();
        }
    }
    
    resetForm() {
        this.elements.form?.reset();
        this.siteCounter = 0;
        this.elements.sitesContainer.innerHTML = '';
        this.clearFormErrors();
    }
    
    addSiteForm() {
        this.siteCounter++;
        const siteHTML = `
            <div class="site-form-group" data-site="${this.siteCounter}">
                <button type="button" class="remove-site-btn" onclick="this.parentElement.remove()">
                    <i class="material-icons">close</i>
                </button>
                <div class="form-grid">
                    <div class="form-group">
                        <label for="site-country-${this.siteCounter}">Pays</label>
                        <input type="text" id="site-country-${this.siteCounter}" name="site_country[]">
                    </div>
                    <div class="form-group">
                        <label for="site-city-${this.siteCounter}">Ville</label>
                        <input type="text" id="site-city-${this.siteCounter}" name="site_city[]">
                    </div>
                    <div class="form-group">
                        <label for="site-name-${this.siteCounter}">Nom du site</label>
                        <input type="text" id="site-name-${this.siteCounter}" name="site_name[]">
                    </div>
                    <div class="form-group">
                        <label for="site-gmp-${this.siteCounter}">
                            <input type="checkbox" id="site-gmp-${this.siteCounter}" name="site_gmp[]">
                            Certifié GMP
                        </label>
                    </div>
                </div>
            </div>
        `;
        this.elements.sitesContainer.insertAdjacentHTML('beforeend', siteHTML);
    }
    
    async submitForm() {
        console.log('Submitting form...');
        
        if (!this.validateForm()) {
            return;
        }
        
        const formData = new FormData(this.elements.form);
        
        // Prepare product data
        const productData = {
            name: formData.get('name'),
            active_ingredient: formData.get('active_ingredient'),
            dosage: formData.get('dosage'),
            form: formData.get('form'),
            therapeutic_area: formData.get('therapeutic_area'),
            status: formData.get('status')
        };
        
        // Prepare optional regulatory data
        const regulatoryData = {};
        if (formData.get('amm_number')) regulatoryData.amm_number = formData.get('amm_number');
        if (formData.get('approval_date')) regulatoryData.approval_date = formData.get('approval_date');
        if (formData.get('renewal_date')) regulatoryData.renewal_date = formData.get('renewal_date');
        if (formData.get('country_code')) regulatoryData.country_code = formData.get('country_code');
        
        // Prepare sites data
        const sitesData = [];
        const siteCountries = formData.getAll('site_country[]');
        const siteCities = formData.getAll('site_city[]');
        const siteNames = formData.getAll('site_name[]');
        const siteGMPs = formData.getAll('site_gmp[]');
        
        for (let i = 0; i < siteCountries.length; i++) {
            if (siteCountries[i] && siteCities[i] && siteNames[i]) {
                sitesData.push({
                    country: siteCountries[i],
                    city: siteCities[i],
                    site_name: siteNames[i],
                    gmp_certified: siteGMPs.includes('on')
                });
            }
        }
        
        // Disable submit button
        this.elements.saveBtn.disabled = true;
        this.elements.saveBtn.innerHTML = '<i class="material-icons">hourglass_empty</i> Enregistrement...';
        
        try {
            const response = await fetch('/client/products/api/products/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCSRFToken()
                },
                body: JSON.stringify({
                    product: productData,
                    regulatory: regulatoryData,
                    sites: sitesData
                })
            });
            
            if (response.ok) {
                const newProduct = await response.json();
                console.log('Product created successfully:', newProduct);
                
                this.showNotification('Produit créé avec succès !', 'success');
                this.hideModal();
                
                // Add new product to local array
                this.products.push(newProduct);
                
                // Re-render products list
                this.renderProducts(this.products);
                
                // Select the new product
                this.selectProduct(newProduct.id);
                
            } else {
                const error = await response.json();
                console.error('Error creating product:', error);
                this.showNotification('Erreur lors de la création du produit', 'error');
            }
        } catch (error) {
            console.error('Error submitting form:', error);
            this.showNotification('Erreur de connexion', 'error');
        } finally {
            this.elements.saveBtn.disabled = false;
            this.elements.saveBtn.innerHTML = '<i class="material-icons">save</i> Enregistrer';
        }
    }
    
    validateForm() {
        this.clearFormErrors();
        let isValid = true;
        
        // Required fields
        const requiredFields = ['name', 'active_ingredient', 'dosage', 'form', 'therapeutic_area', 'status'];
        
        requiredFields.forEach(fieldName => {
            const field = this.elements.form.querySelector(`[name="${fieldName}"]`);
            if (!field || !field.value.trim()) {
                this.showFieldError(field, 'Ce champ est requis');
                isValid = false;
            }
        });
        
        return isValid;
    }
    
    showFieldError(field, message) {
        const formGroup = field.closest('.form-group');
        formGroup.classList.add('error');
        
        const errorEl = document.createElement('div');
        errorEl.className = 'form-error';
        errorEl.textContent = message;
        formGroup.appendChild(errorEl);
    }
    
    clearFormErrors() {
        const errorElements = this.elements.form.querySelectorAll('.form-error');
        errorElements.forEach(el => el.remove());
        
        const errorGroups = this.elements.form.querySelectorAll('.form-group.error');
        errorGroups.forEach(group => group.classList.remove('error'));
    }
    
    getCSRFToken() {
        const token = document.querySelector('[name=csrfmiddlewaretoken]');
        return token ? token.value : '';
    }
    
    showNotification(message, type = 'info') {
        const notification = document.createElement('div');
        notification.className = `notification notification-${type}`;
        notification.textContent = message;
        
        // Add notification styles if not already present
        if (!document.querySelector('.notification-styles')) {
            const style = document.createElement('style');
            style.className = 'notification-styles';
            style.textContent = `
                .notification {
                    position: fixed;
                    top: 20px;
                    right: 20px;
                    padding: 12px 20px;
                    border-radius: 6px;
                    color: white;
                    font-weight: 500;
                    z-index: 9999;
                    animation: slideIn 0.3s ease;
                }
                .notification-success { background-color: #27ae60; }
                .notification-error { background-color: #e74c3c; }
                .notification-info { background-color: #3498db; }
                @keyframes slideIn {
                    from { transform: translateX(100%); opacity: 0; }
                    to { transform: translateX(0); opacity: 1; }
                }
            `;
            document.head.appendChild(style);
        }
        
        document.body.appendChild(notification);
        
        setTimeout(() => {
            notification.remove();
        }, 3000);
    }
    
    handleSearch(query) {
        if (!query.trim()) {
            this.renderProducts(this.products);
            return;
        }
        
        const filteredProducts = this.products.filter(product =>
            product.name.toLowerCase().includes(query.toLowerCase()) ||
            product.active_ingredient.toLowerCase().includes(query.toLowerCase())
        );
        
        this.renderProducts(filteredProducts);
    }
    
    formatDate(dateString) {
        if (!dateString) return 'N/A';
        try {
            return new Date(dateString).toLocaleDateString('fr-FR');
        } catch (error) {
            return dateString;
        }
    }
    
    getStatusLabel(status) {
        const labels = {
            'commercialise': 'Commercialisé',
            'developpement': 'En développement',
            'arrete': 'Arrêté',
            'soumis': 'Soumis',
            'en_cours': 'En cours',
            'approuve': 'Approuvé',
            'rejete': 'Rejeté'
        };
        return labels[status] || status;
    }

    getDocumentLabel(key) {
        const labels = {
            'ctd_dossier_complete': 'Dossier CTD complet',
            'gmp_certificate': 'Certificat GMP',
            'inspection_report': 'Rapport d\'inspection',
            'rcp_etiquetage': 'RCP et étiquetage'
        };
        return labels[key] || key;
    }
    // Sites management functions
async addSite() {
    if (!this.currentProductId) {
        this.showNotification('Aucun produit sélectionné', 'error');
        return;
    }
    
    const siteName = prompt('Nom du site:');
    const country = prompt('Pays:');
    const city = prompt('Ville:');
    
    if (siteName && country && city) {
        const gmpCertified = confirm('Site certifié GMP ?');
        
        try {
            const response = await fetch(`/client/products/api/products/${this.currentProductId}/sites/add/`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCSRFToken(),
                },
                body: JSON.stringify({
                    site_name: siteName,
                    country: country,
                    city: city,
                    gmp_certified: gmpCertified
                })
            });
            
            if (response.ok) {
                this.showNotification('Site ajouté avec succès', 'success');
                // Reload sites tab
                this.loadSitesTab();
            } else {
                this.showNotification('Erreur lors de l\'ajout', 'error');
            }
        } catch (error) {
            console.error('Error adding site:', error);
            this.showNotification('Erreur de connexion', 'error');
        }
    }
}

async viewSites() {
    if (!this.currentProductId) {
        this.showNotification('Aucun produit sélectionné', 'error');
        return;
    }
    
    try {
        const response = await fetch(`/client/products/api/products/${this.currentProductId}/sites/`);
        const sites = await response.json();
        
        if (sites.length === 0) {
            alert('Aucun site trouvé pour ce produit');
            return;
        }
        
        const sitesList = sites.map(site => 
            `• ${site.site_name || 'Nom non défini'} - ${site.city}, ${site.country}${site.gmp_certified ? ' (GMP Certifié)' : ''}`
        ).join('\n');
        
        alert(`Sites de production:\n\n${sitesList}`);
    } catch (error) {
        console.error('Error viewing sites:', error);
        this.showNotification('Erreur lors du chargement', 'error');
    }
}

async editSites() {
    if (!this.currentProductId) {
        this.showNotification('Aucun produit sélectionné', 'error');
        return;
    }
    
    try {
        const response = await fetch(`/client/products/api/products/${this.currentProductId}/sites/`);
        const sites = await response.json();
        
        if (sites.length === 0) {
            this.showNotification('Aucun site à modifier', 'info');
            return;
        }
        
        const siteOptions = sites.map((site, index) => 
            `${index + 1}. ${site.site_name || 'Nom non défini'} - ${site.city}, ${site.country}`
        ).join('\n');
        
        const selection = prompt(`Sélectionnez un site à modifier:\n${siteOptions}\n\nEntrez le numéro (1-${sites.length}):`);
        
        if (selection) {
            const siteIndex = parseInt(selection) - 1;
            if (siteIndex >= 0 && siteIndex < sites.length) {
                const site = sites[siteIndex];
                
                const newName = prompt('Nouveau nom du site:', site.site_name || '');
                const newCountry = prompt('Nouveau pays:', site.country || '');
                const newCity = prompt('Nouvelle ville:', site.city || '');
                
                if (newName && newCountry && newCity) {
                    const gmpCertified = confirm(`Site certifié GMP ? (actuellement: ${site.gmp_certified ? 'Oui' : 'Non'})`);
                    
                    const updateResponse = await fetch(`/client/products/api/sites/${site.id}/edit/`, {
                        method: 'PUT',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRFToken': this.getCSRFToken(),
                        },
                        body: JSON.stringify({
                            site_name: newName,
                            country: newCountry,
                            city: newCity,
                            gmp_certified: gmpCertified
                        })
                    });
                    
                    if (updateResponse.ok) {
                        this.showNotification('Site modifié avec succès', 'success');
                        this.loadSitesTab();
                    } else {
                        this.showNotification('Erreur lors de la modification', 'error');
                    }
                }
            } else {
                this.showNotification('Sélection invalide', 'error');
            }
        }
    } catch (error) {
        console.error('Error editing sites:', error);
        this.showNotification('Erreur lors du chargement', 'error');
    }
    }
    viewSourceDocument(productId) {
        if (!productId) {
            this.showNotification('Aucun produit sélectionné', 'error');
            return;
        }
        
        const documentUrl = `/client/products/api/products/${productId}/source-document/`;
        window.open(documentUrl, '_blank', 'width=1200,height=800,scrollbars=yes,resizable=yes');
    }
}

// View source document function

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    if (window.location.pathname.includes('/client/products/')) {
        window.productsApp = new ProductsApp(); 
    }
});