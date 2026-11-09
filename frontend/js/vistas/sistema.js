// Sistema: estado de dependencias, parámetros operativos, cola de trabajos y consumo de APIs.
import { get, put } from "../api.js";
import { icono } from "../iconos.js";
import { abrirModal, boton, chip, errorToast, esc, fecha, formulario, leerFormulario, tablaPaginada, tarjeta, toast } from "../ui.js";

export async function render(cont, ctx) {
  const [estado, parametros] = await Promise.all([get("/api/sistema/estado"), get("/api/sistema/parametros")]);
  const dep = (ok, si, no) => (ok ? chip("ACTIVO", si) : chip("BLOQUEADA", no));
  cont.innerHTML = `
    <div class="rejilla rejilla-2">
      ${tarjeta("Estado de dependencias", `<dl class="lista-def">
        <dt>Base de datos</dt><dd>${chip(estado.base_de_datos === "OK" ? "ACTIVO" : "FALLIDA", estado.base_de_datos)} <span class="texto-tenue">${esc(estado.motor_bd)}</span></dd>
        <dt>Modelo de lenguaje</dt><dd>${dep(estado.llm.credencial_configurada, "Credencial configurada", "Falta ANTHROPIC_API_KEY")}<br><small class="mono">${esc(estado.llm.modelo_agente)} · supervisor ${esc(estado.llm.modelo_supervisor)}</small></dd>
        <dt>Deepgram</dt><dd>${dep(estado.deepgram.credencial_configurada, "Credencial configurada", "Falta DEEPGRAM_API_KEY")}<br><small class="mono">STT ${esc(estado.deepgram.stt)} · TTS ${esc(estado.deepgram.tts)}</small></dd>
        <dt>Telefonía</dt><dd>${dep(estado.telefonia_habilitada, "Habilitada", "Deshabilitada (bloqueada)")}</dd>
        <dt>Grabaciones</dt><dd>${dep(estado.grabaciones_cifradas, "Cifradas (Fernet)", "No se guardan (sin clave)")}</dd>
        <dt>Pausa de emergencia</dt><dd>${estado.pausa_emergencia ? chip("ALTA", "Activa") : chip("BAJA", "Inactiva")}</dd>
        <dt>Trabajos pendientes</dt><dd>${estado.trabajos_pendientes}</dd><dt>Entorno</dt><dd>${esc(estado.entorno)}</dd></dl>
        <p class="texto-tenue">Las APIs de IA y Deepgram requieren Internet y credenciales propias aunque el sistema corra en localhost. La suscripción de chat no incluye saldo de API.</p>`)}
      ${tarjeta("Parámetros operativos", `<div class="tabla-envoltura"><table><thead><tr><th>Parámetro</th><th>Valor</th><th></th></tr></thead><tbody>
        ${parametros.map((p) => `<tr><td><strong class="mono">${esc(p.clave)}</strong><br><small class="texto-tenue">${esc(p.descripcion)}</small></td><td class="mono">${esc(p.valor)}</td>
          <td>${ctx.tiene("sistema.configurar") && p.clave !== "pausa_emergencia" ? boton("Cambiar", { chico: true, datos: `data-param="${esc(p.clave)}"` }) : ""}</td></tr>`).join("")}</tbody></table></div>`,
        { descripcion: "La pausa de emergencia se gestiona desde Control y Supervisión." })}
    </div>
    <div id="z-trabajos"></div><div id="z-consumo"></div>`;
  cont.querySelectorAll("[data-param]").forEach((b) => b.addEventListener("click", () => {
    const p = parametros.find((x) => x.clave === b.dataset.param);
    const c = [{ nombre: "valor", etiqueta: p.descripcion, requerido: true, ancho: true, valor: p.valor, maxlength: 50 }];
    abrirModal({ titulo: `Cambiar ${p.clave}`, contenido: formulario(c), botones: [{ texto: "Cancelar" }, { texto: "Guardar", clase: "btn-primario", accion: async (m) => {
      await put(`/api/sistema/parametros/${p.clave}`, leerFormulario(m, c)); toast("Parámetro actualizado (auditado).", "exito"); render(cont, ctx);
    } }] });
  }));
  tablaPaginada({
    contenedor: cont.querySelector("#z-trabajos"), titulo: "Cola durable de trabajos", porPagina: 10,
    descripcion: "Procesada por el worker (python -m app.worker). Sobrevive a reinicios.",
    filtros: [{ nombre: "estado", etiqueta: "Estado", tipo: "select", opciones: ["", "PENDIENTE", "EN_PROCESO", "COMPLETADO", "FALLIDO", "CANCELADO"].map((v) => ({ valor: v, texto: v || "Todos" })) }],
    cargar: (p) => get("/api/sistema/trabajos", p),
    columnas: [
      { titulo: "#", html: (t) => t.id }, { titulo: "Tipo", html: (t) => esc(t.tipo) }, { titulo: "Estado", html: (t) => chip(t.estado) },
      { titulo: "Intentos", clase: "num", html: (t) => t.intentos }, { titulo: "Resultado", html: (t) => esc(t.resultado || "") }, { titulo: "Actualizado", html: (t) => fecha(t.actualizado) },
    ],
  });
  try {
    const consumo = await get("/api/sistema/consumo", { dias: 7 });
    cont.querySelector("#z-consumo").innerHTML = tarjeta("Consumo de APIs (últimos 7 días, máx. 500)", `<div class="tabla-envoltura"><table><thead><tr><th>Fecha</th><th>Proveedor</th><th>Servicio</th><th>Modelo</th><th>Prompt</th><th class="num">Tokens</th><th class="num">Audio (s)</th><th class="num">US$ est.</th><th>Resultado</th><th class="num">Latencia</th></tr></thead><tbody>
      ${consumo.map((c) => `<tr><td>${fecha(c.fecha)}</td><td>${esc(c.proveedor)}</td><td>${esc(c.servicio)}</td><td class="mono">${esc(c.modelo)}</td><td class="mono">${esc(c.version_prompt || "")}</td>
        <td class="num">${c.tokens_entrada}/${c.tokens_salida}</td><td class="num">${esc(c.segundos_audio)}</td><td class="num">${esc(c.costo_estimado_usd)}</td>
        <td>${c.exito ? chip("COMPLETADO", "OK") : chip("FALLIDO", c.codigo_error || "Error")}</td><td class="num">${c.latencia_ms ?? "—"}</td></tr>`).join("") || '<tr><td colspan="10" class="texto-tenue">Sin consumo.</td></tr>'}</tbody></table></div>
      <p class="texto-tenue">${icono("alerta")} Estimación con precios de referencia configurables; no es la facturación real del proveedor ni se consulta su saldo.</p>`);
  } catch (e) { errorToast(e); }
}
