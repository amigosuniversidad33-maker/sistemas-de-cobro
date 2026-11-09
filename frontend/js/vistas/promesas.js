// Módulo Promesas de Pago: seguimiento, cumplimiento manual auditado y reingreso por incumplimiento.
import { get, post } from "../api.js";
import { icono } from "../iconos.js";
import { abrirModal, boton, chip, dinero, errorToast, esc, fecha, formulario, leerFormulario, tablaPaginada, toast } from "../ui.js";
import { detalle as detalleLlamada } from "./llamadas.js";

export async function render(cont, ctx) {
  const gestionar = ctx.tiene("promesas.gestionar");
  cont.innerHTML = `<div class="banner info">${icono("promesa")}<div>La IA propone monto y fecha, el backend valida contra saldo y plazo, el cliente confirma explícitamente y el sistema registra la promesa una sola vez.
    <strong>Una promesa no es un pago:</strong> sin integración de pagos, el cumplimiento lo registra un usuario autorizado y queda en auditoría. Las promesas vencidas pasan a INCUMPLIDA y el cliente reingresa a la campaña respetando todas las reglas.</div></div><div id="z"></div>`;
  const t = tablaPaginada({
    contenedor: cont.querySelector("#z"),
    titulo: "Promesas de pago",
    acciones: gestionar && ctx.tiene("campanas.todas") ? boton("Revisar vencidas ahora", { ico: "recargar", datos: "data-vencidas" }) : "",
    filtros: [
      { nombre: "estado", etiqueta: "Estado", tipo: "select", opciones: ["", "PENDIENTE", "CUMPLIDA", "INCUMPLIDA", "CANCELADA"].map((v) => ({ valor: v, texto: v || "Todos" })) },
      { nombre: "desde", etiqueta: "Compromiso desde", tipo: "date" },
      { nombre: "hasta", etiqueta: "Compromiso hasta", tipo: "date" },
    ],
    cargar: (p) => get("/api/promesas", p),
    columnas: [
      { titulo: "#", html: (p) => p.id_promesa },
      { titulo: "Cliente", html: (p) => esc(p.cliente) },
      { titulo: "Referencia", html: (p) => `<span class="mono">${esc(p.referencia)}</span>` },
      { titulo: "Campaña", html: (p) => esc(p.campana || "Prueba") },
      { titulo: "Monto", clase: "num", html: (p) => dinero(p.monto, p.moneda) },
      { titulo: "Fecha compromiso", html: (p) => esc(p.fecha_compromiso) },
      { titulo: "Estado", html: (p) => chip(p.estado) },
      { titulo: "Confirmada", html: (p) => fecha(p.confirmada_en) },
      { titulo: "", html: (p) => `<span class="acciones">${boton("Llamada", { chico: true, datos: `data-llamada="${p.id_llamada}"` })} ${boton("Seguimiento", { chico: true, datos: `data-seg="${p.id_promesa}"` })}
        ${gestionar && ["PENDIENTE", "INCUMPLIDA"].includes(p.estado) ? boton("Marcar cumplida", { chico: true, clase: "btn-exito", datos: `data-cumplida="${p.id_promesa}"` }) : ""}
        ${gestionar && p.estado === "PENDIENTE" ? boton("Cancelar", { chico: true, datos: `data-cancelar="${p.id_promesa}"` }) : ""}</span>` },
    ],
    alRenderizar: (z) => {
      z.querySelectorAll("[data-llamada]").forEach((b) => b.addEventListener("click", () => detalleLlamada(b.dataset.llamada, ctx)));
      z.querySelectorAll("[data-seg]").forEach((b) => b.addEventListener("click", async () => {
        try {
          const s = await get(`/api/promesas/${b.dataset.seg}/seguimiento`);
          abrirModal({ titulo: `Seguimiento de promesa #${b.dataset.seg}`, contenido: s.length ? `<ul>${s.map((x) => `<li>${fecha(x.fecha_revision)} · ${esc(x.resultado)}${x.reingreso_campana ? " · reingreso a campaña" : ""}${x.observacion ? ` · ${esc(x.observacion)}` : ""}</li>`).join("")}</ul>` : '<p class="texto-tenue">Sin seguimiento registrado.</p>', botones: [{ texto: "Cerrar" }] });
        } catch (e) { errorToast(e); }
      }));
      const accion = (attr, ruta, titulo, req) => z.querySelectorAll(`[data-${attr}]`).forEach((b) => b.addEventListener("click", () => {
        const c = [{ nombre: "observacion", etiqueta: req ? "Motivo" : "Observación (p. ej., comprobante verificado)", tipo: "textarea", requerido: req, ancho: true, maxlength: 255 }];
        abrirModal({ titulo, contenido: formulario(c), botones: [{ texto: "Volver" }, { texto: "Confirmar", clase: "btn-primario", accion: async (m) => { await post(`/api/promesas/${b.dataset[attr]}/${ruta}`, leerFormulario(m, c)); toast("Promesa actualizada.", "exito"); t.recargar(); } }] });
      }));
      accion("cumplida", "cumplida", "Registrar cumplimiento manual", false);
      accion("cancelar", "cancelar", "Cancelar promesa", true);
    },
  });
  cont.querySelector("[data-vencidas]")?.addEventListener("click", async () => {
    try { const r = await post("/api/promesas/revisar-vencidas"); toast(`Vencidas: ${r.vencidas} · reingresos: ${r.reingresos}`, "exito"); t.recargar(); } catch (e) { errorToast(e); }
  });
}
