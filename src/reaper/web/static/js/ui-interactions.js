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
        }
        // Note: Financial page now uses grid layout, no tab switching needed
    } else {
        // default tabs
        if (window.location.pathname.includes('/settings')) {
            showTab('general');
        }
    }
}

document.addEventListener('DOMContentLoaded', loadInitialTabs);

// HTMX navigation integration
document.addEventListener('htmx:afterSwap', function(evt) {
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

// Budget data loading
window.loadBudgetData = async () => {
    try {
        const response = await fetch('/api/finops/budget/data');
        const data = await response.json();
        if (data.status === 'success') {
            const budget = data.data;
            // Update UI elements
            const capEl = document.getElementById('display-budget-cap');
            if (capEl) capEl.textContent = `$${budget.budget_cap}`;
            
            const burnRateEl = document.getElementById('display-burn-rate');
            if (burnRateEl) burnRateEl.textContent = `$${budget.burn_rate.toFixed(2)}`;
            
            const forecastEl = document.getElementById('display-forecast');
            if (forecastEl) forecastEl.textContent = `$${budget.forecast.toFixed(2)}`;
            
            const percentText = document.getElementById('budget-percentage-text');
            if (percentText) percentText.textContent = `${budget.utilization_percent.toFixed(1)}% used`;
            
            const progressBar = document.getElementById('budget-progress-bar');
            if (progressBar) progressBar.style.width = `${Math.min(budget.utilization_percent, 100)}%`;
        }
    } catch (e) {
        console.error('Failed to load budget data:', e);
    }
};

// Load budget chart
window.loadBudgetChart = async () => {
    try {
        const response = await fetch('/api/finops/budget/chart');
        const data = await response.json();
        if (data.status === 'success' && typeof Chart !== 'undefined') {
            // Update or create budget chart
            const ctx = document.getElementById('budgetChart');
            if (ctx) {
                // Chart update logic would go here
                console.log('Budget chart data loaded:', data.chart);
            }
        }
    } catch (e) {
        console.error('Failed to load budget chart:', e);
    }
};

// Load issues data
window.loadIssuesData = async () => {
    try {
        const response = await fetch('/api/finops/issues/data');
        const data = await response.json();
        if (data.status === 'success') {
            // Update issues list
            const issuesList = document.getElementById('issues-list-container');
            if (issuesList && data.data.issues) {
                // Dynamic rendering would go here
                console.log('Issues loaded:', data.data.issues);
            }
        }
    } catch (e) {
        console.error('Failed to load issues data:', e);
    }
};

// Load commitments data
window.loadCommitmentsData = async () => {
    try {
        const response = await fetch('/api/finops/commitments/data');
        const data = await response.json();
        if (data.status === 'success') {
            const commitments = data.data.active_commitments;
            const portfolio = document.getElementById('commitments-portfolio-container');
            if (portfolio && commitments) {
                // Update portfolio UI
                console.log('Commitments loaded:', commitments);
            }
            
            // Update coverage stats
            const coverage = data.data.coverage_analysis;
            if (coverage) {
                console.log('Coverage analysis:', coverage);
            }
        }
    } catch (e) {
        console.error('Failed to load commitments data:', e);
    }
};

// Enhanced commitment simulation
window.updateSimSavings = async () => {
    const provider = document.getElementById('sim-provider')?.value;
    const type = document.getElementById('sim-type')?.value;
    const term = document.getElementById('sim-term')?.value;
    const hourly = document.getElementById('sim-hourly-spend')?.value;
    
    if (hourly) {
        try {
            const response = await fetch('/api/finops/commitment/simulate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    provider,
                    type,
                    term,
                    payment: 'no_upfront',
                    hourly_spend: hourly
                })
            });
            const data = await response.json();
            if (data.status === 'success') {
                const sim = data.simulation;
                document.getElementById('sim-est-annually').textContent = `$${sim.annual_savings}`;
                document.getElementById('sim-est-rate').textContent = `${sim.discount_rate} discount`;
            }
        } catch (e) {
            console.error('Simulation failed:', e);
        }
    }
};

// Enhanced policy simulation
window.updateWhatIfModel = async () => {
    const policyLevel = document.getElementById('input-policy-level')?.value;
    const spotLevel = document.getElementById('input-spot-level')?.value;
    
    try {
        const response = await fetch('/api/finops/policy/simulate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                aggressiveness: policyLevel,
                spot_adoption: spotLevel
            })
        });
        const data = await response.json();
        if (data.status === 'success') {
            const sim = data.simulation;
            document.getElementById('val-policy-level').textContent = `${sim.policy_aggressiveness}%`;
            document.getElementById('val-spot-level').textContent = `${sim.spot_adoption}%`;
            document.getElementById('display-model-savings').textContent = `$${sim.monthly_savings}`;
            document.getElementById('display-model-co2').textContent = `${sim.carbon_offset_kg} kg CO2e`;
            document.getElementById('display-model-trees').textContent = `${sim.trees_equivalent} Trees / mo`;
        }
    } catch (e) {
        console.error('Policy simulation failed:', e);
    }
};

// Initialize financial intelligence data on page load
window.initFinancialIntelligence = () => {
    loadBudgetData();
    loadBudgetChart();
    loadIssuesData();
    loadCommitmentsData();
};

document.addEventListener('DOMContentLoaded', () => {
    if (window.location.pathname === '/financial') {
        initFinancialIntelligence();
    }
    if (window.location.pathname === '/finops') {
        initFinopsIntelligence();
    }
    if (window.location.pathname === '/pricing') {
        loadPrices('azure', 1);
    }
});

window.saveBudgetCap = async () => {
    const threshold = document.getElementById('budget-cap')?.value || document.getElementById('budget-threshold')?.value;
    if(threshold) {
        try {
            const response = await fetch('/api/finops/budget/update', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ threshold: parseFloat(threshold) })
            });
            const data = await response.json();
            if (data.status === 'success') {
                notify(data.message, "success");
                // Refresh budget data
                loadBudgetData();
            } else {
                notify(data.message || "Failed to update budget", "error");
            }
        } catch (e) {
            notify("Error updating budget cap.", "error");
        }
    }
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
        const response = await fetch('/api/finops/issues/remediate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ issue_id: id, action: action })
        });
        const data = await response.json();
        if (data.status === 'success') {
            const el = document.getElementById(id);
            if (el) {
                el.style.opacity = '0.5';
                el.style.pointerEvents = 'none';
            }
            notify(`Issue ${id} remediated: ${action}`, "success");
            // Refresh issues list
            loadIssuesData();
        } else {
            notify("Failed to remediate issue.", "error");
        }
    } catch (e) {
        notify("Error triaging issue.", "error");
    }
};

window.purchaseSimCommitment = async () => {
    const provider = document.getElementById('sim-provider')?.value;
    const type = document.getElementById('sim-type')?.value;
    const term = document.getElementById('sim-term')?.value;
    const payment = 'no_upfront';
    const hourly_spend = document.getElementById('sim-hourly-spend')?.value;
    
    try {
        const response = await fetch('/api/finops/commitment/simulate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                provider,
                type,
                term,
                payment,
                hourly_spend: parseFloat(hourly_spend)
            })
        });
        const data = await response.json();
        
        // Purchase the commitment
        const purchaseResponse = await fetch('/api/finops/commitment/purchase', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ simulation: data.simulation })
        });
        const purchaseData = await purchaseResponse.json();
        
        if (purchaseData.status === 'success') {
            notify(`Simulated commitment purchased. Est. Savings: $${data.simulation.annual_savings}`, "success");
            // Refresh commitments data
            loadCommitmentsData();
        }
    } catch (e) {
        notify("Error simulating commitment.", "error");
    }
};

