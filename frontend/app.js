const state = {
  user: null,
  page: "dashboard",
  selectedPlot: null,
  modalSubmit: null,
  toastTimer: null
};

const pageNames = {
  dashboard: "Resumen",
  plots: "Terrenos y lotes",
  clients: "Clientes",
  sales: "Ventas y contratos",
  payments: "Cuotas y abonos",
  reports: "Informes",
  users: "Usuarios y roles",
  settings: "Configuración"
};

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const escapeHtml = value => String(value ?? "").replace(/[&<>"']/g, char => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
})[char]);
const money = value => new Intl.NumberFormat("es-CO", {
  style: "currency", currency: "COP", maximumFractionDigits: 0
}).format(Number(value) || 0);
const dateText = value => value ? new Date(`${value}T12:00:00`).toLocaleDateString("es-CO") : "—";
const today = () => {
  const now = new Date();
  const localPart = value => String(value).padStart(2, "0");
  return `${now.getFullYear()}-${localPart(now.getMonth() + 1)}-${localPart(now.getDate())}`;
};
const canEdit = () => ["Administrador", "Operador"].includes(state.user?.role);
const isAdmin = () => state.user?.role === "Administrador";

class RequestError extends Error {
  constructor(message, statusCode) {
    super(message);
    this.statusCode = statusCode;
  }
}

async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  if (options.body && !(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(path, { ...options, headers, credentials: "same-origin" });
  if (response.status === 204) return null;
  const contentType = response.headers.get("content-type") || "";
  const isJson = contentType.includes("application/json");
  const payload = isJson ? await response.json() : await response.text();
  if (!response.ok) {
    const detail = isJson && typeof payload === "object" && payload !== null ? payload.detail : null;
    const message = Array.isArray(detail)
      ? detail.map(issue => `${issue.loc?.slice(1).join(".") || "Dato"}: ${issue.msg}`).join("; ")
      : detail || (response.status >= 500
        ? "El servidor local encontró un error."
        : "El servicio local no respondió correctamente.");
    throw new RequestError(message, response.status);
  }
  return payload;
}

function showToast(message, kind = "success") {
  const toast = $("#toast");
  toast.textContent = message;
  toast.classList.toggle("error", kind === "error");
  toast.classList.add("show");
  clearTimeout(state.toastTimer);
  state.toastTimer = setTimeout(() => toast.classList.remove("show"), 3300);
}

function badge(status) {
  const className = {
    Disponible: "badge-green",
    Pagada: "badge-green",
    Reservado: "badge-gold",
    Pendiente: "badge-gold",
    Vendido: "badge-red",
    Vencida: "badge-red",
    Activo: "badge-green",
    Inactivo: "badge-gray"
  }[status] || "badge-gray";
  return `<span class="badge ${className}">${escapeHtml(status)}</span>`;
}

function statCard(label, value, foot, icon) {
  return `<article class="card stat-card">
    <div class="stat-label"><span>${label}</span><span class="stat-symbol">${icon}</span></div>
    <div class="stat-value">${value}</div><div class="stat-foot">${foot}</div>
  </article>`;
}

function pageHead(title, description, action = "") {
  return `<header class="page-head"><div><h2>${title}</h2><p>${description}</p></div>${action}</header>`;
}

function primaryButton(label, action, attrs = "") {
  return `<button class="button button-primary" data-action="${action}" ${attrs}>＋ ${label}</button>`;
}

async function init() {
  $("#loginForm").addEventListener("submit", login);
  $("#userMenu").addEventListener("click", logout);
  $("#menuToggle").addEventListener("click", toggleSidebar);
  $("#sidebarScrim").addEventListener("click", toggleSidebar);
  $("#modalClose").addEventListener("click", closeModal);
  $("#modalCancel").addEventListener("click", closeModal);
  $("#modalBackdrop").addEventListener("click", event => {
    if (event.target === $("#modalBackdrop")) closeModal();
  });
  $("#recordForm").addEventListener("submit", submitModal);
  document.addEventListener("click", handleClick);
  document.addEventListener("input", event => {
    if (event.target.matches("[data-filter]")) {
      const query = event.target.value.trim().toLocaleLowerCase("es");
      $$(".filter-row").forEach(row => {
        row.hidden = !row.dataset.search.includes(query);
      });
    }
  });
  $("#modalBackdrop").addEventListener("change", handleChange);
  $("#pageContent").addEventListener("submit", handlePageSubmit);
  try {
    state.user = await api("/api/auth/me");
    showApplication();
  } catch (error) {
    if (error.statusCode === 401) showLogin();
    else showLogin(error.message);
  }
}

async function login(event) {
  event.preventDefault();
  const loginForm = event.currentTarget;
  const form = new FormData(loginForm);
  const error = $("#loginError");
  error.textContent = "";
  try {
    state.user = await api("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email: form.get("email"), password: form.get("password") })
    });
    loginForm.reset();
    showApplication();
  } catch (requestError) {
    error.textContent = requestError.message;
  }
}

