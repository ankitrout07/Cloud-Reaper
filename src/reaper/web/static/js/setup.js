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

function toggleSecretVisibility() {
    const secretInput = document.getElementById('clientSecret');
    const icon = document.getElementById('toggleIcon');
    
    if (secretInput.type === "password") {
        secretInput.type = "text";
        icon.classList.replace('fa-eye', 'fa-eye-slash');
    } else {
        secretInput.type = "password";
        icon.classList.replace('fa-eye-slash', 'fa-eye');
    }
}
