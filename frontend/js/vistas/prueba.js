// Módulo Prueba de Llamada: conversación REAL con la API del modelo por texto y por voz en el navegador (Deepgram).
// Importante: la voz en el navegador NO es una llamada telefónica; se identifica como "VOZ DE PRUEBA".
import { api, get, post, put } from "../api.js";
import { icono } from "../iconos.js";
import { boton, chip, dinero, errorToast, esc, modo, opcionesDe, tablaPaginada, tarjeta, toast, fecha } from "../ui.js";

const UMBRAL_VOZ = 0.035;      // nivel RMS que se considera voz
const SILENCIO_FIN_MS = 1200;  // silencio que marca el fin de turno
const ESPERA_INICIO_MS = 8000; // si no habla en este tiempo, se considera silencio
const MAX_TURNO_MS = 30000;    // duración máxima de un turno

export async function render(cont, ctx) {
  const agentes = (await get("/api/agentes")).filter((a) => a.activo);
  // Si el servidor es de una versión anterior (sin este endpoint), se asume: sin Deepgram y agente sin datos de proveedor.
  const cfgVoz = await get("/api/voz/config").catch(() => ({ deepgram: false, proveedor_ia: "desconocido",
    etiqueta_ia: "reinicie el sistema (DETENER.bat e INICIAR.bat) para ver el proveedor" }));
  const vozNavegadorDisponible = "speechSynthesis" in window;
  guardarVelocidad(agentes[0]?.velocidad_voz ?? 1);   // la velocidad vive en el agente
  cont.innerHTML = `
    <div class="rejilla rejilla-2">
      ${tarjeta("Configurar prueba", `
        <div class="form-rejilla">
          <div class="campo ancho"><label for="p-agente">Agente IA</label><select id="p-agente">${opcionesDe(agentes, "id_agente", (a) => `${a.nombre} · ${a.guion || "sin guion"}`).map((o) => `<option value="${o.valor}">${esc(o.texto)}</option>`).join("")}</select></div>
          <div class="campo ancho"><label for="p-buscar">Cliente ficticio (buscar por nombre o documento)</label><input id="p-buscar" type="search" placeholder="Escriba para buscar…"></div>
          <div class="campo ancho"><label for="p-deuda">Deuda</label><select id="p-deuda"><option value="">— Busque un cliente —</option></select>
            <small>El agente solo recibe el nombre de pila; la deuda se consulta por herramienta tras verificar los últimos 4 dígitos del documento.</small></div>
          <div class="campo"><label for="p-canal">Canal</label><select id="p-canal"><option value="TEXTO">Texto (${cfgVoz.proveedor_ia === "local" ? "agente local" : "API real del modelo"})</option><option value="VOZ_NAVEGADOR">Voz en navegador (${cfgVoz.deepgram ? "Deepgram STT/TTS" : "voz de Chrome/Edge, gratis"})</option></select></div>
          <div class="campo ancho"><label for="p-velocidad">Velocidad de la voz del agente: <strong id="p-vel-valor">${formatoVelocidad(leerVelocidad())}</strong></label>
            <div class="acciones"><input id="p-velocidad" type="range" min="${VEL_MIN}" max="${VEL_MAX}" step="0.05" value="${leerVelocidad()}" aria-describedby="p-vel-ayuda">${boton("Normal", { chico: true, datos: "data-vel-normal" })}${ctx.tiene("agentes.gestionar") ? boton("Guardar en el agente", { ico: "check", chico: true, datos: "data-vel-guardar" }) : ""}</div>
            <small id="p-vel-ayuda">Izquierda: más lento y pausado. Derecha: más rápido. Se aplica al instante, también mientras el agente habla. Guárdela en el agente para usarla también en la llamada real.</small></div>
          <div class="campo"><label class="check"><input type="checkbox" id="p-manos" checked> Manos libres (escucha automática)</label>
            <label class="check"><input type="checkbox" id="p-leer" checked> Escuchar al agente también en modo texto</label></div>
          ${cfgVoz.deepgram ? "" : `<div class="campo ancho"><label for="p-voz-nav">Voz del agente (navegador)</label>
            <div class="acciones"><select id="p-voz-nav"></select>${boton("Escuchar muestra", { ico: "volumen", chico: true, datos: "data-muestra" })}</div>
            <small>Las voces «Natural» u «Online» (Microsoft Edge) y «Google» (Chrome) son las más realistas.</small></div>`}
          <div class="campo ancho"><div class="acciones">
            <span class="chip ${cfgVoz.proveedor_ia === "local" ? "naranja" : "verde"}">IA: ${esc(cfgVoz.etiqueta_ia)}</span>
            <span class="chip ${cfgVoz.deepgram ? "verde" : "naranja"}">Voz: ${cfgVoz.deepgram ? "Deepgram (API real)" : "voz del navegador (sin Deepgram)"}</span></div>
            ${cfgVoz.proveedor_ia === "local" ? '<small>Sin ANTHROPIC_API_KEY el sistema usa un agente local de reglas que sigue el guion y las mismas validaciones. Para conversación con IA real agregue la clave en backend\\.env.</small>' : ""}</div>
        </div><br>
        <div class="acciones">${boton("Iniciar conversación", { ico: "play", clase: "btn-primario", datos: "data-iniciar" })}</div>
        <div id="p-aviso"></div>`, { descripcion: "Las pruebas usan clientes ficticios y no afectan a clientes reales." })}
      ${tarjeta("Estado de la conversación", '<div id="p-estado" class="texto-tenue">Sin conversación activa.</div>')}
    </div>
    <section class="tarjeta" id="p-chat-tarjeta" hidden>
      <div class="tarjeta-cab"><div class="acciones" id="p-modo"></div><div class="acciones">${boton("Finalizar", { ico: "cerrar", datos: "data-finalizar" })}</div></div>
      <div class="chat" id="p-chat" aria-live="polite"></div>
      <div class="chat-entrada" id="p-texto">
        <input id="p-mensaje" maxlength="1000" placeholder="Escriba como si fuera el cliente…" aria-label="Mensaje del cliente">
        ${boton("Enviar", { ico: "enviar", clase: "btn-primario", datos: "data-enviar" })}
      </div>
      <div class="chat-entrada" id="p-voz" hidden>
        ${boton("Hablar", { ico: "mic", clase: "btn-primario", datos: "data-hablar" })}
        <div class="campo"><div class="medidor"><span id="p-nivel"></span></div><small id="p-voz-estado">Listo.</small></div>
      </div>
    </section>
    ${tarjeta("Llamada real a su celular (Twilio)", `<div id="tw-zona"><div class="estado-carga cargando">Revisando configuración</div></div>`,
      { descripcion: "El agente llama a un número autorizado, habla con voz neuronal y entiende lo que usted responde. Usa el agente, el cliente y la deuda elegidos arriba." })}
    ${tarjeta("Llamada real a extensión Zoiper (FreeSWITCH)", `<div id="fs-zona"><div class="estado-carga cargando">Revisando configuración</div></div>`,
      { descripcion: "FreeSWITCH en la máquina virtual Linux llama a la extensión SIP donde está conectado Zoiper (celular o computadora). El agente habla con su voz Deepgram y entiende lo que usted responde. Usa el agente, el cliente y la deuda elegidos arriba." })}
    ${tarjeta("Prueba de calidad de voz (Deepgram TTS)", `
      <div class="form-rejilla"><div class="campo ancho"><label for="tts-texto">Texto</label><input id="tts-texto" maxlength="500" value="Buen día, le saluda Sofía, de Financiera Progreso. Le llamo para recordarle, con mucho gusto, la fecha de pago de su cuota."></div>
      <div class="campo"><label for="tts-voz">Voz</label><select id="tts-voz">${(await get("/api/voces")).map((v) => `<option>${esc(v)}</option>`).join("")}</select></div>
      <div class="campo"><label>&nbsp;</label>${boton("Sintetizar y medir latencia", { ico: "volumen", datos: "data-tts" })}</div></div><div id="tts-res"></div>`)}
    <div id="p-historial"></div>`;

  // ---- llamada real con Twilio
  const twZona = cont.querySelector("#tw-zona");
  const pintarTwilio = async () => {
    let c;
    try { c = await get("/api/twilio/estado-configuracion"); } catch { twZona.innerHTML = '<p class="texto-tenue">Reinicie el sistema para habilitar esta opción.</p>'; return; }
    if (c.faltan.length) {
      twZona.innerHTML = `<div class="banner alerta">${icono("alerta")}<div>Para llamar a un número real falta configurar en <strong>backend\\.env</strong>:<ul>${c.faltan.map((f) => `<li>${esc(f)}</li>`).join("")}</ul>Siga la guía <strong>docs\\TWILIO.md</strong> (cuenta de prueba gratuita).</div></div>`;
      return;
    }
    twZona.innerHTML = `<div class="form-rejilla"><div class="campo"><label for="tw-num">Número autorizado</label>
      <select id="tw-num">${c.numeros_autorizados.map((n) => `<option value="${n.id}">${esc(n.telefono)} · ${esc(n.descripcion)}</option>`).join("") || '<option value="">Ninguno</option>'}</select>
      <small>Escriba el número completo abajo (por seguridad la lista lo muestra enmascarado).</small></div>
      <div class="campo"><label for="tw-tel">Número a llamar (8 dígitos)</label><input id="tw-tel" maxlength="20" placeholder="5555-1234"></div></div><br>
      ${boton("Llamar ahora", { ico: "telefono", clase: "btn-primario", datos: "data-tw-llamar" })} <span id="tw-estado" class="texto-tenue"></span>
      ${c.numeros_autorizados.length ? "" : '<p class="texto-tenue">Primero autorice su número en Extensiones SIP › Números autorizados.</p>'}`;
    twZona.querySelector("[data-tw-llamar]").addEventListener("click", async (ev) => {
      const id_deuda = Number(cont.querySelector("#p-deuda").value);
      if (!id_deuda) return toast("Seleccione arriba un cliente y una deuda.", "error");
      ev.target.disabled = true;
      const est = twZona.querySelector("#tw-estado");
      try {
        const r = await post("/api/twilio/llamar", { id_agente: Number(cont.querySelector("#p-agente").value), id_deuda, telefono: twZona.querySelector("#tw-tel").value });
        est.textContent = "Llamando… conteste su teléfono.";
        chat.innerHTML = "";
        cont.querySelector("#p-chat-tarjeta").hidden = false;
        cont.querySelector("#p-modo").innerHTML = modo("TELEFONIA", "PRUEBA");
        cont.querySelector("#p-texto").hidden = true;
        cont.querySelector("#p-voz").hidden = true;
        let vistos = 0;
        const seguir = setInterval(async () => {
          try {
            const d = await get(`/api/llamadas/${r.id_llamada}`);
            d.turnos.slice(vistos).forEach((t) => agregar(t.rol, t.texto));
            vistos = d.turnos.length;
            est.textContent = `Estado: ${d.estado_tecnico.replace("_", " ")}${d.resultado_contacto ? " · " + d.resultado_contacto.replace("_", " ") : ""}`;
            if (d.estado_tecnico !== "EN_CURSO") { clearInterval(seguir); ev.target.disabled = false; historial.recargar(); }
          } catch { clearInterval(seguir); ev.target.disabled = false; }
        }, 2000);
      } catch (e) { errorToast(e); est.textContent = e.message; ev.target.disabled = false; }
    });
  };
  pintarTwilio();

  // ---- llamada real a una extensión interna (Zoiper registrado en FreeSWITCH)
  const fsZona = cont.querySelector("#fs-zona");
  const seguirLlamada = (id_llamada, est, btn) => {
    chat.innerHTML = "";
    cont.querySelector("#p-chat-tarjeta").hidden = false;
    cont.querySelector("#p-modo").innerHTML = modo("TELEFONIA", "PRUEBA");
    cont.querySelector("#p-texto").hidden = true;
    cont.querySelector("#p-voz").hidden = true;
    let vistos = 0;
    const seguir = setInterval(async () => {
      try {
        const d = await get(`/api/llamadas/${id_llamada}`);
        d.turnos.slice(vistos).forEach((t) => agregar(t.rol, t.texto));
        vistos = d.turnos.length;
        est.textContent = `Estado: ${d.estado_tecnico.replace("_", " ")}${d.resultado_contacto ? " · " + d.resultado_contacto.replace("_", " ") : ""}${d.motivo_fallo ? " · " + d.motivo_fallo : ""}`;
        if (d.estado_tecnico !== "EN_CURSO") { clearInterval(seguir); btn.disabled = false; historial.recargar(); }
      } catch { clearInterval(seguir); btn.disabled = false; }
    }, 2000);
  };
  const pintarFreeswitch = async () => {
    let c;
    try { c = await get("/api/telefonia/extensiones-internas"); } catch { fsZona.innerHTML = '<p class="texto-tenue">Reinicie el sistema para habilitar esta opción.</p>'; return; }
    if (c.faltan.length) {
      fsZona.innerHTML = `<div class="banner alerta">${icono("alerta")}<div>Para llamar a Zoiper falta configurar en <strong>backend\\.env</strong>:<ul>${c.faltan.map((f) => `<li>${esc(f)}</li>`).join("")}</ul>Siga la guía <strong>docs\\ZOIPER_FREESWITCH.md</strong>.</div></div>`;
      return;
    }
    if (!c.extensiones.length) {
      fsZona.innerHTML = '<p class="texto-tenue">Registre la extensión de Zoiper (por ejemplo 1000) en Extensiones SIP, <strong>sin troncal</strong>, en la planta de la máquina virtual.</p>';
      return;
    }
    fsZona.innerHTML = `<div class="form-rejilla"><div class="campo"><label for="fs-ext">Extensión Zoiper</label>
      <select id="fs-ext">${c.extensiones.map((e) => `<option value="${e.id_extension}">${esc(e.numero)} · ${esc(e.planta)} (${esc(e.ip)}) · ${esc(e.estado_planta)}</option>`).join("")}</select>
      <small>Zoiper debe estar abierto y en verde (registrado) en esa extensión.</small></div></div><br>
      ${boton("Llamar a la extensión", { ico: "telefono", clase: "btn-primario", datos: "data-fs-llamar" })} <span id="fs-estado" class="texto-tenue"></span>`;
    fsZona.querySelector("[data-fs-llamar]").addEventListener("click", async (ev) => {
      const id_deuda = Number(cont.querySelector("#p-deuda").value);
      if (!id_deuda) return toast("Seleccione arriba un cliente y una deuda.", "error");
      ev.target.disabled = true;
      const est = fsZona.querySelector("#fs-estado");
      try {
        const r = await post("/api/telefonia/llamar-extension", { id_agente: Number(cont.querySelector("#p-agente").value), id_deuda,
          id_extension: Number(fsZona.querySelector("#fs-ext").value) });
        est.textContent = "Llamando… conteste en Zoiper.";
        seguirLlamada(r.id_llamada, est, ev.target);
      } catch (e) { errorToast(e); est.textContent = e.message; ev.target.disabled = false; }
    });
  };
  pintarFreeswitch();

  // ---- velocidad de la voz del agente
  const selVel = cont.querySelector("#p-velocidad"), txtVel = cont.querySelector("#p-vel-valor");
  const aplicarVelocidad = (v) => {
    const vel = guardarVelocidad(v);
    selVel.value = vel;
    txtVel.textContent = formatoVelocidad(vel);
    if (audioEnCurso) audioEnCurso.playbackRate = vel;   // cambia la voz que se está reproduciendo
    cont.querySelectorAll("#tts-res audio").forEach((a) => { a.playbackRate = vel; });
  };
  selVel.addEventListener("input", () => aplicarVelocidad(selVel.value));
  cont.querySelector("[data-vel-normal]").addEventListener("click", () => aplicarVelocidad(1));
  const agenteElegido = () => agentes.find((a) => String(a.id_agente) === cont.querySelector("#p-agente").value);
  cont.querySelector("#p-agente").addEventListener("change", () => aplicarVelocidad(agenteElegido()?.velocidad_voz ?? 1));
  cont.querySelector("[data-vel-guardar]")?.addEventListener("click", async () => {
    const ag = agenteElegido();
    if (!ag) return;
    try {
      Object.assign(ag, await put(`/api/agentes/${ag.id_agente}/velocidad`, { velocidad_voz: leerVelocidad() }));
      toast(`Velocidad ${formatoVelocidad(leerVelocidad())} guardada en ${ag.nombre}.`, "exito");
    } catch (e) { errorToast(e); }
  });

  // ---- selector de voz del navegador
  const selVoz = cont.querySelector("#p-voz-nav");
  const llenarVoces = () => {
    if (!selVoz) return;
    const voces = vocesEspanol();
    const guardada = leerPreferencia();
    selVoz.innerHTML = voces.length ? voces.map((v) => `<option value="${esc(v.name)}" ${v.name === (guardada || vozEspanol()?.name) ? "selected" : ""}>${esc(v.name)} (${esc(v.lang)})</option>`).join("")
      : "<option>Sin voces en español instaladas</option>";
  };
  llenarVoces();
  if ("speechSynthesis" in window) window.speechSynthesis.addEventListener("voiceschanged", llenarVoces);
  selVoz?.addEventListener("change", () => guardarPreferencia(selVoz.value));
  cont.querySelector("[data-muestra]")?.addEventListener("click", () => hablarNavegador("Buen día, le saluda Sofía, de Financiera Progreso. ¿Hablo con el titular de la cuenta?"));

  if (!window.isSecureContext) {
    cont.querySelector("#p-aviso").innerHTML = `<div class="banner peligro">${icono("alerta")}<div>El navegador bloquea el micrófono fuera de un contexto seguro. Abra el sistema en <strong>http://127.0.0.1:8000</strong> o <strong>http://localhost:8000</strong>.</div></div>`;
  }
  const historial = tablaPaginada({
    contenedor: cont.querySelector("#p-historial"), titulo: "Historial de pruebas", porPagina: 8,
    cargar: (p) => get("/api/pruebas", p),
    columnas: [
      { titulo: "Fecha", html: (p) => fecha(p.fecha) }, { titulo: "Tipo", html: (p) => esc(p.tipo) }, { titulo: "Resultado", html: (p) => esc(p.resultado) },
      { titulo: "Llamada", html: (p) => esc(p.id_llamada ?? "—") }, { titulo: "Latencia", clase: "num", html: (p) => (p.latencia_ms != null ? `${p.latencia_ms} ms` : "—") },
      { titulo: "Confianza STT", clase: "num", html: (p) => (p.calidad_voz != null ? `${p.calidad_voz} %` : "—") },
    ],
  });

  // ---------------------------------------------------------------- búsqueda de cliente
  let temporizador;
  cont.querySelector("#p-buscar").addEventListener("input", (e) => {
    clearTimeout(temporizador);
    temporizador = setTimeout(async () => {
      try {
        const r = await get("/api/clientes", { q: e.target.value, por_pagina: 25 });
        const opciones = r.items.flatMap((c) => c.deudas.filter((d) => d.estado === "ACTIVA").map((d) =>
          `<option value="${d.id_deuda}">${esc(c.nombre)} · ${esc(d.referencia)} · ${dinero(d.saldo, d.moneda)} · ${d.dias_mora} días</option>`));
        cont.querySelector("#p-deuda").innerHTML = opciones.join("") || "<option value=''>Sin resultados</option>";
      } catch (err) { errorToast(err); }
    }, 300);
  });

  // ---------------------------------------------------------------- conversación
  const s = { id: null, canal: null, finalizada: true, voz: null };
  const chat = cont.querySelector("#p-chat");
  const agregar = (rol, texto, extra = "") => {
    const b = document.createElement("div");
    b.className = `burbuja ${rol.toLowerCase()}`;
    b.innerHTML = `<small>${esc(rol)}${extra ? " · " + esc(extra) : ""}</small>${esc(texto)}`;
    chat.appendChild(b);
    chat.scrollTop = chat.scrollHeight;
  };
  const pintarEstado = (r) => {
    cont.querySelector("#p-estado").innerHTML = `<dl class="lista-def">
      <dt>Llamada</dt><dd>#${s.id}</dd><dt>Canal</dt><dd>${modo(s.canal, "PRUEBA")}</dd>
      <dt>Estado técnico</dt><dd>${chip(r.estado_tecnico || "EN_CURSO")}</dd><dt>Identidad verificada</dt><dd>${r.identidad_verificada ? chip("ACTIVA", "Sí") : chip("PENDIENTE", "No")}</dd>
      <dt>Resultado de cobranza</dt><dd>${chip(r.resultado_cobranza)}</dd><dt>Bloqueos de guardrails</dt><dd>${r.bloqueos_guardrail ?? 0}</dd>
      ${r.latencia_stt_ms != null ? `<dt>Latencia STT / TTS</dt><dd>${r.latencia_stt_ms} ms / ${r.latencia_tts_ms ?? "—"} ms</dd>` : ""}
    </dl>`;
  };
  const procesarRespuesta = (r) => {
    (r.eventos || []).forEach((e) => {
      if (e.tipo === "PROMESA_REGISTRADA") toast(`Promesa registrada (#${e.id_promesa}).`, "exito");
      if (e.tipo === "GUARDRAIL_BLOQUEO") agregar("SISTEMA", "Respuesta bloqueada por guardrails: " + e.motivos.join("; "));
      if (e.tipo === "PROMESA_PROPUESTA") agregar("SISTEMA", `Promesa propuesta: ${e.monto} para el ${e.fecha}. Requiere confirmación explícita.`);
      if (e.tipo === "ALERTA_ENTRADA") agregar("SISTEMA", "Alerta de entrada: " + e.detalle);
      if (e.tipo === "FALLA_PROVEEDOR") agregar("SISTEMA", `El proveedor de IA falló (${e.codigo}). Se usó un mensaje de contingencia y no se registró ninguna acción financiera.`);
    });
    if (r.respuesta) agregar("AGENTE", r.respuesta);
    pintarEstado(r);
    if (r.finalizada) terminar("La conversación finalizó.");
  };
  const terminar = (msg) => {
    s.finalizada = true;
    s.voz?.liberar();
    s.voz = null;
    cont.querySelector("#p-texto").hidden = true;
    cont.querySelector("#p-voz").hidden = true;
    agregar("SISTEMA", msg + " Se generó un trabajo de evaluación QA si hubo intervención del cliente.");
    historial.recargar();
  };

  cont.querySelector("[data-iniciar]").addEventListener("click", async (ev) => {
    const id_deuda = Number(cont.querySelector("#p-deuda").value);
    if (!id_deuda) return toast("Seleccione un cliente ficticio y una deuda.", "error");
    if (!s.finalizada && s.id) await post(`/api/conversaciones/${s.id}/finalizar`).catch(() => {});
    s.voz?.liberar();
    ev.target.disabled = true;
    try {
      const canal = cont.querySelector("#p-canal").value;
      window.speechSynthesis?.cancel();
      if (canal === "VOZ_NAVEGADOR") s.voz = cfgVoz.deepgram ? await crearVoz(cont) : crearVozNavegador(cont); // pide micrófono antes de crear la conversación
      const r = await post("/api/conversaciones", { id_agente: Number(cont.querySelector("#p-agente").value), id_deuda, canal });
      Object.assign(s, { id: r.id_llamada, canal, finalizada: false });
      chat.innerHTML = "";
      cont.querySelector("#p-chat-tarjeta").hidden = false;
      cont.querySelector("#p-modo").innerHTML = `${modo(canal, "PRUEBA")} <span class="texto-tenue">Agente ${esc(r.agente)} · voz ${esc(r.voz)}</span>`;
      cont.querySelector("#p-texto").hidden = canal !== "TEXTO";
      cont.querySelector("#p-voz").hidden = canal !== "VOZ_NAVEGADOR";
      r.turnos.forEach((t) => agregar(t.rol, t.texto));
      pintarEstado({ estado_tecnico: "EN_CURSO" });
      if (canal === "VOZ_NAVEGADOR") {
        s.voz.configurar({ id: s.id, alRespuesta: procesarRespuesta, alTranscripcion: (t, c) => agregar("CLIENTE", t, c != null ? `STT ${Math.round(c * 100)}%` : ""),
          manosLibres: () => cont.querySelector("#p-manos").checked, activa: () => !s.finalizada });
        cont.querySelector("#p-modo").innerHTML += cfgVoz.deepgram ? "" : ' <span class="chip naranja">Voz del navegador</span>';
        // El saludo inicial se sintetiza también con Deepgram
        await s.voz.decir(r.turnos[0].texto, r.voz);
      } else {
        if (cont.querySelector("#p-leer").checked) hablarNavegador(r.turnos[0].texto);
        cont.querySelector("#p-mensaje").focus();
      }
    } catch (e) {
      s.voz?.liberar();
      s.voz = null;
      errorToast(e);
      if (e.name) cont.querySelector("#p-aviso").innerHTML = `<div class="banner peligro">${icono("alerta")}<div>${esc(e.message)}</div></div>`;
    } finally { ev.target.disabled = false; }
  });

  const enviar = async () => {
    const input = cont.querySelector("#p-mensaje");
    const texto = input.value.trim();
    if (!texto || s.finalizada) return;
    input.value = "";
    agregar("CLIENTE", texto);
    input.disabled = true;
    try {
      const r = await post(`/api/conversaciones/${s.id}/mensajes`, { texto });
      procesarRespuesta(r);
      if (cont.querySelector("#p-leer").checked && r.respuesta) hablarNavegador(r.respuesta);
    } catch (e) { errorToast(e); } finally { input.disabled = false; input.focus(); }
  };
  cont.querySelector("[data-enviar]").addEventListener("click", enviar);
  cont.querySelector("#p-mensaje").addEventListener("keydown", (e) => { if (e.key === "Enter") enviar(); });
  cont.querySelector("[data-finalizar]").addEventListener("click", async () => {
    if (!s.id || s.finalizada) return;
    try { await post(`/api/conversaciones/${s.id}/finalizar`); terminar("Conversación finalizada por el usuario."); } catch (e) { errorToast(e); }
  });
  cont.querySelector("[data-hablar]").addEventListener("click", () => s.voz?.alternar());

  cont.querySelector("[data-tts]").addEventListener("click", async (ev) => {
    const zona = cont.querySelector("#tts-res");
    if (!cfgVoz.deepgram) {
      if (!vozNavegadorDisponible) { zona.innerHTML = '<div class="estado-error">Este navegador no tiene síntesis de voz. Use Chrome o Edge.</div>'; return; }
      const t0 = performance.now();
      hablarNavegador(cont.querySelector("#tts-texto").value, () => {
        zona.innerHTML = `<p>Reproducido con la <strong>voz del navegador</strong> (Deepgram no configurado). Duración: ${Math.round(performance.now() - t0)} ms.</p>`;
      });
      zona.innerHTML = '<div class="estado-carga cargando">Hablando con la voz del navegador</div>';
      return;
    }
    ev.target.disabled = true;
    zona.innerHTML = '<div class="estado-carga cargando">Sintetizando con Deepgram</div>';
    try {
      const r = await post("/api/voz/tts-prueba", { texto: cont.querySelector("#tts-texto").value, voz: cont.querySelector("#tts-voz").value });
      zona.innerHTML = `<p>Latencia de síntesis: <strong>${r.latencia_ms} ms</strong></p>`;
      const a = document.createElement("audio");
      a.controls = true;
      a.src = URL.createObjectURL(b64ABlob(r.audio, r.mime));
      ajustarVelocidad(a);
      zona.appendChild(a);
      a.play();
      historial.recargar();
    } catch (e) { zona.innerHTML = `<div class="estado-error">${esc(e.message)}</div>`; } finally { ev.target.disabled = false; }
  });
}

