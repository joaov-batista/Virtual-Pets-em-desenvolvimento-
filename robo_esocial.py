# -*- coding: utf-8 -*-
"""Robô eSocial: roda TODA a sequência de scripts (FGTS ou INSS) de 10 em 10, sozinho.

Ciclo para cada parte:  abre um Edge NOVO  ->  entra (gov.br > certificado, Enter automático no único certificado)
                        ->  roda a parte de 10  ->  baixa o ZIP  ->  sai do eSocial  ->  FECHA o Edge  ->  próxima parte.
A escolha do certificado é automática: na janela "Selecionar um certificado" DESTE Edge o robô seleciona o da
DRILLGEO e aperta OK pela acessibilidade do Windows (escolher_certificado.ps1) – sem teclas simuladas, nunca em outro
programa. Se não achar a janela, não faz nada e você escolhe. O robô não digita senha nem PIN.
Não aparece "permitir colagem" (o script é injetado na página, não colado) nem "permitir vários downloads" (liberado).

Uso:  py -3 robo_esocial.py fgts            (ou inss)
      py -3 robo_esocial.py fgts --desde 7  (recomeça da 7ª parte da sequência)
      Retoma sozinho: pula as partes que já têm ZIP na pasta ZIPs (--refazer ignora e roda tudo).
      py -3 robo_esocial.py fgts --testar   (só lista a sequência e vai até a tela do gov.br, sem clicar no certificado)
      py -3 robo_esocial.py fgts --testar-certificado  (abre a janela do certificado, seleciona e aperta CANCELAR)
Opções: --comp 09.2026 (padrão: a pasta de mês mais recente em Conferencia Claudinho\\eSocial)
Os ZIPs vão para  Conferencia Claudinho\\eSocial\\<MM.AAAA>\\ZIPs ; o andamento fica em _andamento_<tipo>.txt.
Só biblioteca padrão do Python."""
import base64
import datetime as dt
import glob
import json
import os
import random
import re
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time
import urllib.request

ESOCIAL = os.path.join(r'C:\Users', os.environ.get('USERNAME', ''), r'DrillGeo Dropbox\RH-DP\Conferencia Claudinho\eSocial')
if not os.path.isdir(ESOCIAL):
    ESOCIAL = r'C:\Users\USUARIO 1\DrillGeo Dropbox\RH-DP\Conferencia Claudinho\eSocial'
