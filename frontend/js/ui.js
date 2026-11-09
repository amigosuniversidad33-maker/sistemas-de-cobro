// Utilidades de interfaz: escape, formato, toasts, modal, confirmación, formularios y tablas paginadas.
import { icono } from "./iconos.js";

export function esc(v) {
  return String(v ?? "").replace(/[&<>"'`]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;", "`": "&#96;" }[c]));
}

const fmtFecha = new Intl.DateTimeFormat("es-GT", { dateStyle: "short", timeStyle: "short", timeZone: "America/Guatemala" });
export const fecha = (iso) => (iso ? fmtFecha.format(new Date(iso)) : "—");
export const dia = (iso) => (iso ? String(iso).slice(0, 10).split("-").reverse().join("/") : "—");
export const num = (n) => (n === null || n === undefined ? "—" : new Intl.NumberFormat("es-GT").format(n));
export const pct = (n) => (n === null || n === undefined ? "—" : `${new Intl.NumberFormat("es-GT", { maximumFractionDigits: 1 }).format(n)} %`);
export function dinero(monto, moneda = "GTQ") {
  if (monto === null || monto === undefined) return "—";
  const simbolo = moneda === "GTQ" ? "Q" : moneda === "USD" ? "US$" : moneda;
  return `${simbolo} ${new Intl.NumberFormat("es-GT", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(Number(monto))}`;
}
export const hoyLocal = () => new Intl.DateTimeFormat("en-CA", { timeZone: "America/Guatemala" }).format(new Date());

const COLORES = {
  ACTIVO: "verde", ACTIVA: "verde", PUBLICADO: "verde", CUMPLIDA: "verde", CONTESTADA: "verde", FINALIZADA: "", DISPONIBLE: "verde",
  LIBRE: "verde", COMPLETADO: "verde", REVISADA: "verde", PROMESA: "verde", BAJA: "", LISTA_PARA_PILOTO: "verde",
  BORRADOR: "gris", INACTIVO: "gris", ARCHIVADO: "gris", CANCELADA: "gris", CANCELADO: "gris", SIN_VERIFICAR: "gris", CERRADA: "gris",
  PAUSADA: "naranja", PENDIENTE: "naranja", RECHAZADA: "naranja", MEDIA: "naranja", EN_COLA: "naranja", RECONOCIDA: "naranja", EN_CURSO: "violeta",
  INCUMPLIDA: "rojo", FALLIDA: "rojo", FALLIDO: "rojo", EXCLUIDO: "rojo", ALTA: "rojo", CRITICA: "rojo", NO_DISPONIBLE: "rojo",
  BLOQUEADA: "rojo", OCUPADO: "violeta", ABIERTA: "rojo", SIN_CONTESTAR: "gris", BLOQUEADO: "gris", "CRÍTICO": "rojo", MEDIO: "naranja", BAJO: "verde",
};
export function chip(valor, texto) {
  if (valor === null || valor === undefined || valor === "") return '<span class="texto-tenue">—</span>';
  return `<span class="chip ${COLORES[valor] ?? ""}">${esc(texto ?? String(valor).replaceAll("_", " "))}</span>`;
}
export function modo(canal, modoLl) {
  if (canal === "TELEFONIA") return `<span class="modo modo-real">${icono("telefono")}TELEFONÍA REAL</span>`;
  if (canal === "VOZ_NAVEGADOR") return `<span class="modo modo-prueba">${icono("mic")}VOZ DE PRUEBA</span>`;
  if (canal === "TEXTO") return `<span class="modo modo-prueba">PRUEBA · TEXTO</span>`;
  return `<span class="modo modo-simulacion">SIMULACIÓN</span>`;
}

export function toast(mensaje, tipo = "info") {
  const t = document.createElement("div");
  t.className = `toast ${tipo}`;
  t.setAttribute("role", tipo === "error" ? "alert" : "status");
  t.innerHTML = `${icono(tipo === "error" ? "alerta" : "check")}<span>${esc(mensaje)}</span>`;
  document.getElementById("toasts").appendChild(t);
  setTimeout(() => t.remove(), tipo === "error" ? 7000 : 4000);
}

export function errorToast(e) {
  const extra = e.errores?.length ? ": " + e.errores.map((x) => `${x.campo} ${x.mensaje}`).join("; ") : "";
  toast((e.message || "Error") + extra, "error");
}

