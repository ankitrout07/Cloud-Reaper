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