function showLogin(message = "") {
  $("#application").classList.add("hidden");
  $("#loginScreen").classList.remove("hidden");
  $("#loginError").textContent = message;
}

function showApplication() {
  $("#loginScreen").classList.add("hidden");
  $("#application").classList.remove("hidden");
  $("#userName").textContent = state.user.name;
  $("#userRole").textContent = state.user.role;
  $("#userAvatar").textContent = state.user.name.split(/\s+/).slice(0, 2).map(part => part[0]).join("").toUpperCase();
  $$(".admin-only").forEach(item => item.classList.toggle("hidden", !isAdmin()));
  navigate("dashboard");
}

async function logout() {
  try {
    await api("/api/auth/logout", { method: "POST" });
  } catch (error) {
    if (error.statusCode !== 401) showToast(error.message, "error");
  }
  state.user = null;
  showLogin();
}

function toggleSidebar() {
  $("#sidebar").classList.toggle("open");
  $("#sidebarScrim").classList.toggle("visible");
}

async function navigate(page) {
  if (!pageNames[page]) return;
  if ((page === "users" || page === "settings") && !isAdmin()) {
    showToast("Esta sección requiere permisos de administrador.", "error");
    return;
  }
  state.page = page;
  $("#pageTitle").textContent = pageNames[page];
  $("#breadcrumb").textContent = pageNames[page];
  $$(".nav-item").forEach(item => item.classList.toggle("active", item.dataset.page === page));
  $("#sidebar").classList.remove("open");
  $("#sidebarScrim").classList.remove("visible");
  const content = $("#pageContent");
  content.innerHTML = `<div class="card empty">Cargando información…</div>`;
  try {
    const renderers = {
      dashboard: renderDashboard,
      plots: renderPlots,
      clients: renderClients,
      sales: renderSales,
      payments: renderPayments,
      reports: renderReports,
      users: renderUsers,
      settings: renderSettings
    };
    content.innerHTML = await renderers[page]();
  } catch (error) {
    if (error.statusCode === 401) {
      state.user = null;
      showLogin("Tu sesión terminó. Ingresa de nuevo.");
      return;
    }
    content.innerHTML = `<div class="card empty">${escapeHtml(error.message)}</div>`;
    showToast(error.message, "error");
  }
}

async function renderDashboard() {
  const data = await api("/api/dashboard");
  const count = data.total_plots;
  const progress = (key, label, color) => {
    const value = data.plots[key] || 0;
    const percent = count ? Math.round(value / count * 100) : 0;
    return `<div class="progress-item"><header><span>${label}</span><strong>${value} lotes · ${percent}%</strong></header>
      <div class="progress-track"><progress class="${color}" value="${value}" max="${count || 1}" aria-label="${label}">${percent}%</progress></div></div>`;
  };
  const activity = data.recent_payments.length ? data.recent_payments.map(payment => `
    <div class="activity-row"><span class="activity-mark">↗</span>
      <div class="activity-copy"><strong>${escapeHtml(payment.client_name)} · ${escapeHtml(payment.plot_code)}</strong>
      <small>${escapeHtml(payment.type)} · ${dateText(payment.date)}</small></div>
      <span class="activity-amount">${money(payment.amount)}</span>
    </div>`).join("") : `<div class="empty">Todavía no hay pagos registrados.</div>`;
  return `${pageHead("¡Hola, " + escapeHtml(state.user.name.split(" ")[0]) + "!", "Aquí tienes el estado actual de tu operación inmobiliaria.",
    canEdit() ? primaryButton("Registrar abono", "new-payment") : "")}
    <div class="grid stat-grid">
      ${statCard("Recaudo registrado", money(data.revenue), "Total de pagos ingresados", "↗")}
      ${statCard("Saldo por recaudar", money(data.balance), "Pendiente en contratos activos", "◷")}
      ${statCard("Lotes disponibles", data.plots.Disponible, `${count} lotes en inventario`, "▦")}
      ${statCard("Lotes vendidos", data.plots.Vendido, `${count ? Math.round(data.plots.Vendido / count * 100) : 0}% del inventario`, "⌂")}
    </div>
    <div class="grid dashboard-grid">
      <article class="card card-pad">
        <div class="card-title"><h3>Estado del inventario</h3><button class="button button-quiet button-small" data-page="plots">Ver terrenos →</button></div>
        <div class="progress-list">
          ${progress("Disponible", "Disponibles", "green")}
          ${progress("Reservado", "Reservados", "gold")}
          ${progress("Vendido", "Vendidos", "red")}
        </div>
        <div class="inventory-value"><span>Valor de inventario disponible</span><strong>${money(data.inventory_value)}</strong></div>
      </article>
      <article class="card card-pad"><div class="card-title"><h3>Actividad reciente</h3><small>Últimos pagos recibidos</small></div>
        <div class="activity-list">${activity}</div>
      </article>
    </div>
    ${canEdit() ? `<article class="card section-card"><div class="card-title"><h3>Accesos rápidos</h3></div>
      <div class="quick-actions">${primaryButton("Agregar lote", "new-plot")}${primaryButton("Nuevo cliente", "new-client")}
      ${primaryButton("Crear contrato", "new-sale")}<button class="button button-quiet" data-page="reports">Ver informes</button></div>
    </article>` : ""}
    <div class="notice">Los datos iniciales son ejemplos editables. El plano es esquemático y no sustituye un plano topográfico; las cuotas son estimaciones, no asesoría contractual o contable.</div>`;
}