// --- Dashboard (index.html) ---
window.applyWhatIfPolicy = async () => {
    const policyLevel = document.getElementById('input-policy-level')?.value;
    const spotLevel = document.getElementById('input-spot-level')?.value;
    
    try {
        const response = await fetch('/api/finops/policy/apply', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                policy: {
                    aggressiveness: policyLevel,
                    spot_adoption: spotLevel
                }
            })
        });
        const data = await response.json();
        if (data.status === 'success') {
            const simResponse = await fetch('/api/finops/policy/simulate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    aggressiveness: policyLevel,
                    spot_adoption: spotLevel
                })
            });
            const simData = await simResponse.json();
            if (simData.status === 'success') {
                notify(`Governance policy applied. Cost Impact: -$${simData.simulation.monthly_savings}/mo`, "success");
            }
        }
    } catch (e) {
        notify("Error applying policy.", "error");
    }
};

// --- Dashboard (index.html) ---
// Note: toggleConsole is now defined in theme.js to handle the new terminal interface

const populateScanResults = (data) => {
    if (!data || data.status !== 'success') return;

    const vmCount = document.getElementById('vm-count');
    if (vmCount) vmCount.textContent = String(data.vm_count ?? 0);

    const diskCount = document.getElementById('disk-count');
    if (diskCount) {
        const orphanCount = (data.orphans || []).length;
        const snapCount = (data.snapshots || []).length;
        diskCount.textContent = String(orphanCount + snapCount);
    }

    const savingsVal = document.getElementById('savings-val');
    if (savingsVal && data.total_savings) savingsVal.textContent = data.total_savings;

    const targetList = document.getElementById('target-list');
    if (targetList) {
        const rows = [];
        
        // Azure Disks (Orphans)
        (data.orphans || []).forEach((item) => {
            rows.push(
                `<tr data-type="DISK" data-provider="azure" data-component="Disk"><td class="px-4 py-3 font-mono">${item.name}</td>` +
                `<td class="px-4 py-3">DISK (Azure)</td><td class="px-4 py-3 text-red-400">${item.savings}</td>` +
                `<td class="px-4 py-3 text-right"><button class="text-cyan-400">Reap</button></td></tr>`
            );
        });
        
        // Azure Snapshots
        (data.snapshots || []).forEach((item) => {
            rows.push(
                `<tr data-type="DISK" data-provider="azure" data-component="Snapshot"><td class="px-4 py-3 font-mono">${item.name}</td>` +
                `<td class="px-4 py-3">SNAPSHOT (Azure)</td><td class="px-4 py-3 text-red-400">${item.savings}</td>` +
                `<td class="px-4 py-3 text-right"><button class="text-cyan-400">Reap</button></td></tr>`
            );
        });
        
        // Azure VMs (Zombies)
        (data.zombies || []).forEach((item) => {
            rows.push(
                `<tr data-type="VM" data-provider="azure" data-component="VirtualMachine"><td class="px-4 py-3 font-mono">${item.name}</td>` +
                `<td class="px-4 py-3">VM (Azure)</td><td class="px-4 py-3 text-purple-400">${item.savings}</td>` +
                `<td class="px-4 py-3 text-right"><button class="text-cyan-400">Reap</button></td></tr>`
            );
        });
        
        // AWS Resources (from aws_resources if available)
        (data.aws_resources || []).forEach((item) => {
            const resourceType = item.type || 'Unknown';
            let component = 'Unknown';
            let displayType = 'RESOURCE';
            let dataType = 'VM';
            
            if (resourceType.includes('EC2')) {
                component = 'EC2Instance';
                displayType = 'EC2 INSTANCE';
                dataType = 'VM';
            } else if (resourceType.includes('EBS') || resourceType.includes('Volume')) {
                component = 'EBS';
                displayType = 'EBS VOLUME';
                dataType = 'DISK';
            } else if (resourceType.includes('Snapshot')) {
                component = 'Snapshot';
                displayType = 'SNAPSHOT';
                dataType = 'DISK';
            }
            
            rows.push(
                `<tr data-type="${dataType}" data-provider="aws" data-component="${component}"><td class="px-4 py-3 font-mono">${item.name || resourceType}</td>` +
                `<td class="px-4 py-3">${displayType} (AWS)</td><td class="px-4 py-3 text-red-400">${item.savings || '$0.00'}</td>` +
                `<td class="px-4 py-3 text-right"><button class="text-cyan-400">Reap</button></td></tr>`
            );
        });
        
        // GCP Resources (from gcp_resources if available)
        (data.gcp_resources || []).forEach((item) => {
            const resourceType = item.type || 'Unknown';
            let component = 'Unknown';
            let displayType = 'RESOURCE';
            let dataType = 'VM';
            
            if (resourceType.includes('Compute') || resourceType.includes('Instance')) {
                component = 'ComputeInstance';
                displayType = 'COMPUTE INSTANCE';
                dataType = 'VM';
            } else if (resourceType.includes('Disk') || resourceType.includes('PersistentDisk')) {
                component = 'PersistentDisk';
                displayType = 'PERSISTENT DISK';
                dataType = 'DISK';
            } else if (resourceType.includes('Snapshot')) {
                component = 'Snapshot';
                displayType = 'SNAPSHOT';
                dataType = 'DISK';
            }
            
            rows.push(
                `<tr data-type="${dataType}" data-provider="gcp" data-component="${component}"><td class="px-4 py-3 font-mono">${item.name || resourceType}</td>` +
                `<td class="px-4 py-3">${displayType} (GCP)</td><td class="px-4 py-3 text-red-400">${item.savings || '$0.00'}</td>` +
                `<td class="px-4 py-3 text-right"><button class="text-cyan-400">Reap</button></td></tr>`
            );
        });
        
        targetList.innerHTML = rows.join('') ||
            '<tr><td colspan="4" class="px-4 py-6 text-center text-gray-500">No reap targets found.</td></tr>';
    }

    const zombieList = document.getElementById('zombie-list');
    if (zombieList) {
        const zombies = [...(data.zombies || []), ...(data.idle_vms || [])];
        zombieList.innerHTML = zombies.map((z) =>
            `<tr><td class="px-4 py-3 font-mono">${z.name}</td>` +
            `<td class="px-4 py-3">CPU: ${z.usage ?? '—'}%</td>` +
            `<td class="px-4 py-3 text-emerald-400">${z.savings ?? '—'}</td>` +
            `<td class="px-4 py-3 text-right"><button class="text-rose-400">Kill</button></td></tr>`
        ).join('') ||
            '<tr><td colspan="4" class="px-4 py-6 text-center text-gray-500">No zombies detected.</td></tr>';
    }

    const efficiencyList = document.getElementById('efficiency-list');
    if (efficiencyList && data.utilization_report) {
        efficiencyList.innerHTML = data.utilization_report.map((row) =>
            `<tr><td class="py-3 px-4 font-mono">${row.name}</td>` +
            `<td class="py-3 px-4">${row.current_sku}</td>` +
            `<td class="py-3 px-4">${row.metrics}</td>` +
            `<td class="py-3 px-4 ${row.color}">${row.status}</td>` +
            `<td class="py-3 px-4">${row.recommendation}</td></tr>`
        ).join('') ||
            '<tr><td colspan="5" class="py-6 text-center text-gray-500">No utilization data.</td></tr>';
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
        if (data.status === 'success') {
            populateScanResults(data);
            notify("Cloud scan completed successfully.", "success");
        } else {
            notify(data.message || "Scan failed.", "error");
        }
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
    // Update tab styling
    document.querySelectorAll('.type-tab').forEach(tab => {
        tab.classList.remove('text-cyan-400', 'border-b-2', 'border-cyan-400');
        tab.classList.add('text-gray-500');
    });
    
    const activeTab = document.querySelector(`[data-filter="${type}"]`);
    if (activeTab) {
        activeTab.classList.remove('text-gray-500');
        activeTab.classList.add('text-cyan-400', 'border-b-2', 'border-cyan-400');
    }
    
    // Filter table rows
    const tableBody = document.getElementById('target-list');
    if (tableBody) {
        const rows = tableBody.querySelectorAll('tr');
        rows.forEach(row => {
            if (type === 'ALL') {
                row.style.display = '';
            } else {
                const rowType = row.getAttribute('data-type');
                if (rowType === type) {
                    row.style.display = '';
                } else {
                    row.style.display = 'none';
                }
            }
        });
    }
    
    notify(`Filtering dashboard by type: ${type}`, "success");
};

window.filterTable = () => {
    const searchTerm = document.getElementById('resourceSearch')?.value.toLowerCase();
    const tableBody = document.getElementById('target-list');
    if (!tableBody) return;
    
    const rows = tableBody.querySelectorAll('tr');
    rows.forEach(row => {
        const text = row.textContent.toLowerCase();
        if (text.includes(searchTerm)) {
            row.style.display = '';
        } else {
            row.style.display = 'none';
        }
    });
};

// Provider and Component Filtering Functions
window.filterByProvider = () => {
    const provider = document.getElementById('providerFilter')?.value || '';
    const tableBody = document.getElementById('target-list');
    if (!tableBody) return;

    // Show/hide component-specific dropdowns
    document.getElementById('awsComponentFilter').classList.toggle('hidden', provider !== 'aws');
    document.getElementById('azureComponentFilter').classList.toggle('hidden', provider !== 'azure');
    document.getElementById('gcpComponentFilter').classList.toggle('hidden', provider !== 'gcp');

    // Reset component filters when provider changes
    if (provider) {
        if (provider === 'aws') {
            document.getElementById('awsComponentFilter').value = '';
        } else if (provider === 'azure') {
            document.getElementById('azureComponentFilter').value = '';
        } else if (provider === 'gcp') {
            document.getElementById('gcpComponentFilter').value = '';
        }
    }

    const rows = tableBody.querySelectorAll('tr');
    rows.forEach(row => {
        const rowProvider = row.getAttribute('data-provider');
        if (!provider) {
            row.style.display = '';
        } else {
            row.style.display = rowProvider === provider ? '' : 'none';
        }
    });

    notify(provider ? `Filtering by ${provider.toUpperCase()} resources` : 'Showing all providers', 'success');
};

window.filterByAwsComponent = () => {
    const component = document.getElementById('awsComponentFilter')?.value || '';
    const tableBody = document.getElementById('target-list');
    if (!tableBody) return;

    const rows = tableBody.querySelectorAll('tr[data-provider="aws"]');
    rows.forEach(row => {
        const rowComponent = row.getAttribute('data-component');
        if (!component) {
            row.style.display = '';
        } else {
            row.style.display = rowComponent === component ? '' : 'none';
        }
    });

    notify(component ? `Filtering AWS by ${component}` : 'Showing all AWS components', 'success');
};

window.filterByAzureComponent = () => {
    const component = document.getElementById('azureComponentFilter')?.value || '';
    const tableBody = document.getElementById('target-list');
    if (!tableBody) return;

    const rows = tableBody.querySelectorAll('tr[data-provider="azure"]');
    rows.forEach(row => {
        const rowComponent = row.getAttribute('data-component');
        if (!component) {
            row.style.display = '';
        } else {
            row.style.display = rowComponent === component ? '' : 'none';
        }
    });

    notify(component ? `Filtering Azure by ${component}` : 'Showing all Azure components', 'success');
};

window.filterByGcpComponent = () => {
    const component = document.getElementById('gcpComponentFilter')?.value || '';
    const tableBody = document.getElementById('target-list');
    if (!tableBody) return;

    const rows = tableBody.querySelectorAll('tr[data-provider="gcp"]');
    rows.forEach(row => {
        const rowComponent = row.getAttribute('data-component');
        if (!component) {
            row.style.display = '';
        } else {
            row.style.display = rowComponent === component ? '' : 'none';
        }
    });

    notify(component ? `Filtering GCP by ${component}` : 'Showing all GCP components', 'success');
};

window.fetchActivity = async () => {
    try {
        await loadIssuesData();
        notify("Activity feed refreshed.", "success");
    } catch (e) {
        notify("Error fetching activity.", "error");
    }
};

// --- AI Copilot (build_with_ai.html) ---

// Store architect results globally for export
let architectResults = null;

window.triggerArchitectEstimation = async () => {
    console.log('triggerArchitectEstimation called');

    const btn = document.getElementById('btn-compile');
    if (btn) {
        btn.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i> Compiling...';
    }

    // Get form values
    const payload = {
        prompt: document.getElementById('ai-prompt')?.value || '',
        provider: document.getElementById('ai-provider')?.value || 'azure',
        region: document.getElementById('ai-region')?.value || 'eastus',
        model_provider: document.getElementById('ai-model-provider')?.value || 'openai'
    };

    console.log('Architect payload:', payload);

    if (!payload.prompt) {
        console.error('No prompt provided');
        notify("Please provide an infrastructure description.", "error");
        if (btn) {
            btn.innerHTML = '<i class="fas fa-brain mr-2"></i> Generate Architecture';
        }
        return;
    }

    try {
        console.log('Sending architect estimation request...');
        const response = await fetch('/api/v1/architect/estimate', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload)
        });
        const data = await response.json();

        console.log('Architect response:', data);

        if (data.error) {
            console.error('Architect API error:', data.error);
            notify("Error compiling architecture: " + data.error, "error");
            return;
        }

        // Store results for export
        architectResults = data;
        console.log('Stored architect results:', architectResults);

        // Update UI with results
        const loadingSpinner = document.getElementById('loading-spinner');
        const resultsOutput = document.getElementById('architecture-results-output');

        console.log('Updating UI - hiding spinner, showing results');
        if (loadingSpinner) loadingSpinner.style.display = 'none';
        if (resultsOutput) {
            resultsOutput.style.display = 'block';
            console.log('Results panel is now visible');
        }

        // Update summary
        const summaryEl = document.getElementById('lbl-arch-summary');
        if (summaryEl && data.architecture_summary) {
            summaryEl.textContent = data.architecture_summary;
        }

        // Update total cost
        const totalCostEl = document.getElementById('lbl-total-cost');
        if (totalCostEl && data.total_monthly_cost !== undefined) {
            totalCostEl.textContent = '$' + data.total_monthly_cost.toFixed(2);
        }

        // Update components table
        const componentsList = document.getElementById('list-components');
        if (componentsList && data.components) {
            console.log('Updating components table with:', data.components);
            componentsList.innerHTML = data.components.map(comp => `
                <tr class="border-b border-slate-800/40">
                    <td class="pb-3 px-2 text-slate-300">${comp.category || 'Compute'}</td>
                    <td class="pb-3 px-2 text-white font-semibold">${comp.sku || comp.name || 'Unknown'}</td>
                    <td class="pb-3 px-2 text-center text-slate-300">${comp.count || 1}</td>
                    <td class="pb-3 px-2 text-right text-cyan-400 font-mono">$${(comp.monthly_cost || 0).toFixed(2)}</td>
                </tr>
            `).join('');
        }

        // Update topology grid
        const topologyGrid = document.getElementById('topology-grid');
        if (topologyGrid && data.components) {
            topologyGrid.innerHTML = data.components.slice(0, 4).map(comp => `
                <div class="bg-slate-800/50 border border-slate-700 rounded-lg p-4">
                    <div class="text-xs text-slate-500 uppercase tracking-wider mb-1">${comp.category || 'Compute'}</div>
                    <div class="text-white font-semibold text-sm">${comp.sku || comp.name || 'Unknown'}</div>
                    <div class="text-cyan-400 text-xs mt-1">$${(comp.monthly_cost || 0).toFixed(2)}/mo</div>
                </div>
            `).join('');
        }

        // Show security warning if present
        const warningWrapper = document.getElementById('security-warning-wrapper');
        const warningText = document.getElementById('lbl-security-warning');
        if (warningWrapper && warningText && data.security_warning) {
            warningText.textContent = data.security_warning;
            warningWrapper.style.display = 'block';
        }

        notify("Architecture compiled successfully.", "success");

    } catch (e) {
        console.error('Architect estimation error:', e);
        notify("Failed to trigger architect: " + e.message, "error");
    } finally {
        if (btn) {
            btn.innerHTML = '<i class="fas fa-brain mr-2"></i> Generate Architecture';
        }
    }
};

