// Bitácora de auditoría de operaciones sensibles.
import { get } from "../api.js";
import { esc, fecha, tablaPaginada } from "../ui.js";

export async function render(cont) {
  tablaPaginada({
    contenedor: cont,
    titulo: "Bitácora de auditoría",
    descripcion: "Registro inmutable desde la interfaz. Los datos sensibles se enmascaran y nunca se registran contraseñas.",
    filtros: [
      { nombre: "accion", etiqueta: "Acción (exacta)", tipo: "text" },
      { nombre: "entidad", etiqueta: "Entidad", tipo: "text" },
      { nombre: "desde", etiqueta: "Desde", tipo: "date" },
      { nombre: "hasta", etiqueta: "Hasta", tipo: "date" },
    ],
    porPagina: 25,
    cargar: (p) => get("/api/auditoria", p),
    columnas: [
      { titulo: "Fecha", html: (b) => fecha(b.fecha) },
      { titulo: "Usuario", html: (b) => esc(b.usuario) },
      { titulo: "Acción", html: (b) => `<span class="mono">${esc(b.accion)}</span>` },
      { titulo: "Entidad", html: (b) => `${esc(b.entidad)} ${b.id_entidad ? `#${esc(b.id_entidad)}` : ""}` },
      { titulo: "Detalle", html: (b) => `<span class="mono">${esc(b.detalle ? JSON.stringify(b.detalle) : "")}</span>` },
      { titulo: "IP", html: (b) => `<span class="mono">${esc(b.ip || "")}</span>` },
    ],
  });
}
