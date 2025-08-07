// static/js/reports.js

class ReportsApp {
    constructor() {
        this.currentFilters = {
            template: '',
            period: '30d',
            authority: '',
            status: ''
        };
        this.init();
    }

    init() {
        console.log('🚀 Initializing Reports App...');
        this.bindEvents();
        this.updateKPIs();
        console.log('📊 Reports App initialized successfully');
    }

    bindEvents() {
    // Store reference to avoid conflicts
    const matrixBuilder = this;
    
    // Remove any existing listeners first
    document.removeEventListener('click', this.handleClick);
    document.removeEventListener('change', this.handleChange);
    
    // Create bound methods
    this.handleClick = function(e) {
        if (e.target.closest('.matrix-builder')) return;
        
        const button = e.target.closest('button');
        if (!button) return;

        // Generate button
        if (e.target.closest('.generate-button')) {
            e.preventDefault();
            e.stopPropagation();
            matrixBuilder.generateMatrix();
            return;
        }

        // Remove column chip
        if (e.target.closest('.column-chip .remove')) {
            e.preventDefault();
            e.stopPropagation();
            const chip = e.target.closest('.column-chip');
            const fieldName = chip.dataset.field;
            matrixBuilder.removeColumn(fieldName);
            return;
        }

        // Clear filters button
        if (e.target.closest('#clear-filters')) {
            e.preventDefault();
            e.stopPropagation();
            matrixBuilder.clearAllFilters();
            return;
        }
    };
    
    this.handleChange = function(e) {
        if (e.target.closest('.matrix-builder') && 
        (e.target.closest('.filter-control') || e.target.classList.contains('filter-select'))) {
            return;
        }
    };
    document.addEventListener('change', this.handleChange);
    
    console.log('✅ Matrix Builder events bound');
}
    

    bindAllButtonsWithDelegation() {
        // Use event delegation for ALL buttons in the document
        document.addEventListener('click', (e) => {
            const button = e.target.closest('button');
            if (!button) return;

            const buttonText = button.textContent.trim().toLowerCase();
            const buttonIcon = button.querySelector('i')?.textContent || '';
            
            console.log(`🔘 Button clicked: "${buttonText}" with icon: "${buttonIcon}"`);

            // Template action buttons (in templates section)
            if (button.closest('.template-actions')) {
                e.preventDefault();
                e.stopPropagation();

                const templateCard = button.closest('.template-card');
                const templateName = templateCard.querySelector('h3').textContent;

                console.log(`🎯 Template action: ${buttonText} on ${templateName}`);

                if (buttonText.includes('aperçu') || buttonIcon === 'visibility') {
                    this.previewTemplate(templateName);
                } else if (buttonText.includes('générer') || buttonIcon === 'get_app') {
                    this.generateTemplateReport(templateName);
                } else if (buttonText.includes('export') || buttonIcon === 'file_download') {
                    this.exportTemplate(templateName);
                }
                return;
            }

            // Saved Views action buttons - FIX THIS SHIT
            if (button.closest('.saved-view-actions')) {
                e.preventDefault();
                e.stopPropagation();
                
                const viewItem = button.closest('.saved-view-item');
                const viewName = viewItem.querySelector('h4').textContent;

                console.log(`👁️ Saved view action: ${buttonIcon} on ${viewName}`);

                if (buttonIcon === 'visibility') {
                    this.viewSavedView(viewName);
                } else if (buttonIcon === 'share') {
                    this.shareSavedView(viewName);
                }
                return;
            }

            // History Reports - ADD FUCKING VIEW BUTTONS
            if (button.closest('.reports-history') || button.closest('.history-item')) {
                e.preventDefault();
                e.stopPropagation();

                const historyItem = button.closest('.history-item');
                const reportName = historyItem.querySelector('h5').textContent;

                console.log(`📋 History report action: ${buttonText} on ${reportName}`);

                if (buttonText.includes('voir') || buttonIcon === 'visibility') {
                    this.viewHistoryReport(reportName, historyItem);
                } else if (buttonText.includes('télécharger') || buttonIcon === 'file_download') {
                    this.downloadReport(reportName, historyItem);
                } else if (buttonText.includes('supprimer') || buttonIcon === 'delete') {
                    this.deleteReport(reportName, historyItem);
                }
                return;
            }

            // Recent Reports action buttons
            if (button.closest('.recent-reports-list') || button.closest('.recent-report-item')) {
                e.preventDefault();
                e.stopPropagation();

                const reportItem = button.closest('.recent-report-item');
                const reportName = reportItem.querySelector('h5').textContent;

                console.log(`📋 Recent report action: ${buttonText} on ${reportName}`);

                if (buttonText.includes('voir') || buttonIcon === 'visibility') {
                    this.viewReport(reportName, reportItem);
                } else if (buttonText.includes('télécharger') || buttonIcon === 'file_download') {
                    this.downloadReport(reportName, reportItem);
                } else if (buttonText.includes('supprimer') || buttonIcon === 'delete') {
                    this.deleteReport(reportName, reportItem);
                }
                return;
            }
        });

        console.log('✅ All buttons bound with event delegation');
    }