window.exportArchitectBOM = async () => {
    console.log('exportArchitectBOM called');
    console.log('architectResults:', architectResults);
    console.log('architectResults.components:', architectResults?.components);

    if (!architectResults || !architectResults.components || architectResults.components.length === 0) {
        console.error('No architect results available');
        notify("No architect results to export. Please generate an architecture first.", "error");
        return;
    }

    try {
        const btn = document.getElementById('btn-export-bom');
        if (btn) {
            btn.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i> Exporting...';
            btn.disabled = true;
        }

        console.log('Preparing BOM payload with components:', architectResults.components);

        // Prepare BOM payload
        const bomPayload = {
            resources: architectResults.components.map(comp => ({
                sku: comp.sku || comp.name || 'Unknown',
                service: comp.category || 'Compute',
                count: comp.count || 1,
                hourly: comp.hourly_cost || (comp.monthly_cost / 730) || 0
            })),
            totalHourly: architectResults.total_hourly_cost || 0,
            totalMonthly: architectResults.total_monthly_cost || 0
        };

        console.log('BOM payload:', bomPayload);

        const response = await fetch('/api/export/bom', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(bomPayload)
        });

        console.log('BOM export response status:', response.status);

        if (response.ok) {
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `Cloud_Reaper_Architect_BOM_${new Date().toISOString().slice(0,10)}.pdf`;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);
            notify("BOM PDF exported successfully.", "success");
        } else {
            const errorData = await response.json();
            console.error('BOM export failed:', errorData);
            notify("Failed to export BOM: " + (errorData.message || "Unknown error"), "error");
        }
    } catch (e) {
        console.error('BOM export error:', e);
        notify("Error exporting BOM: " + e.message, "error");
    } finally {
        const btn = document.getElementById('btn-export-bom');
        if (btn) {
            btn.innerHTML = '<i class="fas fa-file-pdf"></i> Export BOM PDF';
            btn.disabled = false;
        }
    }
};

