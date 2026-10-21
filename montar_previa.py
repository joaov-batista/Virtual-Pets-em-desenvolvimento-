# -*- coding: utf-8 -*-
"""Prévia e teste do robozinho do eSocial SEM o portal: monta um "portal simulado" (menu, formulário, resultado e XML
falsos, 6 pessoas fictícias, nenhum CPF real) e roda nele o script FGTS de verdade, gerado do modelo atual.
Gera:  previa_robozinho_esocial.html  (abrir no navegador: o quadro aparece no canto direito e passa pelos 4 estados)
       teste_node.js                   (teste automático no Node: confere que carrega, que o quadro aparece e os estados)
Uso:   py -3 montar_previa.py"""
import json
import os
import re

AQUI = os.path.dirname(os.path.abspath(__file__))
MODELO = os.path.join(AQUI, '..', '..', 'Plataforma Documentação Mensal', 'separar', 'modelos_esocial', 'esocial_fgts_modelo.js')

FICTICIOS = [  # nomes e CPFs inventados (CPF com dígitos repetidos, não existe)
    ('ANA EXEMPLO DE TESTE', '111.111.111-11', 210.50), ('BRUNO MODELO SIMULADO', '222.222.222-22', 340.12),
    ('CARLA FICTICIA DA SILVA', '333.333.333-33', 455.80), ('DIEGO DEMONSTRACAO', '444.444.444-44', 198.33),
    ('ELIANE PREVIA SANTOS', '555.555.555-55', 512.07), ('FABIO ROBOZINHO LIMA', '666.666.666-66', 287.90)]

js = open(MODELO, encoding='utf-8').read()
js = js.replace('const COMPETENCIA = "MM/AAAA";', 'const COMPETENCIA = "09/2026";', 1)
js = js.replace('/*__PARTE_INFO__*/', '   >>> PRÉVIA: portal simulado, pessoas fictícias <<<')
js = re.sub(r'const LOTE = "[A-Z_]+";', 'const LOTE = "PREVIA_P01de01";', js, count=1)
js = js.replace('const PAUSA_MS    = 300;', 'const PAUSA_MS    = 900;', 1)   # mais devagar para ver a animação
linhas = '\n'.join(f'    {{ nome: "{n}", cpf: "{c}", fgts: {v:.2f} }},' for n, c, v in FICTICIOS)
js = re.sub(r'(  const FUNCIONARIOS = \[\n)(.*?)(\n  \];)', lambda m: m.group(1) + linhas + m.group(3), js, count=1, flags=re.S)

# portal simulado: responde como o eSocial, com espera, e derruba 2 vezes a consulta da 3ª pessoa (para ver o "erro")
PORTAL = r'''
(function () {
  const PESSOAS = __PESSOAS__;
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
'''.replace('__PESSOAS__', json.dumps([[n, c, v] for n, c, v in FICTICIOS]))

HTML = '''<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><title>Prévia robozinho eSocial</title>
<style>
  body { margin:0; background:#f3f5f9; font:14px Inter,"Segoe UI",Calibri,sans-serif; color:#1b2433; }
  .topo { background:#0c1320; color:#dde3ec; padding:14px 24px; font-weight:600; }
  .conteudo { padding:24px; max-width:640px; }
  .caixa { background:#fff; border:1px solid #e2e7ef; border-radius:8px; padding:16px; margin-top:12px; }
  button { font:13px Inter,Calibri,sans-serif; padding:6px 12px; border-radius:6px; border:1px solid #cdd5e1; background:#fff; cursor:pointer; }
  a#menuFgtsTrabalhador { color:#1f6fc0; }
</style></head>
<body>
<div class="topo">eSocial (simulado) — prévia do operador DrillGeo na sonda</div>
<div class="conteudo">
  <p>Esta página imita o portal do eSocial e roda o <b>script FGTS de verdade</b> com <b>6 pessoas fictícias</b>.
     O quadro aparece no canto direito e passa pelos estados: consultando → trocando de pessoa → erro (a 3ª pessoa
     "cai" 2 vezes de propósito) → fim.</p>
  <p>Menu do portal: <a id="menuFgtsTrabalhador" href="/portal/menuFgts">FGTS por Trabalhador</a></p>
  <div class="caixa"><b>Ver cada estado parado:</b>
    <button onclick="verEstado('consultando')">Consultando</button>
    <button onclick="verEstado('trocando')">Trocando de pessoa</button>
    <button onclick="verEstado('erro')">Erro / timeout</button>
    <button onclick="verEstado('fim')">Fim</button></div>
  <div class="caixa"><button onclick="location.reload()">Rodar de novo</button>
  <span style="margin-left:8px;color:#6c7789">O ZIP de exemplo é baixado no fim (pode apagar).</span></div>
  <div class="caixa" style="height:600px;color:#6c7789">Área da página do portal (o quadro fica por cima, sem pegar cliques).
    <button style="margin-top:12px" onclick="this.textContent='Clique funcionou (o quadro não atrapalha)'">Teste: clique aqui</button></div>
</div>
<script>window.alert = m => console.log("[janela] " + m);</script>
<script>
  // só da prévia: mostra um estado parado no quadro (a simulação continua por trás)
  function verEstado(s) {
    const q = document.querySelector("[data-dg-robo]").shadowRoot.querySelector(".q");
    q.className = "q st-" + s;
    q.querySelector(".estado").textContent = { consultando: "Consultando", trocando: "Trocando de pessoa",
      erro: "O portal demorou — tentando de novo", fim: "Concluído — ZIP baixado" }[s];
  }
</script>
<script>__PORTAL__</script>
<script>__SCRIPT__</script>
</body></html>'''
open(os.path.join(AQUI, 'previa_robozinho_esocial.html'), 'w', encoding='utf-8').write(
    HTML.replace('__PORTAL__', PORTAL).replace('__SCRIPT__', js))

# ---------------- teste no Node: DOM mínimo + o mesmo portal simulado ----------------
TESTE = r'''
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
__PORTAL__
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
'''.replace('__PORTAL__', PORTAL)
open(os.path.join(AQUI, 'teste_node.js'), 'w', encoding='utf-8').write(TESTE)
open(os.path.join(AQUI, 'script_previa_fgts.js'), 'w', encoding='utf-8').write(js)
print('ok: previa_robozinho_esocial.html, teste_node.js, script_previa_fgts.js')
