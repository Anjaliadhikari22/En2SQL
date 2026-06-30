/**
 * En2SQL — Frontend Application
 * Communicates with Flask backend at http://localhost:5000
 */

document.addEventListener("DOMContentLoaded", () => {

const API_BASE_URL = "http://127.0.0.1:5000";
const API_BASE = API_BASE_URL;

const SAMPLE_PROMPTS = [
  "Show all employees whose salary is greater than 50000",
  "Find the top 5 highest-paid employees",
  "Show employee name with department name",
  "Find the top 2 highest-paid employees within each department",
  "Find top 3 products by total sales revenue",
  "Show students enrolled in each course",
  "Show doctors with their appointments",
  "Show 3 random employees",
  "Count employees in each department",
];

const DESTRUCTIVE_TYPES = new Set(["UPDATE", "DELETE", "TRANSACTION"]);
const STORAGE_KEY = "en2sql.frontendState";
const AUTH_TOKEN_KEY = "en2sql.token";
const AUTH_ROLE_KEY = "en2sql.role";
const AUTH_NAME_KEY = "en2sql.name";
const AUTH_EMAIL_KEY = "en2sql.email";

const authToken = localStorage.getItem(AUTH_TOKEN_KEY);
const authRole = localStorage.getItem(AUTH_ROLE_KEY);
const authName = localStorage.getItem(AUTH_NAME_KEY) || localStorage.getItem(AUTH_EMAIL_KEY) || "";

if (!authToken || !["admin", "user"].includes(authRole || "")) {
  window.location.href = "login.html";
  return;
}

// Persistent application state
const appState = {
  currentResponse: null,
  selectedQuery: "",
  queryType: "",
  databaseType: "mysql",
  schemaPack: "hr",
};

let backendOnline = false;
let demoMode = true;

// DOM
const $ = (id) => document.getElementById(id);

const promptInput = $("prompt");
const dbTypeSelect = $("db-type");
const btnGenerate = $("btn-generate");
const btnExecute = $("btn-execute");
const btnClear = $("btn-clear");
const btnCopySql = $("btn-copy-sql");
const btnLoadHistory = $("btn-load-history");
const btnLoadSchema = $("btn-load-schema");
const btnViewSchema = $("btn-view-schema");
const btnLogout = $("btn-logout");
const roleBadge = $("role-badge");
const roleNote = $("role-note");

const backendError = $("backend-error");
const statusBadge = $("status-badge");
const outputEmpty = $("output-empty");
const outputResults = $("output-results");
const unsupportedCard = $("unsupported-card");
const unsupportedMessage = $("unsupported-message");
const unsupportedWarning = $("unsupported-warning");
const unsupportedOptimization = $("unsupported-optimization");
const sqlBlock = $("sql-block");
const detailsTabs = $("details-tabs");
const queryOptionsCard = $("query-options-card");
const queryOptionsContainer = $("query-options");

const outputSql = $("output-sql");
const queryTypeBadge = $("query-type-badge");
const databaseBadge = $("database-badge");
const validationBadge = $("validation-badge");
const warningBadge = $("warning-badge");

const outputExplanation = $("output-explanation");
const outputTables = $("output-tables");
const outputColumns = $("output-columns");
const outputImpact = $("output-impact");
const outputOptimization = $("output-optimization");
const outputWarning = $("output-warning");

const executionBlock = $("execution-block");
const executionMessage = $("execution-message");
const executionThead = $("execution-thead");
const executionTbody = $("execution-tbody");
const demoModeNote = $("demo-mode-note");
const executeSection = document.querySelector(".execute-section");

const schemaDrawer = $("schema-drawer");
const schemaContent = $("schema-content");
const schemaMode = $("schema-mode");
const historyDrawer = $("history-drawer");
const historyList = $("history-list");
const sampleButtonsContainer = $("sample-buttons");

const confirmModal = $("confirm-modal");
const confirmBackdrop = confirmModal.querySelector(".modal__backdrop");
const confirmTitle = $("confirm-title");
const confirmMessage = $("confirm-message");
const confirmOk = $("confirm-ok");
const confirmCancel = $("confirm-cancel");
const toastEl = $("toast");

// ---------------------------------------------------------------------------
// API
// ---------------------------------------------------------------------------

async function apiPost(endpoint, body) {
  const response = await fetch(`${API_BASE}${endpoint}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${authToken}`,
    },
    body: JSON.stringify(body),
  });
  let data;
  try { data = await response.json(); } catch { throw new Error(`Invalid response (${response.status})`); }
  if (response.status === 401) handleAuthExpired();
  if (!response.ok) throw new Error(data.error || data.message || `Request failed (${response.status})`);
  return data;
}

async function apiGet(endpoint) {
  const response = await fetch(`${API_BASE}${endpoint}`, {
    headers: { "Authorization": `Bearer ${authToken}` },
  });
  let data;
  try { data = await response.json(); } catch { throw new Error(`Invalid response (${response.status})`); }
  if (response.status === 401) handleAuthExpired();
  if (!response.ok) throw new Error(data.error || `Request failed (${response.status})`);
  return data;
}

function handleAuthExpired() {
  localStorage.removeItem(AUTH_TOKEN_KEY);
  localStorage.removeItem(AUTH_ROLE_KEY);
  localStorage.removeItem(AUTH_NAME_KEY);
  localStorage.removeItem(AUTH_EMAIL_KEY);
  sessionStorage.removeItem(STORAGE_KEY);
  window.location.href = "login.html";
}

