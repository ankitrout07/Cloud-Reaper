/**
 * Example Event Listener Template for Consumer Views
 * ===================================================
 * This template demonstrates how individual page module scripts can listen dynamically
 * for the global 'cloudProviderActivated' event and respond to authentication state changes.
 *
 * Usage:
 * 1. Copy this template into your page-specific JavaScript file
 * 2. Customize the handleProviderActivated function for your specific page needs
 * 3. Remove or modify the handleProviderDeactivated function as needed
 *
 * Supported Pages:
 * - Cost Optimization
 * - Financial Intelligence
 * - Resource Inventory
 * - Dashboard
 * - Metrics Command
 */

(function () {
    'use strict';

    // ── Configuration ────────────────────────────────────────────────────────────────
    const AUTH_REQUIRED = true; // Set to false if this page doesn't require authentication

    // ── Event Handlers ───────────────────────────────────────────────────────────────
    /**
     * Handle cloud provider activation event
     * @param {CustomEvent} event - The cloudProviderActivated event with detail data
     */
    function handleProviderActivated(event) {
        const { provider, authenticated, subscription_id, last_sync } = event.detail;

        console.log('[page] Cloud provider activated:', { provider, authenticated, subscription_id, last_sync });

        if (authenticated) {
            // Enable page functionality
            enablePageFeatures();

            // Un-hide configuration charts/tables
            unhideContentElements();

            // Automatically trigger data loading
            loadPageData(subscription_id);

            // Show success notification
            if (typeof showToast === 'function') {
                showToast(`Connected to ${provider.toUpperCase()} - Loading data...`, 'success');
            }
        }
    }

    /**
     * Handle cloud provider deactivation event
     * @param {CustomEvent} event - The cloudProviderActivated event with authenticated=false
     */
    function handleProviderDeactivated(event) {
        const { authenticated } = event.detail;

        console.log('[page] Cloud provider deactivated:', { authenticated });

        if (!authenticated) {
            // Disable page functionality
            disablePageFeatures();

            // Hide content elements
            hideContentElements();

            // Show authentication prompt
            showAuthPrompt();
        }
    }

    // ── Page-Specific Functions ─────────────────────────────────────────────────────
    /**
     * Enable page features when provider is authenticated
     */
    function enablePageFeatures() {
        // Enable buttons, inputs, and interactive elements
        const interactiveElements = document.querySelectorAll('.auth-required');
        interactiveElements.forEach(el => {
            el.disabled = false;
            el.classList.remove('opacity-40', 'pointer-events-none');
        });

        // Remove any disabled state from buttons
        const buttons = document.querySelectorAll('button[data-auth-required="true"]');
        buttons.forEach(btn => {
            btn.disabled = false;
            btn.classList.remove('opacity-50', 'cursor-not-allowed');
        });
    }

    /**
     * Disable page features when provider is not authenticated
     */
    function disablePageFeatures() {
        // Disable buttons, inputs, and interactive elements
        const interactiveElements = document.querySelectorAll('.auth-required');
        interactiveElements.forEach(el => {
            el.disabled = true;
            el.classList.add('opacity-40', 'pointer-events-none');
        });

        // Add disabled state to buttons
        const buttons = document.querySelectorAll('button[data-auth-required="true"]');
        buttons.forEach(btn => {
            btn.disabled = true;
            btn.classList.add('opacity-50', 'cursor-not-allowed');
        });
    }

    /**
     * Un-hide content elements when provider is authenticated
     */
    function unhideContentElements() {
        // Show data containers, charts, and tables
        const contentElements = document.querySelectorAll('[data-auth-hidden="true"]');
        contentElements.forEach(el => {
            el.classList.remove('hidden');
        });

        // Hide empty state or authentication prompts
        const emptyStates = document.querySelectorAll('.auth-empty-state');
        emptyStates.forEach(el => {
            el.classList.add('hidden');
        });
    }

    /**
     * Hide content elements when provider is not authenticated
     */
    function hideContentElements() {
        // Hide data containers, charts, and tables
        const contentElements = document.querySelectorAll('[data-auth-hidden="true"]');
        contentElements.forEach(el => {
            el.classList.add('hidden');
        });

        // Show empty state or authentication prompts
        const emptyStates = document.querySelectorAll('.auth-empty-state');
        emptyStates.forEach(el => {
            el.classList.remove('hidden');
        });
    }

    /**
     * Load page data automatically when provider is authenticated
     * @param {string} subscriptionId - The active subscription ID
     */
    function loadPageData(subscriptionId) {
        // Example: Trigger cost optimization analysis
        if (typeof window.runAnalysis === 'function') {
            console.log('[page] Automatically running cost analysis...');
            window.runAnalysis();
        }

        // Example: Load resource inventory
        if (typeof window.loadResourceInventory === 'function') {
            console.log('[page] Automatically loading resource inventory...');
            window.loadResourceInventory();
        }

        // Example: Load financial intelligence data
        if (typeof window.loadFinancialData === 'function') {
            console.log('[page] Automatically loading financial data...');
            window.loadFinancialData();
        }

        // Example: Load dashboard metrics
        if (typeof window.loadDashboardMetrics === 'function') {
            console.log('[page] Automatically loading dashboard metrics...');
            window.loadDashboardMetrics();
        }

        // Add your page-specific data loading functions here
        // Replace with your actual function calls
    }

    /**
     * Show authentication prompt to user
     */
    function showAuthPrompt() {
        // Show glassmorphic blurred overlay component
        if (typeof window.setAuthOverlay === 'function') {
            window.setAuthOverlay(true);
        }

        // Alternatively, show inline message
        const promptContainer = document.getElementById('auth-prompt-container');
        if (promptContainer) {
            promptContainer.innerHTML = `
                <div class="bg-slate-800/50 backdrop-blur-sm border border-slate-700 rounded-xl p-6 text-center">
                    <div class="text-4xl mb-3">🔐</div>
                    <h3 class="text-lg font-bold text-white mb-2">Authentication Required</h3>
                    <p class="text-slate-400 text-sm mb-4">
                        Please configure and activate your Azure Service Principal in Settings to view live infrastructure telemetry data.
                    </p>
                    <a href="/settings?tab=cloud" class="inline-block bg-cyan-500 hover:bg-cyan-400 text-white font-bold py-2 px-4 rounded-lg text-sm transition-colors">
                        Configure Provider
                    </a>
                </div>
            `;
            promptContainer.classList.remove('hidden');
        }
    }

    /**
     * Hide authentication prompt
     */
    function hideAuthPrompt() {
        if (typeof window.setAuthOverlay === 'function') {
            window.setAuthOverlay(false);
        }

        const promptContainer = document.getElementById('auth-prompt-container');
        if (promptContainer) {
            promptContainer.classList.add('hidden');
        }
    }

    // ── Initialization ───────────────────────────────────────────────────────────────
    document.addEventListener('DOMContentLoaded', function () {
        console.log('[page] Initializing event listener for cloud provider state...');

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
                // Provider is already authenticated, enable features
                handleProviderActivated({ detail: initialState });
            } else if (AUTH_REQUIRED) {
                // Provider is not authenticated and this page requires it
                handleProviderDeactivated({ detail: initialState });
            }
        }

        console.log('[page] Event listener initialized');
    });

})();
