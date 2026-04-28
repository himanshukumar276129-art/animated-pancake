const GrowFlow = (() => {
    const tokenKey = "growflowToken";
    const userKey = "growflowUser";
    const responseCacheKey = "growflowResponseCache";
    let subscriptionState = null;
    let offlineNoticeShown = false;

    function setToast(message, tone = "default") {
        const toast = document.getElementById("toast");
        if (!toast) {
            return;
        }
        toast.textContent = message;
        toast.className = "pointer-events-none fixed right-4 top-4 z-50 min-w-[240px] rounded-2xl border px-4 py-3 text-sm shadow-neon";
        if (tone === "error") {
            toast.classList.add("border-red-400/30", "bg-red-950/90", "text-red-100");
        } else {
            toast.classList.add("border-glow/20", "bg-panel/95", "text-white");
        }
        toast.classList.remove("hidden");
        window.clearTimeout(toast._timer);
        toast._timer = window.setTimeout(() => toast.classList.add("hidden"), 3200);
    }

    function setSubscriptionState(payload) {
        subscriptionState = payload || null;
        return subscriptionState;
    }

    function getSubscriptionState() {
        return subscriptionState;
    }

    function getResponseCache() {
        try {
            return JSON.parse(localStorage.getItem(responseCacheKey) || "{}") || {};
        } catch {
            return {};
        }
    }

    function saveResponseCache(cache) {
        try {
            localStorage.setItem(responseCacheKey, JSON.stringify(cache));
        } catch {
            // Ignore cache write failures.
        }
    }

    function clearResponseCache() {
        try {
            localStorage.removeItem(responseCacheKey);
        } catch {
            // Ignore cache clear failures.
        }
    }

    function buildCacheKey(path, method = "GET") {
        const url = new URL(path, window.location.origin);
        return `${method.toUpperCase()}:${url.pathname}${url.search}`;
    }

    function pruneResponseCache(cache) {
        const entries = Object.entries(cache);
        if (entries.length <= 20) {
            return cache;
        }
        entries.sort((left, right) => Number(left[1]?.cachedAt || 0) - Number(right[1]?.cachedAt || 0));
        while (entries.length > 20) {
            const [key] = entries.shift();
            delete cache[key];
        }
        return cache;
    }

    function cacheApiResponse(cacheKey, payload) {
        const cache = getResponseCache();
        cache[cacheKey] = {
            payload,
            cachedAt: Date.now(),
        };
        saveResponseCache(pruneResponseCache(cache));
    }

    function getCachedApiResponse(cacheKey) {
        const cache = getResponseCache();
        return cache[cacheKey] || null;
    }

    function clearBrowserPageCache() {
        if (window.caches?.keys) {
            window.caches.keys()
                .then((keys) => {
                    keys
                        .filter((key) => key.startsWith("growflow-pages-"))
                        .forEach((key) => {
                            window.caches.delete(key).catch(() => {});
                        });
                })
                .catch(() => {});
        }

        if (navigator.serviceWorker?.controller) {
            navigator.serviceWorker.controller.postMessage({ type: "CLEAR_CACHES" });
        }
    }

    function clearOfflineData() {
        clearResponseCache();
        clearBrowserPageCache();
        offlineNoticeShown = false;
    }

    function resetOfflineNotice() {
        offlineNoticeShown = false;
    }

    function hideUpgradePrompt() {
        const modal = document.getElementById("upgrade-modal");
        if (!modal) {
            return;
        }
        modal.classList.add("hidden");
        modal.classList.remove("flex");
        document.body.classList.remove("overflow-hidden");
    }

    function getUpgradePayload() {
        const root = subscriptionState || {};
        if (root.subscription && root.subscription.current) {
            return {
                current: root.subscription.current || null,
                quote: root.subscription.quote || root.quote || null,
                access: root.subscription.access || root.access || null,
                notice: root.subscription.notice || root.notice || "",
                paymentGateways: root.subscription.payment_gateways || root.payment_gateways || null,
            };
        }
        return {
            current: root.subscription || root.current || null,
            quote: root.quote || null,
            access: root.access || null,
            notice: root.notice || "",
            paymentGateways: root.payment_gateways || null,
        };
    }

    function showUpgradePrompt(payload = null) {
        if (payload) {
            setSubscriptionState(payload);
        }
        const modal = document.getElementById("upgrade-modal");
        if (!modal) {
            return;
        }
        modal.onclick = (event) => {
            if (event.target === modal) {
                hideUpgradePrompt();
            }
        };

        const nodes = {
            title: document.getElementById("upgrade-modal-title"),
            copy: document.getElementById("upgrade-modal-copy"),
            state: document.getElementById("upgrade-modal-state"),
            days: document.getElementById("upgrade-modal-days"),
            amount: document.getElementById("upgrade-modal-amount"),
            discount: document.getElementById("upgrade-modal-discount"),
            promo: document.getElementById("upgrade-modal-promo"),
            note: document.getElementById("upgrade-modal-note"),
            payment: document.getElementById("upgrade-modal-payment"),
            apply: document.getElementById("upgrade-modal-apply"),
        };

        const payloadState = getUpgradePayload();
        const current = payloadState.current || {};
        const quote = payloadState.quote || {};
        const access = payloadState.access || {};
        const paymentGateways = payloadState.paymentGateways || {};
        const currentPlan = current.label || current.plan_code || "Subscription";
        const notice = payloadState.notice || "Upgrade to keep premium growth tools active.";
        const amountDue = Number(quote.amount_due ?? current.amount_due ?? 200);
        const discountPercent = Number(quote.discount_percent ?? current.promo_discount_percent ?? 0);
        const discountAmount = Number(quote.discount_amount ?? current.promo_discount_amount ?? 0);
        const trialDaysLeft = current.trial_days_left;
        const paymentPending = Boolean(current.payment_pending || quote.payment_pending);
        const freeActivation = amountDue <= 0;
        const paymentReference = current.payment_reference || quote.payment_reference || "";
        const hasRazorpay = Boolean(paymentGateways.razorpay_available);
        const hasDemo = Boolean(paymentGateways.demo_available);
        const preferredProvider = paymentPending
            ? (current.payment_provider || paymentGateways.default_provider || "razorpay")
            : (paymentGateways.default_provider || "demo");

        if (nodes.title) {
            nodes.title.textContent = "Upgrade to GrowFlow AI Pro";
        }
        if (nodes.copy) {
            nodes.copy.textContent = freeActivation
                ? "Promo code applied. Activate Pro for free."
                : "Unlock live WhatsApp campaigns, AI tools, automation, and export features for Rs 200/month.";
        }
        if (nodes.state) {
            const parts = [];
            if (current.status) {
                parts.push(`Status: ${current.status}`);
            }
            if (access?.trial_active) {
                parts.push("Trial active");
            }
            if (access?.trial_expired) {
                parts.push("Trial expired");
            }
            if (paymentPending) {
                parts.push("Payment pending");
            }
            if (access?.premium_active) {
                parts.push("Pro active");
            }
            nodes.state.textContent = parts.join(" - ") || currentPlan;
        }
        if (nodes.days) {
            if (trialDaysLeft !== null && trialDaysLeft !== undefined) {
                nodes.days.textContent = `Trial days left: ${trialDaysLeft}`;
            } else if (current.next_renewal_on) {
                nodes.days.textContent = `Next renewal: ${current.next_renewal_on}`;
            } else {
                nodes.days.textContent = "Trial window tracked automatically.";
            }
        }
        if (nodes.amount) {
            nodes.amount.textContent = `Rs ${amountDue || 200}`;
        }
        if (nodes.discount) {
            nodes.discount.textContent = discountPercent
                ? `${discountPercent}% off (Rs ${discountAmount})`
                : "No promo applied";
        }
        if (nodes.promo) {
            nodes.promo.value = quote.promo_code || current.promo_code_used || "";
        }
        if (nodes.note) {
            const parts = [notice];
            if (freeActivation) {
                parts.push("No payment is required.");
            } else {
                if (paymentPending && paymentReference) {
                    parts.push(`Payment link ready: ${paymentReference}`);
                }
                if (hasRazorpay) {
                    parts.push("Razorpay checkout is available.");
                } else if (hasDemo) {
                    parts.push("Demo payment mode is available in this environment.");
                }
            }
            nodes.note.textContent = parts.join(" ");
        }
        if (nodes.payment) {
            nodes.payment.textContent = paymentPending
                ? "Verify payment"
                : freeActivation
                    ? "Activate for free"
                    : preferredProvider === "razorpay"
                        ? "Pay with Razorpay"
                        : "Upgrade now";
            nodes.payment.dataset.provider = freeActivation ? "promo" : preferredProvider;
            nodes.payment.dataset.paymentReference = paymentReference;
        }
        if (nodes.apply) {
            nodes.apply.textContent = "Apply promo";
        }

        const closeButton = document.getElementById("upgrade-modal-close");
        const closeSecondaryButton = document.getElementById("upgrade-modal-close-secondary");
        if (closeButton) {
            closeButton.onclick = hideUpgradePrompt;
        }
        if (closeSecondaryButton) {
            closeSecondaryButton.onclick = hideUpgradePrompt;
        }
        if (nodes.apply) {
            nodes.apply.onclick = async () => {
                const promoCode = (nodes.promo?.value || "").trim();
                if (!promoCode) {
                    setToast("Enter a promo code first.", "error");
                    return;
                }
                try {
                    const response = await api("/api/subscription/apply-promo", {
                        method: "POST",
                        body: JSON.stringify({ promo_code: promoCode }),
                    });
                    setSubscriptionState(response);
                    showUpgradePrompt(response);
                    setToast(response.message);
                } catch (error) {
                    setToast(error.message, "error");
                }
            };
        }
        if (nodes.payment) {
            nodes.payment.onclick = async () => {
                const activePayload = getUpgradePayload();
                const activeQuote = activePayload.quote || {};
                const activeGateways = activePayload.paymentGateways || {};
                const promoCode = (nodes.promo?.value || "").trim();
                const body = {
                    provider: nodes.payment.dataset.provider || activeGateways.default_provider || "demo",
                };
                if (promoCode) {
                    body.promo_code = promoCode;
                } else if (activeQuote.promo_code) {
                    body.promo_code = activeQuote.promo_code;
                }
                if (nodes.payment.dataset.paymentReference) {
                    body.payment_link_id = nodes.payment.dataset.paymentReference;
                }

                try {
                    const response = await api("/api/subscription/payment", {
                        method: "POST",
                        body: JSON.stringify(body),
                    });
                    setSubscriptionState(response);
                    if (response.checkout?.short_url) {
                        window.open(response.checkout.short_url, "_blank", "noopener,noreferrer");
                    }
                    if (response.subscription?.plan_code && !response.subscription.current) {
                        hideUpgradePrompt();
                        setToast(response.message);
                        window.location.reload();
                        return;
                    }
                    showUpgradePrompt(response);
                    setToast(response.message);
                } catch (error) {
                    setToast(error.message, "error");
                }
            };
        }

        modal.classList.remove("hidden");
        modal.classList.add("flex");
        document.body.classList.add("overflow-hidden");
    }

    async function api(path, options = {}) {
        const method = String(options.method || "GET").toUpperCase();
        const cacheKey = method === "GET" ? buildCacheKey(path, method) : null;
        const token = localStorage.getItem(tokenKey);
        const headers = {
            "Content-Type": "application/json",
            ...(options.headers || {}),
        };
        if (token) {
            headers.Authorization = `Bearer ${token}`;
        }

        try {
            const response = await fetch(path, {
                ...options,
                headers,
            });
            const data = await response.json().catch(() => ({}));
            if (data.upgrade_required) {
                setSubscriptionState(data);
                showUpgradePrompt(data);
            }
            if (!response.ok || data.success === false) {
                const responseError = new Error(data.message || "Request failed.");
                responseError.isResponseError = true;
                throw responseError;
            }
            if (method === "GET" && cacheKey) {
                cacheApiResponse(cacheKey, data);
            }
            return data;
        } catch (error) {
            if (method === "GET" && cacheKey && !error.isResponseError) {
                const cached = getCachedApiResponse(cacheKey);
                if (cached?.payload) {
                    if (cached.payload.upgrade_required || cached.payload.subscription_upgrade_required || cached.payload.subscription?.upgrade_required) {
                        setSubscriptionState(cached.payload);
                        showUpgradePrompt(cached.payload);
                    }
                    if (!offlineNoticeShown) {
                        setToast("Offline basic mode active. Showing cached data.", "error");
                        offlineNoticeShown = true;
                    }
                    return cached.payload;
                }
            }
            if (!navigator.onLine && method === "GET") {
                throw new Error("You are offline and no cached data is available yet.");
            }
            throw error;
        }
    }

    function saveSession(token, user) {
        clearResponseCache();
        offlineNoticeShown = false;
        localStorage.setItem(tokenKey, token);
        localStorage.setItem(userKey, JSON.stringify(user));
    }

    function clearSession() {
        localStorage.removeItem(tokenKey);
        localStorage.removeItem(userKey);
        clearOfflineData();
    }

    function getUser() {
        try {
            return JSON.parse(localStorage.getItem(userKey) || "null");
        } catch {
            return null;
        }
    }

    function requireAuth() {
        const token = localStorage.getItem(tokenKey);
        if (!token) {
            window.location.href = "/auth";
        }
        return token;
    }

    function formatCurrency(value) {
        return new Intl.NumberFormat("en-IN", {
            style: "currency",
            currency: "INR",
            maximumFractionDigits: 0,
        }).format(Number(value || 0));
    }

    function statusClass(value) {
        return String(value || "").toLowerCase().replace(/\s+/g, "-");
    }

    return {
        api,
        clearSession,
        formatCurrency,
        getSubscriptionState,
        getUser,
        hideUpgradePrompt,
        requireAuth,
        saveSession,
        resetOfflineNotice,
        setSubscriptionState,
        setToast,
        showUpgradePrompt,
        statusClass,
    };
})();