async function checkBackendHealth() {
  try {
    const data = await apiGet("/api/health");
    backendOnline = data.status === "ok";
    demoMode = data.database?.mode === "demo" || !data.database?.connected;
    backendError.hidden = true;
    statusBadge.textContent = demoMode ? "Demo Mode" : "Backend Connected";
    statusBadge.className = "status-badge " + (demoMode ? "status-badge--demo" : "status-badge--connected");
    demoModeNote.hidden = !demoMode || !appState.selectedQuery;
  } catch {
    backendOnline = false;
    backendError.hidden = false;
    statusBadge.textContent = "Offline";
    statusBadge.className = "status-badge status-badge--offline";
  }
}

// ---------------------------------------------------------------------------
// Utilities
// ---------------------------------------------------------------------------

function showToast(message, type = "info", duration = 3500) {
  toastEl.textContent = message;
  toastEl.className = "toast" + (type === "error" ? " toast--error" : type === "success" ? " toast--success" : "");
  toastEl.hidden = false;
  setTimeout(() => { toastEl.hidden = true; }, duration);
}

function escapeHtml(text) {
  const d = document.createElement("div");
  d.textContent = text ?? "";
  return d.innerHTML;
}

function formatTimestamp(iso) {
  try { return new Date(iso).toLocaleString(); } catch { return iso || ""; }
}

function userFacingQueries(queries) {
  if (!queries?.length) return [];
  return queries.filter((q) => !/^\s*SELECT\s+COUNT\s*\(\s*\*\s*\)\s+AS\s+RowCount/i.test(q));
}

function getSelectedQuery() {
  return appState.selectedQuery;
}

function getQueryOptionLabel(sql, index) {
  if (/ROW_NUMBER\s*\(\s*\)\s+OVER/i.test(sql)) {
    return "Recommended: ROW_NUMBER ranking";
  }
  if (/DENSE_RANK\s*\(\s*\)\s+OVER/i.test(sql)) {
    return "Handles ties: DENSE_RANK ranking";
  }
  if (/COUNT\s*\(\s*DISTINCT\s+e2\.salary\s*\)/i.test(sql)) {
    return "Alternative: Correlated subquery";
  }
  return `Option ${index + 1}`;
}

function getStructuredOptions(data) {
  return [data?.recommended_query, data?.alternative_query].filter((option) => option?.sql);
}

function renderBullets(items) {
  const list = document.createElement("ul");
  list.className = "option-bullets";
  (Array.isArray(items) ? items : [items]).filter(Boolean).forEach((item) => {
    const li = document.createElement("li");
    li.textContent = item;
    list.appendChild(li);
  });
  return list;
}

function generationSourceLabel(source) {
  const labels = {
    llm: "Generated using GenAI assistance",
    llm_fallback_rule_based: "Generated using safe fallback",
  };
  return labels[source] || "";
}

async function copySql(sql, button) {
  if (!sql) return;
  try {
    await navigator.clipboard.writeText(sql);
    const original = button?.textContent || "Copy SQL";
    if (button) {
      button.textContent = "Copied!";
      button.classList.add("copied");
      setTimeout(() => {
        button.textContent = original;
        button.classList.remove("copied");
      }, 1800);
    }
    showToast("SQL copied to clipboard", "success", 2000);
  } catch {
    showToast("Could not copy to clipboard", "error");
  }
}

function persistState() {
  sessionStorage.setItem(STORAGE_KEY, JSON.stringify({
    appState,
    prompt: promptInput.value,
    role: authRole,
  }));
}

function restoreState() {
  try {
    const saved = JSON.parse(sessionStorage.getItem(STORAGE_KEY) || "null");
    if (!saved) return;
    if (saved.role && saved.role !== authRole) {
      sessionStorage.removeItem(STORAGE_KEY);
      return;
    }

    appState.currentResponse = saved.appState?.currentResponse || null;
    appState.selectedQuery = saved.appState?.selectedQuery || "";
    appState.queryType = saved.appState?.queryType || "";
    appState.databaseType = saved.appState?.databaseType || "mysql";
    appState.schemaPack = saved.appState?.schemaPack || "hr";
    promptInput.value = saved.prompt || "";
    dbTypeSelect.value = appState.databaseType;

    if (appState.currentResponse && (
      appState.selectedQuery ||
      appState.queryType === "UNSUPPORTED_SCHEMA" ||
      appState.queryType === "UNSUPPORTED_DOMAIN" ||
      appState.queryType === "MULTIPLE_PROMPTS_DETECTED" ||
      appState.queryType === "INVALID_PROMPT" ||
      appState.queryType === "UNSAFE_REQUEST"
    )) {
      displayResults(appState.currentResponse);
    }
  } catch {
    sessionStorage.removeItem(STORAGE_KEY);
  }
}

function setGenerateLoading(on) {
  btnGenerate.classList.toggle("loading", on);
  btnGenerate.disabled = on;
  btnGenerate.querySelector(".btn__spinner").hidden = !on;
}

function setGlobalLoading(on) {
  document.body.style.pointerEvents = on ? "none" : "";
  document.body.style.opacity = on ? "0.85" : "";
}

function isAdmin() {
  return authRole === "admin";
}

function setElementHidden(el, hidden) {
  if (el) el.hidden = hidden;
}