// Add a backup click handler for the button
function attachExportButtonListener() {
    const exportBtn = document.getElementById('btn-export-bom');
    if (exportBtn) {
        // Remove existing listener to avoid duplicates
        exportBtn.removeEventListener('click', handleExportClick);
        exportBtn.addEventListener('click', handleExportClick);
        console.log('Export button listener attached');
    } else {
        console.log('Export button not found');
    }
}

function handleExportClick(e) {
    e.preventDefault();
    e.stopPropagation();
    console.log('Button clicked via event listener');
    if (typeof window.exportArchitectBOM === 'function') {
        window.exportArchitectBOM();
    } else {
        console.error('exportArchitectBOM function not found');
        notify('Export function not available. Please refresh the page.', 'error');
    }
}

document.addEventListener('DOMContentLoaded', attachExportButtonListener);
document.addEventListener('htmx:afterSwap', attachExportButtonListener);

// Add event listeners for pricing page cart buttons
function attachPricingCartListeners() {
    const cartButton = document.querySelector('button[onclick*="openCartModal"]');
    if (cartButton) {
        cartButton.removeEventListener('click', handleCartButtonClick);
        cartButton.addEventListener('click', handleCartButtonClick);
        console.log('Pricing cart button listener attached');
    }

    const clearCartButton = document.querySelector('button[onclick*="clearCart"]');
    if (clearCartButton) {
        clearCartButton.removeEventListener('click', handleClearCartClick);
        clearCartButton.addEventListener('click', handleClearCartClick);
        console.log('Clear cart button listener attached');
    }

    const exportCartButton = document.querySelector('button[onclick*="exportCartBOM"]');
    if (exportCartButton) {
        exportCartButton.removeEventListener('click', handleExportCartClick);
        exportCartButton.addEventListener('click', handleExportCartClick);
        console.log('Export cart button listener attached');
    }

    const closeCartButton = document.querySelector('button[onclick*="closeCartModal"]');
    if (closeCartButton) {
        closeCartButton.removeEventListener('click', handleCloseCartClick);
        closeCartButton.addEventListener('click', handleCloseCartClick);
        console.log('Close cart button listener attached');
    }
}

function handleCartButtonClick(e) {
    e.preventDefault();
    console.log('Cart button clicked via event listener');
    if (typeof openCartModal === 'function') {
        openCartModal();
    } else {
        console.error('openCartModal function not found');
        notify('Cart function not available. Please refresh the page.', 'error');
    }
}

function handleClearCartClick(e) {
    e.preventDefault();
    console.log('Clear cart button clicked via event listener');
    if (typeof clearCart === 'function') {
        clearCart();
    } else {
        console.error('clearCart function not found');
        notify('Clear cart function not available. Please refresh the page.', 'error');
    }
}

function handleExportCartClick(e) {
    e.preventDefault();
    console.log('Export cart button clicked via event listener');
    if (typeof exportCartBOM === 'function') {
        exportCartBOM();
    } else {
        console.error('exportCartBOM function not found');
        notify('Export cart function not available. Please refresh the page.', 'error');
    }
}

function handleCloseCartClick(e) {
    e.preventDefault();
    console.log('Close cart button clicked via event listener');
    if (typeof closeCartModal === 'function') {
        closeCartModal();
    } else {
        console.error('closeCartModal function not found');
        notify('Close cart function not available. Please refresh the page.', 'error');
    }
}

document.addEventListener('DOMContentLoaded', attachPricingCartListeners);
document.addEventListener('htmx:afterSwap', attachPricingCartListeners);

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

// --- Pricing (pricing.html) ---

let priceCatalogState = {
    currentProvider: 'azure',
    pricingType: 'hourly',
    prices: [],
    currentPage: 1,
    itemsPerPage: 50,
    totalItems: 0,
    totalPages: 1,
    sortBy: 'sku-asc',
    searchTerm: '',
    serviceFilter: '',
    regionFilter: '',
    isLoading: false,
    searchDebounceTimer: null,
    pollTimer: null,
    hasLoadedOnce: false,
};

// Cart state management
let cartState = {
    items: [],
    isOpen: false
};

function updateCartCount() {
    const cartCountEl = document.getElementById('cart-count');
    if (cartCountEl) {
        if (cartState.items.length > 0) {
            cartCountEl.textContent = cartState.items.length;
            cartCountEl.classList.remove('hidden');
        } else {
            cartCountEl.classList.add('hidden');
        }
    }
}

