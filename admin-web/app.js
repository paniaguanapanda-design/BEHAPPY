// BE HAPPY Admin: private panel, installable as an app. Reads /api/admin/stats with the server's ADMIN_TOKEN.
"use strict";

const KEY = "bh-admin-token";
const CAT = { plumbing: "Fontanería", electrical: "Electricidad", hvac: "Climatización", masonry: "Obra", carpentry: "Carpintería" };
const app = document.getElementById("app");
let token = read();
let data = null;
let people = null; // lista de especialistas (/api/admin/specialists)
let loading = false;
let error = "";
let showTable = false;
let installEvent = null;
let anuncios = null; // anuncios publicados (/api/admin/anuncios)
let annMsg = "";
let annErr = false;
let annBusy = false;
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
    // La lista es aparte: si falla, el resto del panel sigue funcionando.
    try {
      const r2 = await fetch("/api/admin/specialists", { headers: { "X-Admin-Token": t }, cache: "no-store" });
      if (r2.ok) people = await r2.json();
    } catch { /* sin lista por ahora */ }
    try {
      const r3 = await fetch("/api/admin/anuncios", { headers: { "X-Admin-Token": t }, cache: "no-store" });
      if (r3.ok) anuncios = (await r3.json()).items;
    } catch { /* sin anuncios por ahora */ }
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

// Aviso de una sola vía: el administrador escribe, el especialista lo recibe por correo y/o notificación.
let notice = null; // { sid, subject, text, email, push, busy, msg, err }
const noticeHistory = {}; // specialist_id -> avisos enviados

function noticeForm(p) {
  const hist = noticeHistory[p.specialist_id] || [];
  const list = hist.length
    ? `<ul class="hist">${hist.slice(0, 5).map((x) => `<li>${esc(fmtDay(x.created_at))} · ${esc(x.subject)}${x.read_at ? " · leído" : ""}</li>`).join("")}</ul>`
    : `<p class="muted">Todavía no se le ha enviado ningún aviso.</p>`;
  return `
    <form class="notice" id="notice-form" data-sid="${esc(p.specialist_id)}">
      <input id="n-subject" maxlength="120" placeholder="Asunto" aria-label="Asunto" value="${esc(notice.subject)}" required>
      <textarea id="n-text" rows="4" maxlength="2000" placeholder="Mensaje" aria-label="Mensaje" required>${esc(notice.text)}</textarea>
      <label class="check"><input type="checkbox" id="n-email" ${notice.email ? "checked" : ""}> Enviar por correo</label>
      <label class="check"><input type="checkbox" id="n-push" ${notice.push ? "checked" : ""}> Notificación en el móvil</label>
      ${notice.msg ? `<p class="${notice.err ? "error" : "muted"}">${esc(notice.msg)}</p>` : ""}
      <div class="row">
        <button class="btn" ${notice.busy ? "disabled" : ""}>${notice.busy ? "Enviando…" : "Enviar aviso"}</button>
        <button type="button" class="link" id="n-cancel">Cancelar</button>
      </div>
      <p class="muted">Últimos avisos:</p>${list}
    </form>`;
}

async function loadNotices(sid) {
  try {
    const res = await fetch(`/api/admin/specialists/${encodeURIComponent(sid)}/notices`, { headers: { "X-Admin-Token": token }, cache: "no-store" });
    if (res.ok) { noticeHistory[sid] = await res.json(); render(); }
  } catch { /* sin historial por ahora */ }
}

