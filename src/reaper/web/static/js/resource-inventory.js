/**
 * Resource Inventory page — display all Azure resources with cost optimization insights.
 * Supports 20+ categories, server-side pagination, filtering, search, and CSV export.
 */
(function () {
    'use strict';

    // ── State ────────────────────────────────────────────────────────────────
    let resourceInventory = null;   // full /api/resources/inventory data object
    let currentPage = 1;
    let pageSize = 50;
    let totalResources = 0;
    let totalPages = 1;
    let searchDebounceTimer = null;
    let isAuthRequired = true; // This page requires authentication

    // ── Category meta-data ───────────────────────────────────────────────────
    const CATEGORY_META = {
        virtual_machines:   { icon: '🖥️',  label: 'Virtual Machines',  color: 'var(--color-cyan)' },
        disks:              { icon: '💾',  label: 'Disks',             color: 'var(--color-blue)' },
        storage_accounts:   { icon: '🗄️',  label: 'Storage Accounts',   color: 'var(--color-indigo)' },
        network_resources:  { icon: '🌐',  label: 'Network',           color: 'var(--color-purple)' },
        databases:          { icon: '🗄️',  label: 'Databases',         color: 'var(--color-amber)' },
        app_services:       { icon: '⚙️',  label: 'App Services',      color: 'var(--color-emerald)' },
        functions:          { icon: '⚡',  label: 'Functions',         color: 'var(--color-yellow)' },
        kubernetes:         { icon: '☸️',  label: 'Kubernetes',        color: 'var(--color-blue)' },
        key_vaults:         { icon: '🔐',  label: 'Key Vaults',        color: 'var(--color-red)' },
        cognitive_services: { icon: '🧠',  label: 'AI / Cognitive',    color: 'var(--color-purple)' },
        monitoring:         { icon: '📊',  label: 'App Insights',      color: 'var(--color-cyan)' },
        messaging:          { icon: '📡',  label: 'Messaging & Events',color: 'var(--color-pink)' },
        other_resources:    { icon: '❓',  label: 'Other Resources',   color: 'var(--color-slate)' },
    };

    // All inventory category keys (mirrors the backend dict)
    const ALL_CATEGORIES = Object.keys(CATEGORY_META);

    // ── Utilities ────────────────────────────────────────────────────────────
    function escapeHtml(str) {
        if (str == null) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function showLoading(container, message) {
        container.innerHTML =
            '<div class="loading-block">' +
            '<div class="spinner" role="status" aria-label="Loading"></div>' +
            '<p>' + escapeHtml(message) + '</p></div>';
    }

    function showError(container, message) {
        container.innerHTML =
            '<div class="empty-state-pro"><p class="empty-state-pro__title text-error">Error</p>' +
            '<p class="empty-state-pro__desc">' + escapeHtml(message) + '</p></div>';
    }

    // ── Flatten helper ───────────────────────────────────────────────────────
    /**
     * Collect all resources from every category in the inventory object.
     */
    function flattenResources(inventory) {
        const all = [];
        ALL_CATEGORIES.forEach(cat => {
            const list = inventory[cat];
            if (Array.isArray(list)) {
                list.forEach(r => all.push(r));
            }
        });
        return all;
    }

    // ── API fetch ────────────────────────────────────────────────────────────
    async function fetchInventory(page) {
        const container = document.getElementById('resources-container');
        if (!container) return;

        showLoading(container, 'Fetching Azure resource inventory…');

        const categoryFilter = (document.getElementById('category-filter') || {}).value || 'all';
        const statusFilter   = (document.getElementById('status-filter')   || {}).value || 'all';
        const searchTerm     = ((document.getElementById('search-resources') || {}).value || '').trim();

        const params = new URLSearchParams({ page, page_size: pageSize });
        if (categoryFilter !== 'all') params.set('category', categoryFilter);
        if (statusFilter   !== 'all') params.set('status',   statusFilter);
        if (searchTerm)               params.set('q',        searchTerm);

        try {
            const response = await fetch('/api/resources/inventory?' + params.toString());
            const data = await response.json();

            if (data.status === 'success') {
                resourceInventory = data.data;
                currentPage   = data.page       || 1;
                totalResources = data.total      || 0;
                totalPages    = data.total_pages || 1;

                updateSummary(resourceInventory.summary);
                // Use server-paginated flat list if available, otherwise derive client-side
                const resources = data.resources || flattenResources(resourceInventory);
                renderResources(resources);
                renderPagination();
            } else {
                showError(container, data.message || 'Unknown error');
                renderPagination();
            }
        } catch (err) {
            showError(container, err.message);
            renderPagination();
        }
    }

    // ── Summary cards ────────────────────────────────────────────────────────
    function updateSummary(summary) {
        if (!summary) return;
        const set = (id, text) => { const el = document.getElementById(id); if (el) el.textContent = text; };
        set('total-resources',    summary.total_resources);
        set('idle-resources',     summary.idle_resources);
        set('orphaned-resources', summary.orphaned_resources);
        set('estimated-cost',     '$' + (summary.estimated_monthly_cost || 0).toFixed(2));

        // Update category breakdown pills if present
        const breakdown = document.getElementById('category-breakdown');
        if (breakdown && summary.by_category) {
            breakdown.innerHTML = Object.entries(summary.by_category)
                .filter(([, count]) => count > 0)
                .sort(([, a], [, b]) => b - a)
                .map(([cat, count]) => {
                    const meta = CATEGORY_META[cat] || { icon: '❓', label: cat };
                    return `<span class="category-pill" onclick="quickFilter('${escapeHtml(cat)}')" title="${escapeHtml(meta.label)}">${meta.icon} ${escapeHtml(meta.label)} <strong>${count}</strong></span>`;
                })
                .join('');
        }
    }

    // ── Render resource cards ────────────────────────────────────────────────
    function renderResources(resources) {
        const container = document.getElementById('resources-container');
        if (!container) return;

        if (!resources || resources.length === 0) {
            container.innerHTML =
                '<div class="empty-state-pro">' +
                '<p class="empty-state-pro__title">No resources found</p>' +
                '<p class="empty-state-pro__desc">Your Azure subscription may not have resources matching the current filter, or there may be a connection issue.</p>' +
                '</div>';
            return;
        }

        container.innerHTML = resources.map(renderResourceCard).join('');
    }

    function renderResourceCard(resource) {
        const cat  = resource.category || 'other_resources';
        const meta = CATEGORY_META[cat] || CATEGORY_META['other_resources'];

        const statusClass =
            (resource.status === 'Idle' || resource.status === 'Stopped')      ? 'text-warning' :
            (resource.status === 'Orphaned' || resource.status === 'Unassociated' || resource.status === 'Empty') ? 'text-error' :
            (resource.status === 'Active' || resource.status === 'Succeeded')   ? 'text-success' :
            'text-secondary';

        const dismissBtn = resource.can_dismiss
            ? `<button type="button" class="btn btn-error btn-sm"
                   id="dismiss-btn-${escapeHtml(resource.id ? resource.id.slice(-8) : Math.random())}"
                   onclick="dismissResource('${escapeHtml(resource.id)}', '${escapeHtml(resource.dismiss_reason || 'Manual dismissal')}')">
                   Dismiss
               </button>`
            : '';

        const cost = (typeof resource.estimated_cost === 'number')
            ? '$' + resource.estimated_cost.toFixed(2)
            : '$0.00';

        // Extra metadata row
        let extraLine = '';
        if (resource.size)              extraLine = 'Size: ' + resource.size;
        else if (resource.sku)          extraLine = 'SKU: ' + resource.sku;
        else if (resource.kind)         extraLine = 'Kind: ' + resource.kind;
        else if (resource.kubernetes_version) extraLine = 'K8s: ' + resource.kubernetes_version + ' · ' + resource.node_count + ' nodes';

        return (
            '<article class="rec-card">' +
            '<div class="rec-card__body">' +
            '<div class="flex-1 min-w-0">' +
            '<div class="rec-card__meta">' +
            `<span class="badge" style="background:${meta.color}22;color:${meta.color};border-color:${meta.color}44">${meta.icon} ${escapeHtml(meta.label)}</span>` +
            `<span class="badge ${statusClass}">${escapeHtml(resource.status || 'Unknown')}</span>` +
            '</div>' +
            `<h3 class="rec-card__title">${escapeHtml(resource.name)}</h3>` +
            `<p class="rec-card__desc">${escapeHtml(resource.type)}</p>` +
            `<p class="text-sm text-secondary mt-1">📍 ${escapeHtml(resource.location || '—')}` +
            (extraLine ? ` &nbsp;·&nbsp; ${escapeHtml(extraLine)}` : '') +
            '</p>' +
            '</div>' +
            '<div class="rec-card__savings">' +
            `<div class="stat-card__value stat-card__value--accent text-lg">${cost}</div>` +
            '<div class="stat-card__hint">est. monthly</div>' +
            '</div>' +
            '</div>' +
            (resource.dismiss_reason
                ? `<div class="rec-card__panel bg-warning-subtle border border-warning">` +
                  `<p class="text-warning text-sm font-bold">⚠️ ${escapeHtml(resource.dismiss_reason)}</p></div>`
                : '') +
            '<div class="rec-card__actions">' +
            `<button type="button" class="btn btn-ghost btn-sm"
                 onclick="viewResourceDetails('${escapeHtml(resource.id)}')">Details</button>` +
            dismissBtn +
            '</div>' +
            '</article>'
        );
    }

    // ── Pagination ───────────────────────────────────────────────────────────
    function renderPagination() {
        const bar = document.getElementById('pagination-controls');
        if (!bar) return;

        if (totalPages <= 1) {
            bar.style.display = 'none';
            return;
        }
        bar.style.display = 'flex';

        const prevDisabled = currentPage <= 1 ? 'disabled' : '';
        const nextDisabled = currentPage >= totalPages ? 'disabled' : '';

        bar.innerHTML =
            `<button class="btn btn-ghost btn-sm" ${prevDisabled} onclick="window.loadPage(${currentPage - 1})">← Prev</button>` +
            `<span class="pagination-info">Page ${currentPage} of ${totalPages} &nbsp;·&nbsp; ${totalResources} resources</span>` +
            `<button class="btn btn-ghost btn-sm" ${nextDisabled} onclick="window.loadPage(${currentPage + 1})">Next →</button>`;
    }

    window.loadPage = function (page) {
        if (page < 1 || page > totalPages) return;
        currentPage = page;
        fetchInventory(currentPage);
    };

    // ── Public API ───────────────────────────────────────────────────────────
    window.loadResourceInventory = function () {
        currentPage = 1;
        fetchInventory(currentPage);
    };

    window.filterResources = function () {
        currentPage = 1;
        fetchInventory(currentPage);
    };

    window.quickFilter = function (category) {
        const sel = document.getElementById('category-filter');
        if (sel) { sel.value = category; }
        currentPage = 1;
        fetchInventory(currentPage);
    };

    window.viewResourceDetails = function (resourceId) {
        if (!resourceInventory) return;
        const resource = flattenResources(resourceInventory).find(r => r.id === resourceId);
        if (!resource) return;

        const lines = [
            'Resource Details',
            '',
            'Name:     ' + resource.name,
            'Type:     ' + resource.type,
            'Location: ' + (resource.location || '—'),
            'Status:   ' + (resource.status || '—'),
            'Category: ' + (resource.category || '—'),
            'Est. Cost: $' + (resource.estimated_cost || 0).toFixed(2) + '/mo',
        ];
        if (resource.size)   lines.push('Size: ' + resource.size);
        if (resource.sku)    lines.push('SKU:  ' + resource.sku);
        if (resource.kind)   lines.push('Kind: ' + resource.kind);
        alert(lines.join('\n'));
    };

    window.dismissResource = async function (resourceId, reason) {
        if (!confirm('Are you sure you want to dismiss this resource? This action may have cost implications.')) return;
        try {
            const response = await fetch('/api/resources/' + encodeURIComponent(resourceId) + '/dismiss', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ reason }),
            });
            const data = await response.json();
            if (data.status === 'success') {
                if (typeof showToast === 'function') showToast(data.message, 'success');
                else alert(data.message);
                fetchInventory(currentPage);
            } else {
                alert('Error dismissing resource: ' + data.message);
            }
        } catch (err) {
            alert('Error dismissing resource: ' + err.message);
        }
    };

    // ── Export to CSV ────────────────────────────────────────────────────────
    window.exportInventory = function () {
        if (!resourceInventory) {
            alert('No inventory data loaded yet. Please click Refresh first.');
            return;
        }
        const all = flattenResources(resourceInventory);
        if (all.length === 0) {
            alert('No resources to export.');
            return;
        }
        const headers = ['name', 'type', 'category', 'location', 'status', 'estimated_cost', 'id'];
        const rows = all.map(r =>
            headers.map(h => {
                const val = r[h] != null ? String(r[h]) : '';
                return '"' + val.replace(/"/g, '""') + '"';
            }).join(',')
        );
        const csv = [headers.join(','), ...rows].join('\r\n');
        const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
        const url  = URL.createObjectURL(blob);
        const a    = document.createElement('a');
        a.href     = url;
        a.download = 'azure-resource-inventory-' + new Date().toISOString().slice(0, 10) + '.csv';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    };

    // ── Search debounce ──────────────────────────────────────────────────────
    window.onSearchInput = function () {
        clearTimeout(searchDebounceTimer);
        searchDebounceTimer = setTimeout(function () {
            currentPage = 1;
            fetchInventory(currentPage);
        }, 350);
    };

    // ── Cloud Provider Authentication Event Handlers ───────────────────────────────
    function handleProviderActivated(event) {
        const { authenticated, subscription_id } = event.detail;

        if (authenticated) {
            console.log('[resource-inventory] Provider activated, loading data...');
            // Enable page features
            const authElements = document.querySelectorAll('.auth-required');
            authElements.forEach(el => {
                el.disabled = false;
                el.classList.remove('opacity-40', 'pointer-events-none');
            });

            // Un-hide content
            const hiddenElements = document.querySelectorAll('[data-auth-hidden="true"]');
            hiddenElements.forEach(el => el.classList.remove('hidden'));

            // Load data automatically
            loadResourceInventory();
        }
    }

    function handleProviderDeactivated(event) {
        const { authenticated } = event.detail;

        if (!authenticated && isAuthRequired) {
            console.log('[resource-inventory] Provider deactivated, disabling features...');
            // Disable page features
            const authElements = document.querySelectorAll('.auth-required');
            authElements.forEach(el => {
                el.disabled = true;
                el.classList.add('opacity-40', 'pointer-events-none');
            });

            // Hide content
            const hiddenElements = document.querySelectorAll('[data-auth-hidden="true"]');
            hiddenElements.forEach(el => el.classList.add('hidden'));

            // Show auth prompt
            if (typeof window.setAuthOverlay === 'function') {
                window.setAuthOverlay(true);
            }
        }
    }

    // ── Auto-load on DOMContentLoaded ────────────────────────────────────────
    document.addEventListener('DOMContentLoaded', function () {
        // Listen for cloud provider activation events
        window.addEventListener('cloudProviderActivated', function (event) {
            if (event.detail.authenticated) {
                handleProviderActivated(event);
            } else {
                handleProviderDeactivated(event);
            }
        });

        // Check initial authentication state
        if (typeof window.getAuthState === 'function') {
            const initialState = window.getAuthState();
            if (initialState.authenticated) {
                handleProviderActivated({ detail: initialState });
            } else if (isAuthRequired) {
                handleProviderDeactivated({ detail: initialState });
            }
        }

        // Load inventory if authenticated
        if (document.getElementById('resources-container')) {
            loadResourceInventory();
        }
    });

    // ── HTMX SPA Navigation Support ────────────────────────────────────────────
    document.body.addEventListener('htmx:afterSwap', function () {
        // Re-attach event listeners after SPA navigation
        if (document.getElementById('resources-container')) {
            // Check authentication state again after navigation
            if (typeof window.getAuthState === 'function') {
                const currentState = window.getAuthState();
                if (currentState.authenticated) {
                    handleProviderActivated({ detail: currentState });
                } else if (isAuthRequired) {
                    handleProviderDeactivated({ detail: currentState });
                }
            }
            loadResourceInventory();
        }
    });
})();