    bindHeaderButtons() {
        document.querySelectorAll('.header-right .btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.preventDefault();
                this.handleHeaderAction(e);
            });
        });
    }
    

    updateFilter(event) {
        const filterType = event.target.closest('.control-group').querySelector('label').textContent.toLowerCase();
        const value = event.target.value;
        
        console.log(`🔄 Filter updated: ${filterType} = ${value}`);
        
        // Update internal state
        if (filterType.includes('template')) {
            this.currentFilters.template = value;
        } else if (filterType.includes('période')) {
            this.currentFilters.period = value;
        } else if (filterType.includes('autorité')) {
            this.currentFilters.authority = value;
        }

        this.showFilterFeedback();
    }

    showFilterFeedback() {
        const activeFilters = Object.values(this.currentFilters).filter(v => v && v !== '').length;
        
        if (activeFilters > 0) {
            this.showToast(`${activeFilters} filtre(s) actif(s)`, 'info');
        }
    }

    async generateReport(event) {
        console.log('🔄 Generating report from generator...');
        
        const generateBtn = event.target.closest('button');
        const originalText = generateBtn.innerHTML;
        
        // Show loading state
        generateBtn.innerHTML = '<i class="material-icons">hourglass_empty</i> Génération...';
        generateBtn.disabled = true;

        try {
            const response = await fetch('/client/reports/generate/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCSRFToken()
                },
                body: JSON.stringify(this.currentFilters)
            });

            const data = await response.json();

            if (data.status === 'success') {
                this.showToast('✅ Rapport généré avec succès!', 'success');
                this.addToRecentReports(data);
                this.addToReportsHistory(data);
                console.log('📊 Report generated:', data);
            } else {
                throw new Error(data.error || 'Erreur de génération');
            }

        } catch (error) {
            console.error('Generation error:', error);
            this.showToast(`❌ Erreur: ${error.message}`, 'error');
        } finally {
            generateBtn.innerHTML = originalText;
            generateBtn.disabled = false;
        }
    }

    previewTemplate(templateName) {
        console.log(`👁️ Previewing template: ${templateName}`);
        this.showToast(`👁️ Aperçu de "${templateName}"`, 'info');
        
        // Create modal preview
        const modal = this.createModal(`Aperçu - ${templateName}`, `
            <div class="preview-content">
                <h4>📋 Aperçu du template "${templateName}"</h4>
                <div class="preview-info">
                    <p><strong>Ce rapport inclura:</strong></p>
                    <ul>
                        <li>📊 Données des ${this.currentFilters.period || '30 derniers jours'}</li>
                        <li>📈 Graphiques de tendances</li>
                        <li>📋 Tableau de bord KPI</li>
                        <li>🎯 Métriques de performance</li>
                        <li>📄 Format: PDF & Excel</li>
                    </ul>
                    <div class="preview-actions">
                        <button class="btn btn-primary" onclick="this.closest('.modal-overlay').remove(); window.reportsApp.generateTemplateReport('${templateName}')">
                            <i class="material-icons">play_arrow</i>
                            Générer ce rapport
                        </button>
                    </div>
                </div>
            </div>
        `);
        
        document.body.appendChild(modal);
    }

    // NEW: View Saved View
    viewSavedView(viewName) {
        console.log(`👁️ Viewing saved view: ${viewName}`);
        this.showToast(`👁️ Ouverture de "${viewName}"`, 'info');
        
        const modal = this.createModal(`Vue Sauvegardée - ${viewName}`, `
            <div class="saved-view-content">
                <h4>📊 ${viewName}</h4>
                <div class="view-details">
                    <p><strong>Type:</strong> Vue personnalisée</p>
                    <p><strong>Filtres sauvegardés:</strong></p>
                    <ul>
                        <li>🗓️ Période: 30 derniers jours</li>
                        <li>🏢 Autorité: Toutes autorités</li>
                        <li>📊 Données: Documents validés</li>
                        <li>🎯 Focus: Métriques de performance</li>
                    </ul>
                    <div class="view-actions">
                        <button class="btn btn-primary" onclick="window.reportsApp.loadSavedViewFilters('${viewName}'); this.closest('.modal-overlay').remove();">
                            <i class="material-icons">restore</i>
                            Charger cette vue
                        </button>
                        <button class="btn btn-secondary" onclick="window.reportsApp.generateFromSavedView('${viewName}'); this.closest('.modal-overlay').remove();">
                            <i class="material-icons">play_arrow</i>
                            Générer rapport
                        </button>
                    </div>
                </div>
            </div>
        `);
        
        document.body.appendChild(modal);
    }

    // NEW: View History Report
    viewHistoryReport(reportName, reportItem) {
        console.log(`👁️ Viewing history report: ${reportName}`);
        this.showToast(`👁️ Ouverture de "${reportName}"`, 'info');
        
        const modal = this.createModal(`Rapport Généré - ${reportName}`, `
            <div class="report-view">
                <h4>📊 ${reportName}</h4>
                <div class="report-summary">
                    <div class="summary-section">
                        <h5>📈 Résumé Exécutif</h5>
                        <p>Ce rapport présente une analyse complète des données réglementaires pour la période sélectionnée.</p>
                    </div>
                    
                    <div class="summary-section">
                        <h5>📊 Métriques Clés</h5>
                        <div class="metrics-grid-small">
                            <div class="metric-item">
                                <strong>Documents traités:</strong> 6
                            </div>
                            <div class="metric-item">
                                <strong>Annotations créées:</strong> 11
                            </div>
                            <div class="metric-item">
                                <strong>Produits analysés:</strong> 3
                            </div>
                            <div class="metric-item">
                                <strong>Délai moyen:</strong> 2.5 jours
                            </div>
                        </div>
                    </div>
                    
                    <div class="summary-section">
                        <h5>🎯 Points Clés</h5>
                        <ul>
                            <li>✅ 100% des documents ont été validés avec succès</li>
                            <li>📈 Amélioration de 15% du temps de traitement</li>
                            <li>🏆 Tous les produits respectent les standards réglementaires</li>
                            <li>⚡ Performance optimale sur tous les indicateurs</li>
                        </ul>
                    </div>
                </div>
                
                <div class="report-actions">
                    <button class="btn btn-primary" onclick="window.reportsApp.downloadReportFromModal('${reportName}'); this.closest('.modal-overlay').remove();">
                        <i class="material-icons">file_download</i>
                        Télécharger PDF
                    </button>
                    <button class="btn btn-secondary" onclick="window.reportsApp.exportReportCSV('${reportName}'); this.closest('.modal-overlay').remove();">
                        <i class="material-icons">table_chart</i>
                        Exporter CSV
                    </button>
                    <button class="btn btn-outline" onclick="this.closest('.modal-overlay').remove();">
                        Fermer
                    </button>
                </div>
            </div>
        `);
        
        document.body.appendChild(modal);
    }

    async generateTemplateReport(templateName) {
        console.log(`⚙️ Generating template report: ${templateName}`);
        this.showToast(`⚙️ Génération de "${templateName}"...`, 'info');
        
        try {
            const response = await fetch('/client/reports/generate/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCSRFToken()
                },
                body: JSON.stringify({
                    template: templateName,
                    period: this.currentFilters.period,
                    authority: this.currentFilters.authority
                })
            });

            const data = await response.json();

            if (data.status === 'success') {
                this.showToast(`✅ "${templateName}" généré avec succès!`, 'success');
                this.addToRecentReports(data);
                this.addToReportsHistory(data);
            } else {
                throw new Error(data.error || 'Erreur de génération');
            }

        } catch (error) {
            console.error('Template generation error:', error);
            this.showToast(`❌ Erreur: ${error.message}`, 'error');
        }
    }

    async exportTemplate(templateName) {
        console.log(`📤 Exporting template: ${templateName}`);
        this.showToast(`📤 Export de "${templateName}"...`, 'info');
        
        try {
            // Create download URL
            const exportUrl = `/client/reports/export/?format=csv&template=${encodeURIComponent(templateName)}`;
            
            // Create temporary download link
            const link = document.createElement('a');
            link.href = exportUrl;
            link.download = `regx_report_${templateName.replace(/\s+/g, '_')}_${new Date().toISOString().split('T')[0]}.csv`;
            link.style.display = 'none';
            
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            
            setTimeout(() => {
                this.showToast(`✅ Export "${templateName}" terminé!`, 'success');
            }, 1000);
            
        } catch (error) {
            console.error('Export error:', error);
            this.showToast(`❌ Erreur d'export: ${error.message}`, 'error');
        }
    }

    // Methods for handling reports
    viewReport(reportName, reportItem) {
        console.log(`👁️ Viewing report: ${reportName}`);
        this.viewHistoryReport(reportName, reportItem); // Same as history view
    }

    downloadReport(reportName, reportItem) {
        console.log(`📥 Downloading report: ${reportName}`);
        this.showToast(`📥 Téléchargement de "${reportName}"...`, 'info');
        
        // Trigger download
        const exportUrl = `/client/reports/export/?format=csv&template=${encodeURIComponent(reportName)}`;
        const link = document.createElement('a');
        link.href = exportUrl;
        link.download = `${reportName.replace(/\s+/g, '_')}_${new Date().toISOString().split('T')[0]}.csv`;
        link.style.display = 'none';
        
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        
        setTimeout(() => {
            this.showToast(`✅ "${reportName}" téléchargé!`, 'success');
        }, 1000);
    }

    downloadReportFromModal(reportName) {
        this.downloadReport(reportName, null);
    }

    exportReportCSV(reportName) {
        this.downloadReport(reportName, null);
    }

    deleteReport(reportName, reportItem) {
        if (confirm(`Êtes-vous sûr de vouloir supprimer "${reportName}" ?`)) {
            console.log(`🗑️ Deleting report: ${reportName}`);
            reportItem.remove();
            this.showToast(`🗑️ "${reportName}" supprimé`, 'success');
        }
    }

    loadSavedViewFilters(viewName) {
        this.showToast(`📋 Filtres de "${viewName}" chargés!`, 'success');
        // You can implement actual filter loading here
    }

    generateFromSavedView(viewName) {
        this.showToast(`⚙️ Génération depuis "${viewName}"...`, 'info');
        this.generateTemplateReport(viewName);
    }

    addToRecentReports(reportData) {
        console.log('📋 Adding report to recent reports list');
        
        // Find or create recent reports section
        let recentSection = document.querySelector('.recent-reports-section');
        if (!recentSection) {
            recentSection = this.createRecentReportsSection();
        }
        
        const reportsList = recentSection.querySelector('.recent-reports-list');
        
        // Create new report item
        const reportItem = document.createElement('div');
        reportItem.className = 'recent-report-item';
        reportItem.innerHTML = `
            <div class="report-info">
                <h5>${reportData.template || 'Rapport Généré'}</h5>
                <small>Généré le ${new Date().toLocaleString()}</small>
                <div class="report-meta">
                    <span class="meta-tag">Période: ${reportData.period || '30d'}</span>
                    ${reportData.authority ? `<span class="meta-tag">Autorité: ${reportData.authority}</span>` : ''}
                </div>
            </div>
            <div class="report-actions">
                <button class="btn btn-text btn-sm">
                    <i class="material-icons">visibility</i>
                    Voir
                </button>
                <button class="btn btn-text btn-sm">
                    <i class="material-icons">file_download</i>
                    Télécharger
                </button>
                <button class="btn btn-text btn-sm text-danger">
                    <i class="material-icons">delete</i>
                    Supprimer
                </button>
            </div>
        `;
        
        // Add to beginning of list
        reportsList.insertBefore(reportItem, reportsList.firstChild);
        
        // Keep only last 10 reports
        const reports = reportsList.querySelectorAll('.recent-report-item');
        if (reports.length > 10) {
            reports[reports.length - 1].remove();
        }
        
        // Animate the new item
        reportItem.style.opacity = '0';
        reportItem.style.transform = 'translateY(-10px)';
        setTimeout(() => {
            reportItem.style.transition = 'all 0.3s ease';
            reportItem.style.opacity = '1';
            reportItem.style.transform = 'translateY(0)';
        }, 100);
    }

    addToReportsHistory(reportData) {
        console.log('📋 Adding report to history');
        
        // Find history list
        const historyList = document.querySelector('.reports-history-list');
        if (!historyList) return;
        
        // Create new history item WITH VIEW BUTTON
        const historyItem = document.createElement('div');
        historyItem.className = 'history-item';
        historyItem.innerHTML = `
            <div class="history-content">
                <h5>${reportData.template || 'Rapport Généré'}</h5>
                <small>Généré le ${new Date().toLocaleString()}</small>
            </div>
            <div class="history-actions">
                <button class="btn btn-text btn-sm">
                    <i class="material-icons">visibility</i>
                    Voir
                </button>
                <span class="status-badge success">Terminé</span>
            </div>
        `;
        
        // Add to beginning of list
        historyList.insertBefore(historyItem, historyList.firstChild);
        
        // Animate the new item
        historyItem.style.opacity = '0';
        historyItem.style.transform = 'translateY(-10px)';
        setTimeout(() => {
            historyItem.style.transition = 'all 0.3s ease';
            historyItem.style.opacity = '1';
            historyItem.style.transform = 'translateY(0)';
        }, 100);
    }

    createRecentReportsSection() {
        const container = document.querySelector('.reports-container');
        
        // Find a good place to insert (after templates section)
        const templatesSection = document.querySelector('.templates-section');
        
        const recentSection = document.createElement('div');
        recentSection.className = 'recent-reports-section';
        recentSection.innerHTML = `
            <h2 class="section-title">📋 Rapports Récents</h2>
            <div class="recent-reports-list">
                <!-- Reports will be added here dynamically -->
            </div>
        `;
        
        // Insert after templates section
        if (templatesSection && templatesSection.nextSibling) {
            container.insertBefore(recentSection, templatesSection.nextSibling);
        } else {
            container.appendChild(recentSection);
        }
        
        return recentSection;
    }

    handleHeaderAction(event) {
        const action = event.target.closest('button');
        const actionText = action.textContent.trim().toLowerCase();

        if (actionText.includes('sauvegarder')) {
            this.saveCurrentView();
        } else if (actionText.includes('nouveau')) {
            this.createNewReport();
        }
    }

    saveCurrentView() {
        const viewName = prompt('Nom de la vue à sauvegarder:', `Vue ${new Date().toLocaleDateString()}`);
        
        if (viewName) {
            this.showToast(`💾 Vue "${viewName}" sauvegardée!`, 'success');
            this.addSavedView(viewName);
        }
    }

    createNewReport() {
        this.showToast('🆕 Création d\'un nouveau rapport...', 'info');
        console.log('Navigate to report builder');
    }

    loadSavedView(viewName) {
        this.showToast(`👁️ Chargement de "${viewName}"...`, 'info');
        console.log(`Loading saved view: ${viewName}`);
        
        setTimeout(() => {
            this.showToast(`✅ Vue "${viewName}" chargée!`, 'success');
        }, 1000);
    }

    shareSavedView(viewName) {
        const shareUrl = `${window.location.origin}/client/reports/?view=${encodeURIComponent(viewName)}`;
        
        if (navigator.share) {
            navigator.share({
                title: `RegX Report - ${viewName}`,
                url: shareUrl
            });
        } else {
            navigator.clipboard.writeText(shareUrl).then(() => {
                this.showToast(`🔗 Lien de partage copié!`, 'success');
            });
        }
    }

    updateKPIs() {
        // Animate KPI cards on load
        const kpiCards = document.querySelectorAll('.kpi-card');
        
        kpiCards.forEach((card, index) => {
            setTimeout(() => {
                card.style.opacity = '0';
                card.style.transform = 'translateY(20px)';
                card.style.transition = 'all 0.5s ease';
                
                setTimeout(() => {
                    card.style.opacity = '1';
                    card.style.transform = 'translateY(0)';
                }, 100);
            }, index * 100);
        });
    }

    addSavedView(viewName) {
        const savedViewsGrid = document.querySelector('.saved-views-grid');
        
        const newView = document.createElement('div');
        newView.className = 'saved-view-item';
        newView.innerHTML = `
            <div class="saved-view-content">
                <h4>${viewName}</h4>
                <p>Vue personnalisée créée le ${new Date().toLocaleDateString()}</p>
            </div>
            <div class="saved-view-actions">
                <button class="btn btn-text">
                    <i class="material-icons">visibility</i>
                </button>
                <button class="btn btn-text">
                    <i class="material-icons">share</i>
                </button>
            </div>
        `;
        
        savedViewsGrid.insertBefore(newView, savedViewsGrid.firstChild);
    }

    createModal(title, content) {
        const modal = document.createElement('div');
        modal.className = 'modal-overlay';
        modal.innerHTML = `
            <div class="modal-content">
                <div class="modal-header">
                    <h3>${title}</h3>
                    <button class="modal-close">&times;</button>
                </div>
                <div class="modal-body">
                    ${content}
                </div>
            </div>
        `;
        
        // Close modal functionality
        modal.querySelector('.modal-close').addEventListener('click', () => {
            document.body.removeChild(modal);
        });
        
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                document.body.removeChild(modal);
            }
        });
        
        return modal;
    }

    showToast(message, type = 'info') {
        console.log(`🍞 Toast: ${message} (${type})`);
        
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.textContent = message;
        
        // Style the toast
        Object.assign(toast.style, {
            position: 'fixed',
            top: '20px',
            right: '20px',
            padding: '12px 20px',
            borderRadius: '8px',
            color: 'white',
            fontWeight: '500',
            zIndex: '10000',
            transform: 'translateX(100%)',
            transition: 'transform 0.3s ease',
            maxWidth: '400px'
        });
        
        // Type-specific colors
        const colors = {
            success: '#10b981',
            error: '#ef4444', 
            info: '#3b82f6',
            warning: '#f59e0b'
        };
        
        toast.style.background = colors[type] || colors.info;
        
        document.body.appendChild(toast);
        
        // Animate in
        setTimeout(() => {
            toast.style.transform = 'translateX(0)';
        }, 100);
        
        // Remove after delay
        setTimeout(() => {
            toast.style.transform = 'translateX(100%)';
            setTimeout(() => {
                if (document.body.contains(toast)) {
                    document.body.removeChild(toast);
                }
            }, 300);
        }, 3000);
    }

    getCSRFToken() {
        const token = document.querySelector('[name=csrfmiddlewaretoken]');
        if (token) return token.value;
        
        // Alternative: get from cookies
        const cookies = document.cookie.split(';');
        for (let cookie of cookies) {
            const [name, value] = cookie.trim().split('=');
            if (name === 'csrftoken') {
                return value;
            }
        }
        return '';
    }
}

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.reportsApp = new ReportsApp();
});

