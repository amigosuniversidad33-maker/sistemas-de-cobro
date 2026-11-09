// Arranque de la aplicación: sesión, navegación por permisos y enrutamiento por hash.
import { api, get, onNoAutenticado, post } from "./api.js";
import { icono } from "./iconos.js";
import { esc, toast } from "./ui.js";

const RUTAS = [
  { grupo: "Supervisión" },
  { id: "control", titulo: "Control y Supervisión", ico: "actividad", permiso: "dashboard.ver", modulo: "./vistas/control.js" },
  { grupo: "Call Center" },
  { id: "llamadas", titulo: "Llamadas", ico: "telefono", permiso: "llamadas.ver", modulo: "./vistas/llamadas.js" },
  { id: "agentes-ia", titulo: "Agentes IA", ico: "bot", permiso: "agentes.ver", modulo: "./vistas/agentes.js" },
  { id: "agentes-internos", titulo: "Agentes Internos", ico: "usuarios", permiso: "usuarios.ver", modulo: "./vistas/internos.js" },
  { id: "entrenamiento", titulo: "Entrenamiento", ico: "libro", permiso: "agentes.ver", modulo: "./vistas/entrenamiento.js" },
  { id: "campanas", titulo: "Campañas", ico: "megafono", permiso: "campanas.ver", modulo: "./vistas/campanas.js" },
  { id: "promesas", titulo: "Promesas de Pago", ico: "promesa", permiso: "promesas.ver", modulo: "./vistas/promesas.js" },
  { id: "no-contactables", titulo: "No Contactables", ico: "nocontacto", permiso: "exclusiones.ver", modulo: "./vistas/exclusiones.js" },
  { id: "prueba", titulo: "Prueba de Llamada", ico: "prueba", permiso: "prueba.ejecutar", modulo: "./vistas/prueba.js" },
  { id: "qa", titulo: "QA / Análisis", ico: "qa", permiso: "qa.ver", modulo: "./vistas/qa.js" },
  { grupo: "Infraestructura y Seguridad" },
  { id: "plantas", titulo: "Plantas FreeSWITCH", ico: "servidor", permiso: "telefonia.ver", modulo: "./vistas/plantas.js" },
  { id: "extensiones", titulo: "Extensiones SIP", ico: "red", permiso: "telefonia.ver", modulo: "./vistas/extensiones.js" },
  { id: "seguridad-ia", titulo: "Seguridad IA", ico: "escudo", permiso: "seguridad.ver", modulo: "./vistas/seguridad.js" },
  { grupo: "Administración" },
  { id: "clientes", titulo: "Clientes y Deudas", ico: "base", permiso: "clientes.ver", modulo: "./vistas/clientes.js" },
  { id: "auditoria", titulo: "Auditoría", ico: "documento", permiso: "auditoria.ver", modulo: "./vistas/auditoria.js" },
  { id: "sistema", titulo: "Sistema", ico: "ajustes", permiso: "dashboard.ver", modulo: "./vistas/sistema.js" },
];

const estado = { usuario: null };
export const ctx = {
  get usuario() { return estado.usuario; },
  tiene: (p) => !!estado.usuario?.permisos?.includes(p),
};

function mostrarLogin() {
  estado.usuario = null;
  document.getElementById("vista-app").hidden = true;
  document.getElementById("vista-login").hidden = false;
  document.getElementById("login-usuario").focus();
}

function construirNav() {
  const nav = document.getElementById("nav");
  let html = "";
  let grupoPendiente = null;
  for (const r of RUTAS) {
    if (r.grupo) { grupoPendiente = r.grupo; continue; }
    if (!ctx.tiene(r.permiso)) continue;
    if (grupoPendiente) { html += `<div class="nav-grupo">${esc(grupoPendiente)}</div>`; grupoPendiente = null; }
    html += `<a class="nav-item" href="#/${r.id}" data-ruta="${r.id}">${icono(r.ico)}<span>${esc(r.titulo)}</span></a>`;
  }
  nav.innerHTML = html;
}

async function mostrarApp(usuario) {
  estado.usuario = usuario;
  document.getElementById("vista-login").hidden = true;
  document.getElementById("vista-app").hidden = false;
  document.getElementById("usuario-nombre").textContent = `${usuario.nombre} ${usuario.apellido}`;
  document.getElementById("usuario-rol").textContent = usuario.rol;
  construirNav();
  await enrutar();
  actualizarPausa();
}

export async function actualizarPausa() {
  try {
    const p = (await get("/api/sistema/parametros")).find((x) => x.clave === "pausa_emergencia");
    const aviso = document.getElementById("aviso-pausa");
    aviso.hidden = !(p && p.valor === "1");
    aviso.innerHTML = `${icono("emergencia")} Pausa de emergencia activa`;
  } catch { /* sin permiso o sin conexión */ }
}

async function enrutar() {
  if (!estado.usuario) return;
  const id = (location.hash.replace(/^#\//, "") || "").split("?")[0];
  const disponibles = RUTAS.filter((r) => r.id && ctx.tiene(r.permiso));
  const ruta = disponibles.find((r) => r.id === id) || disponibles[0];
  if (!ruta) {
    document.getElementById("contenido").innerHTML = '<div class="estado-vacio">Su rol no tiene módulos asignados.</div>';
    return;
  }
  if (ruta.id !== id) { history.replaceState(null, "", `#/${ruta.id}`); }
  document.querySelectorAll(".nav-item").forEach((a) => a.classList.toggle("activo", a.dataset.ruta === ruta.id));
  document.getElementById("titulo-pagina").textContent = ruta.titulo;
  document.title = `${ruta.titulo} · Cobros IA`;
  const cont = document.getElementById("contenido");
  cont.innerHTML = '<div class="estado-carga cargando">Cargando módulo</div>';
  document.getElementById("menu").classList.remove("abierto");
  try {
    const mod = await import(ruta.modulo);
    cont.innerHTML = "";
    await mod.render(cont, ctx);
    cont.focus({ preventScroll: true });
  } catch (e) {
    cont.innerHTML = `<div class="estado-error">${icono("alerta")} No se pudo cargar el módulo: ${esc(e.message)}</div>`;
  }
}

document.getElementById("form-login").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const err = document.getElementById("login-error");
  err.hidden = true;
  const boton = ev.target.querySelector("button");
  boton.disabled = true;
  try {
    const r = await api("/api/auth/login", { metodo: "POST", cuerpo: {
      usuario: document.getElementById("login-usuario").value.trim(),
      password: document.getElementById("login-password").value,
    } });
    document.getElementById("login-password").value = "";
    await mostrarApp(r.usuario);
  } catch (e) {
    err.textContent = e.message;
    err.hidden = false;
  } finally {
    boton.disabled = false;
  }
});

document.getElementById("btn-salir").addEventListener("click", async () => {
  try { await post("/api/auth/logout"); } catch { /* ya expirada */ }
  location.hash = "";
  mostrarLogin();
  toast("Sesión cerrada.");
});

const btnMenu = document.getElementById("btn-menu");
btnMenu.innerHTML = icono("menu");
btnMenu.addEventListener("click", () => {
  const m = document.getElementById("menu");
  m.classList.toggle("abierto");
  btnMenu.setAttribute("aria-expanded", m.classList.contains("abierto"));
});

window.addEventListener("hashchange", enrutar);
onNoAutenticado(mostrarLogin);

(async () => {
  try {
    const r = await get("/api/auth/yo");
    await mostrarApp(r.usuario);
  } catch {
    mostrarLogin();
  }
})();
