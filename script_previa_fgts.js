/* =====================================================================
   eSocial – Totalizador FGTS por Trabalhador (download em lote + conferência)
   Drillgeo · MODELO – preencher COMPETENCIA, LOTE e FUNCIONARIOS antes de usar
   Unidades que usam: Vale Sul, Vale Norte, Xingu (VRCN e VRSTF)
   >>> PRÉVIA: portal simulado, pessoas fictícias <<<

   COMO USAR
   1. Entre no eSocial (certificado da Drillgeo) e abra qualquer página do
      portal — de preferência Folha de Pagamento > Totalizadores >
      Trabalhador > FGTS.
   2. F12 > aba "Console" > cole este script inteiro > Enter.
      (Se o Edge bloquear a colagem, digite:  allow pasting  e Enter antes.)
      LOGO AO COMEÇAR APARECE UMA JANELA "Script carregado". Se ela NÃO aparecer, o Edge
      recusou a colagem: digite  allow pasting , Enter, e COLE O SCRIPT DE NOVO.
      Se o script parar por erro, aparece outra janela dizendo o motivo.
   3. Aguarde. Ao final baixa DOIS arquivos:
        eSocial_FGTS_<MM-AAAA>_<LOTE>.zip            → empregados ativos
        eSocial_FGTS_<MM-AAAA>_<LOTE>_DEMITIDOS.zip  → demitidos na competência
      (se o Edge perguntar sobre "vários downloads", clique em Permitir)
      Cada ZIP contém:
        - NOME DO FUNCIONARIO.xml   → XML do totalizador (botão "Baixar XML")
        - (opcional) NOME DO FUNCIONARIO.html → cópia da tela, se SALVAR_HTML = true
        - _CONFERENCIA_FGTS_<LOTE>.csv            → Folha x eSocial de TODOS (no ZIP de ativos)
        - _CONFERENCIA_FGTS_<LOTE>_DEMITIDOS.csv  → só os demitidos (no ZIP de demitidos)
   ===================================================================== */
