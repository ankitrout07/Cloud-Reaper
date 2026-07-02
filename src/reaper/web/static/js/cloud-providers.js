const CLOUD_PROVIDERS = ["aws", "azure", "gcp"];

async function readSettingsFileContent(inputId) {
    const input = document.getElementById(inputId);
    if (!input || !input.files || !input.files[0]) {
        return null;
    }
    
    try {
        return await input.files[0].text();
    } catch (error) {
        console.error('[cloud-providers] Failed to read file content:', error);
        return null;
    }
}

function collectProviderCredentials(provider) {
    if (provider === "aws") {
        return {
            access_key_id: document.getElementById("settings-aws-access-key-id")?.value.trim(),
            secret_access_key: document.getElementById("settings-aws-secret-access-key")?.value.trim(),
            region: document.getElementById("settings-aws-region")?.value.trim() || "us-east-1",
        };
    }
    if (provider === "azure") {
        return {
            subscription_id: document.getElementById("settings-azure-subscription-id")?.value.trim(),
            tenant_id: document.getElementById("settings-azure-tenant-id")?.value.trim(),
            client_id: document.getElementById("settings-azure-client-id")?.value.trim(),
            client_secret: document.getElementById("settings-azure-client-secret")?.value.trim(),
        };
    }
    if (provider === "gcp") {
        return {
            project_id: document.getElementById("settings-gcp-project-id")?.value.trim(),
            service_account_json: null,
        };
    }
    return {};
}

async function connectSettingsProvider(provider) {
    const btn = document.getElementById(`settings-connect-${provider}`);
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i> Connecting...';
    }

    let credentials = collectProviderCredentials(provider);
    if (provider === "gcp") {
        const serviceAccount = await readSettingsFileContent("settings-gcp-key-file");
        credentials.service_account_json = serviceAccount;
    }

    try {
        const res = await fetch("/api/settings/connect-cloud", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                provider,
                connection_name: `${provider.toUpperCase()} Connection`,
                credentials,
            }),
        });
        
        if (!res.ok) {
            throw new Error(`HTTP error! status: ${res.status}`);
        }
        
        const data = await res.json();
        if (data.status !== "success") {
            throw new Error(data.message || "Failed to connect provider");
        }
        if (typeof showToast === "function") {
            showToast(data.message, "success");
        }
        await refreshCloudConnections();
        
        // Auto-close panel on success
        if (btn) {
            setTimeout(() => {
                toggleCloudPanel(provider);
            }, 1000);
        }
    } catch (error) {
        console.error('[cloud-providers] Connection failed:', error);
        if (typeof showToast === "function") {
            showToast(error.message || "Connection failed", "error");
        }
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = 'Connect & Activate';
        }
    }
}

async function switchSettingsProvider(provider) {
    try {
        const res = await fetch(`/api/context/switch?provider=${encodeURIComponent(provider)}`);
        
        if (!res.ok) {
            throw new Error(`HTTP error! status: ${res.status}`);
        }
        
        const data = await res.json();
        if (data.status === "redirect" && data.url) {
            window.location.href = data.url;
            return;
        }
        if (data.status === "success") {
            if (typeof showToast === "function") {
                showToast(data.message || `Switched to ${provider.toUpperCase()}.`, "success");
            }
            await refreshCloudConnections();
            return;
        }
        throw new Error(data.message || "Failed to switch provider");
    } catch (error) {
        console.error('[cloud-providers] Switch provider failed:', error);
        if (typeof showToast === "function") {
            showToast(error.message || "Failed to switch provider", "error");
        }
    }
}

