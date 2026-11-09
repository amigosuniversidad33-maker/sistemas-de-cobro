// Módulo Llamadas: monitoreo, historial con filtros, transcripciones y grabaciones (acceso controlado).
import { api, descargar, get, post } from "../api.js";
import { icono } from "../iconos.js";
import { abrirModal, boton, chip, dinero, errorToast, esc, fecha, modo, num, opcionesDe, tablaPaginada, toast } from "../ui.js";

export async function render(cont, ctx) {
  const campanas = (await get("/api/campanas", { por_pagina: 200 })).items;
  const t = tablaPaginada({
    contenedor: cont,
    titulo: "Registro de llamadas e interacciones",
    descripcion: "Estado técnico, resultado de contacto y resultado de cobranza se muestran por separado.",
    acciones: ctx.tiene("clientes.exportar") ? boton("Exportar CSV", { ico: "bajar", datos: "data-exportar" }) : "",
    filtros: [
      { nombre: "id_campana", etiqueta: "Campaña", tipo: "select", opciones: opcionesDe(campanas, "id_campana", "nombre", "Todas") },
      { nombre: "tramo", etiqueta: "Módulo", tipo: "select", opciones: [{ valor: "", texto: "Todos" }, { valor: "MORA_TEMPRANA", texto: "Mora Temprana" }, { valor: "MORA_TARDIA", texto: "Mora Tardía" }] },
      { nombre: "canal", etiqueta: "Canal", tipo: "select", opciones: [{ valor: "", texto: "Todos" }, { valor: "TELEFONIA", texto: "Telefonía real" }, { valor: "VOZ_NAVEGADOR", texto: "Voz de prueba" }, { valor: "TEXTO", texto: "Texto de prueba" }] },
      { nombre: "estado", etiqueta: "Estado técnico", tipo: "select", opciones: ["", "EN_CURSO", "FINALIZADA", "FALLIDA", "CANCELADA"].map((v) => ({ valor: v, texto: v ? v.replace("_", " ") : "Todos" })) },
      { nombre: "resultado", etiqueta: "Contacto", tipo: "select", opciones: ["", "CONTESTADA", "RECHAZADA", "SIN_CONTESTAR"].map((v) => ({ valor: v, texto: v ? v.replace("_", " ") : "Todos" })) },
      { nombre: "desde", etiqueta: "Desde", tipo: "date" },
      { nombre: "hasta", etiqueta: "Hasta", tipo: "date" },
    ],
    cargar: (p) => get("/api/llamadas", p),
    columnas: [
      { titulo: "#", html: (l) => `<button class="btn-icono" data-ver="${l.id_llamada}" aria-label="Ver detalle">${icono("ojo")}</button> ${l.id_llamada}` },
      { titulo: "Inicio", html: (l) => fecha(l.inicio) },
      { titulo: "Canal", html: (l) => modo(l.canal, l.modo) },
      { titulo: "Cliente", html: (l) => esc(l.cliente || "—") },
      { titulo: "Campaña", html: (l) => esc(l.campana || "Prueba") },
      { titulo: "Agente", html: (l) => esc(l.agente || "—") },
      { titulo: "Técnico", html: (l) => chip(l.estado_tecnico) },
      { titulo: "Contacto", html: (l) => chip(l.resultado_contacto) },
      { titulo: "Cobranza", html: (l) => chip(l.resultado_cobranza) },
      { titulo: "Duración", clase: "num", html: (l) => (l.duracion_seg != null ? `${l.duracion_seg} s` : "—") },
    ],
    alRenderizar: (zona) => zona.querySelectorAll("[data-ver]").forEach((b) => b.addEventListener("click", () => detalle(b.dataset.ver, ctx))),
  });
  cont.querySelector("[data-exportar]")?.addEventListener("click", () => {
    const f = Object.fromEntries(new FormData(cont.querySelector("[data-filtros]")));
    descargar("/api/llamadas/exportar.csv", { id_campana: f.id_campana, desde: f.desde, hasta: f.hasta }).catch(errorToast);
  });
  return t;
}

