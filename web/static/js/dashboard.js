// Toast notifications
function showToast(message, type = "success") {
    const container = document.getElementById("toast-container");
    if (!container) return;

    const toast = document.createElement("div");
    const bgClass = type === "success" ? "bg-emerald-600" : (type === "error" ? "bg-red-600" : "bg-blue-600");
    toast.className = `${bgClass} text-white px-4 py-3 rounded-lg shadow-xl text-sm font-medium flex items-center gap-2 transform transition-all duration-300 translate-y-2 opacity-0`;
    toast.innerHTML = `<span>${message}</span>`;

    container.appendChild(toast);
    requestAnimationFrame(() => {
        toast.classList.remove("translate-y-2", "opacity-0");
    });

    setTimeout(() => {
        toast.classList.add("opacity-0", "translate-y-2");
        setTimeout(() => toast.remove(), 300);
    }, 3500);
}

// Generic API post helper
async function postAPI(url, data) {
    try {
        const resp = await fetch(url, {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify(data)
        });
        const json = await resp.json();
        if (!resp.ok) {
            throw new Error(json.detail || "Request failed");
        }
        return json;
    } catch (err) {
        showToast(err.message, "error");
        throw err;
    }
}

// Banned words tag manager
let bannedWords = [];

function initTagInput(initialWords = []) {
    bannedWords = [...initialWords];
    renderTags();

    const input = document.getElementById("banned-words-input");
    if (!input) return;

    input.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === ",") {
            e.preventDefault();
            const word = input.value.trim().toLowerCase();
            if (word && !bannedWords.includes(word)) {
                bannedWords.push(word);
                renderTags();
                input.value = "";
            }
        }
    });
}

function renderTags() {
    const tagList = document.getElementById("banned-words-tags");
    if (!tagList) return;
    tagList.innerHTML = "";

    bannedWords.forEach((word, idx) => {
        const tag = document.createElement("span");
        tag.className = "inline-flex items-center gap-1.5 px-2.5 py-1 rounded bg-[#1e1f22] text-xs font-semibold text-gray-300 border border-[#35373c]";
        tag.innerHTML = `
            <span>${word}</span>
            <button type="button" onclick="removeTag(${idx})" class="text-gray-400 hover:text-red-400 font-bold">&times;</button>
        `;
        tagList.appendChild(tag);
    });
}

function removeTag(idx) {
    bannedWords.splice(idx, 1);
    renderTags();
}

// Tab navigation
function showTab(tabId) {
    const tabs = document.querySelectorAll(".tab-content");
    const btns = document.querySelectorAll(".tab-btn");

    tabs.forEach(t => t.classList.add("hidden"));
    btns.forEach(b => {
        b.classList.remove("text-white", "bg-[#35373c]");
        b.classList.add("text-gray-400");
    });

    const activeTab = document.getElementById(`tab-${tabId}`);
    const activeBtn = document.getElementById(`btn-${tabId}`);
    if (activeTab) activeTab.classList.remove("hidden");
    if (activeBtn) {
        activeBtn.classList.add("text-white", "bg-[#35373c]");
        activeBtn.classList.remove("text-gray-400");
    }
}

// Lockdown toggle
async function toggleLockdown(guildId, currentState) {
    const nextState = !currentState;
    const confirmMsg = nextState 
        ? "Are you sure you want to trigger EMERGENCY LOCKDOWN? All public channels will be locked immediately."
        : "Restore channels and lift lockdown?";
    
    if (!confirm(confirmMsg)) return;

    try {
        const res = await postAPI(`/api/guild/${guildId}/lockdown`, { state: nextState });
        showToast(nextState ? "Lockdown Activated!" : "Lockdown Lifted!", "success");
        setTimeout(() => location.reload(), 1000);
    } catch (e) {}
}

// Whitelist actions
async function addWhitelist(guildId) {
    const input = document.getElementById("whitelist-target-id");
    const reasonInput = document.getElementById("whitelist-reason");
    const targetId = parseInt(input.value);
    if (!targetId) {
        showToast("Enter a valid numeric ID", "error");
        return;
    }
    const reason = reasonInput ? reasonInput.value.trim() : "Dashboard addition";

    try {
        await postAPI(`/api/guild/${guildId}/whitelist`, {
            action: "add",
            target_id: targetId,
            reason: reason
        });
        showToast("Whitelisted successfully!", "success");
        setTimeout(() => location.reload(), 800);
    } catch (e) {}
}

async function removeWhitelist(guildId, targetId) {
    if (!confirm(`Remove ID ${targetId} from whitelist?`)) return;
    try {
        await postAPI(`/api/guild/${guildId}/whitelist`, {
            action: "remove",
            target_id: targetId
        });
        showToast("Removed from whitelist", "success");
        setTimeout(() => location.reload(), 800);
    } catch (e) {}
}

// Warning actions
async function deleteWarning(guildId, warnId) {
    if (!confirm(`Delete warning #${warnId}?`)) return;
    try {
        await postAPI(`/api/guild/${guildId}/warnings/delete`, { warning_id: warnId });
        showToast("Warning revoked", "success");
        const row = document.getElementById(`warning-row-${warnId}`);
        if (row) row.remove();
    } catch (e) {}
}
