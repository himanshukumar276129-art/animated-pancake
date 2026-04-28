document.addEventListener("DOMContentLoaded", () => {
    if (document.body.dataset.authRequired !== "true") {
        return;
    }

    const page = document.body.dataset.page;
    const handlers = {
        dashboard: initDashboardPage,
        employees: initEmployeesPage,
        attendance: initAttendancePage,
        customers: initCustomersPage,
        billing: initBillingPage,
        whatsapp: initWhatsAppPage,
        "whatsapp-settings": initWhatsAppPage,
        "whatsapp-dashboard": initWhatsAppPage,
        "ai-tools": initAiToolsPage,
        "api-settings": initApiSettingsPage,
        database: initDatabasePage,
        analytics: initAnalyticsPage,
        subscription: initSubscriptionPage,
        settings: initSettingsPage,
        support: initSupportPage,
    };

    const handler = handlers[page];
    if (!handler) {
        return;
    }

    handler().catch(handleFatalPageError);
});

function handleFatalPageError(error) {
    const message = error?.message || "Something went wrong.";
    if (/auth|token|session/i.test(message)) {
        GrowFlow.clearSession();
        window.location.href = "/auth";
        return;
    }
    GrowFlow.setToast(message, "error");
}

function escapeHtml(value) {
    return String(value ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
}

function setAlert(node, message, tone = "success") {
    if (!node) {
        return;
    }
    node.textContent = message;
    node.className = "mt-5 rounded-2xl border px-4 py-3 text-sm";
    if (tone === "error") {
        node.classList.add("border-red-500/20", "bg-red-950/40", "text-red-100");
    } else {
        node.classList.add("border-glow/20", "bg-glow/10", "text-mint");
    }
    node.classList.remove("hidden");
}

function clearAlert(node) {
    if (!node) {
        return;
    }
    node.textContent = "";
    node.classList.add("hidden");
}

function formatDate(value) {
    if (!value) {
        return "Not available";
    }
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) {
        return String(value);
    }
    return parsed.toLocaleDateString("en-IN", {
        day: "2-digit",
        month: "short",
        year: "numeric",
    });
}

function formatDateTime(value) {
    if (!value) {
        return "Not available";
    }
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) {
        return String(value);
    }
    return parsed.toLocaleString("en-IN");
}

function getTodayIso() {
    const today = new Date();
    const month = String(today.getMonth() + 1).padStart(2, "0");
    const day = String(today.getDate()).padStart(2, "0");
    return `${today.getFullYear()}-${month}-${day}`;
}

function renderList(container, rows, template, emptyMessage) {
    if (!container) {
        return;
    }
    container.innerHTML = "";
    if (!rows.length) {
        container.innerHTML = `<div class="list-card text-sm text-white/55">${escapeHtml(emptyMessage)}</div>`;
        return;
    }
    rows.forEach((row) => {
        const wrapper = document.createElement("div");
        wrapper.className = "list-card";
        wrapper.innerHTML = template(row);
        container.appendChild(wrapper);
    });
}

function renderSelectOptions(select, rows, labelBuilder, options = {}) {
    if (!select) {
        return;
    }
    const {
        includePlaceholder = true,
        placeholder = "Select an option",
        multiple = false,
        selectedValue = "",
        valueBuilder = (row) => row.id,
    } = options;
    const selectedSet = new Set(
        Array.isArray(selectedValue) ? selectedValue.map((value) => String(value)) : [String(selectedValue || "")]
    );
    const placeholderHtml = !multiple && includePlaceholder
        ? `<option value="">${escapeHtml(placeholder)}</option>`
        : "";
    select.innerHTML = `${placeholderHtml}${rows.map((row) => {
        const value = String(valueBuilder(row));
        const selected = selectedSet.has(value) ? " selected" : "";
        return `<option value="${escapeHtml(value)}"${selected}>${escapeHtml(labelBuilder(row))}</option>`;
    }).join("")}`;
}

function buildBarChart(container, points, formatter = (value) => GrowFlow.formatCurrency(value)) {
    if (!container) {
        return;
    }
    if (!points.length) {
        container.innerHTML = `<div class="text-sm text-white/55">No chart data available.</div>`;
        return;
    }
    const maxValue = Math.max(...points.map((point) => Number(point.value || 0)), 1);
    container.innerHTML = points.map((point) => {
        const height = Math.max(18, Math.round((Number(point.value || 0) / maxValue) * 180));
        return `
            <div class="chart-bar">
                <span class="chart-value">${escapeHtml(formatter(point.value))}</span>
                <div class="chart-bar-fill" style="height:${height}px"></div>
                <span class="chart-label">${escapeHtml(point.label)}</span>
            </div>
        `;
    }).join("");
}

function applyTheme(theme) {
    const isLight = theme === "light";
    document.getElementById("app-body")?.classList.toggle("theme-light", isLight);
    document.getElementById("app-background")?.classList.toggle("theme-light", isLight);
    localStorage.setItem("growflowTheme", isLight ? "light" : "dark");
}

