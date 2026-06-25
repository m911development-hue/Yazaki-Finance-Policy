// ═══════════════════════════════════════════════════════════════════════════
// Yazaki Finance Policy Assistant — UI Module
// Handles: mobile sidebar toggling
// ═══════════════════════════════════════════════════════════════════════════

const UIModule = {
    // ── DOM References ────────────────────────────────────────────────────
    sidebar: null,
    overlay: null,

    // ── Initialization ────────────────────────────────────────────────────
    init() {
        this.sidebar      = document.querySelector('.sidebar');
        this.overlay      = document.getElementById('sidebarOverlay');

        this.setupMobileMenu();
    },

    // ══════════════════════════════════════════════════════════════════════
    //  MOBILE SIDEBAR
    // ══════════════════════════════════════════════════════════════════════

    setupMobileMenu() {
        const menuBtn  = document.querySelector('.mobile-menu-btn');
        const closeBtn = document.querySelector('.sidebar-close-btn');

        if (menuBtn) {
            menuBtn.addEventListener('click', () => this.toggleSidebar());
        }
        if (closeBtn) {
            closeBtn.addEventListener('click', () => this.closeSidebar());
        }
        if (this.overlay) {
            this.overlay.addEventListener('click', () => this.closeSidebar());
        }

        // Close on Escape key
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && this.sidebar.classList.contains('open')) {
                this.closeSidebar();
            }
        });
    },

    toggleSidebar() {
        this.sidebar.classList.toggle('open');
        this.overlay.classList.toggle('visible');
    },

    closeSidebar() {
        this.sidebar.classList.remove('open');
        this.overlay.classList.remove('visible');
    },
};
