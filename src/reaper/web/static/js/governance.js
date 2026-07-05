// Governance Dashboard JavaScript

// API Base URL
const API_BASE = '/api/v1/governance';

// Tab switching
function switchTab(tabName) {
    // Hide all tab contents
    document.querySelectorAll('.tab-content').forEach(content => {
        content.classList.add('hidden');
    });
    
    // Remove active state from all tabs
    document.querySelectorAll('.tab-button').forEach(button => {
        button.classList.remove('active', 'border-blue-500', 'text-blue-600', 'dark:text-blue-400');
        button.classList.add('border-transparent', 'text-gray-500', 'dark:text-gray-400');
    });
    
    // Show selected tab content
    document.getElementById(`content-${tabName}`).classList.remove('hidden');
    
    // Add active state to selected tab
    const activeTab = document.getElementById(`tab-${tabName}`);
    activeTab.classList.add('active', 'border-blue-500', 'text-blue-600', 'dark:text-blue-400');
    activeTab.classList.remove('border-transparent', 'text-gray-500', 'dark:text-gray-400');
    
    // Load content for the tab
    switch(tabName) {
        case 'policies':
            loadPolicies();
            break;
        case 'migration':
            loadMigrationAssessments();
            break;
        case 'cost':
            loadCostSummary();
            break;
        case 'best-practices':
            loadBestPractices();
            break;
    }
}

// ============ Policy Templates ============

async function loadPolicies() {
    try {
        const response = await fetch(`${API_BASE}/policies`);
        const data = await response.json();
        
        if (data.status === 'success') {
            displayPolicies(data.policies);
            updateSummaryCard('active-policies-count', data.policies.filter(p => p.status === 'active').length);
        }
    } catch (error) {
        console.error('Failed to load policies:', error);
    }
}

function displayPolicies(policies) {
    const container = document.getElementById('policies-list');
    
    if (policies.length === 0) {
        container.innerHTML = `
            <div class="text-center py-8 text-gray-500 dark:text-gray-400">
                <p>No policy templates found. Create your first policy to get started.</p>
            </div>
        `;
        return;
    }
    
    container.innerHTML = policies.map(policy => `
        <div class="border border-gray-200 dark:border-gray-700 rounded-lg p-4 hover:bg-gray-50 dark:hover:bg-gray-700 transition">
            <div class="flex justify-between items-start">
                <div>
                    <h3 class="font-semibold text-gray-900 dark:text-white">${policy.name}</h3>
                    <p class="text-sm text-gray-600 dark:text-gray-400 mt-1">${policy.description}</p>
                    <div class="flex space-x-2 mt-2">
                        <span class="px-2 py-1 text-xs rounded-full ${getCategoryColor(policy.category)}">${formatCategory(policy.category)}</span>
                        <span class="px-2 py-1 text-xs rounded-full ${getSeverityColor(policy.severity)}">${policy.severity}</span>
                        <span class="px-2 py-1 text-xs rounded-full ${getStatusColor(policy.status)}">${policy.status}</span>
                    </div>
                </div>
                <div class="flex space-x-2">
                    <button onclick="evaluatePolicy('${policy.policy_id}')" class="px-3 py-1 text-sm bg-blue-100 text-blue-700 rounded hover:bg-blue-200 transition">
                        Evaluate
                    </button>
                    <button onclick="editPolicy('${policy.policy_id}')" class="px-3 py-1 text-sm bg-gray-100 text-gray-700 rounded hover:bg-gray-200 transition">
                        Edit
                    </button>
                    <button onclick="deletePolicy('${policy.policy_id}')" class="px-3 py-1 text-sm bg-red-100 text-red-700 rounded hover:bg-red-200 transition">
                        Delete
                    </button>
                </div>
            </div>
        </div>
    `).join('');
}

function createPolicy() {
    document.getElementById('policy-modal').classList.remove('hidden');
}

function closePolicyModal() {
    document.getElementById('policy-modal').classList.add('hidden');
    document.getElementById('policy-form').reset();
}

async function savePolicy(event) {
    event.preventDefault();
    
    const policyData = {
        policy_id: document.getElementById('policy-id').value,
        name: document.getElementById('policy-name').value,
        category: document.getElementById('policy-category').value,
        severity: document.getElementById('policy-severity').value,
        description: document.getElementById('policy-description').value,
        universal_rules: [],
        provider_translations: {}
    };
    
    try {
        const response = await fetch(`${API_BASE}/policies`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(policyData)
        });
        
        const data = await response.json();
        
        if (data.status === 'success') {
            closePolicyModal();
            loadPolicies();
            showNotification('Policy created successfully', 'success');
        } else {
            showNotification('Failed to create policy: ' + data.error, 'error');
        }
    } catch (error) {
        console.error('Failed to save policy:', error);
        showNotification('Failed to create policy', 'error');
    }
}

async function evaluatePolicy(policyId) {
    // This would typically open a modal to select resources to evaluate
    // For now, just show a notification
    showNotification(`Evaluating policy: ${policyId}`, 'info');
}

async function deletePolicy(policyId) {
    if (!confirm('Are you sure you want to delete this policy?')) return;
    
    try {
        const response = await fetch(`${API_BASE}/policies/${policyId}`, {
            method: 'DELETE'
        });
        
        const data = await response.json();
        
        if (data.status === 'success') {
            loadPolicies();
            showNotification('Policy deleted successfully', 'success');
        } else {
            showNotification('Failed to delete policy: ' + data.error, 'error');
        }
    } catch (error) {
        console.error('Failed to delete policy:', error);
        showNotification('Failed to delete policy', 'error');
    }
}

