// Metadata Learning RLHF System
class MetadataLearning {
    constructor() {
        this.widget = document.getElementById('metadata-learning-widget');
        this.scoreEl = document.getElementById('learning-score');
        this.improvementsEl = document.getElementById('improvements-count');
    }

    showResults(learningData) {
        if (!this.widget || !learningData.show) return;

        if (this.scoreEl) this.scoreEl.textContent = learningData.score + '%';
        if (this.improvementsEl) {
            this.improvementsEl.textContent = (learningData.wrong + learningData.missed).toString();
        }

        this.widget.style.display = 'block';

        // Visual feedback based on score
        this.widget.style.background = learningData.score > 70 ? 
            'linear-gradient(135deg, #10b981, #059669)' : 
            'linear-gradient(135deg, #f59e0b, #d97706)';

        // Auto-fade after 10 seconds
        setTimeout(() => {
            this.widget.style.opacity = '0.7';
        }, 10000);

        console.log('🧠 Metadata Learning Results:', learningData);
    }
}

// Global functions
function reextractMetadata() {
    const button = event.target;
    const originalHtml = button.innerHTML;
    const docId = document.querySelector('input[name="doc_id"]').value;
    
    if (!docId) {
        alert('Document ID not found');
        return;
    }
    
    button.innerHTML = '<i class="fas fa-sync fa-spin"></i> Extraction...';
    button.disabled = true;
    
    fetch('/edit/' + docId + '/reextract/', {
        method: 'POST',
        headers: {
            'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value,
            'Content-Type': 'application/json',
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            window.location.reload();
        } else {
            alert('Erreur lors de la réextraction: ' + data.error);
        }
    })
    .catch(error => {
        console.error('Error:', error);
        alert('Erreur de connexion');
    })
    .finally(() => {
        button.innerHTML = originalHtml;
        button.disabled = false;
    });
}

function showAddFieldModal() {
    alert('Fonctionnalité d\'ajout de champs personnalisés à venir...');
}

// Initialize on DOM load
document.addEventListener('DOMContentLoaded', () => {
    if (location.hash === '#metadata-tab') {
        window.scrollTo(0, 0);
    }

    // Initialize learning system
    window.metadataLearning = new MetadataLearning();
    
    // Get learning data from JSON script tag
    const learningScript = document.getElementById('learning-data');
    if (learningScript) {
        try {
            const learningData = JSON.parse(learningScript.textContent);
            window.metadataLearning.showResults(learningData);
        } catch (e) {
            console.error('Error parsing learning data:', e);
        }
    }
});