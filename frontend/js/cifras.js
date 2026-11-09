// Cifras en palabras para la voz del navegador (misma lógica que backend/app/voz/cifras.py):
// «Q 14,577.63» -> «catorce mil quinientos setenta y siete quetzales con sesenta y tres centavos».
const UNIDADES = ["cero", "uno", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve", "diez", "once", "doce",
  "trece", "catorce", "quince", "dieciséis", "diecisiete", "dieciocho", "diecinueve", "veinte", "veintiuno", "veintidós",
  "veintitrés", "veinticuatro", "veinticinco", "veintiséis", "veintisiete", "veintiocho", "veintinueve"];
const DECENAS = ["", "", "", "treinta", "cuarenta", "cincuenta", "sesenta", "setenta", "ochenta", "noventa"];
const CENTENAS = ["", "ciento", "doscientos", "trescientos", "cuatrocientos", "quinientos", "seiscientos", "setecientos",
  "ochocientos", "novecientos"];

function apocopar(p) {
  if (p.endsWith("veintiuno")) return p.slice(0, -"veintiuno".length) + "veintiún";
  if (p.endsWith("uno")) return p.slice(0, -3) + "un";
  return p;
}

function menorMil(n) {
  if (n < 30) return UNIDADES[n];
  if (n < 100) { const d = Math.floor(n / 10), u = n % 10; return DECENAS[d] + (u ? ` y ${UNIDADES[u]}` : ""); }
  if (n === 100) return "cien";
  const c = Math.floor(n / 100), r = n % 100;
  return CENTENAS[c] + (r ? ` ${menorMil(r)}` : "");
}

export function numeroALetras(n, apocope = false) {
  if (n === 0) return "cero";
  const millones = Math.floor(n / 1e6), miles = Math.floor((n % 1e6) / 1000), unidades = n % 1000;
  const partes = [];
  if (millones) partes.push(millones === 1 ? "un millón" : `${apocopar(numeroALetras(millones))} millones`);
  if (miles) partes.push(miles === 1 ? "mil" : `${apocopar(menorMil(miles))} mil`);
  if (unidades) partes.push(menorMil(unidades));
  let t = partes.join(" ");
  if (apocope && unidades) t = apocopar(t);
  if (apocope && !unidades && !miles && millones) t += " de";
  return t;
}

function montoALetras(cifra, simbolo) {
  const [ent, dec = ""] = cifra.replace(/,/g, "").split(".");
  const entero = parseInt(ent || "0", 10), centavos = dec ? parseInt((dec + "0").slice(0, 2), 10) : 0;
  const [sing, plur] = simbolo === "Q" ? ["quetzal", "quetzales"] : ["dólar", "dólares"];
  let t = `${numeroALetras(entero, true)} ${entero === 1 ? sing : plur}`;
  if (centavos) t += ` con ${numeroALetras(centavos, true)} ${centavos === 1 ? "centavo" : "centavos"}`;
  return t;
}

const CIFRA = String.raw`\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?`;

export function cifrasParaVoz(texto) {
  return String(texto || "")
    .replace(new RegExp(String.raw`(US\$|\$|Q)\s?(${CIFRA})(?!\d|,\d)`, "g"), (_, s, c) => montoALetras(c, s))
    .replace(new RegExp(String.raw`(?<![\w.,])(${CIFRA})\s*(quetzales|quetzal|dólares|dolares|dólar|dolar)\b`, "gi"),
      (_, c, p) => montoALetras(c, /^d/i.test(p) ? "US$" : "Q"))
    .replace(/(?<![\w.,])(\d{1,3}(?:,\d{3})+)(?:\.(\d{1,2}))?(?!\d|,\d)/g,
      (_, e, d) => numeroALetras(parseInt(e.replace(/,/g, ""), 10)) + (d ? ` punto ${numeroALetras(parseInt(d, 10))}` : ""));
}