// ---------------------------------------------------------------- velocidad de la voz del agente
const VEL_MIN = 0.7, VEL_MAX = 1.4;
let audioEnCurso = null;   // audio de Deepgram que suena ahora (para cambiar la velocidad en vivo)
let velocidadActual = 1;   // se toma del agente elegido; el control la cambia en vivo
function leerVelocidad() { return velocidadActual; }
function guardarVelocidad(v) {
  velocidadActual = Math.min(VEL_MAX, Math.max(VEL_MIN, parseFloat(v) || 1));
  return velocidadActual;
}
function formatoVelocidad(v) {
  const t = v < 0.9 ? "lenta" : v > 1.1 ? "rápida" : "normal";
  return `${Number(v).toFixed(2)}× (${t})`;
}
function ajustarVelocidad(audio) {
  audio.preservesPitch = true;   // cambia la velocidad sin volver la voz aguda o grave
  audio.playbackRate = leerVelocidad();
}

// ---------------------------------------------------------------- voz del navegador (Web Speech API, gratis)
function leerPreferencia() { try { return localStorage.getItem("cobros_voz_agente"); } catch { return null; } }
function guardarPreferencia(v) { try { localStorage.setItem("cobros_voz_agente", v); } catch { /* sin almacenamiento */ } }

function vocesEspanol() {
  const voces = (window.speechSynthesis?.getVoices() || []).filter((x) => x.lang?.toLowerCase().startsWith("es"));
  const puntaje = (v) => (/natural|neural/i.test(v.name) ? 0 : /online/i.test(v.name) ? 1 : /google/i.test(v.name) ? 2 : 3) * 10
    + (["es-GT", "es-MX", "es-US", "es-419"].includes(v.lang) ? 0 : 5);
  return voces.sort((a, b) => puntaje(a) - puntaje(b));
}