function applyRoleAccess() {
  const admin = isAdmin();
  document.body.classList.toggle("role-admin", admin);
  document.body.classList.toggle("role-user", !admin);

  if (roleBadge) {
    roleBadge.textContent = admin ? "Admin Workspace" : "User Workspace";
    roleBadge.className = "role-badge " + (admin ? "role-badge--admin" : "role-badge--user");
    roleBadge.title = authName ? `Signed in as ${authName}` : "";
  }

  if (roleNote) {
    roleNote.textContent = admin
      ? "Full access enabled."
      : "User mode allows SQL generation and explanation only. Schema, history, and execution are restricted.";
  }

  setElementHidden(btnLoadSchema, !admin);
  setElementHidden(btnLoadHistory, !admin);
  setElementHidden(executeSection, executeSection?.dataset.optionMode === "true" || !admin || !appState.selectedQuery);
  setElementHidden(executionBlock, !admin || executionBlock.hidden);
  setElementHidden(schemaDrawer, !admin || schemaDrawer.hidden);
  setElementHidden(historyDrawer, !admin || historyDrawer.hidden);

  document.querySelectorAll('.tab-btn[data-tab="tables"], .tab-btn[data-tab="columns"]').forEach((el) => {
    el.hidden = !admin;
  });
  ["tab-tables", "tab-columns"].forEach((id) => {
    const pane = $(id);
    if (pane) pane.hidden = !admin;
  });

  if (!admin) {
    const activeHiddenTab = document.querySelector(".tab-btn.active[hidden]");
    if (activeHiddenTab) activateExplanationTab();
  }
}

function renderTagList(el, items, empty = "None detected") {
  el.innerHTML = "";
  if (!items?.length) {
    const li = document.createElement("li");
    li.className = "empty-tag";
    li.textContent = empty;
    el.appendChild(li);
    return;
  }
  items.forEach((item) => {
    const li = document.createElement("li");
    li.textContent = item;
    el.appendChild(li);
  });
}

function normalizeBulletText(text) {
  return String(text || "").replace(/^\s*[-•]\s*/, "").trim();
}

function renderExplanation(value) {
  outputExplanation.innerHTML = "";

  const items = Array.isArray(value)
    ? value
    : typeof value === "string" && value.includes("\n")
      ? value.split(/\n+/)
      : [];

  const bullets = items.map(normalizeBulletText).filter(Boolean);

  if (bullets.length > 1) {
    const ul = document.createElement("ul");
    ul.className = "detail-list";
    bullets.forEach((text) => {
      const li = document.createElement("li");
      li.textContent = text;
      ul.appendChild(li);
    });
    outputExplanation.appendChild(ul);
    return;
  }

  outputExplanation.textContent = normalizeBulletText(value) || "—";
}

function activateExplanationTab() {
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.tab === "explanation");
  });
  document.querySelectorAll(".tab-pane").forEach((pane) => {
    pane.classList.toggle("active", pane.id === "tab-explanation");
  });
}

// ---------------------------------------------------------------------------
// Tabs
// ---------------------------------------------------------------------------

function initTabs() {
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
      document.querySelectorAll(".tab-pane").forEach((p) => p.classList.remove("active"));
      btn.classList.add("active");
      $("tab-" + btn.dataset.tab)?.classList.add("active");
    });
  });
}

// ---------------------------------------------------------------------------
// Drawers
// ---------------------------------------------------------------------------

function openDrawer(name) {
  const drawer = name === "schema" ? schemaDrawer : historyDrawer;
  drawer.hidden = false;
  document.body.style.overflow = "hidden";
}

function closeDrawer(name) {
  if (name === "schema") schemaDrawer.hidden = true;
  if (name === "history") historyDrawer.hidden = true;
  if (schemaDrawer.hidden && historyDrawer.hidden) document.body.style.overflow = "";
}

function initDrawers() {
  document.querySelectorAll(".drawer [data-close]").forEach((el) => {
    el.addEventListener("click", () => closeDrawer(el.dataset.close));
  });
}

// ---------------------------------------------------------------------------
// Modal
// ---------------------------------------------------------------------------

function showConfirmModal(message, title = "Confirm Data Modification") {
  return new Promise((resolve) => {
    confirmTitle.textContent = title;
    confirmMessage.textContent = message;
    confirmModal.hidden = false;

    const finish = (confirmed) => {
      cleanup();
      resolve(confirmed);
    };
    const onOk = () => finish(true);
    const onCancel = () => finish(false);
    const onKeydown = (event) => {
      if (event.key === "Escape") finish(false);
    };

    function cleanup() {
      confirmModal.hidden = true;
      confirmOk.removeEventListener("click", onOk);
      confirmCancel.removeEventListener("click", onCancel);
      confirmBackdrop.removeEventListener("click", onCancel);
      document.removeEventListener("keydown", onKeydown);
    }

    confirmOk.addEventListener("click", onOk);
    confirmCancel.addEventListener("click", onCancel);
    confirmBackdrop.addEventListener("click", onCancel);
    document.addEventListener("keydown", onKeydown);
    confirmCancel.focus();
  });
}

// ---------------------------------------------------------------------------
// Query options
// ---------------------------------------------------------------------------