async function renderPlots() {
  const plots = await api("/api/plots");
  if (!plots.some(plot => plot.id === state.selectedPlot)) state.selectedPlot = plots[0]?.id ?? null;
  const selected = plots.find(plot => plot.id === state.selectedPlot);
  const tiles = plots.map(plot => `<button class="plot-tile ${plot.status.toLowerCase()}" data-action="select-plot" data-id="${plot.id}">
    <strong>${escapeHtml(plot.code)}</strong><small>${escapeHtml(plot.project)} · ${plot.area} m²</small>
    <small>${escapeHtml(plot.status)} · ${money(plot.price)}</small></button>`).join("");
  const detail = selected ? `<article class="card card-pad"><div class="card-title"><h3>Detalle del lote</h3>${badge(selected.status)}</div>
    <h2>${escapeHtml(selected.code)}</h2><p class="muted">${escapeHtml(selected.project)} · Manzana ${escapeHtml(selected.block || "—")}</p>
    <div class="detail-list">
      <div class="detail-row"><span>Área</span><strong>${selected.area} m²</strong></div>
      <div class="detail-row"><span>Precio de lista</span><strong>${money(selected.price)}</strong></div>
      <div class="detail-row"><span>Estado</span><strong>${escapeHtml(selected.status)}</strong></div>
    </div>${canEdit() ? `<div class="quick-actions">
      <button class="button button-quiet" data-action="edit-plot" data-id="${selected.id}">Editar</button>
      <button class="button button-danger" data-action="delete-plot" data-id="${selected.id}">Eliminar</button></div>` : ""}
    ${selected.status !== "Vendido" && canEdit() ? `<div class="plot-sale-action">${primaryButton("Registrar venta", "new-sale", `data-plot-id="${selected.id}"`)}</div>` : ""}
  </article>` : `<article class="card empty">No hay lotes registrados.</article>`;
  return `${pageHead("Inventario de terrenos", "Consulta los lotes de tus proyectos en el plano y la tabla.", canEdit() ? primaryButton("Nuevo lote", "new-plot") : "")}
    <div class="toolbar"><input class="input" type="search" placeholder="Buscar lote o proyecto…" data-filter aria-label="Buscar terrenos">
    <button class="button button-quiet" data-action="export-csv" data-type="plots">Exportar CSV</button></div>
    <div class="split-layout"><div><article class="card card-pad"><div class="card-title"><h3>Plano esquemático</h3><small>Selecciona un lote para ver detalles</small></div>
      <div class="map-grid">${tiles || `<div class="empty">No hay lotes para mostrar.</div>`}</div>
      <div class="notice">Plano de referencia sin escala topográfica.</div></article></div>${detail}</div>
    <article class="card table-card section-card"><div class="card-title"><h3>Todos los lotes</h3><small>${plots.length} registros</small></div>
      <div class="table-wrap"><table><thead><tr><th>Lote</th><th>Proyecto</th><th>Manzana</th><th>Área</th><th>Precio</th><th>Estado</th><th></th></tr></thead>
      <tbody>${plots.map(plot => `<tr class="filter-row" data-search="${escapeHtml((plot.code + " " + plot.project + " " + plot.block + " " + plot.status).toLocaleLowerCase("es"))}">
        <td><strong>${escapeHtml(plot.code)}</strong></td><td>${escapeHtml(plot.project)}</td><td>${escapeHtml(plot.block || "—")}</td>
        <td>${plot.area} m²</td><td>${money(plot.price)}</td><td>${badge(plot.status)}</td><td><button class="button button-quiet button-small" data-action="select-plot" data-id="${plot.id}">Ver</button></td></tr>`).join("") || emptyRow(7, "No hay lotes registrados.")}</tbody></table></div></article>`;
}