function vozEspanol() {
  const voces = vocesEspanol();
  const guardada = leerPreferencia();
  return voces.find((v) => v.name === guardada) || voces[0] || null;
}

// Igual que el backend: sin comas entre palabras (cada coma es una pausa larga); se conservan las de las cifras.
function textoParaVoz(texto) {
  return String(texto || "").replace(/(?<!\d)\s*[,;]\s*|\s*[,;]\s*(?!\d)/g, " ").replace(/\s{2,}/g, " ").trim();
}

export function hablarNavegador(texto, alTerminar) {
  texto = textoParaVoz(texto);
  if (!("speechSynthesis" in window) || !texto) { alTerminar?.(); return; }
  window.speechSynthesis.cancel();
  const v = vozEspanol();
  // Se habla frase por frase: las pausas entre oraciones suenan más naturales.
  const frases = texto.match(/[^.!?¿¡]*[¿¡]?[^.!?]*[.!?]+|\S[^.!?]*$/g)?.map((f) => f.trim()).filter(Boolean) || [texto];
  frases.forEach((f, i) => {
    const u = new SpeechSynthesisUtterance(f);
    if (v) u.voice = v;
    u.lang = v?.lang || "es-MX";
    u.rate = (/natural|neural|online/i.test(v?.name || "") ? 1.0 : 0.95) * leerVelocidad();
    u.pitch = 1.0;
    if (i === frases.length - 1) { u.onend = () => alTerminar?.(); u.onerror = () => alTerminar?.(); }
    window.speechSynthesis.speak(u);
  });
}