function addToCart(priceItem) {
    // Check if item already exists in cart
    const existingIndex = cartState.items.findIndex(item =>
        item.sku === priceItem.sku && item.region === priceItem.region
    );

    if (existingIndex >= 0) {
        // Update quantity if exists
        cartState.items[existingIndex].count += 1;
    } else {
        // Add new item
        cartState.items.push({
            sku: priceItem.sku || priceItem.name || 'Unknown SKU',
            service: priceItem.service || 'Compute',
            region: priceItem.region || 'Unknown',
            hourly: priceCatalogState.pricingType === 'hourly'
                ? (priceItem.hourly_price || priceItem.price || priceItem.rate || 0)
                : (priceItem.monthly_price || (priceItem.price || priceItem.rate || 0) / 730),
            count: 1,
            description: priceItem.description || ''
        });
    }

    updateCartCount();
    notify(`Added ${priceItem.sku || priceItem.name} to cart`, 'success');
}

function removeFromCart(index) {
    cartState.items.splice(index, 1);
    updateCartCount();
    renderCartItems();
}

function clearCart() {
    cartState.items = [];
    updateCartCount();
    renderCartItems();
    notify('Cart cleared', 'success');
}

function openCartModal() {
    console.log('openCartModal called');
    const modal = document.getElementById('cart-modal');
    if (modal) {
        modal.classList.remove('hidden');
        cartState.isOpen = true;
        renderCartItems();
        console.log('Cart modal opened');
    } else {
        console.error('Cart modal element not found');
    }
}

function closeCartModal() {
    console.log('closeCartModal called');
    const modal = document.getElementById('cart-modal');
    if (modal) {
        modal.classList.add('hidden');
        cartState.isOpen = false;
        console.log('Cart modal closed');
    } else {
        console.error('Cart modal element not found');
    }
}

function renderCartItems() {
    const cartItemsContainer = document.getElementById('cart-items');
    if (!cartItemsContainer) return;

    if (cartState.items.length === 0) {
        cartItemsContainer.innerHTML = '<p class="text-[var(--text-muted)] text-center py-8">Your cart is empty</p>';
        document.getElementById('cart-total-hourly').textContent = '$0.0000';
        document.getElementById('cart-total-monthly').textContent = '$0.00';
        return;
    }

    let totalHourly = 0;
    cartItemsContainer.innerHTML = cartState.items.map((item, index) => {
        const itemHourly = item.hourly * item.count;
        totalHourly += itemHourly;
        return `
            <div class="flex items-center justify-between p-3 bg-[var(--bg-tertiary)] border border-[var(--border-default)] rounded-lg">
                <div class="flex-1 min-w-0">
                    <div class="font-semibold text-[var(--text-primary)] text-sm truncate">${item.sku}</div>
                    <div class="text-xs text-[var(--text-secondary)]">${item.service} • ${item.region}</div>
                    <div class="text-xs text-[var(--accent-primary)] font-mono">$${item.hourly.toFixed(4)}/hr × ${item.count}</div>
                </div>
                <div class="flex items-center gap-3">
                    <div class="text-right">
                        <div class="font-mono font-bold text-[var(--text-primary)]">$${itemHourly.toFixed(4)}/hr</div>
                        <div class="text-xs text-[var(--text-secondary)]">$${(itemHourly * 730).toFixed(2)}/mo</div>
                    </div>
                    <button onclick="removeFromCart(${index})" class="text-red-500 hover:text-red-400 transition p-2">
                        <i class="fas fa-trash-alt"></i>
                    </button>
                </div>
            </div>
        `;
    }).join('');

    document.getElementById('cart-total-hourly').textContent = `$${totalHourly.toFixed(4)}`;
    document.getElementById('cart-total-monthly').textContent = `$${(totalHourly * 730).toFixed(2)}`;
}

async function exportCartBOM() {
    console.log('exportCartBOM called');
    console.log('Cart state items:', cartState.items);

    if (cartState.items.length === 0) {
        notify('Your cart is empty. Add items to export.', 'error');
        return;
    }

    try {
        const totalHourly = cartState.items.reduce((sum, item) => sum + (item.hourly * item.count), 0);
        const totalMonthly = totalHourly * 730;

        const bomPayload = {
            resources: cartState.items.map(item => ({
                sku: item.sku,
                service: item.service,
                count: item.count,
                hourly: item.hourly
            })),
            totalHourly: totalHourly,
            totalMonthly: totalMonthly
        };

        console.log('Cart BOM payload:', bomPayload);

        const response = await fetch('/api/export/bom', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(bomPayload)
        });

        console.log('Cart BOM export response status:', response.status);

        if (response.ok) {
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `Cloud_Reaper_BOM_${new Date().toISOString().slice(0,10)}.pdf`;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);
            notify('BOM PDF exported successfully', 'success');
            closeCartModal();
        } else {
            const errorData = await response.json();
            console.error('Cart BOM export failed:', errorData);
            notify('Failed to export BOM: ' + (errorData.message || 'Unknown error'), 'error');
        }
    } catch (e) {
        console.error('Cart BOM export error:', e);
        notify('Error exporting BOM: ' + e.message, 'error');
    }
}

function updateCatalogStatus(data) {
    const statusEl = document.getElementById('price-catalog-status');
    if (!statusEl) return;

    if (data?.status === 'warming' || data?.catalog_status === 'warming') {
        statusEl.textContent = `Syncing live on-demand rates from ${data.source || 'cloud API'}...`;
        return;
    }

    const total = data?.sku_count || data?.total || 0;
    const source = data?.source || 'live API';
    statusEl.textContent = `${total.toLocaleString()} on-demand SKUs • ${source}`;
}

function showPriceLoading(full = false) {
    if (!full && priceCatalogState.hasLoadedOnce) return;
    const tbody = document.getElementById('priceTableBody');
    if (!tbody) return;
    tbody.innerHTML = `
        <tr>
            <td colspan="4" class="p-12 text-center">
                <div class="flex flex-col items-center gap-4">
                    <div class="w-8 h-8 border-4 border-[var(--accent-primary)] border-t-transparent rounded-full animate-spin"></div>
                    <p class="text-[var(--text-muted)] font-bold animate-pulse">Loading live prices...</p>
                </div>
            </td>
        </tr>
    `;
    if (full) {
        document.getElementById('pagination-controls')?.classList.add('hidden');
    }
}

async function loadPriceFilters(provider) {
    try {
        const response = await fetch(`/api/prices/filters?provider=${provider}`);
        const data = await response.json();
        if (data.status !== 'success') return;

        const serviceSelect = document.getElementById('priceServiceFilter');
        const regionSelect = document.getElementById('priceRegionFilter');
        if (!serviceSelect || !regionSelect) return;

        serviceSelect.innerHTML = '<option value="">All Services</option>' +
            (data.services || []).map(s => `<option value="${s}">${s}</option>`).join('');
        regionSelect.innerHTML = '<option value="">All Regions</option>' +
            (data.regions || []).map(r => `<option value="${r}">${r}</option>`).join('');
    } catch (e) {
        console.error('Error loading price filters:', e);
    }
}

function scheduleCatalogPoll(provider) {
    clearTimeout(priceCatalogState.pollTimer);
    priceCatalogState.pollTimer = setTimeout(() => loadPrices(provider, priceCatalogState.currentPage, true), 2500);
}

