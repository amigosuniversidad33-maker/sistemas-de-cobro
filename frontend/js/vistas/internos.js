// Módulo Agentes Internos (HU-01 a HU-04): usuarios, roles, permisos y asignaciones de supervisión.
import { del, get, post, put } from "../api.js";
import { abrirModal, boton, chip, confirmar, errorToast, esc, fecha, formulario, leerFormulario, opcionesDe, tablaPaginada, tarjeta, toast } from "../ui.js";

export async function render(cont, ctx) {
  const roles = await get("/api/roles");
  const gestionar = ctx.tiene("usuarios.gestionar");
  cont.innerHTML = `<div id="z-usuarios"></div><div class="rejilla rejilla-2"><div id="z-roles"></div><div id="z-supervision"></div></div>`;
  const tabla = tablaPaginada({
    contenedor: cont.querySelector("#z-usuarios"),
    titulo: "Usuarios internos",
    descripcion: "Administradores, supervisores y analistas. No participan en la marcación de llamadas.",
    acciones: gestionar ? boton("Registrar usuario", { ico: "mas", clase: "btn-primario", datos: "data-nuevo" }) : "",
    filtros: [
      { nombre: "q", etiqueta: "Buscar" },
      { nombre: "id_rol", etiqueta: "Rol", tipo: "select", opciones: opcionesDe(roles, "id_rol", "nombre", "Todos") },
      { nombre: "estado", etiqueta: "Estado", tipo: "select", opciones: [{ valor: "", texto: "Todos" }, { valor: "ACTIVO", texto: "Activo" }, { valor: "INACTIVO", texto: "Inactivo" }] },
    ],
    cargar: (p) => get("/api/usuarios", p),
    columnas: [
      { titulo: "Usuario", html: (u) => `<strong>${esc(u.usuario)}</strong>` },
      { titulo: "Nombre", html: (u) => esc(`${u.nombre} ${u.apellido}`) },
      { titulo: "Correo", html: (u) => esc(u.correo) },
      { titulo: "Rol", html: (u) => chip(u.rol, u.rol) },
      { titulo: "Estado", html: (u) => chip(u.estado) + (u.bloqueado_temporalmente ? " " + chip("BLOQUEADO", "Bloqueo temporal") : "") },
      { titulo: "Último acceso", html: (u) => fecha(u.ultimo_acceso) },
      { titulo: "", html: (u) => (gestionar ? `<span class="acciones">${boton("Editar", { chico: true, datos: `data-editar="${u.id_usuario}"` })}
        ${boton(u.estado === "ACTIVO" ? "Desactivar" : "Activar", { chico: true, datos: `data-estado="${u.id_usuario}" data-valor="${u.estado === "ACTIVO" ? "INACTIVO" : "ACTIVO"}"` })}
        ${boton("Contraseña", { chico: true, datos: `data-pass="${u.id_usuario}"` })}</span>` : "") },
    ],
    alRenderizar: (zona, items) => {
      zona.querySelectorAll("[data-editar]").forEach((b) => b.addEventListener("click", () => abrir(items.find((u) => String(u.id_usuario) === b.dataset.editar))));
      zona.querySelectorAll("[data-estado]").forEach((b) => b.addEventListener("click", async () => {
        if (!(await confirmar("Cambiar estado", `¿Cambiar el estado del usuario a ${b.dataset.valor}? Sus sesiones se revocarán si se desactiva.`))) return;
        try { await post(`/api/usuarios/${b.dataset.estado}/estado`, { estado: b.dataset.valor }); toast("Estado actualizado.", "exito"); tabla.recargar(); } catch (e) { errorToast(e); }
      }));
      zona.querySelectorAll("[data-pass]").forEach((b) => b.addEventListener("click", () => cambiarPass(b.dataset.pass)));
    },
  });

  const camposUsuario = (nuevo) => [
    { nombre: "nombre", etiqueta: "Nombre", requerido: true, maxlength: 80 },
    { nombre: "apellido", etiqueta: "Apellido", requerido: true, maxlength: 80 },
    { nombre: "correo", etiqueta: "Correo", tipo: "email", requerido: true, maxlength: 160 },
    { nombre: "id_rol", etiqueta: "Rol", tipo: "select", numerico: true, opciones: opcionesDe(roles, "id_rol", "nombre") },
    ...(nuevo ? [
      { nombre: "usuario", etiqueta: "Nombre de acceso", requerido: true, maxlength: 50, ayuda: "3–50: letras, números, punto, guion" },
      { nombre: "password", etiqueta: "Contraseña inicial", tipo: "password", requerido: true, maxlength: 128, autocompletar: "new-password", ayuda: "Mínimo 10 caracteres y 3 tipos (mayúsculas, minúsculas, números, símbolos)" },
    ] : []),
  ];
  function abrir(u) {
    const c = camposUsuario(!u);
    abrirModal({
      titulo: u ? `Modificar ${u.usuario}` : "Registrar usuario interno",
      contenido: formulario(c, u || {}),
      botones: [{ texto: "Cancelar" }, { texto: "Guardar", clase: "btn-primario", accion: async (m) => {
        const d = leerFormulario(m, c);
        if (u) await put(`/api/usuarios/${u.id_usuario}`, d); else await post("/api/usuarios", d);
        toast(u ? "Usuario actualizado." : "Usuario registrado.", "exito");
        tabla.recargar();
      } }],
    });
  }
  function cambiarPass(id) {
    const c = [{ nombre: "password", etiqueta: "Nueva contraseña", tipo: "password", requerido: true, ancho: true, autocompletar: "new-password" }];
    abrirModal({ titulo: "Restablecer contraseña", contenido: formulario(c) + '<p class="texto-tenue">Se revocarán las sesiones activas del usuario.</p>',
      botones: [{ texto: "Cancelar" }, { texto: "Restablecer", clase: "btn-primario", accion: async (m) => { await post(`/api/usuarios/${id}/password`, leerFormulario(m, c)); toast("Contraseña restablecida.", "exito"); } }] });
  }
  cont.querySelector("[data-nuevo]")?.addEventListener("click", () => abrir(null));

  // Roles y permisos (RBAC)
  const permisos = await get("/api/permisos");
  cont.querySelector("#z-roles").innerHTML = tarjeta("Roles y permisos (RBAC)", `<div class="tabla-envoltura"><table><thead><tr><th>Rol</th><th>Permisos</th><th></th></tr></thead><tbody>
    ${roles.map((r) => `<tr><td><strong>${esc(r.nombre)}</strong><br><small class="texto-tenue">${esc(r.descripcion || "")}</small></td><td>${r.permisos.length} de ${permisos.length}</td>
    <td>${ctx.tiene("roles.gestionar") && r.nombre !== "ADMINISTRADOR" ? boton("Permisos", { chico: true, datos: `data-rol="${r.id_rol}"` }) : ""}</td></tr>`).join("")}</tbody></table></div>`,
    { descripcion: "Denegación por defecto: solo se permite lo asignado." });
  cont.querySelectorAll("[data-rol]").forEach((b) => b.addEventListener("click", () => {
    const rol = roles.find((r) => String(r.id_rol) === b.dataset.rol);
    const porModulo = {};
    permisos.forEach((p) => (porModulo[p.modulo] ||= []).push(p));
    abrirModal({
      titulo: `Permisos de ${rol.nombre}`,
      contenido: Object.entries(porModulo).map(([m, ps]) => `<h3>${esc(m)}</h3>${ps.map((p) => `<label class="check"><input type="checkbox" value="${esc(p.codigo)}" ${rol.permisos.includes(p.codigo) ? "checked" : ""}> ${esc(p.accion)} <span class="mono texto-tenue">${esc(p.codigo)}</span></label>`).join("")}`).join(""),
      botones: [{ texto: "Cancelar" }, { texto: "Guardar permisos", clase: "btn-primario", accion: async (m) => {
        const codigos = [...m.querySelectorAll("input:checked")].map((i) => i.value);
        const r = await put(`/api/roles/${rol.id_rol}/permisos`, { codigos });
        toast(`Permisos actualizados. Sesiones revocadas: ${r.sesiones_revocadas_de_usuarios}`, "exito");
        render(cont, ctx);
      } }],
    });
  }));

  // Asignaciones de supervisión por campaña
  const zSup = cont.querySelector("#z-supervision");
  const pintarSup = async () => {
    const [asig, campanas, usuarios] = await Promise.all([get("/api/supervision"), get("/api/campanas", { por_pagina: 200 }), get("/api/usuarios", { por_pagina: 200 })]);
    zSup.innerHTML = tarjeta("Asignaciones de supervisión", `<div class="tabla-envoltura"><table><thead><tr><th>Usuario</th><th>Campaña</th><th>Alcance</th><th></th></tr></thead><tbody>
      ${asig.map((a) => `<tr><td>${esc(a.usuario)}</td><td>${esc(a.campana)}</td><td>${chip(a.alcance === "GESTION" ? "ACTIVA" : "BORRADOR", a.alcance)}</td><td>${gestionar ? boton("Quitar", { chico: true, datos: `data-quitar="${a.id}"` }) : ""}</td></tr>`).join("") || '<tr><td colspan="4" class="texto-tenue">Sin asignaciones.</td></tr>'}</tbody></table></div>`,
      { descripcion: "Los supervisores solo ven y gestionan las campañas asignadas.", acciones: gestionar ? boton("Asignar", { ico: "mas", datos: "data-asignar" }) : "" });
    zSup.querySelectorAll("[data-quitar]").forEach((b) => b.addEventListener("click", async () => { try { await del(`/api/supervision/${b.dataset.quitar}`); pintarSup(); } catch (e) { errorToast(e); } }));
    zSup.querySelector("[data-asignar]")?.addEventListener("click", () => {
      const c = [
        { nombre: "id_usuario", etiqueta: "Usuario", tipo: "select", numerico: true, opciones: opcionesDe(usuarios.items, "id_usuario", (u) => `${u.usuario} (${u.rol})`) },
        { nombre: "id_campana", etiqueta: "Campaña", tipo: "select", numerico: true, opciones: opcionesDe(campanas.items, "id_campana", "nombre") },
        { nombre: "alcance", etiqueta: "Alcance", tipo: "select", opciones: [{ valor: "GESTION", texto: "Gestión" }, { valor: "LECTURA", texto: "Solo lectura" }] },
      ];
      abrirModal({ titulo: "Asignar supervisión", contenido: formulario(c), botones: [{ texto: "Cancelar" }, { texto: "Asignar", clase: "btn-primario", accion: async (m) => { await post("/api/supervision", leerFormulario(m, c)); pintarSup(); } }] });
    });
  };
  pintarSup().catch((e) => (zSup.innerHTML = `<div class="estado-error">${esc(e.message)}</div>`));
}
