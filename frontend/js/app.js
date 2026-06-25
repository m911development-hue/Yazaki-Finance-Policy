// ═══════════════════════════════════════════════════════════════════════════
// Yazaki Finance Policy Assistant — Main Application Module
// Orchestrates: state, API client, toast system, module initialization
// ═══════════════════════════════════════════════════════════════════════════

// ── Global Application State ─────────────────────────────────────────────
const KaizenApp = {
    conversationHistory: [],
    isRecording: false,
    currentAudio: null,
    lastAudioBlob: null,
    isProcessing: false,
    baseUrl: '', // auto-detected from window.location
};

// ══════════════════════════════════════════════════════════════════════════
//  API CLIENT
// ══════════════════════════════════════════════════════════════════════════

/**
 * Lightweight fetch wrapper with standardised error handling.
 * Throws human-readable Error on failure.
 */
async function apiRequest(url, options = {}) {
    try {
        const response = await fetch(KaizenApp.baseUrl + url, options);

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(
                errorData.detail ||
                errorData.error ||
                `Request failed (${response.status})`
            );
        }

        return response;
    } catch (error) {
        // Network-level failures (DNS, CORS, offline, etc.)
        if (error.name === 'TypeError' && error.message.includes('fetch')) {
            throw new Error('Network error. Please check your connection.');
        }
        throw error;
    }
}

// ══════════════════════════════════════════════════════════════════════════
//  TOAST NOTIFICATION SYSTEM
// ══════════════════════════════════════════════════════════════════════════

/**
 * Show a toast notification.
 * @param {string}  message  - Notification text
 * @param {'info'|'success'|'error'} type - Visual style
 * @param {number}  duration - Auto-dismiss in ms (default 4 000)
 */
function showToast(message, type = 'info', duration = 4000) {
    const container = document.getElementById('toastContainer');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;

    const icons = {
        success:
            '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>',
        error:
            '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="15" y1="9" x2="9" y2="15"></line><line x1="9" y1="9" x2="15" y2="15"></line></svg>',
        info:
            '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>',
    };

    toast.innerHTML = `
        <span class="toast-icon">${icons[type] || icons.info}</span>
        <span class="toast-message">${message}</span>
    `;

    container.appendChild(toast);

    // Auto-dismiss
    setTimeout(() => {
        toast.classList.add('hiding');
        setTimeout(() => toast.remove(), 300);
    }, duration);
}

// ══════════════════════════════════════════════════════════════════════════
//  BOOTSTRAP
// ══════════════════════════════════════════════════════════════════════════

document.addEventListener('DOMContentLoaded', () => {
    // Initialise all modules (order matters: UI → Chat → Voice)
    UIModule.init();
    ChatModule.init();
    VoiceModule.init();

    console.log(
        '%c🚀 Yazaki Finance Policy Assistant initialised successfully',
        'color: #6366f1; font-weight: bold; font-size: 14px;'
    );
});