function renderQueryOptions(queries, selectedIndex) {
  queryOptionsContainer.innerHTML = "";
  const visible = userFacingQueries(queries);

  if (visible.length <= 1) {
    queryOptionsCard.hidden = true;
    return;
  }

  queryOptionsCard.hidden = false;
  visible.forEach((sql, index) => {
    const label = document.createElement("label");
    label.className = "query-option" + (index === selectedIndex ? " selected" : "");

    const radio = document.createElement("input");
    radio.type = "radio";
    radio.name = "generated-query";
    radio.checked = index === selectedIndex;

    const pre = document.createElement("pre");
    pre.textContent = sql;

    const body = document.createElement("div");
    body.className = "query-option__body";

    const title = document.createElement("div");
    title.className = "query-option__title";
    title.textContent = getQueryOptionLabel(sql, index);

    radio.addEventListener("change", () => {
      if (radio.checked) {
        appState.selectedQuery = sql;
        persistState();
        updateSqlDisplay();
        document.querySelectorAll(".query-option").forEach((el, i) => {
          el.classList.toggle("selected", i === index);
        });
      }
    });

    label.appendChild(radio);
    body.appendChild(title);
    body.appendChild(pre);
    label.appendChild(body);
    queryOptionsContainer.appendChild(label);
  });
}

function renderStructuredQueryOptions(data) {
  queryOptionsContainer.innerHTML = "";
  const options = getStructuredOptions(data);
  if (!options.length) {
    queryOptionsCard.hidden = true;
    return;
  }

  queryOptionsCard.hidden = false;
  const sourceLabel = generationSourceLabel(data?.generation_source);
  if (sourceLabel) {
    const sourceBadge = document.createElement("div");
    sourceBadge.className = "generation-source-badge";
    sourceBadge.textContent = sourceLabel;
    queryOptionsContainer.appendChild(sourceBadge);
  }

  options.forEach((option, index) => {
    const article = document.createElement("article");
    article.className = "query-option-card" + (index === 0 ? " selected" : "");

    const header = document.createElement("div");
    header.className = "query-option-card__header";

    const heading = document.createElement("div");
    const eyebrow = document.createElement("span");
    eyebrow.className = "query-option-card__eyebrow";
    eyebrow.textContent = option.label || `Option ${index + 1}`;
    const title = document.createElement("h4");
    title.textContent = option.title || (index === 0 ? "Recommended Query" : "Alternative Query");
    heading.appendChild(eyebrow);
    heading.appendChild(title);

    const badge = document.createElement("span");
    badge.className = "query-option-card__badge";
    badge.textContent = index === 0 ? "Recommended" : "Alternative";
    header.appendChild(heading);
    header.appendChild(badge);

    const pre = document.createElement("pre");
    pre.className = "query-option-card__sql";
    pre.textContent = option.sql;

    const actions = document.createElement("div");
    actions.className = "query-option-card__actions";
    const canCopy = isAdmin() || (appState.queryType || "SELECT") === "SELECT";
    if (canCopy) {
      const copyButton = document.createElement("button");
      copyButton.className = "btn btn-copy";
      copyButton.type = "button";
      copyButton.textContent = "Copy SQL";
      copyButton.addEventListener("click", () => copySql(option.sql, copyButton));
      actions.appendChild(copyButton);
    }
    if (isAdmin()) {
      const executeButton = document.createElement("button");
      executeButton.className = "btn btn-execute btn-execute--inline";
      executeButton.type = "button";
      executeButton.textContent = "Execute";
      executeButton.addEventListener("click", () => handleExecute(option.sql));
      actions.appendChild(executeButton);
    }

    const whyTitle = document.createElement("h5");
    whyTitle.textContent = index === 0 ? "Why recommended" : "Why alternative";
    const why = renderBullets(option.why_best || option.why_less_favourable || []);

    const explanationTitle = document.createElement("h5");
    explanationTitle.textContent = "Explanation";
    const explanation = renderBullets(option.explanation || []);

    const meta = document.createElement("div");
    meta.className = "query-option-card__meta";
    const validation = document.createElement("p");
    validation.textContent = `Validation: ${option.validation?.message || "Not checked."}`;
    const impact = document.createElement("p");
    impact.textContent = `Impact: ${option.impact?.summary || "Impact depends on matching rows."}`;
    const optimization = document.createElement("p");
    optimization.textContent = `Optimization: ${(option.optimization || []).join(" ") || "No specific optimization suggestion."}`;
    const warning = document.createElement("p");
    warning.textContent = `Warning: ${option.warning || data.warning || "No warnings for this query."}`;
    meta.append(validation, impact, optimization, warning);

    article.append(header, pre, actions, whyTitle, why, explanationTitle, explanation, meta);
    queryOptionsContainer.appendChild(article);
  });
}

function updateSqlDisplay() {
  const sql = getSelectedQuery();
  outputSql.textContent = sql;
  btnExecute.disabled = !sql;
  btnCopySql.hidden = !sql;
}

// ---------------------------------------------------------------------------
// Display results
// ---------------------------------------------------------------------------

function showEmptyState() {
  outputEmpty.hidden = false;
  outputResults.hidden = true;
  appState.currentResponse = null;
  appState.selectedQuery = "";
  appState.queryType = "";
  btnExecute.disabled = true;
  btnCopySql.hidden = false;
  outputSql.textContent = "";
  queryOptionsContainer.innerHTML = "";
  delete executeSection.dataset.optionMode;
  demoModeNote.hidden = true;
  applyRoleAccess();
}