async function renderClients() {
  const clients = await api("/api/clients");
  return `${pageHead("Directorio de clientes", "Consulta y administra los datos de contacto de tus compradores.", canEdit() ? primaryButton("Nuevo cliente", "new-client") : "")}
    <div class="toolbar"><input class="input" type="search" placeholder="Buscar por nombre, documento o teléfono…" data-filter aria-label="Buscar clientes">
    <button class="button button-quiet" data-action="export-csv" data-type="clients">Exportar CSV</button></div>
    <article class="card table-card"><div class="card-title"><h3>Clientes registrados</h3><small>${clients.length} registros</small></div>
    <div class="table-wrap"><table><thead><tr><th>Cliente</th><th>Documento</th><th>Teléfono</th><th>Correo</th><th>Dirección</th><th></th></tr></thead><tbody>
      ${clients.map(client => `<tr class="filter-row" data-search="${escapeHtml((client.name + " " + client.document + " " + client.phone + " " + client.email).toLocaleLowerCase("es"))}">
        <td><strong>${escapeHtml(client.name)}</strong></td><td>${escapeHtml(client.document)}</td><td>${escapeHtml(client.phone || "—")}</td>
        <td>${escapeHtml(client.email || "—")}</td><td>${escapeHtml(client.address || "—")}</td>
        <td>${canEdit() ? `<div class="row-actions"><button class="button button-quiet button-small" data-action="edit-client" data-id="${client.id}">Editar</button>
        <button class="button button-danger button-small" data-action="delete-client" data-id="${client.id}">Eliminar</button></div>` : ""}</td></tr>`).join("") || emptyRow(6, "Todavía no hay clientes registrados.")}</tbody></table></div></article>`;
}

async function renderSales() {
  const sales = await api("/api/sales");
  return `${pageHead("Ventas y contratos", "Revisa las ventas, sus condiciones y el saldo pendiente.", canEdit() ? primaryButton("Nuevo contrato", "new-sale") : "")}
    <div class="toolbar"><input class="input" type="search" placeholder="Buscar cliente, lote o proyecto…" data-filter aria-label="Buscar contratos">
    <button class="button button-quiet" data-action="export-csv" data-type="sales">Exportar CSV</button></div>
    <article class="card table-card"><div class="card-title"><h3>Contratos registrados</h3><small>${sales.length} contratos</small></div>
    <div class="table-wrap"><table><thead><tr><th>Cliente</th><th>Lote</th><th>Fecha</th><th>Precio</th><th>Cuotas</th><th>Cuota estimada</th><th>Abonado</th><th>Saldo</th></tr></thead><tbody>
      ${sales.map(sale => `<tr class="filter-row" data-search="${escapeHtml((sale.client_name + " " + sale.plot_code + " " + sale.project).toLocaleLowerCase("es"))}">
        <td><strong>${escapeHtml(sale.client_name)}</strong><small class="muted"><br>${escapeHtml(sale.client_document)}</small></td>
        <td>${escapeHtml(sale.plot_code)}<small class="muted"><br>${escapeHtml(sale.project)}</small></td><td>${dateText(sale.date)}</td>
        <td>${money(sale.price)}</td><td>${sale.installments} · ${escapeHtml(sale.frequency.toLowerCase())}</td>
        <td>${money(sale.estimated_installment)}</td><td>${money(sale.paid)}</td><td><strong>${money(sale.balance)}</strong></td></tr>`).join("") || emptyRow(8, "No hay contratos registrados.")}</tbody></table></div>
    <div class="notice">La cuota se estima con los datos del contrato; no incorpora mora, calendario legal ni reglas contractuales personalizadas.</div></article>`;
}

async function renderPayments() {
  const payments = await api("/api/payments");
  return `${pageHead("Cuotas y abonos", "Consulta los movimientos asociados a cada contrato.", canEdit() ? primaryButton("Registrar abono", "new-payment") : "")}
    <div class="toolbar"><input class="input" type="search" placeholder="Buscar por cliente o lote…" data-filter aria-label="Buscar pagos">
    <button class="button button-quiet" data-action="export-csv" data-type="payments">Exportar CSV</button></div>
    <article class="card table-card"><div class="card-title"><h3>Historial de pagos</h3><small>${payments.length} movimientos</small></div>
    <div class="table-wrap"><table><thead><tr><th>Fecha</th><th>Cliente</th><th>Lote</th><th>Tipo</th><th>Medio</th><th>Valor</th><th>Nota</th><th></th></tr></thead><tbody>
      ${payments.map(payment => `<tr class="filter-row" data-search="${escapeHtml((payment.client_name + " " + payment.plot_code + " " + payment.type).toLocaleLowerCase("es"))}">
        <td>${dateText(payment.date)}</td><td><strong>${escapeHtml(payment.client_name)}</strong></td><td>${escapeHtml(payment.plot_code)}</td>
        <td>${escapeHtml(payment.type)}</td><td>${escapeHtml(payment.method)}</td><td><strong>${money(payment.amount)}</strong></td>
        <td>${escapeHtml(payment.note || "—")}</td><td>${canEdit() ? `<button class="button button-danger button-small" data-action="delete-payment" data-id="${payment.id}">Eliminar</button>` : ""}</td>
      </tr>`).join("") || emptyRow(8, "Todavía no hay abonos registrados.")}</tbody></table></div></article>`;
}

