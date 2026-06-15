// Shared UI functions for tab switching and basic interactions

function showTab(tabId) {
    const tabs = ['general', 'cloud', 'vault', 'advanced'];
    tabs.forEach(t => {
        const el = document.getElementById(t + '-tab');
        if (el) el.classList.add('hidden');
        
        const btn = document.getElementById('tab-' + t);
        if (btn) {
            btn.className = "pb-4 text-sm font-bold text-gray-500 hover:text-white transition-all";
        }
    });

    const selectedEl = document.getElementById(tabId + '-tab');
    if (selectedEl) {
        selectedEl.classList.remove('hidden');
        // If it's an animate-fade-in block, remove and re-add class to re-trigger animation
        selectedEl.classList.remove('animate-fade-in');
        void selectedEl.offsetWidth; // trigger reflow
        selectedEl.classList.add('animate-fade-in');
    }

    const selectedBtn = document.getElementById('tab-' + tabId);
    if (selectedBtn) {
        selectedBtn.className = "pb-4 text-sm font-bold border-b-2 border-blue-500 transition-all text-white";
    }

    const url = new URL(window.location);
    url.searchParams.set('tab', tabId);
    window.history.pushState({}, '', url);
    
    if (typeof initializeSidebarHighlighting === 'function') {
        initializeSidebarHighlighting();
    }
}

function switchTab(tabId) {
    const tabs = ['budget', 'alerts', 'business-metrics', 'commitment-reports', 'issues', 'commitments', 'savings-models'];
    tabs.forEach(t => {
        const el = document.getElementById('tab-content-' + t);
        if (el) el.classList.add('hidden');
        
        const btn = document.getElementById('btn-' + t);
        if (btn) {
            btn.classList.remove('bg-white/5', 'text-white', 'border-l-cyan-400');
            btn.classList.add('text-slate-300');
            // Ensure no left border
            btn.style.borderLeft = "none";
        }
    });

    const targetEl = document.getElementById('tab-content-' + tabId);
    if (targetEl) {
        targetEl.classList.remove('hidden');
        targetEl.classList.remove('animate-fade-in');
        void targetEl.offsetWidth; // trigger reflow
        targetEl.classList.add('animate-fade-in');
    }

    const targetBtn = document.getElementById('btn-' + tabId);
    if (targetBtn) {
        targetBtn.classList.add('bg-white/5', 'text-white');
        targetBtn.classList.remove('text-slate-300');
        targetBtn.style.borderLeft = "3px solid #06b6d4"; // cyan-500
    }

    const url = new URL(window.location);
    url.searchParams.set('tab', tabId);
    window.history.pushState({}, '', url);

    if (typeof initializeSidebarHighlighting === 'function') {
        initializeSidebarHighlighting();
    }
}

// Initial active tab loader for initial page load / refresh
function loadInitialTabs() {
    const params = new URLSearchParams(window.location.search);
    const tab = params.get('tab');
    if (tab) {
        if (window.location.pathname.includes('/settings')) {
            showTab(tab);
        } else if (window.location.pathname.includes('/financial')) {
            switchTab(tab);
        }
    } else {
        // default tabs
        if (window.location.pathname.includes('/settings')) {
            showTab('general');
        } else if (window.location.pathname.includes('/financial')) {
            switchTab('budget');
        }
    }
}

document.addEventListener('DOMContentLoaded', loadInitialTabs);

// HTMX navigation integration
document.body.addEventListener('htmx:afterSwap', function(evt) {
    loadInitialTabs();
});

// Backend API Integration Functions