async function loadPrices(provider = 'azure', page = 1, isPoll = false) {
    if (priceCatalogState.isLoading && !isPoll) return;
    priceCatalogState.isLoading = true;
    showPriceLoading(!priceCatalogState.hasLoadedOnce);

    const params = new URLSearchParams({
        provider,
        page: String(page),
        per_page: String(priceCatalogState.itemsPerPage),
        sort: priceCatalogState.sortBy,
    });
    if (priceCatalogState.searchTerm) params.set('search', priceCatalogState.searchTerm);
    if (priceCatalogState.serviceFilter) params.set('service', priceCatalogState.serviceFilter);
    if (priceCatalogState.regionFilter) params.set('region', priceCatalogState.regionFilter);

    try {
        const response = await fetch(`/api/prices?${params.toString()}`);
        const data = await response.json();
        updateCatalogStatus(data);

        if (data.status === 'warming') {
            renderWarming();
            scheduleCatalogPoll(provider);
            return;
        }

        clearTimeout(priceCatalogState.pollTimer);

        if (data.status === 'success' && Array.isArray(data.prices)) {
            priceCatalogState.prices = data.prices;
            priceCatalogState.currentPage = data.page || page;
            priceCatalogState.totalItems = data.total || data.prices.length;
            priceCatalogState.totalPages = data.total_pages || 1;
            priceCatalogState.hasLoadedOnce = true;
            renderPrices();
            if (page === 1 && !priceCatalogState.serviceFilter && !priceCatalogState.regionFilter) {
                loadPriceFilters(provider);
            }
        } else {
            renderError(data.message || 'Failed to load live price catalog');
        }
    } catch (e) {
        console.error('Error loading prices:', e);
        renderError('Network error while loading live prices');
    } finally {
        priceCatalogState.isLoading = false;
    }
}

// Render prices to table
function renderPrices() {
    const tbody = document.getElementById('priceTableBody');
    if (!tbody) return;

    const { prices, currentPage, itemsPerPage, pricingType, totalItems } = priceCatalogState;

    if (prices.length === 0) {
        renderNoPrices();
        return;
    }

    const startIndex = (currentPage - 1) * itemsPerPage;

    tbody.innerHTML = prices.map(price => {
        const priceValue = pricingType === 'hourly'
            ? (price.hourly_price || price.price || price.rate || 0)
            : (price.monthly_price || (price.price || price.rate || 0) * 730);

        return `
            <tr class="border-b border-white/5 hover:bg-white/5 transition">
                <td class="p-4">
                    <div class="text-white font-semibold text-sm">${price.sku || price.name || 'Unknown SKU'}</div>
                    <div class="text-slate-500 text-xs mt-0.5">${price.description || ''}</div>
                </td>
                <td class="p-4 text-slate-300 text-sm">${price.service || 'Compute'}</td>
                <td class="p-4">
                    <span class="px-2 py-1 bg-cyan-500/10 text-cyan-400 text-xs rounded border border-cyan-500/20">${price.region || 'Unknown'}</span>
                </td>
                <td class="p-4">
                    <span class="text-white font-mono text-sm metric-value">$${Number(priceValue).toFixed(4)}</span>
                    <span class="text-slate-500 text-xs ml-1">/ ${pricingType}</span>
                </td>
                <td class="p-4">
                    <button onclick='addToCart(${JSON.stringify(price).replace(/'/g, "\\'")})' class="px-3 py-2 bg-cyan-500/10 hover:bg-cyan-500/20 text-cyan-400 border border-cyan-500/30 rounded-lg text-xs font-bold uppercase tracking-wider transition">
                        <i class="fas fa-plus mr-1"></i> Add
                    </button>
                </td>
            </tr>
        `;
    }).join('');

    updatePagination(totalItems, startIndex, startIndex + prices.length);
}

// Render no prices state
function renderNoPrices() {
    const tbody = document.getElementById('priceTableBody');
    if (tbody) {
        tbody.innerHTML = `
            <tr>
                <td colspan="5" class="p-12 text-center">
                    <div class="flex flex-col items-center gap-4">
                        <i class="fas fa-search text-4xl text-slate-600"></i>
                        <p class="text-slate-500 font-bold">No matching SKUs found</p>
                        <p class="text-slate-600 text-sm">Adjust your search or filters</p>
                    </div>
                </td>
            </tr>
        `;
    }
    document.getElementById('pagination-controls')?.classList.add('hidden');
}

function renderWarming() {
    const tbody = document.getElementById('priceTableBody');
    if (tbody) {
        tbody.innerHTML = `
            <tr>
                <td colspan="5" class="p-12 text-center">
                    <div class="flex flex-col items-center gap-4">
                        <div class="w-8 h-8 border-4 border-[var(--accent-primary)] border-t-transparent rounded-full animate-spin"></div>
                        <p class="text-[var(--text-muted)] font-bold">Syncing live catalog from cloud API...</p>
                        <p class="text-slate-600 text-sm">First sync may take up to a minute for Azure</p>
                    </div>
                </td>
            </tr>
        `;
    }
    document.getElementById('pagination-controls')?.classList.add('hidden');
}

function renderError(message = 'Failed to load live price catalog') {
    const tbody = document.getElementById('priceTableBody');
    if (tbody) {
        tbody.innerHTML = `
            <tr>
                <td colspan="5" class="p-12 text-center">
                    <div class="flex flex-col items-center gap-4">
                        <i class="fas fa-exclamation-triangle text-4xl text-rose-400"></i>
                        <p class="text-rose-400 font-bold">${message}</p>
                        <button onclick="loadPrices('${priceCatalogState.currentProvider}', 1, true)" class="px-4 py-2 bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 text-xs font-semibold rounded-lg border border-rose-500/20 transition">
                            Retry
                        </button>
                    </div>
                </td>
            </tr>
        `;
    }
    document.getElementById('pagination-controls')?.classList.add('hidden');
}

// Update pagination controls
function updatePagination(totalItems, start, end) {
    const paginationControls = document.getElementById('pagination-controls');
    if (!paginationControls) return;

    paginationControls.classList.remove('hidden');
    document.getElementById('page-start').textContent = totalItems === 0 ? 0 : start + 1;
    document.getElementById('page-end').textContent = Math.min(end, totalItems);
    document.getElementById('total-items').textContent = totalItems;

    document.getElementById('prev-btn').disabled = priceCatalogState.currentPage === 1;
    document.getElementById('next-btn').disabled = priceCatalogState.currentPage >= priceCatalogState.totalPages;
}

// Switch provider
window.switchProvider = (prov) => {
    priceCatalogState.currentProvider = prov;
    priceCatalogState.currentPage = 1;
    priceCatalogState.searchTerm = '';
    priceCatalogState.serviceFilter = '';
    priceCatalogState.regionFilter = '';
    priceCatalogState.hasLoadedOnce = false;
    clearTimeout(priceCatalogState.pollTimer);

    const searchInput = document.getElementById('priceSearch');
    if (searchInput) searchInput.value = '';
    const serviceSelect = document.getElementById('priceServiceFilter');
    if (serviceSelect) serviceSelect.value = '';
    const regionSelect = document.getElementById('priceRegionFilter');
    if (regionSelect) regionSelect.value = '';

    document.getElementById('active-provider-label').textContent = prov.charAt(0).toUpperCase() + prov.slice(1);

    document.querySelectorAll('.prov-btn').forEach(btn => {
        btn.classList.remove('bg-[var(--accent-primary)]', 'text-[var(--bg-primary)]', 'shadow-lg');
        btn.classList.add('hover:bg-[var(--bg-elevated)]', 'text-[var(--text-secondary)]');
    });
    const activeBtn = document.getElementById(`prov-${prov}`);
    if (activeBtn) {
        activeBtn.classList.add('bg-[var(--accent-primary)]', 'text-[var(--bg-primary)]', 'shadow-lg');
        activeBtn.classList.remove('hover:bg-[var(--bg-elevated)]', 'text-[var(--text-secondary)]');
    }

    loadPrices(prov, 1);
};

