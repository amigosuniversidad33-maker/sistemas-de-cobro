// Módulo QA / Análisis: evaluaciones del supervisor IA con evidencia y revisión humana.
import { get, post } from "../api.js";
import { icono } from "../iconos.js";
import { abrirModal, boton, chip, esc, fecha, formulario, leerFormulario, tablaPaginada, toast } from "../ui.js";
import { detalle as detalleLlamada } from "./llamadas.js";

export async function render(cont, ctx) {
  cont.innerHTML = `<div class="banner info">${icono("qa")}<div>El supervisor IA analiza transcripciones minimizadas (con datos sensibles enmascarados), devuelve un resultado estructurado y
    vincula cada hallazgo con un fragmento de evidencia. El sistema verifica que la evidencia exista en la transcripción y eleva la incertidumbre si no la encuentra. Toda evaluación admite revisión humana.</div></div><div id="z"></div>`;
  const t = tablaPaginada({
    contenedor: cont.querySelector("#z"),
    titulo: "Evaluaciones de calidad",
    filtros: [{ nombre: "estado_revision", etiqueta: "Revisión", tipo: "select", opciones: [{ valor: "", texto: "Todas" }, { valor: "PENDIENTE", texto: "Pendiente" }, { valor: "REVISADA", texto: "Revisada" }] }],
    cargar: (p) => get("/api/qa", p),
    columnas: [
      { titulo: "Llamada", html: (q) => boton(`#${q.id_llamada}`, { chico: true, datos: `data-llamada="${q.id_llamada}"` }) },
      { titulo: "Fecha", html: (q) => fecha(q.fecha) },
      { titulo: "Puntaje IA", clase: "num", html: (q) => `<strong>${esc(q.puntaje)}</strong>` },
      { titulo: "Guion", html: (q) => chip(q.cumple_guion ? "COMPLETADO" : "FALLIDO", q.cumple_guion ? "Cumple" : "No cumple") },
      { titulo: "Trato", html: (q) => chip(q.trato_adecuado ? "COMPLETADO" : "FALLIDO", q.trato_adecuado ? "Adecuado" : "Inadecuado") },
      { titulo: "Fuera de política", html: (q) => (q.compromisos_fuera_politica ? chip("ALTA", "Sí") : chip("BAJA", "No")) },
      { titulo: "Incertidumbre", html: (q) => chip(q.incertidumbre) },
      { titulo: "Revisión", html: (q) => chip(q.estado_revision) + (q.puntaje_humano != null ? ` <small>(${esc(q.puntaje_humano)})</small>` : "") },
      { titulo: "", html: (q) => boton("Ver / revisar", { chico: true, datos: `data-ver="${q.id_qa}"` }) },
    ],
    alRenderizar: (z, items) => {
      z.querySelectorAll("[data-llamada]").forEach((b) => b.addEventListener("click", () => detalleLlamada(b.dataset.llamada, ctx)));
      z.querySelectorAll("[data-ver]").forEach((b) => b.addEventListener("click", () => {
        const q = items.find((x) => String(x.id_qa) === b.dataset.ver);
        const campos = [
          { nombre: "puntaje_humano", etiqueta: "Puntaje del revisor (0–100)", tipo: "number", min: 0, max: 100, requerido: true, valor: q.puntaje_humano ?? q.puntaje },
          { nombre: "observacion", etiqueta: "Observación", tipo: "textarea", requerido: true, ancho: true, valor: q.observacion || "" },
        ];
        abrirModal({
          titulo: `Evaluación QA #${q.id_qa} · llamada #${q.id_llamada}`,
          contenido: `<p>${esc(q.resumen || "")}</p>
            <p class="texto-tenue">Proveedor ${esc(q.proveedor)} · modelo ${esc(q.modelo)} · prompt ${esc(q.version_prompt)} · confirmación correcta: ${q.confirmacion_correcta === null ? "no aplica" : q.confirmacion_correcta ? "sí" : "no"}</p>
            <h3>Hallazgos</h3>${(q.hallazgos || []).length ? `<ul>${q.hallazgos.map((h) => `<li><strong>${esc(h.tipo)}</strong>: ${esc(h.descripcion)}<br>
              <span class="mono">«${esc(h.evidencia)}»</span> ${h.evidencia_verificada ? chip("COMPLETADO", "Evidencia verificada") : chip("FALLIDO", "Evidencia no encontrada")}</li>`).join("")}</ul>` : '<p class="texto-tenue">Sin hallazgos.</p>'}
            ${ctx.tiene("qa.revisar") ? "<h3>Revisión humana</h3>" + formulario(campos, q) : ""}`,
          botones: [{ texto: "Cerrar" }, ...(ctx.tiene("qa.revisar") ? [{ texto: "Guardar revisión", clase: "btn-primario", accion: async (m) => {
            await post(`/api/qa/${q.id_qa}/revisar`, leerFormulario(m, campos)); toast("Revisión guardada.", "exito"); t.recargar();
          } }] : [])],
        });
      }));
    },
  });
}
