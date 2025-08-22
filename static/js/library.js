// Library JavaScript functionality

document.addEventListener('DOMContentLoaded', function() {
    initializeSearch();
    initializeDocumentCards();
    LibraryActions.ensureModal();
});

function initializeSearch() {
    const searchInput = document.getElementById('global-search');
    const searchResults = document.getElementById('search-results');
    let searchTimeout;

    if (!searchInput) return;

    searchInput.addEventListener('input', function() {
        const query = this.value.trim();
        
        // Clear previous timeout
        clearTimeout(searchTimeout);
        
        if (query.length < 2) {
            hideSearchResults();
            return;
        }

        // Debounce search
        searchTimeout = setTimeout(() => {
            performSearch(query);
        }, 300);
    });

    searchInput.addEventListener('focus', function() {
        if (this.value.trim().length >= 2) {
            showSearchResults();
        }
    });

    // Hide search results when clicking outside
    document.addEventListener('click', function(e) {
        if (!e.target.closest('.floating-search')) {
            hideSearchResults();
        }
    });

    function performSearch(query) {
        fetch(`/client/library/api/search/?q=${encodeURIComponent(query)}&limit=8`)
            .then(response => response.json())
            .then(data => {
                displaySearchResults(data);
            })
            .catch(error => {
                console.error('Search error:', error);
                hideSearchResults();
            });
    }

    function displaySearchResults(results) {
        if (results.length === 0) {
            searchResults.innerHTML = '<div class="search-result-item">Aucun document trouvé</div>';
        } else {
            const html = results.map(doc => `
                <div class="search-result-item" onclick="location.href='/library/documents/${doc.id}/'">
                    <div style="font-weight: 500; margin-bottom: 4px;">${doc.title}</div>
                    <div style="font-size: 0.8rem; color: #64748b;">
                        ${doc.authority} • ${doc.type}
                        ${doc.publication_date ? '• ' + new Date(doc.publication_date).toLocaleDateString('fr-FR') : ''}
                    </div>
                </div>
            `).join('');
            searchResults.innerHTML = html;
        }
        showSearchResults();
    }

    function showSearchResults() {
        searchResults.style.display = 'block';
    }

    function hideSearchResults() {
        searchResults.style.display = 'none';
    }
}

function initializeDocumentCards() {
    // Add click handlers for document cards
    const documentCards = document.querySelectorAll('.document-card');
    
    documentCards.forEach(card => {
        card.addEventListener('click', function(e) {
            // Don't navigate if clicking on a button or link inside
            if (e.target.closest('button') || e.target.closest('a')) {
                return;
            }
            
            const url = this.getAttribute('onclick');
            if (url) {
                // Extract URL from onclick attribute
                const match = url.match(/location\.href='([^']+)'/);
                if (match) {
                    window.location.href = match[1];
                }
            }
        });
    });
}

