document.addEventListener("DOMContentLoaded", () => {
    if (document.body.dataset.authRequired !== "true") {
        return;
    }

    GrowFlow.requireAuth();

    const savedTheme = localStorage.getItem("growflowTheme");
    if (savedTheme === "light") {
        document.getElementById("app-body")?.classList.add("theme-light");
        document.getElementById("app-background")?.classList.add("theme-light");
    }

    const sidebar = document.getElementById("shell-sidebar");
    const backdrop = document.getElementById("shell-drawer-backdrop");
    const openButton = document.getElementById("shell-drawer-open");
    const closeButton = document.getElementById("shell-drawer-close");

    function closeDrawer() {
        sidebar?.classList.remove("is-open");
        backdrop?.classList.add("hidden");
        document.body.classList.remove("overflow-hidden");
        openButton?.setAttribute("aria-expanded", "false");
    }

    function openDrawer() {
        sidebar?.classList.add("is-open");
        backdrop?.classList.remove("hidden");
        document.body.classList.add("overflow-hidden");
        openButton?.setAttribute("aria-expanded", "true");
    }

    openButton?.setAttribute("aria-controls", "shell-sidebar");
    openButton?.setAttribute("aria-expanded", "false");
    openButton?.addEventListener("click", () => {
        if (sidebar?.classList.contains("is-open")) {
            closeDrawer();
        } else {
            openDrawer();
        }
    });
    closeButton?.addEventListener("click", closeDrawer);
    backdrop?.addEventListener("click", closeDrawer);
    sidebar?.querySelectorAll("a[href]").forEach((link) => {
        link.addEventListener("click", () => {
            if (window.matchMedia("(max-width: 1023px)").matches) {
                closeDrawer();
            }
        });
    });
    window.addEventListener("resize", () => {
        if (window.matchMedia("(min-width: 1024px)").matches) {
            closeDrawer();
        }
    });
    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
            closeDrawer();
        }
    });

    const user = GrowFlow.getUser();
    const nameNode = document.getElementById("shell-user-name");
    const emailNode = document.getElementById("shell-user-email");
    if (user) {
        if (nameNode) {
            nameNode.textContent = user.name || "GrowFlow User";
        }
        if (emailNode) {
            emailNode.textContent = user.email || "JWT-secured access";
        }
    }

    const bannerNode = document.getElementById("shell-subscription-banner");

    function renderSubscriptionBanner(payload) {
        if (!bannerNode) {
            return;
        }

        const state = payload?.subscription || {};
        const current = state.current || {};
        const access = state.access || {};
        const quote = state.quote || {};
        const paymentGateways = state.payment_gateways || {};
        const premiumActive = Boolean(access.premium_active);

        if (premiumActive) {
            bannerNode.classList.add("hidden");
            bannerNode.innerHTML = "";
            return;
        }

        const trialDays = current.trial_days_left;
        const amountDue = Number(quote.amount_due ?? current.amount_due ?? 200);
        const trialText = current.status === "expired" || access.trial_expired
            ? "Trial expired"
            : trialDays !== null && trialDays !== undefined
                ? `${trialDays} day(s) left in the trial`
                : "Trial status available";
        const paymentText = current.payment_pending
            ? "Payment pending"
            : paymentGateways.default_provider === "razorpay"
                ? "Razorpay checkout ready"
                : "Demo payment mode";

        bannerNode.className = "mt-6 rounded-3xl border border-glow/15 bg-glow/10 p-5 text-white shadow-neon";
        bannerNode.innerHTML = `
            <div class="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                <div>
                    <p class="section-kicker">Subscription</p>
                    <h3 class="text-2xl font-semibold">${current.status === "expired" ? "Trial expired" : "Keep premium access active"}</h3>
                    <p class="mt-2 text-sm text-white/72">${trialText}. ${paymentText}. ${state.notice || "Upgrade to Pro for live WhatsApp, AI, and export tools."}</p>
                </div>
                <div class="flex flex-wrap items-center gap-3">
                    <span class="mini-chip">${paymentGateways.default_provider === "razorpay" ? "Razorpay" : "Demo checkout"}</span>
                    <span class="mini-chip">Rs ${amountDue}</span>
                    <button type="button" id="shell-upgrade-button" class="action-btn bg-glow text-ink">Upgrade now</button>
                </div>
            </div>
        `;

        const upgradeButton = document.getElementById("shell-upgrade-button");
        upgradeButton?.addEventListener("click", () => GrowFlow.showUpgradePrompt(payload));
    }

    async function loadSubscriptionState() {
        try {
            const response = await GrowFlow.api("/api/subscription/trial-check");
            GrowFlow.setSubscriptionState(response);
            renderSubscriptionBanner(response);
            if (response.subscription?.upgrade_required) {
                GrowFlow.showUpgradePrompt(response);
            }
        } catch {
            if (bannerNode) {
                bannerNode.classList.add("hidden");
            }
        }
    }

    document.getElementById("logout-button")?.addEventListener("click", () => {
        GrowFlow.clearSession();
        window.location.href = "/auth";
    });

    loadSubscriptionState().catch(() => {});
});