// Toggle pricing type (hourly/monthly)
window.togglePricing = (type) => {
    priceCatalogState.pricingType = type;
    
    // Update button styles
    document.getElementById('toggle-hourly').classList.remove('bg-[var(--accent-primary)]', 'text-[var(--bg-primary)]');
    document.getElementById('toggle-hourly').classList.add('hover:bg-[var(--bg-elevated)]', 'text-[var(--text-secondary)]');
    document.getElementById('toggle-monthly').classList.remove('bg-[var(--accent-primary)]', 'text-[var(--bg-primary)]');
    document.getElementById('toggle-monthly').classList.add('hover:bg-[var(--bg-elevated)]', 'text-[var(--text-secondary)]');

    const activeBtn = document.getElementById(`toggle-${type}`);
    activeBtn.classList.add('bg-[var(--accent-primary)]', 'text-[var(--bg-primary)]');
    activeBtn.classList.remove('hover:bg-[var(--bg-elevated)]', 'text-[var(--text-secondary)]');
    
    // Re-render with new pricing type
    renderPrices();
};

// Search prices (server-side, debounced)
window.filterPrices = () => {
    priceCatalogState.serviceFilter = document.getElementById('priceServiceFilter')?.value || '';
    priceCatalogState.regionFilter = document.getElementById('priceRegionFilter')?.value || '';
    priceCatalogState.currentPage = 1;
    loadPrices(priceCatalogState.currentProvider, 1);
};

window.searchPrices = () => {
    const searchTerm = document.getElementById('priceSearch')?.value.trim() || '';
    priceCatalogState.searchTerm = searchTerm;
    priceCatalogState.currentPage = 1;

    clearTimeout(priceCatalogState.searchDebounceTimer);
    priceCatalogState.searchDebounceTimer = setTimeout(() => {
        loadPrices(priceCatalogState.currentProvider, 1);
    }, 300);
};

// Sort prices (server-side)
window.sortPrices = () => {
    const sortValue = document.getElementById('priceSort')?.value || 'sku-asc';
    priceCatalogState.sortBy = sortValue === 'none' ? 'sku-asc' : sortValue;
    priceCatalogState.currentPage = 1;
    loadPrices(priceCatalogState.currentProvider, 1);
};

// Pagination
window.prevPage = () => {
    if (priceCatalogState.currentPage > 1) {
        loadPrices(priceCatalogState.currentProvider, priceCatalogState.currentPage - 1);
    }
};

window.nextPage = () => {
    if (priceCatalogState.currentPage < priceCatalogState.totalPages) {
        loadPrices(priceCatalogState.currentProvider, priceCatalogState.currentPage + 1);
    }
};

window.refreshAll = async () => {
    const icon = document.getElementById('refresh-icon');
    if (icon) icon.classList.add('animate-spin');
    try {
        if (window.location.pathname === '/finops') {
            await initFinopsIntelligence();
            notify('FinOps intelligence synced.', 'success');
        } else {
            window.location.reload();
        }
    } finally {
        if (icon) icon.classList.remove('animate-spin');
    }
};

const fetchJson = async (url) => {
    const response = await fetch(url);
    return response.json();
};

