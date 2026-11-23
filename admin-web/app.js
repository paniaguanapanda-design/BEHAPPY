// BE HAPPY Admin: private panel, installable as an app. Reads /api/admin/stats with the server's ADMIN_TOKEN.
"use strict";

const KEY = "bh-admin-token";
const CAT = { plumbing: "Fontanería", electrical: "Electricidad", hvac: "Climatización", masonry: "Obra", carpentry: "Carpintería" };
const app = document.getElementById("app");
let token = read();
let data = null;
let loading = false;
let error = "";
let showTable = false;
let installEvent = null;
const selected = {}; // chart id -> selected day index

function read() { try { return localStorage.getItem(KEY) || ""; } catch { return ""; } }
function save(v) { try { v ? localStorage.setItem(KEY, v) : localStorage.removeItem(KEY); } catch { /* private mode */ } }
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const fmtDay = (d) => `${d.slice(8, 10)}/${d.slice(5, 7)}`;
const n = (v) => Number(v || 0).toLocaleString("es-ES");

async function load(t) {
  loading = true;
  error = "";
  render();
  try {
    const res = await fetch("/api/admin/stats?days=30", { headers: { "X-Admin-Token": t }, cache: "no-store" });
    if (res.status === 403) throw new Error("Clave incorrecta");
    if (!res.ok) throw new Error(`El servidor respondió ${res.status}`);
    data = await res.json();
    return true;
  } catch (e) {
    error = e.message === "Failed to fetch" ? "Sin conexión con el servidor" : e.message;
    return false;
  } finally {
    loading = false;
    render();
  }
}

// --- views ---
function loginView() {
  return `
    <form class="login" id="login">
      <img src="/icons/icon-192.png" alt="">
      <h1>BE HAPPY Admin</h1>
      <p class="muted">Introduce la clave de administrador (ADMIN_TOKEN de Render).</p>
      <input id="key" type="password" autocomplete="current-password" placeholder="Clave de administrador" aria-label="Clave de administrador" required>
      ${error ? `<p class="error">${esc(error)}</p>` : ""}
      <button class="btn" ${loading ? "disabled" : ""}>${loading ? "Comprobando…" : "Entrar"}</button>
    </form>
    ${installHint()}`;
}

function installHint() {
  const standalone = matchMedia("(display-mode: standalone)").matches || navigator.standalone;
  if (standalone) return "";
  if (installEvent) return `<div class="install"><span>Instala el panel en tu móvil para abrirlo como una app.</span><button class="btn" id="install">Instalar</button></div>`;
  if (/iphone|ipad|ipod/i.test(navigator.userAgent)) return `<div class="install"><span>Para instalarlo: botón <b>Compartir</b> y después <b>Añadir a pantalla de inicio</b>.</span></div>`;
  return "";
}

function tiles(items) {
  return `<div class="tiles">${items.map(([label, value]) => `<div class="tile"><div class="num">${n(value)}</div><div class="lbl">${esc(label)}</div></div>`).join("")}</div>`;
}

// Single-series bar chart (one hue, no legend): tap a bar to read that day; the plot is also in the table view.
function bars(id, title, pick, small) {
  const series = data.series;
  const values = series.map(pick);
  const max = Math.max(1, ...values);
  const total = values.reduce((a, b) => a + b, 0);
  const i = selected[id] ?? values.length - 1;
  const h = small ? 64 : 96;
  const cols = values.map((v, k) => {
    const height = v ? Math.max(3, (v / max) * h) : 1;
    return `<button type="button" data-chart="${id}" data-i="${k}" aria-pressed="${k === i}" aria-label="${fmtDay(series[k].day)}: ${v}"><i class="${v ? "" : "zero"}" style="height:${height}px"></i></button>`;
  }).join("");
  return `
    <div class="card">
      <h3>${esc(title)}</h3>
      <p class="readout">${fmtDay(series[i].day)}: <b>${values[i]}</b>${small ? "" : ` &nbsp;·&nbsp; 30 días: ${total}`}</p>
      <div class="plot${small ? " small" : ""}" role="group" aria-label="${esc(title)}: ${total} en 30 días">${cols}</div>
      <div class="axis"><span>${fmtDay(series[0].day)}</span><span>máx. ${max}</span><span>${fmtDay(series[series.length - 1].day)}</span></div>
    </div>`;
}

function ranks(list) {
  if (!list.length) return "";
  const max = list[0].count;
  return `<div class="card"><h3>Oficios más pedidos (30 días)</h3>${list.map((c) => `
    <div class="rank"><span>${esc(CAT[c.category] || c.category)}</span><div class="track"><i style="width:${Math.max(4, (c.count / max) * 100)}%"></i></div><b>${c.count}</b></div>`).join("")}</div>`;
}

function table() {
  const cols = [["Día", (d) => fmtDay(d.day)], ["Activas", (d) => d.active_users], ["Nuevas", (d) => d.new_users], ["Diagn.", (d) => d.diagnoses],
    ["Solic.", (d) => d.requests], ["Grok", (d) => d.ai_grok], ["Gemini", (d) => d.ai_gemini]];
  const rows = [...data.series].reverse().map((d) => `<tr>${cols.map(([, f]) => `<td>${f(d)}</td>`).join("")}</tr>`).join("");
  return `<div class="card"><table><thead><tr>${cols.map(([h]) => `<th scope="col">${h}</th>`).join("")}</tr></thead><tbody>${rows}</tbody></table></div>`;
}

