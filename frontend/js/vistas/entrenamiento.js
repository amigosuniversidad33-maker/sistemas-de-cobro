// Módulo Entrenamiento: guiones versionados, casos de prueba y evaluaciones contra la API real.
// No se realiza fine-tuning: el "entrenamiento" consiste en versionar guiones y medir su comportamiento.
import { del, get, post } from "../api.js";
import { icono } from "../iconos.js";
import { abrirModal, boton, chip, errorToast, esc, fecha, formulario, leerFormulario, opcionesDe, tarjeta, toast } from "../ui.js";
import { seccionDudas, seccionSkills, seccionTools } from "./skills_tools.js";

export async function render(cont, ctx) {
  const [guiones, agentes, tramos] = await Promise.all([get("/api/guiones"), get("/api/agentes"), get("/api/tramos")]);
  const gestionar = ctx.tiene("entrenamiento.gestionar");
  cont.innerHTML = `
    <div class="banner info">${icono("libro")}<div>El módulo trabaja con <strong>guiones versionados</strong>, <strong>casos de prueba</strong> y <strong>evaluaciones</strong>.
      Cada conversación guarda la versión del guion y de la política aplicadas. No se anuncia ni se realiza fine-tuning del modelo.</div></div>
    ${tarjeta("Guiones", `<div class="tabla-envoltura"><table><thead><tr><th>Guion</th><th>Versión</th><th>Tramo</th><th>Estado</th><th>Creado</th><th></th></tr></thead><tbody>
      ${guiones.map((g) => `<tr><td><strong>${esc(g.nombre)}</strong></td><td>v${g.version}</td><td>${esc(tramos.find((t) => t.codigo === g.tramo)?.nombre || g.tramo)}</td><td>${chip(g.estado)}</td><td>${fecha(g.fecha_creacion)}</td>
      <td class="acciones">${boton("Ver", { chico: true, datos: `data-ver="${g.id_guion}"` })} ${boton("Casos", { chico: true, datos: `data-casos="${g.id_guion}"` })}
      ${gestionar && g.estado === "BORRADOR" ? boton("Publicar", { chico: true, clase: "btn-primario", datos: `data-publicar="${g.id_guion}"` }) : ""}
      ${gestionar && g.estado !== "ARCHIVADO" ? boton("Archivar", { chico: true, datos: `data-archivar="${g.id_guion}"` }) : ""}
      ${gestionar ? boton("Editar", { ico: "editar", chico: true, datos: `data-version="${g.id_guion}"` }) : ""}</td></tr>`).join("")}</tbody></table></div>`,
      { acciones: gestionar ? boton("Nuevo guion", { ico: "mas", clase: "btn-primario", datos: "data-nuevo" }) : "" })}
    <div id="z-casos"></div>
    <div id="z-skills"></div>
    <div id="z-tools"></div>
    <div id="z-dudas"></div>
    ${gestionar ? tarjeta("Evaluar agente con casos de prueba", `<div class="acciones"><select id="ev-agente">${agentes.map((a) => `<option value="${a.id_agente}">${esc(a.nombre)} · ${esc(a.guion || "sin guion")}</option>`).join("")}</select>
      ${boton("Ejecutar evaluación", { ico: "play", clase: "btn-primario", datos: "data-evaluar" })}</div>
      <p class="texto-tenue">Usa la API real del modelo de lenguaje (consume presupuesto). Si el proveedor falla, no se registran resultados inventados.</p><div id="ev-resultado"></div>`) : ""}`;

  const campos = [
    { nombre: "nombre", etiqueta: "Nombre", requerido: true, maxlength: 100 },
    { nombre: "tramo", etiqueta: "Tramo de mora", tipo: "select", opciones: opcionesDe(tramos, "codigo", "nombre") },
    { nombre: "contenido", etiqueta: "Contenido del guion", tipo: "textarea", requerido: true, ancho: true, maxlength: 8000 },
    { nombre: "frases", etiqueta: "Frases obligatorias (una por línea)", tipo: "textarea", ancho: true },
  ];
  const editor = (base) => abrirModal({
    titulo: base ? `Editar «${base.nombre}» (se guardará como v${base.version + 1})` : "Nuevo guion",
    contenido: formulario(campos, base ? { ...base, frases: (base.frases_obligatorias || []).join("\n") } : {}) + '<p class="texto-tenue">Se crea como BORRADOR. Debe publicarse para usarse en campañas.</p>',
    botones: [{ texto: "Cancelar" }, { texto: "Guardar borrador", clase: "btn-primario", accion: async (m) => {
      const d = leerFormulario(m, campos);
      await post("/api/guiones", { nombre: d.nombre, tramo: d.tramo, contenido: d.contenido, frases_obligatorias: (d.frases || "").split("\n").map((x) => x.trim()).filter(Boolean) });
      toast("Versión creada en borrador.", "exito");
      render(cont, ctx);
    } }],
  });
  cont.querySelector("[data-nuevo]")?.addEventListener("click", () => editor(null));
  const porId = (id) => guiones.find((g) => String(g.id_guion) === id);
  cont.querySelectorAll("[data-version]").forEach((b) => b.addEventListener("click", () => editor(porId(b.dataset.version))));
  cont.querySelectorAll("[data-ver]").forEach((b) => b.addEventListener("click", () => {
    const g = porId(b.dataset.ver);
    abrirModal({ titulo: `${g.nombre} v${g.version}`, contenido: `<pre class="codigo">${esc(g.contenido)}</pre><p><strong>Frases obligatorias:</strong> ${esc((g.frases_obligatorias || []).join("; ") || "—")}</p>`, botones: [{ texto: "Cerrar" }] });
  }));
  for (const [attr, ruta, msg] of [["publicar", "publicar", "Guion publicado."], ["archivar", "archivar", "Guion archivado."]]) {
    cont.querySelectorAll(`[data-${attr}]`).forEach((b) => b.addEventListener("click", async () => {
      try { await post(`/api/guiones/${b.dataset[attr]}/${ruta}`); toast(msg, "exito"); render(cont, ctx); } catch (e) { errorToast(e); }
    }));
  }
  cont.querySelectorAll("[data-casos]").forEach((b) => b.addEventListener("click", () => casos(cont, porId(b.dataset.casos), gestionar)));
  seccionSkills(cont.querySelector("#z-skills"), gestionar);
  seccionTools(cont.querySelector("#z-tools"), gestionar);
  seccionDudas(cont.querySelector("#z-dudas"), gestionar);
  cont.querySelector("[data-evaluar]")?.addEventListener("click", async (ev) => {
    const zona = cont.querySelector("#ev-resultado");
    ev.target.disabled = true;
    zona.innerHTML = '<div class="estado-carga cargando">Ejecutando casos contra la API</div>';
    try {
      const r = await post("/api/entrenamiento/evaluar", { id_agente: Number(cont.querySelector("#ev-agente").value) });
      zona.innerHTML = `<p><strong>${r.aprobados} de ${r.total}</strong> casos aprobados para ${esc(r.agente)}.</p><div class="tabla-envoltura"><table><thead><tr><th>Caso</th><th>Resultado</th><th>Respuesta del agente</th><th>Detalle</th></tr></thead><tbody>
        ${r.resultados.map((x) => `<tr><td>${esc(x.intencion)}</td><td>${chip(x.aprobado ? "COMPLETADO" : "FALLIDO", x.aprobado ? "Aprobado" : "No aprobado")}</td><td>${esc(x.respuesta)}</td><td>${esc(x.detalle)}</td></tr>`).join("")}</tbody></table></div>`;
    } catch (e) {
      zona.innerHTML = `<div class="estado-error">${esc(e.message)}</div>`;
    } finally { ev.target.disabled = false; }
  });
}

