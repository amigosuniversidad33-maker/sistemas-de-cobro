// Control y Supervisión: dashboard ejecutivo (sección 5 y 6.5 del documento) calculado desde datos persistidos.
import { get, post } from "../api.js";
import { actualizarPausa } from "../app.js";
import { icono } from "../iconos.js";
import { abrirModal, chip, dinero, errorToast, esc, fecha, formulario, hoyLocal, leerFormulario, num, pct, tarjeta, toast } from "../ui.js";

export async function render(cont, ctx) {
  const hoy = hoyLocal();
  cont.innerHTML = `
    <section class="tarjeta">
      <form class="filtros" id="f-dash">
        <div class="campo"><label for="d-desde">Desde</label><input type="date" id="d-desde" name="desde" value="${hoy}"></div>
        <div class="campo"><label for="d-hasta">Hasta</label><input type="date" id="d-hasta" name="hasta" value="${hoy}"></div>
        <div class="campo"><label for="d-modo">Modo</label><select id="d-modo" name="modo">
          <option value="TODOS">Todos</option><option value="REAL">Real</option><option value="PRUEBA">Prueba</option></select></div>
        <div class="campo"><label for="d-canal">Canal</label><select id="d-canal" name="canal">
          <option value="TODOS">Todos</option><option value="TELEFONIA">Telefonía real</option><option value="VOZ_NAVEGADOR">Voz de prueba</option><option value="TEXTO">Texto</option></select></div>
        <button class="btn btn-primario" type="submit">${icono("recargar")}Actualizar</button>
        ${ctx.tiene("sistema.emergencia") ? `<button class="btn btn-peligro" type="button" id="btn-emergencia">${icono("emergencia")}Pausa de emergencia</button>` : ""}
      </form>
    </section>
    <div id="dash"><div class="estado-carga cargando">Calculando indicadores</div></div>`;
  const f = cont.querySelector("#f-dash");
  const cargar = async () => {
    const zona = cont.querySelector("#dash");
    zona.innerHTML = '<div class="estado-carga cargando">Calculando indicadores</div>';
    try {
      const d = await get("/api/dashboard", Object.fromEntries(new FormData(f)));
      zona.innerHTML = vista(d);
      dibujarBarras(zona);
    } catch (e) {
      zona.innerHTML = `<div class="estado-error">${esc(e.message)}</div>`;
    }
  };
  f.addEventListener("submit", (e) => { e.preventDefault(); cargar(); });
  cont.querySelector("#btn-emergencia")?.addEventListener("click", () => emergencia(cargar));
  await cargar();
}

function emergencia(recargar) {
  const campos = [
    { nombre: "accion", etiqueta: "Acción", tipo: "select", opciones: [{ valor: "1", texto: "Activar pausa (bloquear nuevas marcaciones)" }, { valor: "0", texto: "Desactivar pausa" }] },
    { nombre: "motivo", etiqueta: "Motivo", requerido: true, ancho: true, maxlength: 255 },
  ];
  abrirModal({
    titulo: "Pausa de emergencia",
    contenido: `<div class="banner peligro">${icono("emergencia")}<div>Al activarla se cancelan los trabajos de marcación pendientes y no se originan nuevas llamadas ni conversaciones.
      Las llamadas activas terminan su turno en curso y se cierran (ver manual técnico).</div></div><br>${formulario(campos)}`,
    botones: [{ texto: "Cancelar" }, { texto: "Aplicar", clase: "btn-peligro", accion: async (c) => {
      const d = leerFormulario(c, campos);
      const r = await post("/api/sistema/emergencia", { activar: d.accion === "1", motivo: d.motivo });
      toast(r.pausa_emergencia ? `Pausa activada. Trabajos cancelados: ${r.trabajos_cancelados}` : "Pausa desactivada.", r.pausa_emergencia ? "error" : "exito");
      actualizarPausa();
      recargar();
    } }],
  });
}

function kpi(etq, valor, sub = "", color = "", ico = "") {
  return `<div class="kpi ${color}"><div class="kpi-etq">${ico ? icono(ico) : ""}${esc(etq)}</div><div class="kpi-valor">${valor}</div><div class="kpi-sub">${sub}</div></div>`;
}