// Lista de especialistas: nombre, oficios, contacto y estado. Pensada para comprobar quién se ha inscrito.
function peopleList() {
  if (!people) return "";
  if (!people.length) return `<div class="card"><p class="muted">Todavía no hay especialistas inscritos.</p></div>`;
  const status = { verified: "Verificado", in_review: "En revisión", rejected: "Rechazado", none: "Sin verificar" };
  const rows = people.map((p) => `
    <li class="person">
      <div class="who"><b>${esc(p.name || "(sin nombre)")}</b>
        <span class="muted">${esc((p.categories || []).map((c) => CAT[c] || c).join(", "))}</span></div>
      <div class="meta">${p.phone ? `<a href="tel:${esc(p.phone)}">${esc(p.phone)}</a>` : ""}${p.email ? ` · ${esc(p.email)}` : ""}</div>
      <div class="meta">${esc(status[p.verification_status] || p.verification_status)} · ${p.membership_active ? "membresía activa" : "sin membresía"} · alta ${esc(fmtDay(p.created_at || "0000-00-00"))}</div>
      <button class="link" data-notice="${esc(p.specialist_id)}" aria-expanded="${notice?.sid === p.specialist_id}">${notice?.sid === p.specialist_id ? "▴ Cerrar" : "✉ Enviar aviso"}</button>
      ${notice?.sid === p.specialist_id ? noticeForm(p) : ""}
    </li>`).join("");
  return `<div class="card"><h3>Inscritos (${people.length})</h3><ul class="people">${rows}</ul></div>`;
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
    ${peopleList()}

    <h2>Solicitudes y chats</h2>
    ${tiles([["Solicitudes abiertas", s.marketplace.requests_open], ["Solicitudes 30 días", s.marketplace.requests_30d], ["Presupuestos 30 días", s.marketplace.quotes_30d],
      ["Presupuestos aceptados 30 días", s.marketplace.quotes_accepted_30d], ["Conversaciones 30 días", s.marketplace.conversations_30d], ["Conversaciones en total", s.marketplace.conversations_total]])}
    ${bars("req", "Solicitudes por día", (d) => d.requests)}

    <h2>Ferreterías</h2>
    ${tiles([["En el mapa", s.stores.on_map], ["Pendientes de revisión", s.stores.pending]])}

    <button class="link" id="table" aria-expanded="${showTable}">${showTable ? "▴ Ocultar tabla" : "☰ Ver los datos en tabla"}</button>
    ${anunciosView()}
    ${showTable ? table() : ""}`;
}

// --- anuncios: novedades, promociones, eventos o sorteos para todos, clientes o especialistas ---
function anunciosView() {
  const list = (anuncios || []).filter((a) => a.active);
  const cuando = (a) => (a.ends_at ? `hasta ${new Date(a.ends_at).toLocaleDateString("es-ES")}` : "permanente");
  return `
    <h2>Anuncios</h2>
    <form id="ann-form" class="card" style="display:grid;gap:10px">
      <label>Tipo
        <select id="a-type">
          <option value="novedad">Novedad</option><option value="promocion">Promoción</option>
          <option value="evento">Evento</option><option value="sorteo">Sorteo (necesita bases legales)</option>
        </select>
      </label>
      <label>Título <input id="a-title" maxlength="100" required></label>
      <label>Texto <textarea id="a-text" rows="4" maxlength="500" required></textarea></label>
      <label>Para
        <select id="a-audience">
          <option value="todos">Todos</option><option value="clientes">Solo clientes</option><option value="especialistas">Solo especialistas</option>
        </select>
      </label>
      <label><input type="checkbox" id="a-nuevos"> Solo personas nuevas (registradas en los últimos 30 días)</label>
      <fieldset style="border:0;padding:0;display:grid;gap:6px">
        <label><input type="radio" name="a-dur" value="perm" checked> Permanente (hasta que lo quites)</label>
        <label><input type="radio" name="a-dur" value="temp"> Temporal, hasta
          <input type="datetime-local" id="a-fin" disabled></label>
      </fieldset>
      <label>Enlace (opcional, https://) <input id="a-link" placeholder="https://..."></label>
      <label>Foto (opcional, JPEG o PNG) <input type="file" id="a-foto" accept="image/jpeg,image/png"></label>
      <button type="submit" id="a-enviar" ${annBusy ? "disabled" : ""}>${annBusy ? "Publicando…" : "Publicar anuncio"}</button>
      ${annMsg ? `<p class="${annErr ? "error" : "note"}" role="status">${esc(annMsg)}</p>` : ""}
    </form>
    <h3>Publicados ahora</h3>
    ${list.length ? `<ul>${list.map((a) => `
      <li style="margin:8px 0">
        <strong>${esc(a.title)}</strong> · ${esc(a.type)} · ${esc(a.audience)}${a.solo_nuevos ? " · solo nuevos" : ""} · ${cuando(a)}
        <button class="link" data-desactivar="${esc(a.announcement_id)}">Quitar</button>
      </li>`).join("")}</ul>` : `<p class="muted">No hay anuncios activos.</p>`}`;
}

// Foto: se reduce en el navegador (máx. 1280 px, JPEG) para que pese poco.
function fotoComprimida(file) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => {
      const k = Math.min(1, 1280 / Math.max(img.width, img.height));
      const c = document.createElement("canvas");
      c.width = Math.round(img.width * k); c.height = Math.round(img.height * k);
      c.getContext("2d").drawImage(img, 0, 0, c.width, c.height);
      URL.revokeObjectURL(url);
      resolve(c.toDataURL("image/jpeg", 0.85));
    };
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error("No se pudo leer la foto")); };
    img.src = url;
  });
}

async function refrescarAnuncios() {
  try {
    const r = await fetch("/api/admin/anuncios", { headers: { "X-Admin-Token": token }, cache: "no-store" });
    if (r.ok) anuncios = (await r.json()).items;
  } catch { /* sin conexión: queda la lista anterior */ }
}

async function publicarAnuncio(e) {
  e.preventDefault();
  const v = (id) => document.getElementById(id).value.trim();
  const body = {
    type: v("a-type"), title: v("a-title"), text: v("a-text"), audience: v("a-audience"),
    solo_nuevos: document.getElementById("a-nuevos").checked,
    permanente: document.querySelector('input[name="a-dur"]:checked').value === "perm",
  };
  const fin = v("a-fin");
  if (!body.permanente) {
    if (!fin) { annMsg = "Pon la fecha de fin o elige permanente."; annErr = true; return render(); }
    body.ends_at = new Date(fin).toISOString();
  }
  if (v("a-link")) body.link = v("a-link");
  const file = document.getElementById("a-foto").files[0];
  if (file) {
    try { body.imagen_base64 = await fotoComprimida(file); }
    catch (err) { annMsg = err.message; annErr = true; return render(); }
  }
  if (body.type === "sorteo" && !body.link) { annMsg = "Un sorteo necesita el enlace a sus bases legales."; annErr = true; return render(); }
  if (!confirm(`¿Publicar «${body.title}» para ${body.audience}${body.permanente ? " (permanente)" : ""}?`)) return;
  annBusy = true; annMsg = ""; render();
  try {
    const res = await fetch("/api/admin/anuncios", {
      method: "POST", headers: { "X-Admin-Token": token, "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
    const j = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(Array.isArray(j.detail) ? j.detail.map((d) => d.msg).join(". ") : (j.detail || `No se pudo publicar (${res.status})`));
    annMsg = "Anuncio publicado. Aparecerá en la app a quien corresponda."; annErr = false;
    await refrescarAnuncios();
  } catch (err) {
    annMsg = err.message === "Failed to fetch" ? "Sin conexión con el servidor" : err.message; annErr = true;
  } finally {
    annBusy = false;
    render();
  }
}

async function quitarAnuncio(aid) {
  if (!confirm("¿Quitar este anuncio? Deja de aparecer en la app.")) return;
  try {
    const res = await fetch(`/api/admin/anuncios/${encodeURIComponent(aid)}/desactivar`, { method: "POST", headers: { "X-Admin-Token": token } });
    if (!res.ok) throw new Error(`No se pudo quitar (${res.status})`);
    annMsg = "Anuncio quitado."; annErr = false;
    await refrescarAnuncios();
  } catch (err) {
    annMsg = err.message; annErr = true;
  }
  render();
}

function render() {
  app.innerHTML = token && (data || error !== "Clave incorrecta") ? dashboardView() : loginView();
}

// --- events ---
app.addEventListener("change", (e) => {
  if (e.target.name === "a-dur") document.getElementById("a-fin").disabled = e.target.value === "perm";
});
app.addEventListener("submit", async (e) => {
  if (e.target.id === "notice-form") return sendNotice(e);
  if (e.target.id === "ann-form") return publicarAnuncio(e);
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
async function sendNotice(e) {
  e.preventDefault();
  const sid = e.target.dataset.sid;
  const p = (people || []).find((x) => x.specialist_id === sid);
  const subject = document.getElementById("n-subject").value.trim();
  const text = document.getElementById("n-text").value.trim();
  const channels = [document.getElementById("n-email").checked && "email", document.getElementById("n-push").checked && "push"].filter(Boolean);
  if (!subject || !text) return;
  if (!channels.length) { notice = { ...notice, msg: "Elige correo, notificación o ambos.", err: true }; return render(); }
  const to = p?.name || "este especialista";
  if (!confirm(`¿Enviar este aviso a ${to}${channels.includes("email") && p?.email ? ` (${p.email})` : ""}?`)) return;
  notice = { ...notice, subject, text, email: channels.includes("email"), push: channels.includes("push"), busy: true, msg: "", err: false };
  render();
  try {
    const res = await fetch(`/api/admin/specialists/${encodeURIComponent(sid)}/notice`, {
      method: "POST", headers: { "X-Admin-Token": token, "Content-Type": "application/json" }, body: JSON.stringify({ subject, text, channels }),
    });
    const j = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(j.detail || `No se pudo enviar (${res.status})`);
    const note = j.email === false && channels.includes("email") ? " Sin correo: no tiene email registrado." : "";
    notice = { sid, subject: "", text: "", email: true, push: true, busy: false, msg: `Aviso enviado.${note}`, err: false };
    await loadNotices(sid);
  } catch (err) {
    notice = { ...notice, busy: false, msg: err.message === "Failed to fetch" ? "Sin conexión con el servidor" : err.message, err: true };
    render();
  }
}

app.addEventListener("click", async (e) => {
  const b = e.target.closest("button");
  if (!b) return;
  if (b.dataset.desactivar) return quitarAnuncio(b.dataset.desactivar);
  if (b.dataset.notice) {
    const sid = b.dataset.notice;
    if (notice?.sid === sid) notice = null;
    else { notice = { sid, subject: "", text: "", email: true, push: true, busy: false, msg: "", err: false }; loadNotices(sid); }
    render();
  }
  else if (b.id === "n-cancel") { notice = null; render(); }
  else if (b.dataset.chart) { selected[b.dataset.chart] = Number(b.dataset.i); render(); }
  else if (b.id === "refresh") load(token);
  else if (b.id === "logout") { token = ""; data = null; error = ""; save(""); render(); }
  else if (b.id === "table") { showTable = !showTable; render(); }
  else if (b.id === "install" && installEvent) { installEvent.prompt(); await installEvent.userChoice; installEvent = null; render(); }
});
addEventListener("beforeinstallprompt", (e) => { e.preventDefault(); installEvent = e; render(); });
addEventListener("appinstalled", () => { installEvent = null; render(); });
// No se recarga mientras se escribe un aviso, para no borrar lo escrito.
// Tampoco mientras hay un anuncio a medio escribir.
const escribiendo = () => !!notice || !!document.getElementById("ann-form");
setInterval(() => { if (token && !escribiendo() && document.visibilityState === "visible") load(token); }, 60_000);
document.addEventListener("visibilitychange", () => { if (token && document.visibilityState === "visible" && data && !escribiendo()) load(token); });

if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {});
if (token) load(token); else render();
