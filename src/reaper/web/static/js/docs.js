// Documentation Page Interactions

// Mobile sidebar toggle
document.addEventListener('DOMContentLoaded', () => {
    const sidebar = document.getElementById('docs-sidebar');
    const toggleBtn = document.getElementById('mobile-sidebar-toggle');
    const closeBtn = document.getElementById('close-sidebar-btn');
    
    if (sidebar && toggleBtn && closeBtn) {
        toggleBtn.addEventListener('click', () => {
            sidebar.classList.remove('-translate-x-full');
        });
        
        closeBtn.addEventListener('click', () => {
            sidebar.classList.add('-translate-x-full');
        });
        
        // Close sidebar when clicking outside
        sidebar.addEventListener('click', (e) => {
            if (e.target === sidebar) {
                sidebar.classList.add('-translate-x-full');
            }
        });
    }
});

function initMarkdownDocs() {
    const markdownContainers = document.querySelectorAll('.doc-markdown-body');
    markdownContainers.forEach(container => {
        // Only render if not already rendered
        if (!container.hasAttribute('data-rendered')) {
            const rawContent = container.getAttribute('data-markdown-content') || '';
            if (rawContent && typeof marked !== 'undefined') {
                container.innerHTML = marked.parse(rawContent);
                container.setAttribute('data-rendered', 'true');
                
                // Generate table of contents
                generateTableOfContents(container);
                
                // Add syntax highlighting
                if (typeof hljs !== 'undefined') {
                    container.querySelectorAll('pre code').forEach((block) => {
                        hljs.highlightElement(block);
                    });
                }
                
                // Add copy-to-code functionality
                addCodeCopyButtons(container);
            }
        }
    });
}

function generateTableOfContents(container) {
    // Find the section ID
    const section = container.closest('.doc-section');
    if (!section) return;
    
    const sectionId = section.id.replace('section-', '');
    const tocContainer = document.getElementById(`toc-${sectionId}`);
    if (!tocContainer) return;
    
    const headings = container.querySelectorAll('h2, h3, h4');
    if (headings.length === 0) {
        tocContainer.innerHTML = '<li class="text-[var(--text-muted)]">No headings found</li>';
        return;
    }
    
    let html = '';
    headings.forEach((heading, index) => {
        const text = heading.textContent.trim();
        const level = parseInt(heading.tagName.charAt(1));
        const indent = (level - 2) * 16;
        const id = `heading-${sectionId}-${index}`;
        heading.id = id;
        
        html += `
            <li class="pl-[${indent}px]">
                <a href="#${id}" class="text-[var(--text-secondary)] hover:text-[var(--accent-primary)] transition block py-1 text-sm">
                    ${text}
                </a>
            </li>
        `;
    });
    
    tocContainer.innerHTML = html;
}

function addCodeCopyButtons(container) {
    const codeBlocks = container.querySelectorAll('pre');
    codeBlocks.forEach(block => {
        const button = document.createElement('button');
        button.className = 'absolute top-2 right-2 px-2 py-1 bg-[var(--bg-tertiary)] border border-[var(--border-default)] rounded text-xs text-[var(--text-secondary)] hover:text-[var(--accent-primary)] transition opacity-0 group-hover:opacity-100';
        button.innerHTML = '<i class="fas fa-copy mr-1"></i>Copy';
        button.setAttribute('data-copy-state', 'copy');
        
        const wrapper = document.createElement('div');
        wrapper.className = 'relative group';
        block.parentNode.insertBefore(wrapper, block);
        wrapper.appendChild(block);
        wrapper.appendChild(button);
        
        button.addEventListener('click', async () => {
            const code = block.textContent;
            try {
                await navigator.clipboard.writeText(code);
                button.innerHTML = '<i class="fas fa-check mr-1"></i>Copied!';
                button.classList.add('text-[var(--success-primary)]', 'border-[var(--success-primary)]');
                setTimeout(() => {
                    button.innerHTML = '<i class="fas fa-copy mr-1"></i>Copy';
                    button.classList.remove('text-[var(--success-primary)]', 'border-[var(--success-primary)]');
                }, 2000);
            } catch (err) {
                console.error('Failed to copy:', err);
            }
        });
    });
}