async function downloadAuthenticated(path, filename) {
    const token = localStorage.getItem("growflowToken");
    const response = await fetch(path, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    const data = await response.clone().json().catch(() => ({}));

    if (data.upgrade_required) {
        GrowFlow.setSubscriptionState(data);
        GrowFlow.showUpgradePrompt(data);
    }

    if (!response.ok) {
        throw new Error(data.message || "Download failed.");
    }

    const blob = await response.blob();
    const blobUrl = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = blobUrl;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(blobUrl);
}

function downloadCsv(filename, rows) {
    const csv = rows.map((row) => row.map((value) => {
        const text = String(value ?? "");
        return `"${text.replace(/"/g, '""')}"`;
    }).join(",")).join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const blobUrl = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = blobUrl;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(blobUrl);
}

function statusPill(value) {
    return `<span class="status-chip ${GrowFlow.statusClass(value)}">${escapeHtml(value)}</span>`;
}

function inferTemplateSelectionValue(template) {
    return template.is_builtin ? `builtin:${template.key}` : `custom:${template.id}`;
}

function inferMessageType(template) {
    const source = `${template.category || ""} ${template.template_name || ""}`.toLowerCase();
    if (source.includes("reminder")) {
        return "reminder";
    }
    if (source.includes("invoice")) {
        return "invoice";
    }
    if (source.includes("welcome")) {
        return "welcome";
    }
    if (source.includes("festival") || source.includes("discount") || source.includes("offer")) {
        return "promotional";
    }
    return "text";
}

async function initDashboardPage() {
    const nodes = {
        sales: document.getElementById("overview-sales"),
        pending: document.getElementById("overview-pending"),
        pendingNote: document.getElementById("overview-pending-note"),
        customers: document.getElementById("overview-customers"),
        attendance: document.getElementById("overview-attendance"),
        whatsappStatus: document.getElementById("overview-whatsapp-status"),
        growthChart: document.getElementById("overview-growth-chart"),
        activityList: document.getElementById("overview-activity-list"),
        marketingList: document.getElementById("overview-marketing-list"),
    };

    const [dashboardData, attendanceData] = await Promise.all([
        GrowFlow.api("/api/dashboard"),
        GrowFlow.api("/api/attendance"),
    ]);

    nodes.sales.textContent = GrowFlow.formatCurrency(dashboardData.stats.today_sales);
    nodes.pending.textContent = GrowFlow.formatCurrency(dashboardData.stats.pending_payments);
    nodes.pendingNote.textContent = `${dashboardData.stats.pending_invoice_count} invoices need follow-up`;
    nodes.customers.textContent = String(dashboardData.stats.customer_count || 0);
    nodes.attendance.textContent = `${dashboardData.stats.today_present} / ${dashboardData.stats.total_employees}`;
    const subscription = dashboardData.subscription || {};
    const currentSubscription = subscription.current || {};
    const access = dashboardData.subscription_access || {};
    const subscriptionNotice = dashboardData.subscription_notice || "";
    GrowFlow.setSubscriptionState({
        subscription,
        access,
        quote: dashboardData.subscription_quote || {},
        payment_gateways: dashboardData.payment_gateways || {},
        notice: subscriptionNotice,
        upgrade_required: dashboardData.subscription_upgrade_required,
    });
    if (access.premium_active) {
        nodes.whatsappStatus.textContent = dashboardData.integrations.whatsapp_configured
            ? `WhatsApp Ready (${dashboardData.integrations.whatsapp_source})`
            : "WhatsApp Setup Needed";
    } else if (access.trial_active && currentSubscription.trial_days_left !== null && currentSubscription.trial_days_left !== undefined) {
        nodes.whatsappStatus.textContent = `Trial: ${currentSubscription.trial_days_left} day(s) left`;
    } else if (dashboardData.subscription_upgrade_required) {
        nodes.whatsappStatus.textContent = "Upgrade required";
    } else {
        nodes.whatsappStatus.textContent = "Free plan active";
    }
    nodes.whatsappStatus.title = subscriptionNotice;
    if (!access.premium_active) {
        nodes.whatsappStatus.classList.add("cursor-pointer");
        nodes.whatsappStatus.addEventListener("click", () => GrowFlow.showUpgradePrompt(GrowFlow.getSubscriptionState()));
    }

    buildBarChart(nodes.growthChart, dashboardData.growth_chart || []);

    renderList(
        nodes.activityList,
        dashboardData.recent_whatsapp_messages || [],
        (row) => `
            <div class="flex items-start justify-between gap-4">
                <div>
                    <p class="font-medium text-white">${escapeHtml(row.template_name || row.message_type || "Activity")}</p>
                    <p class="mt-1 text-sm text-white/60">${escapeHtml(row.customer_name || row.recipient_phone || "Campaign record")}</p>
                    <p class="mt-2 text-xs text-white/45">${escapeHtml((row.message || "").slice(0, 120))}</p>
                </div>
                <div class="text-right">
                    ${statusPill(row.status || "queued")}
                    <p class="mt-2 text-xs text-white/45">${escapeHtml(formatDateTime(row.sent_at || row.created_at))}</p>
                </div>
            </div>
        `,
        "No recent operational activity."
    );

    const marketingRows = (dashboardData.recent_marketing || []).map((row) => ({
        ...row,
        audience: row.audience || "broadcast",
    }));
    if (attendanceData.attendance?.length) {
        marketingRows.unshift({
            id: "attendance-summary",
            message: `Attendance marked for ${attendanceData.attendance.length} team members today.`,
            audience: "attendance",
            delivery_status: "active",
            sent_at: new Date().toISOString(),
        });
    }
    renderList(
        nodes.marketingList,
        marketingRows,
        (row) => `
            <div class="flex items-start justify-between gap-4">
                <div>
                    <p class="font-medium text-white">${escapeHtml(row.audience)}</p>
                    <p class="mt-2 text-sm text-white/65">${escapeHtml((row.message || "").slice(0, 140))}</p>
                </div>
                <div class="text-right">
                    ${statusPill(row.delivery_status || "active")}
                    <p class="mt-2 text-xs text-white/45">${escapeHtml(formatDateTime(row.sent_at))}</p>
                </div>
            </div>
        `,
        "No campaigns have been logged yet."
    );
}

async function initEmployeesPage() {
    const nodes = {
        form: document.getElementById("employee-form"),
        alert: document.getElementById("employee-alert"),
        summary: document.getElementById("employee-summary"),
        recordList: document.getElementById("employee-record-list"),
        id: document.getElementById("employee-id"),
        name: document.getElementById("employee-name"),
        role: document.getElementById("employee-role"),
        reset: document.getElementById("employee-reset-button"),
    };

    const state = { employees: [], attendance: [] };

    function resetForm() {
        nodes.form.reset();
        nodes.id.value = "";
        clearAlert(nodes.alert);
    }

    function render() {
        const presentCount = state.attendance.filter((row) => row.status === "present").length;
        nodes.summary.innerHTML = `
            <span class="mini-chip">Employees: ${state.employees.length}</span>
            <span class="mini-chip">Present today: ${presentCount}</span>
            <span class="mini-chip">Attendance rows: ${state.attendance.length}</span>
        `;

        renderList(
            nodes.recordList,
            state.employees,
            (row) => `
                <div class="flex items-start justify-between gap-4">
                    <div>
                        <p class="font-medium text-white">${escapeHtml(row.name)}</p>
                        <p class="mt-1 text-sm text-white/60">${escapeHtml(row.role)}</p>
                        <p class="mt-2 text-xs text-white/45">Latest status: ${escapeHtml(row.latest_status)}</p>
                    </div>
                    <div class="flex flex-wrap gap-2">
                        ${statusPill(row.latest_status)}
                        <button type="button" class="action-btn border border-white/10 bg-white/5 text-white" data-employee-action="edit" data-id="${row.id}">Edit</button>
                        <button type="button" class="action-btn border border-red-500/20 bg-red-950/30 text-red-100" data-employee-action="delete" data-id="${row.id}">Delete</button>
                    </div>
                </div>
            `,
            "No employees added yet."
        );
    }

    async function loadData() {
        const [employeesData, attendanceData] = await Promise.all([
            GrowFlow.api("/api/employees"),
            GrowFlow.api("/api/attendance"),
        ]);
        state.employees = employeesData.employees || [];
        state.attendance = attendanceData.attendance || [];
        render();
    }

    nodes.form.addEventListener("submit", async (event) => {
        event.preventDefault();
        clearAlert(nodes.alert);
        const payload = Object.fromEntries(new FormData(nodes.form).entries());
        const employeeId = payload.id;
        delete payload.id;
        try {
            const response = employeeId
                ? await GrowFlow.api(`/api/employees/${employeeId}`, { method: "PUT", body: JSON.stringify(payload) })
                : await GrowFlow.api("/api/employees", { method: "POST", body: JSON.stringify(payload) });
            await loadData();
            resetForm();
            setAlert(nodes.alert, response.message, "success");
            GrowFlow.setToast(response.message);
        } catch (error) {
            setAlert(nodes.alert, error.message, "error");
        }
    });

    nodes.recordList.addEventListener("click", async (event) => {
        const button = event.target.closest("[data-employee-action]");
        if (!button) {
            return;
        }
        const employeeId = Number(button.dataset.id);
        const employee = state.employees.find((row) => row.id === employeeId);
        if (!employee) {
            return;
        }

        if (button.dataset.employeeAction === "edit") {
            nodes.id.value = String(employee.id);
            nodes.name.value = employee.name;
            nodes.role.value = employee.role;
            window.scrollTo({ top: 0, behavior: "smooth" });
            return;
        }

        if (!window.confirm(`Delete ${employee.name}?`)) {
            return;
        }
        try {
            const response = await GrowFlow.api(`/api/employees/${employee.id}`, { method: "DELETE" });
            await loadData();
            resetForm();
            GrowFlow.setToast(response.message);
        } catch (error) {
            GrowFlow.setToast(error.message, "error");
        }
    });

    nodes.reset.addEventListener("click", resetForm);

    await loadData();
}

async function initAttendancePage() {
    const nodes = {
        date: document.getElementById("attendance-date-filter"),
        loadButton: document.getElementById("attendance-load-button"),
        exportButton: document.getElementById("attendance-export-button"),
        employeeSelect: document.getElementById("attendance-employee-id"),
        statusSelect: document.getElementById("attendance-status"),
        form: document.getElementById("attendance-form"),
        alert: document.getElementById("attendance-alert"),
        summary: document.getElementById("attendance-summary"),
        recordList: document.getElementById("attendance-record-list"),
    };

    const state = { employees: [], attendance: [] };
    nodes.date.value = getTodayIso();

    function render() {
        const counts = {
            present: state.attendance.filter((row) => row.status === "present").length,
            absent: state.attendance.filter((row) => row.status === "absent").length,
            leave: state.attendance.filter((row) => row.status === "leave").length,
        };
        nodes.summary.innerHTML = `
            <span class="mini-chip">Present: ${counts.present}</span>
            <span class="mini-chip">Absent: ${counts.absent}</span>
            <span class="mini-chip">Leave: ${counts.leave}</span>
            <span class="mini-chip">Date: ${escapeHtml(nodes.date.value)}</span>
        `;
        renderList(
            nodes.recordList,
            state.attendance,
            (row) => `
                <div class="flex items-center justify-between gap-4">
                    <div>
                        <p class="font-medium text-white">${escapeHtml(row.employee_name)}</p>
                        <p class="text-sm text-white/60">${escapeHtml(row.date)}</p>
                    </div>
                    ${statusPill(row.status)}
                </div>
            `,
            "No attendance marked for this date."
        );
    }

    async function loadEmployees() {
        const employeesData = await GrowFlow.api("/api/employees");
        state.employees = employeesData.employees || [];
        renderSelectOptions(nodes.employeeSelect, state.employees, (row) => `${row.name} - ${row.role}`, {
            placeholder: "Choose employee",
        });
    }

    async function loadAttendance() {
        const attendanceData = await GrowFlow.api(`/api/attendance?date=${encodeURIComponent(nodes.date.value)}`);
        state.attendance = attendanceData.attendance || [];
        render();
    }

    nodes.loadButton.addEventListener("click", () => {
        loadAttendance().catch(handleFatalPageError);
    });

    nodes.form.addEventListener("submit", async (event) => {
        event.preventDefault();
        clearAlert(nodes.alert);
        try {
            const payload = {
                employee_id: nodes.employeeSelect.value,
                status: nodes.statusSelect.value,
                date: nodes.date.value,
            };
            const response = await GrowFlow.api("/api/attendance", {
                method: "POST",
                body: JSON.stringify(payload),
            });
            await loadAttendance();
            setAlert(nodes.alert, response.message, "success");
            GrowFlow.setToast(response.message);
        } catch (error) {
            setAlert(nodes.alert, error.message, "error");
        }
    });

    nodes.exportButton.addEventListener("click", () => {
        if (!state.attendance.length) {
            GrowFlow.setToast("Load attendance rows first.", "error");
            return;
        }
        downloadCsv(
            `growflow-attendance-${nodes.date.value}.csv`,
            [["Employee", "Date", "Status"], ...state.attendance.map((row) => [row.employee_name, row.date, row.status])]
        );
        GrowFlow.setToast("Attendance export downloaded.");
    });

    await loadEmployees();
    await loadAttendance();
}

async function initCustomersPage() {
    const nodes = {
        form: document.getElementById("customer-form"),
        alert: document.getElementById("customer-alert"),
        importForm: document.getElementById("customer-import-form"),
        importAlert: document.getElementById("customer-import-alert"),
        summary: document.getElementById("customer-summary"),
        recordList: document.getElementById("customer-record-list"),
        id: document.getElementById("customer-id"),
        name: document.getElementById("customer-name"),
        phone: document.getElementById("customer-phone"),
        email: document.getElementById("customer-email"),
        reset: document.getElementById("customer-reset-button"),
    };

    const state = { customers: [], invoices: [] };

    function resetForm() {
        nodes.form.reset();
        nodes.id.value = "";
        clearAlert(nodes.alert);
    }

    function render() {
        const totalBilled = state.invoices.reduce((sum, row) => sum + Number(row.amount || 0), 0);
        nodes.summary.innerHTML = `
            <span class="mini-chip">Customers: ${state.customers.length}</span>
            <span class="mini-chip">Invoices: ${state.invoices.length}</span>
            <span class="mini-chip">Billed value: ${GrowFlow.formatCurrency(totalBilled)}</span>
        `;

        const invoiceSummary = state.invoices.reduce((accumulator, invoice) => {
            const bucket = accumulator[invoice.customer_id] || { count: 0, total: 0, lastDate: invoice.issued_on };
            bucket.count += 1;
            bucket.total += Number(invoice.amount || 0);
            bucket.lastDate = invoice.issued_on > bucket.lastDate ? invoice.issued_on : bucket.lastDate;
            accumulator[invoice.customer_id] = bucket;
            return accumulator;
        }, {});

        renderList(
            nodes.recordList,
            state.customers,
            (row) => {
                const summary = invoiceSummary[row.id] || { count: 0, total: 0, lastDate: "" };
                return `
                    <div class="flex items-start justify-between gap-4">
                        <div>
                            <p class="font-medium text-white">${escapeHtml(row.name)}</p>
                            <p class="mt-1 text-sm text-white/60">${escapeHtml(row.phone)}</p>
                            <p class="mt-1 text-sm text-white/45">${escapeHtml(row.email || "No email")}</p>
                            <p class="mt-3 text-xs text-white/45">
                                Purchase history: ${summary.count} invoices · ${escapeHtml(GrowFlow.formatCurrency(summary.total))}${summary.lastDate ? ` · latest ${escapeHtml(summary.lastDate)}` : ""}
                            </p>
                        </div>
                        <div class="flex flex-wrap gap-2">
                            <button type="button" class="action-btn border border-white/10 bg-white/5 text-white" data-customer-action="edit" data-id="${row.id}">Edit</button>
                            <button type="button" class="action-btn border border-red-500/20 bg-red-950/30 text-red-100" data-customer-action="delete" data-id="${row.id}">Delete</button>
                        </div>
                    </div>
                `;
            },
            "No customers available yet."
        );
    }

    async function loadData() {
        const [customersData, invoicesData] = await Promise.all([
            GrowFlow.api("/api/customers"),
            GrowFlow.api("/api/invoices"),
        ]);
        state.customers = customersData.customers || [];
        state.invoices = invoicesData.invoices || [];
        render();
    }

    nodes.form.addEventListener("submit", async (event) => {
        event.preventDefault();
        clearAlert(nodes.alert);
        const payload = Object.fromEntries(new FormData(nodes.form).entries());
        const customerId = payload.id;
        delete payload.id;
        try {
            const response = customerId
                ? await GrowFlow.api(`/api/customers/${customerId}`, { method: "PUT", body: JSON.stringify(payload) })
                : await GrowFlow.api("/api/customers", { method: "POST", body: JSON.stringify(payload) });
            await loadData();
            resetForm();
            setAlert(nodes.alert, response.message, "success");
            GrowFlow.setToast(response.message);
        } catch (error) {
            setAlert(nodes.alert, error.message, "error");
        }
    });

    nodes.importForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        clearAlert(nodes.importAlert);
        try {
            const payload = Object.fromEntries(new FormData(nodes.importForm).entries());
            const response = await GrowFlow.api("/api/customers/import", {
                method: "POST",
                body: JSON.stringify(payload),
            });
            nodes.importForm.reset();
            await loadData();
            setAlert(nodes.importAlert, response.message, "success");
            GrowFlow.setToast(response.message);
        } catch (error) {
            setAlert(nodes.importAlert, error.message, "error");
        }
    });

    nodes.recordList.addEventListener("click", async (event) => {
        const button = event.target.closest("[data-customer-action]");
        if (!button) {
            return;
        }
        const customerId = Number(button.dataset.id);
        const customer = state.customers.find((row) => row.id === customerId);
        if (!customer) {
            return;
        }

        if (button.dataset.customerAction === "edit") {
            nodes.id.value = String(customer.id);
            nodes.name.value = customer.name;
            nodes.phone.value = customer.phone;
            nodes.email.value = customer.email || "";
            window.scrollTo({ top: 0, behavior: "smooth" });
            return;
        }

        if (!window.confirm(`Delete ${customer.name}? This also removes related invoices.`)) {
            return;
        }

        try {
            const response = await GrowFlow.api(`/api/customers/${customer.id}`, { method: "DELETE" });
            await loadData();
            resetForm();
            GrowFlow.setToast(response.message);
        } catch (error) {
            GrowFlow.setToast(error.message, "error");
        }
    });

    nodes.reset.addEventListener("click", resetForm);

    await loadData();
}