EDGES = [r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe', r'C:\Program Files\Microsoft\Edge\Application\msedge.exe']
LOGIN = 'https://login.esocial.gov.br/login.aspx'
LOGOUT = 'https://login.esocial.gov.br/Logout.aspx'
ORDEM_UNIDADES = ['VALE_NORTE', 'VALE_SUL', 'VRCN', 'VRTSF']
CFG = {'fgts': {'pasta': 'FGTS', 'menu': '#menuFgtsTrabalhador', 'res': 'esocialFgtsResultado', 'padrao': 'esocial_fgts_*.js'},
       'inss': {'pasta': 'INSS', 'menu': '#menuContribuicaoSocialTrabalhador', 'res': 'esocialInssResultado', 'padrao': 'INSS_*.js'}}

args = sys.argv[1:]
if not args or args[0].lower() not in CFG:
    print(__doc__)
    sys.exit(1)
TIPO = args[0].lower()
C = CFG[TIPO]
TESTAR_CERT = '--testar-certificado' in args   # clica no certificado, seleciona e aperta CANCELAR
TESTAR = '--testar' in args and not TESTAR_CERT
DESDE = int(args[args.index('--desde') + 1]) if '--desde' in args else 1
COMP = args[args.index('--comp') + 1] if '--comp' in args else \
    sorted((d for d in os.listdir(ESOCIAL) if re.fullmatch(r'\d{2}\.\d{4}', d)), key=lambda d: (d[3:], d[:2]))[-1]
BASE = os.path.join(ESOCIAL, COMP)
ZIPS = os.path.join(BASE, 'ZIPs')
os.makedirs(ZIPS, exist_ok=True)
LOG = os.path.join(ZIPS, f'_andamento_{TIPO}.txt')


def aviso(msg):
    linha = f'{dt.datetime.now():%H:%M:%S}  {msg}'
    print(linha, flush=True)
    with open(LOG, 'a', encoding='utf-8') as f:
        f.write(linha + '\n')


def chave(arq):
    n = os.path.basename(arq)
    u = next((i for i, x in enumerate(ORDEM_UNIDADES) if f'_{x}_' in n), 99)
    m = re.search(r'_(\d+)de(\d+)\.js$', n)
    return (u, int(m.group(1)) if m else 0)


PARTES = sorted(glob.glob(os.path.join(BASE, C['pasta'], C['padrao'])), key=chave)


# ---------------- WebSocket mínimo + protocolo do Edge (DevTools) ----------------
class CDP:
    def __init__(self, url):
        hostport, caminho = url[len('ws://'):].split('/', 1)
        h, p = hostport.split(':')
        self.s = socket.create_connection((h, int(p)), timeout=15)
        k = base64.b64encode(os.urandom(16)).decode()
        self.s.sendall((f'GET /{caminho} HTTP/1.1\r\nHost: {hostport}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n'
                        f'Sec-WebSocket-Key: {k}\r\nSec-WebSocket-Version: 13\r\n\r\n').encode())
        r = b''
        while b'\r\n\r\n' not in r:
            r += self.s.recv(4096)
        if b' 101 ' not in r.split(b'\r\n')[0]:
            raise RuntimeError('o Edge recusou a conexão')
        self.n = 0

    def _env(self, txt):
        d = txt.encode()
        cab = bytearray([0x81])
        cab += bytes([0x80 | len(d)]) if len(d) < 126 else (bytes([0x80 | 126]) + struct.pack('>H', len(d)) if len(d) < 65536
                                                            else bytes([0x80 | 127]) + struct.pack('>Q', len(d)))
        m = os.urandom(4)
        self.s.sendall(bytes(cab) + m + bytes(b ^ m[i % 4] for i, b in enumerate(d)))

    def _ler(self, n):
        b = b''
        while len(b) < n:
            x = self.s.recv(n - len(b))
            if not x:
                raise ConnectionError('conexão fechada')
            b += x
        return b

    def _rec(self):
        msg = b''
        while True:
            b1, b2 = self._ler(2)
            t = b2 & 0x7F
            if t == 126:
                t = struct.unpack('>H', self._ler(2))[0]
            elif t == 127:
                t = struct.unpack('>Q', self._ler(8))[0]
            msg += self._ler(t)
            if b1 & 0x80:
                return msg.decode('utf-8', 'replace')

    def call(self, metodo, params=None, espera=15):
        self.n += 1
        self.s.settimeout(espera)
        self._env(json.dumps({'id': self.n, 'method': metodo, 'params': params or {}}))
        while True:
            r = json.loads(self._rec())
            if r.get('id') == self.n:
                if 'error' in r:
                    raise RuntimeError(r['error'].get('message'))
                return r.get('result', {})

    def js(self, codigo, espera=15, promessa=False):
        r = self.call('Runtime.evaluate', {'expression': codigo, 'returnByValue': True, 'awaitPromise': promessa}, espera)
        return r.get('result', {}).get('value')

    def fechar(self):
        try:
            self.s.close()
        except Exception:
            pass


# ---------------- Edge ----------------
edge = next((e for e in EDGES if os.path.exists(e)), None)
if not edge:
    print('Edge não encontrado.')
    sys.exit(1)
aviso(f'===== Robô eSocial {TIPO.upper()} {COMP}: {len(PARTES)} partes; começando na {DESDE}ª =====')
for i, p in enumerate(PARTES, 1):
    print(f'   {i:2d}. {os.path.basename(p)}{"   (pular)" if i < DESDE else ""}')
if not PARTES:
    aviso('Nenhum script encontrado na pasta ' + os.path.join(BASE, C['pasta']))
    sys.exit(1)


# ---------------- um Edge NOVO por parte (fecha tudo no fim de cada parte: sessão limpa = portal rápido) ----------------
def abrir_edge():
    porta = random.randint(20000, 40000)
    perfil = tempfile.mkdtemp(prefix='esocial_robo_')          # perfil temporário: sem cookies nem cache (anônimo)
    # InPrivate: o Edge não entra na conta Microsoft nem mostra "Estamos sincronizando seus dados"
    proc = subprocess.Popen([edge, '--inprivate', f'--remote-debugging-port={porta}', '--remote-debugging-address=127.0.0.1',
                             f'--user-data-dir={perfil}', '--no-first-run', '--no-default-browser-check', '--disable-sync',
                             '--disable-features=msEdgeSidebarV2,msImplicitSignin', 'about:blank'])
    base = f'http://127.0.0.1:{porta}/json'
    for _ in range(60):
        try:
            ver = json.load(urllib.request.urlopen(base + '/version', timeout=2))
            pags = [a for a in json.load(urllib.request.urlopen(base, timeout=2)) if a.get('type') == 'page']
            if pags:
                break
        except Exception:
            pass
        time.sleep(0.5)
    else:
        raise RuntimeError('não consegui controlar o Edge')
    nav = CDP(ver['webSocketDebuggerUrl'])
    e = {'proc': proc, 'perfil': perfil, 'nav': nav, 'base': base, 'pg': None}
    conectar_aba(e)
    return e


def conectar_aba(e):
    """Liga o robô à aba de trabalho. Num Edge recém-aberto a 1ª aba pode ser uma página interna (boas-vindas,
    nova guia): prefere a aba about:blank/eSocial; se não houver, abre uma aba nova."""
    if e.get('pg'):
        e['pg'].fechar()
    pags = [a for a in json.load(urllib.request.urlopen(e['base'], timeout=5)) if a.get('type') == 'page']
    boa = next((a for a in pags if a.get('url', '').startswith(('about:blank', 'https://login.esocial', 'https://sso.acesso',
                                                                    'https://www.esocial'))), None)
    if not boa:
        t = e['nav'].call('Target.createTarget', {'url': 'about:blank'})['targetId']
        time.sleep(1)
        boa = next(a for a in json.load(urllib.request.urlopen(e['base'], timeout=5)) if a.get('id') == t)
    e['pg'] = CDP(boa['webSocketDebuggerUrl'])
    e['pg'].call('Page.enable')
    # downloads liberados direto na pasta ZIPs (sem a pergunta "permitir vários downloads") – por aba, vale no InPrivate
    e['pg'].call('Page.setDownloadBehavior', {'behavior': 'allow', 'downloadPath': ZIPS})
    # o gov.br pede a localização: responde "não" antes de perguntar, então o aviso não aparece
    e['pg'].call('Page.addScriptToEvaluateOnNewDocument', {'source': (
        'if (navigator.geolocation) { const nao = (ok, erro) => erro && erro({code: 1, message: "negado"});'
        ' navigator.geolocation.getCurrentPosition = nao; navigator.geolocation.watchPosition = (ok, erro) => { nao(ok, erro); return 0; }; }')})
    e['pg'].call('Page.bringToFront')


def fechar_edge(e):
    try:
        e['pg'].call('Page.navigate', {'url': LOGOUT})        # sai do eSocial antes de fechar
        time.sleep(3)
    except Exception:
        pass
    try:
        e['nav'].call('Browser.close', espera=5)
    except Exception:
        pass
    for k in ('pg', 'nav'):
        e[k].fechar()
    try:
        e['proc'].wait(timeout=15)
    except Exception:
        e['proc'].kill()
    for _ in range(5):                      # o Edge às vezes demora a soltar os arquivos do perfil temporário
        shutil.rmtree(e['perfil'], ignore_errors=True)
        if not os.path.exists(e['perfil']):
            break
        time.sleep(1)


PS_CERT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'escolher_certificado.ps1')