function renderUnsupportedSchema(data) {
  appState.selectedQuery = "";
  outputSql.textContent = "";
  queryOptionsContainer.innerHTML = "";
  const explanationMessage = Array.isArray(data.explanation)
    ? data.explanation[0]
    : data.explanation;

  unsupportedCard.hidden = false;
  unsupportedCard.classList.remove("multiple-prompts-card");
  unsupportedCard.querySelector("h3").textContent = "Unsupported request";
  unsupportedCard.querySelector(".unsupported-card__eyebrow").textContent =
    "No SQL query was generated to avoid incorrect output.";
  unsupportedCard.querySelector(".unsupported-card__label").textContent = isAdmin()
    ? "Available HR schema"
    : "Suggestion";
  unsupportedCard.querySelector(".unsupported-schema-list").innerHTML = isAdmin()
    ? "<span>employees</span><span>departments</span><span>jobs</span><span>locations</span><span>countries</span><span>regions</span><span>dependents</span>"
    : "<span>Please contact the admin if this type of data needs to be added.</span>";
  sqlBlock.hidden = true;
  queryOptionsCard.hidden = true;
  detailsTabs.hidden = true;
  btnCopySql.hidden = true;
  btnExecute.disabled = true;
  executeSection.hidden = false;
  demoModeNote.hidden = true;

  unsupportedMessage.textContent =
    isAdmin()
      ? (explanationMessage || "This prompt requires tables that are not available in the current schema.")
      : "This request needs data that is not available in the current connected database.";
  unsupportedWarning.textContent =
    data.warning || "The system avoided generating an incorrect hallucinated query.";
  unsupportedOptimization.textContent =
    isAdmin()
      ? (data.optimization_suggestion || "Add the required schema or use one of the available demo tables.")
      : "Contact the admin to add or connect the required database.";
  applyRoleAccess();
}

function renderUnsupportedDomain(data) {
  appState.selectedQuery = "";
  outputSql.textContent = "";
  queryOptionsContainer.innerHTML = "";

  unsupportedCard.hidden = false;
  unsupportedCard.classList.remove("multiple-prompts-card");
  unsupportedCard.querySelector("h3").textContent = "Unsupported request";
  unsupportedCard.querySelector(".unsupported-card__eyebrow").textContent =
    "No SQL query was generated to avoid incorrect output.";
  unsupportedCard.querySelector(".unsupported-card__label").textContent = isAdmin()
    ? "Supported internal domains"
    : "Suggestion";
  unsupportedCard.querySelector(".unsupported-schema-list").innerHTML = isAdmin()
    ? "<span>HR</span><span>E-Commerce</span><span>University</span><span>Healthcare</span><span>Library</span><span>Banking</span><span>Hotel/Booking</span>"
    : "<span>Please ask the admin to connect or add a matching database.</span>";
  sqlBlock.hidden = true;
  queryOptionsCard.hidden = true;
  detailsTabs.hidden = false;
  btnCopySql.hidden = true;
  btnExecute.disabled = true;
  executeSection.hidden = true;
  demoModeNote.hidden = true;

  unsupportedMessage.textContent =
    "This request needs tables that are not available in the current connected database.";
  unsupportedWarning.textContent = data.warning || "Unsupported domain.";
  unsupportedOptimization.textContent =
    data.suggestion || data.optimization_suggestion || "Please ask the admin to connect or add a matching database for this type of query.";

  activateExplanationTab();
  renderExplanation(data.explanation || []);
  if (isAdmin()) {
    renderTagList(outputTables, data.affected_tables);
    renderTagList(outputColumns, data.affected_columns);
  }
  outputImpact.textContent = data.expected_output || "No SQL query was generated.";
  outputOptimization.textContent = data.optimization_suggestion || "Please ask the admin to connect or add a matching database.";
  outputWarning.textContent = data.warning || "Unsupported domain.";
  applyRoleAccess();
}

function renderMultiplePromptsWarning(data) {
  appState.selectedQuery = "";
  outputSql.textContent = "";
  queryOptionsContainer.innerHTML = "";

  unsupportedCard.hidden = false;
  unsupportedCard.classList.add("multiple-prompts-card");
  unsupportedCard.querySelector("h3").textContent = "Multiple requests detected";
  unsupportedCard.querySelector(".unsupported-card__eyebrow").textContent =
    "No SQL query was generated because En2SQL supports one request at a time.";
  unsupportedMessage.textContent =
    "Please enter one SQL request at a time. This helps En2SQL generate a more accurate and safe query.";
  unsupportedWarning.textContent = data.warning || "Multiple prompts detected.";
  unsupportedOptimization.textContent =
    "Example: enter only “Show all employees whose salary is greater than 50000”, then generate the department count query separately.";

  sqlBlock.hidden = true;
  queryOptionsCard.hidden = true;
  detailsTabs.hidden = false;
  btnCopySql.hidden = true;
  btnExecute.disabled = true;
  executeSection.hidden = true;
  demoModeNote.hidden = true;

  activateExplanationTab();
  renderExplanation(data.explanation || []);
  if (isAdmin()) {
    renderTagList(outputTables, data.affected_tables);
    renderTagList(outputColumns, data.affected_columns);
  }
  outputImpact.textContent = data.expected_output || "No SQL query was generated because multiple prompts were entered together.";
  outputOptimization.textContent = data.optimization_suggestion || "Split your input into separate prompts and generate them one by one.";
  outputWarning.textContent = data.warning || "Multiple prompts detected.";
  applyRoleAccess();
}