function crearVozNavegador(cont) {
  const Reconocimiento = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!("speechSynthesis" in window)) throw new Error("Este navegador no tiene síntesis de voz. Use Chrome o Edge.");
  if (!Reconocimiento) throw new Error("Este navegador no reconoce voz. Use Google Chrome o Microsoft Edge (o el canal de texto).");
  const estadoTxt = cont.querySelector("#p-voz-estado"), btn = cont.querySelector("[data-hablar]"), medidor = cont.querySelector("#p-nivel");
  let cfg = {}, rec = null, ocupado = false, silencios = 0, vivo = true;
  const estado = (t) => { estadoTxt.textContent = t; };

  function decir(texto) {
    return new Promise((resolver) => {
      estado("El agente está hablando… (pulse Hablar para interrumpir)");
      medidor.style.width = "100%";
      hablarNavegador(texto, () => {
        medidor.style.width = "0";
        resolver();
        if (vivo && cfg.activa?.() && cfg.manosLibres?.()) escuchar(); else estado("Listo. Pulse Hablar para responder.");
      });
    });
  }

  function escuchar() {
    if (!vivo || rec || ocupado || !cfg.activa?.()) return;
    window.speechSynthesis.cancel();
    rec = new Reconocimiento();
    rec.lang = "es-MX";
    rec.interimResults = false;
    rec.continuous = false;
    rec.maxAlternatives = 1;
    let recibido = false;
    btn.classList.add("grabando");
    estado("Escuchando… hable ahora.");
    rec.onresult = (e) => {
      recibido = true;
      const alt = e.results[0][0];
      enviar(alt.transcript, alt.confidence);
    };
    rec.onerror = (e) => {
      const motivos = { "not-allowed": "Permiso de micrófono denegado. Habilítelo en el candado de la barra de direcciones.",
        "network": "El reconocimiento de voz del navegador necesita Internet.", "audio-capture": "No se encontró un micrófono." };
      if (e.error !== "no-speech" && e.error !== "aborted") estado(motivos[e.error] || `Error de reconocimiento (${e.error}).`);
    };
    rec.onend = () => {
      btn.classList.remove("grabando");
      rec = null;
      if (!recibido && vivo && !ocupado) {
        silencios += 1;
        if (silencios >= 2) { estado("No se detectó voz. Pulse Hablar para intentarlo de nuevo."); silencios = 0; return; }
        if (cfg.manosLibres?.()) decir("¿Me escucha? Por favor, responda después del mensaje.");
      }
    };
    try { rec.start(); } catch { rec = null; btn.classList.remove("grabando"); }
  }

  async function enviar(texto, confianza) {
    silencios = 0;
    ocupado = true;
    estado("Procesando su respuesta…");
    cfg.alTranscripcion(texto, confianza || null);
    try {
      const r = await post(`/api/conversaciones/${cfg.id}/mensajes`, { texto });
      cfg.alRespuesta(r);
      ocupado = false;
      if (r.respuesta) await decir(r.respuesta);
    } catch (e) {
      ocupado = false;
      estado(e.message);
      errorToast(e);
    }
  }

  return {
    configurar(c) { cfg = { ...cfg, ...c }; },
    decir: (texto) => decir(texto),
    alternar() { if (rec) { rec.stop(); } else { window.speechSynthesis.cancel(); escuchar(); } },
    // No se cancela la voz en curso: así se escucha la despedida final del agente.
    liberar() { vivo = false; try { rec?.abort(); } catch { /* ya detenido */ } btn.classList.remove("grabando"); },
  };
}