def escolher_certificado(perfil, confirmar=True):
    """Na janela "Selecionar um certificado" DESTE Edge: seleciona o certificado da DRILLGEO e aperta OK (ou Cancelar,
    no teste). Sem teclas simuladas: usa a acessibilidade do Windows, só na janela do Edge do robô."""
    try:
        r = subprocess.run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', PS_CERT, '-Perfil', perfil,
                            '-Confirmar', '1' if confirmar else '0'], capture_output=True, text=True, timeout=40)
        return (r.stdout.strip().splitlines() or ['erro'])[-1]
    except Exception as x:
        return f'erro ({x})'


PASSO = r'''(() => {
  const h = location.hostname;
  if (document.querySelector('__MENU__')) return 'logado';
  if (h === 'login.esocial.gov.br') {
    const b = document.querySelector('button.sign-in');
    if (b && document.readyState === 'complete') { b.click(); return 'clicou-govbr'; }
    return 'esperando-esocial';
  }
  if (h === 'sso.acesso.gov.br') {
    const c = document.querySelector('#login-certificate');
    if (!c || document.readyState !== 'complete') return 'esperando-govbr';
    if (__TESTAR__) return 'teste-ok';
    if (window.__roboClicou) return 'esperando-certificado';
    window.__roboClicou = true; c.click(); return 'clicou-certificado';
  }
  return 'tela:' + h + location.pathname;
})()'''.replace('__MENU__', C['menu']).replace('__TESTAR__', 'true' if TESTAR else 'false')