export async function detalle(id, ctx) {
  let d;
  try { d = await get(`/api/llamadas/${id}`); } catch (e) { return errorToast(e); }
  const turnos = d.turnos.map((t) => `<div class="burbuja ${t.rol.toLowerCase()}"><small>${esc(t.rol)} · ${fecha(t.fecha)}${t.confianza_stt ? ` · STT ${Math.round(t.confianza_stt * 100)}%` : ""}</small>${esc(t.texto)}</div>`).join("");
  abrirModal({
    titulo: `Llamada #${d.id_llamada}`,
    contenido: `
      <div class="acciones">${modo(d.canal, d.modo)} ${chip(d.estado_tecnico)} ${chip(d.resultado_contacto)} ${chip(d.resultado_cobranza)}</div><br>
      <dl class="lista-def">
        <dt>Cliente</dt><dd>${esc(d.cliente || "—")}</dd><dt>Campaña</dt><dd>${esc(d.campana || "Prueba sin campaña")}</dd>
        <dt>Agente</dt><dd>${esc(d.agente || "—")} · guion v${esc(d.version_guion ?? "—")} · política v${esc(d.version_politica ?? "—")}</dd>
        <dt>Identidad verificada</dt><dd>${d.identidad_verificada ? "Sí" : "No"}</dd><dt>Bloqueos de guardrails</dt><dd>${num(d.bloqueos_guardrail)}</dd>
        <dt>Destino</dt><dd>${esc(d.destino_enmascarado || "—")}</dd><dt>Motivo de fallo</dt><dd>${esc(d.motivo_fallo || "—")}</dd>
        <dt>Costo estimado</dt><dd>US$ ${esc(d.costo_estimado_usd)}</dd>
      </dl>
      ${d.promesa ? `<br><div class="banner info">${icono("promesa")}<div>Promesa #${d.promesa.id_promesa}: ${dinero(d.promesa.monto, d.promesa.moneda)} para el ${esc(d.promesa.fecha_compromiso)} · ${chip(d.promesa.estado)}<br><small>Confirmación: «${esc(d.promesa.frase_confirmacion || "")}»</small></div></div>` : ""}
      <h3>Transcripción (datos sensibles enmascarados)</h3><div class="chat">${turnos || '<p class="texto-tenue">Sin turnos.</p>'}</div>
      ${d.grabaciones.length ? `<h3>Grabaciones cifradas</h3>${d.grabaciones.map((g) => `<p>${boton(`Escuchar grabación ${g.id_grabacion}`, { ico: "volumen", chico: true, datos: `data-audio="${g.id_grabacion}"` })} <span class="texto-tenue">${fecha(g.fecha)}</span></p>`).join("")}<div data-reproductor></div>` : ""}
      ${d.evaluaciones_qa.length ? `<h3>Evaluación QA</h3>${d.evaluaciones_qa.map((q) => `<p>Puntaje <strong>${esc(q.puntaje)}</strong> · ${chip(q.incertidumbre, "Incertidumbre " + q.incertidumbre)} · ${chip(q.estado_revision)}<br>${esc(q.resumen || "")}</p>`).join("")}` : ""}
      <h3>Eventos</h3><ul>${d.eventos.map((e) => `<li class="mono">${fecha(e.fecha_evento)} · ${esc(e.tipo)}</li>`).join("") || '<li class="texto-tenue">Sin eventos telefónicos.</li>'}</ul>`,
    botones: [
      ...(ctx.tiene("qa.revisar") && d.estado_tecnico !== "EN_CURSO" ? [{ texto: "Evaluar con supervisor IA", clase: "btn-primario", accion: async () => {
        const r = await post(`/api/qa/evaluar/${d.id_llamada}`);
        toast(`Evaluación registrada: puntaje ${r.puntaje}`, "exito");
      } }] : []),
      { texto: "Cerrar" },
    ],
    alAbrir: (c) => c.querySelectorAll("[data-audio]").forEach((b) => b.addEventListener("click", async () => {
      try {
        const r = await api(`/api/grabaciones/${b.dataset.audio}/audio`, { crudo: true });
        const url = URL.createObjectURL(await r.blob());
        const zona = c.querySelector("[data-reproductor]");
        zona.innerHTML = "";
        const audio = document.createElement("audio");
        audio.controls = true;
        audio.src = url;
        zona.appendChild(audio);
        audio.play();
      } catch (e) { errorToast(e); }
    })),
  });
}
