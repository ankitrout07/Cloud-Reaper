// Mapping notify to showToast for consistency with existing UI
function notify(message, type) {
    if (typeof showToast === "function") {
        showToast(message, type === "danger" ? "error" : "success");
    } else {
        console.log(`Notification (${type}): ${message}`);
    }
}

let validationTimeout;

function triggerValidation() {
    const subId = document.getElementById('setup_sub_id').value;
    const spinner = document.getElementById('validation-spinner');
    
    if (subId.length > 30) { // Typical UUID length is 36
        spinner.classList.remove('hidden');
        
        clearTimeout(validationTimeout);
        validationTimeout = setTimeout(async () => {
            try {
                const res = await fetch('/api/auth/status');
                const data = await res.json();
                
                if (data.status === "healthy") {
                    notify("Azure Session Active", "success");
                } else {
                    notify("Azure Session Missing - Please run 'az login'", "danger");
                }
            } catch (e) {
                console.error("Validation failed", e);
            } finally {
                spinner.classList.add('hidden');
            }
        }, 1000);
    } else {
        spinner.classList.add('hidden');
    }
}

async function saveInitialSetup() {
    const subIdInput = document.getElementById('setup_sub_id');
    const subId = subIdInput.value;

    if (!subId || subId.length < 10) {
        notify("Please enter a valid Azure Subscription ID", "danger");
        return;
    }

    // Visual feedback: Loading state
    const btn = document.getElementById('setup-btn');
    const originalText = btn.innerText;
    btn.innerText = "INITIALIZING ENGINE...";
    btn.disabled = true;

    try {
        const response = await fetch('/api/settings/update', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                action: 'initial_setup',
                value: subId
            })
        });

        const data = await response.json();

        if (data.status === "success") {
            notify("Connection Established!", "success");
            // Reload the page to clear the setup flag and see the dashboard
            setTimeout(() => { window.location.href = "/"; }, 1500);
        } else {
            throw new Error(data.msg);
        }
    } catch (err) {
        notify("Setup Failed: " + err.message, "danger");
        btn.innerText = originalText;
        btn.disabled = false;
    }
}

function toggleFieldVisibility(inputId, iconId) {
    const input = document.getElementById(inputId);
    const icon = document.getElementById(iconId);
    
    if (input.type === "password") {
        input.type = "text";
        icon.classList.replace('fa-eye', 'fa-eye-slash');
    } else {
        input.type = "password";
        icon.classList.replace('fa-eye-slash', 'fa-eye');
    }
}

async function connectInfrastructure() {
    const payload = {
        subscriptionId: document.getElementById('subId').value,
        tenantId: document.getElementById('tenantId').value,
        clientId: document.getElementById('clientId').value,
        clientSecret: document.getElementById('clientSecret').value
    };

    const response = await fetch('/api/settings/sync', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    });

    if (response.ok) {
        if (typeof showToast === "function") {
            showToast("Success: .env synchronized!", "success");
        } else {
            notify("Success: .env synchronized!", "success");
        }
        // Trigger the status light to turn Green/Cyan
        const pulse = document.getElementById('auth-pulse');
        if (pulse) {
            pulse.className = "w-3 h-3 rounded-full bg-cyan-400 shadow-[0_0_15px_rgba(0,242,255,0.6)] animate-pulse";
        }
        
        // Refresh auth status
        if (typeof checkAuth === "function") checkAuth();
    } else {
        const data = await response.json();
        const msg = data.message || "Sync failed";
        if (typeof showToast === "function") {
            showToast(msg, "error");
        } else {
            notify(msg, "danger");
        }
    }
}
