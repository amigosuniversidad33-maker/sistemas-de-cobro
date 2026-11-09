// Entrenamiento: skills de especialistas, tools de los agentes y dudas frecuentes.
// Todo versionado como los guiones: una versión no se edita; para cambiarla se crea una nueva y queda en la base de datos.
import { get, post } from "../api.js";
import { abrirModal, boton, chip, errorToast, esc, fecha, formulario, leerFormulario, tarjeta, toast } from "../ui.js";

// ---------------------------------------------------------------- skills (escritas por especialistas, versionadas)
export async function seccionSkills(zona, gestionar) {
  const skills = await get("/api/skills");
  const ambito = { AGENTE: "Agente", SUPERVISOR: "Supervisor de calidad" };
  zona.innerHTML = tarjeta("Skills", `<div class="tabla-envoltura"><table><thead><tr><th>Skill</th><th>Versión</th><th>Ámbito</th><th>Cuándo usarla</th><th>Especialista</th><th>Estado</th><th></th></tr></thead><tbody>
    ${skills.map((s) => `<tr><td><strong>${esc(s.nombre)}</strong></td><td>v${s.version}</td><td>${esc(ambito[s.ambito])}</td><td>${esc(s.cuando_usar)}</td><td>${esc(s.autor)}</td><td>${chip(s.estado)}</td>
      <td class="acciones">${boton("Ver", { chico: true, datos: `data-sk-ver="${s.id_skill}"` })}
      ${gestionar && s.estado === "BORRADOR" ? boton("Publicar", { chico: true, clase: "btn-primario", datos: `data-sk-publicar="${s.id_skill}"` }) : ""}
      ${gestionar && s.estado !== "ARCHIVADO" ? boton("Archivar", { chico: true, datos: `data-sk-archivar="${s.id_skill}"` }) : ""}
      ${gestionar ? boton("Editar", { ico: "editar", chico: true, datos: `data-sk-version="${s.id_skill}"` }) : ""}</td></tr>`).join("")
      || '<tr><td colspan="7" class="texto-tenue">Aún no hay skills. Las escriben especialistas con experiencia en cobranza; no se generan con IA.</td></tr>'}</tbody></table></div>`,
    { descripcion: "Una versión no se edita: para cambiarla se crea una nueva (igual que los guiones). Las de ámbito Agente se asignan en Agentes IA; las del Supervisor se aplican a la evaluación de calidad.",
      acciones: gestionar ? boton("Nueva skill", { ico: "mas", clase: "btn-primario", datos: "data-sk-nueva" }) : "" });
  const campos = [
    { nombre: "nombre", etiqueta: "Nombre", requerido: true, maxlength: 100 },
    { nombre: "ambito", etiqueta: "Ámbito", tipo: "select", opciones: [{ valor: "AGENTE", texto: "Agente (negociación)" }, { valor: "SUPERVISOR", texto: "Supervisor de calidad" }] },
    { nombre: "autor", etiqueta: "Especialista que la define", requerido: true, maxlength: 120 },
    { nombre: "cuando_usar", etiqueta: "Cuándo usarla", requerido: true, maxlength: 255 },
    { nombre: "contenido", etiqueta: "Instrucciones de la skill", tipo: "textarea", requerido: true, ancho: true, maxlength: 3000 },
  ];
  const porId = (id) => skills.find((s) => String(s.id_skill) === id);
  const editor = (base) => abrirModal({
    titulo: base ? `Editar «${base.nombre}» (se guardará como v${base.version + 1})` : "Nueva skill",
    contenido: formulario(campos, base || { ambito: "AGENTE" }) + '<p class="texto-tenue">Se crea como BORRADOR. Escríbala breve y concreta: un prompt largo vuelve lento al agente.</p>',
    botones: [{ texto: "Cancelar" }, { texto: "Guardar borrador", clase: "btn-primario", accion: async (m) => {
      await post("/api/skills", leerFormulario(m, campos));
      toast("Versión creada en borrador.", "exito");
      seccionSkills(zona, gestionar);
    } }],
  });
  zona.querySelector("[data-sk-nueva]")?.addEventListener("click", () => editor(null));
  zona.querySelectorAll("[data-sk-version]").forEach((b) => b.addEventListener("click", () => editor(porId(b.dataset.skVersion))));
  zona.querySelectorAll("[data-sk-ver]").forEach((b) => b.addEventListener("click", () => {
    const s = porId(b.dataset.skVer);
    abrirModal({ titulo: `${s.nombre} v${s.version}`, contenido: `<p><strong>Cuándo usarla:</strong> ${esc(s.cuando_usar)}</p><pre class="codigo">${esc(s.contenido)}</pre><p class="texto-tenue">Definida por ${esc(s.autor)} · ${fecha(s.fecha_creacion)}</p>`, botones: [{ texto: "Cerrar" }] });
  }));
  for (const [atributo, clave, ruta, msg] of [["data-sk-publicar", "skPublicar", "publicar", "Skill publicada."], ["data-sk-archivar", "skArchivar", "archivar", "Skill archivada."]]) {
    zona.querySelectorAll(`[${atributo}]`).forEach((b) => b.addEventListener("click", async () => {
      try { await post(`/api/skills/${b.dataset[clave]}/${ruta}`); toast(msg, "exito"); seccionSkills(zona, gestionar); } catch (e) { errorToast(e); }
    }));
  }
}

