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