// ---------------------------------------------------------------- modal
const modal = () => document.getElementById("modal");
export function abrirModal({ titulo, contenido, botones = [], alAbrir }) {
  const m = modal();
  document.getElementById("modal-titulo").textContent = titulo;
  const c = document.getElementById("modal-contenido");
  c.innerHTML = contenido;
  const pie = document.getElementById("modal-pie");
  pie.innerHTML = "";
  botones.forEach((b) => {
    const el = document.createElement("button");
    el.type = "button";
    el.className = `btn ${b.clase || "btn-secundario"}`;
    el.textContent = b.texto;
    el.addEventListener("click", async () => {
      if (!b.accion) return cerrarModal();
      el.disabled = true;
      try {
        const r = await b.accion(c);
        if (r !== false) cerrarModal();
      } catch (e) {
        mostrarErroresForm(c, e);
      } finally {
        el.disabled = false;
      }
    });
    pie.appendChild(el);
  });
  document.getElementById("modal-cerrar").innerHTML = icono("cerrar");
  document.getElementById("modal-cerrar").onclick = cerrarModal;
  if (!m.open) m.showModal();
  alAbrir?.(c);
  c.querySelector("input,select,textarea")?.focus();
  return c;
}
export function cerrarModal() { if (modal().open) modal().close(); }

export function confirmar(titulo, mensaje, { textoOk = "Confirmar", peligro = false } = {}) {
  return new Promise((resolver) => {
    abrirModal({
      titulo,
      contenido: `<p>${esc(mensaje)}</p>`,
      botones: [
        { texto: "Cancelar", accion: () => resolver(false) },
        { texto: textoOk, clase: peligro ? "btn-peligro" : "btn-primario", accion: () => resolver(true) },
      ],
    });
    modal().addEventListener("close", () => resolver(false), { once: true });
  });
}

// ---------------------------------------------------------------- formularios
// campos: [{nombre, etiqueta, tipo, opciones:[{valor,texto}], requerido, ayuda, ancho, valor, min, max, paso, patron}]
export function formulario(campos, valores = {}) {
  return `<div class="form-rejilla">${campos.map((c) => {
    const v = valores[c.nombre] ?? c.valor ?? "";
    const id = `f-${c.nombre}`;
    const req = c.requerido ? "required" : "";
    const attrs = `id="${id}" name="${c.nombre}" ${req} ${c.max !== undefined ? `max="${c.max}"` : ""} ${c.min !== undefined ? `min="${c.min}"` : ""} ${c.paso ? `step="${c.paso}"` : ""} ${c.maxlength ? `maxlength="${c.maxlength}"` : ""} ${c.patron ? `pattern="${esc(c.patron)}"` : ""}`;
    let control;
    if (c.tipo === "select") {
      control = `<select ${attrs}>${(c.opciones || []).map((o) => `<option value="${esc(o.valor)}" ${String(o.valor) === String(v) ? "selected" : ""}>${esc(o.texto)}</option>`).join("")}</select>`;
    } else if (c.tipo === "textarea") {
      control = `<textarea ${attrs}>${esc(v)}</textarea>`;
    } else if (c.tipo === "checkbox") {
      return `<div class="campo ${c.ancho ? "ancho" : ""}"><label class="check"><input type="checkbox" ${attrs} ${v ? "checked" : ""}> ${esc(c.etiqueta)}</label></div>`;
    } else {
      control = `<input type="${c.tipo || "text"}" ${attrs} value="${esc(v)}" ${c.autocompletar ? `autocomplete="${c.autocompletar}"` : ""}>`;
    }
    return `<div class="campo ${c.ancho ? "ancho" : ""}"><label for="${id}">${esc(c.etiqueta)}${c.requerido ? " *" : ""}</label>${control}${c.ayuda ? `<small>${esc(c.ayuda)}</small>` : ""}<span class="error-campo" data-error="${c.nombre}"></span></div>`;
  }).join("")}<p class="error-form ancho" data-error-general hidden></p></div>`;
}

export function leerFormulario(contenedor, campos) {
  const datos = {};
  let valido = true;
  contenedor.querySelectorAll("[data-error]").forEach((e) => (e.textContent = ""));
  for (const c of campos) {
    const el = contenedor.querySelector(`[name="${c.nombre}"]`);
    if (!el) continue;
    let v = c.tipo === "checkbox" ? el.checked : el.value.trim();
    if (c.requerido && (v === "" || v === null)) {
      contenedor.querySelector(`[data-error="${c.nombre}"]`).textContent = "Campo obligatorio.";
      valido = false;
      continue;
    }
    if (c.tipo === "number" && v !== "") v = Number(v);
    if (["select"].includes(c.tipo) && c.numerico && v !== "") v = Number(v);
    if (v === "" && !c.requerido) v = c.vacioComo !== undefined ? c.vacioComo : null;
    datos[c.nombre] = v;
  }
  if (!valido) throw Object.assign(new Error("Revise los campos marcados."), { local: true });
  return datos;
}

export function mostrarErroresForm(contenedor, e) {
  const general = contenedor.querySelector("[data-error-general]");
  (e.errores || []).forEach((x) => {
    const el = contenedor.querySelector(`[data-error="${x.campo}"]`);
    if (el) el.textContent = x.mensaje;
  });
  if (general) {
    general.hidden = false;
    general.textContent = e.message || "Error";
  } else {
    errorToast(e);
  }
}

