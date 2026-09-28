// Format Chain v3.2 - respeta intencion del agente.
// Fallback al leer texto: output -> response -> mensaje_para_cliente -> text -> message.content
// 1) Bloques con \n\n -> respeta cada bloque (max 5)
// 2) \n simples >=200  -> respeta cada \n
// 3) <=320 sin saltos    -> 1 parte
// 4) Largo: 3/4/5 partes por oraciones

const MAX_PARTS_HARD_CAP = 5;
const MAX_CHARS_SINGLE = 320;
const THRESHOLD_4 = 800;
const THRESHOLD_5 = 1200;

const inJson = $input.first().json || {};
let raw = '';
const candidates = [
  inJson.output,
  inJson.response,
  inJson.mensaje_para_cliente,
  inJson.text,
  inJson.message && inJson.message.content,
  inJson.content
];
for (const c of candidates) {
  if (typeof c === 'string' && c.trim()) { raw = c; break; }
}
raw = String(raw || '')
  .replace(/\\r\\n/g, "\n")
  .replace(/\\n/g, "\n")
  .replace(/\r\n/g, "\n")
  .replace(/\r/g, "\n")
  .trim()
  .replace(/¿/g, '')
  .replace(/¡/g, '');

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

function clampToCap(parts) {
  if (parts.length <= MAX_PARTS_HARD_CAP) return parts;
  const head = parts.slice(0, MAX_PARTS_HARD_CAP - 1);
  const tail = parts.slice(MAX_PARTS_HARD_CAP - 1).join("\n\n").trim();
  return [...head, tail];
}

function setResponse(parts) {
  const response = emptyResponse();
  for (let i = 0; i < Math.min(parts.length, MAX_PARTS_HARD_CAP); i++) response['part_' + (i + 1)] = parts[i];
  return [{ json: { response } }];
}

if (!raw) return [{ json: { response: emptyResponse() } }];

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