function vista(d) {
  const l = d.llamadas, c = d.cobranza;
  const montos = Object.entries(c.monto_prometido).map(([m, v]) => dinero(v, m)).join(" · ") || dinero(0);
  const gasto = d.consumo_api;
  const alertas = Object.entries(d.alertas_abiertas).reduce((a, [, n]) => a + n, 0);
  return `
  ${d.pausa_emergencia ? `<div class="banner peligro">${icono("emergencia")}<strong>Pausa de emergencia activa:</strong>&nbsp;no se originan nuevas llamadas.</div>` : ""}
  <div class="kpis">
    ${kpi("Intentos (LS)", num(l.intentos_LS), `${esc(d.rango.desde)} a ${esc(d.rango.hasta)}`, "", "telefono")}
    ${kpi("En curso ahora", num(l.en_curso_ahora), "Llamadas y conversaciones activas", "violeta", "actividad")}
    ${kpi("Contestadas (LC)", num(l.contestadas_LC), pct(l.tasa_contestacion) + " de contacto", "verde")}
    ${kpi("Rechazadas (LR)", num(l.rechazadas_LR), pct(l.tasa_rechazo) + " de contacto", "naranja")}
    ${kpi("Sin contestar (LNC)", num(l.sin_contestar_LNC), pct(l.tasa_no_contestacion) + " de contacto", "gris")}
    ${kpi("Fallos técnicos", num(l.fallos_tecnicos), pct(l.tasa_fallo_tecnico) + " de intentos", "rojo", "alerta")}
    ${kpi("Promesas de pago", num(c.promesas_generadas), montos, "verde", "promesa")}
    ${kpi("Exclusiones activas", num(d.exclusiones.activas), `${num(d.exclusiones.nuevas_en_rango)} nuevas en el rango`, "", "nocontacto")}
    ${kpi("Gasto API estimado hoy", `US$ ${esc(gasto.gasto_estimado_hoy_usd)}`, `Presupuesto diario US$ ${esc(gasto.presupuesto_diario_usd)}`, "violeta")}
    ${kpi("Alertas abiertas", num(alertas), Object.entries(d.alertas_abiertas).map(([s, n]) => `${esc(s)}: ${n}`).join(" · ") || "Sin alertas", alertas ? "rojo" : "verde", "escudo")}
  </div>
  <div class="rejilla rejilla-2">
    ${tarjeta("Resultado de contacto por día", `<div class="grafico" data-serie='${esc(JSON.stringify(d.serie_diaria))}'></div>
      <div class="leyenda"><span><i class="c-contestada"></i>Contestadas</span><span><i class="c-rechazada"></i>Rechazadas</span><span><i class="c-sin"></i>Sin contestar</span><span><i class="c-fallo"></i>Fallidas</span></div>`,
      { descripcion: "Estado técnico, contacto y cobranza se registran por separado" })}
    ${tarjeta("Tasas y denominadores", `
      <dl class="lista-def">
        <dt>Tasa de contestación</dt><dd>${pct(l.tasa_contestacion)}</dd>
        <dt>Tasa de rechazo</dt><dd>${pct(l.tasa_rechazo)}</dd>
        <dt>Tasa de no contestación</dt><dd>${pct(l.tasa_no_contestacion)}</dd>
        <dt>Tasa de fallo técnico</dt><dd>${pct(l.tasa_fallo_tecnico)}</dd>
        <dt>Cumplimiento de promesas</dt><dd>${pct(c.tasa_cumplimiento)}</dd>
      </dl>
      <p class="texto-tenue"><strong>Denominador de tasas de contacto:</strong> ${esc(l.denominadores.tasas_de_contacto)}<br>
      <strong>Fallo técnico:</strong> ${esc(l.denominadores.tasa_fallo_tecnico)}<br><strong>Cumplimiento:</strong> ${esc(c.denominador_cumplimiento)}<br>
      Sin datos se muestra «—» (no se divide entre cero). Canceladas: ${num(l.canceladas)} · en curso en el rango: ${num(l.en_curso_en_rango)}.</p>`)}
  </div>
  <div class="rejilla rejilla-2">
    ${tarjeta("Resultado por módulo de campaña", tablaModulos(d.por_modulo), { descripcion: "Recordatorio / Mora Temprana vs. Mora Tardía" })}
    ${tarjeta("Cobranza", `
      <dl class="lista-def">
        ${Object.entries(c.promesas_por_estado).map(([e, n]) => `<dt>${chip(e)}</dt><dd>${num(n)}</dd>`).join("") || "<dt>Promesas</dt><dd>0</dd>"}
        <dt>Monto prometido</dt><dd>${montos}</dd>
        ${Object.entries(c.resultados).map(([e, n]) => `<dt>Resultado ${esc(e.replaceAll("_", " ").toLowerCase())}</dt><dd>${num(n)}</dd>`).join("")}
      </dl><p class="texto-tenue">Una promesa no es un pago: el cumplimiento lo registra un usuario autorizado.</p>`)}
  </div>
  <div class="rejilla rejilla-3">
    ${tarjeta("Ventana horaria", `<div class="kpi-valor">${num(d.ventana_horaria.llamadas_telefonicas_fuera_de_ventana)}</div>
      <p class="texto-tenue">Llamadas telefónicas iniciadas fuera de ventana (objetivo: 0). Ventana por defecto ${esc(d.ventana_horaria.ventana_por_defecto)} (${esc(d.rango.zona_horaria)}). Política inicial del proyecto, configurable; no es una afirmación legal verificada.</p>`)}
    ${tarjeta("Meta de diseño (futura)", `<div class="kpi-valor">${num(d.meta_diseno.intentos_promedio_diario)} <small class="texto-tenue">/ ${num(d.meta_diseno.meta_diaria)} por día</small></div>
      <p class="texto-tenue">${esc(d.meta_diseno.nota)}</p>`)}
    ${tarjeta("Canales y modos", `<dl class="lista-def">${Object.entries(l.por_canal).map(([k, v]) => `<dt>${esc(k.replaceAll("_", " "))}</dt><dd>${num(v)}</dd>`).join("") || "<dt>Sin interacciones</dt><dd>0</dd>"}
      ${Object.entries(l.por_modo).map(([k, v]) => `<dt>Modo ${esc(k.toLowerCase())}</dt><dd>${num(v)}</dd>`).join("")}</dl>`)}
  </div>
  ${tarjeta("Consumo de APIs en el rango", `<div class="tabla-envoltura"><table><thead><tr><th>Servicio</th><th class="num">Solicitudes</th><th class="num">Fallidas</th><th class="num">Costo estimado (US$)</th></tr></thead>
    <tbody>${gasto.por_servicio.map((s) => `<tr><td>${esc(s.servicio)}</td><td class="num">${num(s.llamadas)}</td><td class="num">${num(s.fallidas)}</td><td class="num">${esc(s.costo_estimado_usd)}</td></tr>`).join("") || '<tr><td colspan="4" class="texto-tenue">Sin consumo registrado.</td></tr>'}</tbody></table></div>
    <p class="texto-tenue">${esc(gasto.nota)}</p>`)}`;
}

