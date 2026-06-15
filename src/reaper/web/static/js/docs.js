// Documentation Page Interactions

function initMarkdownDocs() {
    const markdownContainers = document.querySelectorAll('.doc-markdown-body');
    markdownContainers.forEach(container => {
        // Only render if not already rendered
        if (!container.hasAttribute('data-rendered')) {
            const rawContent = container.getAttribute('data-markdown-content') || '';
            if (rawContent && typeof marked !== 'undefined') {
                container.innerHTML = marked.parse(rawContent);
                container.setAttribute('data-rendered', 'true');
            }
        }
    });
}

function showDoc(filename) {
    // Hide all sections
    document.querySelectorAll('.doc-section').forEach(section => {
        section.classList.add('hidden');
    });

    // Reset all buttons
    document.querySelectorAll('[id^="nav-btn-"]').forEach(btn => {
        btn.classList.remove('text-cyan-400', 'border-cyan-500/30', 'shadow-[0_0_15px_rgba(6,182,212,0.15)]');
        btn.classList.add('text-gray-400', 'border-white/5');
        
        const icon = btn.querySelector('i');
        if (icon) {
            icon.classList.remove('text-cyan-400');
            icon.classList.add('text-gray-500');
        }
    });

    // Show target section
    const targetSection = document.getElementById('section-' + filename);
    if (targetSection) {
        targetSection.classList.remove('hidden');
    }

    // Highlight target button
    const targetBtn = document.getElementById('nav-btn-' + filename);
    if (targetBtn) {
        targetBtn.classList.add('text-cyan-400', 'border-cyan-500/30', 'shadow-[0_0_15px_rgba(6,182,212,0.15)]');
        targetBtn.classList.remove('text-gray-400', 'border-white/5');
        
        const targetIcon = document.getElementById('nav-icon-' + filename);
        if (targetIcon) {
            targetIcon.classList.add('text-cyan-400');
            targetIcon.classList.remove('text-gray-500');
        }
    }
}

async function triggerDocSearch() {
    const input = document.getElementById('doc-search-input');
    if (!input || !input.value.trim()) return;

    const query = input.value.trim();
    const panel = document.getElementById('search-results-panel');
    const content = document.getElementById('search-results-content');
    
    // Show loading
    panel.classList.remove('hidden');
    content.innerHTML = '<div class="text-xs text-gray-500"><i class="fas fa-spinner fa-spin mr-2"></i> Searching document vectors...</div>';

    try {
        const response = await fetch('/api/v1/docs/search', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query: query })
        });
        
        const data = await response.json();
        if (data.status === 'success' && data.results && data.results.length > 0) {
            let html = '';
            data.results.forEach(res => {
                html += `
                    <div class="p-4 bg-white/5 border border-white/10 rounded-lg hover:border-cyan-500/50 transition cursor-pointer" onclick="showDoc('${res.metadata.filename}')">
                        <div class="text-[10px] font-black text-cyan-400 uppercase tracking-wider mb-2">${res.metadata.title} (Score: ${(res.score*100).toFixed(1)}%)</div>
                        <div class="text-xs text-slate-300 italic">"...${res.text.substring(0, 150)}..."</div>
                    </div>
                `;
            });
            content.innerHTML = html;
        } else {
            content.innerHTML = '<div class="text-xs text-rose-400">No semantic matches found for this query.</div>';
        }
    } catch (e) {
        console.error(e);
        content.innerHTML = '<div class="text-xs text-rose-500">Error performing vector search. Ensure the AI engine is running.</div>';
    }
}

function closeSearchResults() {
    const panel = document.getElementById('search-results-panel');
    if (panel) panel.classList.add('hidden');
}

// Re-init markdown rendering on page load and htmx swap
document.addEventListener('DOMContentLoaded', initMarkdownDocs);
document.body.addEventListener('htmx:afterSwap', function(evt) {
    if (window.location.pathname.includes('/docs')) {
        initMarkdownDocs();
    }
});