function showDoc(filename) {
    // Hide all sections with fade out
    document.querySelectorAll('.doc-section').forEach(section => {
        section.style.opacity = '0';
        setTimeout(() => {
            section.classList.add('hidden');
            section.style.opacity = '';
        }, 200);
    });

    // Reset all buttons
    document.querySelectorAll('[id^="nav-btn-"]').forEach(btn => {
        btn.classList.remove('bg-[var(--accent-subtle)]', 'text-[var(--accent-primary)]', 'border-l-2', 'border-[var(--accent-primary)]');
        btn.classList.add('text-[var(--text-secondary)]');
    });

    // Show target section with fade in
    setTimeout(() => {
        const targetSection = document.getElementById('section-' + filename);
        if (targetSection) {
            targetSection.classList.remove('hidden');
            targetSection.style.opacity = '0';
            setTimeout(() => {
                targetSection.style.opacity = '1';
            }, 50);
        }

        // Highlight target button
        const targetBtn = document.getElementById('nav-btn-' + filename);
        if (targetBtn) {
            targetBtn.classList.add('bg-[var(--accent-subtle)]', 'text-[var(--accent-primary)]', 'border-l-2', 'border-[var(--accent-primary)]');
            targetBtn.classList.remove('text-[var(--text-secondary)]');
        }
    }, 200);

    // Scroll to top
    window.scrollTo({ top: 0, behavior: 'smooth' });
}

async function triggerDocSearch() {
    const input = document.getElementById('doc-search-input') || document.getElementById('doc-search-input-mobile');
    if (!input || !input.value.trim()) return;

    const query = input.value.trim();
    const panel = document.getElementById('search-results-panel');
    const content = document.getElementById('search-results-content');
    
    // Show loading
    panel.classList.remove('hidden');
    content.innerHTML = '<div class="text-sm text-[var(--text-muted)]"><i class="fas fa-spinner fa-spin mr-2"></i>Searching documentation...</div>';

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
                    <div class="p-4 bg-[var(--bg-tertiary)] border border-[var(--border-default)] rounded-lg hover:border-[var(--accent-primary)] cursor-pointer transition" onclick="showDoc('${res.metadata.filename}')">
                        <div class="text-xs font-bold text-[var(--accent-primary)] uppercase tracking-wider mb-2">
                            ${res.metadata.title} <span class="text-[var(--text-muted)] font-normal">(Score: ${(res.score * 100).toFixed(1)}%)</span>
                        </div>
                        <div class="text-sm text-[var(--text-secondary)] italic">"...${res.text.substring(0, 150)}..."</div>
                    </div>
                `;
            });
            content.innerHTML = html;
        } else {
            content.innerHTML = '<div class="text-sm text-[var(--error-primary)]">No semantic matches found for this query.</div>';
        }
    } catch (e) {
        console.error(e);
        content.innerHTML = '<div class="text-sm text-[var(--error-primary)]">Error performing search. Ensure the search engine is running.</div>';
    }
}

function closeSearchResults() {
    const panel = document.getElementById('search-results-panel');
    if (panel) panel.classList.add('hidden');
}

// Add keyboard shortcuts
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        closeSearchResults();
    }
    if (e.key === '/' && (e.metaKey || e.ctrlKey)) {
        const input = document.getElementById('doc-search-input');
        if (input) {
            e.preventDefault();
            input.focus();
        }
    }
});

// Re-init markdown rendering on page load and htmx swap
document.addEventListener('DOMContentLoaded', () => {
    initMarkdownDocs();
    // Add smooth scrolling to TOC links
    document.addEventListener('click', (e) => {
        if (e.target.matches('a[href^="#"]')) {
            e.preventDefault();
            const target = document.querySelector(e.target.getAttribute('href'));
            if (target) {
                target.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
        }
    });
});

document.addEventListener('htmx:afterSwap', function(evt) {
    if (window.location.pathname.includes('/docs')) {
        initMarkdownDocs();
    }
});