function tablaModulos(pm) {
  const filas = Object.entries(pm);
  if (!filas.length) return '<div class="estado-vacio">Sin llamadas en el rango.</div>';
  return `<div class="tabla-envoltura"><table><thead><tr><th>Módulo</th><th class="num">Intentos</th><th class="num">LC</th><th class="num">LR</th><th class="num">LNC</th><th class="num">Promesas</th><th>Distribución</th></tr></thead><tbody>
    ${filas.map(([m, v]) => `<tr><td>${esc(m)}</td><td class="num">${num(v.intentos || 0)}</td><td class="num">${num(v.CONTESTADA || 0)}</td><td class="num">${num(v.RECHAZADA || 0)}</td><td class="num">${num(v.SIN_CONTESTAR || 0)}</td><td class="num">${num(v.PROMESA || 0)}</td>
    <td><div class="barra-apilada" data-barra='${esc(JSON.stringify([v.CONTESTADA || 0, v.RECHAZADA || 0, v.SIN_CONTESTAR || 0]))}'><span class="c-contestada"></span><span class="c-rechazada"></span><span class="c-sin"></span></div></td></tr>`).join("")}
  </tbody></table></div>`;
}

function dibujarBarras(zona) {
  // Anchos aplicados por CSSOM (compatible con la política CSP sin estilos en línea).
  zona.querySelectorAll("[data-barra]").forEach((b) => {
    const v = JSON.parse(b.dataset.barra);
    const t = v.reduce((a, x) => a + x, 0) || 1;
    [...b.children].forEach((s, i) => { s.style.width = `${(v[i] * 100) / t}%`; });
  });
  zona.querySelectorAll("[data-serie]").forEach((g) => {
    const serie = JSON.parse(g.dataset.serie);
    const dias = Object.keys(serie);
    if (!dias.length) { g.innerHTML = '<div class="estado-vacio">Sin llamadas en el rango.</div>'; return; }
    const claves = [["CONTESTADA", "c-contestada"], ["RECHAZADA", "c-rechazada"], ["SIN_CONTESTAR", "c-sin"], ["FALLIDA", "c-fallo"]];
    const max = Math.max(1, ...dias.map((d) => claves.reduce((a, [k]) => a + (serie[d][k] || 0), 0)));
    const W = 600, H = 200, m = 28, ancho = Math.min(48, (W - m * 2) / dias.length - 6);
    let svg = `<svg viewBox="0 0 ${W} ${H + 20}" role="img" aria-label="Llamadas por día"><line class="eje" x1="${m}" y1="${H}" x2="${W - 8}" y2="${H}"/>`;
    svg += `<text x="4" y="14">${max}</text><text x="4" y="${H}">0</text>`;
    dias.forEach((d, i) => {
      const x = m + 6 + i * ((W - m * 2) / dias.length);
      let y = H;
      claves.forEach(([k, cls]) => {
        const h = ((serie[d][k] || 0) / max) * (H - 20);
        if (h > 0) { y -= h; svg += `<rect class="${cls}" x="${x}" y="${y}" width="${ancho}" height="${h}" rx="2"><title>${esc(k)}: ${serie[d][k]}</title></rect>`; }
      });
      svg += `<text x="${x}" y="${H + 14}">${esc(d.slice(5))}</text>`;
    });
    g.innerHTML = svg + "</svg>";
  });
}

export { fecha };