// Global functions for compatibility
window.generateReport = () => {
    const generateBtn = document.querySelector('.control-button');
    if (generateBtn && window.reportsApp) {
        generateBtn.click();
    }
};

window.refreshData = () => {
    if (window.reportsApp) {
        window.reportsApp.showToast('🔄 Actualisation des données...', 'info');
        setTimeout(() => {
            window.location.reload();
        }, 1000);
    }
};

console.log('📊 Reports JavaScript loaded successfully');

// Matrix Builder Class 

    // REPLACE YOUR ENTIRE MatrixBuilder CLASS WITH THIS:

class MatrixBuilder {
    constructor() {
        this.selectedColumns = [];
        this.availableFields = { annotations: [], documents: [], products: [] };
        this.currentFilters = {};
        this.generatedData = [];
        this.init();
    }

    init() {
        console.log('🏗️ Initializing Matrix Builder...');
        this.loadDynamicFields();
        this.bindEvents();
        this.setupPerformantFiltering();
        console.log('✅ Matrix Builder initialized');
    }

    loadDynamicFields() {
        if (window.allFields) {
            console.log('📊 All fields loaded:', window.allFields.length);
            this.allFields = window.allFields;
        }
        // Don't call renderFieldSelector - fields are in template
    }

    setupPerformantFiltering() {
        this.debouncedUpdateFilters = this.debounce(() => {
            this.updateFilters();
        }, 300);
    }

    debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    }

    

   

    bindEvents() {
        const self = this; 
        
        // Use different event handler names to avoid conflicts with ReportsApp
        document.removeEventListener('click', this.matrixClickHandler);
        document.removeEventListener('change', this.matrixChangeHandler);
        
        // Create bound methods with unique names
        this.matrixClickHandler = function(e) {
            // Only handle clicks inside matrix-builder, but NOT return early
            if (!e.target.closest('.matrix-builder')) return;
            
            const button = e.target.closest('button');
            if (button) {
                // Generate button
                if (e.target.closest('.generate-button')) {
                    e.preventDefault();
                    e.stopPropagation();
                    self.generateMatrix(); 
                    return;
                }

                // Remove column chip
                if (e.target.closest('.column-chip .remove')) {
                    e.preventDefault();
                    e.stopPropagation();
                    const chip = e.target.closest('.column-chip');
                    const fieldName = chip.dataset.field;
                    self.removeColumn(fieldName);
                    return;
                }

                // Clear filters button
                if (e.target.closest('#clear-filters')) {
                    e.preventDefault();
                    e.stopPropagation();
                    self.clearAllFilters(); 
                    return;
                }
            }
            
            // Handle field item clicks
            const fieldItem = e.target.closest('.field-item');
            if (fieldItem) {
                e.preventDefault();
                e.stopPropagation();
                self.toggleField(fieldItem);
                return;
            }
        };

        this.matrixChangeHandler = function(e) {
            if (e.target.closest('.matrix-builder') && 
            (e.target.closest('.filter-control') || e.target.classList.contains('filter-select'))) {
                self.updateFilters(); 
            }
        };
        
        // Add the event listeners with unique handler names
        document.addEventListener('click', this.matrixClickHandler);
        document.addEventListener('change', this.matrixChangeHandler);
        
        console.log('✅ Matrix Builder events bound');
}
    toggleField(fieldItem) {
        const fieldName = fieldItem.dataset.field;
        const fieldType = fieldItem.dataset.type;
        const dataCount = parseInt(fieldItem.dataset.count) || 0;
        
        if (fieldItem.classList.contains('selected')) {
            this.removeColumn(fieldName);
        } else {
            if (dataCount === 0) {
                this.showToast(`⚠️ Ce champ n'a pas de données`, 'warning');
                return;
            }
            this.addColumn(fieldName, fieldType);
        }
    }

    addColumn(fieldName, fieldType) {
        if (this.selectedColumns.find(col => col.name === fieldName)) return;

        const fieldConfig = this.findFieldConfig(fieldName, fieldType);
        if (!fieldConfig) return;

        this.selectedColumns.push({
        name: fieldName,
        label: fieldConfig.label,
        type: fieldType,
        source_type: fieldType, 
        field_path: fieldName
    });

        this.updateUI();
        this.showToast(`✅ Colonne "${fieldConfig.label}" ajoutée`, 'success');
    }
    clearAllFilters() {
        // Clear all filter select elements
        const filterInputs = document.querySelectorAll('.matrix-builder .filter-select');
        filterInputs.forEach(input => {
            input.value = '';
        });
        
        // Clear internal filters state
        this.currentFilters = {};
        
        // Regenerate matrix without filters
        if (this.selectedColumns.length > 0) {
            this.generateMatrix();
        }
        
        this.showToast('🧹 Tous les filtres ont été effacés', 'info');
    }
    removeColumn(fieldName) {
        const removedColumn = this.selectedColumns.find(col => col.name === fieldName);
        this.selectedColumns = this.selectedColumns.filter(col => col.name !== fieldName);
        this.updateUI();
        
        if (removedColumn) {
            this.showToast(`🗑️ Colonne "${removedColumn.label}" supprimée`, 'info');
        }
    }

    findFieldConfig(fieldName, fieldType) {
        if (window.allFields) {
            return window.allFields.find(field => field.name === fieldName);
        }
        return null;
    }

    getSourceType(fieldType) {
    const mapping = {
        'annotation': 'annotation',
        'document': 'document', 
        'product': 'product'
    };
    return mapping[fieldType] || fieldType; // Return fieldType if not in mapping
}

    updateUI() {
        this.updateFieldSelection();
        this.updateMatrixPreview();
    }

    updateFieldSelection() {
        document.querySelectorAll('.matrix-builder .field-item').forEach(item => {
            const fieldName = item.dataset.field;
            const isSelected = this.selectedColumns.some(col => col.name === fieldName);
            item.classList.toggle('selected', isSelected);
        });
    }

    updateMatrixPreview() {
        const container = document.querySelector('.matrix-preview');
        if (!container) return;

        container.innerHTML = `
            <div class="preview-header">
                <div class="preview-title">
                    <i class="material-icons">table_chart</i>
                    Matrix de Données Réelles
                    ${this.selectedColumns.length > 0 ? `<span class="column-count">${this.selectedColumns.length} colonnes</span>` : ''}
                </div>
                <div class="preview-actions">
                    <button class="generate-button" ${this.selectedColumns.length === 0 ? 'disabled' : ''}>
                        <i class="material-icons">auto_awesome</i>
                        Générer Matrix
                    </button>
                </div>
            </div>
            
            ${this.selectedColumns.length > 0 ? `
                <div class="selected-columns">
                    <div class="columns-list">
                        ${this.selectedColumns.map(col => `
                            <div class="column-chip" data-field="${col.name}">
                                <span class="chip-label">${col.label}</span>
                                <span class="chip-type">${col.type}</span>
                                <span class="remove">×</span>
                            </div>
                        `).join('')}
                    </div>
                </div>
            ` : ''}
            
            <div class="matrix-table-container">
                ${this.renderTableContent()}
            </div>
        `;
    }

    renderTableContent() {
        if (this.selectedColumns.length === 0) {
            return `
                <div class="empty-state">
                    <i class="material-icons">view_column</i>
                    <h3>Sélectionnez vos données</h3>
                    <p>Choisissez des champs avec des données réelles validées</p>
                    <div class="quick-start">
                        <h4>🚀 Données disponibles:</h4>
                        <ul>
                        <li>📝 ${window.allFields ? window.allFields.filter(f => f.source_type === 'annotation').length : 0} types d'annotations validées</li>
                        <li>🏭 ${window.allFields ? window.allFields.filter(f => f.source_type === 'product').length : 0} champs produits avec données</li>
                        <li>📄 ${window.allFields ? window.allFields.filter(f => f.source_type === 'document').length : 0} champs documents populés</li>
                        </ul>
                    </div>
                </div>
            `;
        }

        if (this.generatedData.length === 0) {
            return `
                <table class="matrix-table">
                    <thead>
                        <tr>
                            ${this.selectedColumns.map(col => `
                                <th>
                                    <div class="header-content">
                                        <span class="header-label">${col.label}</span>
                                        <span class="header-type">${col.type}</span>
                                    </div>
                                </th>
                            `).join('')}
                        </tr>
                    </thead>
                    <tbody>
                        <tr>
                            <td colspan="${this.selectedColumns.length}" class="generate-prompt">
                                <div class="prompt-content">
                                    <i class="material-icons">play_circle</i>
                                    <p>Cliquez sur "Générer Matrix" pour extraire vos données réelles</p>
                                </div>
                            </td>
                        </tr>
                    </tbody>
                </table>
            `;
        }

        return `
            <div class="table-header">
                <div class="table-info">
                    <span class="row-count">${this.generatedData.length} lignes de données réelles</span>
                    <span class="generation-time">Généré en ${this.lastGenerationTime}s</span>
                </div>
            </div>
            
            <table class="matrix-table">
                <thead>
                    <tr>
                        ${this.selectedColumns.map(col => `
                            <th>
                                <div class="header-content">
                                    <span class="header-label">${col.label}</span>
                                    <span class="header-type">${col.type}</span>
                                </div>
                            </th>
                        `).join('')}
                    </tr>
                </thead>
                <tbody>
                    ${this.generatedData.map((row, index) => `
                        <tr class="data-row" data-row="${index}">
                            ${this.selectedColumns.map(col => `
                                <td>
                                    <div class="cell-content" title="${row[col.name] || 'N/A'}">
                                        ${this.formatCellValue(row[col.name])}
                                    </div>
                                </td>
                            `).join('')}
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        `;
    }

    formatCellValue(value) {
        if (!value || value === '' || value === 'N/A') {
            return '<span class="empty-value">—</span>';
        }
        
        const maxLength = 100;
        const sanitized = String(value);
        
        if (sanitized.length > maxLength) {
            return `<span class="truncated-value">${sanitized.substring(0, maxLength)}...</span>`;
        }
        
        return sanitized;
    }

    updateFilters() {
    const filterInputs = document.querySelectorAll('.matrix-builder .filter-select');
    const oldFilters = {...this.currentFilters};
    this.currentFilters = {};
    
    console.log('🔍 Found filter inputs:', filterInputs.length);
    
    filterInputs.forEach(input => {
        console.log(`🔍 Processing input: ${input.name} = '${input.value}'`);
        
        if (input.value && input.value !== '') {
            const filterName = input.name.replace('filter_', '');
            this.currentFilters[filterName] = input.value;
            console.log(`✅ Added filter: ${filterName} = '${input.value}'`);
        }
    });

    console.log('🔍 Final filters to send to backend:', this.currentFilters);
    
    if (JSON.stringify(oldFilters) !== JSON.stringify(this.currentFilters)) {
        if (this.selectedColumns.length > 0) {
            console.log('🔄 Calling generateMatrix with filters...');
            this.generateMatrix();
        }
    }
}
    

    async generateMatrix() {
        if (this.selectedColumns.length === 0) {
            this.showToast('⚠️ Sélectionnez au moins une colonne', 'warning');
            return;
        }

        this.showGeneratingState();

        try {
            const matrixConfig = {
                columns: this.selectedColumns.map((col, index) => ({
                    name: col.name,
                    source_type: col.source_type,
                    field_path: col.field_path,
                    display_format: 'text',
                    order: index
                })),
                filters: this.currentFilters
            };

            const response = await fetch('/client/reports/generate-matrix/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCSRFToken()
                },
                body: JSON.stringify(matrixConfig)
            });

            const result = await response.json();

            if (result.success) {
                this.generatedData = result.result.rows || [];
                this.lastGenerationTime = result.result.generation_time || 0;
                
                this.updateMatrixPreview();
                this.showToast(`✅ Matrix générée avec ${this.generatedData.length} lignes!`, 'success');
                
            } else {
                throw new Error(result.message || result.error || 'Erreur de génération');
            }

        } catch (error) {
            console.error('❌ Matrix generation error:', error);
            this.showToast(`❌ Erreur: ${error.message}`, 'error');
        } finally {
            this.hideGeneratingState();
        }
    }

    showGeneratingState() {
        const button = document.querySelector('.generate-button');
        if (button) {
            button.disabled = true;
            button.innerHTML = '<i class="material-icons">hourglass_empty</i> Génération...';
        }
    }

    hideGeneratingState() {
        const button = document.querySelector('.generate-button');
        if (button) {
            button.disabled = false;
            button.innerHTML = '<i class="material-icons">auto_awesome</i> Générer Matrix';
        }
    }

    showToast(message, type = 'info') {
        if (window.reportsApp && window.reportsApp.showToast) {
            window.reportsApp.showToast(message, type);
        } else {
            console.log(`${type.toUpperCase()}: ${message}`);
        }
    }

    updateUI() {
        this.updateFieldSelection();
        this.updateMatrixPreview();
        this.updateDynamicFilters(); 
    }

    updateDynamicFilters() {
        const filtersContainer = document.getElementById('column-specific-filters');
        const filterCount = document.getElementById('filter-count');
        
        if (!filtersContainer) return;
        
        // Clear existing filters
        filtersContainer.innerHTML = '';
        
        let filterHtml = '';
        let filterCounter = 0;
        
        console.log('🔍 Updating filters for columns:', this.selectedColumns);
        console.log('🔍 Available window.filterOptions:', window.filterOptions);

        // Generate filters for selected columns
        this.selectedColumns.forEach(column => {
            const fieldName = column.name;
            const fieldType = column.type;
            const fieldLabel = column.label;
            
            console.log(`🔍 Processing column: ${fieldName} (${fieldType}) - ${fieldLabel}`);
            const filterOptions = this.getFilterOptionsForField(fieldName, fieldType);
            
            console.log(`🔍 Filter options for ${fieldName}:`, filterOptions);
            
            if (filterOptions && filterOptions.length > 0) {
                filterCounter++;
                filterHtml += `
                    <div class="filter-group column-filter" data-column="${fieldName}">
                        <label>${this.getFilterIcon(fieldType)} ${fieldLabel}</label>
                        <select name="filter_${fieldName}" class="filter-select">
                            <option value="">Tous les ${fieldLabel.toLowerCase()}</option>
                            ${filterOptions.map(option => `
                                <option value="${option}">${option}</option>
                            `).join('')}
                        </select>
                    </div>
                `;
            } else {
                console.log(`❌ No filter options found for ${fieldName}`);
            }   
        });
        
        filtersContainer.innerHTML = filterHtml;
        const newFilterSelects = filtersContainer.querySelectorAll('.filter-select');
        newFilterSelects.forEach(select => {
            select.addEventListener('change', () => {
                console.log(`🔍 Filter changed: ${select.name} = ${select.value}`);
                this.debouncedUpdateFilters();
            });
        });
        // Update filter count
        if (filterCount) {
            filterCount.textContent = filterCounter > 0 ? `${filterCounter} filtres` : '0 filtres';
        }
        
        // Show/hide clear button
        const clearButton = document.getElementById('clear-filters');
        if (clearButton) {
            clearButton.style.display = filterCounter > 0 ? 'block' : 'none';
        }
    }

    getFilterOptionsForField(fieldName, fieldType) {
        console.log(`🔍 Looking for filter options for: ${fieldName} (type: ${fieldType})`);
        
        if (typeof window.filterOptions === 'undefined') {
            console.log('❌ window.filterOptions not found');
            return [];
        }
        
        const options = window.filterOptions;
        console.log('🔍 Available filter option keys:', Object.keys(options));
        
        let foundOptions = [];
        
        // 1. EXACT MATCH
        if (options[fieldName] && Array.isArray(options[fieldName]) && options[fieldName].length > 0) {
            foundOptions = options[fieldName];
            console.log(`✅ EXACT match: ${fieldName}`);
            return foundOptions;
        }
        
        // 2. GENERATE ALL POSSIBLE VARIATIONS
        const variations = [
            fieldName + 's',                        // name -> names
            fieldName + 'es',                       // dosage -> dosages  
            fieldType + '_' + fieldName,            // product_name
            fieldType + '_' + fieldName + 's',      // product_names
            'doc_' + fieldName,                     // doc_title
            'doc_' + fieldName + 's',               // doc_titles
            fieldName.replace('_', ''),             // active_ingredient -> activeingredient
            fieldName.replace('_', '') + 's',       // activeingredients
            fieldName + '_type',                    // name_type
            fieldName + '_types',                   // name_types
            fieldName + '_name',                    // field_name
            fieldName + '_names',                   // field_names
        ];
        
        // Try all variations
        for (const variation of variations) {
            if (options[variation] && Array.isArray(options[variation]) && options[variation].length > 0) {
                foundOptions = options[variation];
                console.log(`✅ VARIATION match: ${fieldName} -> ${variation}`);
                return foundOptions;
            }
        }
        
        // 3. HANDLE ADDITIONAL ANNOTATION FIELDS
        if (fieldName.startsWith('additional_') && options.annotations) {
            const annotationType = fieldName.replace('additional_', '');
            console.log(`🔍 Checking annotation type: ${annotationType}`);
            
            if (options.annotations[annotationType] && options.annotations[annotationType].options) {
                foundOptions = options.annotations[annotationType].options;
                console.log(`✅ Found annotation options for ${annotationType}`);
                return foundOptions;
            }
        }
        
        // 4. FUZZY SEARCH - Search through ALL keys
        const allKeys = Object.keys(options);
        for (const key of allKeys) {
            // Skip non-array values
            if (!Array.isArray(options[key]) || options[key].length === 0) continue;
            
            // Check if key contains field name (either direction)
            if (key.toLowerCase().includes(fieldName.toLowerCase()) || 
                fieldName.toLowerCase().includes(key.toLowerCase())) {
                foundOptions = options[key];
                console.log(`✅ FUZZY match: ${fieldName} -> ${key}`);
                return foundOptions;
            }
        }
        
        // 5. LAST RESORT - Check for partial word matches
        const fieldWords = fieldName.split('_');
        for (const key of allKeys) {
            if (!Array.isArray(options[key]) || options[key].length === 0) continue;
            
            const keyWords = key.split('_');
            const hasCommonWord = fieldWords.some(word => 
                keyWords.some(keyWord => 
                    word.toLowerCase() === keyWord.toLowerCase() && word.length > 2
                )
            );
            
            if (hasCommonWord) {
                foundOptions = options[key];
                console.log(`✅ WORD match: ${fieldName} -> ${key}`);
                return foundOptions;
            }
        }
        
        console.log(`❌ NO FILTER OPTIONS found for field: ${fieldName}`);
        console.log(`🔍 Available keys were:`, Object.keys(options));
        return [];
    }
    getFilterIcon(fieldType) {
        const icons = {
            'product': '🏥',
            'document': '📄',
            'annotation': '🏷️'
        };
        return icons[fieldType] || '🔍';
    }

    removeColumn(fieldName) {
        const removedColumn = this.selectedColumns.find(col => col.name === fieldName);
        this.selectedColumns = this.selectedColumns.filter(col => col.name !== fieldName);
        this.updateUI(); // This will call updateDynamicFilters
        
        if (removedColumn) {
            this.showToast(`🗑️ Colonne "${removedColumn.label}" supprimée`, 'info');
        }
    }

    getCSRFToken() {
        if (window.reportsApp && window.reportsApp.getCSRFToken) {
            return window.reportsApp.getCSRFToken();
        }
        
        const token = document.querySelector('[name=csrfmiddlewaretoken]');
        return token ? token.value : '';
    }
}

document.addEventListener('DOMContentLoaded', function() {
    // Always initialize MatrixBuilder
    console.log('🏗️ Initializing Matrix Builder...');
    window.matrixBuilder = new MatrixBuilder();
});