function updateCloudProviderCards(connections, activeProvider) {
    CLOUD_PROVIDERS.forEach((provider) => {
        const statusEl = document.getElementById(`cloud-status-${provider}`);
        const switchBtn = document.getElementById(`cloud-switch-${provider}`);
        const card = document.getElementById(`cloud-status-${provider}`)?.closest('.group') || 
                     document.getElementById(`cloud-status-${provider}`)?.closest('[class*="p-8"]');
        const info = connections[provider];
        const isActive = activeProvider === provider || (info && info.is_active);

        if (statusEl) {
            if (!info) {
                statusEl.textContent = "Not connected";
                statusEl.className = "text-[10px] font-bold uppercase text-slate-500";
            } else if (isActive) {
                statusEl.textContent = "Active";
                statusEl.className = "text-[10px] font-bold uppercase text-cyan-400";
            } else {
                statusEl.textContent = "Connected";
                statusEl.className = "text-[10px] font-bold uppercase text-green-400";
            }
        }

        if (switchBtn) {
            switchBtn.disabled = !info || isActive;
            switchBtn.classList.toggle("opacity-40", !info || isActive);
        }
        
        // Add visual indicator to card for active provider
        if (card && isActive) {
            card.classList.add('border-cyan-400', 'bg-cyan-500/10');
            card.classList.remove('border-gray-700', 'border-white/[0.06]');
        } else if (card) {
            card.classList.remove('border-cyan-400', 'bg-cyan-500/10');
            card.classList.add('border-gray-700', 'border-white/[0.06]');
        }
    });
}

async function refreshCloudConnections() {
    try {
        const res = await fetch("/api/settings/cloud-connections");
        
        if (!res.ok) {
            console.warn('[cloud-providers] Cloud connections endpoint returned non-OK status:', res.status);
            return;
        }
        
        const data = await res.json();
        if (data.status === "success") {
            updateCloudProviderCards(data.connections || {}, data.active_provider || "");
        }
    } catch (error) {
        console.warn('[cloud-providers] Failed to refresh cloud connections:', error);
    }
}

// Make refreshCloudConnections globally accessible
window.refreshCloudConnections = refreshCloudConnections;

function toggleCloudPanel(provider) {
    document.querySelectorAll(".cloud-provider-panel").forEach((panel) => {
        panel.classList.add("hidden");
    });
    const panel = document.getElementById(`cloud-panel-${provider}`);
    if (panel) {
        panel.classList.remove("hidden");
    }
    // Refresh connections when showing a provider panel
    refreshCloudConnections();
}

document.addEventListener("DOMContentLoaded", () => {
    refreshCloudConnections();

    const params = new URLSearchParams(window.location.search);
    const provider = params.get("provider");
    if (params.get("tab") === "cloud" && provider && CLOUD_PROVIDERS.includes(provider)) {
        if (typeof showTab === "function") {
            showTab("cloud");
        }
        toggleCloudPanel(provider);
    }
});

// Wizard functions for onboarding
let selectedWizardProvider = null;

window.selectWizardProvider = (provider) => {
    selectedWizardProvider = provider;
    
    // Highlight selected provider card
    document.querySelectorAll('.provider-card').forEach(card => {
        card.classList.remove('border-cyan-400', 'bg-cyan-500/10');
        card.classList.add('border-white/10');
    });
    
    const selectedCard = document.getElementById(`provider-card-${provider}`);
    if (selectedCard) {
        selectedCard.classList.remove('border-white/10');
        selectedCard.classList.add('border-cyan-400', 'bg-cyan-500/10');
    }
    
    // Enable next button
    const nextBtn = document.getElementById('provider-select-next');
    if (nextBtn) {
        nextBtn.disabled = false;
        nextBtn.classList.remove('bg-gray-700', 'text-gray-500', 'cursor-not-allowed');
        nextBtn.classList.add('bg-cyan-500', 'text-white', 'cursor-pointer');
    }
};

window.wizardNext = (step) => {
    // Hide current step
    document.getElementById(`wizard-step-${step - 1}`).classList.add('hidden');
    
    // Show next step
    const nextStepEl = document.getElementById(`wizard-step-${step}`);
    if (nextStepEl) {
        nextStepEl.classList.remove('hidden');
    }
    
    // If going to step 2, show the appropriate provider panel
    if (step === 2 && selectedWizardProvider) {
        document.querySelectorAll('.provider-panel').forEach(panel => {
            panel.classList.add('hidden');
        });
        
        const providerPanel = document.getElementById(`provider-${selectedWizardProvider}`);
        if (providerPanel) {
            providerPanel.classList.remove('hidden');
        }
    }
};

window.wizardBack = (step) => {
    // Hide current step
    document.getElementById(`wizard-step-${step + 1}`).classList.add('hidden');
    
    // Show previous step
    const prevStepEl = document.getElementById(`wizard-step-${step}`);
    if (prevStepEl) {
        prevStepEl.classList.remove('hidden');
    }
};

