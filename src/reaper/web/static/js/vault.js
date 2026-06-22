let vaultUnlocked = false;

async function refreshVaultStatus() {
    console.log("Refreshing vault status...");
    try {
        const res = await fetch("/api/vault/status");
        const data = await res.json();
        console.log("Vault status response:", data);
        vaultUnlocked = Boolean(data.unlocked);
        renderVaultState(Boolean(data.configured), vaultUnlocked);
        if (vaultUnlocked) {
            await loadVaultEntries();
        }
    } catch (error) {
        console.error("Failed to refresh vault status:", error);
        renderVaultState(false, false);
    }
}

function renderVaultState(configured, unlocked) {
    console.log("Rendering vault state:", { configured, unlocked });
    const setupBlock = document.getElementById("vault-setup-block");
    const unlockBlock = document.getElementById("vault-unlock-block");
    const contentBlock = document.getElementById("vault-content-block");

    if (!configured) {
        setupBlock?.classList.remove("hidden");
        unlockBlock?.classList.add("hidden");
        contentBlock?.classList.add("hidden");
        console.log("Vault not configured - showing setup block");
        return;
    }

    setupBlock?.classList.add("hidden");
    if (unlocked) {
        unlockBlock?.classList.add("hidden");
        contentBlock?.classList.remove("hidden");
        console.log("Vault unlocked - showing content block");
    } else {
        unlockBlock?.classList.remove("hidden");
        contentBlock?.classList.add("hidden");
        console.log("Vault locked - showing unlock block");
    }
}

function toggleVaultSetupPlaceholder() {
    const type = document.getElementById("vault-setup-type")?.value || "password";
    const tip = document.getElementById("vault-setup-tip");
    const passcode = document.getElementById("vault-setup-passcode");
    const confirm = document.getElementById("vault-setup-confirm");

    if (type === "pin") {
        if (tip) tip.innerText = "Create your vault passcode (exactly 4 characters/digits).";
        if (passcode) passcode.placeholder = "4-digit PIN";
        if (confirm) confirm.placeholder = "Confirm 4-digit PIN";
    } else {
        if (tip) tip.innerText = "Create your vault passcode (minimum 8 characters).";
        if (passcode) passcode.placeholder = "Vault passcode";
        if (confirm) confirm.placeholder = "Confirm passcode";
    }
}

async function setupVault() {
    const passcode = document.getElementById("vault-setup-passcode")?.value || "";
    const confirm = document.getElementById("vault-setup-confirm")?.value || "";
    const passcodeType = document.getElementById("vault-setup-type")?.value || "password";

    try {
        const res = await fetch("/api/vault/setup", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ passcode, confirm, passcode_type: passcodeType }),
        });
        const data = await res.json();
        if (data.status !== "success") {
            throw new Error(data.message || "Failed to create vault");
        }
        if (typeof notify === "function") {
            notify(data.message, "success");
        } else if (typeof showToast === "function") {
            showToast(data.message, "success");
        } else {
            alert(data.message);
        }

        // Clear setup fields
        if (document.getElementById("vault-setup-passcode")) document.getElementById("vault-setup-passcode").value = "";
        if (document.getElementById("vault-setup-confirm")) document.getElementById("vault-setup-confirm").value = "";

        await refreshVaultStatus();
    } catch (error) {
        if (typeof notify === "function") {
            notify(error.message, "error");
        } else if (typeof showToast === "function") {
            showToast(error.message, "error");
        } else {
            alert(error.message);
        }
    }
}

async function resetVault() {
    if (!confirm("WARNING: Are you absolutely sure you want to reset the vault?\n\nThis action will PERMANENTLY erase all stored passwords and secrets. This cannot be undone!")) {
        return;
    }

    try {
        const res = await fetch("/api/vault/reset", {
            method: "POST"
        });
        const data = await res.json();
        if (data.status !== "success") {
            throw new Error(data.message || "Failed to reset vault");
        }
        if (typeof notify === "function") {
            notify(data.message, "success");
        } else if (typeof showToast === "function") {
            showToast(data.message, "success");
        } else {
            alert(data.message);
        }

        // Clear all fields
        if (document.getElementById("vault-unlock-passcode")) document.getElementById("vault-unlock-passcode").value = "";

        await refreshVaultStatus();
    } catch (error) {
        if (typeof notify === "function") {
            notify(error.message, "error");
        } else if (typeof showToast === "function") {
            showToast(error.message, "error");
        } else {
            alert(error.message);
        }
    }
}

async function unlockVault() {
    const passcode = document.getElementById("vault-unlock-passcode")?.value || "";

    try {
        const res = await fetch("/api/vault/unlock", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ passcode }),
        });
        const data = await res.json();
        if (data.status !== "success") {
            throw new Error(data.message || "Failed to unlock vault");
        }
        if (typeof notify === "function") {
            notify(data.message, "success");
        } else if (typeof showToast === "function") {
            showToast(data.message, "success");
        } else {
            alert(data.message);
        }
        document.getElementById("vault-unlock-passcode").value = "";
        await refreshVaultStatus();
    } catch (error) {
        if (typeof notify === "function") {
            notify(error.message, "error");
        } else if (typeof showToast === "function") {
            showToast(error.message, "error");
        } else {
            alert(error.message);
        }
    }
}

