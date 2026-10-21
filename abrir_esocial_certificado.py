# -*- coding: utf-8 -*-
"""Abre o eSocial numa janela InPrivate do Edge e já clica em "Entrar com gov.br" e em "Seu certificado digital".
Daí em diante é com a pessoa: escolher o certificado e digitar o PIN (o script não toca em senha nem certificado).

Como funciona: abre um Edge separado (perfil temporário, InPrivate) com controle local ligado só em 127.0.0.1,
espera cada tela carregar e clica no botão certo. Assim que clica no certificado, o script termina.
Feche a janela do eSocial ao terminar o trabalho (o controle local acaba junto com ela).

Uso:  py -3 abrir_esocial_certificado.py            (normal)
      py -3 abrir_esocial_certificado.py --testar   (vai até a tela do gov.br e NÃO clica no certificado)
Só biblioteca padrão do Python (sem instalar nada)."""
import base64
import json
import os
import random
import socket
import struct
import subprocess
import sys
import tempfile
import time
import urllib.request

URL = 'https://login.esocial.gov.br/login.aspx'
EDGES = [r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe', r'C:\Program Files\Microsoft\Edge\Application\msedge.exe']
TESTAR = '--testar' in sys.argv


def aviso(msg):
    print(msg, flush=True)


# ---------- cliente WebSocket mínimo (só o necessário para falar com o Edge) ----------
class WS:
    def __init__(self, url):
        hostport, caminho = url[len('ws://'):].split('/', 1)
        host, porta = hostport.split(':')
        self.s = socket.create_connection((host, int(porta)), timeout=10)
        chave = base64.b64encode(os.urandom(16)).decode()
        self.s.sendall((f'GET /{caminho} HTTP/1.1\r\nHost: {hostport}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n'
                        f'Sec-WebSocket-Key: {chave}\r\nSec-WebSocket-Version: 13\r\n\r\n').encode())
        resp = b''
        while b'\r\n\r\n' not in resp:
            resp += self.s.recv(4096)
        if b' 101 ' not in resp.split(b'\r\n')[0]:
            raise RuntimeError('o Edge recusou a conexão de controle')
        self.n = 0

    def _enviar(self, texto):
        dados = texto.encode()
        cab = bytearray([0x81])
        if len(dados) < 126:
            cab.append(0x80 | len(dados))
        elif len(dados) < 65536:
            cab += bytes([0x80 | 126]) + struct.pack('>H', len(dados))
        else:
            cab += bytes([0x80 | 127]) + struct.pack('>Q', len(dados))
        mascara = os.urandom(4)
        self.s.sendall(bytes(cab) + mascara + bytes(b ^ mascara[i % 4] for i, b in enumerate(dados)))

    def _ler(self, n):
        b = b''
        while len(b) < n:
            parte = self.s.recv(n - len(b))
            if not parte:
                raise ConnectionError('conexão fechada')
            b += parte
        return b

    def _receber(self):
        msg = b''
        while True:
            b1, b2 = self._ler(2)
            tam = b2 & 0x7F
            if tam == 126:
                tam = struct.unpack('>H', self._ler(2))[0]
            elif tam == 127:
                tam = struct.unpack('>Q', self._ler(8))[0]
            msg += self._ler(tam)
            if b1 & 0x80:
                return msg.decode('utf-8', 'replace')

    def js(self, codigo):
        self.n += 1
        self._enviar(json.dumps({'id': self.n, 'method': 'Runtime.evaluate',
                                 'params': {'expression': codigo, 'returnByValue': True}}))
        while True:
            r = json.loads(self._receber())
            if r.get('id') == self.n:
                return r.get('result', {}).get('result', {}).get('value')


# ---------- abre o Edge ----------
edge = next((e for e in EDGES if os.path.exists(e)), None)
if not edge:
    aviso('Edge não encontrado neste computador.')
    sys.exit(1)
porta = random.randint(20000, 40000)
perfil = tempfile.mkdtemp(prefix='esocial_edge_')
subprocess.Popen([edge, '--inprivate', f'--remote-debugging-port={porta}', '--remote-debugging-address=127.0.0.1',
                  f'--user-data-dir={perfil}', '--no-first-run', '--no-default-browser-check', URL])
aviso('Abrindo o eSocial numa janela InPrivate...')

alvo = None
for _ in range(60):
    try:
        abas = json.load(urllib.request.urlopen(f'http://127.0.0.1:{porta}/json', timeout=2))
        alvo = next((a for a in abas if a.get('type') == 'page' and 'esocial' in a.get('url', '') + a.get('title', '').lower()), None)
        alvo = alvo or next((a for a in abas if a.get('type') == 'page'), None)
        if alvo:
            break
    except Exception:
        pass
    time.sleep(0.5)
if not alvo:
    aviso('Não consegui controlar a janela do Edge. Faça o login pelo botão normalmente.')
    sys.exit(1)

# ---------- clica nos botões ----------
PASSO = r'''(() => {
  const h = location.hostname;
  if (h === 'login.esocial.gov.br') {
    const b = document.querySelector('button.sign-in');
    if (b && document.readyState === 'complete') { b.click(); return 'clicou-govbr'; }
    return 'esperando-esocial';
  }
  if (h === 'sso.acesso.gov.br') {
    const c = document.querySelector('#login-certificate');
    if (!c || document.readyState !== 'complete') return 'esperando-govbr';
    if (__TESTAR__) return 'teste-ok';
    c.click(); return 'clicou-certificado';
  }
  return 'outra:' + h;
})()'''.replace('__TESTAR__', 'true' if TESTAR else 'false')

ws = None
fim = time.time() + 90
estado = ''
while time.time() < fim:
    try:
        ws = ws or WS(alvo['webSocketDebuggerUrl'])
        estado = ws.js(PASSO) or ''
    except Exception:
        ws = None                      # a página trocou: reconecta
        estado = 'reconectando'
    if estado == 'clicou-govbr':
        aviso('eSocial: clicou em "Entrar com gov.br".')
        time.sleep(2)
    elif estado == 'teste-ok':
        aviso('TESTE OK: chegou na tela do gov.br e achou "Seu certificado digital" (não clicou).')
        break
    elif estado == 'clicou-certificado':
        aviso('gov.br: clicou em "Seu certificado digital". Escolha o certificado da Drillgeo e digite o PIN.')
        break
    else:
        time.sleep(0.7)
else:
    aviso(f'Parou sem concluir (última tela: {estado}). Termine o login clicando normalmente.')