async function postApiUpdate(action, payload = {}) {
    payload.action = action;
    try {
        const response = await fetch('/api/settings/update', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await response.json();
        if (data.status === 'success') {
            notify(data.msg || "Operation successful.", "success");
        } else {
            notify(data.msg || "Operation failed.", "error");
        }
        return data;
    } catch (e) {
        console.error(e);
        notify("Network error occurred.", "error");
    }
}

window.saveBudgetCap = () => {
    const threshold = document.getElementById('budget-cap')?.value || document.getElementById('budget-threshold')?.value;
    if(threshold) postApiUpdate('update_billing', { threshold: parseFloat(threshold) });
};

window.saveWebhooks = () => {
    const discord = document.getElementById('discord-webhook-url')?.value;
    const slack = document.getElementById('slack-webhook-url')?.value;
    postApiUpdate('update_integrations', { discord_webhook_url: discord, slack_webhook_url: slack });
};

window.triggerTestAlert = async () => {
    try {
        const response = await fetch('/api/v1/finops/test-webhook', { method: 'POST' });
        const data = await response.json();
        if (data.status === 'success') notify("Test alert sent successfully.", "success");
        else notify("Failed to send test alert.", "error");
    } catch (e) {
        notify("Error triggering test alert.", "error");
    }
};

window.openAddMetricModal = () => {
    const el = document.getElementById('add-metric-modal');
    if (el) el.classList.remove('hidden');
};

window.closeAddMetricModal = () => {
    const el = document.getElementById('add-metric-modal');
    if (el) el.classList.add('hidden');
};

window.submitNewMetric = async () => {
    const name = document.getElementById('metric-name')?.value;
    const target = document.getElementById('metric-target')?.value;
    if (!name || !target) {
        notify("Please fill all fields.", "error");
        return;
    }
    
    try {
        const response = await fetch('/api/finops/business-metrics', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: name, target_value: parseFloat(target) })
        });
        const data = await response.json();
        if (data.status === 'success') {
            closeAddMetricModal();
            notify("Business metric added.", "success");
            // Optional: refresh page to see new metric
            setTimeout(() => window.location.reload(), 1000);
        } else {
            notify(data.message || "Failed to add metric", "error");
        }
    } catch (e) {
        notify("Error adding metric.", "error");
    }
};

window.remediateIssue = async (id, action) => {
    try {
        const response = await fetch('/api/finops/anomalies/triage', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ anomaly_id: id, action: action })
        });
        const data = await response.json();
        if (data.status === 'success') {
            const el = document.getElementById(id);
            if (el) el.style.opacity = '0.5';
            notify(`Issue ${id} triaged: ${action}`, "success");
        } else {
            notify("Failed to triage issue.", "error");
        }
    } catch (e) {
        notify("Error triaging issue.", "error");
    }
};

window.purchaseSimCommitment = async () => {
    try {
        const response = await fetch('/api/v1/finops/simulate/commitment', { method: 'POST', headers: {'Content-Type': 'application/json'} });
        const data = await response.json();
        if (data.status === 'success') {
            notify(`Simulated commitment purchased. Est. Savings: $${data.savings_estimate}`, "success");
        }
    } catch (e) {
        notify("Error simulating commitment.", "error");
    }
};
window.updateSimSavings = () => console.log("Sim savings updated visually");
window.updateWhatIfModel = () => console.log("What-if model updated visually");
window.applyWhatIfPolicy = async () => {
    try {
        const response = await fetch('/api/v1/finops/simulate/policy', { method: 'POST', headers: {'Content-Type': 'application/json'} });
        const data = await response.json();
        if (data.status === 'success') {
            notify(`Governance policy applied. Cost Impact: $${data.cost_impact}`, "success");
        }
    } catch (e) {
        notify("Error applying policy.", "error");
    }
};

// --- Dashboard (index.html) ---
window.toggleConsole = () => {
    const consoleEl = document.getElementById('engine-console');
    if (consoleEl) {
        consoleEl.classList.toggle('hidden');
    }
};

window.runScan = async () => {
    const scanBtn = document.getElementById('scanBtn');
    if (scanBtn) {
        const origText = scanBtn.innerHTML;
        scanBtn.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i> Scanning...';
        scanBtn.disabled = true;
    }
    try {
        const response = await fetch('/api/scan');
        const data = await response.json();
        notify("Cloud scan completed successfully.", "success");
    } catch (e) {
        notify("Error running scan.", "error");
    } finally {
        if (scanBtn) {
            scanBtn.innerHTML = '<i class="fas fa-radar mr-2"></i> Run Cloud Scan';
            scanBtn.disabled = false;
        }
    }
};

window.filterType = (type) => {
    // In a real app, this would filter DOM elements or fetch filtered data
    notify(`Filtering dashboard by type: ${type}`, "success");
};

