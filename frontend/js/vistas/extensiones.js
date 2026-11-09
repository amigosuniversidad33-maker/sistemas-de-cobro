// Módulo Extensiones SIP: troncales, extensiones, canales concurrentes y números autorizados para el piloto.
import { del, get, post } from "../api.js";
import { abrirModal, boton, chip, confirmar, errorToast, esc, fecha, formulario, leerFormulario, opcionesDe, tarjeta, toast } from "../ui.js";
import { bannerEstado } from "./plantas.js";

export async function render(cont, ctx) {
  const [estado, plantas, troncales, extensiones, canales, numeros] = await Promise.all([
    get("/api/telefonia/estado"), get("/api/telefonia/plantas"), get("/api/telefonia/troncales"), get("/api/telefonia/extensiones"),
    get("/api/telefonia/canales"), get("/api/telefonia/numeros-autorizados")]);
  const g = ctx.tiene("telefonia.gestionar");
  const planta = (id) => plantas.find((p) => p.id_planta === id)?.nombre || "—";
  cont.innerHTML = `
    ${bannerEstado(estado)}
    <div class="rejilla rejilla-2">
      ${tarjeta("Troncales SIP salientes", `<div class="tabla-envoltura"><table><thead><tr><th>Troncal</th><th>Gateway FreeSWITCH</th><th>Planta</th><th>Máx. canales</th><th>Estado</th><th></th></tr></thead><tbody>
        ${troncales.map((t) => `<tr><td>${esc(t.nombre)}<br><small class="texto-tenue">${esc(t.proveedor || "")}</small></td><td class="mono">${esc(t.gateway)}</td><td>${esc(planta(t.id_planta))}</td><td class="num">${t.max_canales}</td>
          <td>${chip(t.activa ? "ACTIVA" : "INACTIVO")}</td><td>${g ? boton(t.activa ? "Desactivar" : "Activar", { chico: true, datos: `data-alt-troncal="${t.id_troncal}"` }) : ""}</td></tr>`).join("") || '<tr><td colspan="6" class="texto-tenue">Sin troncales. La telefonía queda bloqueada.</td></tr>'}</tbody></table></div>
        <p class="texto-tenue">El nombre del gateway debe coincidir con el definido en sofia (sip_profiles/external). El usuario y la contraseña SIP se configuran en FreeSWITCH, no aquí.</p>`,
        { acciones: g ? boton("Nueva troncal", { ico: "mas", datos: "data-troncal" }) : "" })}
      ${tarjeta("Números autorizados para pruebas", `<div class="tabla-envoltura"><table><thead><tr><th>Teléfono</th><th>Descripción</th><th></th></tr></thead><tbody>
        ${numeros.map((n) => `<tr><td class="mono">${esc(n.telefono)}</td><td>${esc(n.descripcion)}</td><td>${g ? boton("Quitar", { chico: true, datos: `data-quitar-num="${n.id}"` }) : ""}</td></tr>`).join("") || '<tr><td colspan="3" class="texto-tenue">Ninguno. No se marcará a ningún número.</td></tr>'}</tbody></table></div>
        <p class="texto-tenue">Durante el desarrollo solo se marca a números de prueba autorizados. No se realizan campañas a clientes reales.</p>`,
        { acciones: g ? boton("Autorizar número", { ico: "mas", datos: "data-numero" }) : "" })}
    </div>
    ${tarjeta("Extensiones SIP", `<div class="tabla-envoltura"><table><thead><tr><th>Extensión</th><th>Planta</th><th>Troncal</th><th>Canales</th><th>Estado</th></tr></thead><tbody>
      ${extensiones.map((e) => `<tr><td class="mono">${esc(e.numero)}</td><td>${esc(e.planta)}</td><td>${esc(e.troncal || "—")}</td><td class="num">${e.canales_max}</td><td>${chip(e.activa ? "ACTIVA" : "INACTIVO")}</td></tr>`).join("") || '<tr><td colspan="5" class="texto-tenue">Sin extensiones.</td></tr>'}</tbody></table></div>`,
      { acciones: g ? boton("Nueva extensión", { ico: "mas", datos: "data-extension" }) : "" })}
    ${tarjeta("Canales concurrentes", `<div class="tabla-envoltura"><table><thead><tr><th>Canal</th><th>Extensión</th><th>Estado</th><th>Llamada</th><th>Ocupado desde</th><th></th></tr></thead><tbody>
      ${canales.map((c) => `<tr><td>#${c.id_canal}</td><td class="mono">${esc(c.extension)}</td><td>${chip(c.estado)}</td><td>${esc(c.id_llamada ?? "—")}</td><td>${fecha(c.ocupado_desde)}</td>
        <td>${g && c.estado === "OCUPADO" ? boton("Liberar", { chico: true, datos: `data-liberar="${c.id_canal}"` }) : ""}</td></tr>`).join("") || '<tr><td colspan="6" class="texto-tenue">Sin canales.</td></tr>'}</tbody></table></div>`,
      { descripcion: "Un canal se reserva al originar y se libera al colgar, ante errores o al reiniciar el worker.", acciones: g ? boton("Recuperar canales huérfanos", { ico: "recargar", datos: "data-recuperar" }) : "" })}`;

  const modal = (titulo, campos, ruta, valores = {}) => abrirModal({ titulo, contenido: formulario(campos, valores), botones: [{ texto: "Cancelar" }, { texto: "Guardar", clase: "btn-primario", accion: async (m) => { await post(ruta, leerFormulario(m, campos)); toast("Guardado.", "exito"); render(cont, ctx); } }] });
  const opPlantas = opcionesDe(plantas, "id_planta", "nombre");
  cont.querySelector("[data-troncal]")?.addEventListener("click", () => modal("Nueva troncal SIP", [
    { nombre: "id_planta", etiqueta: "Planta", tipo: "select", numerico: true, opciones: opPlantas },
    { nombre: "nombre", etiqueta: "Nombre", requerido: true, maxlength: 80 },
    { nombre: "gateway", etiqueta: "Nombre del gateway en FreeSWITCH", requerido: true, maxlength: 60, ayuda: "Solo letras, números, guion y guion bajo" },
    { nombre: "proveedor", etiqueta: "Proveedor", maxlength: 80 },
    { nombre: "max_canales", etiqueta: "Máx. canales", tipo: "number", valor: 1, min: 1, max: 500 },
    { nombre: "activa", etiqueta: "Activa", tipo: "checkbox", valor: true }], "/api/telefonia/troncales"));
  cont.querySelector("[data-extension]")?.addEventListener("click", () => modal("Nueva extensión SIP", [
    { nombre: "id_planta", etiqueta: "Planta", tipo: "select", numerico: true, opciones: opPlantas },
    { nombre: "id_troncal", etiqueta: "Troncal (Sin troncal = extensión interna, p. ej. Zoiper)", tipo: "select", numerico: true, opciones: opcionesDe(troncales, "id_troncal", "nombre", "Sin troncal") },
    { nombre: "numero", etiqueta: "Número de extensión", requerido: true, maxlength: 20 },
    { nombre: "canales_max", etiqueta: "Canales", tipo: "number", valor: 1, min: 1, max: 50, ayuda: "Se crea un registro de canal por cada uno." },
    { nombre: "activa", etiqueta: "Activa", tipo: "checkbox", valor: true }], "/api/telefonia/extensiones"));
  cont.querySelector("[data-numero]")?.addEventListener("click", () => modal("Autorizar número de prueba", [
    { nombre: "telefono", etiqueta: "Teléfono (Guatemala, 8 dígitos)", requerido: true, maxlength: 30 },
    { nombre: "descripcion", etiqueta: "Descripción (de quién es y quién autorizó)", requerido: true, ancho: true, maxlength: 160 }], "/api/telefonia/numeros-autorizados"));
  cont.querySelectorAll("[data-alt-troncal]").forEach((b) => b.addEventListener("click", async () => { try { await post(`/api/telefonia/troncales/${b.dataset.altTroncal}/alternar`); render(cont, ctx); } catch (e) { errorToast(e); } }));
  cont.querySelectorAll("[data-quitar-num]").forEach((b) => b.addEventListener("click", async () => { try { await del(`/api/telefonia/numeros-autorizados/${b.dataset.quitarNum}`); render(cont, ctx); } catch (e) { errorToast(e); } }));
  cont.querySelectorAll("[data-liberar]").forEach((b) => b.addEventListener("click", async () => {
    if (!(await confirmar("Liberar canal", "Solo libere un canal si está seguro de que no hay una llamada activa en FreeSWITCH."))) return;
    try { await post(`/api/telefonia/canales/${b.dataset.liberar}/liberar`); render(cont, ctx); } catch (e) { errorToast(e); }
  }));
  cont.querySelector("[data-recuperar]")?.addEventListener("click", async () => {
    try { const r = await post("/api/telefonia/canales/recuperar"); toast(`Canales liberados: ${r.canales_liberados} · llamadas recuperadas: ${r.llamadas_recuperadas}`, "exito"); render(cont, ctx); } catch (e) { errorToast(e); }
  });
}
