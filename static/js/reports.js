// Reports Dashboard JavaScript

// Application State
const ReportsApp = {
    filtersExpanded: true,
    charts: {},
    filters: window.currentFilters || {
        period: '30d',
        product: '',
        status: '',
        team: ''
    },
    autoRefreshInterval: null
};

// Initialize Application
document.addEventListener('DOMContentLoaded', function() {
    console.log('Reports app initializing...');
    initializeCharts();
    bindEventListeners();
    animateElements();
    updateFilterBadge();
});

// Chart Initialization
function initializeCharts() {
    console.log('Initializing charts...');
    initializeTrendChart();
    initializeStatusChart();
}

function initializeTrendChart() {
    const trendCanvas = document.getElementById('trendChart');
    if (!trendCanvas) {
        console.error('Trend chart canvas not found');
        return;
    }

    const trendCtx = trendCanvas.getContext('2d');
    
    // Use data from Django context or fallback to mock data
    const trendData = window.chartData && window.chartData.trend ? window.chartData.trend : {
        labels: ['Jan', 'Fév', 'Mar', 'Avr', 'Mai', 'Jun'],
        datasets: [
            {
                label: 'Total soumissions',
                data: [65, 78, 82, 91, 95, 88],
                borderColor: '#3498db',
                backgroundColor: 'rgba(52, 152, 219, 0.1)',
                tension: 0.4,
                fill: false,
                pointRadius: 5,
                pointHoverRadius: 8
            },
            {
                label: 'Approuvées',
                data: [52, 68, 71, 79, 83, 76],
                borderColor: '#27ae60',
                backgroundColor: 'rgba(39, 174, 96, 0.1)',
                tension: 0.4,
                fill: false,
                pointRadius: 5,
                pointHoverRadius: 8
            },
            {
                label: 'Rejetées',
                data: [8, 6, 7, 9, 8, 7],
                borderColor: '#e74c3c',
                backgroundColor: 'rgba(231, 76, 60, 0.1)',
                tension: 0.4,
                fill: false,
                pointRadius: 5,
                pointHoverRadius: 8
            }
        ]
    };
    
    ReportsApp.charts.trend = new Chart(trendCtx, {
        type: 'line',
        data: trendData,
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                intersect: false,
                mode: 'index'
            },
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: {
                        padding: 20,
                        font: {
                            family: 'Inter'
                        }
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    grid: {
                        color: '#f0f0f0'
                    },
                    ticks: {
                        font: {
                            family: 'Inter'
                        }
                    }
                },
                x: {
                    grid: {
                        display: false
                    },
                    ticks: {
                        font: {
                            family: 'Inter'
                        }
                    }
                }
            }
        }
    });
}

function initializeStatusChart() {
    const statusCanvas = document.getElementById('statusChart');
    if (!statusCanvas) {
        console.error('Status chart canvas not found');
        return;
    }

    const statusCtx = statusCanvas.getContext('2d');
    
    // Use data from Django context or fallback to mock data
    const statusData = window.chartData && window.chartData.status ? window.chartData.status : {
        labels: ['Approuvé', 'En cours', 'En attente', 'Rejeté'],
        datasets: [{
            data: [156, 67, 18, 6],
            backgroundColor: [
                '#27ae60',
                '#3498db',
                '#f39c12',
                '#e74c3c'
            ],
            borderWidth: 0,
            cutout: '60%'
        }]
    };
    
    ReportsApp.charts.status = new Chart(statusCtx, {
        type: 'doughnut',
        data: statusData,
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: {
                        padding: 20,
                        font: {
                            family: 'Inter'
                        },
                        generateLabels: function(chart) {
                            const data = chart.data;
                            if (data.labels.length && data.datasets.length) {
                                return data.labels.map((label, i) => {
                                    const dataset = data.datasets[0];
                                    const value = dataset.data[i];
                                    const total = dataset.data.reduce((a, b) => a + b, 0);
                                    const percentage = Math.round((value / total) * 100);
                                    
                                    return {
                                        text: `${label} (${percentage}%)`,
                                        fillStyle: dataset.backgroundColor[i],
                                        strokeStyle: dataset.backgroundColor[i],
                                        lineWidth: 0,
                                        index: i
                                    };
                                });
                            }
                            return [];
                        }
                    }
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            const value = context.parsed;
                            const total = context.dataset.data.reduce((a, b) => a + b, 0);
                            const percentage = Math.round((value / total) * 100);
                            return `${context.label}: ${value} (${percentage}%)`;
                        }
                    }
                }
            }
        }
    });
}