function b64ABlob(b64, mime) {
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return new Blob([bytes], { type: mime || "audio/mpeg" });
}

// ---------------------------------------------------------------- motor de voz del navegador
async function crearVoz(cont) {
  if (!navigator.mediaDevices?.getUserMedia) throw new Error("Este navegador no permite capturar audio. Use Chrome o Edge actualizados.");
  if (!window.isSecureContext) throw new Error("El micrófono requiere http://localhost o http://127.0.0.1 (contexto seguro).");
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
  } catch (e) {
    const motivos = { NotAllowedError: "Permiso de micrófono denegado. Habilítelo en el candado de la barra de direcciones.",
      NotFoundError: "No se encontró un micrófono.", NotReadableError: "El micrófono está siendo usado por otra aplicación." };
    throw new Error(motivos[e.name] || `No se pudo acceder al micrófono (${e.name}).`);
  }
  const ac = new AudioContext();
  const analizador = ac.createAnalyser();
  analizador.fftSize = 1024;
  ac.createMediaStreamSource(stream).connect(analizador);
  const buf = new Float32Array(analizador.fftSize);
  const nivel = () => { analizador.getFloatTimeDomainData(buf); let s = 0; for (const v of buf) s += v * v; return Math.sqrt(s / buf.length); };
  const mime = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus"].find((m) => MediaRecorder.isTypeSupported(m)) || "";
  const medidor = cont.querySelector("#p-nivel"), estadoTxt = cont.querySelector("#p-voz-estado"), btn = cont.querySelector("[data-hablar]");
  let cfg = {}, grabador = null, reproductor = null, raf = null, ocupado = false, silencios = 0, vivo = true;

  const bucle = () => { if (!vivo) return; medidor.style.width = `${Math.min(100, nivel() * 600)}%`; raf = requestAnimationFrame(bucle); };
  bucle();
  const estado = (t) => { estadoTxt.textContent = t; };

  function escuchar() {
    if (!vivo || grabador || ocupado || !cfg.activa()) return;
    const partes = [];
    grabador = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
    grabador.ondataavailable = (e) => e.data.size && partes.push(e.data);
    const inicio = performance.now();
    let habloEn = null, ultimaVoz = 0;
    btn.classList.add("grabando");
    estado("Escuchando… hable ahora.");
    const vigilar = setInterval(() => {
      const ahora = performance.now(), n = nivel();
      if (n > UMBRAL_VOZ) { habloEn ??= ahora; ultimaVoz = ahora; }
      const finTurno = habloEn && ahora - ultimaVoz > SILENCIO_FIN_MS;
      const sinVoz = !habloEn && ahora - inicio > ESPERA_INICIO_MS;
      if (finTurno || sinVoz || ahora - inicio > MAX_TURNO_MS) { clearInterval(vigilar); detener(!!habloEn); }
    }, 60);
    const detener = (conVoz) => {
      grabador.onstop = () => {
        const tipoGrabado = grabador.mimeType;
        btn.classList.remove("grabando");
        grabador = null;
        if (!conVoz) {
          silencios += 1;
          estado(silencios >= 2 ? "No se detectó voz. Pulse Hablar para intentarlo de nuevo." : "Silencio detectado.");
          if (silencios < 2 && cfg.manosLibres()) decir("¿Me escucha? Por favor, responda después del mensaje.", null).catch(() => {});
          return;
        }
        silencios = 0;
        enviar(new Blob(partes, { type: tipoGrabado || mime || "audio/webm" }));
      };
      grabador.stop();
    };
    grabador._detener = () => { clearInterval(vigilar); detener(true); };
    grabador.start(250);
  }

  async function enviar(blob) {
    ocupado = true;
    estado("Transcribiendo con Deepgram y consultando al agente…");
    try {
      const fd = new FormData();
      fd.append("audio", blob, "turno.webm");
      const r = await api(`/api/conversaciones/${cfg.id}/voz`, { metodo: "POST", formulario: fd });
      if (r.silencio) { estado("Deepgram no reconoció palabras. Intente de nuevo."); ocupado = false; if (cfg.manosLibres()) escuchar(); return; }
      cfg.alTranscripcion(r.transcripcion, r.confianza_stt);
      cfg.alRespuesta(r);
      if (r.error_tts) toast(r.error_tts, "error");
      ocupado = false;
      if (r.audio && !r.finalizada) await reproducir(r.audio, r.mime);
      else if (r.audio) await reproducir(r.audio, r.mime, false);
    } catch (e) {
      ocupado = false;
      estado(e.message);
      errorToast(e);
    }
  }

  function reproducir(b64, mimeAudio, continuar = true) {
    return new Promise((resolver) => {
      cancelarAudio();
      reproductor = new Audio(URL.createObjectURL(b64ABlob(b64, mimeAudio)));
      ajustarVelocidad(reproductor);
      audioEnCurso = reproductor;
      estado("El agente está hablando… (puede interrumpir hablando)");
      let ventanaVoz = 0;
      const barge = setInterval(() => {   // detección de interrupción del interlocutor
        if (!cfg.manosLibres() || !continuar) return;
        if (nivel() > UMBRAL_VOZ * 1.8) { ventanaVoz += 60; } else ventanaVoz = 0;
        if (ventanaVoz >= 240) { clearInterval(barge); cancelarAudio(); estado("Interrupción detectada."); resolver(); escuchar(); }
      }, 60);
      reproductor.onended = () => { clearInterval(barge); URL.revokeObjectURL(reproductor.src); reproductor = null; resolver(); if (continuar && cfg.manosLibres()) escuchar(); else estado("Listo."); };
      reproductor.onerror = () => { clearInterval(barge); resolver(); estado("No se pudo reproducir el audio."); };
      reproductor.play().catch(() => { clearInterval(barge); resolver(); estado("Pulse Hablar para continuar (reproducción automática bloqueada)."); });
    });
  }
  function cancelarAudio() { if (reproductor) { reproductor.pause(); URL.revokeObjectURL(reproductor.src); reproductor = null; } audioEnCurso = null; }

  async function decir(texto, voz) {
    try {
      const r = await post("/api/voz/tts-prueba", { texto, voz: voz || cfg.voz || "aura-2-diana-es" });
      if (voz) cfg.voz = voz;
      await reproducir(r.audio, r.mime);
    } catch (e) {
      estado(`Deepgram TTS no disponible: ${e.message}`);
      if (cfg.manosLibres()) escuchar();
    }
  }

  return {
    configurar(c) { cfg = { ...cfg, ...c }; },
    decir,
    alternar() { if (grabador) grabador._detener(); else { cancelarAudio(); escuchar(); } },
    liberar() {   // liberación de recursos: micrófono, audio y contexto
      vivo = false;
      cancelAnimationFrame(raf);
      try { grabador?.stop(); } catch { /* ya detenido */ }
      cancelarAudio();
      stream.getTracks().forEach((t) => t.stop());
      ac.close().catch(() => {});
      btn.classList.remove("grabando");
      medidor.style.width = "0";
    },
  };
}
