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

    // ── Toasts ───────────────────────────────────────────────────────────────
    function toast(msg, type) {
        if (typeof window.showToast === 'function') { window.showToast(msg, type); return; }
        if (typeof window.notify   === 'function') { window.notify(msg, type);    return; }
        // Fallback: inline minimal toast
        const t = document.createElement('div');
        t.textContent = msg;
        t.style.cssText = 'position:fixed;bottom:1.5rem;right:1.5rem;z-index:9999;padding:0.75rem 1.25rem;border-radius:0.75rem;font-size:0.85rem;font-weight:600;color:#fff;backdrop-filter:blur(12px);animation:fadeIn 0.2s ease;';
        t.style.background = type === 'success' ? 'rgba(16,185,129,0.9)' : type === 'error' ? 'rgba(239,68,68,0.9)' : 'rgba(99,102,241,0.9)';
        document.body.appendChild(t);
        setTimeout(() => t.remove(), 3500);
    }

    // ── Resource Detail Modal ────────────────────────────────────────────────
    function openDetailModal(resource) {
        let modal = document.getElementById('resource-detail-modal');
        if (!modal) {
            modal = document.createElement('div');
            modal.id = 'resource-detail-modal';
            modal.style.cssText = 'position:fixed;inset:0;z-index:10000;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,0.65);backdrop-filter:blur(4px);';
            modal.innerHTML = `
              <div id="rdm-inner" style="background:rgba(15,23,42,0.95);border:1px solid rgba(255,255,255,0.12);border-radius:1.25rem;padding:2rem;max-width:480px;width:90%;box-shadow:0 25px 60px rgba(0,0,0,0.6);position:relative;">
                <button onclick="document.getElementById('resource-detail-modal').remove()" style="position:absolute;top:1rem;right:1rem;background:rgba(255,255,255,0.08);border:1px solid rgba(255,255,255,0.15);border-radius:50%;width:2rem;height:2rem;cursor:pointer;color:#94a3b8;font-size:1rem;line-height:1;" aria-label="Close">✕</button>
                <h2 id="rdm-title" style="font-size:1.1rem;font-weight:700;color:#f1f5f9;margin:0 0 1.25rem;letter-spacing:-0.02em;"></h2>
                <div id="rdm-body" style="display:grid;gap:0.6rem;"></div>
                <div id="rdm-footer" style="margin-top:1.5rem;display:flex;gap:0.75rem;justify-content:flex-end;"></div>
              </div>`;
            modal.addEventListener('click', (e) => { if (e.target === modal) modal.remove(); });
            document.body.appendChild(modal);
        }

        const cat = resource.category || 'other_resources';
        const meta = CATEGORY_META[cat] || { icon: '❓', label: cat };
        const cost = typeof resource.estimated_cost === 'number' ? '$' + resource.estimated_cost.toFixed(2) : '$0.00';

        const rows = [
            ['Name',       resource.name],
            ['Type',       resource.type],
            ['Location',   resource.location || '—'],
            ['Status',     resource.status   || '—'],
            ['Category',   meta.icon + ' ' + meta.label],
            ['Est. Cost',  cost + '/mo'],
        ];
        if (resource.size) rows.push(['Size', resource.size]);
        if (resource.sku)  rows.push(['SKU',  resource.sku]);
        if (resource.kind) rows.push(['Kind', resource.kind]);
        if (resource.kubernetes_version) rows.push(['K8s', resource.kubernetes_version + ' · ' + resource.node_count + ' nodes']);
        if (resource.id)   rows.push(['ID',   resource.id]);

        document.getElementById('rdm-title').textContent = '📋 Resource Details';
        document.getElementById('rdm-body').innerHTML = rows.map(([k, v]) =>
            `<div style="display:grid;grid-template-columns:130px 1fr;gap:0.5rem;align-items:start;padding:0.4rem 0.6rem;border-radius:0.5rem;background:rgba(255,255,255,0.03);">
              <span style="font-size:0.72rem;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:0.05em;">${escapeHtml(k)}</span>
              <span style="font-size:0.83rem;color:#e2e8f0;word-break:break-all;">${escapeHtml(String(v))}</span>
            </div>`
        ).join('');

        const footer = document.getElementById('rdm-footer');
        footer.innerHTML = '';
        if (resource.can_dismiss) {
            const btn = document.createElement('button');
            btn.className = 'btn btn-error btn-sm';
            btn.textContent = '🗑 Dismiss Resource';
            btn.onclick = () => { modal.remove(); dismissResource(resource.id, resource.dismiss_reason || 'Manual dismissal'); };
            footer.appendChild(btn);
        }
        const closeBtn = document.createElement('button');
        closeBtn.className = 'btn btn-ghost btn-sm';
        closeBtn.textContent = 'Close';
        closeBtn.onclick = () => modal.remove();
        footer.appendChild(closeBtn);
    }

    // ── Inline Confirm ───────────────────────────────────────────────────────
    function confirmAction(message, onConfirm) {
        let modal = document.getElementById('resource-confirm-modal');
        if (modal) modal.remove();
        modal = document.createElement('div');
        modal.id = 'resource-confirm-modal';
        modal.style.cssText = 'position:fixed;inset:0;z-index:10001;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,0.7);backdrop-filter:blur(4px);';
        modal.innerHTML = `
          <div style="background:rgba(15,23,42,0.97);border:1px solid rgba(239,68,68,0.3);border-radius:1.25rem;padding:2rem;max-width:400px;width:90%;box-shadow:0 25px 60px rgba(0,0,0,0.6);">
            <h3 style="color:#f87171;font-size:1rem;font-weight:700;margin:0 0 0.75rem;">⚠️ Confirm Action</h3>
            <p style="color:#94a3b8;font-size:0.875rem;margin:0 0 1.5rem;">${escapeHtml(message)}</p>
            <div style="display:flex;gap:0.75rem;justify-content:flex-end;">
              <button id="rcm-cancel" class="btn btn-ghost btn-sm">Cancel</button>
              <button id="rcm-confirm" class="btn btn-error btn-sm">Confirm</button>
            </div>
          </div>`;
        document.body.appendChild(modal);
        document.getElementById('rcm-cancel').onclick  = () => modal.remove();
        document.getElementById('rcm-confirm').onclick = () => { modal.remove(); onConfirm(); };
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
                currentPage    = data.page       || 1;
                totalResources  = data.total      || 0;
                totalPages     = data.total_pages || 1;

                // Show snapshot timestamp badge
                const tsBadge = document.getElementById('snapshot-timestamp-badge');
                if (tsBadge && data.data && data.data.timestamp) {
                    const d = new Date(data.data.timestamp * 1000);
                    tsBadge.textContent = '🕐 Snapshot: ' + d.toLocaleString();
                    tsBadge.style.display = 'inline-flex';
                }

                updateSummary(resourceInventory.summary);
                // Use server-paginated flat list if available, otherwise derive client-side
                const resources = data.resources || flattenResources(resourceInventory);
                renderResources(resources, data.db_empty);
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
    function renderResources(resources, dbEmpty) {
        const container = document.getElementById('resources-container');
        if (!container) return;

        if (dbEmpty || !resources || resources.length === 0) {
            const isDbEmpty = dbEmpty || !resources || resources.length === 0;
            container.innerHTML =
                '<div class="empty-state-pro" style="text-align:center;padding:4rem 2rem;">' +
                '<div style="font-size:4rem;margin-bottom:1rem;">☁️</div>' +
                '<p class="empty-state-pro__title" style="font-size:1.25rem;font-weight:700;color:#f1f5f9;margin-bottom:0.5rem;">' +
                (isDbEmpty ? 'No snapshot found' : 'No resources found') +
                '</p>' +
                '<p class="empty-state-pro__desc" style="color:#64748b;margin-bottom:1.5rem;">' +
                (isDbEmpty
                    ? 'No inventory data yet. Run a cloud scan to populate the database.'
                    : 'No resources match the current filters. Try adjusting your search or category.') +
                '</p>' +
                (isDbEmpty
                    ? '<button type="button" class="btn btn-primary" onclick="triggerCloudScan()" style="margin:0 auto;">🚀 Run Cloud Scan</button>'
                    : '') +
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
        openDetailModal(resource);
    };

    window.dismissResource = function (resourceId, reason) {
        confirmAction(
            'Are you sure you want to dismiss this resource? This action may have cost implications.',
            async function () {
                try {
                    const response = await fetch('/api/resources/' + encodeURIComponent(resourceId) + '/dismiss', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ reason }),
                    });
                    const data = await response.json();
                    if (data.status === 'success') {
                        toast(data.message || 'Resource dismissed.', 'success');
                        fetchInventory(currentPage);
                    } else {
                        toast('Error dismissing resource: ' + data.message, 'error');
                    }
                } catch (err) {
                    toast('Error dismissing resource: ' + err.message, 'error');
                }
            }
        );
    };

    // ── Trigger Cloud Scan ───────────────────────────────────────────────────
    window.triggerCloudScan = async function () {
        const btn = document.getElementById('trigger-scan-btn');
        if (btn) {
            btn.disabled = true;
            btn.innerHTML = '<span class="spinner" style="width:14px;height:14px;border-width:2px;margin-right:6px;"></span> Scanning…';
        }
        toast('Cloud scan started — this may take a moment…', 'info');
        try {
            const response = await fetch('/api/resources/scan', { method: 'POST' });
            const data = await response.json();
            if (data.status === 'success') {
                toast('Scan complete! Refreshing inventory…', 'success');
                setTimeout(() => fetchInventory(1), 800);
            } else {
                toast('Scan error: ' + (data.message || 'Unknown error'), 'error');
            }
        } catch (err) {
            toast('Scan failed: ' + err.message, 'error');
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = '<svg class="btn-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"/></svg> Scan Cloud';
            }
        }
    };

    // ── Export to CSV ────────────────────────────────────────────────────────
    window.exportInventory = function () {
        if (!resourceInventory) {
            toast('No inventory data loaded yet. Please click Refresh first.', 'error');
            return;
        }
        const all = flattenResources(resourceInventory);
        if (all.length === 0) {
            toast('No resources to export.', 'error');
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