async function renderReports() {
  const data = await api("/api/dashboard");
  const reports = [
    ["plots", "Inventario de lotes", "Listado de proyectos, áreas, precios y estados.", "▦"],
    ["clients", "Directorio de clientes", "Datos de contacto de los clientes registrados.", "♙"],
    ["sales", "Ventas y contratos", "Condiciones, valores y plazos de los contratos.", "↗"],
    ["payments", "Pagos y abonos", "Historial de movimientos recibidos.", "◷"]
  ];
  return `${pageHead("Informes y exportaciones", "Descarga los datos en CSV y ábrelos con Excel o una hoja de cálculo.")}
    <div class="grid report-grid">${reports.map(([type, title, description, icon]) => `<article class="card report-card">
      <span class="report-icon">${icon}</span><h3>${title}</h3><p>${description}</p>
      <button class="button button-quiet" data-action="export-csv" data-type="${type}">Descargar CSV</button></article>`).join("")}</div>
    <article class="card section-card"><div class="card-title"><h3>Resumen de inventario</h3></div>
      <div class="detail-list">
        <div class="detail-row"><span>Total de lotes</span><strong>${data.total_plots}</strong></div>
        <div class="detail-row"><span>Disponibles</span><strong>${data.plots.Disponible}</strong></div>
        <div class="detail-row"><span>Reservados</span><strong>${data.plots.Reservado}</strong></div>
        <div class="detail-row"><span>Vendidos</span><strong>${data.plots.Vendido}</strong></div>
        <div class="detail-row"><span>Valor del inventario libre</span><strong>${money(data.inventory_value)}</strong></div>
      </div>
    </article>`;
}

async function renderUsers() {
  const users = await api("/api/users");
  return `${pageHead("Usuarios y roles", "Administra las cuentas y el nivel de acceso de cada persona.", primaryButton("Crear usuario", "new-user"))}
    <article class="card table-card"><div class="card-title"><h3>Cuentas del sistema</h3><small>${users.length} cuentas</small></div>
      <div class="table-wrap"><table><thead><tr><th>Nombre</th><th>Correo</th><th>Rol</th><th>Estado</th><th>Creación</th><th></th></tr></thead><tbody>
      ${users.map(user => `<tr><td><strong>${escapeHtml(user.name)}</strong></td><td>${escapeHtml(user.email)}</td><td>${badge(user.role)}</td>
        <td>${badge(user.active ? "Activo" : "Inactivo")}</td><td>${dateText(user.created_at?.slice(0, 10))}</td>
        <td>${user.id === state.user.id ? "Tu cuenta" : `<button class="button ${user.active ? "button-danger" : "button-quiet"} button-small" data-action="toggle-user" data-id="${user.id}" data-active="${user.active ? "true" : "false"}">${user.active ? "Desactivar" : "Activar"}</button>`}</td></tr>`).join("")}</tbody></table></div>
      <div class="notice">Administrador: gestiona usuarios y configuración. Operador: registra y modifica operaciones. Consulta: solo lectura.</div>
    </article>`;
}

async function renderSettings() {
  const audit = await api("/api/audit?limit=30");
  return `${pageHead("Configuración y seguridad", "Actualiza tu contraseña, respalda la información y consulta la actividad.")}
    <div class="grid settings-grid">
      <article class="card settings-card"><h3>Cambiar contraseña</h3><p>Usa una contraseña nueva de al menos 12 caracteres.</p>
        <form data-form="password" class="form-stack">
          <label class="field">Contraseña actual<input class="input" name="current_password" type="password" required autocomplete="current-password"></label>
          <label class="field">Nueva contraseña<input class="input" name="new_password" type="password" minlength="12" required autocomplete="new-password"></label>
          <button class="button button-primary" type="submit">Actualizar contraseña</button>
        </form>
      </article>
      <article class="card settings-card"><h3>Copia de seguridad</h3><p>La copia incluye clientes, lotes, contratos y pagos. No contiene usuarios ni contraseñas.</p>
        <div class="quick-actions"><button class="button button-primary" data-action="backup">Descargar copia JSON</button></div>
        <label class="field settings-file">Restaurar una copia JSON<input class="file-input" id="backupFile" type="file" accept=".json,application/json"></label>
        <button class="button button-quiet" data-action="restore">Restaurar copia</button>
        <div class="notice">La restauración reemplaza los datos operativos actuales. Descarga una copia primero.</div>
      </article>
    </div>
    <article class="card table-card section-card"><div class="card-title"><h3>Registro de actividad</h3><small>Últimos 30 eventos</small></div>
      <div class="table-wrap"><table><thead><tr><th>Fecha</th><th>Usuario</th><th>Acción</th><th>Elemento</th><th>Referencia</th></tr></thead><tbody>
      ${audit.map(entry => `<tr><td>${escapeHtml(entry.created_at)}</td><td>${escapeHtml(entry.user_name || "Sistema")}</td>
        <td>${escapeHtml(entry.action.replaceAll("_", " "))}</td><td>${escapeHtml(entry.entity.replaceAll("_", " "))}</td>
        <td>${entry.entity_id ?? "—"}</td></tr>`).join("") || emptyRow(5, "Todavía no hay actividad registrada.")}</tbody></table></div>
    </article>`;
}

