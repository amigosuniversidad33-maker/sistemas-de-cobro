// Módulo Plantas FreeSWITCH: servidores, verificación ESL y dimensionamiento (Ley de Little, sección 6 del documento).
import { get, post, put } from "../api.js";
import { icono } from "../iconos.js";
import { abrirModal, boton, chip, errorToast, esc, fecha, formulario, leerFormulario, num, tarjeta, toast } from "../ui.js";

export async function render(cont, ctx) {
  const [estado, plantas] = await Promise.all([get("/api/telefonia/estado"), get("/api/telefonia/plantas")]);
  const gestionar = ctx.tiene("telefonia.gestionar");
  cont.innerHTML = `
    ${bannerEstado(estado)}
    ${tarjeta("Plantas FreeSWITCH", `<div class="tabla-envoltura"><table><thead><tr><th>Planta</th><th>Dirección ESL</th><th>Capacidad</th><th>Canales ocupados</th><th>Estado</th><th>Última verificación</th><th></th></tr></thead><tbody>
      ${plantas.map((p) => `<tr><td><strong>${esc(p.nombre)}</strong> ${p.activa ? "" : chip("INACTIVO")}</td><td class="mono">${esc(p.ip)}:${p.puerto_esl}</td><td class="num">${num(p.capacidad_canales)}</td>
        <td class="num">${num(p.canales_ocupados)} / ${num(p.canales_total)}</td><td>${chip(p.estado)}</td><td>${fecha(p.ultima_verificacion)}</td>
        <td class="acciones">${gestionar ? boton("Verificar ESL", { chico: true, datos: `data-verificar="${p.id_planta}"` }) + boton("Editar", { chico: true, datos: `data-editar="${p.id_planta}"` }) : ""}</td></tr>`).join("") || '<tr><td colspan="7" class="texto-tenue">Sin plantas.</td></tr>'}</tbody></table></div>
      <p class="texto-tenue">El acceso administrativo (Event Socket) solo se permite hacia localhost o redes privadas. Las credenciales SIP y la contraseña ESL viven en la configuración de FreeSWITCH y en .env, nunca en la base de datos ni en el navegador.</p>`,
      { descripcion: "Control de llamada por Event Socket; el audio se intercambia por archivos compartidos (puente de medios).", acciones: gestionar ? boton("Nueva planta", { ico: "mas", clase: "btn-primario", datos: "data-nueva" }) : "" })}
    ${tarjeta("Dimensionamiento de canales (Ley de Little: C = R × T)", `
      <form id="f-little" class="form-rejilla">
        ${[["llamadas_dia", "Llamadas por día", 65000], ["horas", "Horas de operación", 12], ["pct_contestadas", "% contestadas", 50], ["pct_rechazadas", "% rechazadas", 20],
          ["t_contestada_seg", "T contestada (s)", 90], ["t_rechazada_seg", "T rechazada (s)", 20], ["t_sin_contestar_seg", "T sin contestar (s)", 30], ["margen_pct", "Margen de seguridad (%)", 20]]
          .map(([n, e, v]) => `<div class="campo"><label for="l-${n}">${e}</label><input id="l-${n}" name="${n}" type="number" step="any" value="${v}"></div>`).join("")}
        <div class="ancho acciones"><button class="btn btn-secundario" type="submit">${icono("recargar")}Calcular</button>
          <button class="btn btn-secundario" type="button" data-escenario="min">Escenario mínimo</button><button class="btn btn-secundario" type="button" data-escenario="max">Escenario máximo</button></div>
      </form><div id="r-little"></div>`, { descripcion: "Estimación de diseño para la meta futura de 65,000 llamadas/día. No reemplaza los límites efectivos de concurrencia del piloto." })}`;

  const calcular = async () => {
    try {
      const r = await get("/api/telefonia/dimensionamiento", Object.fromEntries(new FormData(cont.querySelector("#f-little"))));
      cont.querySelector("#r-little").innerHTML = `<br><div class="kpis">
        <div class="kpi"><div class="kpi-etq">Ritmo R</div><div class="kpi-valor">${esc(r.R_llamadas_por_minuto)}</div><div class="kpi-sub">llamadas/min (${esc(r.R_llamadas_por_segundo)}/s)</div></div>
        <div class="kpi"><div class="kpi-etq">Ocupación T</div><div class="kpi-valor">${esc(r.T_segundos)} s</div><div class="kpi-sub">${esc(r.T_minutos)} min ponderados</div></div>
        <div class="kpi violeta"><div class="kpi-etq">Canales teóricos C</div><div class="kpi-valor">${esc(r.C_canales_teoricos)}</div></div>
        <div class="kpi verde"><div class="kpi-etq">Canales recomendados</div><div class="kpi-valor">${esc(r.C_canales_recomendados)}</div><div class="kpi-sub">con margen</div></div>
        <div class="kpi gris"><div class="kpi-etq">Distribución</div><div class="kpi-sub">LC ${num(r.distribucion.contestadas)} · LR ${num(r.distribucion.rechazadas)} · LNC ${num(r.distribucion.sin_contestar)}</div></div>
      </div><p class="texto-tenue">${esc(r.nota)}</p>`;
    } catch (e) { errorToast(e); }
  };
  cont.querySelector("#f-little").addEventListener("submit", (e) => { e.preventDefault(); calcular(); });
  cont.querySelectorAll("[data-escenario]").forEach((b) => b.addEventListener("click", () => {
    const v = b.dataset.escenario === "min" ? { t_contestada_seg: 45, t_rechazada_seg: 10, t_sin_contestar_seg: 15 } : { t_contestada_seg: 180, t_rechazada_seg: 30, t_sin_contestar_seg: 45 };
    Object.entries(v).forEach(([k, x]) => { cont.querySelector(`#l-${k}`).value = x; });
    calcular();
  }));
  calcular();

  const campos = [
    { nombre: "nombre", etiqueta: "Nombre", requerido: true, maxlength: 80 },
    { nombre: "ip", etiqueta: "IP (localhost o red privada)", requerido: true, maxlength: 45, valor: "127.0.0.1" },
    { nombre: "puerto_esl", etiqueta: "Puerto Event Socket", tipo: "number", valor: 8021, min: 1, max: 65535 },
    { nombre: "capacidad_canales", etiqueta: "Capacidad de canales", tipo: "number", valor: 1, min: 1, max: 500, ayuda: "Piloto: empiece con 1 canal." },
    { nombre: "activa", etiqueta: "Planta activa", tipo: "checkbox", valor: true },
  ];
  const editor = (p) => abrirModal({
    titulo: p ? `Editar ${p.nombre}` : "Nueva planta FreeSWITCH", contenido: formulario(campos, p || {}),
    botones: [{ texto: "Cancelar" }, { texto: "Guardar", clase: "btn-primario", accion: async (m) => {
      const d = leerFormulario(m, campos);
      if (p) await put(`/api/telefonia/plantas/${p.id_planta}`, d); else await post("/api/telefonia/plantas", d);
      toast("Planta guardada.", "exito"); render(cont, ctx);
    } }],
  });
  cont.querySelector("[data-nueva]")?.addEventListener("click", () => editor(null));
  cont.querySelectorAll("[data-editar]").forEach((b) => b.addEventListener("click", () => editor(plantas.find((p) => String(p.id_planta) === b.dataset.editar))));
  cont.querySelectorAll("[data-verificar]").forEach((b) => b.addEventListener("click", async () => {
    b.disabled = true;
    try {
      const r = await post(`/api/telefonia/plantas/${b.dataset.verificar}/verificar`);
      abrirModal({ titulo: r.ok ? "FreeSWITCH respondió" : "No se pudo verificar", contenido: r.ok ? `<pre class="codigo">${esc(r.status)}</pre><h3>Gateways SIP</h3><pre class="codigo">${esc(r.gateways)}</pre>` : `<div class="banner peligro">${esc(r.error)}</div>`, botones: [{ texto: "Cerrar" }] });
      render(cont, ctx);
    } catch (e) { errorToast(e); } finally { b.disabled = false; }
  }));
}