window.connectWizardProvider = async () => {
    if (!selectedWizardProvider) {
        if (typeof showToast === "function") {
            showToast("Please select a provider first.", "error");
        }
        return;
    }
    
    const btn = document.getElementById('connect-provider-btn');
    const originalBtnText = btn?.innerHTML;
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i> Validating credentials...';
    }
    
    try {
        let credentials = {};
        
        if (selectedWizardProvider === 'aws') {
            credentials = {
                access_key_id: document.getElementById('aws-access-key-id')?.value.trim(),
                secret_access_key: document.getElementById('aws-secret-access-key')?.value.trim(),
                region: document.getElementById('aws-region')?.value.trim() || 'us-east-1',
            };
        } else if (selectedWizardProvider === 'azure') {
            credentials = {
                subscription_id: document.getElementById('azure-subscription-id')?.value.trim(),
                tenant_id: document.getElementById('azure-tenant-id')?.value.trim(),
                client_id: document.getElementById('azure-client-id')?.value.trim(),
                client_secret: document.getElementById('azure-client-secret')?.value.trim(),
            };
        } else if (selectedWizardProvider === 'gcp') {
            credentials = {
                project_id: document.getElementById('gcp-project-id')?.value.trim(),
                service_account_json: null,
            };
            
            // Handle file upload for GCP
            const keyFile = document.getElementById('gcp-key-file');
            if (keyFile && keyFile.files[0]) {
                try {
                    credentials.service_account_json = await keyFile.files[0].text();
                } catch (error) {
                    console.error('[cloud-providers] Failed to read GCP key file:', error);
                    throw new Error('Failed to read GCP key file');
                }
            }
        }
        
        // Add connection log entry to show progress
        const logPanel = document.getElementById('setup-scan-log');
        if (logPanel) {
            logPanel.innerHTML += `<p class="text-cyan-400">> Validating ${selectedWizardProvider.toUpperCase()} credentials...</p>`;
            logPanel.scrollTop = logPanel.scrollHeight;
        }
        
        const response = await fetch('/api/settings/connect-cloud', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                provider: selectedWizardProvider,
                connection_name: `${selectedWizardProvider.toUpperCase()} Connection`,
                credentials: credentials,
            }),
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        
        if (data.status === 'success') {
            if (logPanel) {
                logPanel.innerHTML += `<p class="text-green-400">> ${data.message}</p>`;
                logPanel.scrollTop = logPanel.scrollHeight;
            }
            
            if (typeof showToast === "function") {
                showToast(data.message, "success");
            }
            
            // Enable finish button
            const finishBtn = document.getElementById('finish-btn');
            if (finishBtn) {
                finishBtn.disabled = false;
                finishBtn.classList.remove('bg-gray-700', 'text-gray-500', 'cursor-not-allowed');
                finishBtn.classList.add('bg-cyan-500', 'text-white', 'cursor-pointer');
            }
            
            // Move to step 3
            wizardNext(3);
        } else {
            if (logPanel) {
                logPanel.innerHTML += `<p class="text-red-400">> Connection failed: ${data.message}</p>`;
                logPanel.scrollTop = logPanel.scrollHeight;
            }
            throw new Error(data.message || 'Connection failed');
        }
    } catch (error) {
        console.error('[cloud-providers] Wizard connection failed:', error);
        if (typeof showToast === "function") {
            showToast(error.message || "Connection failed", "error");
        }
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = originalBtnText;
        }
    }
};

window.completeSetup = () => {
    const logPanel = document.getElementById('setup-scan-log');
    if (logPanel) {
        logPanel.innerHTML += `<p class="text-green-400">> Setup completed successfully!</p>`;
        logPanel.innerHTML += `<p class="text-cyan-400">> Redirecting to dashboard...</p>`;
        logPanel.scrollTop = logPanel.scrollHeight;
    }
    
    if (typeof showToast === "function") {
        showToast("Setup complete! Redirecting to dashboard...", "success");
    }
    setTimeout(() => {
        window.location.href = '/';
    }, 1500);
};
