// static/rawdocs/js/rlhf_annotation.js 

// Enhanced AI annotation with RLHF learning
function annotateWithGroq() {
    const btn = document.getElementById('groq-annotate-btn');
    const loading = document.getElementById('ai-loading');
    const validateBtn = document.getElementById('validate-page-btn');
    
    btn.style.display = 'none';
    loading.style.display = 'flex';
    
    // Get current page ID from template
    const pageId = document.getElementById('text-content').dataset.pageId;
    
    fetch(`/annotation/groq/${pageId}/`, {
        method: 'POST',
        headers: {
            'X-CSRFToken': getCookie('csrftoken'),
            'Content-Type': 'application/json'
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            showSuccessMessage(`🎉 ${data.annotations_created} annotations créées avec IA améliorée!`);
            
            // Enable validate button
            if (validateBtn) {
                validateBtn.disabled = false;
                validateBtn.innerHTML = '<i class="fas fa-graduation-cap"></i> Validate Page';
            }
            
            // Reload page to show annotations
            setTimeout(() => {
                location.reload();
            }, 1500);
        } else {
            showErrorMessage('Erreur: ' + data.error);
        }
    })
    .catch(error => {
        console.error('Error:', error);
        showErrorMessage('Erreur lors de l\'annotation automatique');
    })
    .finally(() => {
        btn.style.display = 'flex';
        loading.style.display = 'none';
    });
}

// NEW: Validate page function with RLHF learning
function validatePage() {
    const btn = document.getElementById('validate-page-btn');
    const learningProgress = document.getElementById('learning-progress');
    const pageId = document.getElementById('text-content').dataset.pageId;
    
    // Confirm validation
    if (!confirm('Valider cette page ? L\'IA va apprendre de vos corrections.')) {
        return;
    }
    
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Validation...';
    
    if (learningProgress) {
        learningProgress.style.display = 'flex';
    }
    
    fetch(`/annotation/validate-page/${pageId}/`, {
        method: 'POST',
        headers: {
            'X-CSRFToken': getCookie('csrftoken'),
            'Content-Type': 'application/json'
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Show detailed success message with feedback score
            showValidationSuccess(data.message, data.feedback_score, data.corrections_summary);
            
            // Update button to show validated state
            btn.innerHTML = '<i class="fas fa-check-circle"></i> Page Validée 🎓';
            btn.classList.add('validated');
            
            // Show learning dashboard widget
            showLearningWidget(data);
            
            // Update page selector to show validation
            updatePageSelector();
            
        } else {
            showErrorMessage('Erreur: ' + data.error);
            btn.disabled = false;
            btn.innerHTML = '<i class="fas fa-graduation-cap"></i> Validate Page';
        }
    })
    .catch(error => {
        console.error('Error:', error);
        showErrorMessage('Erreur lors de la validation de la page');
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-graduation-cap"></i> Validate Page';
    })
    .finally(() => {
        if (learningProgress) {
            learningProgress.style.display = 'none';
        }
    });
}

// Show validation success with detailed feedback
function showValidationSuccess(message, feedbackScore, corrections) {
    const container = document.querySelector('.main-content');
    
    // Calculate detailed metrics
    const aiCorrect = corrections.kept_correct?.length || 0;
    const aiWrong = corrections.false_positives?.length || 0;
    const aiMissed = corrections.false_negatives?.length || 0;
    const aiWrongType = corrections.wrong_classifications?.length || 0;
    const totalExpected = aiCorrect + aiWrong + aiMissed + aiWrongType;
    
    const successDiv = document.createElement('div');
    successDiv.className = 'validation-success';
    successDiv.innerHTML = `
        <i class="fas fa-graduation-cap"></i>
        <div>
            <strong>${message}</strong>
            <div class="validation-details">
                <div class="feedback-breakdown">
                    <div class="metric-row">
                        <span class="metric-icon">✅</span>
                        <span class="metric-text">AI Correct (kept): ${aiCorrect}</span>
                    </div>
                    <div class="metric-row">
                        <span class="metric-icon">❌</span>
                        <span class="metric-text">AI Wrong (deleted): ${aiWrong}</span>
                    </div>
                    <div class="metric-row">
                        <span class="metric-icon">➕</span>
                        <span class="metric-text">AI Missed (you added): ${aiMissed}</span>
                    </div>
                    ${aiWrongType > 0 ? `
                    <div class="metric-row">
                        <span class="metric-icon">🔄</span>
                        <span class="metric-text">AI Wrong Type: ${aiWrongType}</span>
                    </div>
                    ` : ''}
                    <div class="metric-row total">
                        <span class="metric-icon">📊</span>
                        <span class="metric-text">Total Expected: ${totalExpected}</span>
                    </div>
                    <div class="metric-row score">
                        <span class="metric-icon">🎯</span>
                        <span class="metric-text">Real Score: ${(feedbackScore * 100).toFixed(0)}%</span>
                    </div>
                </div>
            </div>
        </div>
    `;
    
    container.insertBefore(successDiv, container.firstChild);
    
    // Auto-remove after 8 seconds (longer for detailed view)
    setTimeout(() => {
        successDiv.remove();
    }, 8000);
}