// Event Listeners
function bindEventListeners() {
    console.log('Binding event listeners...');
    
    // Chart resize handler
    window.addEventListener('resize', function() {
        Object.values(ReportsApp.charts).forEach(chart => {
            if (chart && chart.resize) {
                chart.resize();
            }
        });
    });

    // Keyboard shortcuts
    document.addEventListener('keydown', function(e) {
        if (e.ctrlKey || e.metaKey) {
            switch(e.key) {
                case 'r':
                    e.preventDefault();
                    refreshData();
                    break;
                case 'f':
                    e.preventDefault();
                    const periodFilter = document.getElementById('period-filter');
                    if (periodFilter) periodFilter.focus();
                    break;
                case 'e':
                    e.preventDefault();
                    exportData('excel');
                    break;
            }
        }
    });
}

// Filter Functions
function toggleFilters() {
    const content = document.getElementById('filter-content');
    const toggleText = document.getElementById('filter-toggle-text');
    
    if (!content || !toggleText) return;
    
    ReportsApp.filtersExpanded = !ReportsApp.filtersExpanded;
    
    if (ReportsApp.filtersExpanded) {
        content.style.display = 'block';
        toggleText.textContent = 'Réduire';
    } else {
        content.style.display = 'none';
        toggleText.textContent = 'Développer';
    }
}

function submitFilters() {
    const form = document.getElementById('filter-form');
    if (form) {
        showLoading();
        form.submit();
    }
}

function updateFilterBadge() {
    const badge = document.querySelector('.filter-badge');
    if (badge) {
        const activeFilters = Object.values(ReportsApp.filters).filter(Boolean).length;
        badge.textContent = activeFilters;
        badge.style.display = activeFilters > 0 ? 'inline-block' : 'none';
    }
}

function clearFilters() {
    // Reset all filter selects
    const filterSelects = document.querySelectorAll('.filter-select');
    filterSelects.forEach(select => {
        select.value = '';
    });
    
    // Reset state
    ReportsApp.filters = {
        period: '',
        product: '',
        status: '',
        team: ''
    };
    
    updateFilterBadge();
    showToast('Filtres effacés', 'success');
    
    // Redirect to clear URL
    window.location.href = window.location.pathname;
}

// Export Functions
function exportData(format) {
    showToast(`Export ${format.toUpperCase()} en cours...`, 'info');
    
    // Build export URL with current filters
    const params = new URLSearchParams();
    Object.entries(ReportsApp.filters).forEach(([key, value]) => {
        if (value) {
            params.append(key, value);
        }
    });
    params.append('format', format);
    
    // Create download link
    const exportUrl = `/reports/export/?${params.toString()}`;
    const link = document.createElement('a');
    link.href = exportUrl;
    link.download = `regx_report_${new Date().toISOString().split('T')[0]}.${format}`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    
    // Show success message
    setTimeout(() => {
        showToast(`Fichier ${format.toUpperCase()} téléchargé`, 'success');
    }, 2000);
}

// Data Refresh
function refreshData() {
    showToast('Actualisation des données...', 'info');
    showLoading();
    
    // Reload the page to get fresh data
    setTimeout(() => {
        window.location.reload();
    }, 1000);
}

function updateCharts() {
    // This would be called with new data from the server
    Object.values(ReportsApp.charts).forEach(chart => {
        if (chart && chart.update) {
            chart.update('active');
        }
    });
}

// Utility Functions
function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    
    document.body.appendChild(toast);
    
    setTimeout(() => {
        toast.remove();
    }, 3000);
}

function showLoading() {
    const charts = document.querySelectorAll('.chart-container');
    charts.forEach(chart => {
        chart.innerHTML = `
            <div class="loading">
                <i class="material-icons">hourglass_empty</i>
                <span>Chargement...</span>
            </div>
        `;
    });
}

function hideLoading() {
    // This would reinitialize charts with new data
    setTimeout(() => {
        const chartContainers = document.querySelectorAll('.chart-container');
        chartContainers.forEach((container, index) => {
            if (index === 0) {
                container.innerHTML = '<canvas id="trendChart"></canvas>';
            } else if (index === 1) {
                container.innerHTML = '<canvas id="statusChart"></canvas>';
            }
        });
        
        initializeCharts();
    }, 100);
}

function animateElements() {
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
    
    // Animate chart cards
    const chartCards = document.querySelectorAll('.chart-card');
    chartCards.forEach((card, index) => {
        setTimeout(() => {
            card.style.opacity = '0';
            card.style.transform = 'translateY(20px)';
            card.style.transition = 'all 0.5s ease';
            
            setTimeout(() => {
                card.style.opacity = '1';
                card.style.transform = 'translateY(0)';
            }, 100);
        }, (index + 4) * 100);
    });
}

// Error handling
window.addEventListener('error', function(e) {
    console.error('Reports error:', e.error);
    showToast('Une erreur est survenue', 'error');
});

// Make functions available globally
window.ReportsApp = ReportsApp;
window.toggleFilters = toggleFilters;
window.submitFilters = submitFilters;
window.clearFilters = clearFilters;
window.exportData = exportData;
window.refreshData = refreshData;

console.log('Reports JavaScript loaded successfully');