function emptyRow(columns, message) {
  return `<tr><td colspan="${columns}" class="empty">${message}</td></tr>`;
}

function fieldMarkup(field) {
  const required = field.required === false ? "" : "required";
  const full = field.full ? " full" : "";
  const value = field.value ?? "";
  let control;
  if (field.type === "select") {
    control = `<select class="select" name="${field.name}" ${required}>${field.options.map(option => `
      <option value="${escapeHtml(option.value)}" ${String(option.value) === String(value) ? "selected" : ""}>${escapeHtml(option.label)}</option>`).join("")}</select>`;
  } else if (field.type === "textarea") {
    control = `<textarea class="textarea" name="${field.name}" maxlength="${field.maxlength || 1000}" ${required}>${escapeHtml(value)}</textarea>`;
  } else {
    control = `<input class="input" name="${field.name}" type="${field.type || "text"}" value="${escapeHtml(value)}"
      ${field.min !== undefined ? `min="${field.min}"` : ""} ${field.max !== undefined ? `max="${field.max}"` : ""}
      ${field.step ? `step="${field.step}"` : ""} ${field.minlength ? `minlength="${field.minlength}"` : ""}
      ${field.maxlength ? `maxlength="${field.maxlength}"` : ""} ${required}>`;
  }
  return `<label class="field${full}">${field.label}${control}</label>`;
}

