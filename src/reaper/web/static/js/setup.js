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
        if (typeof showToast === "function") {
            showToast("Unable to switch provider context.", "error");
        } else {
            notify("Unable to switch provider context.", "danger");
        }
    }
}

async function connectInfrastructure() {
    const payload = {
        subscriptionId: document.getElementById("subId").value,
        tenantId: document.getElementById("tenantId").value,
        clientId: document.getElementById("clientId").value,
        clientSecret: document.getElementById("clientSecret").value,
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

// Sidebar dynamic highlighting
function initializeSidebarHighlighting() {
    const currentPath = window.location.pathname;
    const navLinks = document.querySelectorAll('#sidebar a');
    
    navLinks.forEach(link => {
        const href = link.getAttribute('href');
        const isActive = (href === currentPath) || (currentPath === '/' && href === '/');
        
        if (isActive) {
            // Apply active styles
            link.classList.remove('text-gray-400', 'hover:bg-white/10');
            link.classList.add('bg-cyan-500/10', 'text-cyan-400', 'border-l-2', 'border-cyan-400');
            
            // Highlight the icon specifically if needed
            const icon = link.querySelector('.sidebar-icon');
            if (icon) {
                icon.classList.add('text-cyan-400');
            }
        } else {
            // Ensure non-active styles
            link.classList.add('text-gray-400', 'hover:bg-white/10');
            link.classList.remove('bg-cyan-500/10', 'text-cyan-400', 'border-l-2', 'border-cyan-400', 'bg-white/10');
        }
    });
}

document.addEventListener('DOMContentLoaded', initializeSidebarHighlighting);
