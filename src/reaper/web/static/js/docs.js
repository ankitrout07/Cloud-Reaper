// Enhanced Documentation Page Interactions

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

    // Initialize search functionality
    initSearchFunctionality();
    
    // Initialize markdown rendering
    initMarkdownDocs();
});

function initSearchFunctionality() {
    const searchInput = document.getElementById('doc-search-input');
    const mobileSearchInput = document.getElementById('doc-search-input-mobile');
    
    if (searchInput) {
        searchInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                triggerDocSearch();
            }
        });
    }
    
    if (mobileSearchInput) {
        mobileSearchInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                triggerDocSearch();
            }
        });
    }
}

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
                
                // Enhance code blocks with language labels
                enhanceCodeBlocks(container);
                
                // Add callout/alert styling
                enhanceCallouts(container);
            }
        }
    });
}

function enhanceCodeBlocks(container) {
    container.querySelectorAll('pre code').forEach((block) => {
        const pre = block.parentElement;
        const languageClass = Array.from(block.classList).find(cls => cls.startsWith('language-'));
        if (languageClass) {
            const language = languageClass.replace('language-', '').toUpperCase();
            const label = document.createElement('div');
            label.className = 'text-xs font-bold text-slate-400 uppercase tracking-wider mb-2';
            label.textContent = language;
            pre.parentNode.insertBefore(label, pre);
        }
    });
}

