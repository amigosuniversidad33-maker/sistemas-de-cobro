// Módulo No Contactables: listas de exclusión aplicadas antes de cualquier marcación (DS-09).
import { get, post } from "../api.js";
import { icono } from "../iconos.js";
import { abrirModal, boton, chip, confirmar, errorToast, esc, fecha, formulario, leerFormulario, tablaPaginada, toast } from "../ui.js";

const MOTIVOS = [
  { valor: "NUMERO_INVALIDO", texto: "Número inválido" },
  { valor: "SOLICITUD_NO_CONTACTO", texto: "Solicitud de no contacto" },
  { valor: "PROCESO_LEGAL", texto: "Caso en proceso legal" },
  { valor: "OTRO", texto: "Otro" },
];

export async function render(cont, ctx) {
  const gestionar = ctx.tiene("exclusiones.gestionar");
  cont.innerHTML = `<div class="banner info">${icono("nocontacto")}<div>El filtro se aplica al clasificar, al encolar y otra vez justo antes de originar cada llamada.
    Una exclusión nueva cancela de inmediato los trabajos de marcación pendientes del cliente.</div></div><div id="z"></div>`;
  const t = tablaPaginada({
    contenedor: cont.querySelector("#z"),
    titulo: "Lista de no contactables",
    acciones: gestionar ? boton("Agregar exclusión", { ico: "mas", clase: "btn-primario", datos: "data-nueva" }) : "",
    filtros: [
      { nombre: "activo", etiqueta: "Estado", tipo: "select", valor: "true", opciones: [{ valor: "true", texto: "Activas" }, { valor: "false", texto: "Retiradas" }] },
      { nombre: "motivo", etiqueta: "Motivo", tipo: "select", opciones: [{ valor: "", texto: "Todos" }, ...MOTIVOS] },
    ],
    cargar: (p) => get("/api/exclusiones", p),
    columnas: [
      { titulo: "Cliente", html: (n) => esc(n.cliente || "—") },
      { titulo: "Teléfono", html: (n) => `<span class="mono">${esc(n.telefono || "—")}</span>` },
      { titulo: "Motivo", html: (n) => chip("EXCLUIDO", MOTIVOS.find((m) => m.valor === n.motivo)?.texto || n.motivo) },
      { titulo: "Origen", html: (n) => esc(n.origen) },
      { titulo: "Detalle", html: (n) => esc(n.detalle || "") },
      { titulo: "Registro", html: (n) => fecha(n.fecha_registro) },
      { titulo: "", html: (n) => (gestionar && n.activo ? boton("Retirar", { chico: true, datos: `data-retirar="${n.id}"` }) : "") },
    ],
    alRenderizar: (z) => z.querySelectorAll("[data-retirar]").forEach((b) => b.addEventListener("click", async () => {
      if (!(await confirmar("Retirar exclusión", "El cliente podrá volver a ser contactado si cumple las demás reglas. ¿Continuar?"))) return;
      try { await post(`/api/exclusiones/${b.dataset.retirar}/desactivar`); toast("Exclusión retirada.", "exito"); t.recargar(); } catch (e) { errorToast(e); }
    })),
  });
  cont.querySelector("[data-nueva]")?.addEventListener("click", async () => {
    const campos = [
      { nombre: "q", etiqueta: "Buscar cliente (nombre o documento)", ancho: true },
      { nombre: "id_cliente", etiqueta: "Cliente", tipo: "select", numerico: true, opciones: [{ valor: "", texto: "— Seleccione tras buscar, o indique un teléfono —" }], ancho: true },
      { nombre: "telefono", etiqueta: "Teléfono (si no hay cliente)", maxlength: 30 },
      { nombre: "motivo", etiqueta: "Motivo", tipo: "select", opciones: MOTIVOS },
      { nombre: "detalle", etiqueta: "Detalle", tipo: "textarea", ancho: true, maxlength: 255 },
    ];
    abrirModal({
      titulo: "Agregar a no contactables",
      contenido: formulario(campos),
      alAbrir: (m) => {
        const q = m.querySelector('[name="q"]');
        let temporizador;
        q.addEventListener("input", () => {
          clearTimeout(temporizador);
          temporizador = setTimeout(async () => {
            const r = await get("/api/clientes", { q: q.value, por_pagina: 20 });
            m.querySelector('[name="id_cliente"]').innerHTML = '<option value="">— Seleccione —</option>' + r.items.map((c) => `<option value="${c.id_cliente}">${esc(c.nombre)} · ${esc(c.documento)}</option>`).join("");
          }, 300);
        });
      },
      botones: [{ texto: "Cancelar" }, { texto: "Agregar", clase: "btn-primario", accion: async (m) => {
        const d = leerFormulario(m, campos.filter((c) => c.nombre !== "q"));
        const r = await post("/api/exclusiones", d);
        toast(`Exclusión registrada. Trabajos cancelados: ${r.trabajos_cancelados}`, "exito");
        t.recargar();
      } }],
    });
  });
}
