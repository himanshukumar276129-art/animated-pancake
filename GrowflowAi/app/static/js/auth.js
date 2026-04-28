document.addEventListener("DOMContentLoaded", () => {
    const tabs = document.querySelectorAll(".auth-tab");
    const loginForm = document.getElementById("login-form");
    const registerForm = document.getElementById("register-form");
    const forgotPasswordForm = document.getElementById("forgot-password-form");
    const feedback = document.getElementById("auth-feedback");
    const forgotPasswordButton = document.getElementById("forgot-password-button");
    const params = new URLSearchParams(window.location.search);

    const supabaseUrl = (document.body.dataset.supabaseUrl || "").trim();
    const supabaseKey = (document.body.dataset.supabaseKey || "").trim();
    const supabaseEnabled = document.body.dataset.supabaseEnabled === "true";
    const supabaseClient = supabaseEnabled && window.supabase?.createClient
        ? window.supabase.createClient(supabaseUrl, supabaseKey, {
            auth: {
                autoRefreshToken: false,
                detectSessionInUrl: false,
                persistSession: false,
            },
        })
        : null;

    function setMode(mode) {
        tabs.forEach((tab) => tab.classList.toggle("is-active", tab.dataset.mode === mode));
        loginForm.classList.toggle("hidden", mode !== "login");
        registerForm.classList.toggle("hidden", mode !== "register");
        forgotPasswordForm.classList.toggle("hidden", mode !== "forgot");
        feedback.classList.add("hidden");
    }

    function setFeedback(message, tone = "success") {
        feedback.textContent = message;
        feedback.className = "mt-5 rounded-2xl border px-4 py-3 text-sm";
        if (tone === "error") {
            feedback.classList.add("border-red-500/20", "bg-red-950/40", "text-red-100");
        } else {
            feedback.classList.add("border-glow/20", "bg-glow/10", "text-mint");
        }
        feedback.classList.remove("hidden");
    }

    function extractSupabaseError(error) {
        return (
            error?.message ||
            error?.error_description ||
            error?.msg ||
            "Supabase authentication failed."
        );
    }

    function getAuthClient() {
        if (supabaseClient) {
            return supabaseClient;
        }
        throw new Error("Supabase authentication is not configured.");
    }

    async function exchangeSession(accessToken) {
        const data = await GrowFlow.api("/api/auth/supabase/exchange", {
            method: "POST",
            body: JSON.stringify({ access_token: accessToken }),
        });
        GrowFlow.saveSession(data.token, data.user);
        return data;
    }

    async function signInWithSupabase(payload) {
        const client = getAuthClient();
        const { data, error } = await client.auth.signInWithPassword({
            email: payload.email,
            password: payload.password,
        });
        if (error) {
            throw new Error(extractSupabaseError(error));
        }

        const accessToken = data?.session?.access_token;
        if (!accessToken) {
            throw new Error("Supabase sign-in did not return a session.");
        }
        await exchangeSession(accessToken);
    }

    async function signUpWithSupabase(payload) {
        const client = getAuthClient();
        const { data, error } = await client.auth.signUp({
            email: payload.email,
            password: payload.password,
            options: {
                data: {
                    name: payload.name,
                },
            },
        });
        if (error) {
            throw new Error(extractSupabaseError(error));
        }

        const accessToken = data?.session?.access_token;
        if (!accessToken) {
            return {
                needs_verification: true,
                email: payload.email || "",
            };
        }

        await exchangeSession(accessToken);
        return {
            needs_verification: false,
        };
    }

    async function requestPasswordReset(email) {
        const client = getAuthClient();
        const { error } = await client.auth.resetPasswordForEmail(email, {
            redirectTo: `${window.location.origin}/auth?mode=login`,
        });
        if (error) {
            throw new Error(extractSupabaseError(error));
        }
    }

    async function signInWithLegacyAuth(payload) {
        const data = await GrowFlow.api("/api/login", {
            method: "POST",
            body: JSON.stringify(payload),
        });
        GrowFlow.saveSession(data.token, data.user);
    }

    async function signUpWithLegacyAuth(payload) {
        const data = await GrowFlow.api("/api/register", {
            method: "POST",
            body: JSON.stringify(payload),
        });
        GrowFlow.saveSession(data.token, data.user);
    }

    async function requestLegacyPasswordReset(email) {
        const data = await GrowFlow.api("/api/forgot-password", {
            method: "POST",
            body: JSON.stringify({ email }),
        });
        return data;
    }

    tabs.forEach((tab) => {
        tab.addEventListener("click", () => setMode(tab.dataset.mode));
    });

    forgotPasswordButton.addEventListener("click", () => {
        forgotPasswordForm.email.value = loginForm.email.value || "";
        setMode("forgot");
    });

    loginForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        try {
            const payload = Object.fromEntries(new FormData(loginForm).entries());
            if (supabaseClient) {
                await signInWithSupabase(payload);
            } else {
                await signInWithLegacyAuth(payload);
            }
            window.location.href = "/dashboard";
        } catch (error) {
            setFeedback(error.message, "error");
        }
    });

    registerForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        try {
            const payload = Object.fromEntries(new FormData(registerForm).entries());
            if (supabaseClient) {
                const result = await signUpWithSupabase(payload);
                if (result.needs_verification) {
                    setMode("login");
                    loginForm.email.value = result.email || "";
                    setFeedback(
                        "Account created. Check your email to confirm your address, then sign in.",
                        "success"
                    );
                    return;
                }
            } else {
                await signUpWithLegacyAuth(payload);
            }
            window.location.href = "/dashboard";
        } catch (error) {
            setFeedback(error.message, "error");
        }
    });

    forgotPasswordForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        try {
            const payload = Object.fromEntries(new FormData(forgotPasswordForm).entries());
            if (supabaseClient) {
                await requestPasswordReset(payload.email);
                setMode("login");
                loginForm.email.value = payload.email || "";
                setFeedback("Password reset email sent if the account exists.");
            } else {
                const data = await requestLegacyPasswordReset(payload.email);
                setMode("login");
                loginForm.email.value = payload.email || "";
                setFeedback(data.message);
            }
        } catch (error) {
            setFeedback(error.message, "error");
        }
    });

    const initialMode = params.get("mode");
    if (initialMode && ["login", "register", "forgot"].includes(initialMode)) {
        setMode(initialMode);
    }
});