window.fetchActivity = async () => {
    try {
        const response = await fetch('/api/finops/anomalies');
        const data = await response.json();
        notify("Activity feed refreshed.", "success");
    } catch (e) {
        notify("Error fetching activity.", "error");
    }
};

// --- AI Copilot (build_with_ai.html) ---
window.triggerArchitectEstimation = async () => {
    const btn = document.getElementById('btn-compile');
    if (btn) {
        btn.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i> Compiling...';
    }
    
    // Mock payload
    const payload = {
        cloud_provider: document.getElementById('cloud-provider')?.value || 'aws',
        environment_tier: document.getElementById('env-tier')?.value || 'production',
        components: []
    };
    
    try {
        const response = await fetch('/api/v1/architect/estimate', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload)
        });
        const data = await response.json();
        const codeBlock = document.getElementById('architect-code');
        if (codeBlock && data.status === 'success') {
            codeBlock.innerText = JSON.stringify(data.architecture, null, 2);
            notify("Architecture compiled.", "success");
        } else if (data.status === 'error') {
            notify("Error compiling architecture.", "error");
        }
    } catch (e) {
        notify("Failed to trigger architect.", "error");
    } finally {
        if (btn) {
            btn.innerHTML = '<i class="fas fa-cube mr-2"></i> Compile Infrastructure';
        }
    }
};

// --- Integrations (integrations.html) ---
window.fetchTelemetryInsights = async () => {
    try {
        const response = await fetch('/api/v1/finops/telemetry-insights', { method: 'POST', headers: {'Content-Type': 'application/json'} });
        const data = await response.json();
        notify("Telemetry insights fetched successfully.", "success");
    } catch (e) {
        notify("Error fetching telemetry.", "error");
    }
};

window.openWebhookModal = (type) => {
    notify(`Opening ${type} webhook modal.`, "success");
};

// --- Pricing (pricing.html) & FinOps ---
window.togglePricing = (type) => {
    notify(`Switched pricing view to: ${type}`, "success");
};

window.switchProvider = (prov) => {
    notify(`Switched pricing provider to: ${prov}`, "success");
};

window.prevPage = () => {
    notify("Previous page loaded.", "success");
};

window.nextPage = () => {
    notify("Next page loaded.", "success");
};

window.toggleArchitectDrawer = () => {
    notify("Architect drawer toggled.", "success");
};

window.refreshAll = () => {
    window.location.reload();
};

window.toggleAdvancedLock = () => {
    const el = document.getElementById('advanced-content');
    if (el) {
        if (el.classList.contains('opacity-40')) {
            el.classList.remove('opacity-40', 'pointer-events-none');
            notify("Advanced settings unlocked.", "success");
        } else {
            el.classList.add('opacity-40', 'pointer-events-none');
            notify("Advanced settings locked.", "success");
        }
    }
};

window.switchDirectory = () => {
    const dir = document.getElementById('target-directory')?.value;
    if(dir) notify(`Switched context to directory: ${dir} (UI only)`, "success");
};

window.saveSubscriptions = () => {
    // In a real scenario, this would collect checked items from the #sub-checklist
    // For now, passing empty list to trigger the API backend log.
    postApiUpdate('save_subscriptions', { value: [] });
};

window.saveCompliance = () => {
    const tags = document.getElementById('mandatory-tags')?.value;
    const autoFlag = document.getElementById('auto-flag-compliance')?.checked;
    postApiUpdate('update_compliance', { tags: tags, auto_flag: autoFlag });
};

window.saveIntegrations = () => {
    const webhook = document.getElementById('webhook-url')?.value;
    postApiUpdate('update_integrations', { webhook_url: webhook });
};

window.saveBilling = () => {
    const threshold = document.getElementById('budget-threshold')?.value;
    if(threshold) postApiUpdate('update_billing', { threshold: parseFloat(threshold) });
};

window.updateCurrency = (curr) => {
    postApiUpdate('set_currency', { value: curr });
};

window.syncPriceBook = () => {
    postApiUpdate('sync_pricebook', {});
};

window.saveAISettings = () => {
    const strategy = document.getElementById('ai-personality')?.value;
    if(strategy) postApiUpdate('set_strategy', { value: strategy });
};
