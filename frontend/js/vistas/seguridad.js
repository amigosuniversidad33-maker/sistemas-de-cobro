// Módulo Seguridad IA: políticas versionadas, reglas guardrail, alertas, supervisor IA de seguridad y matriz de riesgos.
import { get, post } from "../api.js";
import { icono } from "../iconos.js";
import { abrirModal, boton, chip, errorToast, esc, fecha, formulario, leerFormulario, tablaPaginada, tarjeta, toast } from "../ui.js";

export async function render(cont, ctx) {
  const g = ctx.tiene("seguridad.gestionar");
  const [politicas, riesgos, metricas] = await Promise.all([get("/api/politicas"), get("/api/seguridad/riesgos"), get("/api/seguridad/metricas")]);
  cont.innerHTML = `
    <div class="banner info">${icono("escudo")}<div>La seguridad no depende solo del prompt ni del supervisor IA: el backend valida cada herramienta, los guardrails deterministas filtran
      la respuesta antes de convertirla en voz y, tras más de N bloqueos, la conversación se cierra. El supervisor IA de seguridad solo analiza métricas sanitizadas y recomienda;
      las acciones automáticas (como la pausa de emergencia ante fallas masivas del proveedor) las ejecutan reglas deterministas.</div></div>
    <div id="z-alertas"></div>
    <div class="rejilla rejilla-2">
      ${tarjeta("Métricas sanitizadas (24 h)", `<dl class="lista-def">${Object.entries(metricas).map(([k, v]) => `<dt>${esc(k.replaceAll("_", " "))}</dt><dd>${esc(String(v))}</dd>`).join("")}</dl>`,
        { acciones: g ? boton("Ejecutar reglas", { ico: "check", chico: true, datos: "data-reglas" }) + boton("Supervisor IA", { ico: "bot", chico: true, clase: "btn-primario", datos: "data-supervisor" }) : "" })}
      ${tarjeta("Políticas de comportamiento", politicas.map((p) => `
        <h3>${esc(p.nombre)} v${p.version} ${chip(p.activa ? "ACTIVA" : "INACTIVO")}</h3>
        <dl class="lista-def"><dt>Plazo máximo de promesa</dt><dd>${p.plazo_max_dias} días</dd><dt>Monto mínimo</dt><dd>${esc(p.monto_min_pct)} % del saldo</dd>
          <dt>Bloqueos antes de cerrar</dt><dd>${p.max_bloqueos}</dd><dt>Intentos de verificación</dt><dd>${p.max_intentos_identidad}</dd>
          <dt>Contingencia</dt><dd>«${esc(p.mensaje_contingencia)}»</dd><dt>Temas prohibidos</dt><dd>${esc(p.temas_prohibidos || "—")}</dd></dl>
        <div class="tabla-envoltura"><table><thead><tr><th>Tipo</th><th>Patrón</th><th>Acción</th><th>Descripción</th><th></th></tr></thead><tbody>
        ${p.reglas.map((r) => `<tr><td>${esc(r.tipo)}</td><td class="mono">${esc(r.patron)}</td><td>${chip(r.accion === "BLOQUEAR" ? "ALTA" : "MEDIA", r.accion)}</td><td>${esc(r.descripcion || "")}</td>
          <td>${g ? boton(r.activa ? "Desactivar" : "Activar", { chico: true, datos: `data-regla="${r.id_regla}"` }) : chip(r.activa ? "ACTIVA" : "INACTIVO")}</td></tr>`).join("")}</tbody></table></div>
        ${g ? `<div class="acciones">${boton("Agregar regla", { chico: true, ico: "mas", datos: `data-nueva-regla="${p.id_politica}"` })} ${boton("Nueva versión", { chico: true, datos: `data-version="${p.id_politica}"` })}</div>` : ""}`).join("<hr>"),
        { descripcion: "Además existen reglas fijas: no exponer documentos/tarjetas, no revelar la deuda sin verificar identidad, sin emojis, longitud apta para voz." })}
    </div>
    ${tarjeta("Matriz de riesgos (documento de fase final, NR = P × I)", `<div class="tabla-envoltura"><table><thead><tr><th>ID</th><th>Riesgo</th><th class="num">P</th><th class="num">I</th><th class="num">NR</th><th>Nivel</th><th>Disparador</th><th>Estrategia</th><th>Control implementado en el piloto</th></tr></thead><tbody>
      ${riesgos.map((r) => `<tr><td><strong>${esc(r.codigo)}</strong></td><td>${esc(r.nombre)}<br><small class="texto-tenue">${esc(r.categoria)}</small></td><td class="num">${r.probabilidad}</td><td class="num">${r.impacto}</td>
        <td class="num"><strong>${r.nivel_riesgo}</strong></td><td>${chip(r.nivel)}</td><td>${esc(r.disparador)}</td><td>${esc(r.estrategia)}</td><td>${esc(r.control_implementado)}</td></tr>`).join("")}</tbody></table></div>`)}`;

  const alertas = tablaPaginada({
    contenedor: cont.querySelector("#z-alertas"),
    titulo: "Alertas",
    filtros: [
      { nombre: "estado", etiqueta: "Estado", tipo: "select", valor: "ABIERTA", opciones: ["ABIERTA", "RECONOCIDA", "CERRADA", ""].map((v) => ({ valor: v, texto: v || "Todas" })) },
      { nombre: "severidad", etiqueta: "Severidad", tipo: "select", opciones: ["", "CRITICA", "ALTA", "MEDIA", "BAJA"].map((v) => ({ valor: v, texto: v || "Todas" })) },
    ],
    cargar: (p) => get("/api/alertas", p),
    columnas: [
      { titulo: "Fecha", html: (a) => fecha(a.fecha) }, { titulo: "Severidad", html: (a) => chip(a.severidad) }, { titulo: "Tipo", html: (a) => esc(a.tipo) },
      { titulo: "Origen", html: (a) => esc(a.origen) }, { titulo: "Mensaje", html: (a) => esc(a.mensaje) + (a.recomendacion ? `<br><small class="texto-tenue">Recomendación: ${esc(a.recomendacion)}</small>` : "") },
      { titulo: "Estado", html: (a) => chip(a.estado) },
      { titulo: "", html: (a) => (a.estado !== "CERRADA" ? `<span class="acciones">${a.estado === "ABIERTA" ? boton("Reconocer", { chico: true, datos: `data-alerta="${a.id}" data-estado="RECONOCIDA"` }) : ""}${boton("Cerrar", { chico: true, datos: `data-alerta="${a.id}" data-estado="CERRADA"` })}</span>` : "") },
    ],
    alRenderizar: (z) => z.querySelectorAll("[data-alerta]").forEach((b) => b.addEventListener("click", async () => {
      try { await post(`/api/alertas/${b.dataset.alerta}/estado`, { estado: b.dataset.estado }); alertas.recargar(); } catch (e) { errorToast(e); }
    })),
  });

  cont.querySelector("[data-reglas]")?.addEventListener("click", async () => {
    try { const r = await post("/api/seguridad/reglas/ejecutar"); toast(r.alertas_generadas.length ? `Alertas: ${r.alertas_generadas.join(", ")}` : "Sin condiciones anómalas.", "exito"); alertas.recargar(); } catch (e) { errorToast(e); }
  });
  cont.querySelector("[data-supervisor]")?.addEventListener("click", async (ev) => {
    ev.target.disabled = true;
    try { const r = await post("/api/seguridad/supervisor-ia"); toast(`Supervisor IA: ${r.alertas.length} alerta(s) y recomendaciones.`, "exito"); alertas.recargar(); } catch (e) { errorToast(e); } finally { ev.target.disabled = false; }
  });
  cont.querySelectorAll("[data-regla]").forEach((b) => b.addEventListener("click", async () => { try { await post(`/api/reglas/${b.dataset.regla}/alternar`); render(cont, ctx); } catch (e) { errorToast(e); } }));
  cont.querySelectorAll("[data-nueva-regla]").forEach((b) => b.addEventListener("click", () => {
    const c = [
      { nombre: "tipo", etiqueta: "Aplica a", tipo: "select", opciones: [{ valor: "SALIDA", texto: "Respuesta del agente (salida)" }, { valor: "ENTRADA", texto: "Mensaje del interlocutor (entrada)" }] },
      { nombre: "accion", etiqueta: "Acción", tipo: "select", opciones: [{ valor: "BLOQUEAR", texto: "Bloquear" }, { valor: "ALERTAR", texto: "Alertar" }] },
      { nombre: "patron", etiqueta: "Expresión regular", requerido: true, ancho: true, maxlength: 300 },
      { nombre: "descripcion", etiqueta: "Descripción", ancho: true, maxlength: 255 },
    ];
    abrirModal({ titulo: "Nueva regla guardrail", contenido: formulario(c), botones: [{ texto: "Cancelar" }, { texto: "Guardar", clase: "btn-primario", accion: async (m) => { await post(`/api/politicas/${b.dataset.nuevaRegla}/reglas`, leerFormulario(m, c)); render(cont, ctx); } }] });
  }));
  cont.querySelectorAll("[data-version]").forEach((b) => b.addEventListener("click", () => {
    const p = politicas.find((x) => String(x.id_politica) === b.dataset.version);
    const c = [
      { nombre: "nombre", etiqueta: "Nombre", requerido: true, maxlength: 100 },
      { nombre: "plazo_max_dias", etiqueta: "Plazo máximo (días)", tipo: "number", min: 1, max: 60 },
      { nombre: "monto_min_pct", etiqueta: "Monto mínimo (% del saldo)", tipo: "number", min: 0, max: 100, paso: "0.01" },
      { nombre: "max_bloqueos", etiqueta: "Bloqueos antes de cerrar", tipo: "number", min: 1, max: 10 },
      { nombre: "max_intentos_identidad", etiqueta: "Intentos de verificación", tipo: "number", min: 1, max: 5 },
      { nombre: "mensaje_contingencia", etiqueta: "Mensaje de contingencia", tipo: "textarea", requerido: true, ancho: true, maxlength: 500 },
      { nombre: "temas_prohibidos", etiqueta: "Temas prohibidos", tipo: "textarea", ancho: true },
    ];
    abrirModal({ titulo: "Nueva versión de política", contenido: formulario(c, p) + '<p class="texto-tenue">Se copian las reglas de la versión anterior. Asigne la nueva versión a los agentes para usarla.</p>',
      botones: [{ texto: "Cancelar" }, { texto: "Crear versión", clase: "btn-primario", accion: async (m) => { await post("/api/politicas", leerFormulario(m, c)); toast("Política versionada.", "exito"); render(cont, ctx); } }] });
  }));
}