async function initBillingPage() {
    const nodes = {
        form: document.getElementById("invoice-form"),
        alert: document.getElementById("invoice-alert"),
        customerSelect: document.getElementById("invoice-customer-id"),
        totalPaid: document.getElementById("billing-total-paid"),
        pendingAmount: document.getElementById("billing-pending-amount"),
        invoiceCount: document.getElementById("billing-invoice-count"),
        recordList: document.getElementById("invoice-record-list"),
        statusFilter: document.getElementById("invoice-status-filter"),
    };

    const state = { customers: [], invoices: [] };

    function render() {
        const totalPaid = state.invoices
            .filter((row) => row.status === "paid")
            .reduce((sum, row) => sum + Number(row.amount || 0), 0);
        const pendingAmount = state.invoices
            .filter((row) => row.status !== "paid")
            .reduce((sum, row) => sum + Number(row.amount || 0), 0);

        nodes.totalPaid.textContent = GrowFlow.formatCurrency(totalPaid);
        nodes.pendingAmount.textContent = GrowFlow.formatCurrency(pendingAmount);
        nodes.invoiceCount.textContent = String(state.invoices.length);
        renderSelectOptions(nodes.customerSelect, state.customers, (row) => `${row.name} - ${row.phone}`, {
            placeholder: "Choose customer",
        });

        const filter = nodes.statusFilter.value;
        const filteredInvoices = filter === "all"
            ? state.invoices
            : state.invoices.filter((row) => row.status === filter);

        renderList(
            nodes.recordList,
            filteredInvoices,
            (row) => `
                <div class="space-y-4" data-invoice-row="${row.id}">
                    <div class="flex items-start justify-between gap-4">
                        <div>
                            <p class="font-medium text-white">${escapeHtml(row.customer_name)}</p>
                            <p class="mt-1 text-sm text-white/60">${escapeHtml(row.issued_on)}</p>
                            <p class="mt-2 text-lg font-semibold text-white">${escapeHtml(GrowFlow.formatCurrency(row.amount))}</p>
                        </div>
                        <div class="text-right">
                            ${statusPill(row.status)}
                        </div>
                    </div>
                    <div class="flex flex-col gap-3 md:flex-row">
                        <select class="field" data-invoice-status>
                            <option value="pending" ${row.status === "pending" ? "selected" : ""}>Pending</option>
                            <option value="paid" ${row.status === "paid" ? "selected" : ""}>Paid</option>
                            <option value="overdue" ${row.status === "overdue" ? "selected" : ""}>Overdue</option>
                        </select>
                        <button type="button" class="action-btn border border-glow/20 bg-glow/10 text-glow" data-invoice-action="save" data-id="${row.id}">Save Status</button>
                        <button type="button" class="action-btn border border-red-500/20 bg-red-950/30 text-red-100" data-invoice-action="delete" data-id="${row.id}">Delete</button>
                    </div>
                </div>
            `,
            "No invoices found for the selected filter."
        );
    }

    async function loadData() {
        const [customersData, invoicesData] = await Promise.all([
            GrowFlow.api("/api/customers"),
            GrowFlow.api("/api/invoices"),
        ]);
        state.customers = customersData.customers || [];
        state.invoices = invoicesData.invoices || [];
        render();
    }

    nodes.form.addEventListener("submit", async (event) => {
        event.preventDefault();
        clearAlert(nodes.alert);
        const formData = new FormData(nodes.form);
        const payload = {
            customer_id: formData.get("customer_id"),
            amount: formData.get("amount"),
            status: formData.get("status"),
            send_whatsapp: document.getElementById("invoice-send-whatsapp").checked,
        };
        try {
            const response = await GrowFlow.api("/api/invoices", {
                method: "POST",
                body: JSON.stringify(payload),
            });
            nodes.form.reset();
            await loadData();
            setAlert(nodes.alert, response.notification?.message || response.message, "success");
            GrowFlow.setToast(response.message);
        } catch (error) {
            setAlert(nodes.alert, error.message, "error");
        }
    });

    nodes.recordList.addEventListener("click", async (event) => {
        const button = event.target.closest("[data-invoice-action]");
        if (!button) {
            return;
        }
        const invoiceId = Number(button.dataset.id);

        if (button.dataset.invoiceAction === "delete") {
            if (!window.confirm("Delete this invoice?")) {
                return;
            }
            try {
                const response = await GrowFlow.api(`/api/invoices/${invoiceId}`, { method: "DELETE" });
                await loadData();
                GrowFlow.setToast(response.message);
            } catch (error) {
                GrowFlow.setToast(error.message, "error");
            }
            return;
        }

        try {
            const wrapper = button.closest("[data-invoice-row]");
            const status = wrapper?.querySelector("[data-invoice-status]")?.value || "pending";
            const response = await GrowFlow.api(`/api/invoices/${invoiceId}`, {
                method: "PUT",
                body: JSON.stringify({ status }),
            });
            await loadData();
            GrowFlow.setToast(response.message);
        } catch (error) {
            GrowFlow.setToast(error.message, "error");
        }
    });

    nodes.statusFilter.addEventListener("change", render);

    await loadData();
}