// ---------------------------------------------------------------- tools (comportamiento en el código, texto editable y versionado)
export async function seccionTools(zona, gestionar) {
  const tools = await get("/api/herramientas");
  zona.innerHTML = tarjeta("Tools de los agentes", `<div class="tabla-envoltura"><table><thead><tr><th>Tool</th><th>Tipo</th><th>Lo que lee el agente</th><th>Versión</th><th></th></tr></thead><tbody>
    ${tools.map((t) => `<tr><td><strong>${esc(t.etiqueta)}</strong><br><small class="mono">${esc(t.nombre)}</small></td><td>${chip(t.basica ? "ACTIVO" : "PENDIENTE", t.basica ? "Básica" : "Opcional")}</td>
      <td><small>${esc(t.descripcion)}</small>${t.texto_respuesta ? `<br><small><strong>Texto:</strong> ${esc(t.texto_respuesta)}</small>` : ""}</td><td>${t.version ? `v${t.version}` : "original"}</td>
      <td class="acciones">${gestionar ? boton("Editar", { chico: true, datos: `data-tl-editar="${t.nombre}"` }) : ""} ${t.version ? boton("Historial", { chico: true, datos: `data-tl-historial="${t.nombre}"` }) : ""}</td></tr>`).join("")}</tbody></table></div>`,
    { descripcion: "Las tools mantienen liviano el prompt: el agente las usa para obtener y guardar datos en tiempo real (deuda, opciones de pago, dudas, aviso legal, bloqueo por pago). Las validaciones las hace siempre el sistema. Editar crea una versión nueva; las anteriores quedan en el historial. Se activan por agente en Agentes IA." });
  const porNombre = (n) => tools.find((t) => t.nombre === n);
  zona.querySelectorAll("[data-tl-editar]").forEach((b) => b.addEventListener("click", () => {
    const t = porNombre(b.dataset.tlEditar);
    const c = [{ nombre: "descripcion", etiqueta: "Lo que lee el agente (cuándo y cómo usarla)", tipo: "textarea", requerido: true, ancho: true, maxlength: 1000 }];
    if (t.admite_texto) c.push({ nombre: "texto_respuesta", etiqueta: "Texto del aviso legal ({empresa} se reemplaza por el nombre de la empresa)", tipo: "textarea", requerido: true, ancho: true, maxlength: 1000 });
    abrirModal({ titulo: `Editar tool «${t.etiqueta}»`, contenido: formulario(c, t) + '<p class="texto-tenue">Se guarda como una versión nueva y se usa desde la siguiente conversación.</p>',
      botones: [{ texto: "Cancelar" }, { texto: "Guardar versión", clase: "btn-primario", accion: async (m) => {
        await post(`/api/herramientas/${t.nombre}/versiones`, leerFormulario(m, c));
        toast("Nueva versión de la tool guardada.", "exito");
        seccionTools(zona, gestionar);
      } }] });
  }));
  zona.querySelectorAll("[data-tl-historial]").forEach((b) => b.addEventListener("click", async () => {
    const vs = await get(`/api/herramientas/${b.dataset.tlHistorial}/versiones`);
    abrirModal({ titulo: `Historial de «${porNombre(b.dataset.tlHistorial).etiqueta}»`, contenido: `<div class="tabla-envoltura"><table><thead><tr><th>Versión</th><th>Texto</th><th>Fecha</th></tr></thead><tbody>
      ${vs.map((v) => `<tr><td>v${v.version}</td><td><small>${esc(v.descripcion)}${v.texto_respuesta ? `<br><strong>Texto:</strong> ${esc(v.texto_respuesta)}` : ""}</small></td><td>${fecha(v.fecha_creacion)}</td></tr>`).join("")}</tbody></table></div>`, botones: [{ texto: "Cerrar" }] });
  }));
}