// ---------------------------------------------------------------- tabla paginada con filtros
// opciones: {contenedor, titulo, descripcion, cargar(params)->{items,total,...}, columnas:[{titulo, html(fila), clase}],
//           filtros:[{nombre, etiqueta, tipo, opciones}], acciones: html, porPagina}
export function tablaPaginada(op) {
  const estado = { pagina: 1, filtros: {} };
  (op.filtros || []).forEach((f) => { if (f.valor !== undefined) estado.filtros[f.nombre] = f.valor; });
  op.contenedor.innerHTML = `
    <section class="tarjeta">
      <div class="tarjeta-cab"><div><h2>${esc(op.titulo)}</h2>${op.descripcion ? `<p>${esc(op.descripcion)}</p>` : ""}</div>
        <div class="acciones">${op.acciones || ""}</div></div>
      ${op.filtros?.length ? `<form class="filtros" data-filtros>${op.filtros.map((f) => `
        <div class="campo"><label for="flt-${f.nombre}">${esc(f.etiqueta)}</label>
        ${f.tipo === "select" ? `<select id="flt-${f.nombre}" name="${f.nombre}">${f.opciones.map((o) => `<option value="${esc(o.valor)}" ${String(o.valor) === String(f.valor ?? "") ? "selected" : ""}>${esc(o.texto)}</option>`).join("")}</select>`
          : `<input id="flt-${f.nombre}" name="${f.nombre}" type="${f.tipo || "search"}" value="${esc(f.valor ?? "")}" ${f.tipo === "search" || !f.tipo ? 'placeholder="Buscar…"' : ""}>`}</div>`).join("")}
        <button class="btn btn-secundario" type="submit">${icono("buscar")}Filtrar</button></form>` : ""}
      <div class="tabla-envoltura" data-tabla><div class="estado-carga cargando">Cargando</div></div>
      <div class="paginacion" data-paginacion></div>
    </section>`;
  const cont = op.contenedor;
  async function render() {
    const zona = cont.querySelector("[data-tabla]");
    zona.innerHTML = '<div class="estado-carga cargando">Cargando</div>';
    try {
      const datos = await op.cargar({ ...estado.filtros, pagina: estado.pagina, por_pagina: op.porPagina || 15 });
      const items = datos.items ?? datos;
      if (!items.length) {
        zona.innerHTML = `<div class="estado-vacio">${esc(op.vacio || "No hay registros para mostrar.")}</div>`;
      } else {
        zona.innerHTML = `<table><thead><tr>${op.columnas.map((c) => `<th class="${c.clase || ""}">${esc(c.titulo)}</th>`).join("")}</tr></thead>
          <tbody>${items.map((f, i) => `<tr data-i="${i}">${op.columnas.map((c) => `<td class="${c.clase || ""}">${c.html(f)}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
        op.alRenderizar?.(zona, items);
      }
      const pag = cont.querySelector("[data-paginacion]");
      if (datos.total !== undefined) {
        pag.innerHTML = `<span>${num(datos.total)} registro(s) · página ${datos.pagina} de ${datos.paginas}</span>
          <span class="acciones"><button class="btn btn-secundario btn-chico" data-ant ${datos.pagina <= 1 ? "disabled" : ""}>Anterior</button>
          <button class="btn btn-secundario btn-chico" data-sig ${datos.pagina >= datos.paginas ? "disabled" : ""}>Siguiente</button></span>`;
        pag.querySelector("[data-ant]").onclick = () => { estado.pagina--; render(); };
        pag.querySelector("[data-sig]").onclick = () => { estado.pagina++; render(); };
      } else pag.innerHTML = "";
    } catch (e) {
      zona.innerHTML = `<div class="estado-error">${icono("alerta")} ${esc(e.message)}</div>`;
    }
  }
  cont.querySelector("[data-filtros]")?.addEventListener("submit", (ev) => {
    ev.preventDefault();
    estado.filtros = Object.fromEntries(new FormData(ev.target).entries());
    estado.pagina = 1;
    render();
  });
  render();
  return { recargar: render };
}

export function tarjeta(titulo, cuerpo, { descripcion = "", acciones = "" } = {}) {
  return `<section class="tarjeta"><div class="tarjeta-cab"><div><h2>${esc(titulo)}</h2>${descripcion ? `<p>${esc(descripcion)}</p>` : ""}</div><div class="acciones">${acciones}</div></div><div class="tarjeta-cuerpo">${cuerpo}</div></section>`;
}

export function boton(texto, { ico, clase = "btn-secundario", datos = "", chico = false } = {}) {
  return `<button type="button" class="btn ${clase} ${chico ? "btn-chico" : ""}" ${datos}>${ico ? icono(ico) : ""}${esc(texto)}</button>`;
}

export const opcionesDe = (lista, valor, texto, vacio) =>
  (vacio !== undefined ? [{ valor: "", texto: vacio }] : []).concat(lista.map((x) => ({ valor: x[valor], texto: typeof texto === "function" ? texto(x) : x[texto] })));
