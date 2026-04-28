document.addEventListener("DOMContentLoaded", () => {
    const banner = document.getElementById("pwa-banner");
    const connectionTargets = Array.from(document.querySelectorAll("[data-pwa-connection]"));
    const installButtons = Array.from(document.querySelectorAll('[data-pwa-action="install"]'));
    const notificationButtons = Array.from(document.querySelectorAll('[data-pwa-action="notifications"]'));
    const isStandalone = window.matchMedia("(display-mode: standalone)").matches || window.navigator.standalone === true;
    const isIos = /iphone|ipad|ipod/i.test(window.navigator.userAgent);
    let deferredPrompt = null;
    let serviceWorkerRegistration = null;

    function setBanner(message, tone = "online") {
        if (!banner) {
            return;
        }
        banner.textContent = message;
        banner.classList.remove("hidden", "is-online", "is-warning");
        banner.classList.add(tone === "warning" ? "is-warning" : "is-online");
    }

    function hideBanner() {
        banner?.classList.add("hidden");
    }

    function setConnectionState(online) {
        connectionTargets.forEach((node) => {
            node.textContent = online ? "Online" : "Offline";
            node.className = "mini-chip";
            if (online) {
                node.removeAttribute("style");
            } else {
                node.style.borderColor = "rgba(248, 113, 113, 0.35)";
                node.style.background = "rgba(127, 29, 29, 0.42)";
                node.style.color = "#fecaca";
            }
        });

        if (online) {
            hideBanner();
            return;
        }

        setBanner("Offline basic mode active. Cached pages and last synced data remain available.", "warning");
    }

    function setInstallButtonState() {
        installButtons.forEach((button) => {
            if (isStandalone) {
                button.hidden = true;
                return;
            }

            button.hidden = false;
            button.textContent = deferredPrompt
                ? "Install app"
                : isIos
                    ? "Add to Home Screen"
                    : "Install app";
        });
    }

    function setNotificationButtonState() {
        if (!("Notification" in window)) {
            notificationButtons.forEach((button) => {
                button.hidden = true;
            });
            return;
        }

        const permission = Notification.permission;
        notificationButtons.forEach((button) => {
            button.hidden = false;
            if (permission === "granted") {
                button.textContent = "Alerts enabled";
                button.disabled = true;
            } else if (permission === "denied") {
                button.textContent = "Enable in settings";
                button.disabled = false;
            } else {
                button.textContent = "Enable alerts";
                button.disabled = false;
            }
        });
    }

    async function enableNotifications() {
        if (!("Notification" in window)) {
            GrowFlow.setToast("This browser does not support notifications.", "error");
            return;
        }

        const permission = Notification.permission === "granted"
            ? "granted"
            : await Notification.requestPermission();

        setNotificationButtonState();

        if (permission !== "granted") {
            GrowFlow.setToast("Notifications were not enabled.", "error");
            return;
        }

        try {
            if (serviceWorkerRegistration?.showNotification) {
                await serviceWorkerRegistration.showNotification("GrowFlow AI", {
                    body: "Browser alerts are ready on this device.",
                    icon: "/static/img/20851361-e614-4795-8051-7a6b75d3d2c3-removebg-preview.png",
                    badge: "/static/img/20851361-e614-4795-8051-7a6b75d3d2c3-removebg-preview.png",
                    tag: "growflow-alerts-ready",
                });
            } else {
                new Notification("GrowFlow AI", {
                    body: "Browser alerts are ready on this device.",
                    icon: "/static/img/20851361-e614-4795-8051-7a6b75d3d2c3-removebg-preview.png",
                });
            }
            GrowFlow.setToast("Browser notifications enabled.");
        } catch {
            GrowFlow.setToast("Notifications were enabled, but the test alert could not be shown.", "error");
        }
    }

    async function handleInstall() {
        if (deferredPrompt) {
            deferredPrompt.prompt();
            const choice = await deferredPrompt.userChoice.catch(() => null);
            deferredPrompt = null;
            setInstallButtonState();
            if (choice?.outcome === "accepted") {
                GrowFlow.setToast("GrowFlow AI is ready to install.");
            }
            return;
        }

        const instruction = isIos
            ? "On iPhone Safari, use Share > Add to Home Screen."
            : "Use your browser menu to install GrowFlow AI on this device.";
        GrowFlow.setToast(instruction, "error");
    }

    if (!isStandalone) {
        setInstallButtonState();
        setNotificationButtonState();
    }

    installButtons.forEach((button) => {
        button.addEventListener("click", () => {
            handleInstall().catch(() => {});
        });
    });

    notificationButtons.forEach((button) => {
        button.addEventListener("click", () => {
            enableNotifications().catch((error) => {
                GrowFlow.setToast(error.message || "Unable to enable notifications.", "error");
            });
        });
    });

    window.addEventListener("beforeinstallprompt", (event) => {
        event.preventDefault();
        deferredPrompt = event;
        setInstallButtonState();
    });

    window.addEventListener("appinstalled", () => {
        deferredPrompt = null;
        setInstallButtonState();
        GrowFlow.setToast("GrowFlow AI installed on this device.");
    });

    window.addEventListener("online", () => {
        setConnectionState(true);
        GrowFlow.resetOfflineNotice?.();
        GrowFlow.setToast("Back online. Fresh data will sync again.");
    });

    window.addEventListener("offline", () => {
        setConnectionState(false);
    });

    if (window.isSecureContext && "serviceWorker" in navigator) {
        window.addEventListener("load", () => {
            navigator.serviceWorker.register("/sw.js").then((registration) => {
                serviceWorkerRegistration = registration;
            }).catch(() => {});
        });
    }

    setConnectionState(window.navigator.onLine !== false);

    if (installButtons.length && isStandalone) {
        installButtons.forEach((button) => {
            button.hidden = true;
        });
    }

    if (notificationButtons.length) {
        setNotificationButtonState();
    }
});