async function lockVault() {
    await fetch("/api/vault/lock", { method: "POST" });
    vaultUnlocked = false;
    await refreshVaultStatus();
    if (typeof notify === "function") {
        notify("Vault locked.", "success");
    } else if (typeof showToast === "function") {
        showToast("Vault locked.", "success");
    } else {
        alert("Vault locked.");
    }
}

async function loadVaultEntries() {
    const list = document.getElementById("vault-entries-list");
    if (!list) {
        return;
    }

    try {
        const res = await fetch("/api/vault/entries");
        const data = await res.json();
        if (data.status !== "success") {
            throw new Error(data.message || "Unable to load entries");
        }

        const entries = data.entries || [];
        if (!entries.length) {
            list.innerHTML = '<p class="text-[10px] text-slate-500 italic">No entries yet. Add credentials or passcodes below.</p>';
            return;
        }

        list.innerHTML = entries
            .map(
                (entry) => `
            <div class="vault-entry-row flex items-center justify-between p-4 bg-black/30 border border-white/5 rounded-2xl" data-id="${entry.id}">
                <div>
                    <p class="text-xs font-bold text-white">${entry.label}</p>
                    <p class="text-[9px] uppercase text-slate-500 mt-1">${entry.entry_type.replace('_', ' ')}</p>
                </div>
                <div class="flex gap-2">
                    <button type="button" onclick="revealVaultEntry(${entry.id})" class="px-3 py-2 text-[9px] font-black uppercase bg-cyan-500/10 text-cyan-400 rounded-lg border border-cyan-500/20">Reveal</button>
                    <button type="button" onclick="deleteVaultEntry(${entry.id})" class="px-3 py-2 text-[9px] font-black uppercase bg-rose-500/10 text-rose-400 rounded-lg border border-rose-500/20">Delete</button>
                </div>
            </div>`
            )
            .join("");
    } catch (error) {
        list.innerHTML = `<p class="text-[10px] text-rose-400">${error.message}</p>`;
    }
}

async function saveVaultEntry() {
    const label = document.getElementById("vault-entry-label")?.value.trim();
    const entryType = document.getElementById("vault-entry-type")?.value || "credential";
    const username = document.getElementById("vault-entry-username")?.value.trim();
    const value = document.getElementById("vault-entry-value")?.value.trim();
    const notes = document.getElementById("vault-entry-notes")?.value.trim();

    try {
        const res = await fetch("/api/vault/entries", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ label, entry_type: entryType, username, value, notes }),
        });
        const data = await res.json();
        if (data.status !== "success") {
            throw new Error(data.message || "Failed to save entry");
        }
        document.getElementById("vault-entry-label").value = "";
        document.getElementById("vault-entry-username").value = "";
        document.getElementById("vault-entry-value").value = "";
        document.getElementById("vault-entry-notes").value = "";
        if (typeof notify === "function") {
            notify(data.message, "success");
        } else if (typeof showToast === "function") {
            showToast(data.message, "success");
        } else {
            alert(data.message);
        }
        await loadVaultEntries();
    } catch (error) {
        if (typeof notify === "function") {
            notify(error.message, "error");
        } else if (typeof showToast === "function") {
            showToast(error.message, "error");
        } else {
            alert(error.message);
        }
    }
}

async function revealVaultEntry(entryId) {
    try {
        const res = await fetch(`/api/vault/entries/${entryId}`);
        const data = await res.json();
        if (data.status !== "success") {
            throw new Error(data.message || "Unable to reveal entry");
        }
        const entry = data.entry;
        const details = [
            entry.username ? `User: ${entry.username}` : null,
            `Secret: ${entry.value}`,
            entry.notes ? `Notes: ${entry.notes}` : null,
        ]
            .filter(Boolean)
            .join("\n");
        alert(`${entry.label} (${entry.entry_type.replace('_', ' ').toUpperCase()})\n\n${details}`);
    } catch (error) {
        if (typeof notify === "function") {
            notify(error.message, "error");
        } else if (typeof showToast === "function") {
            showToast(error.message, "error");
        } else {
            alert(error.message);
        }
    }
}

async function deleteVaultEntry(entryId) {
    if (!confirm("Delete this vault entry?")) {
        return;
    }
    try {
        const res = await fetch(`/api/vault/entries/${entryId}`, { method: "DELETE" });
        const data = await res.json();
        if (data.status !== "success") {
            throw new Error(data.message || "Failed to delete entry");
        }
        if (typeof notify === "function") {
            notify(data.message, "success");
        } else if (typeof showToast === "function") {
            showToast(data.message, "success");
        } else {
            alert(data.message);
        }
        await loadVaultEntries();
    } catch (error) {
        if (typeof notify === "function") {
            notify(error.message, "error");
        } else if (typeof showToast === "function") {
            showToast(error.message, "error");
        } else {
            alert(error.message);
        }
    }
}

document.addEventListener("DOMContentLoaded", () => {
    refreshVaultStatus();
    const params = new URLSearchParams(window.location.search);
    if (params.get("tab") === "vault") {
        // Try the settings-specific function first, then fall back to generic showTab
        if (typeof showSettingsTab === "function") {
            showSettingsTab("vault");
        } else if (typeof showTab === "function") {
            showTab("vault");
        }
    }
});