async function openForm(kind, id = null, extra = {}) {
  if (!canEdit() && kind !== "password") return;
  let record = extra.record || null;
  if (id !== null && kind === "plot") record = record || (await api("/api/plots")).find(item => item.id === id);
  if (id !== null && kind === "client") record = record || (await api("/api/clients")).find(item => item.id === id);
  const titleByType = {
    plot: record ? "Editar lote" : "Agregar lote",
    client: record ? "Editar cliente" : "Registrar cliente",
    sale: "Crear contrato de venta",
    payment: "Registrar abono",
    user: "Crear usuario"
  };
  let fields = [];
  let submit;
  if (kind === "plot") {
    fields = [
      { name: "code", label: "Código del lote", value: record?.code, maxlength: 40 },
      { name: "project", label: "Proyecto", value: record?.project, maxlength: 140 },
      { name: "block", label: "Manzana", value: record?.block, required: false, maxlength: 40 },
      { name: "area", label: "Área (m²)", type: "number", value: record?.area || 120, min: 0.01, step: 0.01 },
      { name: "price", label: "Precio (COP)", type: "number", value: record?.price || 0, min: 0, step: 1 },
      { name: "status", label: "Estado", type: "select", value: record?.status || "Disponible", options: ["Disponible", "Reservado", "Vendido"].map(value => ({ value, label: value })) }
    ];
    submit = async data => api(id ? `/api/plots/${id}` : "/api/plots", { method: id ? "PATCH" : "POST", body: JSON.stringify({
      ...data, area: Number(data.area), price: Number(data.price)
    }) });
  } else if (kind === "client") {
    fields = [
      { name: "name", label: "Nombre completo", value: record?.name, maxlength: 140 },
      { name: "document", label: "Documento", value: record?.document, maxlength: 40 },
      { name: "phone", label: "Teléfono", value: record?.phone, required: false, maxlength: 40 },
      { name: "email", label: "Correo electrónico", type: "email", value: record?.email, required: false, maxlength: 254 },
      { name: "address", label: "Dirección o ciudad", value: record?.address, required: false, maxlength: 200 },
      { name: "notes", label: "Notas", type: "textarea", value: record?.notes, required: false, full: true, maxlength: 1000 }
    ];
    submit = async data => api(id ? `/api/clients/${id}` : "/api/clients", { method: id ? "PATCH" : "POST", body: JSON.stringify(data) });
  } else if (kind === "sale") {
    const [clients, plots] = await Promise.all([api("/api/clients"), api("/api/plots")]);
    const availablePlots = plots.filter(plot => plot.status !== "Vendido");
    if (!clients.length || !availablePlots.length) throw new Error("Necesitas al menos un cliente y un lote disponible para crear un contrato.");
    const selectedPlot = availablePlots.find(plot => plot.id === Number(extra.plotId));
    fields = [
      { name: "client_id", label: "Cliente", type: "select", value: clients[0].id, options: clients.map(client => ({ value: client.id, label: `${client.name} · ${client.document}` })) },
      { name: "plot_id", label: "Lote", type: "select", value: selectedPlot?.id || availablePlots[0].id, options: availablePlots.map(plot => ({ value: plot.id, label: `${plot.code} · ${plot.project} · ${money(plot.price)}` })) },
      { name: "date", label: "Fecha del contrato", type: "date", value: today() },
      { name: "price", label: "Precio de venta (COP)", type: "number", value: selectedPlot?.price || availablePlots[0].price, min: 0, step: 1 },
      { name: "initial", label: "Cuota inicial (COP)", type: "number", value: 0, min: 0, step: 1 },
      { name: "installments", label: "Número de cuotas", type: "number", value: 48, min: 1, max: 600, step: 1 },
      { name: "frequency", label: "Frecuencia", type: "select", value: "Mensual", options: ["Mensual", "Quincenal", "Semanal"].map(value => ({ value, label: value })) },
      { name: "interest", label: "Interés anual (%)", type: "number", value: 0, min: 0, max: 100, step: 0.01 },
      { name: "initial_method", label: "Medio de pago inicial", type: "select", value: "Transferencia", options: ["Transferencia", "Efectivo", "Consignación", "Otro"].map(value => ({ value, label: value })) },
      { name: "notes", label: "Notas del contrato", type: "textarea", required: false, full: true, maxlength: 1000 }
    ];
    submit = async data => api("/api/sales", { method: "POST", body: JSON.stringify({
      ...data, client_id: Number(data.client_id), plot_id: Number(data.plot_id), price: Number(data.price),
      initial: Number(data.initial), installments: Number(data.installments), interest: Number(data.interest)
    }) });
  } else if (kind === "payment") {
    const sales = await api("/api/sales");
    const openSales = sales.filter(sale => sale.balance > 0);
    if (!openSales.length) throw new Error("No hay contratos con saldo pendiente.");
    fields = [
      { name: "sale_id", label: "Contrato · cliente · lote · saldo", type: "select", value: openSales[0].id,
        options: openSales.map(sale => ({ value: sale.id, label: `${sale.client_name} · ${sale.plot_code} · ${money(sale.balance)}` })) },
      { name: "date", label: "Fecha del pago", type: "date", value: today() },
      { name: "amount", label: "Valor recibido (COP)", type: "number", value: 0, min: 1, step: 1 },
      { name: "type", label: "Tipo de movimiento", type: "select", value: "Abono", options: ["Abono", "Cuota", "Otro"].map(value => ({ value, label: value })) },
      { name: "method", label: "Medio de pago", type: "select", value: "Transferencia", options: ["Transferencia", "Efectivo", "Consignación", "Otro"].map(value => ({ value, label: value })) },
      { name: "note", label: "Nota", type: "textarea", required: false, full: true, maxlength: 500 }
    ];
    submit = async data => api("/api/payments", { method: "POST", body: JSON.stringify({
      ...data, sale_id: Number(data.sale_id), amount: Number(data.amount)
    }) });
  } else if (kind === "user") {
    fields = [
      { name: "name", label: "Nombre", maxlength: 140 },
      { name: "email", label: "Correo electrónico", type: "email", maxlength: 254 },
      { name: "password", label: "Contraseña temporal (mínimo 12 caracteres)", type: "password", minlength: 12, maxlength: 128 },
      { name: "role", label: "Rol", type: "select", value: "Operador", options: ["Administrador", "Operador", "Consulta"].map(value => ({ value, label: value })) }
    ];
    submit = async data => api("/api/users", { method: "POST", body: JSON.stringify(data) });
  }
  $("#modalTitle").textContent = titleByType[kind];
  $("#modalBody").innerHTML = `<div class="field-grid">${fields.map(fieldMarkup).join("")}</div>`;
  state.modalSubmit = submit;
  $("#modalBackdrop").classList.remove("hidden");
  $("input, select, textarea", $("#modalBody"))?.focus();
}

function closeModal() {
  $("#modalBackdrop").classList.add("hidden");
  state.modalSubmit = null;
  $("#recordForm").reset();
}

async function submitModal(event) {
  event.preventDefault();
  if (!state.modalSubmit) return;
  const button = $("#modalSubmit");
  button.disabled = true;
  try {
    const values = Object.fromEntries(new FormData(event.currentTarget).entries());
    await state.modalSubmit(values);
    closeModal();
    showToast("Cambios guardados correctamente.");
    await navigate(state.page);
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    button.disabled = false;
  }
}