async function casos(cont, g, gestionar) {
  const zona = cont.querySelector("#z-casos");
  const lista = await get(`/api/guiones/${g.id_guion}/casos`);
  zona.innerHTML = tarjeta(`Casos de prueba · ${g.nombre} v${g.version}`, `<div class="tabla-envoltura"><table><thead><tr><th>Intención</th><th>Entrada del cliente</th><th>Respuesta esperada</th><th>Reglas</th><th>Última evaluación</th><th></th></tr></thead><tbody>
    ${lista.map((c) => `<tr><td>${esc(c.intencion)}</td><td>${esc(c.entrada_cliente)}</td><td>${esc(c.respuesta_esperada)}</td>
      <td class="mono">${c.debe_contener ? `debe: ${esc(c.debe_contener)}<br>` : ""}${c.no_debe_contener ? `no debe: ${esc(c.no_debe_contener)}` : ""}</td>
      <td>${c.ultima_evaluacion ? `${chip(c.ultima_evaluacion.aprobado ? "COMPLETADO" : "FALLIDO", c.ultima_evaluacion.aprobado ? "Aprobado" : "No aprobado")}<br><small>${fecha(c.ultima_evaluacion.fecha)}</small>` : "—"}</td>
      <td>${gestionar ? boton("Eliminar", { chico: true, datos: `data-borrar="${c.id}"` }) : ""}</td></tr>`).join("") || '<tr><td colspan="6" class="texto-tenue">Sin casos.</td></tr>'}</tbody></table></div>`,
    { acciones: gestionar ? boton("Agregar caso", { ico: "mas", datos: "data-agregar" }) : "" });
  zona.scrollIntoView({ behavior: "smooth" });
  zona.querySelectorAll("[data-borrar]").forEach((b) => b.addEventListener("click", async () => { try { await del(`/api/casos/${b.dataset.borrar}`); casos(cont, g, gestionar); } catch (e) { errorToast(e); } }));
  zona.querySelector("[data-agregar]")?.addEventListener("click", () => {
    const c = [
      { nombre: "intencion", etiqueta: "Intención", requerido: true, maxlength: 100 },
      { nombre: "entrada_cliente", etiqueta: "Lo que dice el cliente", requerido: true, ancho: true, tipo: "textarea" },
      { nombre: "respuesta_esperada", etiqueta: "Respuesta esperada", requerido: true, ancho: true, tipo: "textarea" },
      { nombre: "debe_contener", etiqueta: "Debe contener (regex separadas por |)", maxlength: 255 },
      { nombre: "no_debe_contener", etiqueta: "No debe contener (regex separadas por |)", maxlength: 255 },
    ];
    abrirModal({ titulo: "Nuevo caso de prueba", contenido: formulario(c), botones: [{ texto: "Cancelar" }, { texto: "Guardar", clase: "btn-primario", accion: async (m) => { await post(`/api/guiones/${g.id_guion}/casos`, leerFormulario(m, c)); casos(cont, g, gestionar); } }] });
  });
}
