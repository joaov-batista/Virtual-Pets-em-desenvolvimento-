
// Teste automático (Node): DOM mínimo, portal simulado, script FGTS de verdade. Confere carregamento, quadro e estados.
const estados = [];
const el = (tag) => {
  const e = { tagName: tag, style: {}, children: [], attrs: {}, _cls: new Set(), textContent: "", onclick: null,
    classList: { add: c => e._cls.add(c), remove: (...cs) => cs.forEach(c => e._cls.delete(c)), contains: c => e._cls.has(c) },
    setAttribute: (k, v) => e.attrs[k] = v, getAttribute: k => e.attrs[k], appendChild: c => (e.children.push(c), c),
    prepend: c => e.children.unshift(c), remove: () => {}, click: () => {}, contentWindow: { console },
    attachShadow: () => shadow, querySelector: () => null, querySelectorAll: () => [] };
  return e;
};
const pecas = {};
const shadow = { set innerHTML(v) { shadow.html = v; }, querySelector: s => (pecas[s] ||= el(s)) };
const host = [];
const docMain = { body: { appendChild: c => host.push(c) }, documentElement: { appendChild() {} }, createElement: el,
  querySelector: s => s === "#menuFgtsTrabalhador" ? { getAttribute: () => "/portal/menuFgts" } : null, querySelectorAll: () => [] };
global.document = docMain;
global.window = {};
Object.defineProperty(global.window, "__dgRoboEstado", { set(v) { if (estados[estados.length - 1] !== v) estados.push(v); } });
global.alert = () => {};
// DOMParser mínimo que entende o HTML do portal simulado
global.DOMParser = class { parseFromString(h) {
  const tem = (re) => re.test(h);
  return {
    querySelector: s => {
      if (s.startsWith("form")) { const m = h.match(/<form action="([^"]+)"/); return m ? { getAttribute: () => m[1] } : null; }
      if (s === ".totalizador-fgts-por-trabalhador") return tem(/totalizador/) ? { cloneNode: () => ({}) } : null;
      return null; },
    querySelectorAll: s => {
      if (s === "table.informacoes-finais tr") { const m = h.match(/<td class="right">([^<]+)</); return m ? [{ textContent: "Total de Depósitos " + m[1], querySelector: () => ({ textContent: m[1] }) }] : []; }
      if (s === ".bloco-informacoes .form-group") { const m = h.match(/<p>([^<]+)<\/p>/); return m ? [{ querySelector: t => ({ textContent: t === "label" ? "Nome" : m[1] }) }] : []; }
      if (s.startsWith("a.download")) { const m = h.match(/href="(\/portal\/DownloadEvento[^"]+)"/); return m ? [{ getAttribute: () => m[1] }] : []; }
      return []; } };
} };
global.window.__ESPERA__ = 5;

(function () {
  const PESSOAS = [["ANA EXEMPLO DE TESTE", "111.111.111-11", 210.5], ["BRUNO MODELO SIMULADO", "222.222.222-22", 340.12], ["CARLA FICTICIA DA SILVA", "333.333.333-33", 455.8], ["DIEGO DEMONSTRACAO", "444.444.444-44", 198.33], ["ELIANE PREVIA SANTOS", "555.555.555-55", 512.07], ["FABIO ROBOZINHO LIMA", "666.666.666-66", 287.9]];
  const esperar = ms => new Promise(r => setTimeout(r, ms));
  const brl = v => v.toFixed(2).replace(".", ",");
  let quedas = 0;
  const FORM = '<form action="/portal/FolhaPagamento/FGTSPorTrabalhador?id=1"></form>';
  window.fetch = async function (url, op) {
    url = String(url);
    await esperar(window.__ESPERA__ || 700);
    if (/menuFgts/.test(url)) return resp(FORM);
    if (/DownloadEvento/.test(url)) return resp('<?xml version="1.0"?><eSocial><evtBasesFGTS/></eSocial>');
    const cpf = new URLSearchParams(op && op.body).get("Cpf");
    const p = PESSOAS.find(x => x[1] === cpf);
    if (p && p[1] === "333.333.333-33" && quedas < 2) { quedas++; throw new TypeError("Failed to fetch"); }
    return resp(FORM + '<div class="totalizador-fgts-por-trabalhador"><div class="bloco-informacoes"><div class="form-group">' +
      '<label>Nome</label><p>' + p[0] + '</p></div></div><table class="informacoes-finais"><tr><td>Total de Depósitos</td>' +
      '<td class="right">R$ ' + brl(p[2]) + '</td></tr></table><a class="download" href="/portal/DownloadEvento?c=' + p[1] + '">XML</a></div>');
  };
  function resp(html) {
    return { ok: true, status: 200, text: async () => html, arrayBuffer: async () => new TextEncoder().encode(html).buffer };
  }
})();

global.fetch = window.fetch;
global.URL.createObjectURL = () => "blob:teste"; global.URL.revokeObjectURL = () => {};
const inicio = Date.now();
eval(require("fs").readFileSync(process.argv[2], "utf8"));
setTimeout(() => {
  const q = pecas[".q"];
  const ok = (cond, msg) => { console.log((cond ? "OK   " : "FALHA") + "  " + msg); if (!cond) process.exitCode = 1; };
  ok(host.filter(h => h.attrs && h.attrs["data-dg-robo"] === "FGTS").length === 1, "quadro criado na página (1 quadro fixo, shadow DOM)");
  ok(/<svg class="robo r"/.test(shadow.html) && /capacete/.test(shadow.html) && /class="sonda"/.test(shadow.html) && />DG</.test(shadow.html), "operador (jaqueta DG, capacete) + sonda em SVG");
  ok(!/linear-gradient|radial-gradient|filter:\s*blur|text-shadow/.test(shadow.html), "sem degradê, desfoque ou brilho");
  ok(host[0].style.cssText.includes("pointer-events:none"), "quadro não pega cliques (só o botão ✕)");
  ok(estados.includes("consultando") && estados.includes("trocando") && estados.includes("erro") && estados.includes("fim"),
     "passou pelos 4 estados: " + estados.join(" → "));
  ok(estados[estados.length - 1] === "fim", "terminou em 'fim'");
  ok(pecas[".cont"].textContent === "6/6 desta parte", "barra de progresso: " + pecas[".cont"].textContent);
  ok(pecas[".n-ok"].textContent === 6 || pecas[".n-ok"].textContent === "6", "contador OK = " + pecas[".n-ok"].textContent);
  ok(q && q._cls.has("st-fim"), "quadro com a classe do estado final");
  console.log("tempo: " + (Date.now() - inicio) + " ms");
}, 25000);