async function initWhatsAppPage() {
    const nodes = {
        connectionForm: document.getElementById("whatsapp-connection-form"),
        settingsAlert: document.getElementById("whatsapp-settings-alert"),
        summaryChips: document.getElementById("whatsapp-summary-chips"),
        apiKey: document.getElementById("whatsapp-api-key"),
        phoneNumberId: document.getElementById("whatsapp-phone-number-id"),
        businessAccountId: document.getElementById("whatsapp-business-account-id"),
        verifyToken: document.getElementById("whatsapp-verify-token"),
        sendForm: document.getElementById("whatsapp-send-form"),
        sendAlert: document.getElementById("whatsapp-send-alert"),
        sendMode: document.getElementById("whatsapp-send-mode"),
        sendCustomers: document.getElementById("whatsapp-send-customers"),
        sendSelectedWrap: document.getElementById("whatsapp-send-selected-wrap"),
        sendSingleWrap: document.getElementById("whatsapp-send-single-wrap"),
        sendManualWrap: document.getElementById("whatsapp-send-manual-wrap"),
        sendSingle: document.getElementById("whatsapp-send-single"),
        sendManual: document.getElementById("whatsapp-send-manual"),
        templateSelect: document.getElementById("whatsapp-template-select"),
        messageType: document.getElementById("whatsapp-message-type"),
        deliveryMode: document.getElementById("whatsapp-delivery-mode"),
        scheduledFor: document.getElementById("whatsapp-scheduled-for"),
        messageContent: document.getElementById("whatsapp-message-content"),
        templateForm: document.getElementById("whatsapp-template-form"),
        templateAlert: document.getElementById("whatsapp-template-alert"),
        templateId: document.getElementById("whatsapp-template-id"),
        templateName: document.getElementById("whatsapp-template-name"),
        templateCategory: document.getElementById("whatsapp-template-category"),
        templateContent: document.getElementById("whatsapp-template-content"),
        templateReset: document.getElementById("whatsapp-template-reset"),
        templateLibrary: document.getElementById("whatsapp-template-library"),
        logList: document.getElementById("whatsapp-log-list"),
        saveButton: document.getElementById("whatsapp-save-button"),
        connectButton: document.getElementById("whatsapp-connect-button"),
        disconnectButton: document.getElementById("whatsapp-disconnect-button"),
    };

    const state = {
        customers: [],
        messages: [],
        summary: { total: 0, sent: 0, demo: 0, scheduled: 0, failed: 0 },
        status: null,
        templates: [],
    };

    function resetTemplateForm() {
        if (!nodes.templateForm) {
            return;
        }
        nodes.templateForm.reset();
        if (nodes.templateId) {
            nodes.templateId.value = "";
        }
        clearAlert(nodes.templateAlert);
    }

    function normalizeTemplates(rawTemplates) {
        return (rawTemplates || []).map((template) => ({
            ...template,
            selectionValue: inferTemplateSelectionValue(template),
        }));
    }

    function findTemplate(selectionValue) {
        return state.templates.find((template) => template.selectionValue === selectionValue);
    }

    function updateRecipientModeDisplay() {
        if (!nodes.sendMode) {
            return;
        }
        const mode = nodes.sendMode.value;
        nodes.sendSelectedWrap?.classList.toggle("hidden", mode !== "selected_customers");
        nodes.sendSingleWrap?.classList.toggle("hidden", mode !== "single_customer");
        nodes.sendManualWrap?.classList.toggle("hidden", mode !== "manual_number");
    }

    function syncDeliveryModeAvailability() {
        if (!nodes.deliveryMode) {
            return;
        }
        const liveAccess = !!state.status?.live_access;
        const liveOption = nodes.deliveryMode.querySelector('option[value="live"]');
        if (liveOption) {
            liveOption.disabled = !liveAccess;
        }
        if (!liveAccess && nodes.deliveryMode.value !== "demo") {
            nodes.deliveryMode.value = "demo";
        }
    }

    function applyTemplate(selectionValue) {
        const template = findTemplate(selectionValue);
        if (!template) {
            return;
        }
        if (nodes.templateSelect) {
            nodes.templateSelect.value = template.selectionValue;
        }
        if (nodes.messageContent) {
            nodes.messageContent.value = template.content || "";
        }
        if (nodes.messageType) {
            nodes.messageType.value = inferMessageType(template);
        }
    }

    function render() {
        renderSelectOptions(nodes.sendCustomers, state.customers, (row) => `${row.name} - ${row.phone}`, {
            includePlaceholder: false,
            multiple: true,
        });
        renderSelectOptions(nodes.sendSingle, state.customers, (row) => `${row.name} - ${row.phone}`, {
            placeholder: "Choose customer",
        });
        renderSelectOptions(
            nodes.templateSelect,
            state.templates,
            (row) => `${row.template_name}${row.is_builtin ? " (built-in)" : ""}`,
            {
                placeholder: "Choose template",
                valueBuilder: (row) => row.selectionValue,
            }
        );

        const status = state.status?.status || {};
        const liveAccess = !!state.status?.live_access;
        const credentialSource = state.status?.credential_source || "none";
        const connectionState = state.status?.connection_state || status.status || "disconnected";
        if (nodes.summaryChips) {
            nodes.summaryChips.innerHTML = `
                <span class="mini-chip">Connection: ${escapeHtml(connectionState)}</span>
                <span class="mini-chip">Source: ${escapeHtml(credentialSource)}</span>
                <span class="mini-chip">Access: ${liveAccess ? "live" : "demo only"}</span>
                <span class="mini-chip">Saved: ${status.api_key_saved ? "yes" : "no"}</span>
                <span class="mini-chip">Sent: ${state.summary.sent || 0}</span>
                <span class="mini-chip">Scheduled: ${state.summary.scheduled || 0}</span>
            `;
        }

        if (nodes.phoneNumberId) {
            nodes.phoneNumberId.value = status.phone_number_id || "";
        }
        if (nodes.businessAccountId) {
            nodes.businessAccountId.value = status.business_account_id || "";
        }
        if (nodes.apiKey) {
            nodes.apiKey.value = "";
            nodes.apiKey.placeholder = status.api_key_masked ? `Saved: ${status.api_key_masked}` : "Access token";
        }
        if (nodes.verifyToken) {
            nodes.verifyToken.value = "";
            nodes.verifyToken.placeholder = status.verify_token_masked ? `Saved: ${status.verify_token_masked}` : "Verify token (optional)";
        }

        if (nodes.connectButton) {
            nodes.connectButton.disabled = !liveAccess;
            nodes.connectButton.textContent = liveAccess ? "Save and Verify" : "Live Verification Locked";
            nodes.connectButton.title = liveAccess
                ? "Save the credentials and verify them against Meta."
                : "Upgrade to Pro or use the trial to verify live WhatsApp connectivity.";
            nodes.connectButton.classList.toggle("opacity-50", !liveAccess);
            nodes.connectButton.classList.toggle("cursor-not-allowed", !liveAccess);
        }
        syncDeliveryModeAvailability();

        renderList(
            nodes.templateLibrary,
            state.templates,
            (row) => `
                <div class="flex items-start justify-between gap-4">
                    <div>
                        <p class="font-medium text-white">${escapeHtml(row.template_name)}</p>
                        <p class="mt-1 text-sm text-white/60">${escapeHtml(row.category || "custom")}${row.is_builtin ? " - built-in" : ""}</p>
                        <p class="mt-2 text-xs text-white/45">${escapeHtml((row.content || "").slice(0, 140))}</p>
                    </div>
                    <div class="flex flex-wrap gap-2">
                        <button type="button" class="action-btn border border-glow/20 bg-glow/10 text-glow" data-template-action="use" data-selection="${escapeHtml(row.selectionValue)}">Use</button>
                        ${row.is_builtin ? "" : `<button type="button" class="action-btn border border-white/10 bg-white/5 text-white" data-template-action="edit" data-id="${row.id}">Edit</button>`}
                        ${row.is_builtin ? "" : `<button type="button" class="action-btn border border-red-500/20 bg-red-950/30 text-red-100" data-template-action="delete" data-id="${row.id}">Delete</button>`}
                    </div>
                </div>
            `,
            "No WhatsApp templates available."
        );

        renderList(
            nodes.logList,
            state.messages,
            (row) => `
                <div class="flex items-start justify-between gap-4">
                    <div>
                        <p class="font-medium text-white">${escapeHtml(row.template_name || row.message_type || "Message")}</p>
                        <p class="mt-1 text-sm text-white/60">${escapeHtml(row.customer_name || row.recipient_phone)}</p>
                        <p class="mt-2 text-xs text-white/45">${escapeHtml((row.message || "").slice(0, 120))}</p>
                    </div>
                    <div class="text-right">
                        ${statusPill(row.status)}
                        <p class="mt-2 text-xs text-white/45">${escapeHtml(formatDateTime(row.sent_at || row.scheduled_for || row.created_at))}</p>
                    </div>
                </div>
            `,
            "No WhatsApp activity yet."
        );
    }

    async function loadData() {
        const [customersData, messagesData, templatesData, statusData] = await Promise.all([
            GrowFlow.api("/api/customers"),
            GrowFlow.api("/api/whatsapp/messages"),
            GrowFlow.api("/api/whatsapp/templates"),
            GrowFlow.api("/api/whatsapp/status"),
        ]);
        state.customers = customersData.customers || [];
        state.messages = messagesData.messages || [];
        state.summary = messagesData.summary || state.summary;
        state.templates = normalizeTemplates(templatesData.templates || []);
        state.status = statusData;
        render();
    }

    async function saveConnection(verify) {
        clearAlert(nodes.settingsAlert);
        try {
            const payload = {
                access_token: nodes.apiKey?.value || "",
                phone_number_id: nodes.phoneNumberId?.value || "",
                business_account_id: nodes.businessAccountId?.value || "",
                verify_token: nodes.verifyToken?.value || "",
                verify,
            };
            const response = await GrowFlow.api("/api/whatsapp/connect", {
                method: "POST",
                body: JSON.stringify(payload),
            });
            await loadData();
            setAlert(nodes.settingsAlert, response.message, "success");
            GrowFlow.setToast(response.message);
        } catch (error) {
            setAlert(nodes.settingsAlert, error.message, "error");
        }
    }

    function buildSendPayload() {
        const payload = {
            send_to: nodes.sendMode?.value || "selected_customers",
            template_selection: nodes.templateSelect?.value || "",
            message_type: nodes.messageType?.value || "text",
            mode: nodes.deliveryMode?.value || "auto",
            scheduled_for: nodes.scheduledFor?.value || "",
            message_content: nodes.messageContent?.value || "",
        };
        if (payload.send_to === "selected_customers") {
            payload.customer_ids = Array.from(nodes.sendCustomers?.selectedOptions || []).map((option) => option.value);
        } else if (payload.send_to === "single_customer") {
            payload.customer_id = nodes.sendSingle?.value || "";
        } else if (payload.send_to === "manual_number") {
            payload.customer_phone_number = nodes.sendManual?.value || "";
        }
        return payload;
    }

    nodes.saveButton?.addEventListener("click", () => {
        saveConnection(false).catch(handleFatalPageError);
    });
    nodes.connectButton?.addEventListener("click", () => {
        if (nodes.connectButton.disabled) {
            GrowFlow.setToast("Live WhatsApp verification is locked on this plan.", "error");
            return;
        }
        saveConnection(true).catch(handleFatalPageError);
    });
    nodes.disconnectButton?.addEventListener("click", async () => {
        clearAlert(nodes.settingsAlert);
        try {
            const response = await GrowFlow.api("/api/whatsapp/disconnect", {
                method: "POST",
                body: JSON.stringify({}),
            });
            await loadData();
            setAlert(nodes.settingsAlert, response.message, "success");
            GrowFlow.setToast(response.message);
        } catch (error) {
            setAlert(nodes.settingsAlert, error.message, "error");
        }
    });

    nodes.sendMode?.addEventListener("change", updateRecipientModeDisplay);
    nodes.templateSelect?.addEventListener("change", (event) => {
        applyTemplate(event.currentTarget.value);
    });

    nodes.sendForm?.addEventListener("submit", async (event) => {
        event.preventDefault();
        clearAlert(nodes.sendAlert);
        try {
            const response = await GrowFlow.api("/api/whatsapp/send", {
                method: "POST",
                body: JSON.stringify(buildSendPayload()),
            });
            await loadData();
            setAlert(nodes.sendAlert, response.message, "success");
            GrowFlow.setToast(response.message);
        } catch (error) {
            setAlert(nodes.sendAlert, error.message, "error");
        }
    });

    nodes.templateForm?.addEventListener("submit", async (event) => {
        event.preventDefault();
        clearAlert(nodes.templateAlert);
        try {
            const payload = Object.fromEntries(new FormData(nodes.templateForm).entries());
            if (!payload.id) {
                delete payload.id;
            }
            const response = await GrowFlow.api("/api/whatsapp/templates", {
                method: "POST",
                body: JSON.stringify(payload),
            });
            await loadData();
            resetTemplateForm();
            setAlert(nodes.templateAlert, response.message, "success");
            GrowFlow.setToast(response.message);
        } catch (error) {
            setAlert(nodes.templateAlert, error.message, "error");
        }
    });

    nodes.templateReset?.addEventListener("click", resetTemplateForm);

    nodes.templateLibrary?.addEventListener("click", async (event) => {
        const button = event.target.closest("[data-template-action]");
        if (!button) {
            return;
        }
        const action = button.dataset.templateAction;
        if (action === "use") {
            applyTemplate(button.dataset.selection);
            GrowFlow.setToast("Template loaded.");
            return;
        }

        const templateId = Number(button.dataset.id);
        const template = state.templates.find((row) => row.id === templateId);
        if (!template) {
            return;
        }

        if (action === "edit") {
            if (nodes.templateId) {
                nodes.templateId.value = String(template.id);
            }
            if (nodes.templateName) {
                nodes.templateName.value = template.template_name;
            }
            if (nodes.templateCategory) {
                nodes.templateCategory.value = template.category;
            }
            if (nodes.templateContent) {
                nodes.templateContent.value = template.content;
            }
            window.scrollTo({ top: 0, behavior: "smooth" });
            return;
        }

        if (!window.confirm(`Delete template "${template.template_name}"?`)) {
            return;
        }
        try {
            const response = await GrowFlow.api(`/api/whatsapp/templates/${template.id}`, { method: "DELETE" });
            await loadData();
            GrowFlow.setToast(response.message);
        } catch (error) {
            GrowFlow.setToast(error.message, "error");
        }
    });

    updateRecipientModeDisplay();
    await loadData();
}

