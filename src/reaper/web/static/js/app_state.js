/**
 * Global Application State Manager
 * ================================
 * This script runs continuously across all page DOM render templates and provides
 * a centralized orchestrator for cloud provider authentication state.
 *
 * Features:
 * - Queries GET /api/v1/auth/status on document initialization
 * - Updates sidebar status element (#go-engine-status) when authenticated
 * - Dispatches global CustomEvent 'cloudProviderActivated' for component listeners
 * - Provides polling mechanism for real-time state updates
 * - Manages UI state for authentication-aware components
 */

(function () {
    'use strict';

    // ── Configuration ────────────────────────────────────────────────────────────────
    const AUTH_STATUS_ENDPOINT = '/api/v1/auth/status';
    const POLLING_INTERVAL_MS = 10000; // Poll every 10 seconds
    const SIDEBAR_STATUS_ID = 'go-engine-status';

    // ── State ─────────────────────────────────────────────────────────────────────────
    let currentAuthState = {
        provider: null,
        authenticated: false,
        subscription_id: null,
        last_sync: null
    };

    let pollingTimer = null;

    // ── Utilities ───────────────────────────────────────────────────────────────────
    function escapeHtml(str) {
        if (str == null) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    // ── Core Functions ───────────────────────────────────────────────────────────────
    /**
     * Fetch the current authentication status from the backend
     */
    async function fetchAuthStatus() {
        try {
            const response = await fetch(AUTH_STATUS_ENDPOINT);
            const data = await response.json();

            if (data.provider !== undefined) {
                currentAuthState = {
                    provider: data.provider,
                    authenticated: data.authenticated || false,
                    subscription_id: data.subscription_id,
                    last_sync: data.last_sync
                };

                // Update UI and dispatch event if state changed
                updateAuthenticationUI();
                dispatchAuthEvent();

                return currentAuthState;
            }
        } catch (error) {
            console.warn('[app_state] Failed to fetch auth status:', error);
        }
        return currentAuthState;
    }

    /**
     * Update the sidebar status element based on authentication state
     */
    function updateAuthenticationUI() {
        const statusElement = document.getElementById(SIDEBAR_STATUS_ID);
        if (!statusElement) return;

        if (currentAuthState.authenticated) {
            // Update to green "GO ENGINE LIVE" status
            statusElement.textContent = 'GO ENGINE LIVE';
            statusElement.className = 'text-[10px] font-bold uppercase text-green-400';

            // Add a subtle glow effect
            statusElement.style.textShadow = '0 0 10px rgba(74, 222, 128, 0.5)';
        } else {
            // Reset to default/inactive state
            statusElement.textContent = 'GO ENGINE OFFLINE';
            statusElement.className = 'text-[10px] font-bold uppercase text-slate-500';
            statusElement.style.textShadow = 'none';
        }
    }

    /**
     * Dispatch a global CustomEvent to notify all components of authentication state changes
     */
    function dispatchAuthEvent() {
        const event = new CustomEvent('cloudProviderActivated', {
            detail: {
                provider: currentAuthState.provider,
                authenticated: currentAuthState.authenticated,
                subscription_id: currentAuthState.subscription_id,
                last_sync: currentAuthState.last_sync
            }
        });

        window.dispatchEvent(event);
        console.log('[app_state] Dispatched cloudProviderActivated event:', currentAuthState);
    }

    /**
     * Show or hide authentication overlay on pages that require provider authentication
     */
    function updateAuthOverlay(show) {
        // Check if an auth overlay exists
        let overlay = document.getElementById('auth-required-overlay');

        if (show) {
            if (!overlay) {
                // Create overlay if it doesn't exist
                overlay = document.createElement('div');
                overlay.id = 'auth-required-overlay';
                overlay.className = 'fixed inset-0 bg-slate-900/80 backdrop-blur-sm z-50 flex items-center justify-center';
                overlay.innerHTML = `
                    <div class="bg-slate-800 border border-slate-700 rounded-xl p-8 max-w-md text-center shadow-2xl">
                        <div class="text-6xl mb-4">🔐</div>
                        <h2 class="text-xl font-bold text-white mb-2">Authentication Required</h2>
                        <p class="text-slate-400 mb-6">
                            Please configure and activate your Azure Service Principal in Settings to view live infrastructure telemetry data.
                        </p>
                        <a href="/settings?tab=cloud" class="inline-block bg-cyan-500 hover:bg-cyan-400 text-white font-bold py-3 px-6 rounded-lg transition-colors">
                            Go to Settings
                        </a>
                    </div>
                `;
                document.body.appendChild(overlay);
            }
            overlay.classList.remove('hidden');
        } else {
            if (overlay) {
                overlay.classList.add('hidden');
            }
        }
    }

    // ── Public API ───────────────────────────────────────────────────────────────────
    /**
     * Get the current authentication state (synchronous)
     */
    window.getAuthState = function () {
        return currentAuthState;
    };

    /**
     * Manually trigger a refresh of the authentication state
     */
    window.refreshAuthState = async function () {
        return await fetchAuthStatus();
    };

    /**
     * Enable or disable authentication overlay for the current page
     */
    window.setAuthOverlay = function (enabled) {
        updateAuthOverlay(enabled);
    };

    /**
     * Start polling for authentication state changes
     */
    window.startAuthPolling = function () {
        if (pollingTimer) {
            clearInterval(pollingTimer);
        }
        pollingTimer = setInterval(fetchAuthStatus, POLLING_INTERVAL_MS);
        console.log('[app_state] Started auth polling (interval:', POLLING_INTERVAL_MS, 'ms)');
    };

    /**
     * Stop polling for authentication state changes
     */
    window.stopAuthPolling = function () {
        if (pollingTimer) {
            clearInterval(pollingTimer);
            pollingTimer = null;
            console.log('[app_state] Stopped auth polling');
        }
    };

    // ── Initialization ───────────────────────────────────────────────────────────────
    document.addEventListener('DOMContentLoaded', async function () {
        console.log('[app_state] Initializing global application state manager...');

        // Initial fetch of authentication status
        await fetchAuthStatus();

        // Start polling for real-time updates
        startAuthPolling();

        // Listen for page navigation to refresh auth state
        if (typeof window.addEventListener === 'function') {
            window.addEventListener('popstate', async function () {
                await fetchAuthStatus();
            });
        }

        console.log('[app_state] Global application state manager initialized');
    });

    // ── Event Listener for SPA Navigation (HTMX) ───────────────────────────────────────
    document.body.addEventListener('htmx:afterSwap', async function (evt) {
        // Refresh auth state after page navigation
        await fetchAuthStatus();
    });

})();