function renderNoSqlWarning(data, options = {}) {
  appState.selectedQuery = "";
  outputSql.textContent = "";
  queryOptionsContainer.innerHTML = "";

  unsupportedCard.hidden = false;
  unsupportedCard.classList.add(options.className || "multiple-prompts-card");
  unsupportedCard.querySelector("h3").textContent = options.title || "No SQL generated";
  unsupportedCard.querySelector(".unsupported-card__eyebrow").textContent =
    options.eyebrow || "No SQL query was generated.";
  unsupportedMessage.textContent =
    options.message || data.expected_output || "Please revise your prompt and try again.";
  unsupportedWarning.textContent = data.warning || options.warning || "No SQL generated.";
  unsupportedOptimization.textContent =
    data.optimization_suggestion || options.optimization || "Try entering one clear SQL request in English.";

  sqlBlock.hidden = true;
  queryOptionsCard.hidden = true;
  detailsTabs.hidden = false;
  btnCopySql.hidden = true;
  btnExecute.disabled = true;
  executeSection.hidden = true;
  demoModeNote.hidden = true;

  activateExplanationTab();
  renderExplanation(data.explanation || []);
  if (isAdmin()) {
    renderTagList(outputTables, data.affected_tables);
    renderTagList(outputColumns, data.affected_columns);
  }
  outputImpact.textContent = data.expected_output || "No SQL query was generated.";
  outputOptimization.textContent =
    data.optimization_suggestion || options.optimization || "Try entering one clear SQL request in English.";
  outputWarning.textContent = data.warning || options.warning || "No SQL generated.";
  applyRoleAccess();
}

function displayResults(data) {
  console.log("Rendering output");

  outputEmpty.hidden = true;
  outputResults.hidden = false;
  executionBlock.hidden = true;

  const queryType = appState.queryType;

  if (queryType === "MULTIPLE_PROMPTS_DETECTED") {
    renderMultiplePromptsWarning(data);
    return;
  }

  if (queryType === "INVALID_PROMPT") {
    renderNoSqlWarning(data, {
      title: "Invalid prompt",
      eyebrow: "Please enter a clear SQL request in English.",
      message: "En2SQL needs a clear request before it can generate a safe SQL query.",
      warning: "Invalid prompt.",
      optimization: "Example: Show all employees whose salary is greater than 50000.",
    });
    return;
  }

  if (queryType === "UNSAFE_REQUEST") {
    renderNoSqlWarning(data, {
      title: "Unsafe request detected",
      eyebrow: "No SQL query was generated for safety.",
      message: "This request may modify or remove database objects, so En2SQL did not generate it automatically.",
      warning: "Unsafe request detected.",
      optimization: "Use a safe read-only request or a clearly supported update/delete request.",
    });
    return;
  }

  if (queryType === "ACCESS_DENIED_OPERATION") {
    renderNoSqlWarning(data, {
      title: "Operation restricted",
      eyebrow: "No SQL query was generated.",
      message: "User accounts are allowed to generate read-only SELECT queries only.",
      warning: "Access denied.",
      optimization: "Please contact the admin for modification operations.",
    });
    return;
  }

  if (queryType === "UNSAFE_SCHEMA_OPERATION") {
    renderNoSqlWarning(data, {
      title: "Unsafe schema operation blocked",
      eyebrow: "No SQL query was generated for safety.",
      message: "This request attempts to change or remove database structure.",
      warning: "Blocked unsafe schema operation.",
      optimization: "Schema-level changes should be performed manually by an authorized database administrator.",
    });
    return;
  }

  if (queryType === "SCHEMA_CREATION_GUIDANCE") {
    renderNoSqlWarning(data, {
      title: "Schema creation guidance",
      eyebrow: "No executable SQL was generated.",
      message: "Schema creation is not available from the normal Text-to-SQL workspace.",
      warning: "Schema creation is blocked from this workspace.",
      optimization: data.suggestion || "Create a schema pack SQL file and import it manually.",
    });
    return;
  }

  if (queryType === "UNSUPPORTED_DOMAIN") {
    renderUnsupportedDomain(data);
    return;
  }

  // Unsupported schema
  if (queryType === "UNSUPPORTED_SCHEMA") {
    renderUnsupportedSchema(data);
    return;
  }

  unsupportedCard.classList.remove("multiple-prompts-card");
  unsupportedCard.hidden = true;
  executeSection.hidden = false;
  sqlBlock.hidden = false;
  detailsTabs.hidden = false;
  btnCopySql.hidden = false;

  const sql = appState.selectedQuery;

  if (!sql || sql.startsWith("-- Error")) {
    appState.selectedQuery = "";
    outputSql.textContent = "";
    unsupportedCard.hidden = false;
    sqlBlock.hidden = true;
    queryOptionsCard.hidden = true;
    detailsTabs.hidden = true;
    btnCopySql.hidden = true;
    executeSection.hidden = false;
    unsupportedMessage.textContent = sql || "No valid SQL could be generated for this prompt.";
    unsupportedWarning.textContent = data.warning || "No SQL query was generated to avoid incorrect output.";
    unsupportedOptimization.textContent = data.optimization_suggestion || "Try a prompt using employees, departments, jobs, or locations.";
    btnExecute.disabled = true;
    return;
  }

  const structuredOptions = getStructuredOptions(data);
  if (structuredOptions.length) {
    renderStructuredQueryOptions(data);
    sqlBlock.hidden = true;
    btnCopySql.hidden = true;
    executeSection.hidden = true;
    executeSection.dataset.optionMode = "true";
    appState.selectedQuery = structuredOptions[0].sql;
  } else {
    delete executeSection.dataset.optionMode;
    const visibleQueries = userFacingQueries(data.generated_queries);
    const selectedIndex = Math.max(0, visibleQueries.indexOf(sql));
    renderQueryOptions(data.generated_queries, selectedIndex);
    outputSql.textContent = sql;
    btnExecute.disabled = false;
    demoModeNote.hidden = !demoMode;
  }

  queryTypeBadge.textContent = queryType;
  databaseBadge.textContent = (data.database_type || "mysql").toUpperCase();

  const valid = (data.validation || "").toLowerCase().includes("valid");
  validationBadge.textContent = valid ? "Valid SQL" : "Check SQL";
  validationBadge.style.background = valid ? "" : "#78350f";
  validationBadge.style.color = valid ? "" : "#fde68a";

  const warningText = (data.warning || "").trim();
  if (warningText) {
    warningBadge.hidden = false;
    warningBadge.textContent = "Safety Warning";
    warningBadge.title = warningText;
  } else {
    warningBadge.hidden = true;
  }

  renderExplanation(data.explanation || "—");
  if (isAdmin()) {
    renderTagList(outputTables, data.affected_tables);
    renderTagList(outputColumns, data.affected_columns);
  }
  outputImpact.textContent = data.expected_output || "—";
  outputOptimization.textContent = data.optimization_suggestion || "—";
  outputWarning.textContent = warningText || "No warnings for this query.";
  applyRoleAccess();
}