async function initAiToolsPage() {
    const nodes = {
        alert: document.getElementById("ai-alert"),
        businessName: document.getElementById("ai-business-name"),
        contentType: document.getElementById("ai-content-type"),
        prompt: document.getElementById("ai-prompt"),
        form: document.getElementById("ai-generate-form"),
        output: document.getElementById("ai-output"),
        posterPreview: document.getElementById("ai-poster-preview"),
        providerStatus: document.getElementById("ai-provider-status"),
        providerSource: document.getElementById("ai-provider-source"),
        providerNote: document.getElementById("ai-provider-note"),
        refreshStatus: document.getElementById("ai-refresh-status"),
    };

    let providerState = null;

    async function loadProviderStatus() {
        const response = await GrowFlow.api("/api/settings/api-management");
        providerState = response.api_management || null;
        if (providerState) {
            nodes.providerStatus.textContent = `Status: ${providerState.status || "unknown"}`;
            nodes.providerSource.textContent = `Source: ${providerState.source || "none"}`;
            nodes.providerNote.textContent = providerState.configured
                ? `Groq is configured with a ${providerState.masked_key ? "masked key" : "server-side environment key"}. Model: ${providerState.model}.`
                : "Groq is not configured yet. Add a key in API Settings to enable external AI responses.";
        }
    }

    function renderResult(result) {
        nodes.output.textContent = result.content || "No AI output returned.";
        if (result.poster_svg) {
            nodes.posterPreview.innerHTML = result.poster_svg;
            nodes.posterPreview.classList.remove("hidden");
        } else {
            nodes.posterPreview.innerHTML = "";
            nodes.posterPreview.classList.add("hidden");
        }
        const statusMessage = result.used_fallback
            ? result.warning || "Generated with local fallback content."
            : `Generated using ${result.provider || "groq"}.`;
        setAlert(nodes.alert, statusMessage, result.used_fallback ? "error" : "success");
    }

    async function requestAi(endpoint, payload) {
        clearAlert(nodes.alert);
        const response = await GrowFlow.api(endpoint, {
            method: "POST",
            body: JSON.stringify(payload),
        });
        renderResult(response.result || {});
        await loadProviderStatus().catch(() => {});
        GrowFlow.setToast("AI output ready.");
    }

    document.querySelectorAll("[data-ai-prompt]").forEach((button) => {
        button.addEventListener("click", () => {
            const endpoint = button.dataset.aiType === "poster"
                ? "/api/ai/generate-poster"
                : button.dataset.aiType === "marketing"
                ? "/api/ai/generate-marketing-message"
                : "/api/ai/generate-content";
            requestAi(endpoint, {
                business_name: nodes.businessName.value,
                content_type: button.dataset.aiType,
                type: button.dataset.aiType,
                prompt: button.dataset.aiPrompt,
            }).catch((error) => setAlert(nodes.alert, error.message, "error"));
        });
    });

    nodes.form.addEventListener("submit", async (event) => {
        event.preventDefault();
        try {
            await requestAi("/api/ai/generate-content", {
                business_name: nodes.businessName.value,
                content_type: nodes.contentType.value,
                type: nodes.contentType.value,
                prompt: nodes.prompt.value,
            });
        } catch (error) {
            setAlert(nodes.alert, error.message, "error");
        }
    });

    nodes.refreshStatus?.addEventListener("click", () => {
        loadProviderStatus().catch((error) => setAlert(nodes.alert, error.message, "error"));
    });

    await loadProviderStatus();
}

