const CLOUD_PROVIDERS = ["aws", "azure", "gcp", "k8s"];

async function readSettingsFileContent(inputId) {
    const input = document.getElementById(inputId);
    if (!input || !input.files || !input.files[0]) {
        return null;
    }
    return input.files[0].text();
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
    if (provider === "k8s") {
        return {
            kubeconfig: document.getElementById("settings-k8s-kubeconfig")?.value.trim(),
            service_account_token: document.getElementById("settings-k8s-service-account-token")?.value.trim(),
            context: document.getElementById("settings-k8s-context")?.value.trim(),
        };
    }
    return {};
}

async function connectSettingsProvider(provider) {
    const btn = document.getElementById(`settings-connect-${provider}`);
    if (btn) {
        btn.disabled = true;
        btn.textContent = "Connecting...";
    }

    let credentials = collectProviderCredentials(provider);
    if (provider === "gcp") {
        const serviceAccount = await readSettingsFileContent("settings-gcp-key-file");
        credentials.service_account_json = serviceAccount;
    }
    if (provider === "k8s") {
        const kubeconfigFile = await readSettingsFileContent("settings-k8s-kubeconfig-file");
        if (!credentials.kubeconfig && kubeconfigFile) {
            credentials.kubeconfig = kubeconfigFile;
        }
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
        const data = await res.json();
        if (data.status !== "success") {
            throw new Error(data.message || "Failed to connect provider");
        }
        if (typeof showToast === "function") {
            showToast(data.message, "success");
        }
        await refreshCloudConnections();
    } catch (error) {
        if (typeof showToast === "function") {
            showToast(error.message, "error");
        }
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.textContent = "Connect & Activate";
        }
    }
}

async function switchSettingsProvider(provider) {
    try {
        const res = await fetch(`/api/context/switch?provider=${encodeURIComponent(provider)}`);
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
        if (typeof showToast === "function") {
            showToast(error.message, "error");
        }
    }
}

function updateCloudProviderCards(connections, activeProvider) {
    CLOUD_PROVIDERS.forEach((provider) => {
        const statusEl = document.getElementById(`cloud-status-${provider}`);
        const switchBtn = document.getElementById(`cloud-switch-${provider}`);
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
    });
}

async function refreshCloudConnections() {
    try {
        const res = await fetch("/api/settings/cloud-connections");
        const data = await res.json();
        if (data.status === "success") {
            updateCloudProviderCards(data.connections || {}, data.active_provider || "");
        }
    } catch {
        /* ignore refresh errors */
    }
}

function toggleCloudPanel(provider) {
    document.querySelectorAll(".cloud-provider-panel").forEach((panel) => {
        panel.classList.add("hidden");
    });
    const panel = document.getElementById(`cloud-panel-${provider}`);
    if (panel) {
        panel.classList.remove("hidden");
    }
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
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i> Connecting...';
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
                credentials.service_account_json = await keyFile.files[0].text();
            }
        } else if (selectedWizardProvider === 'k8s') {
            credentials = {
                kubeconfig: document.getElementById('k8s-kubeconfig')?.value.trim(),
                service_account_token: document.getElementById('k8s-service-account-token')?.value.trim(),
                context: document.getElementById('k8s-context')?.value.trim(),
            };
            
            // Handle file upload for k8s
            const kubeconfigFile = document.getElementById('k8s-kubeconfig-file');
            if (kubeconfigFile && kubeconfigFile.files[0]) {
                credentials.kubeconfig = await kubeconfigFile.files[0].text();
            }
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
        
        const data = await response.json();
        
        if (data.status === 'success') {
            if (typeof showToast === "function") {
                showToast(data.message, "success");
            }
            // Move to step 3
            wizardNext(3);
        } else {
            throw new Error(data.message || 'Connection failed');
        }
    } catch (error) {
        if (typeof showToast === "function") {
            showToast(error.message, "error");
        }
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = 'Connect & Activate';
        }
    }
};

window.completeSetup = () => {
    if (typeof showToast === "function") {
        showToast("Setup complete! Redirecting to dashboard...", "success");
    }
    setTimeout(() => {
        window.location.href = '/';
    }, 2000);
};
