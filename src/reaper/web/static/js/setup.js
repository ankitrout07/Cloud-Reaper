// Maps notify() to showToast() when the settings page defines it.
function notify(message, type) {
    if (typeof showToast === "function") {
        showToast(message, type === "danger" ? "error" : "success");
    } else {
        console.log(`Notification (${type}): ${message}`);
    }
}

function toggleFieldVisibility(inputId, iconId) {
    const input = document.getElementById(inputId);
    const icon = document.getElementById(iconId);

    if (input.type === "password") {
        input.type = "text";
        icon.classList.replace("fa-eye", "fa-eye-slash");
    } else {
        input.type = "password";
        icon.classList.replace("fa-eye-slash", "fa-eye");
    }
}

async function switchGlobalProvider(provider) {
    try {
        const response = await fetch(`/api/context/switch?provider=${encodeURIComponent(provider)}`);
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();

        if (data.status === "redirect" && data.url) {
            window.location.href = data.url;
            return;
        }

        if (data.status === "success") {
            if (typeof showToast === "function") {
                showToast(data.message || `Switched to ${provider.toUpperCase()} context.`, "success");
            } else {
                notify(data.message || `Switched to ${provider.toUpperCase()} context.`, "success");
            }
            window.location.reload();
            return;
        }

        const message = data.message || "Failed to switch provider context.";
        if (typeof showToast === "function") {
            showToast(message, "error");
        } else {
            notify(message, "danger");
        }
    } catch (error) {
        console.error('[setup] Error switching provider context:', error);
        if (typeof showToast === "function") {
            showToast("Unable to switch provider context.", "error");
        } else {
            notify("Unable to switch provider context.", "danger");
        }
    }
}

async function connectInfrastructure() {
    const payload = {
        subscriptionId: document.getElementById("subId")?.value,
        tenantId: document.getElementById("tenantId")?.value,
        clientId: document.getElementById("clientId")?.value,
        clientSecret: document.getElementById("clientSecret")?.value,
    };

    const response = await fetch("/api/settings/sync", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
    });

    let data = {};
    try {
        data = await response.json();
    } catch {
        data = {};
    }

    if (response.ok) {
        if (typeof showToast === "function") {
            showToast(data.message || "Credentials synced to .env", "success");
        } else {
            notify(data.message || "Credentials synced to .env", "success");
        }
        const pulse = document.getElementById("auth-pulse");
        if (pulse) {
            pulse.className =
                "w-3 h-3 rounded-full bg-cyan-400 shadow-[0_0_15px_rgba(0,242,255,0.6)] animate-pulse";
        }
        if (typeof checkAuth === "function") checkAuth();
    } else {
        const msg = data.message || data.msg || "Sync failed";
        if (typeof showToast === "function") {
            showToast(msg, "error");
        } else {
            notify(msg, "danger");
        }
    }
}

// Sidebar dynamic highlighting (path + settings tab query)
function initializeSidebarHighlighting() {
    const currentPath = window.location.pathname;
    const params = new URLSearchParams(window.location.search);
    const settingsTab = params.get("tab");
    const navLinks = document.querySelectorAll("#sidebar a.nav-link");

    navLinks.forEach((link) => {
        link.classList.remove("nav-link-active");

        const navPath = link.getAttribute("data-nav-path");
        const navTab = link.getAttribute("data-nav-tab");

        let isActive = false;
        if (navTab && currentPath === "/settings") {
            isActive = settingsTab === navTab;
        } else if (navPath) {
            isActive =
                navPath === currentPath ||
                (currentPath === "/" && navPath === "/") ||
                (navPath === "/settings" && currentPath === "/settings" && !settingsTab);
        } else {
            const href = (link.getAttribute("href") || "").split("?")[0];
            isActive = href === currentPath || (currentPath === "/" && href === "/");
        }

        if (isActive) {
            link.classList.add("nav-link-active");
        }
    });
}

document.addEventListener('DOMContentLoaded', initializeSidebarHighlighting);

// Additional settings functions
window.refreshSubs = async () => {
    try {
        const response = await fetch('/api/settings/subscriptions');
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const data = await response.json();
        if (data.status === 'success') {
            if (typeof showToast === "function") {
                showToast("Subscriptions refreshed.", "success");
            }
            // Update subscription list if element exists
            const subList = document.getElementById('sub-checklist');
            if (subList && data.subscriptions) {
                subList.innerHTML = data.subscriptions.map(sub => `
                    <label class="flex items-center gap-3 p-3 bg-white/5 rounded-xl border border-white/10 hover:border-cyan-500/30 cursor-pointer transition">
                        <input type="checkbox" value="${sub.id}" class="w-4 h-4 rounded border-white/20 bg-white/10 text-cyan-500 focus:ring-cyan-500/30">
                        <span class="text-xs font-medium text-slate-300">${sub.name}</span>
                    </label>
                `).join('');
            }
        }
    } catch (error) {
        console.error('[setup] Error refreshing subscriptions:', error);
        if (typeof showToast === "function") {
            showToast("Failed to refresh subscriptions.", "error");
        }
    }
};

window.checkAuth = async () => {
    try {
        const response = await fetch('/api/settings/auth');
        
        if (!response.ok) {
            console.warn('[setup] Auth check endpoint returned non-OK status:', response.status);
            return;
        }
        
        const data = await response.json();
        if (data.status === 'success') {
            const pulse = document.getElementById("auth-pulse");
            if (pulse) {
                if (data.authenticated) {
                    pulse.className = "w-3 h-3 rounded-full bg-cyan-400 shadow-[0_0_15px_rgba(0,242,255,0.6)] animate-pulse";
                } else {
                    pulse.className = "w-3 h-3 rounded-full bg-rose-500 shadow-[0_0_15px_rgba(244,63,94,0.6)] animate-pulse";
                }
            }
        }
    } catch (error) {
        console.error('[setup] Auth check failed:', error);
    }
};