// ---------------------------------------------------------------------------
// Execution
// ---------------------------------------------------------------------------

function displayExecutionResult(data) {
  executionBlock.hidden = false;
  executionMessage.textContent = data.message || "";

  if (demoMode && data.status === "success") {
    demoModeNote.hidden = false;
  }

  executionThead.innerHTML = "";
  executionTbody.innerHTML = "";

  if (data.status !== "success") {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.className = "no-rows";
    td.textContent = data.message || "Execution failed.";
    tr.appendChild(td);
    executionTbody.appendChild(tr);
    return;
  }

  const columns = data.columns || [];
  const rows = data.rows || [];

  if (!columns.length && !rows.length) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.className = "no-rows";
    td.textContent = data.message || "Query executed — no rows returned.";
    tr.appendChild(td);
    executionTbody.appendChild(tr);
    return;
  }

  const headerRow = document.createElement("tr");
  columns.forEach((col) => {
    const th = document.createElement("th");
    th.textContent = col;
    headerRow.appendChild(th);
  });
  executionThead.appendChild(headerRow);

  if (!rows.length) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = columns.length || 1;
    td.className = "no-rows";
    td.textContent = "No rows returned.";
    tr.appendChild(td);
    executionTbody.appendChild(tr);
    return;
  }

  rows.forEach((row) => {
    const tr = document.createElement("tr");
    columns.forEach((col) => {
      const td = document.createElement("td");
      const val = row[col];
      td.textContent = val == null ? "NULL" : String(val);
      tr.appendChild(td);
    });
    executionTbody.appendChild(tr);
  });
}

// ---------------------------------------------------------------------------
// Schema & History
// ---------------------------------------------------------------------------

function renderSchema(data) {
  schemaContent.innerHTML = "";
  schemaMode.textContent = (data.mode || "demo").toUpperCase();

  (data.tables || []).forEach((table) => {
    const card = document.createElement("div");
    card.className = "schema-table-card";
    const pkSet = new Set(table.primary_key || []);
    const colsHtml = (table.columns || [])
      .map((c) => `<span class="schema-col${pkSet.has(c) ? " pk" : ""}">${escapeHtml(c)}</span>`)
      .join("");
    card.innerHTML = `
      <h4>${escapeHtml(table.name)}</h4>
      <p class="schema-desc">${escapeHtml(table.description || "")}</p>
      <div class="schema-columns">${colsHtml}</div>`;
    schemaContent.appendChild(card);
  });
}

function renderHistory(entries) {
  historyList.innerHTML = "";
  if (!entries?.length) {
    historyList.innerHTML = '<li class="history-placeholder">No history yet. Generate a query to get started.</li>';
    return;
  }

  entries.forEach((entry) => {
    const li = document.createElement("li");
    li.className = "history-item";
    li.innerHTML = `
      <div class="history-prompt">${escapeHtml(entry.user_prompt)}</div>
      <div class="history-meta">${escapeHtml((entry.database_type || "").toUpperCase())} · ${escapeHtml(entry.query_type || "SELECT")} · ${escapeHtml(formatTimestamp(entry.timestamp))}</div>
      <div class="history-sql">${escapeHtml(entry.generated_sql)}</div>
      ${entry.expected_output ? `<div class="history-impact">${escapeHtml(entry.expected_output)}</div>` : ""}`;
    li.addEventListener("click", () => {
      promptInput.value = entry.user_prompt || "";
      dbTypeSelect.value = entry.database_type || "mysql";
      closeDrawer("history");
      promptInput.focus();
    });
    historyList.appendChild(li);
  });
}

// ---------------------------------------------------------------------------
// Event handlers
// ---------------------------------------------------------------------------

