// Cliente HTTP. La sesión viaja en una cookie HttpOnly (no se guarda ningún token en localStorage).
// Las solicitudes que modifican datos envían el token CSRF leído de la cookie sc_csrf.

export class ErrorAPI extends Error {
  constructor(estado, detalle, errores) {
    super(detalle || `Error ${estado}`);
    this.estado = estado;
    this.errores = errores || [];
  }
}

let alNoAutenticado = () => {};
export function onNoAutenticado(fn) { alNoAutenticado = fn; }

function csrf() {
  const m = document.cookie.match(/(?:^|;\s*)sc_csrf=([^;]+)/);
  return m ? decodeURIComponent(m[1]) : "";
}

export async function api(ruta, { metodo = "GET", cuerpo, formulario, params, crudo = false } = {}) {
  let url = ruta;
  if (params) {
    const q = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => { if (v !== undefined && v !== null && v !== "") q.append(k, v); });
    const s = q.toString();
    if (s) url += (url.includes("?") ? "&" : "?") + s;
  }
  const opciones = { method: metodo, credentials: "same-origin", headers: {} };
  if (metodo !== "GET") opciones.headers["X-CSRF-Token"] = csrf();
  if (formulario) opciones.body = formulario;
  else if (cuerpo !== undefined) {
    opciones.headers["Content-Type"] = "application/json";
    opciones.body = JSON.stringify(cuerpo);
  }
  let r;
  try {
    r = await fetch(url, opciones);
  } catch {
    throw new ErrorAPI(0, "No se pudo conectar con el servidor. ¿Está iniciado el backend?");
  }
  if (r.status === 401 && !ruta.endsWith("/auth/login")) {
    alNoAutenticado();
    throw new ErrorAPI(401, "Su sesión expiró. Inicie sesión de nuevo.");
  }
  if (crudo && r.ok) return r;
  let datos = null;
  const tipo = r.headers.get("content-type") || "";
  if (tipo.includes("application/json")) datos = await r.json();
  if (!r.ok) {
    const detalle = datos && typeof datos.detail === "string" ? datos.detail : `Error ${r.status}`;
    throw new ErrorAPI(r.status, detalle, datos && datos.errores);
  }
  return datos;
}

export const get = (ruta, params) => api(ruta, { params });
export const post = (ruta, cuerpo) => api(ruta, { metodo: "POST", cuerpo: cuerpo ?? {} });
export const put = (ruta, cuerpo) => api(ruta, { metodo: "PUT", cuerpo });
export const del = (ruta) => api(ruta, { metodo: "DELETE" });

export async function descargar(ruta, params) {
  const r = await api(ruta, { params, crudo: true });
  const blob = await r.blob();
  const nombre = (r.headers.get("content-disposition") || "").match(/filename="([^"]+)"/)?.[1] || "archivo";
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = nombre;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}