async function initApiSettingsPage() {
    const nodes = {
        form: document.getElementById("api-management-form"),
        alert: document.getElementById("api-management-alert"),
        recordList: document.getElementById("api-management-list"),
        statusChip: document.getElementById("api-management-status"),
        sourceChip: document.getElementById("api-management-source"),
        modelChip: document.getElementById("api-management-model-chip"),
        maskNode: document.getElementById("api-management-mask"),
        keyInput: document.getElementById("api-management-key"),
        modelInput: document.getElementById("api-management-model"),
        verifyInput: document.getElementById("api-management-verify"),
        testButton: document.getElementById("api-management-test"),
        clearButton: document.getElementById("api-management-clear"),
    };

    const state = { apiKeys: [], management: null };

    function render() {
        if (state.management) {
            nodes.statusChip.textContent = `Status: ${state.management.status || "unknown"}`;
            nodes.sourceChip.textContent = `Source: ${state.management.source || "none"}`;
            nodes.modelChip.textContent = `Model: ${state.management.model || "llama-3.3-70b-versatile"}`;
            nodes.maskNode.textContent = state.management.configured
                ? `Active Groq key: ${state.management.masked_key || "stored securely"}`
                : "No Groq API key is configured yet.";
            nodes.keyInput.placeholder = state.management.has_user_key
                ? "Enter a new Groq API key to update the saved one"
                : "Paste Groq API key here or leave blank to use GROQ_API_KEY";
            nodes.modelInput.value = state.management.model || "llama-3.3-70b-versatile";
            nodes.verifyInput.checked = true;
        }

        renderList(
            nodes.recordList,
            state.apiKeys,
            (row) => `
                <div class="flex items-start justify-between gap-4">
                    <div>
                        <p class="font-medium text-white">${escapeHtml(row.label)}</p>
                        <p class="mt-1 text-sm text-white/60">${escapeHtml(row.masked_key || "No key saved")}</p>
                        <p class="mt-2 text-xs text-white/45">Status: ${escapeHtml(row.status)}</p>
                    </div>
                    <div class="flex flex-wrap gap-2">
                        ${statusPill(row.status)}
                        <button type="button" class="action-btn border border-red-500/20 bg-red-950/30 text-red-100" data-api-delete="${escapeHtml(row.service_name)}">Delete</button>
                    </div>
                </div>
            `,
            "No API keys have been saved yet."
        );
    }

    async function loadData() {
        const [managementData, apiKeyData] = await Promise.all([
            GrowFlow.api("/api/settings/api-management"),
            GrowFlow.api("/api/settings/api-keys"),
        ]);
        state.management = managementData.api_management || null;
        state.apiKeys = apiKeyData.api_keys || [];
        render();
    }

    function refreshManagementState() {
        return loadData().catch((error) => setAlert(nodes.alert, error.message, "error"));
    }

    function buildPayload(verifyOverride = true) {
        return {
            api_key: nodes.keyInput.value,
            model: nodes.modelInput.value,
            verify: verifyOverride,
            service_name: "groq",
        };
    }

    nodes.form.addEventListener("submit", async (event) => {
        event.preventDefault();
        clearAlert(nodes.alert);
        try {
            const response = await GrowFlow.api("/api/settings/api-management", {
                method: "POST",
                body: JSON.stringify(buildPayload(nodes.verifyInput.checked)),
            });
            nodes.keyInput.value = "";
            await refreshManagementState();
            setAlert(nodes.alert, response.message, "success");
            GrowFlow.setToast(response.message);
        } catch (error) {
            setAlert(nodes.alert, error.message, "error");
        }
    });

    nodes.testButton?.addEventListener("click", async () => {
        clearAlert(nodes.alert);
        try {
            const response = await GrowFlow.api("/api/settings/api-management", {
                method: "POST",
                body: JSON.stringify({
                    api_key: "",
                    model: nodes.modelInput.value,
                    verify: true,
                    service_name: "groq",
                }),
            });
            await refreshManagementState();
            setAlert(nodes.alert, response.message, "success");
            GrowFlow.setToast(response.message);
        } catch (error) {
            setAlert(nodes.alert, error.message, "error");
        }
    });

    nodes.clearButton?.addEventListener("click", async () => {
        clearAlert(nodes.alert);
        try {
            const response = await GrowFlow.api("/api/settings/api-management", {
                method: "DELETE",
            });
            nodes.keyInput.value = "";
            await refreshManagementState();
            setAlert(nodes.alert, response.message, "success");
            GrowFlow.setToast(response.message);
        } catch (error) {
            setAlert(nodes.alert, error.message, "error");
        }
    });

    nodes.recordList.addEventListener("click", async (event) => {
        const button = event.target.closest("[data-api-delete]");
        if (!button) {
            return;
        }
        try {
            const response = await GrowFlow.api("/api/settings/api-keys", {
                method: "DELETE",
                body: JSON.stringify({ service_name: button.dataset.apiDelete }),
            });
            await refreshManagementState();
            setAlert(nodes.alert, response.message, "success");
            GrowFlow.setToast(response.message);
        } catch (error) {
            setAlert(nodes.alert, error.message, "error");
        }
    });

    await loadData();
}

async function initDatabasePage() {
    const nodes = {
        customers: document.getElementById("database-customers"),
        employees: document.getElementById("database-employees"),
        invoices: document.getElementById("database-invoices"),
        apiKeys: document.getElementById("database-api-keys"),
        summaryList: document.getElementById("database-summary-list"),
        alert: document.getElementById("database-alert"),
        backupButton: document.getElementById("download-backup-button"),
        csvButton: document.getElementById("download-csv-button"),
        restoreInput: document.getElementById("restore-backup-input"),
        restoreButton: document.getElementById("restore-backup-button"),
        deleteConfirm: document.getElementById("delete-data-confirm"),
        deleteButton: document.getElementById("delete-all-data-button"),
    };

    let summary = null;

    function render() {
        if (!summary) {
            return;
        }
        nodes.customers.textContent = String(summary.customers || 0);
        nodes.employees.textContent = String(summary.employees || 0);
        nodes.invoices.textContent = String(summary.invoices || 0);
        nodes.apiKeys.textContent = String(summary.api_keys || 0);

        const rows = [
            ["Customers", summary.customers],
            ["Employees", summary.employees],
            ["Invoices", summary.invoices],
            ["Templates", summary.templates],
            ["WhatsApp messages", summary.whatsapp_messages],
            ["Marketing logs", summary.marketing_logs],
            ["API keys", summary.api_keys],
        ];
        renderList(
            nodes.summaryList,
            rows,
            (row) => `
                <div class="flex items-center justify-between gap-4">
                    <p class="font-medium text-white">${escapeHtml(row[0])}</p>
                    <span class="mini-chip">${escapeHtml(String(row[1]))}</span>
                </div>
            `,
            "No data summary available."
        );
    }

    async function loadData() {
        const response = await GrowFlow.api("/api/settings/data");
        summary = response.data;
        render();
    }

    nodes.backupButton.addEventListener("click", async () => {
        try {
            await downloadAuthenticated("/api/backup/export", "growflow-backup.json");
            GrowFlow.setToast("Backup downloaded.");
        } catch (error) {
            setAlert(nodes.alert, error.message, "error");
        }
    });

    nodes.csvButton.addEventListener("click", async () => {
        try {
            await downloadAuthenticated("/api/settings/data?format=csv", "growflow-export-csv.zip");
            GrowFlow.setToast("CSV export downloaded.");
        } catch (error) {
            setAlert(nodes.alert, error.message, "error");
        }
    });

    nodes.restoreButton.addEventListener("click", async () => {
        clearAlert(nodes.alert);
        try {
            const response = await GrowFlow.api("/api/settings/data", {
                method: "POST",
                body: JSON.stringify({
                    action: "restore",
                    backup: nodes.restoreInput.value,
                }),
            });
            nodes.restoreInput.value = "";
            await loadData();
            setAlert(nodes.alert, response.message, "success");
            GrowFlow.setToast(response.message);
        } catch (error) {
            setAlert(nodes.alert, error.message, "error");
        }
    });

    nodes.deleteButton.addEventListener("click", async () => {
        clearAlert(nodes.alert);
        try {
            const response = await GrowFlow.api("/api/settings/data", {
                method: "DELETE",
                body: JSON.stringify({ confirm: nodes.deleteConfirm.value }),
            });
            nodes.deleteConfirm.value = "";
            await loadData();
            setAlert(nodes.alert, response.message, "success");
            GrowFlow.setToast(response.message);
        } catch (error) {
            setAlert(nodes.alert, error.message, "error");
        }
    });

    await loadData();
}

