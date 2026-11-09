// Módulo Campañas: creación, parametrización, clasificación por tramo de mora, estados y encolado.
import { del, get, post, put } from "../api.js";
import { icono } from "../iconos.js";
import { abrirModal, boton, chip, confirmar, dinero, errorToast, esc, formulario, hoyLocal, leerFormulario, num, opcionesDe, tablaPaginada, tarjeta, toast } from "../ui.js";

const MOTIVOS = {
  PAUSA_EMERGENCIA: "Pausa de emergencia", CAMPANA_NO_ACTIVA: "Campaña no activa", FUERA_DE_VIGENCIA: "Fuera de vigencia", DEUDA_NO_ACTIVA: "Deuda no activa",
  TELEFONO_INVALIDO: "Teléfono inválido", EXCLUIDO: "Excluido (No Contactables)", FUERA_DE_HORARIO: "Fuera de horario", INTENTOS_AGOTADOS: "Intentos agotados",
  INTENTOS_DIARIOS_AGOTADOS: "Intentos diarios agotados", TIEMPO_MINIMO_ENTRE_INTENTOS: "Tiempo mínimo entre intentos", LLAMADA_SIMULTANEA: "Llamada simultánea",
  PROMESA_VIGENTE: "Promesa vigente", PRESUPUESTO_AGOTADO: "Presupuesto agotado", YA_EN_COLA: "Ya en cola", ENCOLADOS: "Encolados",
};

export async function render(cont, ctx) {
  const tramos = await get("/api/tramos");
  cont.innerHTML = `<div id="z-lista"></div><div id="z-detalle"></div>`;
  const tabla = tablaPaginada({
    contenedor: cont.querySelector("#z-lista"),
    titulo: "Campañas de cobranza",
    descripcion: "Módulos secuenciales: Recordatorio / Mora Temprana (1–30) y Mora Tardía (31–60).",
    acciones: ctx.tiene("campanas.gestionar") ? boton("Nueva campaña", { ico: "mas", clase: "btn-primario", datos: "data-nueva" }) : "",
    filtros: [{ nombre: "estado", etiqueta: "Estado", tipo: "select", opciones: ["", "BORRADOR", "ACTIVA", "PAUSADA", "FINALIZADA"].map((v) => ({ valor: v, texto: v || "Todos" })) }],
    cargar: (p) => get("/api/campanas", p),
    columnas: [
      { titulo: "Campaña", html: (c) => `<button class="btn-icono" data-abrir="${c.id_campana}">${icono("ojo")}</button> <strong>${esc(c.nombre)}</strong>` },
      { titulo: "Módulo", html: (c) => `${esc(c.tramo.nombre)}<br><small class="texto-tenue">${c.tramo.dias_min}–${c.tramo.dias_max} días</small>` },
      { titulo: "Estado", html: (c) => chip(c.estado) },
      { titulo: "Vigencia", html: (c) => `${esc(c.fecha_inicio || "—")} → ${esc(c.fecha_fin || "—")}` },
      { titulo: "Horario", html: (c) => `${esc(c.hora_inicio)}–${esc(c.hora_fin)}` },
      { titulo: "Agentes", html: (c) => esc(c.agentes.map((a) => a.nombre).join(", ") || "—") },
      { titulo: "Clientes", clase: "num", html: (c) => num(c.total_clientes) },
    ],
    alRenderizar: (z) => z.querySelectorAll("[data-abrir]").forEach((b) => b.addEventListener("click", () => detalle(cont, ctx, b.dataset.abrir, tabla))),
  });
  cont.querySelector("[data-nueva]")?.addEventListener("click", () => editor(cont, ctx, null, tramos, tabla));
}

const campos = (tramos) => [
  { nombre: "nombre", etiqueta: "Nombre", requerido: true, maxlength: 120, ancho: true },
  { nombre: "id_tramo", etiqueta: "Módulo / tramo de mora", tipo: "select", numerico: true, opciones: opcionesDe(tramos, "id_tramo", (t) => `${t.nombre} (${t.dias_min}–${t.dias_max} días)`) },
  { nombre: "prioridad", etiqueta: "Prioridad (1–10)", tipo: "number", min: 1, max: 10, valor: 1 },
  { nombre: "fecha_inicio", etiqueta: "Fecha de inicio", tipo: "date" },
  { nombre: "fecha_fin", etiqueta: "Fecha de fin", tipo: "date" },
  { nombre: "hora_inicio", etiqueta: "Hora inicio (America/Guatemala)", tipo: "time", valor: "08:00" },
  { nombre: "hora_fin", etiqueta: "Hora fin (exclusiva)", tipo: "time", valor: "20:00", ayuda: "Ventana inicial del proyecto; configurable, no es una afirmación legal." },
  { nombre: "max_intentos_dia", etiqueta: "Máx. intentos por día", tipo: "number", min: 1, max: 10, valor: 2 },
  { nombre: "max_intentos_total", etiqueta: "Máx. intentos totales", tipo: "number", min: 1, max: 50, valor: 6 },
  { nombre: "minutos_entre_intentos", etiqueta: "Minutos entre intentos", tipo: "number", min: 5, max: 10080, valor: 120 },
  { nombre: "max_concurrencia", etiqueta: "Concurrencia máxima (piloto)", tipo: "number", min: 1, max: 5, valor: 1 },
  { nombre: "mensaje_base", etiqueta: "Mensaje base", tipo: "textarea", ancho: true, maxlength: 2000 },
];

