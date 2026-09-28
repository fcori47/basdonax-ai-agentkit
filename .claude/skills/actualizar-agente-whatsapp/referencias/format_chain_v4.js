// Format Chain v4 - la v3.2 + elegir cómo responde el agente.
//
// ===================== ELEGÍ ACÁ CÓMO RESPONDE =====================
// FORMA_DE_RESPONDER:
//   'humano'     -> varios mensajes cortos, como escribe una persona
//                   (hasta MAXIMO_DE_MENSAJES; más solo si alguno pasa los
//                   4.096 caracteres, que WhatsApp no entrega).
//   'un_mensaje' -> toda la respuesta en un solo mensaje. Se parte solo si
//                   pasa los 4.096 caracteres, el tope de WhatsApp.
//
// Lo que cuesta: desde el 1/10/2026 Meta cobra cada mensaje que manda el
// agente, pasados los 1.000 gratis por mes de cada número. Responder en
// 3 mensajes son 3 mensajes cobrados. Lo que entra por un anuncio de clic
// a WhatsApp es gratis durante 72 h, se manden los mensajes que se manden.
const FORMA_DE_RESPONDER = 'humano';
const MAXIMO_DE_MENSAJES = 3;   // solo cuenta en 'humano': de 1 a 5
// ====================================================================
//
// Fallback al leer texto: output -> response -> text -> message.content -> content
// -> el primer campo de texto que traiga la entrada
// En modo 'humano' parte igual que la v3.2:
// 1) Bloques con \n\n -> respeta cada bloque (máx. MAXIMO_DE_MENSAJES)
// 2) \n simples >=200  -> respeta cada \n
// 3) <=320 sin saltos    -> 1 parte
// 4) Largo: 3/4/5 partes por oraciones (nunca más de MAXIMO_DE_MENSAJES)
// En los dos modos, ningún mensaje pasa los 4.096 caracteres.
// La salida es la de siempre: response.part_1 ... response.part_5 (las que
// sobran van vacías), así que el resto del flujo no se toca.

const MAX_PARTS_HARD_CAP = 5;   // la forma de la salida (part_1..part_5): no tocar
const MAX_CHARS_SINGLE = 320;
const THRESHOLD_4 = 800;
const THRESHOLD_5 = 1200;
const TOPE_WHATSAPP = 4096;     // lo máximo que WhatsApp acepta en un mensaje

// Un error de tipeo en la elección no puede dejar al agente mudo:
// cualquier cosa que no sea 'un_mensaje' responde como 'humano'.
const UN_MENSAJE = String(FORMA_DE_RESPONDER || '').toLowerCase().replace(/[\s_-]/g, '') === 'unmensaje';
const CAP = Math.max(1, Math.min(MAX_PARTS_HARD_CAP, Math.floor(Number(MAXIMO_DE_MENSAJES)) || 3));

const inJson = $input.first().json || {};
let raw = '';
const candidates = [
  inJson.output,
  inJson.response,
  inJson.text,
  inJson.message && inJson.message.content,
  inJson.content
];
for (const c of candidates) {
  if (typeof c === 'string' && c.trim()) { raw = c; break; }
}
// Si el agente devuelve el texto en un campo con otro nombre, se toma el
// primer texto que haya: mejor eso que dejar al agente mudo.
if (!raw) {
  for (const v of Object.values(inJson)) {
    if (typeof v === 'string' && v.trim()) { raw = v; break; }
  }
}
raw = String(raw || '')
  .replace(/\\r\\n/g, "\n")
  .replace(/\\n/g, "\n")
  .replace(/\r\n/g, "\n")
  .replace(/\r/g, "\n")
  .trim()
  .replace(/\u00BF/g, '')
  .replace(/\u00A1/g, '');

function emptyResponse() { const r = {}; for (let i = 1; i <= MAX_PARTS_HARD_CAP; i++) r['part_' + i] = ""; return r; }

function fallbackSplitByLength(text, maxParts) {
  const t = text.trim(); if (!t) return []; if (maxParts <= 1) return [t];
  const parts = []; let remaining = t;
  for (let i = maxParts; i > 1; i--) {
    const target = Math.ceil(remaining.length / i);
    let cut = remaining.lastIndexOf(" ", target);
    if (cut < 20) cut = target;
    parts.push(remaining.slice(0, cut).trim()); remaining = remaining.slice(cut).trim();
  }
  if (remaining) parts.push(remaining); return parts.filter(Boolean);
}

function splitSentencesSmart(text) {
  const s = String(text || "").trim(); if (!s) return [];
  const out = []; let cur = "";
  const isDigit = (ch) => ch >= "0" && ch <= "9";
  const isSpace = (ch) => ch === " " || ch === "\n" || ch === "\t" || ch === "\r";
  function prevNonSpace(i) { for (let k = i; k >= 0; k--) if (!isSpace(s[k])) return s[k]; return ""; }
  function nextNonSpace(i) { for (let k = i; k < s.length; k++) if (!isSpace(s[k])) return s[k]; return ""; }
  for (let i = 0; i < s.length; i++) {
    let ch = s[i]; cur += ch;
    if (ch === "." || ch === "?" || ch === "!") {
      while (ch === "." && s[i + 1] === ".") { i++; cur += "."; }
      const prev = prevNonSpace(i - (cur.endsWith("...") ? 3 : 1));
      const next = nextNonSpace(i + 1);
      let isBoundary = (ch === "?" || ch === "!") ? true : !(isDigit(prev) && isDigit(next));
      if (isBoundary) { const p = cur.trim(); if (p) out.push(p); cur = ""; }
    }
  }
  const tail = cur.trim(); if (tail) out.push(tail); return out;
}