async function initAnalyticsPage() {
    const nodes = {
        totalSales: document.getElementById("analytics-total-sales"),
        campaignCount: document.getElementById("analytics-campaign-count"),
        pendingCount: document.getElementById("analytics-pending-count"),
        messageCount: document.getElementById("analytics-message-count"),
        salesChart: document.getElementById("analytics-sales-chart"),
        trendList: document.getElementById("analytics-trend-list"),
        customerList: document.getElementById("analytics-customer-list"),
        messageChart: document.getElementById("analytics-message-chart"),
    };

    const [dashboardData, invoicesData, customersData, messagesData] = await Promise.all([
        GrowFlow.api("/api/dashboard"),
        GrowFlow.api("/api/invoices"),
        GrowFlow.api("/api/customers"),
        GrowFlow.api("/api/whatsapp/messages"),
    ]);

    const invoices = invoicesData.invoices || [];
    const customers = customersData.customers || [];
    const messages = messagesData.messages || [];
    const totalSales = invoices
        .filter((row) => row.status === "paid")
        .reduce((sum, row) => sum + Number(row.amount || 0), 0);
    const pendingInvoices = invoices.filter((row) => row.status !== "paid");
    const collectionRate = invoices.length
        ? Math.round((invoices.filter((row) => row.status === "paid").length / invoices.length) * 100)
        : 0;

    nodes.totalSales.textContent = GrowFlow.formatCurrency(totalSales);
    nodes.campaignCount.textContent = String(dashboardData.stats.campaign_count || 0);
    nodes.pendingCount.textContent = String(pendingInvoices.length);
    nodes.messageCount.textContent = String(messages.length);
    buildBarChart(nodes.salesChart, dashboardData.growth_chart || []);

    const averageInvoice = invoices.length
        ? invoices.reduce((sum, row) => sum + Number(row.amount || 0), 0) / invoices.length
        : 0;
    renderList(
        nodes.trendList,
        [
            ["Average invoice value", GrowFlow.formatCurrency(averageInvoice)],
            ["Collection rate", `${collectionRate}%`],
            ["Customer base", `${customers.length} active`],
            ["WhatsApp live access", dashboardData.integrations.whatsapp_live_access ? "Enabled" : "Locked"],
        ],
        (row) => `
            <div class="flex items-center justify-between gap-4">
                <p class="font-medium text-white">${escapeHtml(row[0])}</p>
                <span class="mini-chip">${escapeHtml(row[1])}</span>
            </div>
        `,
        "No trend summary yet."
    );

    const customerTotals = invoices.reduce((accumulator, invoice) => {
        const bucket = accumulator[invoice.customer_id] || { name: invoice.customer_name, total: 0, count: 0 };
        bucket.total += Number(invoice.amount || 0);
        bucket.count += 1;
        accumulator[invoice.customer_id] = bucket;
        return accumulator;
    }, {});
    const topCustomers = Object.values(customerTotals)
        .sort((a, b) => b.total - a.total)
        .slice(0, 5);
    renderList(
        nodes.customerList,
        topCustomers,
        (row) => `
            <div class="flex items-center justify-between gap-4">
                <div>
                    <p class="font-medium text-white">${escapeHtml(row.name)}</p>
                    <p class="text-sm text-white/60">${row.count} invoice(s)</p>
                </div>
                <span class="mini-chip">${escapeHtml(GrowFlow.formatCurrency(row.total))}</span>
            </div>
        `,
        "No customer trend data available."
    );

    const summary = messagesData.summary || { total: 0, sent: 0, demo: 0, scheduled: 0, failed: 0 };
    const messageSummary = [
        ["Sent", summary.sent || 0],
        ["Demo", summary.demo || 0],
        ["Scheduled", summary.scheduled || 0],
        ["Failed", summary.failed || 0],
    ];
    const maxValue = Math.max(...messageSummary.map((row) => row[1]), 1);
    renderList(
        nodes.messageChart,
        messageSummary,
        (row) => `
            <div>
                <div class="flex items-center justify-between gap-4">
                    <p class="font-medium text-white">${escapeHtml(row[0])}</p>
                    <span class="mini-chip">${row[1]}</span>
                </div>
                <div class="progress-track mt-3">
                    <div class="progress-fill" style="width:${Math.round((row[1] / maxValue) * 100)}%"></div>
                </div>
            </div>
        `,
        "No message summary yet."
    );
}

async function initSubscriptionPage() {
    const nodes = {
        alert: document.getElementById("subscription-alert"),
        currentSummary: document.getElementById("subscription-current-summary"),
        quoteSummary: document.getElementById("subscription-quote-summary"),
        paymentSummary: document.getElementById("subscription-payment-summary"),
        historyList: document.getElementById("subscription-history-list"),
        promoForm: document.getElementById("subscription-promo-form"),
        promoCode: document.getElementById("subscription-promo-code"),
        applyButton: document.getElementById("subscription-apply-promo"),
        paymentButton: document.getElementById("subscription-payment-button"),
        paymentNote: document.getElementById("subscription-payment-note"),
    };

    let payload = null;

    function render() {
        const current = payload?.current || null;
        const quote = payload?.quote || {};
        const access = payload?.access || {};
        const paymentGateways = payload?.payment_gateways || {};
        const notice = payload?.notice || "";
        const amountDue = Number(quote.amount_due ?? current?.amount_due ?? 200);
        const paymentPending = Boolean(current?.payment_pending || quote.payment_pending);
        const freeActivation = amountDue <= 0;
        const paymentReference = current?.payment_reference || quote.payment_reference || "";

        GrowFlow.setSubscriptionState(payload);
        nodes.currentSummary.innerHTML = current
            ? `
                <div class="soft-panel">
                    <p class="font-semibold text-white">${escapeHtml(current.label || "Subscription")}</p>
                    <p class="mt-2 text-sm text-white/65">${escapeHtml(current.price_label || "Rs 200/month")} - ${escapeHtml(current.status || "active")}</p>
                    <div class="mt-3 flex flex-wrap gap-2">
                        <span class="mini-chip">${escapeHtml(current.trial_active ? "Trial active" : current.trial_expired ? "Trial expired" : current.premium_active ? "Pro active" : "Free plan")}</span>
                        <span class="mini-chip">${escapeHtml(current.trial_days_left !== null && current.trial_days_left !== undefined ? `${current.trial_days_left} day(s) left` : current.next_renewal_on || "Billing ready")}</span>
                        <span class="mini-chip">${escapeHtml(current.payment_status || "pending")}</span>
                    </div>
                    <p class="mt-3 text-xs text-white/45">Renewed on ${escapeHtml(current.renewed_on || "not available")}</p>
                    ${current.upgrade_prompt_shown_at ? `<p class="mt-2 text-xs text-white/45">Upgrade prompt shown at ${escapeHtml(current.upgrade_prompt_shown_at)}</p>` : ""}
                </div>
            `
            : `<div class="soft-panel text-sm text-white/65">No active subscription found.</div>`;

        nodes.quoteSummary.innerHTML = `
            <div class="soft-panel">
                <p class="font-semibold text-white">Upgrade quote</p>
                <p class="mt-2 text-sm text-white/65">Base price: ${escapeHtml(GrowFlow.formatCurrency(quote.base_amount || 200))}</p>
                <p class="mt-2 text-sm text-white/65">Discount: ${escapeHtml(quote.discount_percent ? `${quote.discount_percent}% (${GrowFlow.formatCurrency(quote.discount_amount || 0)})` : "No discount applied")}</p>
                <p class="mt-2 text-sm text-white/65">Amount due: ${escapeHtml(GrowFlow.formatCurrency(amountDue))}</p>
                <p class="mt-2 text-xs text-white/45">${escapeHtml(paymentGateways.default_provider === "razorpay" ? "Razorpay checkout is available." : "Demo checkout will activate Pro immediately in this environment.")}</p>
            </div>
        `;

        nodes.paymentSummary.innerHTML = `
            <div class="soft-panel">
                <p class="font-semibold text-white">Upgrade status</p>
                <p class="mt-2 text-sm text-white/65">${escapeHtml(freeActivation ? "Promo code applied. Activate Pro for free." : notice || "Upgrade to Pro to keep premium tools active.")}</p>
                <div class="mt-3 flex flex-wrap gap-2">
                    <span class="mini-chip">${escapeHtml(access.trial_active ? "Trial active" : "Trial closed")}</span>
                    <span class="mini-chip">${escapeHtml(access.premium_active ? "Pro active" : "Pro locked")}</span>
                    <span class="mini-chip">${escapeHtml(paymentPending ? "Payment pending" : "Payment ready")}</span>
                </div>
                ${paymentReference ? `<p class="mt-3 text-xs text-white/45">Payment reference: ${escapeHtml(paymentReference)}</p>` : ""}
            </div>
        `;

        renderList(
            nodes.historyList,
            payload?.billing_history || [],
            (row) => `
                <div class="flex items-center justify-between gap-4">
                    <div>
                        <p class="font-medium text-white">${escapeHtml(row.label)}</p>
                        <p class="text-sm text-white/60">${escapeHtml(row.price_label)}</p>
                    </div>
                    <div class="text-right">
                        ${statusPill(row.status)}
                        <p class="mt-2 text-xs text-white/45">${escapeHtml(row.renewed_on)}</p>
                    </div>
                </div>
            `,
            "No billing history yet."
        );

        if (nodes.paymentNote) {
            nodes.paymentNote.textContent = freeActivation
                ? "Promo applied. No payment is required. Activate Pro instantly."
                : notice || nodes.paymentNote.textContent;
        }
        if (nodes.applyButton) {
            nodes.applyButton.disabled = false;
        }
        if (nodes.paymentButton) {
            nodes.paymentButton.textContent = paymentPending
                ? "Verify payment"
                : freeActivation
                    ? "Activate for free"
                    : paymentGateways.default_provider === "razorpay"
                        ? "Pay with Razorpay"
                        : "Upgrade now";
            nodes.paymentButton.dataset.provider = freeActivation
                ? "promo"
                : paymentPending
                    ? (current?.payment_provider || paymentGateways.default_provider || "razorpay")
                    : (paymentGateways.default_provider || "demo");
            nodes.paymentButton.dataset.paymentReference = paymentReference;
        }
    }

    async function loadData() {
        const response = await GrowFlow.api("/api/subscription/status");
        payload = response.subscription;
        render();
    }

    async function applyPromoCode(promoCode) {
        clearAlert(nodes.alert);
        try {
            const response = await GrowFlow.api("/api/subscription/apply-promo", {
                method: "POST",
                body: JSON.stringify({ promo_code: promoCode }),
            });
            payload = response.subscription || payload;
            await loadData();
            setAlert(nodes.alert, response.message, "success");
            GrowFlow.setToast(response.message);
        } catch (error) {
            setAlert(nodes.alert, error.message, "error");
        }
    }

    async function handlePayment() {
        clearAlert(nodes.alert);
        try {
            const body = {
                provider: nodes.paymentButton.dataset.provider || "demo",
            };
            const promoCode = (nodes.promoCode?.value || "").trim();
            if (promoCode) {
                body.promo_code = promoCode;
            }
            if (nodes.paymentButton.dataset.paymentReference) {
                body.payment_link_id = nodes.paymentButton.dataset.paymentReference;
            }
            const response = await GrowFlow.api("/api/subscription/payment", {
                method: "POST",
                body: JSON.stringify(body),
            });
            if (response.checkout?.short_url) {
                window.open(response.checkout.short_url, "_blank", "noopener,noreferrer");
            }
            if (response.subscription?.current) {
                payload = response.subscription;
                GrowFlow.setSubscriptionState(response);
                render();
                setAlert(nodes.alert, response.message, "success");
                GrowFlow.setToast(response.message);
                return;
            }
            if (response.subscription?.plan_code) {
                setAlert(nodes.alert, response.message, "success");
                GrowFlow.setToast(response.message);
                window.location.reload();
                return;
            }
            GrowFlow.setSubscriptionState(response);
            await loadData();
            setAlert(nodes.alert, response.message, "success");
            GrowFlow.setToast(response.message);
        } catch (error) {
            setAlert(nodes.alert, error.message, "error");
        }
    }

    nodes.promoForm?.addEventListener("submit", async (event) => {
        event.preventDefault();
        await applyPromoCode((nodes.promoCode?.value || "").trim());
    });

    nodes.paymentButton?.addEventListener("click", async () => {
        await handlePayment();
    });

    await loadData();
}

