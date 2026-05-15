let vaultUnlocked = false;

async function refreshVaultStatus() {
    try {
        const res = await fetch("/api/vault/status");
        const data = await res.json();
        vaultUnlocked = Boolean(data.unlocked);
        renderVaultState(Boolean(data.configured), vaultUnlocked);
        if (vaultUnlocked) {
            await loadVaultEntries();
        }
    } catch {
        renderVaultState(false, false);
    }
}

function renderVaultState(configured, unlocked) {
    const setupBlock = document.getElementById("vault-setup-block");
    const unlockBlock = document.getElementById("vault-unlock-block");
    const contentBlock = document.getElementById("vault-content-block");

    if (!configured) {
        setupBlock?.classList.remove("hidden");
        unlockBlock?.classList.add("hidden");
        contentBlock?.classList.add("hidden");
        return;
    }

    setupBlock?.classList.add("hidden");
    if (unlocked) {
        unlockBlock?.classList.add("hidden");
        contentBlock?.classList.remove("hidden");
    } else {
        unlockBlock?.classList.remove("hidden");
        contentBlock?.classList.add("hidden");
    }
}

async function setupVault() {
    const passcode = document.getElementById("vault-setup-passcode")?.value || "";
    const confirm = document.getElementById("vault-setup-confirm")?.value || "";

    try {
        const res = await fetch("/api/vault/setup", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ passcode, confirm }),
        });
        const data = await res.json();
        if (data.status !== "success") {
            throw new Error(data.message || "Failed to create vault");
        }
        if (typeof showToast === "function") {
            showToast(data.message, "success");
        }
        await refreshVaultStatus();
    } catch (error) {
        if (typeof showToast === "function") {
            showToast(error.message, "error");
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
        if (typeof showToast === "function") {
            showToast(data.message, "success");
        }
        document.getElementById("vault-unlock-passcode").value = "";
        await refreshVaultStatus();
    } catch (error) {
        if (typeof showToast === "function") {
            showToast(error.message, "error");
        }
    }
}

async function lockVault() {
    await fetch("/api/vault/lock", { method: "POST" });
    vaultUnlocked = false;
    await refreshVaultStatus();
    if (typeof showToast === "function") {
        showToast("Vault locked.", "success");
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
                    <p class="text-[9px] uppercase text-slate-500 mt-1">${entry.entry_type}</p>
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
        if (typeof showToast === "function") {
            showToast(data.message, "success");
        }
        await loadVaultEntries();
    } catch (error) {
        if (typeof showToast === "function") {
            showToast(error.message, "error");
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
        alert(`${entry.label}\n\n${details}`);
    } catch (error) {
        if (typeof showToast === "function") {
            showToast(error.message, "error");
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
        if (typeof showToast === "function") {
            showToast(data.message, "success");
        }
        await loadVaultEntries();
    } catch (error) {
        if (typeof showToast === "function") {
            showToast(error.message, "error");
        }
    }
}

document.addEventListener("DOMContentLoaded", () => {
    refreshVaultStatus();
    const params = new URLSearchParams(window.location.search);
    if (params.get("tab") === "vault" && typeof showTab === "function") {
        showTab("vault");
    }
});