async function handleClick(event) {
  const pageButton = event.target.closest("[data-page]");
  if (pageButton) {
    event.preventDefault();
    await navigate(pageButton.dataset.page);
    return;
  }
  const button = event.target.closest("[data-action]");
  if (!button) return;
  const { action, id } = button.dataset;
  try {
    if (action === "new-plot") await openForm("plot");
    else if (action === "new-client") await openForm("client");
    else if (action === "new-sale") await openForm("sale", null, { plotId: button.dataset.plotId });
    else if (action === "new-payment") await openForm("payment");
    else if (action === "new-user") await openForm("user");
    else if (action === "edit-plot") await openForm("plot", Number(id));
    else if (action === "edit-client") await openForm("client", Number(id));
    else if (action === "select-plot") {
      state.selectedPlot = Number(id);
      await navigate("plots");
    } else if (action === "delete-plot") {
      await deleteRecord(`/api/plots/${id}`, "¿Eliminar este lote?");
    } else if (action === "delete-client") {
      await deleteRecord(`/api/clients/${id}`, "¿Eliminar este cliente?");
    } else if (action === "delete-payment") {
      await deleteRecord(`/api/payments/${id}`, "¿Eliminar este abono? Esta acción quedará en el registro de actividad.");
    } else if (action === "export-csv") await downloadFile(`/api/reports/export?report_type=${encodeURIComponent(button.dataset.type)}`, `terranova-${button.dataset.type}.csv`);
    else if (action === "backup") await downloadBackup();
    else if (action === "restore") await restoreBackup();
    else if (action === "toggle-user") await toggleUser(button);
  } catch (error) {
    showToast(error.message, "error");
  }
}

async function deleteRecord(path, message) {
  if (!window.confirm(message)) return;
  await api(path, { method: "DELETE" });
  showToast("Registro eliminado.");
  await navigate(state.page);
}

async function downloadFile(path, name) {
  const response = await fetch(path, { credentials: "same-origin" });
  if (!response.ok) {
    const data = await response.json();
    throw new RequestError(data.detail || "No se pudo descargar el informe.", response.status);
  }
  saveBlob(await response.blob(), name);
}

async function downloadBackup() {
  const backup = await api("/api/admin/backup");
  saveBlob(new Blob([JSON.stringify(backup, null, 2)], { type: "application/json" }), `terranova-respaldo-${today()}.json`);
  showToast("Copia de seguridad descargada.");
}

async function restoreBackup() {
  const file = $("#backupFile")?.files?.[0];
  if (!file) throw new Error("Selecciona primero un archivo JSON.");
  if (!window.confirm("La restauración reemplazará los datos actuales. ¿Continuar?")) return;
  let data;
  try {
    data = JSON.parse(await file.text());
  } catch {
    throw new Error("El archivo seleccionado no contiene JSON válido.");
  }
  await api("/api/admin/restore", { method: "POST", body: JSON.stringify(data) });
  showToast("Copia restaurada correctamente.");
  await navigate("settings");
}

function saveBlob(blob, filename) {
  const link = document.createElement("a");
  const objectUrl = URL.createObjectURL(blob);
  link.href = objectUrl;
  link.download = filename;
  link.click();
  setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
}

async function toggleUser(button) {
  const active = button.dataset.active !== "true";
  if (!window.confirm(`${active ? "¿Activar" : "¿Desactivar"} este usuario?`)) return;
  await api(`/api/users/${button.dataset.id}/status`, {
    method: "PATCH", body: JSON.stringify({ active })
  });
  showToast("Estado del usuario actualizado.");
  await navigate("users");
}

function handleChange(event) {
  if (event.target.name === "plot_id" && state.page === "sales") {
    api("/api/plots").then(plots => {
      const plot = plots.find(item => item.id === Number(event.target.value));
      const price = $('input[name="price"]', $("#modalBody"));
      if (plot && price) price.value = plot.price;
    }).catch(error => showToast(error.message, "error"));
  }
}

async function handlePageSubmit(event) {
  const form = event.target.closest("form[data-form]");
  if (!form) return;
  event.preventDefault();
  const values = Object.fromEntries(new FormData(form).entries());
  try {
    if (form.dataset.form === "password") {
      await api("/api/auth/password", { method: "POST", body: JSON.stringify(values) });
      form.reset();
      showToast("Contraseña actualizada.");
      const audit = await api("/api/audit?limit=30");
      const table = $(".table-wrap tbody", $("#pageContent"));
      if (table) table.innerHTML = audit.map(entry => `<tr><td>${escapeHtml(entry.created_at)}</td><td>${escapeHtml(entry.user_name || "Sistema")}</td>
        <td>${escapeHtml(entry.action.replaceAll("_", " "))}</td><td>${escapeHtml(entry.entity.replaceAll("_", " "))}</td><td>${entry.entity_id ?? "—"}</td></tr>`).join("");
    }
  } catch (error) {
    showToast(error.message, "error");
  }
}

document.addEventListener("DOMContentLoaded", init);