async function handleGenerate(event) {
  event?.preventDefault();
  console.log("Generate clicked");

  const prompt = promptInput.value.trim();
  if (!backendOnline) { showToast("Backend is not reachable. Start Flask on http://localhost:5000", "error"); return; }

  appState.databaseType = dbTypeSelect.value;
  persistState();
  setGenerateLoading(true);
  try {
    const data = await apiPost("/api/generate", {
      prompt,
      database_type: appState.databaseType,
    });
    console.log("API response received", data);

    const queries = userFacingQueries(data.generated_queries);
    appState.currentResponse = data;
    appState.selectedQuery = data.recommended_query?.sql || data.selected_query || queries[0] || "";
    appState.queryType = (data.query_type || "SELECT").toUpperCase();
    appState.schemaPack = data.schema_pack || data.detected_domain || "hr";

    persistState();
    displayResults(data);
  } catch (err) {
    showToast(`Generation failed: ${err.message}`, "error");
  } finally {
    setGenerateLoading(false);
  }
}

async function handleExecute(queryOverride = "") {
  if (!isAdmin()) {
    showToast("Execution is restricted to admin.", "error");
    return;
  }
  const query = queryOverride || getSelectedQuery();
  if (!query) { showToast("No query selected.", "error"); return; }

  const queryType = appState.queryType || "SELECT";
  let confirmed = false;
  if (DESTRUCTIVE_TYPES.has(queryType)) {
    const msg = queryType === "DELETE"
      ? "This query may permanently remove records from the database. Continue only if you understand the impact."
      : "This query may change database records. Continue only if you understand the impact.";

    confirmed = await showConfirmModal(msg, "Confirm Data Modification");
    if (!confirmed) return;
  }

  setGlobalLoading(true);
  try {
    const data = await apiPost("/api/execute", {
      query,
      database_type: appState.databaseType,
      schema_pack: appState.schemaPack,
      confirmed,
    });
    displayExecutionResult(data);
  } catch (err) {
    displayExecutionResult({ status: "error", columns: [], rows: [], message: err.message });
  } finally {
    setGlobalLoading(false);
  }
}

async function handleCopySql() {
  const sql = getSelectedQuery() || outputSql.textContent;
  if (!sql) return;
  await copySql(sql, btnCopySql);
}

async function loadHistory() {
  if (!isAdmin()) { showToast("History is restricted to admin.", "error"); return; }
  if (!backendOnline) { showToast("Backend is not reachable.", "error"); return; }
  setGlobalLoading(true);
  try {
    const data = await apiGet("/api/history");
    renderHistory(data.history || []);
    openDrawer("history");
  } catch (err) {
    showToast(`Failed to load history: ${err.message}`, "error");
  } finally {
    setGlobalLoading(false);
  }
}

async function loadSchema() {
  if (!isAdmin()) { showToast("Schema access is restricted to admin.", "error"); return; }
  if (!backendOnline) { showToast("Backend is not reachable.", "error"); return; }
  setGlobalLoading(true);
  try {
    const params = new URLSearchParams({
      database_type: appState.databaseType,
      schema_pack: appState.schemaPack || "hr",
    });
    const data = await apiGet(`/api/schema?${params.toString()}`);
    renderSchema(data);
    openDrawer("schema");
  } catch (err) {
    showToast(`Failed to load schema: ${err.message}`, "error");
  } finally {
    setGlobalLoading(false);
  }
}

function clearAll(event) {
  event?.preventDefault();
  console.log("Clear clicked");

  appState.currentResponse = null;
  appState.selectedQuery = "";
  appState.queryType = "";
  appState.databaseType = "mysql";
  appState.schemaPack = "hr";
  sessionStorage.removeItem(STORAGE_KEY);
  promptInput.value = "";
  dbTypeSelect.value = appState.databaseType;
  showEmptyState();
  executionBlock.hidden = true;
  promptInput.focus();
  applyRoleAccess();
}

function logout() {
  localStorage.removeItem(AUTH_TOKEN_KEY);
  localStorage.removeItem(AUTH_ROLE_KEY);
  localStorage.removeItem(AUTH_NAME_KEY);
  localStorage.removeItem(AUTH_EMAIL_KEY);
  sessionStorage.removeItem(STORAGE_KEY);
  window.location.href = "index.html";
}

function initSampleChips() {
  SAMPLE_PROMPTS.forEach((text) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "sample-chip";
    btn.textContent = text;
    btn.addEventListener("click", (event) => {
      event.preventDefault();
      promptInput.value = text;
      persistState();
      promptInput.focus();
    });
    sampleButtonsContainer.appendChild(btn);
  });
}

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------

initSampleChips();
initTabs();
initDrawers();

document.addEventListener("submit", function (event) {
  event.preventDefault();
});

btnGenerate.addEventListener("click", handleGenerate);
btnExecute.addEventListener("click", handleExecute);
btnClear.addEventListener("click", clearAll);
btnCopySql.addEventListener("click", handleCopySql);
btnLoadHistory.addEventListener("click", loadHistory);
btnLoadSchema.addEventListener("click", loadSchema);
btnViewSchema?.addEventListener("click", loadSchema);
btnLogout?.addEventListener("click", logout);

promptInput.addEventListener("input", persistState);
dbTypeSelect.addEventListener("change", () => {
  appState.databaseType = dbTypeSelect.value;
  persistState();
});

promptInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
    e.preventDefault();
    handleGenerate();
  }
});

applyRoleAccess();
restoreState();
checkBackendHealth();
setInterval(checkBackendHealth, 30000);

});