def entrar(e, limite):
    e['pg'].call('Page.navigate', {'url': LOGIN})
    fim, ult, t_cert, enters = time.time() + limite, '', None, 0
    parado_desde, tentativas, quedas = time.time(), 0, 0
    while time.time() < fim:
        try:
            st = e['pg'].js(PASSO) or ''
        except Exception:
            st = 'carregando'
        # o gov.br às vezes derruba a conexão do certificado (ERR_CONNECTION_RESET, página de erro do Edge).
        # 2 etapas (pedido da usuária, 20/10/2026): 1) espera 10 s e ATUALIZA a página (F5) – a janela do certificado
        # volta e o robô escolhe de novo; 2) se cair de novo, RECOMEÇA o login do zero. Repete o par até 3 vezes.
        if t_cert and st.startswith('tela:chromewebdata'):
            quedas += 1
            if quedas > 6:
                aviso('   o gov.br derrubou a conexão do certificado 6 vezes seguidas – sigo para a próxima parte.')
                return False
            try:
                if quedas % 2 == 1:
                    aviso('   o gov.br derrubou a conexão do certificado – esperando 10 s e atualizando a página')
                    time.sleep(10)
                    e['pg'].call('Page.reload', {'ignoreCache': True})
                    t_cert = time.time()
                else:
                    aviso('   caiu de novo depois de atualizar – recomeçando o login')
                    e['pg'].call('Page.navigate', {'url': LOGIN})
                    t_cert = None
            except Exception:
                pass
            enters, ult = 0, ''
            fim = max(fim, time.time() + 90)
            time.sleep(1)
            continue
        # 15 s sem chegar ao eSocial/gov.br (aba errada ou travada): reconecta e abre o login de novo
        if (st == 'carregando' or st.startswith('tela:')) and not t_cert:
            if time.time() - parado_desde > 15 and tentativas < 3:
                tentativas += 1
                aviso(f'   a página não respondeu ({st}) – tentando de novo')
                try:
                    conectar_aba(e)
                    e['pg'].call('Page.navigate', {'url': LOGIN})
                except Exception:
                    pass
                parado_desde = time.time()
        else:
            parado_desde = time.time()
        if st == 'logado':
            return True
        if st == 'teste-ok':
            aviso('   TESTE OK: chegou na tela do gov.br e achou "Seu certificado digital" (não clicou).')
            return False
        if st == 'clicou-certificado':
            t_cert = time.time()
        # a janela do certificado é do Edge (não da página): seleciona o certificado e aperta OK nela (até 2 vezes)
        na_tela_cert = st in ('esperando-certificado', 'carregando', 'esperando-govbr') or st.startswith('tela:certificado.sso')
        if t_cert and na_tela_cert and time.time() - t_cert > 1.5 + 6 * enters and enters < 2:
            enters += 1
            r = escolher_certificado(e['perfil'], confirmar=not TESTAR_CERT)
            if r.startswith('teste-ok'):
                aviso(f'   TESTE OK: achou o certificado da DRILLGEO e apertou CANCELAR, sem entrar ({r}).')
                return False
            aviso('   certificado: ' + (f'escolheu o da DRILLGEO e apertou OK – {r}' if r.startswith('ok') else f'não consegui ({r}) – escolha você'))
        if st != ult and not st.startswith('esperando') and st != 'carregando':
            aviso({'clicou-govbr': '   eSocial: clicou em "Entrar com gov.br"',
                   'clicou-certificado': '   gov.br: clicou em "Seu certificado digital"'}
                  .get(st, f'   aguardando ({st}) – se o eSocial pedir algo (perfil, aviso), clique você'))
        ult = st
        time.sleep(1)
    aviso('   Não entrou no eSocial a tempo.')
    return False


