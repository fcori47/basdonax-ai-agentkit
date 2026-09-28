// Prueba el código de un nodo «Format Chain» ANTES de subirlo a n8n.
//
//   node probar_format_chain.js codigo.js
//
// Corre el código como lo corre el nodo Code de n8n (el `return` del final es
// la salida) contra siete respuestas de ejemplo y revisa tres cosas:
//   1. que la salida tenga la forma de siempre: [{ json: { response: { part_1 … part_5 } } }]
//   2. que ningún mensaje pase los 4.096 caracteres (WhatsApp no lo entrega)
//   3. que respete la elección de arriba del código: en 'humano' no pasa del
//      máximo; en 'un_mensaje' sale uno solo (salvo que no entre en 4.096)
// Termina con código 1 si algo falla.
//
// El código se corre ENCERRADO: con el modelo de permisos de node, solo puede
// leer este script y el archivo que se prueba. No puede escribir archivos,
// abrir otros ni lanzar programas, y a los 30 segundos se corta (por si trae
// un bucle infinito). En n8n ese código corre adentro del nodo Code; acá
// correría en tu compu, con tus archivos y tus claves al lado.

const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");

const archivo = process.argv[2];
if (!archivo) {
  console.log("Uso: node probar_format_chain.js codigo.js");
  process.exit(1);
}

if (!process.env.PROBAR_FC_ENCERRADO) {
  // Se vuelve a lanzar a sí mismo, pero encerrado. La bandera del modelo de
  // permisos cambió de nombre entre versiones de node: se prueba cuál anda.
  const anda = (bandera) =>
    spawnSync(process.execPath, [bandera, "-e", "0"], { windowsHide: true, timeout: 10000 }).status === 0;
  const bandera = ["--permission", "--experimental-permission"].find(anda);
  if (!bandera) {
    console.log("Aviso: esta versión de node no puede encerrar el código (hace falta node 20 o más nuevo).");
    console.log("       Corre con los permisos de tu usuario: probá solo código que conozcas.");
  } else {
    const r = spawnSync(
      process.execPath,
      [bandera, `--allow-fs-read=${__filename}`, `--allow-fs-read=${path.resolve(archivo)}`, __filename, archivo],
      {
        stdio: "inherit",
        timeout: 30000,
        windowsHide: true,
        env: { ...process.env, PROBAR_FC_ENCERRADO: "1" },
      }
    );
    if (r.error && r.error.code === "ETIMEDOUT") {
      console.log("\nEl código tardó más de 30 segundos y se cortó: ¿tiene un bucle infinito? No lo subas así.");
      process.exit(1);
    }
    process.exit(r.status === null ? 1 : r.status);
  }
}

const CODIGO = fs.readFileSync(archivo, "utf8");
const TOPE = 4096;

const lineaForma = /const FORMA_DE_RESPONDER = '([^']*)';/;
const lineaMaximo = /const MAXIMO_DE_MENSAJES = ([^;]*);/;

function eleccion(code) {
  const f = code.match(lineaForma);
  const m = code.match(lineaMaximo);
  const forma = f ? f[1] : null;
  const unMensaje = forma !== null && forma.toLowerCase().replace(/[\s_-]/g, "") === "unmensaje";
  const maximo = m ? Math.max(1, Math.min(5, Math.floor(Number(m[1])) || 3)) : 5;
  return { forma, unMensaje, maximo };
}

function conEleccion(code, forma, maximo) {
  return code
    .replace(lineaForma, `const FORMA_DE_RESPONDER = '${forma}';`)
    .replace(lineaMaximo, `const MAXIMO_DE_MENSAJES = ${maximo};`);
}

// El nodo Code de n8n corre el código como cuerpo de una función, con
// $input, $json, items y $('Otro nodo') a mano. Se dan los cuatro: una Format
// Chain que lea $json es tan válida como una que lea $input.
function correr(code, respuestaDelAgente) {
  const entrada = { output: respuestaDelAgente };
  const item = { json: entrada };
  const nodo = { first: () => item, last: () => item, all: () => [item], item };
  const $input = nodo;
  const $ = () => nodo;
  return new Function("$input", "$json", "items", "$", code)($input, entrada, [item], $);
}