function clampToCap(parts, cap = CAP) {
  if (parts.length <= cap) return parts;
  const head = parts.slice(0, cap - 1);
  const tail = parts.slice(cap - 1).join("\n\n").trim();
  return [...head, tail];
}

// Parte un texto en trozos de hasta `tope` caracteres, en el mejor borde que
// encuentre (párrafo, renglón, fin de oración, espacio).
function partirPorTope(text, tope) {
  const trozos = [];
  let resto = String(text || "").trim();
  while (resto.length > tope) {
    const ventana = resto.slice(0, tope);
    const minimo = Math.floor(tope / 2);
    let corte = ventana.lastIndexOf("\n\n");
    if (corte < minimo) corte = Math.max(corte, ventana.lastIndexOf("\n"));
    if (corte < minimo) {
      const re = /[.!?](?=\s)/g; let m;
      while ((m = re.exec(ventana)) !== null) corte = Math.max(corte, m.index + 1);
    }
    if (corte < minimo) corte = Math.max(corte, ventana.lastIndexOf(" "));
    if (corte <= 0) corte = tope;
    trozos.push(resto.slice(0, corte).trim());
    resto = resto.slice(corte).trim();
  }
  if (resto) trozos.push(resto);
  return trozos.filter(Boolean);
}

// Ningún mensaje puede pasar los 4.096 caracteres: WhatsApp no lo entrega.
// Con respuestas normales no cambia nada. Si uno se pasa, se parte ese solo y
// después se juntan los mensajes cortos vecinos (sin pasar el tope) para volver
// al máximo elegido; solo si no se puede queda alguno de más. Techo: 5 partes.
function dentroDelTope(parts) {
  if (parts.length <= MAX_PARTS_HARD_CAP && parts.every(p => String(p).length <= TOPE_WHATSAPP)) return parts;
  let out = [];
  for (const p of parts) out.push(...(String(p).length > TOPE_WHATSAPP ? partirPorTope(p, TOPE_WHATSAPP) : [String(p)]));
  const objetivo = UN_MENSAJE ? 1 : CAP;
  while (out.length > objetivo) {
    let mejor = -1;   // el par de vecinos más corto que entra junto en un mensaje
    for (let i = 0; i + 1 < out.length; i++) {
      const largo = out[i].length + 2 + out[i + 1].length;
      if (largo <= TOPE_WHATSAPP && (mejor < 0 || largo <= out[mejor].length + 2 + out[mejor + 1].length)) mejor = i;
    }
    if (mejor < 0) break;
    out.splice(mejor, 2, out[mejor] + "\n\n" + out[mejor + 1]);
  }
  if (out.length > MAX_PARTS_HARD_CAP) {
    out = [...out.slice(0, MAX_PARTS_HARD_CAP - 1), out.slice(MAX_PARTS_HARD_CAP - 1).join("\n\n")];
  }
  const ultimo = out[out.length - 1];
  if (ultimo.length > TOPE_WHATSAPP) {
    // Si no entra ni en 5 partes (más de ~20.000 caracteres), el 5º va recortado con "…": mejor eso que no entregarlo.
    let corte = ultimo.lastIndexOf(" ", TOPE_WHATSAPP - 1);
    if (corte < TOPE_WHATSAPP / 2) corte = TOPE_WHATSAPP - 1;
    out[out.length - 1] = ultimo.slice(0, corte).trimEnd() + "\u2026";
  }
  return out;
}

function setResponse(parts) {
  parts = dentroDelTope(parts);
  const response = emptyResponse();
  for (let i = 0; i < Math.min(parts.length, MAX_PARTS_HARD_CAP); i++) response['part_' + (i + 1)] = parts[i];
  return [{ json: { response } }];
}

if (!raw) return [{ json: { response: emptyResponse() } }];

// 'un_mensaje': todo en part_1, con sus párrafos adentro.
if (UN_MENSAJE) return setResponse(partirPorTope(raw, TOPE_WHATSAPP));

const dobleBloques = raw.split(/\n\s*\n+/g).map(t => t.trim()).filter(Boolean);
if (dobleBloques.length >= 2) return setResponse(clampToCap(dobleBloques));

if (raw.includes('\n') && raw.length >= 200) {
  const simpleBloques = raw.split(/\n+/g).map(t => t.trim()).filter(Boolean);
  if (simpleBloques.length >= 2) return setResponse(clampToCap(simpleBloques));
}

if (raw.length <= MAX_CHARS_SINGLE) return setResponse([raw]);

let targetParts;
if (raw.length <= THRESHOLD_4) targetParts = 3;
else if (raw.length <= THRESHOLD_5) targetParts = 4;
else targetParts = 5;
targetParts = Math.min(targetParts, CAP);

const sentences = splitSentencesSmart(raw);
if (sentences.length >= targetParts) {
  const perGroup = Math.ceil(sentences.length / targetParts);
  const groups = [];
  for (let i = 0; i < sentences.length; i += perGroup) {
    groups.push(sentences.slice(i, i + perGroup).join(' ').trim());
  }
  return setResponse(clampToCap(groups));
}

return setResponse(fallbackSplitByLength(raw, targetParts));
