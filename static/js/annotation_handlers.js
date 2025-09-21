// Gestionnaire d'annotations centralisé

function addClickHandlerToAnnotation(annotation) {
    annotation.addEventListener('click', function(e) {
        e.preventDefault();
        e.stopPropagation();
        window.getSelection().removeAllRanges();
        
        const annotationId = this.dataset.annotationId;
        const annotationText = this.textContent.replace(this.querySelector('.ann-label').textContent, '').trim();
        
        // Remplacer l'élément annoté par son texte brut
        const textNode = document.createTextNode(annotationText);
        this.parentNode.replaceChild(textNode, this);
        
        // Supprimer l'annotation de la base de données
        deleteAnnotationFromDB(annotationId);
    });
}

// Ajouter les handlers aux annotations existantes dans toutes les zones
function initializeAnnotationHandlers() {
    // Sélectionner toutes les annotations dans la zone principale et structurée
    const allAnnotations = document.querySelectorAll('.inline-annotation');
    allAnnotations.forEach(annotation => {
        addClickHandlerToAnnotation(annotation);
    });
}

// Initialiser les handlers au chargement de la page
document.addEventListener('DOMContentLoaded', function() {
    initializeAnnotationHandlers();
});

// Fonction pour ajouter les handlers après l'ajout dynamique d'annotations
function addHandlersToNewAnnotations() {
    const mainArea = document.getElementById('page-text');
    const structuredArea = document.getElementById('structured-annotation-area');
    
    // Ajouter les handlers aux nouvelles annotations dans la zone principale
    if (mainArea) {
        const mainAnnotations = mainArea.querySelectorAll('.inline-annotation');
        mainAnnotations.forEach(annotation => {
            addClickHandlerToAnnotation(annotation);
        });
    }
    
    // Ajouter les handlers aux nouvelles annotations dans la zone structurée
    if (structuredArea) {
        const structuredAnnotations = structuredArea.querySelectorAll('.inline-annotation');
        structuredAnnotations.forEach(annotation => {
            addClickHandlerToAnnotation(annotation);
        });
    }
}