// ============ Migration Advisor ============

async function loadMigrationAssessments() {
    const container = document.getElementById('migration-list');
    container.innerHTML = `
        <div class="text-center py-8 text-gray-500 dark:text-gray-400">
            <p>No migration assessments found. Create a new assessment to compare cloud providers.</p>
        </div>
    `;
}

function newMigrationAssessment() {
    showNotification('Migration assessment wizard would open here', 'info');
}

// ============ Cost Aggregation ============

async function loadCostSummary() {
    const container = document.getElementById('cost-summary');
    container.innerHTML = `
        <div class="text-center py-8 text-gray-500 dark:text-gray-400">
            <p>Generate a multi-cloud cost report to see aggregated spending across providers.</p>
        </div>
    `;
}

function generateCostReport() {
    showNotification('Cost report generation wizard would open here', 'info');
}

// ============ Best Practices ============

async function loadBestPractices() {
    const provider = document.getElementById('provider-filter').value;
    const url = provider ? `${API_BASE}/best-practices?provider=${provider}` : `${API_BASE}/best-practices`;
    
    try {
        const response = await fetch(url);
        const data = await response.json();
        
        if (data.status === 'success') {
            displayBestPractices(data.practices);
        }
    } catch (error) {
        console.error('Failed to load best practices:', error);
    }
}

function displayBestPractices(practices) {
    const container = document.getElementById('best-practices-list');
    
    if (practices.length === 0) {
        container.innerHTML = `
            <div class="text-center py-8 text-gray-500 dark:text-gray-400">
                <p>No best practices found for the selected provider.</p>
            </div>
        `;
        return;
    }
    
    container.innerHTML = practices.map(practice => `
        <div class="border border-gray-200 dark:border-gray-700 rounded-lg p-4 hover:bg-gray-50 dark:hover:bg-gray-700 transition">
            <div class="flex justify-between items-start">
                <div>
                    <h3 class="font-semibold text-gray-900 dark:text-white">${practice.name}</h3>
                    <p class="text-sm text-gray-600 dark:text-gray-400 mt-1">${practice.description}</p>
                    <div class="flex space-x-2 mt-2">
                        <span class="px-2 py-1 text-xs rounded-full bg-blue-100 text-blue-700">${practice.provider}</span>
                        <span class="px-2 py-1 text-xs rounded-full ${getCategoryColor(practice.category)}">${formatCategory(practice.category)}</span>
                        <span class="px-2 py-1 text-xs rounded-full ${getSeverityColor(practice.severity)}">${practice.severity}</span>
                    </div>
                </div>
                <button onclick="evaluatePractice('${practice.practice_id}')" class="px-3 py-1 text-sm bg-blue-100 text-blue-700 rounded hover:bg-blue-200 transition">
                    Evaluate
                </button>
            </div>
        </div>
    `).join('');
}

function filterBestPractices() {
    loadBestPractices();
}

function evaluatePractice(practiceId) {
    showNotification(`Evaluating best practice: ${practiceId}`, 'info');
}

// ============ Compliance Scan ============

async function runComplianceScan() {
    showNotification('Running compliance scan...', 'info');
    
    // Simulate compliance scan
    setTimeout(() => {
        updateSummaryCard('compliance-score', '85%');
        updateSummaryCard('violations-count', '12');
        updateSummaryCard('recommendations-count', '8');
        showNotification('Compliance scan completed', 'success');
    }, 2000);
}

// ============ Report Generation ============

function generateReport() {
    showNotification('Generating governance report...', 'info');
}

// ============ Utility Functions ============

function updateSummaryCard(cardId, value) {
    document.getElementById(cardId).textContent = value;
}

function getCategoryColor(category) {
    const colors = {
        'cost_optimization': 'bg-green-100 text-green-700',
        'security_governance': 'bg-red-100 text-red-700',
        'operational_excellence': 'bg-blue-100 text-blue-700',
        'sustainability': 'bg-yellow-100 text-yellow-700',
        'compliance': 'bg-purple-100 text-purple-700'
    };
    return colors[category] || 'bg-gray-100 text-gray-700';
}

function getSeverityColor(severity) {
    const colors = {
        'critical': 'bg-red-100 text-red-700',
        'high': 'bg-orange-100 text-orange-700',
        'medium': 'bg-yellow-100 text-yellow-700',
        'low': 'bg-blue-100 text-blue-700',
        'info': 'bg-gray-100 text-gray-700'
    };
    return colors[severity] || 'bg-gray-100 text-gray-700';
}

function getStatusColor(status) {
    const colors = {
        'active': 'bg-green-100 text-green-700',
        'draft': 'bg-yellow-100 text-yellow-700',
        'disabled': 'bg-gray-100 text-gray-700',
        'archived': 'bg-red-100 text-red-700'
    };
    return colors[status] || 'bg-gray-100 text-gray-700';
}

function formatCategory(category) {
    return category.split('_').map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' ');
}

function showNotification(message, type = 'info') {
    // Simple notification implementation
    const notification = document.createElement('div');
    notification.className = `fixed top-4 right-4 px-4 py-2 rounded-lg shadow-lg text-white ${
        type === 'success' ? 'bg-green-500' :
        type === 'error' ? 'bg-red-500' :
        'bg-blue-500'
    }`;
    notification.textContent = message;
    document.body.appendChild(notification);
    
    setTimeout(() => {
        notification.remove();
    }, 3000);
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    loadPolicies();
});