window.initFinopsIntelligence = async () => {
    const loaders = [
        fetchJson('/api/finops/tag-health').then((data) => {
            if (data.status !== 'success') return;
            const rate = data.compliance_rate ?? 0;
            const indicator = document.getElementById('tag-health-indicator');
            if (indicator) {
                indicator.textContent = `${Math.round(rate)}%`;
                indicator.className = `w-12 h-12 rounded-2xl flex items-center justify-center font-bold text-lg metric-value ${
                    rate >= 80 ? 'bg-emerald-500/20 text-emerald-400' : 'bg-rose-500/20 text-rose-400'
                }`;
            }
            const pct = document.getElementById('tag-integrity-pct');
            if (pct) pct.textContent = `${rate}%`;
            const bar = document.getElementById('tag-health-bar');
            if (bar) bar.style.width = `${Math.min(rate, 100)}%`;
            const list = document.getElementById('tag-missing-list');
            if (list) {
                const items = data.missing_tags_summary || [];
                list.innerHTML = items.slice(0, 5).map((t) =>
                    `<div class="flex justify-between text-sm"><span class="text-slate-300">${t.resource}</span>` +
                    `<span class="text-rose-400 text-xs">${t.missing}</span></div>`
                ).join('') || '<p class="text-xs text-slate-500">All resources tagged.</p>';
            }
        }),
        fetchJson('/api/finops/anomalies').then((data) => {
            if (data.status !== 'success') return;
            const count = document.getElementById('anomaly-alert-count');
            if (count) count.textContent = `${data.spike_count ?? 0} ALERTS`;
            const list = document.getElementById('anomaly-list');
            if (list) {
                list.innerHTML = (data.services || []).slice(0, 4).map((s) =>
                    `<div class="flex justify-between items-center ${s.is_anomaly ? 'text-rose-400' : 'text-slate-400'}">` +
                    `<span>${s.service || s.name || 'Service'}</span>` +
                    `<span class="text-xs font-mono">$${(s.cost ?? 0).toFixed?.(2) ?? s.cost ?? 0}</span></div>`
                ).join('') || '<p class="text-xs text-slate-500">No anomalies detected.</p>';
            }
        }),
        fetchJson('/api/finops/utilization').then((data) => {
            if (data.status !== 'success') return;
            const critical = (data.report || []).filter((r) => r.waste_coefficient > 0.7);
            const badge = document.getElementById('zombie-count-badge');
            if (badge) badge.textContent = String(critical.length);
            const list = document.getElementById('zombie-radar-list');
            if (list) {
                list.innerHTML = critical.slice(0, 5).map((r) =>
                    `<div class="flex justify-between text-sm"><span class="text-slate-300">${r.name}</span>` +
                    `<span class="text-rose-400 text-xs">${Math.round(r.waste_coefficient * 100)}% waste</span></div>`
                ).join('') || '<p class="text-xs text-slate-500">No high-waste resources.</p>';
            }
            const pending = document.getElementById('pending-reap-list');
            if (pending) {
                pending.innerHTML = critical.slice(0, 6).map((r) =>
                    `<tr><td class="py-3 font-mono">${r.name}</td>` +
                    `<td class="py-3">${Math.round(r.waste_coefficient * 100)}</td>` +
                    `<td class="py-3">$${(r.monthly_cost ?? 0).toFixed(2)}</td>` +
                    `<td class="py-3 text-right"><button class="text-cyan-400 text-xs">Approve</button></td></tr>`
                ).join('') ||
                    '<tr><td colspan="4" class="py-6 text-center text-slate-500">No pending approvals.</td></tr>';
            }
        }),
        fetchJson('/api/finops/unit-economics').then((data) => {
            if (data.status !== 'success') return;
            const list = document.getElementById('unit-economics-list');
            if (list) {
                list.innerHTML = (data.metrics || []).map((m) =>
                    `<div class="flex justify-between items-center"><div><p class="text-white font-semibold">${m.metric}</p>` +
                    `<p class="text-xs text-slate-500">${m.count} ${m.unit}</p></div>` +
                    `<div class="text-right"><p class="text-cyan-400 font-mono">$${m.cost_per_unit}</p>` +
                    `<p class="text-xs text-slate-500">/ unit</p></div></div>`
                ).join('') || '<p class="text-xs text-slate-500">No business metrics recorded.</p>';
            }
        }),
        fetchJson('/api/finops/burn-rate-forecast').then((data) => {
            if (data.status !== 'success' || !data.forecast) return;
            const f = data.forecast;
            const total = document.getElementById('projected-total');
            if (total) total.textContent = `$${(f.projected_total ?? 0).toFixed(2)}`;
            const trend = document.getElementById('burn-trend');
            if (trend) {
                const slope = f.slope ?? 0;
                trend.textContent = `${slope >= 0 ? '+' : ''}${slope.toFixed(2)}%`;
                trend.className = `text-xs font-bold ${slope >= 0 ? 'text-rose-400' : 'text-emerald-400'}`;
            }
            const chart = document.getElementById('burn-chart');
            if (chart && f.daily_history?.length) {
                const max = Math.max(...f.daily_history, 1);
                chart.innerHTML = f.daily_history.slice(-14).map((v) =>
                    `<div class="flex-1 bg-cyan-500/60 rounded-t" style="height:${Math.max(8, (v / max) * 100)}%"></div>`
                ).join('');
            }
        }),
        fetchJson('/api/finops/virtual-tags').then((data) => {
            if (data.status !== 'success') return;
            const list = document.getElementById('virtual-tags-list');
            if (list) {
                list.innerHTML = (data.virtual_tags || []).slice(0, 5).map((t) =>
                    `<div class="p-3 bg-black/20 rounded-xl border border-white/5">` +
                    `<p class="text-sm text-white font-mono">${t.resource_name}</p>` +
                    `<p class="text-[10px] text-cyan-400 mt-1">${Object.entries(t.virtual_tags || {}).map(([k, v]) => `${k}: ${v}`).join(' · ')}</p></div>`
                ).join('') || '<p class="text-xs text-slate-500">No virtual tags mapped.</p>';
            }
        }),
        fetchJson('/api/finops/greenops').then((data) => {
            if (data.status !== 'success') return;
            const list = document.getElementById('greenops-list');
            if (list) {
                list.innerHTML = (data.recommendations || []).slice(0, 4).map((r) =>
                    `<div class="flex justify-between text-sm"><span class="text-slate-300">${r.name}</span>` +
                    `<span class="text-emerald-400 text-xs">${r.current_region} → ${r.target_region} (${r.savings_pct}%)</span></div>`
                ).join('') || '<p class="text-xs text-slate-500">No carbon migrations suggested.</p>';
            }
        }),
        fetchJson('/api/finops/ri-advisor').then((data) => {
            if (data.status !== 'success') return;
            const total = document.getElementById('ri-savings-total');
            if (total) total.textContent = `+$${(data.total_annual_savings ?? 0).toFixed(2)}/yr`;
            const list = document.getElementById('ri-list');
            if (list) {
                list.innerHTML = (data.candidates || []).slice(0, 5).map((c) =>
                    `<tr><td class="py-3">${c.name || c.sku || 'Candidate'}</td>` +
                    `<td class="py-3">$${(c.on_demand_monthly ?? c.on_demand ?? 0).toFixed?.(2) ?? c.on_demand ?? 0}</td>` +
                    `<td class="py-3">$${(c.ri_monthly ?? 0).toFixed?.(2) ?? c.ri_monthly ?? 0}</td>` +
                    `<td class="py-3 text-right text-emerald-400">$${(c.annual_savings ?? 0).toFixed?.(2) ?? c.annual_savings ?? 0}</td></tr>`
                ).join('') ||
                    '<tr><td colspan="4" class="py-6 text-center text-slate-500">No RI candidates.</td></tr>';
            }
        }),
        fetchJson('/api/finops/cold-storage').then((data) => {
            if (data.status !== 'success') return;
            const total = document.getElementById('storage-savings-total');
            if (total) total.textContent = `$${(data.total_monthly_savings ?? 0).toFixed(2)}/mo`;
            const list = document.getElementById('storage-list');
            if (list) {
                list.innerHTML = (data.buckets || []).slice(0, 4).map((b) =>
                    `<div class="flex justify-between text-sm"><span class="text-slate-300">${b.name}</span>` +
                    `<span class="text-emerald-400">$${(b.monthly_savings ?? 0).toFixed(2)}/mo</span></div>`
                ).join('') || '<p class="text-xs text-slate-500">No cold storage candidates.</p>';
            }
        }),
        fetchJson('/api/finops/modernization').then((data) => {
            if (data.status !== 'success') return;
            const list = document.getElementById('modernization-list');
            if (list) {
                list.innerHTML = (data.suggestions || []).slice(0, 3).map((s) =>
                    `<div class="p-4 bg-black/20 rounded-xl border border-white/5"><p class="text-white font-semibold">${s.title || s.resource || 'Upgrade'}</p>` +
                    `<p class="text-xs text-slate-400 mt-2">${s.description || s.recommendation || ''}</p>` +
                    `<p class="text-emerald-400 text-sm mt-2">$${(s.annual_savings ?? 0).toFixed(2)}/yr</p></div>`
                ).join('') || '<p class="text-xs text-slate-500 col-span-3">No modernization tips.</p>';
            }
        }),
        fetch('/api/rightsizing').then((r) => r.json()).then((data) => {
            if (data.status !== 'success') return;
            const total = document.getElementById('rightsizing-total-saving');
            if (total) total.textContent = `$${(data.total_saving ?? 0).toFixed(2)}`;
            const list = document.getElementById('rightsizing-list');
            if (list) {
                list.innerHTML = (data.recommendations || []).slice(0, 4).map((r) =>
                    `<div class="p-4 bg-black/30 rounded-xl border border-cyan-500/10"><p class="font-mono text-white">${r.name || r.vm_name}</p>` +
                    `<p class="text-xs text-slate-400 mt-1">${r.current_sku || r.current_size} → ${r.recommended_sku || r.recommended_size}</p>` +
                    `<p class="text-emerald-400 text-sm mt-2">$${(r.monthly_saving ?? 0).toFixed(2)}/mo</p></div>`
                ).join('') || '<p class="text-xs text-slate-500 col-span-2">No rightsizing recommendations.</p>';
            }
        }),
        fetchJson('/api/finops/policy-violations').then((data) => {
            if (data.status !== 'success') return;
            const count = document.getElementById('policy-violation-count');
            if (count) count.textContent = String(data.critical_count ?? 0);
            const list = document.getElementById('policy-list');
            if (list) {
                list.innerHTML = (data.violations || []).slice(0, 4).map((v) =>
                    `<div class="p-3 bg-rose-500/5 border border-rose-500/20 rounded-xl"><p class="text-sm text-white">${v.resource || v.name}</p>` +
                    `<p class="text-xs text-rose-400 mt-1">${v.policy || v.violation} · ${v.severity}</p></div>`
                ).join('') || '<p class="text-xs text-slate-500">No policy violations.</p>';
            }
        }),
        fetchJson('/api/finops/budget-status').then((data) => {
            if (data.status !== 'success') return;
            const list = document.getElementById('budget-list');
            if (list) {
                list.innerHTML = (data.budgets || []).map((b) => {
                    const pct = b.budget > 0 ? (b.actual / b.budget) * 100 : 0;
                    return `<div><div class="flex justify-between text-sm mb-2"><span class="text-white">${b.name}</span>` +
                        `<span class="${pct > 90 ? 'text-rose-400' : 'text-cyan-400'}">${pct.toFixed(0)}%</span></div>` +
                        `<div class="w-full bg-white/5 h-1.5 rounded-full"><div class="bg-cyan-400 h-full rounded-full" style="width:${Math.min(pct, 100)}%"></div></div></div>`;
                }).join('') || '<p class="text-xs text-slate-500">No budgets configured.</p>';
            }
        }),
    ];
    await Promise.allSettled(loaders);
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