(async () => {
  // ---- PAINEL NA TELA COM O OPERADOR DRILLGEO NA SONDA (21/10/2026) ----------------------------------------------------
  // Só visual. O portal do eSocial esconde as mensagens do Console; este "console" local escreve no Console verdadeiro
  // (pego de um iframe limpo) E num quadro fixo no canto direito. O robozinho muda de estado lendo as MESMAS mensagens
  // que o script já escreve ("Iniciando", "3/10 OK ...", "conexão caiu", "FIM") — não mexe na consulta, nos ZIPs nem nas listas.
  // O quadro fica num shadow DOM (o CSS do portal não entra, o nosso não sai) e não pega cliques (só o botão ✕).
  // Fonte única: separar\modelos_esocial\painel_robo.js (aplicado nos dois modelos; FGTS = FGTS ou INSS).
  const console = (() => {
    const fr = document.createElement("iframe"); fr.style.display = "none"; document.documentElement.appendChild(fr);
    const c = fr.contentWindow.console;
    const host = document.createElement("div");
    host.setAttribute("data-dg-robo", "FGTS");
    host.style.cssText = "position:fixed;top:12px;right:12px;z-index:2147483647;pointer-events:none";
    const raiz = host.attachShadow ? host.attachShadow({ mode: "open" }) : host;
    raiz.innerHTML = `
<style>
  :host, .q { all: initial; }
  .q { display:block; width:400px; box-sizing:border-box; background:#151d2b; color:#e4e9f1; border:1px solid #2e3a50;
       border-radius:10px; box-shadow:0 12px 40px rgba(0,0,0,.45); font:13px Inter,"Segoe UI",Calibri,system-ui,sans-serif;
       padding:12px 14px; pointer-events:none; }
  .cab { display:flex; align-items:center; justify-content:space-between; margin-bottom:8px; }
  .tit { font-weight:600; font-size:13px; color:#e4e9f1; }
  .tit b { color:#4a94e0; font-weight:600; }
  .lote { font:11px "Cascadia Mono",Consolas,monospace; color:#7f8ba0; margin-left:6px; }
  .x { pointer-events:auto; cursor:pointer; border:1px solid #2e3a50; background:#1a2332; color:#a9b4c6; border-radius:6px;
       width:24px; height:24px; font:14px/22px Inter,Calibri,sans-serif; text-align:center; padding:0; }
  .x:hover { background:#1f2939; color:#e4e9f1; }
  .meio { display:flex; gap:12px; align-items:center; }
  .robo { width:160px; height:120px; flex:none; background:#0e1522; border:1px solid #232e40; border-radius:8px; }
  .info { flex:1; min-width:0; }
  .estado { font-weight:600; font-size:13px; color:#4a94e0; }
  .q.st-erro .estado { color:#de9a62; } .q.st-fim .estado { color:#52be8c; }
  .pessoa { font-size:12px; color:#a9b4c6; margin-top:2px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .barra { height:8px; background:#232e40; border-radius:4px; margin:10px 0 4px; overflow:hidden; }
  .barra i { display:block; height:100%; width:0; background:#4a94e0; border-radius:4px; transition:width .5s ease; }
  .q.st-fim .barra i { background:#52be8c; }
  .num { display:flex; justify-content:space-between; font:11px "Cascadia Mono",Consolas,monospace; color:#7f8ba0; }
  .chips { display:flex; gap:6px; margin-top:8px; }
  .chip { flex:1; border-radius:6px; padding:4px 6px; font-size:11px; color:#a9b4c6; }
  .chip b { display:block; font:600 14px "Cascadia Mono",Consolas,monospace; }
  .ok { background:rgba(82,190,140,.13); } .ok b { color:#52be8c; }
  .dv { background:rgba(222,154,98,.13); } .dv b { color:#de9a62; }
  .er { background:rgba(226,123,115,.13); } .er b { color:#e27b73; }
  .nota { font-size:11px; color:#7f8ba0; margin-top:8px; }
  .log { margin-top:8px; max-height:110px; overflow:auto; border-top:1px solid #232e40; padding-top:6px;
         font:11px "Cascadia Mono",Consolas,monospace; color:#7f8ba0; pointer-events:auto; }
  .log div { white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .log .w { color:#de9a62; } .log .e { color:#e27b73; } .log .k { color:#52be8c; }

  /* ---------------- operador DrillGeo na sonda de mineração: peças ---------------- */
  .r * { transform-box:fill-box; }
  .r .folha, .r .zip, .r .pergunta, .r .lamp-erro, .r .po { opacity:0; }
  /* consultando: o cabeçote desce perfurando, a haste gira, sobe poeira; o operador mexe na alavanca */
  .st-consultando .r .cabecote { animation:dg-perfura 2.6s ease-in-out infinite alternate; }
  .st-consultando .r .haste-gira { animation:dg-gira .35s linear infinite; }
  .st-consultando .r .po { animation:dg-poeira 1.1s ease-out infinite; }
  .st-consultando .r .po2 { animation-delay:.4s; } .st-consultando .r .po3 { animation-delay:.75s; }
  .st-consultando .r .bd { transform-origin:50% 0%; animation:dg-alavanca .6s ease-in-out infinite alternate; }
  .st-consultando .r .olhos { animation:dg-olha 2.4s ease-in-out infinite; }
  /* trocando de pessoa: o cabeçote sobe; o operador pula e leva a folha até a sonda */
  .st-trocando .r .cabecote { animation:dg-sobe .9s ease-in-out infinite; }
  .st-trocando .r .operador { animation:dg-pula .6s ease-in-out infinite; }
  .st-trocando .r .folha { opacity:1; animation:dg-folha 1.2s ease-in-out infinite; }
  .st-trocando .r .bd { transform-origin:50% 0%; animation:dg-leva 1.2s ease-in-out infinite; }
  /* erro / timeout: a sonda para, luz laranja pisca; o operador coça o capacete e aparece "?" */
  .st-erro .r .cabecote { transform:translateY(12px); }
  .st-erro .r .lamp-ok { opacity:0; }
  .st-erro .r .lamp-erro { opacity:1; animation:dg-pisca .7s steps(2) infinite; }
  .st-erro .r .cabeca { transform-origin:50% 100%; animation:dg-inclina 1.6s ease-in-out infinite; }
  .st-erro .r .bd { transform-origin:50% 0%; transform:rotate(-155deg); animation:dg-coca .35s ease-in-out infinite alternate; }
  .st-erro .r .pergunta { opacity:1; animation:dg-boia 1.2s ease-in-out infinite; }
  /* fim: cabeçote no alto, operador comemora e entrega o ZIP */
  .st-fim .r .operador { animation:dg-pula 1s ease-in-out infinite; }
  .st-fim .r .be { transform-origin:50% 0%; animation:dg-viva .5s ease-in-out infinite alternate; }
  .st-fim .r .bd { transform-origin:50% 0%; transform:rotate(-35deg); }
  .st-fim .r .zip { opacity:1; animation:dg-entrega 1.6s ease-in-out infinite; }
  @keyframes dg-perfura { from { transform:translateY(0); } to { transform:translateY(24px); } }
  @keyframes dg-sobe { 0% { transform:translateY(24px); } 70%,100% { transform:translateY(0); } }
  @keyframes dg-gira { to { stroke-dashoffset:-10; } }
  @keyframes dg-poeira { 0% { opacity:.9; transform:translate(0,0); } 100% { opacity:0; transform:translate(var(--dx,4px),-8px); } }
  @keyframes dg-alavanca { from { transform:rotate(-14deg); } to { transform:rotate(10deg); } }
  @keyframes dg-olha { 0%,40% { transform:translateX(-1px); } 50%,90% { transform:translateX(1.5px); } 100% { transform:translateX(-1px); } }
  @keyframes dg-pula { 0%,100% { transform:translateY(0); } 50% { transform:translateY(-5px); } }
  @keyframes dg-folha { 0% { transform:translate(0,0) rotate(-6deg); } 50% { transform:translate(22px,-12px) rotate(6deg); }
                        100% { transform:translate(44px,4px) rotate(-6deg); } }
  @keyframes dg-leva { 0%,100% { transform:rotate(-40deg); } 50% { transform:rotate(-95deg); } }
  @keyframes dg-pisca { 0% { opacity:1; } 100% { opacity:.25; } }
  @keyframes dg-inclina { 0%,100% { transform:rotate(-6deg); } 50% { transform:rotate(6deg); } }
  @keyframes dg-coca { from { transform:rotate(-155deg); } to { transform:rotate(-138deg); } }
  @keyframes dg-boia { 0%,100% { transform:translateY(0); } 50% { transform:translateY(-3px); } }
  @keyframes dg-viva { from { transform:rotate(150deg); } to { transform:rotate(172deg); } }
  @keyframes dg-entrega { 0% { transform:translateX(-3px); } 50% { transform:translateX(4px); } 100% { transform:translateX(-3px); } }
  @media (prefers-reduced-motion: reduce) { .r * { animation:none !important; } }
</style>
<div class="q st-consultando">
  <div class="cab">
    <div class="tit">eSocial · <b>FGTS</b><span class="lote"></span></div>
    <button class="x" title="Fechar o quadro (o script continua rodando)">✕</button>
  </div>
  <div class="meio">
    <svg class="robo r" viewBox="0 0 160 120" aria-hidden="true">
      <!-- SONDA DE MINERAÇÃO (cores da paleta: laranja suave = "amarelo" da máquina; azul = cabeçote/hidráulica) -->
      <g class="sonda">
        <!-- esteira e estabilizadores -->
        <rect x="46" y="94" width="96" height="10" rx="5" fill="#2e3a50"/>
        <circle cx="54" cy="99" r="3" fill="#1a2332"/><circle cx="68" cy="99" r="3" fill="#1a2332"/><circle cx="82" cy="99" r="3" fill="#1a2332"/>
        <circle cx="96" cy="99" r="3" fill="#1a2332"/><circle cx="110" cy="99" r="3" fill="#1a2332"/><circle cx="124" cy="99" r="3" fill="#1a2332"/>
        <circle cx="136" cy="99" r="3" fill="#1a2332"/>
        <rect x="43" y="89" width="3" height="15" fill="#7f8ba0"/><rect x="146" y="89" width="3" height="15" fill="#7f8ba0"/>
        <!-- plataforma -->
        <rect x="42" y="86" width="108" height="6" rx="1" fill="#232e40"/>
        <!-- motor / casa de máquinas -->
        <rect x="84" y="68" width="56" height="18" rx="3" fill="#de9a62"/>
        <rect x="90" y="72" width="3" height="11" fill="#b35f1c"/><rect x="96" y="72" width="3" height="11" fill="#b35f1c"/>
        <rect x="102" y="72" width="3" height="11" fill="#b35f1c"/>
        <rect x="122" y="60" width="16" height="9" rx="2" fill="#de9a62"/>
        <rect x="112" y="56" width="3" height="12" fill="#2e3a50"/>
        <circle class="lamp-ok" cx="131" cy="57" r="2.6" fill="#52be8c"/>
        <circle class="lamp-erro" cx="131" cy="57" r="2.6" fill="#de9a62"/>
        <!-- mangueiras hidráulicas -->
        <path d="M74 62 C 80 62 82 70 84 74" stroke="#1a2332" stroke-width="2" fill="none"/>
        <!-- torre (mastro) com treliça -->
        <rect x="64" y="8" width="9" height="80" fill="#de9a62"/>
        <path d="M64 16 L73 24 M73 24 L64 32 M64 32 L73 40 M73 40 L64 48 M64 48 L73 56 M73 56 L64 64 M64 64 L73 72 M73 72 L64 80"
              stroke="#b35f1c" stroke-width="1.2" fill="none"/>
        <rect x="60" y="5" width="17" height="4" rx="1" fill="#b35f1c"/>
        <!-- cabeçote + haste (descem e sobem juntos pela torre) -->
        <g class="cabecote">
          <rect x="67.5" y="38" width="2" height="80" fill="#a9b4c6"/>
          <line class="haste-gira" x1="68.5" y1="38" x2="68.5" y2="118" stroke="#7f8ba0" stroke-width="2" stroke-dasharray="2 3"/>
          <rect x="61" y="28" width="15" height="11" rx="2" fill="#4a94e0"/>
          <rect x="63" y="31" width="11" height="2" rx="1" fill="#1f6fc0"/>
        </g>
      </g>
      <!-- chão (cobre a haste que entrou no furo) -->
      <rect x="0" y="104" width="160" height="16" fill="#0e1522"/>
      <rect x="0" y="104" width="160" height="2" fill="#2e3a50"/>
      <ellipse cx="68.5" cy="105" rx="4" ry="1.4" fill="#0a101b"/>
      <circle class="po po1" cx="63" cy="102" r="1.6" fill="#7f8ba0" style="--dx:-5px"/>
      <circle class="po po2" cx="73" cy="102" r="1.4" fill="#7f8ba0" style="--dx:5px"/>
      <circle class="po po3" cx="68" cy="101" r="1.2" fill="#7f8ba0" style="--dx:2px"/>
      <!-- painel de comando da sonda -->
      <rect x="40" y="72" width="11" height="16" rx="1.5" fill="#1a2332"/>
      <rect x="42" y="75" width="7" height="2" rx="1" fill="#4a94e0"/><rect x="42" y="79" width="4" height="2" rx="1" fill="#52be8c"/>
      <!-- OPERADOR: robozinho DrillGeo de jaqueta azul com "DG" e capacete (de sonda) branco -->
      <g class="operador">
        <rect x="15" y="88" width="6" height="16" rx="2" fill="#2e3a50"/><rect x="25" y="88" width="6" height="16" rx="2" fill="#2e3a50"/>
        <g class="be"><rect x="7" y="68" width="6" height="17" rx="3" fill="#4a94e0"/><rect x="7.5" y="83" width="5" height="4" rx="2" fill="#a9b4c6"/></g>
        <rect x="12" y="65" width="22" height="25" rx="5" fill="#4a94e0"/>
        <rect x="22.4" y="66" width="1.2" height="23" fill="#1f6fc0"/>
        <rect x="14" y="70" width="8" height="6" rx="1" fill="#e4e9f1"/>
        <text x="18" y="74.8" text-anchor="middle" font-family="Inter,Calibri,sans-serif" font-size="4.6" font-weight="700" fill="#1f6fc0">DG</text>
        <rect x="12" y="84" width="22" height="2" fill="#1f6fc0"/>
        <g class="bd"><rect x="33" y="68" width="6" height="17" rx="3" fill="#4a94e0"/><rect x="33.5" y="83" width="5" height="4" rx="2" fill="#a9b4c6"/></g>
        <g class="cabeca">
          <rect x="20" y="60" width="6" height="6" rx="1.5" fill="#7f8ba0"/>
          <rect x="12" y="45" width="22" height="16" rx="5" fill="#a9b4c6"/>
          <rect x="14.5" y="49" width="17" height="9" rx="3" fill="#0e1522"/>
          <g class="olhos"><rect x="18" y="51.5" width="3" height="4" rx="1.5" fill="#4a94e0"/><rect x="25" y="51.5" width="3" height="4" rx="1.5" fill="#4a94e0"/></g>
          <!-- capacete -->
          <path d="M12.5 47 C12.5 36 33.5 36 33.5 47 Z" fill="#e4e9f1"/>
          <rect x="9.5" y="45.5" width="27" height="3" rx="1.5" fill="#cdd5e1"/>
          <rect x="21" y="39" width="4" height="4" rx="1" fill="#de9a62"/>
        </g>
      </g>
      <!-- folha que o operador leva até a sonda (trocando de pessoa) -->
      <g class="folha">
        <rect x="34" y="60" width="10" height="13" rx="1" fill="#e4e9f1" stroke="#7f8ba0" stroke-width=".8"/>
        <rect x="36" y="63" width="6" height="1.2" fill="#7f8ba0"/><rect x="36" y="66" width="6" height="1.2" fill="#7f8ba0"/>
        <rect x="36" y="69" width="4" height="1.2" fill="#7f8ba0"/>
      </g>
      <text class="pergunta" x="35" y="40" font-family="Inter,Calibri,sans-serif" font-size="14" font-weight="700" fill="#de9a62">?</text>
      <!-- ZIP entregue no fim -->
      <g class="zip">
        <rect x="36" y="88" width="16" height="13" rx="1.5" fill="#4a94e0"/>
        <rect x="42.5" y="88" width="3" height="13" fill="#1f6fc0"/>
        <text x="44" y="112" text-anchor="middle" font-family="Cascadia Mono,Consolas,monospace" font-size="6" fill="#e4e9f1">ZIP</text>
      </g>
    </svg>
    <div class="info">
      <div class="estado">Consultando</div>
      <div class="pessoa">preparando...</div>
      <div class="barra"><i></i></div>
      <div class="num"><span class="cont">0/0</span><span class="vel"></span></div>
      <div class="chips">
        <div class="chip ok"><b class="n-ok">0</b>OK</div>
        <div class="chip dv"><b class="n-dv">0</b>Divergentes</div>
        <div class="chip er"><b class="n-er">0</b>Erros</div>
      </div>
    </div>
  </div>
  <div class="nota">Não feche esta aba. No fim o ZIP é baixado.</div>
  <div class="log"></div>
</div>`;
    const $ = s => raiz.querySelector(s);
    const q = $(".q"), log = $(".log");
    $(".x").onclick = () => host.remove();
    (document.body || document.documentElement).appendChild(host);

    // ----- estado do painel (só lê as mensagens) -----
    const P = { total: 0, feitos: 0, ok: 0, dv: 0, er: 0, estado: "consultando", fim: false, timer: null };
    const NOMES = { consultando: "Consultando", trocando: "Trocando de pessoa", erro: "Tentando de novo", fim: "Concluído — ZIP baixado" };
    const lista = () => { try { return FUNCIONARIOS; } catch (e) { return []; } };   // a lista do próprio script (só leitura)
    function estado(s, rotulo) {
      if (P.fim && s !== "fim") return;
      P.estado = s;
      q.classList.remove("st-consultando", "st-trocando", "st-erro", "st-fim");
      q.classList.add("st-" + s);
      $(".estado").textContent = rotulo || NOMES[s];
      try { window.__dgRoboEstado = s; } catch (e) {}
    }
    function pessoaAtual() {
      const f = lista()[P.feitos];
      $(".pessoa").textContent = P.fim ? `${P.feitos} pessoas conferidas` : (f ? f.nome : "finalizando...");
    }
    function numeros() {
      const t = P.total || lista().length || 0;
      $(".cont").textContent = `${P.feitos}/${t} desta parte`;
      $(".barra i").style.width = (t ? Math.min(100, 100 * P.feitos / t) : 0) + "%";
      $(".n-ok").textContent = P.ok; $(".n-dv").textContent = P.dv; $(".n-er").textContent = P.er;
    }
    function ler(t, nivel) {
      let m;
      if ((m = t.match(/iniciando (\d+) consultas/i))) {
        P.total = +m[1];
        try { $(".lote").textContent = " · " + LOTE; } catch (e) {}
        estado("consultando"); pessoaAtual(); numeros();
      } else if ((m = t.match(/^\s*(\d+)\/(\d+)\s+(OK|DIVERGENTE|NAO ENCONTRADO|ERRO)\b/))) {
        P.feitos = +m[1]; P.total = +m[2];
        if (m[3] === "OK") P.ok++; else if (m[3] === "ERRO") P.er++; else P.dv++;
        numeros();
        clearTimeout(P.timer);
        estado(m[3] === "ERRO" ? "erro" : "trocando", m[3] === "ERRO" ? "Erro nesta pessoa — sigo adiante" : null);
        P.timer = setTimeout(() => { estado("consultando"); pessoaAtual(); }, 1300);
      } else if (/repescagem/i.test(t)) {
        estado("consultando", "Repescagem dos que deram erro");
      } else if ((m = t.match(/velocidade: .*média ([\d.,]+) s/))) {
        $(".vel").textContent = m[1] + " s/pessoa";
      } else if (/FIM –/.test(t)) {
        P.fim = true; clearTimeout(P.timer); estado("fim"); pessoaAtual(); numeros();
      } else if (nivel === "w" && /conexão caiu|nova tentativa/i.test(t)) {
        clearTimeout(P.timer); estado("erro", "O portal demorou — tentando de novo");
      } else if (nivel === "e" && /PAROU|Sessão expirada|não encontrado/i.test(t)) {
        clearTimeout(P.timer); estado("erro", "Parou — veja a mensagem abaixo");
      } else if (/Tela do eSocial aberta/.test(t)) {
        estado("consultando"); pessoaAtual();
      }
    }
    const texto = a => a.filter(x => !(typeof x === "string" && /^(color|font)[^:]*:/.test(x)))
      .map(x => typeof x === "string" ? x.replace(/%c/g, "") : (x && x.message) || String(x)).join(" ");
    const add = (cls, a) => {
      const t = texto(a);
      const d = document.createElement("div");
      if (cls) d.className = cls;
      d.textContent = t; d.title = t; log.prepend(d);
      try { ler(t, cls); } catch (e) {}
    };
    return { log: (...a) => { c.log(...a); add(/\bOK\b/.test(texto(a)) && /^\s*\d+\//.test(texto(a)) ? "k" : "", a); },
             warn: (...a) => { c.warn(...a); add("w", a); },
             error: (...a) => { c.error(...a); add("e", a); }, table: (...a) => c.table(...a) };
  })();

  // ------------------------------- CONFIG -------------------------------
  const COMPETENCIA = "09/2026";   // ex.: "09/2026"
  const CONCORRENCIA = 1;    // 1 por vez: o eSocial atende uma pesquisa por vez na mesma sessão (com 3, as outras
                             // ficavam na fila do servidor e davam "signal timed out" – 20/10/2026)
  const PAUSA_MS    = 900;   // pausa de cada "fila" entre uma consulta e outra
  const SALVAR_XML  = true;
  const SALVAR_HTML = false;  // true = salva também uma cópia da tela em HTML
  const TOLERANCIA  = 0.01;  // diferença aceitável em R$
  const LIMITE      = 0;     // teste: ponha 2 para rodar só os 2 primeiros; 0 = todos

  const LOTE = "PREVIA_P01de01";   // VALE_SUL | VALE_NORTE | VRCN | VRSTF – entra no nome dos ZIPs
  // Nome, CPF e "Valor FGTS" (linha NF) extraídos do Extrato Mensal da unidade.
  // A soma do campo fgts deve bater com "Valor do FGTS" + "Valor FGTS Rescisório" do resumo do extrato.
  const FUNCIONARIOS = [
    { nome: "ANA EXEMPLO DE TESTE", cpf: "111.111.111-11", fgts: 210.50 },
    { nome: "BRUNO MODELO SIMULADO", cpf: "222.222.222-22", fgts: 340.12 },
    { nome: "CARLA FICTICIA DA SILVA", cpf: "333.333.333-33", fgts: 455.80 },
    { nome: "DIEGO DEMONSTRACAO", cpf: "444.444.444-44", fgts: 198.33 },
    { nome: "ELIANE PREVIA SANTOS", cpf: "555.555.555-55", fgts: 512.07 },
    { nome: "FABIO ROBOZINHO LIMA", cpf: "666.666.666-66", fgts: 287.90 },
  ];

  if (!/^\d{2}\/\d{4}$/.test(COMPETENCIA) || !FUNCIONARIOS.length) {
    console.error("[FGTS] Preencha COMPETENCIA (MM/AAAA) e a lista FUNCIONARIOS antes de rodar.");
    return;
  }
  if (LIMITE > 0) FUNCIONARIOS.splice(LIMITE);

  // ------------------------------ UTILITÁRIOS ------------------------------
  const BASE = "https://www.esocial.gov.br";
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const brl = v => v == null ? "" : v.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const numBR = s => { const m = String(s || "").match(/-?[\d.]+,\d{2}/); return m ? parseFloat(m[0].replace(/\./g, "").replace(",", ".")) : null; };
  const limpo = s => (s || "").replace(/\s+/g, " ").trim();
  const nomeArquivo = s => limpo(s).replace(/[\\/:*?"<>|]/g, "").slice(0, 120);
  const parse = html => new DOMParser().parseFromString(html, "text/html");
  const abs = u => new URL(u, BASE).href;
  // O portal às vezes derruba a conexão (ERR_HTTP2_PROTOCOL_ERROR / "Failed to fetch") quando
  // recebe muitas consultas. fetchSeguro tenta de novo com espera crescente e, a cada queda,
  // reduz o número de consultas simultâneas (volta a subir depois de 5 acertos seguidos).
  let concAtual = 0, pausaAte = 0, falhasSeguidas = 0, acertosSeguidos = 0;
  async function fetchSeguro(url, opcoes) {
    for (let t = 1; ; t++) {
      while (Date.now() < pausaAte) await sleep(250);
      try {
        const r = await fetch(url, { ...(opcoes || {}), cache: "no-store", signal: AbortSignal.timeout(20000) });
        if (r.status === 429 || r.status >= 500) throw new Error(`HTTP ${r.status}`);
        falhasSeguidas = 0;
        if (++acertosSeguidos >= 5 && concAtual < CONCORRENCIA) { concAtual++; acertosSeguidos = 0; }
        return r;
      } catch (e) {
        acertosSeguidos = 0; falhasSeguidas++;
        concAtual = Math.max(1, concAtual - 1);
        const espera = Math.min(10000, 1000 * 2 ** (falhasSeguidas - 1));
        pausaAte = Math.max(pausaAte, Date.now() + espera);
        if (t >= 5) throw e;
        console.warn(`[FGTS] conexão caiu (${e.message}) – nova tentativa em ${espera / 1000}s, ${concAtual} consulta(s) por vez`);
      }
    }
  }
  const log = (...a) => console.log("%c[FGTS]", "color:#0a7;font-weight:bold", ...a);

  // --------- ZIP (sem compressão, sem biblioteca externa, nomes em UTF-8) ---------
  const CRC = (() => { const t = new Uint32Array(256); for (let n = 0; n < 256; n++) { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xEDB88320 ^ (c >>> 1) : c >>> 1; t[n] = c >>> 0; } return t; })();
  const crc32 = b => { let c = 0xFFFFFFFF; for (let i = 0; i < b.length; i++) c = CRC[(c ^ b[i]) & 0xFF] ^ (c >>> 8); return (c ^ 0xFFFFFFFF) >>> 0; };
  function criarZip(arquivos) {           // arquivos: [{nome, dados:Uint8Array}]
    const enc = new TextEncoder(), partes = [], central = [];
    const d = new Date(), hora = (d.getHours() << 11) | (d.getMinutes() << 5) | (d.getSeconds() >> 1);
    const data = ((d.getFullYear() - 1980) << 9) | ((d.getMonth() + 1) << 5) | d.getDate();
    let offset = 0;
    for (const a of arquivos) {
      const nome = enc.encode(a.nome), crc = crc32(a.dados), tam = a.dados.length;
      const h = new DataView(new ArrayBuffer(30));
      h.setUint32(0, 0x04034b50, true); h.setUint16(4, 20, true); h.setUint16(6, 0x0800, true);
      h.setUint16(8, 0, true); h.setUint16(10, hora, true); h.setUint16(12, data, true);
      h.setUint32(14, crc, true); h.setUint32(18, tam, true); h.setUint32(22, tam, true);
      h.setUint16(26, nome.length, true); h.setUint16(28, 0, true);
      partes.push(new Uint8Array(h.buffer), nome, a.dados);
      const c = new DataView(new ArrayBuffer(46));
      c.setUint32(0, 0x02014b50, true); c.setUint16(4, 20, true); c.setUint16(6, 20, true);
      c.setUint16(8, 0x0800, true); c.setUint16(10, 0, true); c.setUint16(12, hora, true); c.setUint16(14, data, true);
      c.setUint32(16, crc, true); c.setUint32(20, tam, true); c.setUint32(24, tam, true);
      c.setUint16(28, nome.length, true); c.setUint32(42, offset, true);
      central.push(new Uint8Array(c.buffer), nome);
      offset += 30 + nome.length + tam;
    }
    const tamCentral = central.reduce((s, p) => s + p.length, 0);
    const e = new DataView(new ArrayBuffer(22));
    e.setUint32(0, 0x06054b50, true); e.setUint16(8, arquivos.length, true); e.setUint16(10, arquivos.length, true);
    e.setUint32(12, tamCentral, true); e.setUint32(16, offset, true);
    return new Blob([...partes, ...central, new Uint8Array(e.buffer)], { type: "application/zip" });
  }

  // ----------------------------- ACESSO AO PORTAL -----------------------------
  // A URL da tela FGTS por Trabalhador leva um "id" de sessão que muda a cada página.
  // Sempre usamos o link mais recente (menu #menuFgtsTrabalhador ou action do formulário).
  let docAtual = document;
  function urlTelaFGTS(doc) {
    const a = doc.querySelector("#menuFgtsTrabalhador");
    return a ? abs(a.getAttribute("href")) : null;
  }
  function urlFormulario(doc) {
    const f = doc.querySelector("form[action*='FGTSPorTrabalhador']");
    return f ? abs(f.getAttribute("action")) : null;
  }
  async function abrirTela() {
    const url = urlTelaFGTS(docAtual) || urlTelaFGTS(document);
    if (!url) throw new Error("Menu FGTS por Trabalhador não encontrado. Abra uma página do eSocial logado e rode de novo.");
    const r = await fetchSeguro(url, { credentials: "include" });
    const doc = parse(await r.text());
    if (!urlFormulario(doc)) throw new Error("Sessão expirada ou tela diferente do esperado. Faça login novamente.");
    docAtual = doc;
  }
  async function consultar(cpf) {
    for (let tentativa = 1; tentativa <= 2; tentativa++) {
      let action = urlFormulario(docAtual);
      if (!action) { await abrirTela(); action = urlFormulario(docAtual); }
      const corpo = new URLSearchParams({ HabilitarPesquisaParcialCpf: "False", PeriodoApuracao: COMPETENCIA, Cpf: cpf });
      const r = await fetchSeguro(action, { method: "POST", credentials: "include", body: corpo,
        headers: { "Content-Type": "application/x-www-form-urlencoded" } });
      const doc = parse(await r.text());
      if (r.ok && urlFormulario(doc)) { docAtual = doc; return doc; }
      await abrirTela();   // id/sessão inválido → recarrega a tela e tenta de novo
    }
    throw new Error("Falha ao consultar (sessão expirada?)");
  }
  function lerResultado(doc) {
    const bloco = doc.querySelector(".totalizador-fgts-por-trabalhador");
    // Total de Depósitos (pode haver mais de um bloco, ex.: rescisão + mensal)
    const totais = [...doc.querySelectorAll("table.informacoes-finais tr")]
      .filter(tr => /Total de Dep[oó]sitos/i.test(tr.textContent))
      .map(tr => numBR(tr.querySelector("td.right")?.textContent));
    let nome = null, recibos = [];
    doc.querySelectorAll(".bloco-informacoes .form-group").forEach(g => {
      const rot = limpo(g.querySelector("label")?.textContent), val = limpo(g.querySelector("p")?.textContent);
      if (/^Nome$/i.test(rot) && !nome) nome = val;
      if (/Recibo/i.test(rot)) recibos.push(val);
    });
    const xmls = [...doc.querySelectorAll("a.download[href*='DownloadEvento']")].map(a => abs(a.getAttribute("href")));
    const msg = limpo(doc.querySelector("#mensagemGeral")?.textContent) ||
                limpo(doc.querySelector(".field-validation-error")?.textContent);
    return { bloco, nome, recibos, xmls, msg,
             total: totais.length ? Math.round(totais.reduce((s, v) => s + (v || 0), 0) * 100) / 100 : null };
  }
  function montarHTML(res, f, status) {
    const css = [...document.querySelectorAll("link[rel='stylesheet']")].map(l => `<link rel="stylesheet" href="${abs(l.getAttribute("href"))}">`).join("\n");
    const clone = res.bloco.cloneNode(true);
    clone.querySelectorAll("h2.titulo-tabela").forEach(h => { if (/Filtro de pesquisa/.test(h.textContent)) h.remove(); });
    clone.querySelectorAll("section.well, input, a.download").forEach(e => e.remove());
    return `<!DOCTYPE html><html><head><meta charset="utf-8"><base href="${BASE}/"><title>FGTS ${COMPETENCIA} - ${f.nome}</title>${css}
<style>body{background:#fff;padding:20px}.accordion>div{display:block!important}.conf{border:1px solid #999;padding:8px 12px;margin-bottom:16px;font:13px Arial}</style></head>
<body><div class="conf"><b>eSocial – FGTS por Trabalhador – Período ${COMPETENCIA}</b><br>
Folha (extrato): R$ ${brl(f.fgts)} &nbsp;|&nbsp; eSocial (total de depósitos): R$ ${brl(res.total)} &nbsp;|&nbsp; <b>${status}</b><br>
Gerado em ${new Date().toLocaleString("pt-BR")}</div>${clone.outerHTML}</body></html>`;
  }

  // ---------------------------------- EXECUÇÃO ----------------------------------
  const enc = new TextEncoder(), relatorio = [], usados = new Set();
  const arqAtivos = [], arqDemitidos = [];   // demitidos vão para um ZIP separado
  const nomeUnico = base => { let n = base, i = 2; while (usados.has(n)) n = `${base} (${i++})`; usados.add(n); return n; };
  log(`Iniciando ${FUNCIONARIOS.length} consultas – competência ${COMPETENCIA}`);
  alert(`[FGTS] Script carregado: ${FUNCIONARIOS.length} consultas, competência ${COMPETENCIA}.\nClique OK e acompanhe no QUADRO no canto direito da tela (não feche a aba). No fim baixa o ZIP.`);
  await abrirTela();
  log("Tela do eSocial aberta – consultando os CPFs...");

  // Processa vários CPFs ao mesmo tempo (CONCORRENCIA). O relatório sai na ordem do extrato.
  let abortar = false, feitos = 0, proximo = 0;
  const resultados = new Array(FUNCIONARIOS.length), nomesArq = [];
  async function processar(f, i) {
      const linha = { n: i + 1, nome: f.nome, cpf: f.cpf, folha: f.fgts, esocial: null, dif: null, status: "", obs: "", demitido: !!f.demitido };
      const arquivos = [];   // só entra no ZIP se a consulta terminar sem erro (evita duplicar na nova tentativa)
      try {
        const res = lerResultado(await consultar(f.cpf));
        if (res.total == null) {
          linha.status = "NAO ENCONTRADO";
          linha.obs = res.msg || "Sem resultado para o CPF/período";
        } else {
          linha.esocial = res.total;
          linha.dif = Math.round((res.total - f.fgts) * 100) / 100;
          linha.status = Math.abs(linha.dif) <= TOLERANCIA ? "OK" : "DIVERGENTE";
          // DEMITIDOS: no extrato, o "Valor FGTS" de quem foi dispensado pela empresa já inclui a
          // multa rescisória de 40%. A multa é apurada/recolhida no FGTS Digital e NÃO entra no
          // "Total de Depósitos" do eSocial. Por isso comparamos o eSocial com 8% da Base FGTS.
          if (linha.status === "DIVERGENTE" && f.demitido && f.baseFgts) {
            const deposito = Math.round(f.baseFgts * 0.08 * 100) / 100;
            if (Math.abs(res.total - deposito) <= 0.05) {   // eSocial trunca os 8% em cada parcela (mês, 13º, aviso) → pode dar alguns centavos a menos
              const multa = Math.round((f.fgts - deposito) * 100) / 100;
              linha.status = "OK"; linha.rescisao = true;
              linha.obs = `Rescisão: depósito 8% confere. Diferença de R$ ${brl(multa)} = multa 40% (recolhida no FGTS Digital)`;
            }
          }
          if (res.nome && limpo(res.nome).toUpperCase() !== f.nome.toUpperCase()) linha.obs += ` | Nome no eSocial: ${res.nome}`;
          const base = nomesArq[i] ??= nomeUnico(nomeArquivo(f.nome || res.nome));
          if (SALVAR_HTML && res.bloco) arquivos.push({ nome: `${base}.html`, dados: enc.encode(montarHTML(res, f, linha.status)) });
          if (SALVAR_XML) {
            for (const [k, url] of res.xmls.entries()) {
              const rx = await fetchSeguro(url, { credentials: "include" });
              const dados = new Uint8Array(await rx.arrayBuffer());
              if (!rx.ok || /<html/i.test(new TextDecoder().decode(dados.slice(0, 300)))) { linha.obs += " | XML não baixou"; continue; }
              arquivos.push({ nome: `${base}${res.xmls.length > 1 ? ` (${k + 1})` : ""}.xml`, dados });
            }
            if (!res.xmls.length) linha.obs += " | sem botão Baixar XML";
          }
        }
      } catch (e) {
        linha.status = "ERRO"; linha.obs = e.message;
        console.error(`[FGTS] ${f.nome}:`, e);
        if (/Sessão expirada/.test(e.message)) abortar = true;
      }
      if (linha.status !== "ERRO") (f.demitido ? arqDemitidos : arqAtivos).push(...arquivos);
    return linha;
  }
  async function trabalhador(_, id) {
    while (!abortar && proximo < FUNCIONARIOS.length) {
      if (id >= concAtual) { await sleep(500); continue; }   // fila "desligada" pelo freio
      const i = proximo++, f = FUNCIONARIOS[i];
      let linha = await processar(f, i);
      if (linha.status === "ERRO" && !abortar) {          // erro passageiro → 1 nova tentativa
        await sleep(2000);
        linha = await processar(f, i);
      }
      resultados[i] = linha;
      const cor = linha.status.startsWith("OK") ? "color:green" : "color:#c00;font-weight:bold";
      console.log(`%c${String(++feitos).padStart(2)}/${FUNCIONARIOS.length} ${linha.status.padEnd(14)} ${f.nome} – folha ${brl(f.fgts)} | eSocial ${brl(linha.esocial)} ${linha.obs.replace(/^ \| /, "")}`, cor);
      if (feitos % 10 === 0) { const s = (Date.now() - t0) / 1000; log(`velocidade: ${feitos} em ${Math.round(s)} s – média ${(s / feitos).toFixed(1)} s por pessoa`); }
      await sleep(PAUSA_MS);
    }
  }
  const t0 = Date.now();
  concAtual = Math.max(1, CONCORRENCIA);
  await Promise.all(Array.from({ length: concAtual }, trabalhador));
  // Repescagem: quem terminou em ERRO é consultado de novo, um por vez, depois de 5 s
  const comErro = resultados.map((l, i) => l && l.status === "ERRO" ? i : -1).filter(i => i >= 0);
  if (comErro.length && !abortar) {
    log(`Repescagem de ${comErro.length} CPF(s) com erro, um por vez...`);
    await sleep(5000); falhasSeguidas = 0;
    for (const i of comErro) {
      resultados[i] = await processar(FUNCIONARIOS[i], i);
      console.log(`   repescagem: ${resultados[i].status.padEnd(14)} ${FUNCIONARIOS[i].nome}`);
      await sleep(1000);
    }
  }
  relatorio.push(...resultados.filter(Boolean));
  if (abortar) console.warn("[FGTS] Sessão expirou no meio – o ZIP terá só o que foi processado. Faça login e rode de novo.");
  log(`Consultas concluídas em ${Math.round((Date.now() - t0) / 1000)} s`);

  // ------------------------------- RELATÓRIO + ZIP -------------------------------
  const cab = ["Nº", "Nome", "CPF", "Situação", "FGTS Folha", "FGTS eSocial (Total Depósitos)", "Diferença", "Status", "Observação"];
  const gerarCSV = linhas => "\uFEFF" + [cab, ...linhas.map(l => [l.n, l.nome, l.cpf, l.demitido ? "Demitido" : "Ativo", brl(l.folha), brl(l.esocial), brl(l.dif), l.status, l.obs.replace(/^ \| /, "")])]
    .map(r => r.map(c => `"${String(c).replace(/"/g, '""')}"`).join(";")).join("\r\n");
  function baixar(blob, nome) {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = nome;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 60000);
  }
  const comp = COMPETENCIA.replace("/", "-");
  const porNome = (x, y) => x.nome.localeCompare(y.nome, "pt-BR");
  arqAtivos.sort(porNome); arqDemitidos.sort(porNome);   // ordem alfabética dentro do ZIP
  // ZIP 1 – ativos (CSV com a conferência COMPLETA, ativos + demitidos)
  arqAtivos.unshift({ nome: "_CONFERENCIA_FGTS_" + LOTE + ".csv", dados: enc.encode(gerarCSV(relatorio)) });
  baixar(criarZip(arqAtivos), `eSocial_FGTS_${comp}_${LOTE}.zip`);
  // ZIP 2 – demitidos (CSV só com os demitidos)
  const relDem = relatorio.filter(l => l.demitido);
  if (relDem.length) {
    await sleep(1500);   // o Edge pode pedir "Permitir vários downloads" – clique em Permitir
    arqDemitidos.unshift({ nome: "_CONFERENCIA_FGTS_" + LOTE + "_DEMITIDOS.csv", dados: enc.encode(gerarCSV(relDem)) });
    baixar(criarZip(arqDemitidos), `eSocial_FGTS_${comp}_${LOTE}_DEMITIDOS.zip`);
  }

  const cont = s => relatorio.filter(l => l.status === s).length;
  const somaF = relatorio.reduce((s, l) => s + l.folha, 0), somaE = relatorio.reduce((s, l) => s + (l.esocial || 0), 0);
  console.table(relatorio.map(l => ({ Nome: l.nome, CPF: l.cpf, Folha: brl(l.folha), eSocial: brl(l.esocial), Dif: brl(l.dif), Status: l.status, Obs: l.obs })));
  log(`FIM – OK: ${cont("OK")} (${relatorio.filter(l => l.rescisao).length} de rescisão) | Divergentes: ${cont("DIVERGENTE")} | Não encontrados: ${cont("NAO ENCONTRADO")} | Erros: ${cont("ERRO")}`);
  log(`Total folha R$ ${brl(somaF)} | Total eSocial R$ ${brl(somaE)} | ZIP ativos: ${arqAtivos.length} arquivos | ZIP demitidos: ${relDem.length ? arqDemitidos.length : 0} arquivos`);
  window.esocialFgtsResultado = relatorio;   // fica disponível no Console
})().catch(e => {
  console.error("[FGTS] PAROU:", e);
  alert("[FGTS] O script parou: " + (e && e.message ? e.message : e) +
        "\n\nConfira se está logado no eSocial, na tela de Totalizadores, e rode de novo.");
});