async function initSettingsPage() {
    const nodes = {
        accountForm: document.getElementById("settings-account-form"),
        accountAlert: document.getElementById("settings-account-alert"),
        accountName: document.getElementById("settings-account-name"),
        accountEmail: document.getElementById("settings-account-email"),
        accountPhone: document.getElementById("settings-account-phone"),
        accountBusiness: document.getElementById("settings-account-business"),
        preferencesForm: document.getElementById("settings-preferences-form"),
        preferencesAlert: document.getElementById("settings-preferences-alert"),
        emailNotifications: document.getElementById("settings-email-notifications"),
        whatsappNotifications: document.getElementById("settings-whatsapp-notifications"),
        smsAlerts: document.getElementById("settings-sms-alerts"),
        theme: document.getElementById("settings-theme"),
        language: document.getElementById("settings-language"),
        securityForm: document.getElementById("settings-security-form"),
        securityAlert: document.getElementById("settings-security-alert"),
        twoFactor: document.getElementById("settings-two-factor"),
        save2faButton: document.getElementById("settings-save-2fa"),
        logoutAllButton: document.getElementById("settings-logout-all"),
        authSummary: document.getElementById("settings-auth-summary"),
        securitySummary: document.getElementById("settings-security-summary"),
        passwordResetButton: document.getElementById("settings-password-reset"),
    };

    const state = {
        account: null,
        preferences: null,
        security: null,
        auth: null,
    };

    function render() {
        const supabaseAuth = state.auth?.auth_provider === "supabase";
        if (state.account) {
            nodes.accountName.value = state.account.name || "";
            nodes.accountEmail.value = state.account.email || "";
            nodes.accountPhone.value = state.account.phone_number || "";
            nodes.accountBusiness.value = state.account.business_name || "";
        }
        const emailLocked = supabaseAuth;
        nodes.accountEmail.readOnly = emailLocked;
        nodes.accountEmail.title = emailLocked
            ? "Email is managed by Supabase authentication."
            : "";
        nodes.accountEmail.classList.toggle("cursor-not-allowed", emailLocked);
        nodes.accountEmail.classList.toggle("opacity-70", emailLocked);
        if (state.preferences) {
            nodes.emailNotifications.checked = !!state.preferences.email_notifications;
            nodes.whatsappNotifications.checked = !!state.preferences.whatsapp_notifications;
            nodes.smsAlerts.checked = !!state.preferences.sms_alerts;
            nodes.theme.value = state.preferences.theme || "dark";
            nodes.language.value = state.preferences.language || "english";
            applyTheme(nodes.theme.value);
        }
        if (state.security) {
            nodes.twoFactor.checked = !!state.security.two_factor_enabled;
            renderList(
                nodes.securitySummary,
                [
                    ["Two-factor preference", state.security.two_factor_enabled ? "Enabled" : "Disabled"],
                    ["Session version", state.security.session_version],
                    ["API key encryption", state.security.api_key_encryption ? "Enabled" : "Disabled"],
                ],
                (row) => `
                    <div class="flex items-center justify-between gap-4">
                        <p class="font-medium text-white">${escapeHtml(row[0])}</p>
                        <span class="mini-chip">${escapeHtml(String(row[1]))}</span>
                    </div>
                `,
                "No security details available."
            );
        }
        if (state.auth) {
            renderList(
                nodes.authSummary,
                [
                    ["Provider", state.auth.provider_label || "Supabase Auth"],
                    ["Login method", state.auth.login_method || "Email + password"],
                    ["Password reset", state.auth.password_reset_enabled ? "Available" : "Unavailable"],
                    ["Password change", supabaseAuth ? "Managed by Supabase" : "Available in app"],
                ],
                (row) => `
                    <div class="flex items-center justify-between gap-4">
                        <p class="font-medium text-white">${escapeHtml(row[0])}</p>
                        <span class="mini-chip">${escapeHtml(row[1])}</span>
                    </div>
                `,
                "No authentication settings available."
            );
        }

        if (nodes.securityForm) {
            nodes.securityForm.querySelectorAll("input, button").forEach((element) => {
                if (element.name === "current_password" || element.name === "new_password" || element.type === "submit") {
                    element.disabled = supabaseAuth;
                }
            });
            nodes.securityForm.classList.toggle("opacity-60", supabaseAuth);
        }
    }

    async function loadData() {
        const [accountData, preferencesData, securityData, authData] = await Promise.all([
            GrowFlow.api("/api/settings/account"),
            GrowFlow.api("/api/settings/notifications"),
            GrowFlow.api("/api/settings/security"),
            GrowFlow.api("/api/settings/auth"),
        ]);
        state.account = accountData.account;
        state.preferences = preferencesData.preferences;
        state.security = securityData.security;
        state.auth = authData.auth;
        render();
    }

    nodes.accountForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        clearAlert(nodes.accountAlert);
        try {
            const payload = Object.fromEntries(new FormData(nodes.accountForm).entries());
            const response = await GrowFlow.api("/api/settings/account", {
                method: "POST",
                body: JSON.stringify(payload),
            });
            if (response.user) {
                GrowFlow.saveSession(localStorage.getItem("growflowToken"), response.user);
            }
            await loadData();
            setAlert(nodes.accountAlert, response.message, "success");
            GrowFlow.setToast(response.message);
        } catch (error) {
            setAlert(nodes.accountAlert, error.message, "error");
        }
    });

    nodes.preferencesForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        clearAlert(nodes.preferencesAlert);
        try {
            const response = await GrowFlow.api("/api/settings/notifications", {
                method: "POST",
                body: JSON.stringify({
                    email_notifications: nodes.emailNotifications.checked,
                    whatsapp_notifications: nodes.whatsappNotifications.checked,
                    sms_alerts: nodes.smsAlerts.checked,
                    theme: nodes.theme.value,
                    language: nodes.language.value,
                }),
            });
            applyTheme(nodes.theme.value);
            await loadData();
            setAlert(nodes.preferencesAlert, response.message, "success");
            GrowFlow.setToast(response.message);
        } catch (error) {
            setAlert(nodes.preferencesAlert, error.message, "error");
        }
    });

    nodes.theme.addEventListener("change", () => applyTheme(nodes.theme.value));

    nodes.securityForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        clearAlert(nodes.securityAlert);
        try {
            const payload = Object.fromEntries(new FormData(nodes.securityForm).entries());
            payload.action = "change_password";
            const response = await GrowFlow.api("/api/settings/security", {
                method: "POST",
                body: JSON.stringify(payload),
            });
            if (response.token && response.user) {
                GrowFlow.saveSession(response.token, response.user);
            }
            nodes.securityForm.reset();
            await loadData();
            setAlert(nodes.securityAlert, response.message, "success");
            GrowFlow.setToast(response.message);
        } catch (error) {
            setAlert(nodes.securityAlert, error.message, "error");
        }
    });

    nodes.save2faButton.addEventListener("click", async () => {
        clearAlert(nodes.securityAlert);
        try {
            const response = await GrowFlow.api("/api/settings/security", {
                method: "POST",
                body: JSON.stringify({
                    action: "toggle_2fa",
                    enabled: nodes.twoFactor.checked,
                }),
            });
            await loadData();
            setAlert(nodes.securityAlert, response.message, "success");
            GrowFlow.setToast(response.message);
        } catch (error) {
            setAlert(nodes.securityAlert, error.message, "error");
        }
    });

    nodes.logoutAllButton.addEventListener("click", async () => {
        clearAlert(nodes.securityAlert);
        try {
            const response = await GrowFlow.api("/api/settings/security", {
                method: "POST",
                body: JSON.stringify({ action: "logout_all" }),
            });
            setAlert(nodes.securityAlert, response.message, "success");
            GrowFlow.setToast(response.message);
            GrowFlow.clearSession();
            window.setTimeout(() => {
                window.location.href = "/auth";
            }, 500);
        } catch (error) {
            setAlert(nodes.securityAlert, error.message, "error");
        }
    });

    nodes.passwordResetButton.addEventListener("click", async () => {
        try {
            const response = await GrowFlow.api("/api/settings/auth", {
                method: "POST",
                body: JSON.stringify({ action: "password_reset" }),
            });
            GrowFlow.setToast(response.message);
        } catch (error) {
            GrowFlow.setToast(error.message, "error");
        }
    });

    await loadData();
}

async function initSupportPage() {
    await GrowFlow.api("/api/dashboard");
}