// ---------------------------------------------------------------- dudas frecuentes (las consulta la tool «Dudas frecuentes»)
export async function seccionDudas(zona, gestionar) {
  const lista = await get("/api/preguntas-frecuentes");
  zona.innerHTML = tarjeta("Dudas frecuentes", `<div class="tabla-envoltura"><table><thead><tr><th>Pregunta</th><th>Palabras clave</th><th>Respuesta aprobada</th><th>Estado</th><th></th></tr></thead><tbody>
    ${lista.map((p) => `<tr><td>${esc(p.pregunta)}</td><td class="mono">${esc(p.palabras_clave)}</td><td><small>${esc(p.respuesta)}</small></td><td>${chip(p.activa ? "ACTIVO" : "INACTIVO")}</td>
      <td>${gestionar ? boton(p.activa ? "Desactivar" : "Activar", { chico: true, datos: `data-dd-alternar="${p.id}"` }) : ""}</td></tr>`).join("")
      || '<tr><td colspan="5" class="texto-tenue">Sin respuestas. Mientras no haya, el agente no inventa: ofrece que un asesor confirme el dato.</td></tr>'}</tbody></table></div>`,
    { descripcion: "Respuestas que el agente consulta en la base de datos durante la llamada (dónde pagar, horarios, comprobantes).",
      acciones: gestionar ? boton("Agregar respuesta", { ico: "mas", datos: "data-dd-nueva" }) : "" });
  zona.querySelector("[data-dd-nueva]")?.addEventListener("click", () => {
    const c = [
      { nombre: "pregunta", etiqueta: "Pregunta del cliente", requerido: true, ancho: true, maxlength: 255 },
      { nombre: "palabras_clave", etiqueta: "Palabras clave (separadas por espacio)", requerido: true, ancho: true, maxlength: 255 },
      { nombre: "respuesta", etiqueta: "Respuesta aprobada", tipo: "textarea", requerido: true, ancho: true, maxlength: 1000 },
    ];
    abrirModal({ titulo: "Nueva respuesta aprobada", contenido: formulario(c), botones: [{ texto: "Cancelar" }, { texto: "Guardar", clase: "btn-primario", accion: async (m) => {
      await post("/api/preguntas-frecuentes", leerFormulario(m, c)); toast("Respuesta guardada.", "exito"); seccionDudas(zona, gestionar);
    } }] });
  });
  zona.querySelectorAll("[data-dd-alternar]").forEach((b) => b.addEventListener("click", async () => {
    try { await post(`/api/preguntas-frecuentes/${b.dataset.ddAlternar}/alternar`); seccionDudas(zona, gestionar); } catch (e) { errorToast(e); }
  }));
}