// Enhanced learning widget with better metrics
function showLearningWidget(data) {
    let widget = document.getElementById('learning-widget');
    
    if (!widget) {
        widget = document.createElement('section');
        widget.id = 'learning-widget';
        widget.className = 'learning-dashboard-widget';
        
        const container = document.querySelector('.main-content');
        container.appendChild(widget);
    }
    
    // Fetch and display learning metrics
    fetch('/learning/dashboard/')
        .then(response => response.json())
        .then(learningData => {
            const avgScore = (learningData.average_feedback_score * 100).toFixed(0);
            const validations = learningData.total_feedbacks;
            
            // Determine performance level
            let performanceLevel = '';
            let performanceIcon = '';
            if (avgScore >= 90) {
                performanceLevel = 'Excellent';
                performanceIcon = '🏆';
            } else if (avgScore >= 75) {
                performanceLevel = 'Good';
                performanceIcon = '👍';
            } else if (avgScore >= 50) {
                performanceLevel = 'Learning';
                performanceIcon = '🎓';
            } else {
                performanceLevel = 'Needs Training';
                performanceIcon = '📚';
            }
            
            widget.innerHTML = `
                <h4><i class="fas fa-chart-line"></i> Progrès d'Apprentissage IA</h4>
                <div class="learning-metrics">
                    <div class="metric">
                        <span class="metric-label">Score Réel (avec manqués):</span>
                        <span class="metric-value">${avgScore}%</span>
                        <span class="performance-indicator">${performanceIcon} ${performanceLevel}</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">Total Validations:</span>
                        <span class="metric-value">${validations}</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">Amélioration:</span>
                        <span class="metric-trend">📈 Active</span>
                    </div>
                </div>
                <div class="learning-explanation">
                    <small>
                        <i class="fas fa-info-circle"></i>
                        Le score inclut: annotations correctes, erreurs supprimées, et manquées ajoutées
                    </small>
                </div>
            `;
            
            widget.style.display = 'block';
        })
        .catch(error => {
            console.error('Error loading learning data:', error);
        });
}

// Show learning widget with AI progress
function showLearningWidget(data) {
    let widget = document.getElementById('learning-widget');
    
    if (!widget) {
        widget = document.createElement('section');
        widget.id = 'learning-widget';
        widget.className = 'learning-dashboard-widget';
        
        const container = document.querySelector('.main-content');
        container.appendChild(widget);
    }
    
    // Fetch and display learning metrics
    fetch('/learning/dashboard/')
        .then(response => response.json())
        .then(learningData => {
            widget.innerHTML = `
                <h4><i class="fas fa-chart-line"></i> Progrès d'Apprentissage IA</h4>
                <div class="learning-metrics">
                    <div class="metric">
                        <span class="metric-label">Score Feedback Moyen:</span>
                        <span class="metric-value">${(learningData.average_feedback_score * 100).toFixed(0)}%</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">Total Validations:</span>
                        <span class="metric-value">${learningData.total_feedbacks}</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">Amélioration:</span>
                        <span class="metric-trend">📈 Active</span>
                    </div>
                </div>
            `;
            
            widget.style.display = 'block';
        })
        .catch(error => {
            console.error('Error loading learning data:', error);
        });
}

// Update page selector to show validation status
function updatePageSelector() {
    const pageSelect = document.getElementById('page-select');
    if (pageSelect) {
        const currentOption = pageSelect.querySelector('option:checked');
        if (currentOption && !currentOption.textContent.includes('🎓')) {
            currentOption.textContent = currentOption.textContent.replace('✅', '🎓');
        }
    }
}

// Enhanced success message function
function showSuccessMessage(message) {
    const alert = document.createElement('div');
    alert.className = 'alert alert-success';
    alert.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        background: linear-gradient(45deg, #10b981, #047857);
        color: white;
        padding: 1rem 1.5rem;
        border-radius: 8px;
        box-shadow: 0 4px 15px rgba(16, 185, 129, 0.3);
        z-index: 1000;
        font-weight: 600;
    `;
    alert.innerHTML = `<i class="fas fa-check-circle"></i> ${message}`;
    
    document.body.appendChild(alert);
    
    setTimeout(() => {
        alert.remove();
    }, 4000);
}

// Enhanced error message function
function showErrorMessage(message) {
    const alert = document.createElement('div');
    alert.className = 'alert alert-error';
    alert.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        background: linear-gradient(45deg, #ef4444, #dc2626);
        color: white;
        padding: 1rem 1.5rem;
        border-radius: 8px;
        box-shadow: 0 4px 15px rgba(239, 68, 68, 0.3);
        z-index: 1000;
        font-weight: 600;
    `;
    alert.innerHTML = `<i class="fas fa-exclamation-circle"></i> ${message}`;
    
    document.body.appendChild(alert);
    
    setTimeout(() => {
        alert.remove();
    }, 4000);
}

// Load learning dashboard on page load
document.addEventListener('DOMContentLoaded', function() {
    // Check if page is already validated
    const validateBtn = document.getElementById('validate-page-btn');
    if (validateBtn && validateBtn.textContent.includes('Validée')) {
        showLearningWidget({});
    }
    
    // Add RLHF indicator to AI-generated annotations
    const annotations = document.querySelectorAll('.annotation-item');
    annotations.forEach(annotation => {
        const reasoning = annotation.querySelector('.annotation-reasoning');
        if (reasoning && reasoning.textContent.includes('RLHF')) {
            annotation.classList.add('ai-generated');
            
            // Add learning indicator
            const learningIndicator = document.createElement('div');
            learningIndicator.className = 'rlhf-indicator';
            learningIndicator.innerHTML = '<i class="fas fa-brain"></i> IA Apprenante';
            annotation.appendChild(learningIndicator);
        }
    });
});

// Utility function to get CSRF token
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}