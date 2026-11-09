// Módulo Agentes IA: guion, tono, personalidad, voz Deepgram, severidad por tramo, tools, skills y tiempos de llamada.
import { get, post, put } from "../api.js";
import { abrirModal, boton, chip, esc, formulario, leerFormulario, opcionesDe, tarjeta, toast } from "../ui.js";

export async function render(cont, ctx) {
  const [agentes, guiones, politicas, voces, tramos, herramientas, skills] = await Promise.all([
    get("/api/agentes"), get("/api/guiones"), ctx.tiene("seguridad.ver") ? get("/api/politicas") : Promise.resolve([]),
    get("/api/voces"), get("/api/tramos"), get("/api/herramientas"), get("/api/skills"),
  ]);
  const sev = Object.fromEntries(tramos.map((t) => [t.codigo, t]));
  const etiqueta = Object.fromEntries(herramientas.map((h) => [h.nombre, h.etiqueta]));
  const opcionales = herramientas.filter((h) => !h.basica);
  const skillsAgente = skills.filter((s) => s.ambito === "AGENTE" && s.estado === "PUBLICADO");
  cont.innerHTML = `
    <div class="banner info"><div>Cada agente es un <strong>negociador senior</strong>: busca un acuerdo de pago real y concreto, sin juzgar al cliente.
      Sus <strong>skills</strong> las escriben especialistas (Entrenamiento) y sus <strong>tools</strong> hacen el trabajo pesado para mantener el prompt liviano.
      La severidad se ajusta al tramo de mora y nunca autoriza amenazas, engaños, descuentos ni condonaciones.</div></div>
    ${tarjeta("Agentes configurados", `<div class="tabla-envoltura"><table><thead><tr><th>Agente</th><th>Voz</th><th>Tiempos</th><th>Severidad</th><th>Guion (tramo)</th><th>Skills</th><th>Tools activas</th><th>Estado</th><th></th></tr></thead>
      <tbody>${agentes.map((a) => `<tr><td><strong>${esc(a.nombre)}</strong><br><small class="texto-tenue">${esc(a.tono)} · ${esc(a.personalidad || "")}</small></td>
        <td class="mono">${esc(a.voz_deepgram)}<br><small>${esc(Number(a.velocidad_voz || 1).toFixed(2))}×</small></td>
        <td><small>Espera ${esc(Number(a.espera_inicio_seg).toFixed(1))} s<br>Escucha ${esc(Number(a.silencio_fin_seg).toFixed(1))} s<br>Silencio máx. ${esc(Number(a.silencio_max_seg).toFixed(1))} s</small></td>
        <td>${chip(a.severidad >= 2 ? "MEDIA" : "BAJA", `Nivel ${a.severidad}`)}</td>
        <td>${esc(a.guion || "—")}<br><small class="texto-tenue">${esc(sev[a.tramo]?.nombre || "")}</small></td>
        <td><small>${a.skills.map((s) => esc(`${s.nombre} v${s.version}`)).join("<br>") || "—"}</small></td>
        <td><small>${a.herramientas.filter((h) => opcionales.some((o) => o.nombre === h)).map((h) => esc(etiqueta[h] || h)).join("<br>") || "Solo básicas"}</small></td>
        <td>${chip(a.activo ? "ACTIVO" : "INACTIVO")}</td>
        <td>${ctx.tiene("agentes.gestionar") ? boton("Editar", { ico: "editar", chico: true, datos: `data-editar="${a.id_agente}"` }) : ""}</td></tr>`).join("")}</tbody></table></div>`,
      { acciones: ctx.tiene("agentes.gestionar") ? boton("Nuevo agente", { ico: "mas", clase: "btn-primario", datos: "data-nuevo" }) : "" })}
    ${tarjeta("Severidad por tramo de mora", `<div class="tabla-envoltura"><table><thead><tr><th>Tramo</th><th>Días</th><th>Severidad</th><th>Tono permitido</th></tr></thead><tbody>
      ${tramos.map((t) => `<tr><td>${esc(t.nombre)}</td><td>${t.dias_min}–${t.dias_max}</td><td>${t.severidad}</td><td>${esc(t.tono_permitido)}</td></tr>`).join("")}</tbody></table></div>
      <p class="texto-tenue">Casos fuera de 1–60 días se clasifican como «Gestión especial» y requieren una regla explícita; no se asignan automáticamente.</p>`)}`;

  const campos = (a = {}) => [
    { nombre: "nombre", etiqueta: "Nombre del agente", requerido: true, maxlength: 80 },
    { nombre: "voz_deepgram", etiqueta: "Voz Deepgram (español)", tipo: "select", opciones: voces.map((v) => ({ valor: v, texto: v })) },
    { nombre: "velocidad_voz", etiqueta: "Velocidad de la voz", tipo: "number", requerido: true, min: 0.7, max: 1.4, paso: 0.05,
      ayuda: "1.00 = normal; 0.85–0.95 suena más pausado y natural por teléfono; hasta 1.40 más rápido." },
    { nombre: "tono", etiqueta: "Tono", requerido: true, maxlength: 80 },
    { nombre: "espera_inicio_seg", etiqueta: "Tiempo de espera al contestar (s)", tipo: "number", requerido: true, min: 0, max: 5, paso: 0.5,
      ayuda: "Recomendado 0: el agente habla apenas contestan." },
    { nombre: "silencio_fin_seg", etiqueta: "Silencio de escucha (s)", tipo: "number", requerido: true, min: 0.3, max: 5, paso: 0.1,
      ayuda: "Cuando el cliente deja de hablar, cuánto silencio espera el agente para responder. Recomendado 2." },
    { nombre: "silencio_max_seg", etiqueta: "Tiempo de silencio del cliente (s)", tipo: "number", requerido: true, min: 2, max: 20, paso: 0.5,
      ayuda: "Si el cliente no dice nada, cuánto espera antes de preguntar «¿Me escucha?». Recomendado 6." },
    { nombre: "severidad", etiqueta: "Severidad (según tramo del guion)", tipo: "select", numerico: true, opciones: [1, 2, 3].map((n) => ({ valor: n, texto: `Nivel ${n}` })) },
    { nombre: "id_guion", etiqueta: "Guion", tipo: "select", numerico: true, opciones: opcionesDe(guiones.filter((g) => g.estado !== "ARCHIVADO"), "id_guion", (g) => `${g.nombre} v${g.version} · ${g.estado} · ${sev[g.tramo]?.nombre || g.tramo}`, "Sin guion") },
    { nombre: "id_politica", etiqueta: "Política de seguridad IA", tipo: "select", numerico: true, opciones: opcionesDe(politicas.filter((p) => p.activa), "id_politica", (p) => `${p.nombre} v${p.version}`, a.id_politica ? undefined : "Sin política") },
    { nombre: "personalidad", etiqueta: "Personalidad", tipo: "textarea", ancho: true, maxlength: 255 },
    { nombre: "activo", etiqueta: "Agente activo", tipo: "checkbox", ancho: true, valor: true },
  ];
  const grupoChecks = (titulo, nombre, items, marcados, ayuda) => `<div class="campo ancho"><label>${esc(titulo)}</label>
    <div class="lista-checks">${items.map((it) => `<label class="check"><input type="checkbox" name="${nombre}" value="${esc(it.valor)}" ${marcados.includes(it.valor) ? "checked" : ""}>
      <span>${esc(it.texto)}${it.detalle ? `<small class="texto-tenue">${esc(it.detalle)}</small>` : ""}</span></label>`).join("") || '<span class="texto-tenue">No hay opciones.</span>'}</div>
    <small>${esc(ayuda)}</small></div>`;
  const abrir = (a) => {
    const c = campos(a || {});
    const tools = grupoChecks("Tools activas", "herramientas",
      opcionales.map((h) => ({ valor: h.nombre, texto: h.etiqueta })),
      a ? a.herramientas : opcionales.map((h) => h.nombre),
      `Siempre activas: ${herramientas.filter((h) => h.basica).map((h) => h.etiqueta).join(", ")}. El texto de cada tool se edita en Entrenamiento.`);
    const sks = grupoChecks("Skills del agente", "skills",
      skillsAgente.map((s) => ({ valor: String(s.id_skill), texto: `${s.nombre} v${s.version}`, detalle: `${s.autor} · ${s.cuando_usar}` })),
      a ? a.skills.map((s) => String(s.id_skill)) : [],
      "Solo skills PUBLICADAS de ámbito Agente. Se crean y versionan en Entrenamiento.");
    abrirModal({
      titulo: a ? `Editar agente ${a.nombre}` : "Nuevo agente IA",
      contenido: formulario(c, a || { activo: true, voz_deepgram: voces[0], velocidad_voz: 1, severidad: 1, espera_inicio_seg: 0, silencio_fin_seg: 2, silencio_max_seg: 6 })
        + `<div class="form-rejilla">${tools}${sks}</div>`,
      alAbrir: (m) => {
        const sel = m.querySelector('[name="id_guion"]');
        const sevSel = m.querySelector('[name="severidad"]');
        sel.addEventListener("change", () => {
          const g = guiones.find((x) => String(x.id_guion) === sel.value);
          if (g && sev[g.tramo]) sevSel.value = sev[g.tramo].severidad;
        });
      },
      botones: [{ texto: "Cancelar" }, { texto: "Guardar", clase: "btn-primario", accion: async (m) => {
        const datos = leerFormulario(m, c);
        datos.herramientas = [...m.querySelectorAll('[name="herramientas"]:checked')].map((x) => x.value);
        datos.skills = [...m.querySelectorAll('[name="skills"]:checked')].map((x) => Number(x.value));
        if (a) await put(`/api/agentes/${a.id_agente}`, datos); else await post("/api/agentes", datos);
        toast("Agente guardado.", "exito");
        render(cont, ctx);
      } }],
    });
  };
  cont.querySelector("[data-nuevo]")?.addEventListener("click", () => abrir(null));
  cont.querySelectorAll("[data-editar]").forEach((b) => b.addEventListener("click", () => abrir(agentes.find((a) => String(a.id_agente) === b.dataset.editar))));
}