// Utility functions
function formatFileSize(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

function formatDate(dateString) {
    const date = new Date(dateString);
    return date.toLocaleDateString('fr-FR', {
        year: 'numeric',
        month: 'long',
        day: 'numeric'
    });
}

// Simple modal + API calls for analyze/summary
const LibraryActions = {
    ensureModal() {
        if (document.getElementById('library-modal')) return;
        const modal = document.createElement('div');
        modal.id = 'library-modal';
        modal.style.cssText = 'position:fixed;inset:0;display:none;align-items:center;justify-content:center;background:rgba(0,0,0,0.5);z-index:9999;';
        modal.innerHTML = `
            <div id="library-modal-content" style="background:#fff;max-width:900px;width:90%;border-radius:12px;box-shadow:0 10px 30px rgba(0,0,0,0.2);overflow:hidden;">
                <div style="display:flex;align-items:center;justify-content:space-between;padding:14px 16px;border-bottom:1px solid #e5e7eb;">
                    <div style="font-weight:700;color:#111827">Résultat</div>
                    <button id="library-modal-close" style="border:none;background:#ef4444;color:#fff;padding:6px 10px;border-radius:8px;cursor:pointer;">Fermer</button>
                </div>
                <div id="library-modal-body" style="max-height:70vh;overflow:auto;padding:16px;color:#111827;font-size:0.95rem;line-height:1.5;"></div>
            </div>`;
        document.body.appendChild(modal);
        document.getElementById('library-modal-close').addEventListener('click', LibraryActions.hide);
        modal.addEventListener('click', (e)=>{ if(e.target.id==='library-modal'){ LibraryActions.hide(); } });
    },
    show(html) {
        const modal = document.getElementById('library-modal');
        const body = document.getElementById('library-modal-body');
        body.innerHTML = html;
        modal.style.display = 'flex';
    },
    hide() { document.getElementById('library-modal').style.display = 'none'; },
    spinner(text='Analyse en cours...') {
        return `<div style="display:flex;align-items:center;gap:12px;color:#374151;"><span class="material-icons" style="color:#3b82f6;">autorenew</span>${text}</div>`
    },
    renderAnalysis(analysis){
        // Accepts object with summary, key_points, obligations, deadlines, authorities
        const esc = (s)=> (s==null?'' : String(s))
            .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
        const list = (arr)=> Array.isArray(arr)&&arr.length? `<ul style="margin:8px 0 0 18px;">${arr.map(x=>`<li>${esc(x)}</li>`).join('')}</ul>` : '<div style="color:#6b7280;">-</div>';
        return `
            <div>
                <h3 style="margin:0 0 8px 0;font-size:1.1rem;color:#111827;">Résumé</h3>
                <div style="white-space:pre-wrap;background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px;padding:10px;">${esc(analysis.summary||'')}</div>
                <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px;margin-top:12px;">
                    <div><div style="font-weight:700;color:#111827;margin-bottom:6px;">Points clés</div>${list(analysis.key_points)}</div>
                    <div><div style="font-weight:700;color:#111827;margin-bottom:6px;">Obligations</div>${list(analysis.obligations)}</div>
                    <div><div style="font-weight:700;color:#111827;margin-bottom:6px;">Délais</div>${list(analysis.deadlines)}</div>
                    <div><div style="font-weight:700;color:#111827;margin-bottom:6px;">Autorités</div>${list(analysis.authorities)}</div>
                </div>
            </div>`;
    },
    analyze(pk){
        LibraryActions.show(LibraryActions.spinner('Analyse du document...'));
        fetch(`/client/library/api/documents/${pk}/analyze/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': LibraryActions.csrf() },
            body: JSON.stringify({})
        }).then(async r=>{ if(!r.ok){ const t = await r.text(); throw new Error(`${r.status} ${t}`);} return r.json(); }).then(data=>{
            if (data.error){
                LibraryActions.show(`<div style="color:#b91c1c;">${data.error}</div>`);
                return;
            }
            const html = LibraryActions.renderAnalysis(data.analysis||{});
            LibraryActions.show(html);
        }).catch(err=>{
            LibraryActions.show(`<div style="color:#b91c1c;">Erreur: ${err}</div>`);
        });
    },
    rawText(pk){
        LibraryActions.show(LibraryActions.spinner('Extraction du texte brut...'));
        fetch(`/client/library/api/documents/${pk}/raw-text/`, {
            method: 'GET',
            headers: { 'X-CSRFToken': LibraryActions.csrf() }
        }).then(async r=>{ if(!r.ok){ const t = await r.text(); throw new Error(`${r.status} ${t}`);} return r.json(); }).then(data=>{
            if (data.error){
                LibraryActions.show(`<div style="color:#b91c1c;">${data.error}</div>`);
                return;
            }
            const esc = (s)=> (s==null?'' : String(s))
              .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
            LibraryActions.show(`
                <div style="color:#6b7280;font-size:0.85rem;margin-bottom:6px;">Texte brut extrait (aperçu)</div>
                <pre style="white-space:pre-wrap;background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px;padding:10px;max-height:70vh;overflow:auto;">${esc(data.text||'')}</pre>
            `);
        }).catch(err=>{
            LibraryActions.show(`<div style=\"color:#b91c1c;\">Erreur: ${err}</div>`);
        });
    },
    summary(pk, force=false){
        LibraryActions.show(LibraryActions.spinner(force ? 'Régénération du résumé...' : 'Chargement du résumé...'));
        fetch(`/client/library/api/documents/${pk}/summary/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': LibraryActions.csrf() },
            body: JSON.stringify({ force })
        }).then(async r=>{ if(!r.ok){ const t = await r.text(); throw new Error(`${r.status} ${t}`);} return r.json(); }).then(data=>{
            if (data.error){
                LibraryActions.show(`<div style="color:#b91c1c;">${data.error}</div>`);
                return;
            }
            const esc = (s)=> (s==null?'' : String(s))
              .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
            const when = data.generated_at ? new Date(data.generated_at).toLocaleString('fr-FR') : '';
            const meta = data.cached ? `<div style="color:#6b7280;font-size:0.85rem;margin-bottom:6px;">Résumé en cache (généré le ${when}).</div>` : `<div style="color:#059669;font-size:0.85rem;margin-bottom:6px;">Résumé mis à jour.</div>`;
            LibraryActions.show(`
                ${meta}
                <div style="white-space:pre-wrap;background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px;padding:10px;">${esc(data.summary||'')}</div>
            `);
        }).catch(err=>{
            LibraryActions.show(`<div style="color:#b91c1c;">Erreur: ${err}</div>`);
        });
    },
    csrf(){
        // Try to grab CSRF token from cookies (Django default)
        const m = document.cookie.match(/csrftoken=([^;]+)/);
        return m ? m[1] : '';
    }
};

// Export functions for use in other scripts
window.LibraryJS = {
    formatFileSize,
    formatDate
};
window.LibraryActions = LibraryActions;