function enhanceCallouts(container) {
    // Style blockquotes as callouts
    container.querySelectorAll('blockquote').forEach((blockquote) => {
        const text = blockquote.textContent.trim();
        if (text.startsWith('[!NOTE]') || text.startsWith('[!WARNING]') || text.startsWith('[!IMPORTANT]')) {
            blockquote.className = 'border-l-4 p-4 rounded-r-lg my-4';
            
            if (text.startsWith('[!NOTE]')) {
                blockquote.classList.add('border-cyan-500', 'bg-cyan-500/10');
                blockquote.innerHTML = blockquote.innerHTML.replace('[!NOTE]', '<span class="font-bold text-cyan-400">NOTE:</span>');
            } else if (text.startsWith('[!WARNING]')) {
                blockquote.classList.add('border-amber-500', 'bg-amber-500/10');
                blockquote.innerHTML = blockquote.innerHTML.replace('[!WARNING]', '<span class="font-bold text-amber-400">WARNING:</span>');
            } else if (text.startsWith('[!IMPORTANT]')) {
                blockquote.classList.add('border-purple-500', 'bg-purple-500/10');
                blockquote.innerHTML = blockquote.innerHTML.replace('[!IMPORTANT]', '<span class="font-bold text-purple-400">IMPORTANT:</span>');
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
    const tocCount = document.getElementById(`toc-count-${sectionId}`);
    if (!tocContainer) return;
    
    const headings = container.querySelectorAll('h2, h3, h4');
    if (headings.length === 0) {
        tocContainer.innerHTML = '<li class="text-slate-500">No headings found</li>';
        if (tocCount) tocCount.textContent = '0 sections';
        return;
    }
    
    // Update count
    if (tocCount) tocCount.textContent = `${headings.length} sections`;
    
    let html = '';
    headings.forEach((heading, index) => {
        const text = heading.textContent.trim();
        const level = parseInt(heading.tagName.charAt(1));
        const indent = (level - 2) * 16;
        const id = `heading-${sectionId}-${index}`;
        heading.id = id;
        
        const levelIndicator = level === 2 ? '¶' : (level === 3 ? '•' : '◦');
        
        html += `
            <li class="pl-[${indent}px]">
                <a href="#${id}" class="text-slate-400 hover:text-cyan-400 transition block py-2 text-sm flex items-center gap-2">
                    <span class="text-slate-500">${levelIndicator}</span>
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
        const wrapper = document.createElement('div');
        wrapper.className = 'code-block-wrapper group relative mb-4';
        
        const button = document.createElement('button');
        button.className = 'copy-code-btn absolute top-3 right-3 px-3 py-1.5 bg-slate-700/80 hover:bg-cyan-500/80 border border-slate-600 hover:border-cyan-500 rounded-lg text-xs text-slate-300 hover:text-white transition-all duration-200';
        button.innerHTML = '<i class="fas fa-copy mr-1"></i>Copy';
        button.setAttribute('data-copy-state', 'copy');
        
        block.parentNode.insertBefore(wrapper, block);
        wrapper.appendChild(block);
        wrapper.appendChild(button);
        
        button.addEventListener('click', async () => {
            const code = block.textContent;
            try {
                await navigator.clipboard.writeText(code);
                button.innerHTML = '<i class="fas fa-check mr-1"></i>Copied!';
                button.classList.add('bg-emerald-500/80', 'border-emerald-500', 'text-white');
                
                setTimeout(() => {
                    button.innerHTML = '<i class="fas fa-copy mr-1"></i>Copy';
                    button.classList.remove('bg-emerald-500/80', 'border-emerald-500', 'text-white');
                }, 2000);
            } catch (err) {
                console.error('Failed to copy:', err);
                button.innerHTML = '<i class="fas fa-times mr-1"></i>Failed';
                button.classList.add('bg-red-500/80', 'border-red-500', 'text-white');
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
        btn.classList.remove('active', 'bg-cyan-500/10', 'text-cyan-400', 'border-l-3', 'border-cyan-500');
        btn.classList.add('text-slate-400');
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
            targetBtn.classList.add('active', 'bg-cyan-500/10', 'text-cyan-400', 'border-l-3', 'border-cyan-500');
            targetBtn.classList.remove('text-slate-400');
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
    const count = document.getElementById('search-result-count');
    
    // Show loading
    panel.classList.remove('hidden');
    content.innerHTML = '<div class="text-sm text-slate-400 flex items-center gap-2"><i class="fas fa-spinner fa-spin"></i>Searching documentation...</div>';
    count.textContent = '0 results';

    try {
        const response = await fetch('/api/v1/docs/search', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query: query })
        });
        
        const data = await response.json();
        if (data.status === 'success' && data.results && data.results.length > 0) {
            // Store results globally for filtering
            if (typeof window !== 'undefined') {
                window.searchResults = data.results;
            }
            
            // Use the renderSearchResults function if available, otherwise render manually
            if (typeof renderSearchResults === 'function') {
                renderSearchResults(data.results);
            } else {
                let html = '';
                data.results.forEach((res, index) => {
                    const scorePercent = (res.score * 100).toFixed(1);
                    const relevanceColor = scorePercent > 80 ? 'emerald' : (scorePercent > 50 ? 'cyan' : 'orange');
                    
                    html += `
                        <div class="p-4 bg-slate-800/50 border border-slate-700 hover:border-cyan-500/50 rounded-xl cursor-pointer transition-all duration-200 hover:bg-slate-700/50" onclick="showDoc('${res.metadata.filename}')">
                            <div class="flex items-center justify-between mb-2">
                                <span class="text-xs font-bold text-cyan-400 uppercase tracking-wider">${res.metadata.title}</span>
                                <span class="text-[10px] bg-${relevanceColor}-500/20 text-${relevanceColor}-400 px-2 py-0.5 rounded-full font-medium">${scorePercent}% match</span>
                            </div>
                            <div class="text-sm text-slate-300 leading-relaxed">"${res.text.substring(0, 120)}..."</div>
                            <div class="text-[10px] text-slate-500 mt-2">
                                <i class="fas fa-file-alt mr-1"></i>${res.metadata.filename}
                            </div>
                        </div>
                    `;
                });
                content.innerHTML = html;
                if (count) count.textContent = `${data.results.length} results`;
            }
        } else {
            content.innerHTML = '<div class="text-sm text-amber-400 flex items-center gap-2"><i class="fas fa-exclamation-triangle"></i>No semantic matches found for this query. Try different keywords.</div>';
            if (count) count.textContent = '0 results';
        }
    } catch (e) {
        console.error(e);
        content.innerHTML = '<div class="text-sm text-red-400 flex items-center gap-2"><i class="fas fa-times-circle"></i>Error performing search. Ensure the search engine is running.</div>';
        if (count) count.textContent = '0 results';
    }
}

function closeSearchResults() {
    const panel = document.getElementById('search-results-panel');
    if (panel) panel.classList.add('hidden');
}

// Search filtering functionality
function filterSearchResults(category) {
    // Update active button states
    document.querySelectorAll('.search-filter-btn').forEach(btn => {
        btn.classList.remove('active', 'bg-cyan-500/20', 'border-cyan-500/30', 'text-cyan-400');
        btn.classList.add('bg-slate-800/50', 'border-slate-700', 'text-slate-400');
    });
    
    event.target.classList.add('active', 'bg-cyan-500/20', 'border-cyan-500/30', 'text-cyan-400');
    event.target.classList.remove('bg-slate-800/50', 'border-slate-700', 'text-slate-400');
    
    // Filter results
    const content = document.getElementById('search-results-content');
    const count = document.getElementById('search-result-count');
    let filteredResults = window.searchResults || [];
    
    if (category !== 'all') {
        filteredResults = filteredResults.filter(result => {
            const title = result.metadata.title.toLowerCase();
            if (category === 'getting-started') {
                return title.includes('getting') || title.includes('introduction') || title.includes('setup');
            } else if (category === 'technical') {
                return title.includes('architecture') || title.includes('api') || title.includes('scanner') || title.includes('engine');
            } else if (category === 'api') {
                return title.includes('api') || title.includes('endpoint');
            }
            return true;
        });
    }
    
    // Re-render filtered results
    renderSearchResults(filteredResults);
}

function renderSearchResults(results) {
    const content = document.getElementById('search-results-content');
    const count = document.getElementById('search-result-count');
    
    if (count) count.textContent = `${results.length} results`;
    
    if (results.length === 0) {
        content.innerHTML = '<div class="text-sm text-slate-400 flex items-center gap-2"><i class="fas fa-exclamation-triangle"></i>No results found for this filter.</div>';
        return;
    }
    
    let html = '';
    results.forEach((res, index) => {
        const scorePercent = (res.score * 100).toFixed(1);
        const relevanceColor = scorePercent > 80 ? 'emerald' : (scorePercent > 50 ? 'cyan' : 'orange');
        
        html += `
            <div class="p-4 bg-slate-800/50 border border-slate-700 hover:border-cyan-500/50 rounded-xl cursor-pointer transition-all duration-200 hover:bg-slate-700/50" onclick="showDoc('${res.metadata.filename}')">
                <div class="flex items-center justify-between mb-2">
                    <span class="text-xs font-bold text-cyan-400 uppercase tracking-wider">${res.metadata.title}</span>
                    <span class="text-[10px] bg-${relevanceColor}-500/20 text-${relevanceColor}-400 px-2 py-0.5 rounded-full font-medium">${scorePercent}% match</span>
                </div>
                <div class="text-sm text-slate-300 leading-relaxed">"${res.text.substring(0, 120)}..."</div>
                <div class="text-[10px] text-slate-500 mt-2 flex items-center gap-3">
                    <i class="fas fa-file-alt"></i>${res.metadata.filename}
                    <i class="fas fa-clock"></i>Recently updated
                </div>
            </div>
        `;
    });
    content.innerHTML = html;
}

// Enhanced keyboard shortcuts
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        closeSearchResults();
        // Also close mobile sidebar
        const sidebar = document.getElementById('docs-sidebar');
        if (sidebar && !sidebar.classList.contains('-translate-x-full')) {
            sidebar.classList.add('-translate-x-full');
        }
    }
    if ((e.key === 'k' || e.key === '/') && (e.metaKey || e.ctrlKey)) {
        const input = document.getElementById('doc-search-input');
        if (input) {
            e.preventDefault();
            input.focus();
        }
    }
});

// Add smooth scrolling and reading progress
document.addEventListener('DOMContentLoaded', () => {
    // Add smooth scrolling to TOC links
    document.addEventListener('click', (e) => {
        const a = e.target.closest('a[href^="#"]');
        if (a) {
            const href = a.getAttribute('href');
            if (href && href !== '#') {
                e.preventDefault();
                const targetId = href.substring(1);
                const target = document.getElementById(targetId);
                if (target) {
                    target.scrollIntoView({ behavior: 'smooth', block: 'start' });
                }
            }
        }
    });
    
    // Initialize reading progress indicator
    initReadingProgress();
});

function initReadingProgress() {
    const progressBar = document.createElement('div');
    progressBar.className = 'fixed top-0 left-0 h-1 bg-gradient-to-r from-cyan-500 to-blue-500 z-50 transition-all duration-300';
    progressBar.style.width = '0%';
    document.body.appendChild(progressBar);
    
    window.addEventListener('scroll', () => {
        const scrollTop = window.scrollY;
        const docHeight = document.documentElement.scrollHeight - window.innerHeight;
        const scrollPercent = (scrollTop / docHeight) * 100;
        progressBar.style.width = scrollPercent + '%';
    });
}

// Re-init markdown rendering on htmx swap
document.addEventListener('htmx:afterSwap', function(evt) {
    if (window.location.pathname.includes('/docs')) {
        initMarkdownDocs();
    }
});

// Add back the original showDoc function reference for external calls
window.showDoc = showDoc;