function dashboardView() {
  const s = data;
  const updated = s ? new Date(s.generated_at).toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit" }) : "";
  const head = `
    <div class="header">
      <div><h1>BE HAPPY Admin</h1><p class="muted">${s ? `Actualizado ${updated} · se actualiza cada minuto` : "Cargando…"}</p></div>
      <button class="icon-btn" id="refresh" aria-label="Actualizar" title="Actualizar">${loading ? "…" : "↻"}</button>
      <button class="icon-btn" id="logout" aria-label="Salir" title="Salir">⎋</button>
    </div>
    ${error ? `<p class="error">${esc(error)}</p>` : ""}
    ${installHint()}`;
  if (!s) return head;
  return head + `
    <h2>Personas</h2>
    ${tiles([["Activas hoy", s.users.active_today], ["Activas 7 días", s.users.active_7d], ["Activas 30 días", s.users.active_30d],
      ["Cuentas en total", s.users.total], ["Nuevas hoy", s.users.new_today], ["Nuevas 7 días", s.users.new_7d]])}
    ${bars("active", "Personas activas por día", (d) => d.active_users)}
    ${bars("new", "Cuentas nuevas por día", (d) => d.new_users)}
    <p class="note">«Activa» = abrió la app con sesión ese día. Se cuenta desde el 23/11/2026.</p>

    <h2>Diagnósticos</h2>
    ${tiles([["Hoy", s.diagnoses.today], ["Últimos 7 días", s.diagnoses.last_7d], ["Fallidos 7 días", s.diagnoses.failed_7d], ["En total", s.diagnoses.total]])}
    ${bars("diag", "Diagnósticos por día", (d) => d.diagnoses)}
    ${ranks(s.diagnoses.top_categories_30d)}

    <h2>Inteligencia artificial</h2>
    ${tiles([[`Grok hoy (tope ${s.ai.grok_daily_cap})`, s.ai.grok_today], [`Gemini hoy (tope ${s.ai.gemini_daily_cap})`, s.ai.gemini_today]])}
    <div class="two" style="margin-top:8px">${bars("grok", "Grok por día", (d) => d.ai_grok, true)}${bars("gemini", "Gemini por día", (d) => d.ai_gemini, true)}</div>
    <p class="note">Principal: ${s.ai.primary === "grok" ? "Grok (Gemini de reserva)" : "Gemini"}. Incluye diagnósticos y traducciones.</p>

    <h2>Especialistas</h2>
    ${tiles([["Registrados", s.specialists.total], ["Membresía activa", s.specialists.active_membership], ["Verificados", s.specialists.verified], ["Verificación pendiente", s.specialists.in_review]])}

    <h2>Solicitudes y chats</h2>
    ${tiles([["Solicitudes abiertas", s.marketplace.requests_open], ["Solicitudes 30 días", s.marketplace.requests_30d], ["Presupuestos 30 días", s.marketplace.quotes_30d],
      ["Presupuestos aceptados 30 días", s.marketplace.quotes_accepted_30d], ["Conversaciones 30 días", s.marketplace.conversations_30d], ["Conversaciones en total", s.marketplace.conversations_total]])}
    ${bars("req", "Solicitudes por día", (d) => d.requests)}

    <h2>Ferreterías</h2>
    ${tiles([["En el mapa", s.stores.on_map], ["Pendientes de revisión", s.stores.pending]])}

    <button class="link" id="table" aria-expanded="${showTable}">${showTable ? "▴ Ocultar tabla" : "☰ Ver los datos en tabla"}</button>
    ${showTable ? table() : ""}`;
}

function render() {
  app.innerHTML = token && (data || error !== "Clave incorrecta") ? dashboardView() : loginView();
}

// --- events ---
app.addEventListener("submit", async (e) => {
  if (e.target.id !== "login") return;
  e.preventDefault();
  const t = document.getElementById("key").value.trim();
  if (!t) return;
  if (await load(t)) {
    token = t;
    save(t);
    render();
  }
});
app.addEventListener("click", async (e) => {
  const b = e.target.closest("button");
  if (!b) return;
  if (b.dataset.chart) { selected[b.dataset.chart] = Number(b.dataset.i); render(); }
  else if (b.id === "refresh") load(token);
  else if (b.id === "logout") { token = ""; data = null; error = ""; save(""); render(); }
  else if (b.id === "table") { showTable = !showTable; render(); }
  else if (b.id === "install" && installEvent) { installEvent.prompt(); await installEvent.userChoice; installEvent = null; render(); }
});
addEventListener("beforeinstallprompt", (e) => { e.preventDefault(); installEvent = e; render(); });
addEventListener("appinstalled", () => { installEvent = null; render(); });
setInterval(() => { if (token && document.visibilityState === "visible") load(token); }, 60_000);
document.addEventListener("visibilitychange", () => { if (token && document.visibilityState === "visible" && data) load(token); });

if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {});
if (token) load(token); else render();
