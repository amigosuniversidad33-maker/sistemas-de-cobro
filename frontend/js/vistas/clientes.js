// Clientes y deudas: importación CSV/Excel con reporte de errores, consulta enmascarada y exportación auditada.
import { api, descargar, get } from "../api.js";
import { icono } from "../iconos.js";
import { abrirModal, boton, chip, dinero, errorToast, esc, fecha, modo, num, tablaPaginada, tarjeta, toast } from "../ui.js";

export async function render(cont, ctx) {
  const importar = ctx.tiene("clientes.importar");
  cont.innerHTML = `
    ${importar ? tarjeta("Carga masiva de clientes y deudas", `
      <form id="f-import" class="acciones">
        <input type="file" id="archivo" name="archivo" accept=".csv,.xlsx" required aria-label="Archivo CSV o Excel">
        <button class="btn btn-primario" type="submit">${icono("subir")}Importar</button>
        ${boton("Descargar plantilla", { ico: "bajar", datos: "data-plantilla" })}
      </form>
      <p class="texto-tenue">Columnas obligatorias: documento, nombre, telefono, referencia, saldo, dias_mora (opcionales: telefono_alterno, moneda GTQ/USD). Máximo 5 MB y 5,000 filas.
        Se valida cada fila; las inválidas se reportan sin detener la carga. Un mismo archivo no se importa dos veces y los clientes existentes se actualizan por documento.</p>
      <div id="r-import"></div>`) : ""}
    <div id="z-clientes"></div><div id="z-lotes"></div>`;

  const clientes = tablaPaginada({
    contenedor: cont.querySelector("#z-clientes"),
    titulo: "Clientes",
    descripcion: "Documento y teléfono se muestran enmascarados.",
    acciones: ctx.tiene("clientes.exportar") ? boton("Exportar CSV", { ico: "bajar", datos: "data-exportar" }) : "",
    filtros: [{ nombre: "q", etiqueta: "Buscar" }, { nombre: "tramo", etiqueta: "Tramo", tipo: "select", opciones: [{ valor: "", texto: "Todos" }, { valor: "MORA_TEMPRANA", texto: "Mora Temprana (1–30)" }, { valor: "MORA_TARDIA", texto: "Mora Tardía (31–60)" }, { valor: "GESTION_ESPECIAL", texto: "Gestión especial (sin regla)" }, { valor: "AL_DIA", texto: "Al día" }] }],
    cargar: (p) => get("/api/clientes", p),
    columnas: [
      { titulo: "Cliente", html: (c) => `<button class="btn-icono" data-ver="${c.id_cliente}">${icono("ojo")}</button> ${esc(c.nombre)}` },
      { titulo: "Documento", html: (c) => `<span class="mono">${esc(c.documento)}</span>` },
      { titulo: "Teléfono", html: (c) => `<span class="mono">${esc(c.telefono || "—")}</span>` },
      { titulo: "Deudas", html: (c) => c.deudas.map((d) => `${esc(d.referencia)} · ${dinero(d.saldo, d.moneda)} · ${d.dias_mora} d · ${chip(d.tramo === "GESTION_ESPECIAL" ? "PENDIENTE" : "", (d.tramo || "").replaceAll("_", " "))}`).join("<br>") },
    ],
    alRenderizar: (z) => z.querySelectorAll("[data-ver]").forEach((b) => b.addEventListener("click", async () => {
      try {
        const c = await get(`/api/clientes/${b.dataset.ver}`);
        abrirModal({ titulo: c.nombre, contenido: `<dl class="lista-def"><dt>Documento</dt><dd class="mono">${esc(c.documento)}</dd><dt>Teléfono</dt><dd class="mono">${esc(c.telefono)}</dd></dl>
          <h3>Historial de llamadas</h3>${c.historial_llamadas.length ? `<ul>${c.historial_llamadas.map((l) => `<li>#${l.id_llamada} · ${fecha(l.inicio)} · ${modo(l.canal)} ${chip(l.estado_tecnico)} ${chip(l.resultado_contacto)} ${chip(l.resultado_cobranza)}</li>`).join("")}</ul>` : '<p class="texto-tenue">Sin llamadas.</p>'}
          <h3>Promesas</h3>${c.promesas.length ? `<ul>${c.promesas.map((p) => `<li>${dinero(p.monto, p.moneda)} para el ${esc(p.fecha_compromiso)} ${chip(p.estado)}</li>`).join("")}</ul>` : '<p class="texto-tenue">Sin promesas.</p>'}`, botones: [{ texto: "Cerrar" }] });
      } catch (e) { errorToast(e); }
    })),
  });
  const lotes = tablaPaginada({
    contenedor: cont.querySelector("#z-lotes"), titulo: "Lotes de importación", porPagina: 8,
    cargar: (p) => get("/api/lotes", p),
    columnas: [
      { titulo: "Lote", html: (l) => `#${l.id_lote}` }, { titulo: "Archivo", html: (l) => esc(l.archivo) }, { titulo: "Fecha", html: (l) => fecha(l.fecha_carga) },
      { titulo: "Nuevos", clase: "num", html: (l) => num(l.registros_validos) }, { titulo: "Actualizados", clase: "num", html: (l) => num(l.registros_actualizados) },
      { titulo: "Rechazados", clase: "num", html: (l) => num(l.registros_rechazados) },
      { titulo: "", html: (l) => (importar && l.registros_rechazados ? boton("Errores CSV", { chico: true, datos: `data-errores="${l.id_lote}"` }) : "") },
    ],
    alRenderizar: (z) => z.querySelectorAll("[data-errores]").forEach((b) => b.addEventListener("click", () => descargar(`/api/lotes/${b.dataset.errores}/errores.csv`).catch(errorToast))),
  });

  cont.querySelector("[data-plantilla]")?.addEventListener("click", () => descargar("/api/clientes/plantilla.csv").catch(errorToast));
  cont.querySelector("[data-exportar]")?.addEventListener("click", () => descargar("/api/clientes/exportar.csv").catch(errorToast));
  cont.querySelector("#f-import")?.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const archivo = cont.querySelector("#archivo").files[0];
    const zona = cont.querySelector("#r-import");
    if (!archivo) return toast("Seleccione un archivo.", "error");
    if (archivo.size > 5 * 1024 * 1024) return toast("El archivo supera 5 MB.", "error");
    const fd = new FormData();
    fd.append("archivo", archivo);
    zona.innerHTML = '<div class="estado-carga cargando">Importando y validando</div>';
    try {
      const r = await api("/api/clientes/importar", { metodo: "POST", formulario: fd });
      zona.innerHTML = `<div class="banner info">${icono("check")}<div>Lote #${r.id_lote}: <strong>${r.registros_validos}</strong> nuevos, <strong>${r.registros_actualizados}</strong> actualizados, <strong>${r.registros_rechazados}</strong> rechazados.</div></div>
        ${r.errores.length ? `<div class="tabla-envoltura"><table><thead><tr><th>Fila</th><th>Documento</th><th>Motivos</th></tr></thead><tbody>${r.errores.slice(0, 50).map((e) => `<tr><td>${e.fila}</td><td class="mono">${esc(e.documento)}</td><td>${esc(e.motivos.join("; "))}</td></tr>`).join("")}</tbody></table></div>` : ""}`;
      clientes.recargar();
      lotes.recargar();
    } catch (e) {
      zona.innerHTML = `<div class="banner peligro">${icono("alerta")}<div>${esc(e.message)}</div></div>`;
    }
  });
}