function editor(cont, ctx, c, tramos, tabla) {
  const cs = campos(tramos);
  abrirModal({
    titulo: c ? `Modificar ${c.nombre}` : "Nueva campaña",
    contenido: formulario(cs, c || { fecha_inicio: hoyLocal() }),
    botones: [{ texto: "Cancelar" }, { texto: "Guardar", clase: "btn-primario", accion: async (m) => {
      const d = leerFormulario(m, cs);
      const r = c ? await put(`/api/campanas/${c.id_campana}`, d) : await post("/api/campanas", d);
      toast("Campaña guardada en estado " + r.estado + ".", "exito");
      tabla.recargar();
      detalle(cont, ctx, r.id_campana, tabla);
    } }],
  });
}

async function detalle(cont, ctx, id, tabla) {
  const zona = cont.querySelector("#z-detalle");
  zona.innerHTML = '<div class="estado-carga cargando">Cargando campaña</div>';
  let c, agentes, tramos;
  try { [c, agentes, tramos] = await Promise.all([get(`/api/campanas/${id}`), get("/api/agentes"), get("/api/tramos")]); } catch (e) { zona.innerHTML = `<div class="estado-error">${esc(e.message)}</div>`; return; }
  const gestionar = ctx.tiene("campanas.gestionar"), operar = ctx.tiene("campanas.operar");
  const est = Object.entries(c.clientes_por_estado);
  const acciones = [
    gestionar && ["BORRADOR", "PAUSADA"].includes(c.estado) ? boton("Editar", { ico: "editar", datos: "data-editar" }) : "",
    gestionar && c.estado !== "FINALIZADA" ? boton("Clasificar clientes", { ico: "recargar", datos: "data-clasificar" }) : "",
    operar && ["BORRADOR", "PAUSADA"].includes(c.estado) ? boton("Activar", { ico: "play", clase: "btn-exito", datos: 'data-estado="ACTIVA"' }) : "",
    operar && c.estado === "ACTIVA" ? boton("Encolar marcación", { ico: "telefono", clase: "btn-primario", datos: "data-encolar" }) : "",
    operar && c.estado === "ACTIVA" ? boton("Pausar", { ico: "pausa", datos: 'data-estado="PAUSADA"' }) : "",
    operar && c.estado !== "FINALIZADA" ? boton("Finalizar", { datos: 'data-estado="FINALIZADA"' }) : "",
  ].join("");
  zona.innerHTML = `
    ${tarjeta(c.nombre, `
      ${c.faltantes_para_activar.length ? `<div class="banner alerta">${icono("alerta")}<div><strong>No se puede activar todavía:</strong><ul>${c.faltantes_para_activar.map((f) => `<li>${esc(f)}</li>`).join("")}</ul></div></div><br>` : ""}
      <div class="rejilla rejilla-3">
        <dl class="lista-def"><dt>Estado</dt><dd>${chip(c.estado)}</dd><dt>Módulo</dt><dd>${esc(c.tramo.nombre)}</dd><dt>Días de mora</dt><dd>${c.tramo.dias_min}–${c.tramo.dias_max}</dd><dt>Prioridad</dt><dd>${c.prioridad}</dd></dl>
        <dl class="lista-def"><dt>Vigencia</dt><dd>${esc(c.fecha_inicio || "—")} → ${esc(c.fecha_fin || "—")}</dd><dt>Horario</dt><dd>${esc(c.hora_inicio)}–${esc(c.hora_fin)}</dd>
          <dt>Intentos</dt><dd>${c.max_intentos_dia}/día · ${c.max_intentos_total} total</dd><dt>Entre intentos</dt><dd>${c.minutos_entre_intentos} min</dd></dl>
        <dl class="lista-def"><dt>Clientes</dt><dd>${num(c.total_clientes)}</dd>${est.map(([e, n]) => `<dt>${chip(e)}</dt><dd>${num(n)}</dd>`).join("")}</dl>
      </div>
      <h3>Agentes IA asignados</h3>
      <div class="acciones">${c.agentes.map((a) => `<span class="chip">${esc(a.nombre)} ${gestionar && c.estado !== "ACTIVA" ? `<button class="btn-icono" data-quitar="${a.id_agente}" aria-label="Quitar">${icono("cerrar")}</button>` : ""}</span>`).join("") || '<span class="texto-tenue">Ninguno</span>'}
        ${(() => {
          const libres = agentes.filter((a) => a.tramo === c.tramo.codigo && !c.agentes.some((x) => x.id_agente === a.id_agente));
          if (!gestionar) return "";
          if (!libres.length) return '<span class="texto-tenue">No hay otros agentes con guion de este tramo.</span>';
          return `<select id="sel-agente" aria-label="Agente a asignar">${libres.map((a) => `<option value="${a.id_agente}">${esc(a.nombre)}</option>`).join("")}</select>${boton("Asignar agente", { chico: true, datos: "data-asignar" })}`;
        })()}</div>
      <p class="texto-tenue">${esc(c.mensaje_base || "")}</p>`, { acciones })}
    <div id="z-cc"></div>`;
  const recargar = () => { tabla.recargar(); detalle(cont, ctx, id, tabla); };
  zona.querySelector("[data-editar]")?.addEventListener("click", () => editor(cont, ctx, c, tramos, tabla));
  zona.querySelector("[data-clasificar]")?.addEventListener("click", async () => {
    try {
      const r = await post(`/api/campanas/${id}/clasificar`);
      toast(`Asignados: ${r.asignados} · excluidos: ${r.excluidos} · ya asignados: ${r.ya_asignados} · fuera de tramos (sin regla): ${r.gestion_especial_sin_regla}`, "exito");
      recargar();
    } catch (e) { errorToast(e); }
  });
  zona.querySelectorAll("[data-estado]").forEach((b) => b.addEventListener("click", async () => {
    const nuevo = b.dataset.estado;
    if (!(await confirmar("Cambiar estado", `¿Cambiar la campaña a ${nuevo}?${nuevo !== "ACTIVA" ? " Los trabajos de marcación pendientes se cancelarán." : ""}`, { peligro: nuevo === "FINALIZADA" }))) return;
    try { const r = await post(`/api/campanas/${id}/estado`, { estado: nuevo }); toast(`Estado: ${r.nuevo}. Trabajos cancelados: ${r.trabajos_cancelados}`, "exito"); recargar(); } catch (e) { errorToast(e); }
  }));
  zona.querySelector("[data-encolar]")?.addEventListener("click", async () => {
    if (!(await confirmar("Encolar marcación", "Se verificarán exclusiones, horario, intentos, presupuesto y demás reglas antes de encolar. Las reglas se vuelven a verificar justo antes de marcar."))) return;
    try {
      const r = await post(`/api/campanas/${id}/encolar`);
      abrirModal({ titulo: "Resultado del encolado", contenido: `<dl class="lista-def">${Object.entries(r).map(([k, v]) => `<dt>${esc(MOTIVOS[k] || k)}</dt><dd>${num(v)}</dd>`).join("") || "<dt>Sin clientes pendientes</dt><dd>0</dd>"}</dl>
        <p class="texto-tenue">El proceso worker origina las llamadas solo si la telefonía está habilitada y configurada; de lo contrario quedan registradas como bloqueadas.</p>`, botones: [{ texto: "Cerrar" }] });
      recargar();
    } catch (e) { errorToast(e); }
  });
  zona.querySelector("[data-asignar]")?.addEventListener("click", async () => {
    const v = zona.querySelector("#sel-agente").value;
    if (!v) return toast("No hay agentes disponibles para este tramo.", "error");
    try { await post(`/api/campanas/${id}/agentes`, { id_agente: Number(v) }); recargar(); } catch (e) { errorToast(e); }
  });
  zona.querySelectorAll("[data-quitar]").forEach((b) => b.addEventListener("click", async () => { try { await del(`/api/campanas/${id}/agentes/${b.dataset.quitar}`); recargar(); } catch (e) { errorToast(e); } }));
  tablaPaginada({
    contenedor: zona.querySelector("#z-cc"),
    titulo: "Clientes asignados",
    filtros: [{ nombre: "estado", etiqueta: "Estado de gestión", tipo: "select", opciones: ["", "PENDIENTE", "EN_COLA", "EN_LLAMADA", "CONTACTADO", "PROMESA", "EXCLUIDO", "AGOTADO", "CERRADO"].map((v) => ({ valor: v, texto: v || "Todos" })) }],
    cargar: (p) => get(`/api/campanas/${id}/clientes`, p),
    columnas: [
      { titulo: "Cliente", html: (x) => esc(x.cliente) },
      { titulo: "Teléfono", html: (x) => `<span class="mono">${esc(x.telefono)}</span>` },
      { titulo: "Saldo", clase: "num", html: (x) => dinero(x.saldo, x.moneda) },
      { titulo: "Días mora", clase: "num", html: (x) => num(x.dias_mora) },
      { titulo: "Intentos", clase: "num", html: (x) => num(x.intentos) },
      { titulo: "Gestión", html: (x) => chip(x.estado_gestion) },
    ],
  });
  zona.scrollIntoView({ behavior: "smooth" });
}