function formaDeLaSalida(salida) {
  if (!Array.isArray(salida) || salida.length !== 1) return "no devuelve una lista de 1 elemento";
  const r = salida[0] && salida[0].json && salida[0].json.response;
  if (!r || typeof r !== "object") return "falta json.response";
  const claves = Object.keys(r).join(",");
  if (claves !== "part_1,part_2,part_3,part_4,part_5") return "las claves no son part_1 a part_5: " + claves;
  if (!Object.values(r).every((v) => typeof v === "string")) return "hay una parte que no es texto";
  return "";
}

// Lo que sale de verdad por WhatsApp: las partes que no están vacías.
const mensajes = (salida) => Object.values(salida[0].json.response).filter((p) => p.trim() !== "");

const oracion = (i) => `Esta es la oración ${i} de la respuesta, con un poco de detalle sobre el pedido y los plazos.`;
const CASOS = [
  ["corta", "Hola, sí, tenemos stock. ¿Querés que te pase el precio?"],
  ["tres párrafos", "¡Hola! Sí, enviamos a todo el país.\n\nLlega en 3 a 5 días hábiles.\n\n¿Querés que te arme el pedido?"],
  ["seis párrafos", Array.from({ length: 6 }, (_, i) => `Párrafo ${i + 1}: ${oracion(i)}`).join("\n\n")],
  ["larga sin saltos", Array.from({ length: 9 }, (_, i) => oracion(i)).join(" ")],
  ["saltos simples", Array.from({ length: 5 }, (_, i) => `- Punto ${i + 1}: ${oracion(i)}`).join("\n")],
  ["vacía", ""],
  ["más de 4.096", Array.from({ length: 90 }, (_, i) => oracion(i)).join(" ")],
];

function probar(code, titulo) {
  const { forma, unMensaje, maximo } = eleccion(code);
  console.log(`\n${titulo}: forma ${forma === null ? "(sin elección: como la v3.2)" : forma}, máximo ${maximo}`);
  let fallas = 0;
  for (const [nombre, texto] of CASOS) {
    let salida;
    try {
      salida = correr(code, texto);
    } catch (e) {
      console.log(`  ✗ ${nombre}: el código explotó: ${e.message}`);
      fallas++;
      continue;
    }
    const problema = formaDeLaSalida(salida);
    if (problema) {
      console.log(`  ✗ ${nombre}: ${problema}`);
      fallas++;
      continue;
    }
    const salen = mensajes(salida);
    const largos = salen.map((m) => m.length);
    const errores = [];
    if (largos.some((l) => l > TOPE)) errores.push("un mensaje pasa los 4.096 caracteres");
    const entra = texto.trim().length <= TOPE;
    if (forma !== null && unMensaje && entra && salen.length > 1) errores.push("pidió un solo mensaje y salieron " + salen.length);
    if (forma !== null && !unMensaje && entra && salen.length > maximo) errores.push(`salieron ${salen.length}, más que el máximo`);
    if (texto.trim() && salen.length === 0) errores.push("no salió ningún mensaje");
    const marca = errores.length ? "✗" : "✓";
    if (errores.length) fallas++;
    console.log(`  ${marca} ${nombre}: ${salen.length} mensaje(s) ${JSON.stringify(largos)}${errores.length ? " → " + errores.join("; ") : ""}`);
  }
  return fallas;
}

let fallas = probar(CODIGO, "Así como está");

// Si el código tiene la elección, también se muestra el otro modo.
const { forma, unMensaje, maximo } = eleccion(CODIGO);
if (forma !== null) {
  const otro = unMensaje ? conEleccion(CODIGO, "humano", maximo) : conEleccion(CODIGO, "un_mensaje", maximo);
  fallas += probar(otro, "En el otro modo");
}

console.log(fallas ? `\n${fallas} caso(s) con problemas: no lo subas así.` : "\nTodo bien: se puede subir.");
process.exit(fallas ? 1 : 0);