# ---------------- ciclo ----------------
resumo = []
PAUSA_ENTRE = 20                            # segundos entre fechar um Edge e abrir o próximo (o gov.br não gosta de pressa)


def zip_da_parte(arq):
    """Nome do ZIP que a parte baixa (ex.: eSocial_FGTS_09-2026_VALE_NORTE_P01de12.zip)."""
    m = re.search(r'_(VALE_NORTE|VALE_SUL|VRCN|VRTSF)_(\d+)de(\d+)\.js$', os.path.basename(arq))
    if not m:
        return None
    return os.path.join(ZIPS, f'eSocial_{TIPO.upper()}_{COMP.replace(".", "-")}_{m.group(1)}_P{int(m.group(2)):02d}de{int(m.group(3)):02d}.zip')


fazer = [(i, a) for i, a in enumerate(PARTES, 1) if i >= DESDE]
if not ('--refazer' in args or TESTAR or TESTAR_CERT):   # retoma sozinho: pula as partes que já têm ZIP na pasta
    feitas = [i for i, a in fazer if zip_da_parte(a) and os.path.exists(zip_da_parte(a))]
    if feitas:
        aviso(f'Já feitas (ZIP na pasta), vou pular: partes {feitas}. Para refazer tudo: --refazer')
    fazer = [(i, a) for i, a in fazer if i not in feitas]
if TESTAR or TESTAR_CERT:
    fazer = fazer[:1 if TESTAR_CERT else 2]                       # teste: abre e fecha o Edge 2 vezes, sem clicar no certificado
for i, arq in fazer:
    nome = os.path.basename(arq)
    aviso(f'Parte {i}/{len(PARTES)}: {nome} – abrindo um Edge novo...')
    try:
        e = abrir_edge()
    except Exception as x:
        aviso(f'   {x}. Para continuar:  py -3 robo_esocial.py {TIPO} --desde {i}')
        break
    if not entrar(e, 180):
        fechar_edge(e)
        if TESTAR or TESTAR_CERT:
            aviso('   Edge fechado.')
            continue
        aviso(f'   Não entrou na parte {i}: sigo para a próxima; esta fica sem ZIP e é refeita quando abrir o robô de novo.')
        time.sleep(PAUSA_ENTRE)
        continue
    aviso('   rodando a parte...')
    # o script é injetado direto na página: não passa pelo Console, então não aparece "permitir colagem"
    codigo = 'window.alert = m => console.log("[aviso] " + m);\n' + open(arq, encoding='utf-8').read()
    t0 = time.time()
    try:
        e['pg'].js(codigo, espera=1800, promessa=True)
        st = json.loads(e['pg'].js(f'JSON.stringify((window.{C["res"]} || []).map(l => l.status))') or '[]')
    except Exception as x:
        st = []
        aviso(f'   erro ao rodar: {x}')
    cont = {s: st.count(s) for s in sorted(set(st))}
    aviso(f'   terminou em {round(time.time() - t0)} s: {len(st)} pessoas {cont}')
    resumo.append((i, nome, len(st), cont))
    time.sleep(3)                           # deixa o ZIP terminar de baixar
    fechar_edge(e)
    aviso('   saiu do eSocial e fechou o Edge.')
    if not st:
        aviso(f'   Sem resultado nesta parte (sem ZIP): na próxima vez que abrir o robô ele tenta de novo.')
    if (i, arq) != fazer[-1]:
        aviso(f'   esperando {PAUSA_ENTRE} s antes da próxima parte...')
        time.sleep(PAUSA_ENTRE)

if not (TESTAR or TESTAR_CERT):
    aviso('===== FIM =====')
    for i, nome, n, cont in resumo:
        aviso(f'   {i:2d}. {nome}: {n} pessoas {cont}')
    aviso(f'ZIPs em: {ZIPS}')
