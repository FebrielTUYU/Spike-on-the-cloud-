// Fase 18 -- verificacion del dashboard COMPLETO (no solo sintaxis).
//
// Leccion de la Fase 18 original (bug del `ico`): `node --check` solo valida
// sintaxis y un arnes de una funcion aislada no ve errores de ejecucion del
// script entero. Esto carga un dashboard.html generado (con datos reales),
// ejecuta TODO su <script> en jsdom, hace click en cada boton de navegacion y
// falla si aparece cualquier error de JavaScript o si Noticias queda vacia.
//
// Uso:  npm install jsdom   (una vez, en cualquier carpeta)
//       NODE_PATH=<esa carpeta>/node_modules node pruebas/verificar_dashboard.js dashboard.html
const fs = require("fs");
const { JSDOM, VirtualConsole } = require("jsdom");

const ruta = process.argv[2] || "dashboard.html";
const html = fs.readFileSync(ruta, "utf8");
const errores = [];
const vc = new VirtualConsole();
vc.on("jsdomError", (e) => errores.push(String(e && (e.stack || e.message) || e)));
vc.on("error", (e) => errores.push("console.error: " + e));

const m = html.match(/const DATA_INICIAL\s*=|\/\*__DATA__\*\//);
const dom = new JSDOM(html, {
  runScripts: "dangerously", pretendToBeVisual: true, url: "http://127.0.0.1:8000/dashboard.html",
  virtualConsole: vc,
  beforeParse(w) {
    w.fetch = () => Promise.resolve({ ok: false, status: 404, json: async () => ({}), text: async () => "" });
    w.scrollTo = () => {};
    w.HTMLElement.prototype.scrollIntoView = () => {};
  },
});
const w = dom.window, d = w.document;
const pasos = [];
function click(sel) {
  d.querySelectorAll(sel).forEach((b) => {
    try { b.click(); pasos.push(sel + " -> " + (b.dataset.sec || b.dataset.prod || b.textContent.trim().slice(0, 20))); }
    catch (e) { errores.push("click " + sel + ": " + e); }
  });
}
setTimeout(() => {
  const lista = d.querySelector("#list");
  const largoInicial = lista ? lista.innerHTML.length : -1;
  click("#mainnav [data-sec]");
  click("[data-prod]");
  click("#mainnav [data-sec='noticias']");
  const res = {
    errores, pasos: pasos.length, list_chars: largoInicial,
    nueva_chips: (d.body.innerHTML.match(/>Nueva</g) || []).length,
    actualizacion_chips: (d.body.innerHTML.match(/Actualización · vista por primera vez/g) || []).length,
    eventos: (d.body.innerHTML.match(/Evento en curso ·/g) || []).length,
  };
  console.log(JSON.stringify(res, null, 1));
  process.exit(errores.length || largoInicial < 1000 ? 1 : 0);
}, 1500);