export function bannerEstado(e) {
  if (e.estado === "BLOQUEADA") {
    return `<div class="banner peligro">${icono("alerta")}<div><strong>Telefonía real: BLOQUEADA.</strong> La llamada piloto no puede ejecutarse hasta resolver:
      <ul>${e.bloqueos.map((b) => `<li>${esc(b)}</li>`).join("")}</ul>Esto requiere una línea telefónica SIP contratada y FreeSWITCH; es normal verlo mientras no existan.
      <br><strong>Para escuchar y hablar con el agente sin línea telefónica use el módulo <a href="#/prueba">Prueba de Llamada</a></strong> (voz en el navegador).
      <br>Llamada real a su celular con Twilio: ${e.twilio_faltan && e.twilio_faltan.length ? "falta configurar " + esc(e.twilio_faltan.join(", ")) + " (docs\\TWILIO.md)." : "<strong>configurada</strong>, disponible en Prueba de Llamada."}</div></div>`;
  }
  return `<div class="banner info">${icono("check")}<div><strong>Telefonía lista para piloto.</strong> Máximo ${e.max_canales_piloto} canal(es) simultáneo(s); ${e.solo_numeros_autorizados ? "solo números autorizados" : "ATENCIÓN: se permite cualquier número"}. Llamadas activas: ${e.llamadas_activas}.</div></div>`;
}
