# -*- coding: utf-8 -*-
"""Robozinho DrillGeo - assistente de mesa.

Robô animado que anda pela base da tela e manda perguntas para o Claude Code
(claude -p), rodando na pasta do cofre "Segundo cerebro" para seguir o CLAUDE.md.

Só usa a biblioteca padrão do Python (tkinter + ctypes). Pillow é opcional e só
serve para desenhar o ícone do atalho (--criar-atalho).

Uso:
    pythonw robozinho.py                 abre o robô
    python  robozinho.py --criar-atalho  cria o atalho na área de trabalho
    python  robozinho.py --demo PASTA    teste: passa por todas as animações e salva prints
"""

import sys
import os

try:
    import tkinter as tk
    import tkinter.font as tkfont
except Exception:  # Python sem tkinter
    import ctypes
    ctypes.windll.user32.MessageBoxW(
        0, "O Python deste computador está sem o tkinter (parte gráfica).\n\n"
           "Reinstale o Python pelo site python.org marcando a opção \"tcl/tk and IDLE\".",
        "Robozinho DrillGeo", 0x30)
    sys.exit(1)

import ctypes
import json
import math
import queue
import random
import shutil
import subprocess
import threading
import time
import traceback
import uuid
from ctypes import wintypes
from pathlib import Path
from tkinter import filedialog

import funcoes as fn
import jogos

PASTA = Path(__file__).resolve().parent          # ...\Claude outputs\Robozinho DrillGeo
COFRE = PASTA.parents[1]                         # ...\Segundo cerebro
CONFIG = PASTA / "config.json"
LOG = PASTA / "erro.log"
NOME = "Robozinho DrillGeo"

LIMITE_SEG = 180          # tempo máximo de espera pelo Claude
SONO_SEG = 900            # parado sem ninguém mexer -> dorme (15 min; era 3)
SONO_ANDANDO_SEG = 1800   # andando sem ninguém mexer -> cansa e dorme (30 min; era 10)
SONECA_SEG = 90           # cochilo sozinho dura pouco: depois levanta e volta ao trabalho
EVENTO_SEG = (100, 260)   # intervalo entre problemas (chuva, petróleo, água, rocha dura...)
QUADRO_MS = 50            # 20 quadros por segundo

# Cores do design system DrillGeo (drillgeo.css, tema escuro). Nada fora dos tokens.
BG = "#0e1522"
SURFACE = "#151d2b"
SURFACE2 = "#1a2332"
HOVER = "#1f2939"
LINE = "#232e40"
LINE2 = "#2e3a50"
TX = "#e4e9f1"
TX2 = "#a9b4c6"
TX3 = "#7f8ba0"
ACCENT = "#4a94e0"
ACCENT_ESC = "#1f6fc0"    # accent do tema claro (capacete)
OK = "#52be8c"
WARN = "#de9a62"
BAD = "#e27b73"
CONSOLE = "#0a101b"
ATIVO = "#1a2a42"
CLARO = "#f3f5f9"
TRANSP = "#020304"        # cor-chave da transparência (quase preta: borda de texto vira sombra, não rosa)

# Instrução extra para respostas que cabem num balão.
SISTEMA_LEITURA = (
    "Você está respondendo pelo Robozinho DrillGeo, um balão pequeno na tela da equipe de RH/DP. "
    "Responda em português, curto e direto (de preferência até 12 linhas), em texto simples, sem tabelas largas. "
    "MODO SÓ LEITURA: você não pode criar, alterar ou apagar arquivos nem rodar comandos, e não há registro no cofre. "
    "Se o pedido exigir alterar algo, explique o que faria e diga para repetir a mensagem começando com !fazer. "
    "Cálculos, traduções e textos curtos: responda direto. Dúvidas de RH/DP: consulte as notas do cofre."
)
SISTEMA_FAZER = (
    "Você está respondendo pelo Robozinho DrillGeo, um balão pequeno na tela da equipe de RH/DP. "
    "Responda em português e termine com um resumo curto do que foi feito e quais arquivos mudaram. "
    "A usuária confirmou que você pode criar e alterar arquivos nesta tarefa. Siga o CLAUDE.md "
    "(nunca apagar nem sobrescrever sem pedido). Comandos de terminal não estão liberados."
)
SISTEMA_EXTERNO = (
    "Você é o Robozinho DrillGeo, assistente da equipe de RH/DP da DrillGeo (sondagem e perfuração). "
    "Responda em português do Brasil, curto e direto (até 12 linhas), em texto simples, sem tabelas largas. "
    "Você não tem acesso aos arquivos da empresa; se a pergunta depender deles, diga que o Claude do cofre responde melhor."
)

# Tamagotchi: o que sai do furo (nome, cor, chance, valor mínimo, valor máximo). Só cores dos tokens.
MINERIOS = [("Rocha", TX3, 0.48, 8, 18), ("Ferro", BAD, 0.25, 20, 35), ("Cobre", WARN, 0.15, 35, 60),
            ("Diamante", ACCENT, 0.09, 80, 130), ("Esmeralda", OK, 0.03, 180, 260)]
METAS = [(1, "Primeiro testemunho"), (5, "Sondador iniciante"), (10, "10 testemunhos"),
         (25, "Sondador de respeito"), (50, "Meio cento de furos"), (100, "Lenda da sondagem")]
# Peças da sonda: chave -> (nome, revisão que cuida dela, preço da peça nova)
PECAS = {"broca": ("Broca", "mecanica", 60), "haste": ("Haste", "mecanica", 45),
         "bomba": ("Bomba de lama", "mecanica", 80), "motor": ("Motor", "mecanica", 150),
         "painel": ("Painel elétrico", "eletrica", 90), "fiacao": ("Fiação", "eletrica", 40),
         "bateria": ("Bateria", "eletrica", 55)}
REVISAO = {"mecanica": ("Revisão mecânica", 30), "eletrica": ("Revisão elétrica", 25)}   # taxa fixa
CUSTO_SUJA = 1.5          # sonda suja de petróleo: manutenção e peças 50% mais caras
VIDA_PADRAO = {"energia": 100.0, "oleo": 100.0, "humor": 80.0, "sonda": 100.0, "quebrada": False, "suja": False,
               "dinheiro": 30, "testemunhos": 0, "premios": [], "minerios": {}, "furo": 0.0, "metros": 0.0,
               "usos": {}, "uso_dia": {}}


# ----------------------------------------------------------------------------
# Windows: área de trabalho, DPI, estilo da janela, instância única
# ----------------------------------------------------------------------------

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32


def ligar_dpi():
    """Sem isso o Windows estica a janela e a cor-chave vaza nas bordas."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass


def area_de_trabalho():
    """Retângulo da tela principal sem a barra de tarefas."""
    r = wintypes.RECT()
    user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(r), 0)  # SPI_GETWORKAREA
    return r.left, r.top, r.right, r.bottom


def esconder_da_barra(janela):
    """Janela de ferramenta: fora da barra de tarefas e do Alt+Tab."""
    janela.update_idletasks()
    hwnd = user32.GetParent(janela.winfo_id()) or janela.winfo_id()
    GWL_EXSTYLE, WS_EX_TOOLWINDOW, WS_EX_APPWINDOW = -20, 0x80, 0x40000
    estilo = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    user32.SetWindowLongW(hwnd, GWL_EXSTYLE, (estilo | WS_EX_TOOLWINDOW) & ~WS_EX_APPWINDOW)


def trazer_para_frente(janela):
    try:
        hwnd = user32.GetParent(janela.winfo_id()) or janela.winfo_id()
        user32.SetForegroundWindow(hwnd)
    except Exception:
        pass
    janela.focus_force()


WM_DROPFILES = 0x0233
WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)


def aceitar_arquivos(root, canvas, ao_soltar):
    """Arrastar arquivos do Explorer para cima do robô (WM_DROPFILES, sem biblioteca extra).
    Devolve as funções de retorno: precisam ficar guardadas enquanto o robô estiver aberto."""
    shell32 = ctypes.windll.shell32
    shell32.DragQueryFileW.argtypes = [ctypes.c_void_p, wintypes.UINT, wintypes.LPWSTR, wintypes.UINT]
    shell32.DragFinish.argtypes = [ctypes.c_void_p]
    user32.CallWindowProcW.argtypes = [ctypes.c_void_p, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.CallWindowProcW.restype = ctypes.c_ssize_t
    user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
    user32.SetWindowLongPtrW.restype = ctypes.c_void_p
    guardados = []
    root.update_idletasks()
    for hwnd in {canvas.winfo_id(), root.winfo_id(), user32.GetParent(root.winfo_id())}:
        if not hwnd:
            continue
        shell32.DragAcceptFiles(hwnd, True)
        antigo = {}

        def proc(h, msg, wp, lp, antigo=antigo):
            if msg == WM_DROPFILES:
                n = shell32.DragQueryFileW(wp, 0xFFFFFFFF, None, 0)
                arqs = []
                for i in range(n):
                    buf = ctypes.create_unicode_buffer(1024)
                    shell32.DragQueryFileW(wp, i, buf, 1024)
                    arqs.append(buf.value)
                shell32.DragFinish(wp)
                ao_soltar(arqs)
                return 0
            return user32.CallWindowProcW(antigo["p"], h, msg, wp, lp)
        cb = WNDPROC(proc)
        antigo["p"] = user32.SetWindowLongPtrW(hwnd, -4, ctypes.cast(cb, ctypes.c_void_p))  # GWLP_WNDPROC
        guardados.append(cb)
    return guardados


def ja_aberto():
    kernel32.CreateMutexW(None, False, "RobozinhoDrillGeo_instancia_unica")
    return kernel32.GetLastError() == 183  # ERROR_ALREADY_EXISTS


def registrar_erro(texto):
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(time.strftime("%d/%m/%Y %H:%M:%S ") + texto + "\n")
    except Exception:
        pass


# ----------------------------------------------------------------------------
# Claude Code
# ----------------------------------------------------------------------------

def achar_claude():
    """Prefere o claude.exe (sem passar pelo cmd); cai para o que estiver no PATH."""
    appdata = os.environ.get("APPDATA", "")
    perfil = os.environ.get("USERPROFILE", "")
    candidatos = [
        Path(appdata) / "npm" / "node_modules" / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe",
        Path(perfil) / ".local" / "bin" / "claude.exe",
    ]
    for c in candidatos:
        if c.is_file():
            return str(c)
    return shutil.which("claude.exe") or shutil.which("claude")


def ambiente_limpo():
    """Se o robô for aberto de dentro de uma sessão do Claude, não herda as variáveis dela."""
    env = dict(os.environ)
    if "CLAUDE_CODE_ENTRYPOINT" in env or "CLAUDECODE" in env:
        for k in list(env):
            if k.startswith("CLAUDE") or k == "ANTHROPIC_BASE_URL":
                env.pop(k, None)
    return env


def montar_comando(exe, fazer, sessao, continuar):
    cmd = [exe, "-p", "--output-format", "text", "--strict-mcp-config", "--permission-prompts", "none"]
    if fazer:
        # Edição de arquivo aceita; comando de terminal pediria permissão -> negado.
        cmd += ["--permission-mode", "acceptEdits", "--append-system-prompt", SISTEMA_FAZER]
    else:
        cmd += ["--tools", "Read,Glob,Grep",
                "--disallowedTools", "Edit,Write,NotebookEdit,Bash,PowerShell",
                "--permission-mode", "dontAsk",
                "--append-system-prompt", SISTEMA_LEITURA]
    cmd += ["--resume", sessao] if continuar else ["--session-id", sessao]
    return cmd


def explicar_erro(saida, codigo):
    baixo = saida.lower()
    if "authenticate" in baixo or "not logged in" in baixo or "/login" in baixo or "oauth" in baixo:
        return ("O Claude Code deste computador não está conectado à sua conta.\n\n"
                "Clique com o botão direito em mim > \"Entrar no Claude Code\", faça o login "
                "no navegador uma vez e pergunte de novo.")
    if "no conversation found" in baixo or "session" in baixo and "not found" in baixo:
        return "Não achei a conversa anterior. Use \"Nova conversa\" e pergunte de novo."
    if "rate limit" in baixo or "usage limit" in baixo or "limit reached" in baixo:
        return "O limite de uso do Claude foi atingido. Tente mais tarde.\n\n" + saida[-400:]
    resumo = saida.strip()[-600:] or "(sem mensagem)"
    return f"O Claude Code respondeu com erro (código {codigo}).\n\n{resumo}"


class Pedido(threading.Thread):
    """Roda um claude -p e devolve o resultado na fila."""

    def __init__(self, fila, exe, texto, fazer, sessao, continuar, historico=None, externo=True):
        super().__init__(daemon=True)
        self.fila, self.exe, self.texto = fila, exe, texto
        self.fazer, self.sessao, self.continuar = fazer, sessao, continuar
        self.historico = historico or []
        # !fazer e texto com CPF não saem do computador: só o Claude Code (conta da empresa).
        self.externo = externo and not fazer and not fn.tem_dado_pessoal(texto)
        self.motor = "claude"
        self.falhas = []
        self.proc = None
        self.cancelado = False

    def run(self):
        motores = fn.ordem_motores()
        externos = [m for m in motores if m[0] != "claude"]
        if self.externo and externos:
            # segunda volta: falha passageira (lotado, rede) costuma passar em segundos
            motores = externos + [("espera", "", "")] + motores
        for nome, chave, modelo in motores:
            if nome == "espera":
                time.sleep(3)
                continue
            if nome == "claude":
                break
            if not self.externo:
                continue
            try:
                msgs = [{"role": "system", "content": SISTEMA_EXTERNO}] + self.historico[-8:] + \
                       [{"role": "user", "content": self.texto}]
                texto = fn.perguntar_externo(nome, chave, modelo, msgs)
                if not self.cancelado:
                    self.motor = nome
                    self.fila.put(("resposta", texto, self))
                return
            except Exception as e:
                corpo = ""
                try:
                    corpo = e.read().decode("utf-8", "replace")[:160]   # erro HTTP: o motivo vem no corpo
                except Exception:
                    pass
                self.falhas.append(f"{nome}: {str(e)[:80]} {corpo}".strip())
                registrar_erro(f"IA {nome} ({modelo}) falhou: {e} {corpo}")
            if self.cancelado:
                return
        usa_claude = any(n == "claude" for n, _, _ in fn.ordem_motores())
        if not usa_claude or not self.exe:
            if self.fazer:
                motivo = "O !fazer precisa do Claude Code, que está desligado (fora da ordem no chaves.json)."
            elif not self.externo:
                motivo = ("O texto tem CPF, então não mando para as IAs grátis (elas podem guardar o que recebem).\n"
                          "Tire os CPFs e mande de novo.")
            else:
                motivo = ("Nenhuma IA respondeu. Tente de novo daqui a pouco.\n\n"
                          + ("\n".join(self.falhas) or fn.diagnostico_chaves()))
                if not self.falhas:
                    registrar_erro("Sem IA para tentar. " + fn.diagnostico_chaves() + f" · ordem lida: {[n for n, _, _ in motores]}")
            self.fila.put(("erro", motivo, self))
            return
        self.rodar_claude()

    def rodar_claude(self):
        cmd = montar_comando(self.exe, self.fazer, self.sessao, self.continuar)
        try:
            self.proc = subprocess.Popen(
                cmd, cwd=str(COFRE), env=ambiente_limpo(),
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                creationflags=0x08000000)  # CREATE_NO_WINDOW
            # A pergunta vai pela entrada padrão: nada de aspas ou acentos quebrando a linha de comando.
            saida, _ = self.proc.communicate(self.texto.encode("utf-8"), timeout=LIMITE_SEG)
            saida = saida.decode("utf-8", errors="replace").strip()
            if self.cancelado:
                return
            if self.proc.returncode == 0 and saida:
                self.fila.put(("resposta", saida, self))
            else:
                self.fila.put(("erro", explicar_erro(saida, self.proc.returncode), self))
        except subprocess.TimeoutExpired:
            self.matar()
            if not self.cancelado:
                self.fila.put(("erro", "Passou de 3 minutos e o Claude ainda não respondeu, então eu parei.\n\n"
                                       "Tente uma pergunta menor ou use \"Abrir no Claude\" para tarefas longas.", self))
        except Exception as e:
            registrar_erro(traceback.format_exc())
            self.fila.put(("erro", f"Não consegui falar com o Claude Code.\n\n{e}", self))

    def matar(self):
        if self.proc and self.proc.poll() is None:
            subprocess.run(["taskkill", "/PID", str(self.proc.pid), "/T", "/F"],
                           capture_output=True, creationflags=0x08000000)

    def cancelar(self):
        self.cancelado = True
        self.matar()


# ----------------------------------------------------------------------------
# Atalho global Ctrl+Alt+Espaço (RegisterHotKey: não precisa de administrador)
# ----------------------------------------------------------------------------

class AtalhoGlobal(threading.Thread):
    def __init__(self, fila):
        super().__init__(daemon=True)
        self.fila = fila
        self.tid = None

    def run(self):
        self.tid = kernel32.GetCurrentThreadId()
        ok = user32.RegisterHotKey(None, 1, 0x0001 | 0x0002 | 0x4000, 0x20)  # Alt|Ctrl|NoRepeat, Espaço
        self.fila.put(("atalho_status", bool(ok), None))
        if not ok:
            return
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == 0x0312:  # WM_HOTKEY
                self.fila.put(("atalho", None, None))
        user32.UnregisterHotKey(None, 1)

    def parar(self):
        if self.tid:
            user32.PostThreadMessageW(self.tid, 0x0012, 0, 0)  # WM_QUIT


# ----------------------------------------------------------------------------
# Atalhos .lnk (área de trabalho e inicialização do Windows)
# ----------------------------------------------------------------------------

def pasta_inicializar():
    return Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def criar_lnk(destino_lnk):
    """Atalho que abre o robô pelo Abrir Robozinho.vbs (sem janela preta; avisa se faltar Python)."""
    def q(s):
        return "'" + str(s).replace("'", "''") + "'"
    icone = PASTA / "robozinho.ico"
    script = (
        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut(" + q(destino_lnk) + ");"
        "$s.TargetPath=" + q(Path(os.environ.get("WINDIR", r"C:\Windows")) / "System32" / "wscript.exe") + ";"
        "$s.Arguments=" + q('"' + str(PASTA / "Abrir Robozinho.vbs") + '"') + ";"
        "$s.WorkingDirectory=" + q(PASTA) + ";"
        "$s.Description=" + q("Assistente de mesa da DrillGeo") + ";"
        + ("$s.IconLocation=" + q(icone) + ";" if icone.is_file() else "")
        + "$s.Save()"
    )
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
                       capture_output=True, creationflags=0x08000000)
    return r.returncode == 0 and Path(destino_lnk).is_file()


def desenhar_icone():
    """Ícone do atalho (rosto do robô). Precisa do Pillow; sem ele, o atalho usa o ícone padrão."""
    try:
        from PIL import Image, ImageDraw
    except Exception:
        return False
    n = 256
    im = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.pieslice((28, 22, 228, 182), 180, 360, fill=ACCENT_ESC, outline=SURFACE, width=6)   # capacete
    d.rounded_rectangle((18, 96, 238, 116), 8, fill=SURFACE)                               # aba
    d.ellipse((108, 42, 148, 82), fill=CLARO, outline=SURFACE, width=5)                   # lanterna
    d.rounded_rectangle((36, 112, 220, 236), 34, fill=CLARO, outline=SURFACE, width=6)    # cabeça
    d.rounded_rectangle((56, 130, 200, 218), 24, fill=BG)                                 # tela
    d.ellipse((86, 148, 112, 182), fill=ACCENT)
    d.ellipse((144, 148, 170, 182), fill=ACCENT)
    d.arc((112, 178, 144, 204), 20, 160, fill=ACCENT, width=6)
    im.save(PASTA / "robozinho.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    return True


# ----------------------------------------------------------------------------
# O robô
# ----------------------------------------------------------------------------

class Robozinho:
    W, H = 270, 175       # tamanho lógico da janela (antes da escala de DPI); a sonda fica à direita
    BASE = 165            # linha dos pés
    CX = 75               # centro do robô dentro da janela

    def __init__(self, demo_pasta=None):
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title(NOME)
        self.S = max(1.0, self.root.winfo_fpixels("1i") / 96.0)
        self.root.tk.call("tk", "scaling", self.S * 96 / 72)
        self.fonte = "Inter" if "Inter" in tkfont.families() else "Segoe UI"
        self.fila = queue.Queue()
        self.cfg = self.ler_config()

        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-transparentcolor", TRANSP)
        self.root.configure(bg=TRANSP)
        self.cv = tk.Canvas(self.root, width=self.px(self.W), height=self.px(self.H),
                            bg=TRANSP, highlightthickness=0, bd=0, cursor="hand2")
        self.cv.pack()

        L, T, R, B = area_de_trabalho()
        self.x = float(R - self.px(self.W) - 40)
        self.y = float(self.chao())
        self.vy = 0.0

        # comportamento
        self.modo = self.cfg.get("modo", "andar")      # andar | parado | canto
        self.estado = "parado"
        self.ate = 0.0                                 # fim de estados passageiros
        self.prox_decisao = time.time() + 2
        self.dir = -1
        self.lado = 0                                  # -1 esquerda, 0 de frente, 1 direita
        self.alvo_x = None
        self.virando = 0
        self.piscar = 0
        self.prox_piscar = time.time() + 3
        self.ultima_interacao = time.time()
        self.t = 0
        self.arraste = None
        self.com_sonda = False      # sonda montada ao lado (quando ele fica parado)
        self.sonda_t = 0.0          # 0 = mastro deitado, 1 = mastro em pé
        self.depois_alvo = None     # o que fazer ao chegar no alvo_x
        self.alavanca = (113, self.BASE - 57)

        # conversa
        self.claude_exe = achar_claude()
        self.sessao = None
        self.sessao_iniciada = False
        self.pedido = None
        self.inicio_pedido = 0.0
        self.ultima_pergunta = ""
        self.ultimo_fazer = False
        self.balao = None
        self.balao_tipo = None
        self.var_continuar = tk.BooleanVar(value=True)
        self.historico = []          # conversa com as IAs grátis (só na memória)

        # vida (tamagotchi): energia, óleo, humor, sonda, dinheiro e testemunhos
        self.vida = dict(VIDA_PADRAO, **self.cfg.get("vida", {}))
        self.vida["premios"] = list(self.vida["premios"])
        salvas = dict(self.cfg.get("vida", {}).get("pecas", {}))
        if not salvas:
            salvas = {k: float(self.vida["sonda"]) for k in PECAS}
            if self.vida["quebrada"]:
                salvas["broca"] = 0.0
        self.vida["pecas"] = {k: float(salvas.get(k, 100.0)) for k in PECAS}
        self.atualizar_sonda()
        self.vida["minerios"] = dict(self.vida["minerios"])
        self.vida["usos"], self.vida["uso_dia"] = dict(self.vida["usos"]), dict(self.vida["uso_dia"])
        h = min(24.0, max(0.0, (time.time() - self.cfg.get("vida_ts", time.time())) / 3600))
        self.ajustar(energia=30 * h, oleo=-2 * h, humor=-3 * h)   # computador desligado = descanso
        self.ultimo_testemunho = None   # (nome, cor) mostrado no "tirando testemunho"
        self.salvo_em = time.time()
        self.parede_ate = 0.0            # tempo pendurado no alto da parede
        self.alvo_y = None
        self.lembretes = fn.ler_lembretes()
        self.alerta = None             # lembrete tocando agora
        self.prox_conferir = 0.0
        # problemas do dia a dia (mexem no humor)
        self.prox_evento = time.time() + 60
        self.chuva_ate = 0.0             # chovendo em cima dele até
        self.jorro_ate, self.jorro_cor = 0.0, CONSOLE   # jato saindo do furo (petróleo ou água)
        self.dormiu_em = 0.0
        self.sono_pedido = False         # "Dormir" no menu: dorme até alguém mexer
        self.doido_x = 0.0
        self.jogo_ativo = None          # jogo ou passeio aberto

        # atalho global
        self.atalho = None
        self.atalho_ok = None
        self.var_atalho = tk.BooleanVar(value=self.cfg.get("atalho", True))
        self.var_iniciar = tk.BooleanVar(value=(pasta_inicializar() / f"{NOME}.lnk").is_file())
        if self.var_atalho.get():
            self.ligar_atalho()

        self.montar_menu()
        self.cv.bind("<ButtonPress-1>", self.ao_apertar)
        self.cv.bind("<B1-Motion>", self.ao_arrastar)
        self.cv.bind("<ButtonRelease-1>", self.ao_soltar)
        self.cv.bind("<Button-3>", self.abrir_menu)

        self.root.geometry(f"+{int(self.x)}+{int(self.y)}")
        self.root.deiconify()
        esconder_da_barra(self.root)
        self.soltar_cb = aceitar_arquivos(self.root, self.cv, lambda arqs: self.fila.put(("arquivos", arqs, None)))
        if self.modo == "canto":
            self.ir_para_canto()

        self.demo = None
        if demo_pasta:
            self.demo = Demo(self, Path(demo_pasta))
        self.root.after(QUADRO_MS, self.quadro)

    # ---------- utilidades ----------

    def px(self, v):
        return int(round(v * self.S))

    def chao(self):
        return area_de_trabalho()[3] - self.px(self.H)

    def ler_config(self):
        try:
            return json.loads(CONFIG.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def salvar_config(self):
        self.cfg.update(modo=self.modo, atalho=self.var_atalho.get(), vida=self.vida, vida_ts=time.time())
        self.salvo_em = time.time()
        try:
            CONFIG.write_text(json.dumps(self.cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            registrar_erro(traceback.format_exc())

    def mexeu(self):
        self.ultima_interacao = time.time()
        self.sono_pedido = False
        if self.estado in ("dormindo", "sentado"):
            self.estado = "parado"
            self.prox_decisao = time.time() + 2

    def mudar(self, estado, segundos=0.0):
        self.estado = estado
        self.ate = time.time() + segundos

    # ---------- vida (tamagotchi) ----------

    def ajustar(self, **dif):
        for k, v in dif.items():
            self.vida[k] = max(0.0, min(100.0, self.vida[k] + v))

    def tique_vida(self):
        """Gasta e recupera aos poucos (valores por hora)."""
        st, h = self.estado, QUADRO_MS / 1000 / 3600
        if st == "dormindo":
            self.ajustar(energia=120 * h, humor=2 * h)   # cochilo curto já recarrega
        elif st in ("operando", "escalando", "consertando"):
            self.ajustar(energia=-18 * h, oleo=-9 * h, humor=-2 * h)
        else:
            self.ajustar(energia=-6 * h, oleo=-2.5 * h, humor=-4 * h)
        v = self.vida
        if v["energia"] < 25:
            self.ajustar(humor=-6 * h)
        if self.chuva_ate:      # chuva acaba com ele
            self.ajustar(humor=-40 * h, energia=-15 * h)
        if v["suja"]:           # melado de petróleo
            self.ajustar(humor=-10 * h)
        # perfuração: o furo avança e, no fim, sai um testemunho
        if st == "operando" and self.sonda_t >= 1 and not v["quebrada"]:
            ritmo = 0.45 * (0.5 + v["oleo"] / 200) * (0.6 if v["energia"] < 25 else 1)
            ritmo *= (0.6 if v["suja"] else 1) * (0.3 if self.chuva_ate else 1)
            v["furo"] += ritmo * QUADRO_MS / 1000
            if v["furo"] >= 100:
                self.tirar_testemunho()
        if time.time() - self.salvo_em > 60:
            self.salvar_config()

    def emocao(self):
        """Rosto do dia a dia, conforme o que ele está sentindo."""
        v = self.vida
        if v["quebrada"]:
            return "preocupado"
        if self.chuva_ate:
            return "triste"
        if v["energia"] < 25:
            return "cansado"
        if v["humor"] < 30 or v["oleo"] < 15:
            return "triste"
        if v["humor"] > 75:
            return "feliz"
        return "normal"

    def precisa_cuidado(self):
        v = self.vida
        return v["quebrada"] or min(v["energia"], v["oleo"], v["humor"]) < 20

    def tirar_testemunho(self):
        v = self.vida
        v["furo"] = 0.0
        sorteio, soma = random.random(), 0.0
        for nome, cor, chance, vmin, vmax in MINERIOS:
            soma += chance
            if sorteio <= soma:
                break
        valor = random.randint(vmin, vmax)
        antes = v["metros"]
        v["metros"] += random.randint(25, 45)          # cada manobra do testemunho avança o furo
        marcos = int(v["metros"] // 1000) - int(antes // 1000)
        if marcos > 0:
            valor += 150 * marcos                      # bônus por mil metros perfurados
        v["dinheiro"] += valor
        v["testemunhos"] += 1
        v["minerios"][nome] = v["minerios"].get(nome, 0) + 1
        novos = [p for n, p in METAS if v["testemunhos"] == n]
        if marcos > 0:
            novos.append(f"{int(v['metros'] // 1000)}.000 m perfurados")
        if v["minerios"][nome] == 1 and nome != "Rocha":
            novos.append(f"Primeiro {nome}")
        v["premios"] += [p for p in novos if p not in v["premios"]]
        self.ajustar(humor=8 + (10 if nome in ("Diamante", "Esmeralda") else 0), energia=-2)
        # desgaste de duas peças por manobra; com pouco óleo gasta mais
        f = 1.6 if v["oleo"] < 30 else 1
        quebradas = self.desgastar(random.sample(list(PECAS), 2), 4 * f, 9 * f)
        if quebradas:
            self.root.after(3600, lambda: self.avisar_quebra(quebradas))
        self.ultimo_testemunho = (nome, cor, valor, novos)
        self.mudar("testemunho", 3.2)
        self.salvar_config()

    # ---------- sonda: peças, revisões e compra ----------

    def atualizar_sonda(self):
        """'sonda' = média das peças; quebrada = alguma peça a zero."""
        v = self.vida
        v["sonda"] = sum(v["pecas"].values()) / len(v["pecas"])
        v["quebrada"] = any(x <= 0 for x in v["pecas"].values())

    def pecas_quebradas(self):
        return [k for k, x in self.vida["pecas"].items() if x <= 0]

    def desgastar(self, pecas, vmin, vmax):
        """Gasta as peças (em dobro com petróleo na sonda); abaixo de 30% pode quebrar. Devolve as que quebraram."""
        v = self.vida
        fator = 2.0 if v["suja"] else 1.0
        quebradas = []
        for k in pecas:
            if v["pecas"][k] <= 0:
                continue
            v["pecas"][k] = max(0.0, v["pecas"][k] - random.uniform(vmin, vmax) * fator)
            if v["pecas"][k] < 30 and random.random() < (35 - v["pecas"][k]) / 100:
                v["pecas"][k] = 0.0
            if v["pecas"][k] <= 0:
                quebradas.append(k)
        self.atualizar_sonda()
        return quebradas

    def nomes(self, chaves):
        return ", ".join(PECAS[k][0] for k in chaves)

    def avisar_quebra(self, quebradas):
        if self.balao is None:
            self.mudar("triste", 3)
            self.aviso("Quebrou: " + self.nomes(quebradas),
                       "A sonda parou. Compre a peça nova no meu painel: "
                       + ", ".join(f"{PECAS[k][0]} R$ {self.preco_peca(k)}" for k in quebradas) + ".")

    def fator_custo(self):
        return CUSTO_SUJA if self.vida["suja"] else 1.0

    def custo_revisao(self, tipo):
        """Taxa fixa + o desgaste das peças daquele tipo que ainda funcionam (quebrada só com peça nova)."""
        falta = sum(100 - x for k, x in self.vida["pecas"].items() if PECAS[k][1] == tipo and x > 0)
        if falta < 1:
            return 0
        return int((REVISAO[tipo][1] + falta * 0.8) * self.fator_custo())

    def preco_peca(self, k):
        return int(PECAS[k][2] * self.fator_custo())

    def pagar(self, custo, o_que):
        if self.vida["dinheiro"] >= custo:
            self.vida["dinheiro"] -= custo
            return True
        self.mudar("triste", 3)
        self.aviso("Não tenho dinheiro", f"{o_que} custa R$ {custo} e eu só tenho R$ {self.vida['dinheiro']}.\n\n"
                   f"Faltam R$ {custo - self.vida['dinheiro']}. Me ajuda com uma doação? (botão Doar no meu painel)")
        return False

    def manutencao(self, depois):
        """Animação de 5 s mexendo na sonda; no fim aplica o reparo."""
        self.mexeu()
        self.fechar_balao()
        self.operar_sonda_parada()
        self.mudar("consertando", 5)

        def pronto():
            depois()
            self.atualizar_sonda()
            self.ajustar(humor=8)
            self.mudar("comemorando", 2.5)
            self.salvar_config()
        self.root.after(5000, pronto)

    def revisar(self, tipo):
        nome, custo = REVISAO[tipo][0], self.custo_revisao(tipo)
        if not custo:
            self.aviso(nome, "As peças dessa revisão estão 100%. Peça quebrada só volta com peça nova.")
            return
        if not self.pagar(custo, nome):
            return
        pecas = self.vida["pecas"]
        self.manutencao(lambda: pecas.update({k: 100.0 for k, x in pecas.items() if PECAS[k][1] == tipo and x > 0}))

    def comprar_peca(self, k):
        if not self.pagar(self.preco_peca(k), f"{PECAS[k][0]} nova"):
            return
        self.manutencao(lambda: self.vida["pecas"].update({k: 100.0}))

    def trocar_quebradas(self):
        quebradas = self.pecas_quebradas()
        if not quebradas:
            self.aviso("Peças", "Nenhuma peça quebrada.")
            return
        total = sum(self.preco_peca(k) for k in quebradas)
        if not self.pagar(total, "Trocar " + self.nomes(quebradas)):
            return
        self.manutencao(lambda: self.vida["pecas"].update({k: 100.0 for k in quebradas}))

    def operar_sonda_parada(self):
        """Encosta na sonda (sem perfurar) para consertar."""
        self.com_sonda = True
        self.sonda_t = max(self.sonda_t, 0.99)
        self.lado = 1

    def doar(self, valor):
        self.vida["dinheiro"] += valor
        self.ajustar(humor=12 + valor / 10)
        self.mexeu()
        self.fechar_balao()
        self.mudar("amor", 3.5)
        self.salvar_config()

    def cuidar(self, tipo):
        self.mexeu()
        self.fechar_balao()
        if tipo == "limpar":
            if not self.pagar(25, "Limpar o petróleo"):
                return
            self.mudar("lubrificando", 3.5)
            self.root.after(3500, lambda: (self.vida.update(suja=False), self.ajustar(humor=12)))
        elif tipo == "recarregar":
            self.mudar("recarregando", 5)
            self.root.after(5000, lambda: (self.ajustar(energia=45), self.mudar("comemorando", 1.5)))
        elif tipo == "oleo":
            if self.vida["dinheiro"] < 5:
                self.aviso("Sem dinheiro para o óleo", "O óleo custa R$ 5. Me ajuda com uma doação?")
                return
            self.vida["dinheiro"] -= 5
            self.mudar("lubrificando", 3.5)
            self.root.after(3500, lambda: self.ajustar(oleo=100))
        else:
            self.ajustar(humor=20)
            self.mudar("amor", 3)
        self.salvar_config()

    # ---------- laço de animação ----------

    def quadro(self):
        try:
            self.ler_fila()
            if self.demo:
                if self.demo.passo():  # o teste escolhe a animação; o comportamento normal fica desligado
                    self.root.destroy()
                    return
            else:
                self.comportar()
                self.tique_vida()
                self.conferir_lembretes()
            if self.estado in ("operando", "testemunho", "consertando"):
                self.com_sonda = True
            elif self.estado in ("andando", "arrastando", "caindo", "escalando"):
                self.com_sonda = False
            self.sonda_t = min(1.0, self.sonda_t + 0.035) if self.com_sonda else 0.0
            self.desenhar()
            self.root.geometry(f"+{int(self.x)}+{int(self.y)}")
        except Exception:
            registrar_erro(traceback.format_exc())
        self.t += 1
        self.root.after(QUADRO_MS, self.quadro)

    def comportar(self):
        agora = time.time()
        L, T, R, B = area_de_trabalho()
        chao = self.chao()
        largura = self.px(self.W)

        # piscar
        if self.piscar > 0:
            self.piscar -= 1
        elif agora > self.prox_piscar:
            self.piscar = 3
            self.prox_piscar = agora + random.uniform(2.5, 6)

        if self.estado == "arrastando":
            return
        if self.estado == "caindo":
            self.vy += 1.6 * self.S
            self.y = min(chao, self.y + self.vy)
            if self.y >= chao:
                self.vy = 0
                self.mudar("operando" if self.modo != "andar" else "parado")
                self.prox_decisao = agora + 1
            return
        if self.pedido:
            self.estado = "pensando"
            self.lado = 0
            return
        if self.estado in ("comemorando", "confuso", "testemunho", "consertando", "amor", "recarregando",
                           "lubrificando", "triste", "bocejando"):
            if agora < self.ate:
                return
            if self.estado == "testemunho":
                self.mudar("comemorando", 2.2)
                nome, cor, valor, novos = self.ultimo_testemunho
                if novos and self.balao is None:
                    self.aviso("Prêmio!", f"Ganhei: {', '.join(novos)}.\nTestemunho de {nome}: + R$ {valor}.")
                return
            self.mudar("operando" if self.estado in ("consertando", "lubrificando") else "parado")
            self.prox_decisao = agora + 3
        if self.estado == "pensando":
            self.mudar("parado")

        # cansaço: sem energia ele apaga; cansado boceja de vez em quando
        v = self.vida
        if v["energia"] < 6 and self.estado not in ("dormindo", "escalando"):
            self.dormir(pedido=False)
            return
        if self.estado == "dormindo" and v["energia"] >= 98:   # bateria cheia: acorda sozinho
            self.ultima_interacao = agora
            self.mudar("parado")
            self.prox_decisao = agora + 2
        if v["energia"] < 25 and self.estado in ("parado", "andando", "operando") and random.random() < 0.002:
            self.mudar("bocejando", 1.8)
            return

        if self.alerta and self.alerta["jeito"] == "urgente" and self.estado not in ("arrastando", "caindo"):
            self.estado, self.lado = "doido", 0
            self.x = self.doido_x + math.sin(agora * 5) * self.px(40) + random.uniform(-2, 2) * self.S
            return

        # escalando a lateral da tela
        if self.estado == "escalando":
            self.lado = 0
            if agora < self.parede_ate:
                return
            if self.y > self.alvo_y:
                self.y -= 1.6 * self.S * (0.6 if v["energia"] < 25 else 1)
                return
            if not self.parede_ate:
                self.parede_ate = agora + random.uniform(1.5, 4)   # olha a vista lá de cima
                return
            self.parede_ate = 0.0
            self.mudar("caindo")     # solta da parede e cai de volta no chão
            self.vy = 0
            return

        if self.virando > 0:
            self.virando -= 1
            self.lado = 0
            if self.virando == 0:
                self.lado = self.dir
            return

        # balão aberto: fica parado olhando para a pessoa
        if self.balao is not None and self.estado != "dormindo":
            if self.estado in ("andando", "operando"):
                self.estado = "parado"
            self.lado = 0
            return

        parado_ha = agora - self.ultima_interacao
        if self.estado == "dormindo":
            if not self.dormiu_em:
                self.dormiu_em = agora
            # cochilo sozinho é curto: levanta e volta ao trabalho (o "Dormir" do menu continua até mexerem)
            if not self.sono_pedido and v["energia"] >= 40 and agora - self.dormiu_em > SONECA_SEG:
                self.dormiu_em = 0.0
                self.ultima_interacao = agora
                self.mudar("bocejando", 1.8)
            return
        self.dormiu_em = 0.0

        # a chuva passa (e lava o petróleo da sonda)
        if self.chuva_ate and agora > self.chuva_ate:
            self.chuva_ate = 0.0
            if v["suja"]:
                v["suja"] = False
                self.ajustar(humor=10)
                self.aviso("Parou de chover", "A chuva lavou o petróleo da sonda. Pelo menos isso!")
            elif random.random() < 0.5:
                self.ajustar(humor=8)
                self.mudar("comemorando", 2)
            return
        # problemas do dia a dia
        if agora > self.prox_evento:
            self.prox_evento = agora + random.uniform(*EVENTO_SEG)
            if self.estado in ("andando", "operando", "parado", "sentado") and not self.jogo_ativo \
                    and self.alvo_x is None:
                self.sortear_evento(agora)
                return

        # andando até um ponto (Ficar no canto)
        if self.alvo_x is not None:
            falta = self.alvo_x - self.x
            if abs(falta) <= self.px(3):
                self.x = self.alvo_x
                self.alvo_x = None
                self.mudar(self.depois_alvo or "parado")
                self.depois_alvo = None
                self.lado = 0
            else:
                d = 1 if falta > 0 else -1
                if d != self.dir:
                    self.dir = d
                    self.virando = 4
                self.estado = "andando"
                self.lado = self.dir
                self.x += d * min(abs(falta), 2.2 * self.S)
            return

        if self.modo == "andar":
            if parado_ha > SONO_ANDANDO_SEG:
                self.estado = "dormindo" if parado_ha > SONO_ANDANDO_SEG + 8 else "sentado"
                self.lado = 0
                return
            if agora > self.prox_decisao:
                sorteio = random.random()
                if sorteio < 0.62:
                    self.estado = "andando"
                    if random.random() < 0.3:
                        self.dir = -self.dir
                        self.virando = 4
                    self.prox_decisao = agora + random.uniform(3, 8)
                elif sorteio < 0.97:  # sentar à toa ficou raro (era 8%, agora 3%)
                    self.operar()     # para e monta a sonda
                    self.prox_decisao = agora + random.uniform(8, 16)
                else:
                    self.estado = "sentado"
                    self.lado = 0
                    self.prox_decisao = agora + random.uniform(4, 8)
            if self.estado == "andando":
                if self.y < chao - 1:   # foi solto no alto: desce antes de andar
                    self.mudar("caindo")
                    return
                self.lado = self.dir
                lento = (0.5 if v["energia"] < 25 else 1) * (0.4 if v["oleo"] < 20 and self.t % 6 < 3 else 1)
                self.x += self.dir * 2.0 * self.S * lento
                limite_esq = L - self.px(self.CX - 38)    # encosta o robô na borda esquerda
                limite_dir = R - self.px(self.CX + 38)    # andando, só o robô precisa caber na tela
                if self.x <= limite_esq and self.dir < 0 or self.x >= limite_dir and self.dir > 0:
                    self.x = max(limite_esq, min(self.x, limite_dir))
                    if v["energia"] > 35 and random.random() < 0.45:
                        self.estado = "escalando"
                        self.alvo_y = self.chao() - random.uniform(0.25, 0.7) * (B - T)
                        self.parede_ate = 0.0
                        self.ajustar(humor=3)
                    self.dir = -self.dir
                    self.virando = 4
            elif self.estado == "operando":
                self.lado = 1
        else:   # parado / canto: fica operando a sonda até dormir
            if parado_ha > SONO_SEG:
                self.estado = "dormindo"
                self.lado = 0
            elif self.estado != "operando":
                self.operar()
            else:
                self.lado = 1

    def sortear_evento(self, agora):
        """Problema (ou alegria) do dia a dia de sondador. Todos mexem no humor."""
        v = self.vida
        na_sonda = self.estado == "operando" and self.sonda_t >= 1 and not v["quebrada"]
        opcoes = [] if self.chuva_ate else [("chuva", 3)]
        if na_sonda:
            opcoes += [("petroleo", 2), ("agua", 2), ("rocha", 2)]
        if self.estado == "andando":
            opcoes.append(("tropeco", 2))
        opcoes.append(("elogio", 1))
        nome = random.choices([n for n, _ in opcoes], [p for _, p in opcoes])[0]

        if nome == "chuva":
            self.chuva_ate = agora + random.uniform(60, 150)
            self.ajustar(humor=-12, energia=-5)
            self.mudar("triste", 3)
            self.aviso("Começou a chover", "Caiu um toró em cima de mim. Estou ensopado e sem ânimo; "
                       "a sonda vai bem devagar até a chuva passar.")
        elif nome == "petroleo":
            ganho = random.randint(40, 90)
            v["dinheiro"] += ganho
            quebradas = self.desgastar(["bomba", "broca", "motor", "haste"], 15, 30) + self.desgastar(["painel"], 5, 15)
            v["suja"] = True
            self.jorro_ate, self.jorro_cor = agora + 5, CONSOLE
            self.ajustar(humor=-18)
            self.mudar("confuso", 3)
            self.aviso("Achei petróleo!", f"Jorrou petróleo do furo: + R$ {ganho}. Mas a lama de óleo entrou na bomba, "
                       "na broca e no motor"
                       + (f", e quebrou: {self.nomes(quebradas)}" if quebradas else "") + ".\n\n"
                       "Enquanto a sonda estiver suja, as peças gastam em dobro e toda manutenção fica 50% mais cara. "
                       "Limpe no meu painel (R$ 25) ou espere uma chuva lavar.")
        elif nome == "agua":
            self.jorro_ate, self.jorro_cor = agora + 5, ACCENT
            quebradas = self.desgastar(["painel", "fiacao", "bateria"], 20, 40)
            self.ajustar(humor=-12)
            self.mudar("triste", 3)
            self.aviso("Bateu água no furo", "Achei um lençol d'água e molhou a parte elétrica. "
                       + (f"Quebrou: {self.nomes(quebradas)}. Compre peça nova no meu painel." if quebradas
                          else "Estragou o painel, a fiação e a bateria: faça uma revisão elétrica."))
        elif nome == "rocha":
            quebradas = self.desgastar(["broca", "haste"], 10, 20)
            self.ajustar(energia=-12, humor=-8)
            self.operar_sonda_parada()
            self.mudar("consertando", 4)
            self.aviso("Rocha dura", "A broca travou numa rocha duríssima. Destravei na mão e fiquei moído."
                       + (f" Quebrou: {self.nomes(quebradas)}." if quebradas else ""))
        elif nome == "tropeco":
            self.ajustar(humor=-5, energia=-2)
            self.mudar("confuso", 2)
        else:
            self.ajustar(humor=15)
            self.mudar("comemorando", 2.5)
            self.aviso("Visita do supervisor", "O supervisor passou pela sonda e elogiou meu trabalho. Fiquei todo bobo!")
        self.salvar_config()

    def operar(self):
        """Para e opera a sonda; se a sonda não couber na tela, anda um pouco antes."""
        R = area_de_trabalho()[2]
        cabe = R - self.px(self.W) - 4
        if self.x > cabe:
            self.alvo_x, self.depois_alvo = float(cabe), "operando"
        else:
            self.estado = "operando"
            self.lado = 1

    # ---------- desenho ----------

    def desenhar(self):
        c = self.cv
        c.delete("all")
        S, t, st, f = self.S, self.t, self.estado, self.lado
        cx, base = self.CX, self.BASE
        w = lambda v: max(1, v * S)  # espessura de linha na escala

        if self.com_sonda:
            self.desenhar_sonda(base, st == "operando" and not self.vida["quebrada"], w)

        bob = 0.0
        if st == "andando":
            bob = -abs(math.sin(t * 0.45)) * 3
        elif st == "comemorando":
            bob = -abs(math.sin(t * 0.32)) * 18
        elif st in ("parado", "pensando", "confuso"):
            bob = math.sin(t * 0.08) * 1.2
        elif st == "operando":
            bob = math.sin(t * 0.9) * 0.6     # tremidinha da máquina
        elif st == "dormindo":
            bob = math.sin(t * 0.06) * 1.5
        elif st in ("amor", "triste", "bocejando", "recarregando", "lubrificando"):
            bob = math.sin(t * 0.1) * 1.5
        elif st == "testemunho":
            bob = -abs(math.sin(t * 0.25)) * 6
        elif st == "doido":
            bob = -abs(math.sin(t * 0.55)) * 22
        elif st == "escalando":
            bob = math.sin(t * 0.5) * 2
        sentado = st in ("sentado", "dormindo", "recarregando")
        if sentado:
            bob += 13
        pendurado = st in ("arrastando", "caindo")

        # pernas e pés
        for i, lx in enumerate((cx - 11, cx + 11)):
            if sentado:
                px_ = lx + (-7 if i == 0 else 7)
                c.create_oval(px_ - 9, base - 9, px_ + 9, base + 1, fill=ACCENT_ESC, outline=SURFACE, width=w(2))
                continue
            sobe = 0.0
            if st == "escalando":
                sobe = max(0.0, math.sin(t * 0.5 + (0 if i == 0 else math.pi))) * 7
            elif st == "andando":
                fase = math.sin(t * 0.45 + (0 if i == 0 else math.pi))
                sobe = max(0.0, fase) * 5
            balanço = math.sin(t * 0.3 + i) * 3 if pendurado else 0
            pe_y = base - 4 - sobe + bob * 0.3 + (4 if pendurado else 0)
            c.create_line(lx, base - 24 + bob, lx + balanço, pe_y - 3, fill=SURFACE, width=w(7), capstyle="round")
            dx = f * 3
            c.create_oval(lx - 8 + dx + balanço, pe_y - 6, lx + 8 + dx + balanço, pe_y + 3,
                          fill=ACCENT_ESC, outline=SURFACE, width=w(2))

        # corpo
        top_corpo, fim_corpo = base - 58 + bob, base - 20 + bob
        self.retangulo(cx - 24, top_corpo, cx + 24, fim_corpo, 9, fill=SURFACE, outline=TX, width=w(2))
        c.create_text(cx + f * 4, top_corpo + 17, text="DG", fill=ACCENT,
                      font=(self.fonte, -max(8, int(11 * S)), "bold"))
        luz = ACCENT if (st == "pensando" and (t // 5) % 2) else LINE2
        if st == "recarregando":
            luz = OK if (t // 4) % 2 else LINE2
        elif self.vida["energia"] < 25:
            luz = BAD if (t // 10) % 2 else LINE2      # bateria fraca piscando
        c.create_oval(cx - 3 + f * 4, top_corpo + 27, cx + 3 + f * 4, top_corpo + 33, fill=luz, outline="")
        if self.vida["oleo"] < 25:                      # ferrugem de falta de óleo
            for ox_, oy_ in ((-15, 8), (14, 22), (-9, 30)):
                c.create_oval(cx + ox_ - 2, top_corpo + oy_ - 2, cx + ox_ + 2, top_corpo + oy_ + 2, fill=WARN, outline="")

        # braços
        ombro_y = top_corpo + 9
        for lado_b in (-1, 1):
            ox = cx + lado_b * 23
            if st in ("comemorando", "doido"):
                mao = (cx + lado_b * 38, ombro_y - 30 + math.sin(t * (1.4 if st == "doido" else 0.6) + lado_b) * 5)
            elif st == "testemunho":
                mao = (cx + lado_b * 36, ombro_y - 30)                   # braços sobem (o tubo vem depois da cabeça)
            elif st == "escalando":
                mao = (cx + lado_b * 30, ombro_y - 26 + math.sin(t * 0.5 + (lado_b + 1) * 1.57) * 9)
            elif st == "consertando" and lado_b == 1:
                mao = (cx + 44 + math.sin(t * 0.7) * 6, ombro_y + 4 - abs(math.sin(t * 0.7)) * 10)
            elif st == "lubrificando" and lado_b == 1:
                mao = (cx + 30, ombro_y - 26)
            elif st == "amor":
                mao = (cx + lado_b * 8, ombro_y + 10)                    # mãos no peito
            elif st == "bocejando" and lado_b == -1:
                mao = (cx - 6, ombro_y - 22)                             # mão na boca
            elif st == "triste":
                mao = (cx + lado_b * 24, ombro_y + 24)
            elif st == "operando" and lado_b == 1:
                mao = self.alavanca                             # mão na alavanca da sonda
            elif st == "pensando" and lado_b == 1:
                mao = (cx + 8, ombro_y - 4)                     # mão no queixo
            elif st == "confuso" and lado_b == 1:
                mao = (cx + 30, ombro_y - 40)                   # coçando o capacete
            elif sentado:
                mao = (cx + lado_b * 20, fim_corpo + 2)
            elif pendurado:
                mao = (cx + lado_b * 36, ombro_y - 18 + math.sin(t * 0.5) * 3)
            elif st == "andando":
                mao = (cx + lado_b * 31 + math.sin(t * 0.45) * 4 * lado_b, ombro_y + 20)
            else:
                mao = (cx + lado_b * 31, ombro_y + 21)
            c.create_line(ox, ombro_y, mao[0], mao[1], fill=SURFACE, width=w(6), capstyle="round")
            c.create_oval(mao[0] - 5, mao[1] - 5, mao[0] + 5, mao[1] + 5, fill=CLARO, outline=SURFACE, width=w(1.5))
            if lado_b == 1 and st == "consertando":          # chave inglesa
                c.create_line(mao[0], mao[1], mao[0] + 9, mao[1] - 9, fill=TX2, width=w(3), capstyle="round")
                c.create_oval(mao[0] + 6, mao[1] - 13, mao[0] + 13, mao[1] - 6, outline=TX2, width=w(2))
            elif lado_b == 1 and st == "lubrificando":       # almotolia pingando óleo na junta
                c.create_polygon(mao[0] - 5, mao[1] + 2, mao[0] + 5, mao[1] + 2, mao[0], mao[1] - 9,
                                 fill=WARN, outline=SURFACE, width=w(1))
                gy = mao[1] + 6 + (t * 1.5) % 22
                c.create_oval(mao[0] - 2, gy - 2, mao[0] + 2, gy + 3, fill=WARN, outline="")
        if st == "recarregando":                             # cabo de carga até o chão
            c.create_line(cx + 20, fim_corpo - 6, cx + 46, base - 2, fill=SURFACE, width=w(3), smooth=True)
            c.create_rectangle(cx + 42, base - 8, cx + 54, base, fill=SURFACE, outline=LINE2, width=w(1))
            ry = base - 16 - (t % 20) * 0.6                   # raio subindo
            c.create_polygon(cx + 49, ry - 7, cx + 44, ry + 1, cx + 48, ry + 1, cx + 46, ry + 7,
                             cx + 52, ry - 1, cx + 48, ry - 1, fill=OK, outline="")

        # cabeça
        topo_cab, fim_cab = base - 104 + bob, base - 60 + bob
        self.retangulo(cx - 30, topo_cab, cx + 30, fim_cab, 12, fill=CLARO, outline=SURFACE, width=w(2))
        self.retangulo(cx - 24, topo_cab + 6, cx + 24, fim_cab - 6, 9, fill=BG, outline="")
        for lado_p in ((-1, 1) if f == 0 else (-f,)):  # parafusos das "orelhas"
            px_ = cx + lado_p * 31
            c.create_oval(px_ - 4, topo_cab + 18, px_ + 4, topo_cab + 26, fill=ACCENT_ESC, outline=SURFACE, width=w(1.5))
        self.rosto(cx + f * 5, (topo_cab + fim_cab) / 2 - 3, st, w)

        # capacete de sonda
        c.create_arc(cx - 33, topo_cab - 21, cx + 33, topo_cab + 19, start=0, extent=180, style="chord",
                     fill=ACCENT_ESC, outline=SURFACE, width=w(2))
        c.create_line(cx + f * 6, topo_cab - 20, cx + f * 6, topo_cab - 1, fill=SURFACE, width=w(2))
        self.retangulo(cx - 37, topo_cab - 3, cx + 37, topo_cab + 3, 3, fill=SURFACE, outline="")
        lx = cx + (f * 17 if f else 0)
        lanterna = ACCENT if (st == "pensando" and (t // 5) % 2 == 0) else CLARO
        if f == 0:
            lx = cx
        c.create_oval(lx - 6, topo_cab - 15, lx + 6, topo_cab - 4, fill=lanterna, outline=SURFACE, width=w(1.5))
        # broquinha da sonda no topo
        c.create_line(cx, topo_cab - 21, cx, topo_cab - 28, fill=SURFACE, width=w(3))
        c.create_polygon(cx - 4, topo_cab - 28, cx + 4, topo_cab - 28, cx, topo_cab - 36,
                         fill=TX2, outline=SURFACE, width=w(1))

        # extras acima da cabeça
        if st == "dormindo":
            for i in range(3):
                fase = ((t * 0.04) + i / 3) % 1
                zx = cx + 26 + i * 9 + math.sin(fase * 6) * 2
                zy = topo_cab - 8 - fase * 40
                c.create_text(zx, zy, text="Z" if i else "z", fill=ACCENT,
                              font=(self.fonte, -int((10 + i * 3) * S), "bold"))
        elif st == "pensando":
            for i in range(3):
                acesa = (t // 6) % 4 > i
                c.create_oval(cx + 36 + i * 10 - 3.5, topo_cab - 24 - i * 6 - 3.5,
                              cx + 36 + i * 10 + 3.5, topo_cab - 24 - i * 6 + 3.5,
                              fill=ACCENT if acesa else LINE2, outline="")
        elif st == "confuso":
            c.create_text(cx + 44, topo_cab - 26 + math.sin(t * 0.2) * 2, text="?", fill=BAD,
                          font=(self.fonte, -int(24 * S), "bold"))
        elif st == "comemorando":
            c.create_line(cx + 34, topo_cab - 24, cx + 40, topo_cab - 17, cx + 52, topo_cab - 33,
                          fill=OK, width=w(4), capstyle="round", joinstyle="round")
        elif st == "testemunho" and self.ultimo_testemunho:   # ergue o tubo com a cor do minério
            cor, ty_ = self.ultimo_testemunho[1], topo_cab - 50 - abs(math.sin(t * 0.25)) * 4
            for lado_b in (-1, 1):
                c.create_line(cx + lado_b * 36, ombro_y - 30, cx + lado_b * 30, ty_ + 6, fill=SURFACE, width=w(6),
                              capstyle="round")
            self.retangulo(cx - 32, ty_, cx + 32, ty_ + 12, 5, fill=cor, outline=SURFACE, width=w(1.5))
            for k in (-16, 0, 16):
                c.create_line(cx + k, ty_ + 1, cx + k, ty_ + 11, fill=SURFACE, width=w(1))
            for lado_b in (-1, 1):
                c.create_oval(cx + lado_b * 30 - 5, ty_ + 1, cx + lado_b * 30 + 5, ty_ + 11, fill=CLARO,
                              outline=SURFACE, width=w(1.5))
            if (t // 3) % 2:   # brilho
                for k in range(4):
                    a = t * 0.3 + k * 1.57
                    bx_, by_ = cx + math.cos(a) * 44, ty_ + 6 + math.sin(a) * 14
                    c.create_line(bx_ - 3, by_, bx_ + 3, by_, fill=cor, width=w(1.5))
                    c.create_line(bx_, by_ - 3, bx_, by_ + 3, fill=cor, width=w(1.5))
        elif st == "doido":
            for k, lado_x in enumerate((-46, 46)):
                if (t // 4 + k) % 2:
                    c.create_text(cx + lado_x, topo_cab - 10, text="!", fill=BAD,
                                  font=(self.fonte, -int(26 * S), "bold"))
        elif st == "amor":
            for i in range(3):
                fase = ((t * 0.035) + i / 3) % 1
                hx_ = cx - 20 + i * 20 + math.sin(fase * 7 + i) * 4
                hy_ = topo_cab - 10 - fase * 38
                tam = 4 + i % 2
                c.create_oval(hx_ - tam, hy_ - tam, hx_, hy_, fill=BAD, outline="")
                c.create_oval(hx_, hy_ - tam, hx_ + tam, hy_, fill=BAD, outline="")
                c.create_polygon(hx_ - tam, hy_ - tam / 2, hx_ + tam, hy_ - tam / 2, hx_, hy_ + tam, fill=BAD, outline="")
        elif st == "consertando" and (t // 2) % 3 == 0:
            for k in range(3):
                a = random.uniform(0, 6.28)
                c.create_line(cx + 56, base - 46, cx + 56 + math.cos(a) * 8, base - 46 + math.sin(a) * 8,
                              fill=WARN, width=w(1.5))
        emo = self.emocao()
        if emo == "cansado" and st not in ("dormindo", "recarregando"):   # gota de suor
            gy = topo_cab + 8 + (t * 0.4) % 14
            c.create_oval(cx - 38, gy - 3, cx - 33, gy + 4, fill=ACCENT, outline="")
        if self.precisa_cuidado() and st not in ("dormindo", "amor") and (t // 12) % 2:
            c.create_oval(cx - 46, topo_cab - 34, cx - 30, topo_cab - 18, fill=BAD, outline=SURFACE, width=w(1.5))
            c.create_text(cx - 38, topo_cab - 26, text="!", fill=CLARO, font=(self.fonte, -int(11 * S), "bold"))
        self.desenhar_eventos(cx, base, top_corpo, w)

        c.scale("all", 0, 0, S, S)

    def desenhar_eventos(self, cx, base, top_corpo, w):
        """Petróleo (manchas escuras), jato do furo, e a nuvem de chuva que segue o robô."""
        c, t = self.cv, self.t
        if self.vida["suja"]:
            manchas = [(cx - 12, top_corpo + 26, 5), (cx + 10, top_corpo + 9, 3.5)]
            if self.com_sonda:
                manchas += [(150, base - 19, 6), (176, base - 21, 4), (238, base - 42, 5), (205, base - 16, 3.5)]
            for mx, my, r_ in manchas:
                c.create_oval(mx - r_, my - r_ * 0.8, mx + r_, my + r_ * 0.8, fill=CONSOLE, outline=TX3, width=w(1))
                c.create_line(mx, my, mx, my + r_ + 2 + (t * 0.2 + mx) % 3, fill=CONSOLE, width=w(1.5))
        if self.com_sonda and time.time() < self.jorro_ate:
            for k in range(9):
                fase = (t * 0.08 + k / 9) % 1
                jx = 144 + math.sin(k * 2.1) * 14 * fase
                jy = base - 4 - math.sin(fase * math.pi) * 70
                c.create_oval(jx - 2.5, jy - 2.5, jx + 2.5, jy + 2.5, fill=self.jorro_cor, outline="")
        if self.chuva_ate:
            for dx_, r_ in ((-22, 10), (-6, 14), (12, 11), (26, 8)):
                c.create_oval(cx + dx_ - r_, 20 - r_, cx + dx_ + r_, 20 + r_, fill=TX3, outline="")
            for k in range(16):
                gx = cx - 32 + (k * 37) % 66
                gy = 32 + (t * 5 + k * 29) % (base - 34)
                c.create_line(gx, gy, gx - 2, gy + 7, fill=ACCENT, width=w(1.2))
            c.create_oval(cx - 36, base - 2, cx + 36, base + 4, fill=ACCENT_ESC, outline="")

    def desenhar_sonda(self, base, ativa, w):
        """Sonda de perfuração DrillGeo (esteira, mastro inclinado, cabeça que desce girando a haste).
        Cor da máquina: âmbar --warn, o token mais próximo do amarelo das sondas."""
        c, t = self.cv, self.t
        MAQ = WARN

        # painel do operador, com a alavanca que o robô segura
        c.create_line(113, base, 113, base - 30, fill=SURFACE, width=w(3))
        self.retangulo(104, base - 44, 122, base - 30, 3, fill=SURFACE, outline=LINE2, width=w(1))
        c.create_oval(107, base - 40, 111, base - 36, fill=OK if ativa and (t // 8) % 2 else LINE2, outline="")
        giro = math.sin(t * 0.25) * 3 if ativa else 0
        self.alavanca = (113 + giro, base - 57)
        c.create_line(113, base - 44, *self.alavanca, fill=TX2, width=w(2.5))

        # esteira e chassi
        self.retangulo(130, base - 13, 252, base, 6, fill=SURFACE, outline="")
        for rx, rr in ((138, 5.5), (244, 5.5), (162, 3), (190, 3), (218, 3)):
            c.create_oval(rx - rr, base - 6.5 - rr, rx + rr, base - 6.5 + rr, fill=LINE2, outline="")
        if ativa:  # garras da esteira vibrando
            for k in range(8):
                gx = 136 + k * 15 + (t % 2)
                c.create_line(gx, base, gx + 4, base, fill=LINE2, width=w(1.5))
        c.create_rectangle(128, base - 24, 254, base - 13, fill=MAQ, outline=SURFACE, width=w(1.5))

        # tanque de água/lama e painel de manômetros
        self.retangulo(226, base - 56, 248, base - 24, 5, fill=MAQ, outline=SURFACE, width=w(1.5))
        c.create_rectangle(233, base - 61, 241, base - 56, fill=SURFACE, outline="")
        c.create_rectangle(190, base - 52, 216, base - 24, fill=SURFACE, outline=LINE2, width=w(1))
        for gx in (197, 209):
            c.create_oval(gx - 3.5, base - 48.5, gx + 3.5, base - 41.5, fill=BG, outline=TX2, width=w(1))
            ang = (math.sin(t * 0.3 + gx) * 0.8 if ativa else -0.8) - math.pi / 2
            c.create_line(gx, base - 45, gx + 3 * math.cos(ang), base - 45 + 3 * math.sin(ang), fill=TX, width=w(1))
        for k, cor in enumerate((OK, ACCENT, OK)):
            acesa = ativa and (t // 6 + k) % 3 != 0
            c.create_rectangle(194 + k * 7, base - 35, 198 + k * 7, base - 31, fill=cor if acesa else LINE2, outline="")

        # mastro: sobe de deitado para inclinado quando a sonda é montada
        sobe = 1 - (1 - self.sonda_t) ** 2
        a = math.radians(8 + 68 * sobe)
        bx, by, comp = 144.0, base - 2.0, 138.0
        dx, dy = math.cos(a), -math.sin(a)
        tx, ty = bx + comp * dx, by + comp * dy
        c.create_line(bx, by, tx, ty, fill=SURFACE, width=w(11))
        c.create_line(bx, by, tx, ty, fill=MAQ, width=w(8))
        c.create_line(bx, by, tx, ty, fill=SURFACE, width=w(1.5))
        c.create_rectangle(tx - 6, ty - 4, tx + 6, ty + 3, fill=MAQ, outline=SURFACE, width=w(1.5))
        c.create_rectangle(136, base - 5, 154, base, fill=MAQ, outline=SURFACE, width=w(1.5))  # sapata

        # cabeça de perfuração: desce devagar girando a haste e volta rápido
        s = 0.85
        if ativa and self.sonda_t >= 1:
            ciclo = (t % 160) / 160
            s = 0.85 - 0.65 * (ciclo / 0.85) if ciclo < 0.85 else 0.2 + 0.65 * ((ciclo - 0.85) / 0.15)
        hx, hy = bx + comp * s * dx, by + comp * s * dy
        c.create_line(hx, hy, bx, by, fill=TX2, width=w(3))                        # haste
        if ativa:
            passo = 7
            for k in range(int(comp * s / passo)):
                d = k * passo + (t * 2) % passo
                px_, py_ = bx + d * dx, by + d * dy
                c.create_line(px_ - 2, py_ - 1, px_ + 2, py_ + 1, fill=SURFACE, width=w(1))
        c.create_line(196, base - 50, (196 + hx) / 2, base - 70, hx + 4, hy, fill=SURFACE, width=w(2), smooth=True)
        c.create_rectangle(hx - 8, hy - 6, hx + 8, hy + 6, fill=MAQ, outline=SURFACE, width=w(1.5))
        c.create_rectangle(hx - 3, hy - 9, hx + 5, hy - 6, fill=SURFACE, outline="")

        # poeira da perfuração
        if ativa and self.sonda_t >= 1:
            for k in range(5):
                fase = (t * 0.15 + k * 1.3) % 2.0
                px_ = bx + (k - 2) * 4 + math.sin(t * 0.4 + k) * 2
                py_ = by - fase * 7
                c.create_oval(px_ - 1.6, py_ - 1.6, px_ + 1.6, py_ + 1.6, fill=TX3, outline="")

        # quebrada: fumaça saindo do motor e luz vermelha; senão, barra do furo
        if self.vida["quebrada"]:
            c.create_oval(229, base - 52, 235, base - 46, fill=BAD if (t // 6) % 2 else LINE2, outline="")
            for k in range(4):
                fase = (t * 0.03 + k / 4) % 1
                r_ = 3 + fase * 7
                fx, fy = 237 + math.sin(fase * 5 + k) * 5, base - 62 - fase * 45
                c.create_oval(fx - r_, fy - r_, fx + r_, fy + r_, fill=TX3 if k % 2 else LINE2, outline="")
        elif self.sonda_t >= 1:
            c.create_rectangle(160, base - 31, 186, base - 27, fill=BG, outline=LINE2, width=w(1))
            c.create_rectangle(160, base - 31, 160 + 26 * self.vida["furo"] / 100, base - 27, fill=OK, outline="")

    def rosto(self, cx, ey, st, w):
        c = self.cv
        olhos = (cx - 11, cx + 11)
        if st in ("parado", "andando", "operando", "sentado", "escalando"):
            emo = self.emocao()
            st = {"cansado": "cansado", "triste": "triste", "preocupado": "triste"}.get(emo, st)
            if emo == "feliz" and st != "sentado" and not self.piscar:
                st = "feliz"
        if st == "doido":
            st = "testemunho"   # olhos arregalados
        if st in ("testemunho", "amor", "feliz", "recarregando"):
            if st == "amor":       # olhos de coração
                for ex in olhos:
                    c.create_oval(ex - 6, ey - 5, ex, ey + 1, fill=BAD, outline="")
                    c.create_oval(ex, ey - 5, ex + 6, ey + 1, fill=BAD, outline="")
                    c.create_polygon(ex - 6, ey - 2, ex + 6, ey - 2, ex, ey + 6, fill=BAD, outline="")
            elif st == "testemunho":   # olhos arregalados de surpresa
                for ex in olhos:
                    c.create_oval(ex - 6, ey - 7, ex + 6, ey + 7, fill=ACCENT, outline="")
                    c.create_oval(ex - 2, ey - 4, ex + 2, ey, fill=CLARO, outline="")
            else:
                for ex in olhos:
                    c.create_arc(ex - 6, ey - 3, ex + 6, ey + 9, start=20, extent=140, style="arc",
                                 outline=ACCENT, width=w(3))
            if st == "testemunho":
                c.create_oval(cx - 4, ey + 6, cx + 4, ey + 14, fill=ACCENT, outline="")
            else:
                c.create_arc(cx - 7, ey + 2, cx + 7, ey + 14, start=180, extent=180, style="chord", fill=ACCENT, outline="")
            return
        if st == "bocejando":
            for ex in olhos:
                c.create_line(ex - 5, ey - 1, ex + 5, ey + 1, fill=ACCENT, width=w(3), capstyle="round")
            abre = 5 + abs(math.sin(self.t * 0.15)) * 4
            c.create_oval(cx - 5, ey + 5, cx + 5, ey + 5 + abre * 1.4, fill=ACCENT, outline="")
            return
        if st in ("cansado", "triste", "consertando", "lubrificando"):
            for i, ex in enumerate(olhos):
                if st == "cansado":   # pálpebra pesada
                    c.create_arc(ex - 5, ey - 5, ex + 5, ey + 6, start=180, extent=180, style="chord", fill=ACCENT, outline="")
                    c.create_line(ex - 6, ey, ex + 6, ey, fill=ACCENT, width=w(2))
                else:
                    c.create_oval(ex - 5, ey - 5, ex + 5, ey + 6, fill=ACCENT, outline="")
                    if st == "triste":   # sobrancelha caída
                        s_ = -1 if i == 0 else 1
                        c.create_line(ex - 6, ey - 9 - 2 * s_, ex + 6, ey - 9 + 2 * s_, fill=ACCENT, width=w(2))
            if st == "triste":
                c.create_arc(cx - 6, ey + 8, cx + 6, ey + 16, start=20, extent=140, style="arc", outline=ACCENT, width=w(2))
                if (self.t // 30) % 3 == 0:   # lagriminha
                    gy = ey + 6 + (self.t % 30) * 0.5
                    c.create_oval(olhos[0] - 3, gy, olhos[0] + 1, gy + 5, fill=ACCENT, outline="")
            elif st == "cansado":
                c.create_line(cx - 4, ey + 11, cx + 4, ey + 11, fill=ACCENT, width=w(2), capstyle="round")
            else:   # concentrado no conserto
                c.create_line(cx - 3, ey + 11, cx + 5, ey + 9, fill=ACCENT, width=w(2), capstyle="round")
            return
        if st == "dormindo":
            for ex in olhos:
                c.create_arc(ex - 6, ey - 6, ex + 6, ey + 4, start=200, extent=140, style="arc", outline=ACCENT, width=w(2.5))
            c.create_oval(cx - 3, ey + 7, cx + 3, ey + 12, outline=ACCENT, width=w(2))
            return
        if st == "comemorando":
            for ex in olhos:
                c.create_arc(ex - 6, ey - 3, ex + 6, ey + 9, start=20, extent=140, style="arc", outline=ACCENT, width=w(3))
            c.create_arc(cx - 7, ey + 2, cx + 7, ey + 14, start=180, extent=180, style="chord", fill=ACCENT, outline="")
            return
        if st == "confuso":
            c.create_oval(olhos[0] - 6, ey - 7, olhos[0] + 6, ey + 7, fill=ACCENT, outline="")
            c.create_line(olhos[1] - 6, ey - 1, olhos[1] + 6, ey + 1, fill=ACCENT, width=w(3), capstyle="round")
            c.create_line(cx - 7, ey + 11, cx - 3, ey + 8, cx + 1, ey + 11, cx + 5, ey + 8, cx + 8, ey + 10,
                          fill=ACCENT, width=w(2), smooth=False)
            return
        fechado = self.piscar > 0 and st != "pensando"
        sobe = -3 if st == "pensando" else 0
        desvio = math.sin(self.t * 0.08) * 2 if st == "pensando" else 0
        for ex in olhos:
            if fechado:
                c.create_line(ex - 5, ey, ex + 5, ey, fill=ACCENT, width=w(3), capstyle="round")
            elif st == "sentado":
                c.create_oval(ex - 5, ey - 4, ex + 5, ey + 5, fill=ACCENT, outline="")
            else:
                c.create_oval(ex - 5 + desvio, ey - 6 + sobe, ex + 5 + desvio, ey + 6 + sobe, fill=ACCENT, outline="")
        if st == "pensando":
            c.create_line(cx - 4, ey + 10, cx + 4, ey + 10, fill=ACCENT, width=w(2), capstyle="round")
        else:
            c.create_arc(cx - 6, ey + 3, cx + 6, ey + 12, start=200, extent=140, style="arc", outline=ACCENT, width=w(2))

    def retangulo(self, x1, y1, x2, y2, r, **kw):
        pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
               x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
        return self.cv.create_polygon(pts, smooth=True, **kw)

    # ---------- mouse ----------

    def ao_apertar(self, e):
        self.arraste = (e.x_root, e.y_root, self.x, self.y, False)

    def ao_arrastar(self, e):
        if not self.arraste:
            return
        x0, y0, rx, ry, movendo = self.arraste
        if not movendo and abs(e.x_root - x0) + abs(e.y_root - y0) < 5:
            return
        self.arraste = (x0, y0, rx, ry, True)
        self.estado = "arrastando"
        self.alvo_x = None
        self.lado = 0
        self.x = rx + e.x_root - x0
        self.y = ry + e.y_root - y0
        self.fechar_balao()

    def ao_soltar(self, e):
        if not self.arraste:
            return
        movendo = self.arraste[4]
        self.arraste = None
        self.mexeu()
        if movendo:
            if self.modo == "parado":       # parado: fica onde foi solto
                self.mudar("parado")
            else:
                self.mudar("caindo")
            return
        if self.pedido:
            self.mostrar_pensando()
        else:
            self.abrir_painel()

    # ---------- menu ----------

    def montar_menu(self):
        m = tk.Menu(self.root, tearoff=0, bg=SURFACE, fg=TX, activebackground=ATIVO, activeforeground=TX,
                    font=(self.fonte, 10), bd=0, relief="flat")
        m.add_command(label="Painel (vida e ferramentas)", command=self.abrir_painel)
        m.add_command(label="Perguntar ao Claude", command=self.abrir_pergunta)
        m.add_command(label="Nova conversa", command=self.nova_conversa)
        m.add_command(label="Procurar no cofre", command=self.abrir_busca)
        m.add_command(label="Ferramentas de PDF", command=self.abrir_pdf)
        m.add_command(label="Imagens (converter / tirar fundo)", command=self.abrir_imagens)
        m.add_command(label="Corretor ortográfico", command=self.abrir_corretor)
        m.add_command(label="Analisar documento", command=self.analisar_documento)
        m.add_command(label="Auditoria de erros", command=self.auditoria)
        m.add_command(label="Lembretes", command=self.abrir_lembrete)
        m.add_command(label="Jogar: moto pela tela", command=lambda: self.jogar("moto"))
        m.add_command(label="Jogar: nave e monstrinhos", command=lambda: self.jogar("nave"))
        m.add_command(label="Descansar: passeio de moto (sozinho)", command=lambda: self.jogar("moto", True))
        m.add_command(label="Descansar: passeio de nave (sozinho)", command=lambda: self.jogar("nave", True))
        m.add_separator()
        cuidar = tk.Menu(m, tearoff=0, bg=SURFACE, fg=TX, activebackground=ATIVO, activeforeground=TX,
                         font=(self.fonte, 10), bd=0)
        cuidar.add_command(label="Recarregar bateria", command=lambda: self.cuidar("recarregar"))
        cuidar.add_command(label="Passar óleo (R$ 5)", command=lambda: self.cuidar("oleo"))
        cuidar.add_command(label="Fazer carinho", command=lambda: self.cuidar("carinho"))
        cuidar.add_command(label="Revisão mecânica da sonda", command=lambda: self.revisar("mecanica"))
        cuidar.add_command(label="Revisão elétrica da sonda", command=lambda: self.revisar("eletrica"))
        cuidar.add_command(label="Trocar peças quebradas", command=self.trocar_quebradas)
        for v in (10, 50, 100):
            cuidar.add_command(label=f"Doar R$ {v}", command=lambda v=v: self.doar(v))
        m.add_cascade(label="Cuidar", menu=cuidar)
        m.add_command(label="Chaves das IAs grátis", command=self.abrir_chaves)
        m.add_separator()
        m.add_command(label="Andar", command=lambda: self.trocar_modo("andar"))
        m.add_command(label="Parar", command=lambda: self.trocar_modo("parado"))
        m.add_command(label="Dormir", command=self.dormir)
        m.add_command(label="Ficar no canto", command=lambda: self.trocar_modo("canto"))
        m.add_separator()
        m.add_checkbutton(label="Atalho Ctrl+Alt+Espaço", variable=self.var_atalho, command=self.trocar_atalho)
        m.add_checkbutton(label="Abrir junto com o Windows", variable=self.var_iniciar, command=self.trocar_iniciar)
        m.add_command(label="Entrar no Claude Code (login)", command=self.fazer_login)
        m.add_command(label="Abrir o LEIA-ME", command=lambda: os.startfile(str(PASTA / "LEIA-ME.md")))
        m.add_separator()
        m.add_command(label="Fechar", command=self.fechar)
        self.menu = m

    def abrir_menu(self, e):
        self.mexeu()
        try:
            self.menu.tk_popup(e.x_root, e.y_root)
        finally:
            self.menu.grab_release()

    def trocar_modo(self, modo):
        self.mexeu()
        self.modo = modo
        self.alvo_x = None
        self.salvar_config()
        if modo == "canto":
            self.ir_para_canto()
        elif modo == "andar":
            self.estado = "caindo" if self.y < self.chao() - 1 else "andando"
            self.prox_decisao = time.time() + 5
        else:
            self.operar()

    def ir_para_canto(self):
        L, T, R, B = area_de_trabalho()
        if self.y < self.chao() - 1:
            self.y = float(self.chao())
        self.alvo_x = float(R - self.px(self.W) - 8)
        self.depois_alvo = "operando"

    def dormir(self, pedido=True):
        self.alvo_x = None
        self.lado = 0
        self.estado = "dormindo"
        self.sono_pedido = pedido
        if pedido:
            self.ultima_interacao = time.time() - SONO_ANDANDO_SEG - 60  # continua dormindo até alguém mexer

    def nova_conversa(self):
        self.mexeu()
        self.sessao = None
        self.sessao_iniciada = False
        self.historico = []
        self.var_continuar.set(False)
        self.aviso("Conversa nova", "Pronto. A próxima pergunta começa do zero: o Claude não lembra do que foi falado antes.")

    def fechar(self):
        if self.pedido:
            self.pedido.cancelar()
        if self.atalho:
            self.atalho.parar()
        if not self.demo:
            self.salvar_config()
        self.root.destroy()

    # ---------- atalho global e inicialização ----------

    def ligar_atalho(self):
        self.atalho = AtalhoGlobal(self.fila)
        self.atalho.start()

    def trocar_atalho(self):
        if self.var_atalho.get():
            self.ligar_atalho()
        elif self.atalho:
            self.atalho.parar()
            self.atalho = None
        self.salvar_config()

    def trocar_iniciar(self):
        lnk = pasta_inicializar() / f"{NOME}.lnk"
        if self.var_iniciar.get():
            if not self.confirmar("Abrir junto com o Windows?",
                                  "O robô vai abrir sozinho toda vez que você entrar no Windows.\n"
                                  "Dá para desligar aqui mesmo, no mesmo item do menu.",
                                  "Sim, abrir junto"):
                self.var_iniciar.set(False)
                return
            if not criar_lnk(lnk):
                self.var_iniciar.set(False)
                self.aviso("Não consegui", "Não consegui criar o atalho de inicialização do Windows.", erro=True)
        else:
            try:
                if lnk.is_file():
                    lnk.unlink()   # só o atalho que o próprio robô criou
            except Exception:
                registrar_erro(traceback.format_exc())

    def fazer_login(self):
        exe = self.claude_exe or achar_claude()
        if not exe:
            self.aviso_sem_claude()
            return
        # Abre uma janela de terminal; o login é feito pela própria pessoa, no navegador.
        subprocess.Popen(["cmd", "/c", "start", "Login do Claude Code", "cmd", "/k", exe, "auth", "login"],
                         env=ambiente_limpo(), creationflags=0x08000000)

    # ---------- fila (respostas do Claude e atalho) ----------

    def ler_fila(self):
        while True:
            try:
                tipo, dado, origem = self.fila.get_nowait()
            except queue.Empty:
                return
            if tipo == "atalho" and self.jogo_ativo:
                self.jogo_ativo.fim()
            elif tipo == "atalho":
                self.mexeu()
                if self.pedido:
                    self.mostrar_pensando()
                else:
                    self.abrir_pergunta()
            elif tipo == "arquivos":
                self.receber_arquivos(dado)
            elif tipo == "atalho_status":
                self.atalho_ok = dado
                if not dado:
                    self.var_atalho.set(False)
            elif origem is self.pedido:
                self.pedido = None
                self.mexeu()
                if tipo == "resposta":
                    if origem.motor == "claude":
                        self.sessao_iniciada = True
                    self.historico += [{"role": "user", "content": origem.texto},
                                       {"role": "assistant", "content": dado}]
                    self.vida["dinheiro"] += 2          # gorjeta por ajudar
                    self.ajustar(humor=4, energia=-1)
                    self.mudar("comemorando", 2.8)
                    self.mostrar_resposta(dado, motor=origem.motor)
                else:
                    self.mudar("confuso", 4.5)
                    self.mostrar_resposta(dado, erro=True)

    # ---------- conversa ----------

    def enviar(self, texto, continuar):
        texto = texto.strip()
        if not texto:
            return
        if not self.claude_exe:
            self.claude_exe = achar_claude()
        if not self.claude_exe and not fn.ordem_motores():
            self.mudar("confuso", 4.5)
            self.aviso("Nenhuma IA configurada", "Coloque uma chave grátis no menu > Chaves das IAs grátis.", erro=True)
            return
        fazer = texto.lower().startswith("!fazer")
        sinais = fn.sinais_sensiveis(texto)
        externo = not fazer and not fn.tem_dado_pessoal(texto) and any(
            n != "claude" for n, _, _ in fn.ordem_motores())
        if externo and sinais:
            self.fechar_balao()
            if not self.confirmar("Mandar para IA grátis?",
                                  "Este texto parece ter dado de colaborador (" + ", ".join(sinais[:4]) + ").\n\n"
                                  "Ele vai para uma IA grátis de fora da empresa (Groq, Google ou OpenRouter), "
                                  "que pode guardar o que recebe. Holerite, ficha, atestado e documentos com nome "
                                  "de colaborador não devem ir (LGPD).",
                                  "Enviar mesmo assim"):
                return
        if fazer:
            texto = texto[6:].strip(" :,-")
            if not texto:
                return
            self.fechar_balao()
            if not self.confirmar("Tem certeza?",
                                  "Com !fazer o Claude PODE CRIAR E ALTERAR ARQUIVOS no cofre e nas pastas "
                                  "da empresa para cumprir o pedido.\n\nComandos de terminal continuam bloqueados.",
                                  "Sim, pode alterar"):
                return
        if not (continuar and (self.historico or self.sessao and self.sessao_iniciada)):
            continuar = False
        if not (continuar and self.sessao and self.sessao_iniciada):   # conversa do Claude Code
            self.sessao = str(uuid.uuid4())
            self.sessao_iniciada = False
        self.ultima_pergunta = texto
        self.ultimo_fazer = fazer
        self.inicio_pedido = time.time()
        if not continuar:
            self.historico = []
        self.pedido = Pedido(self.fila, self.claude_exe, texto, fazer, self.sessao, continuar, self.historico)
        self.pedido.start()
        self.mexeu()
        self.mostrar_pensando()

    def cancelar_pedido(self):
        if self.pedido:
            self.pedido.cancelar()
            self.pedido = None
        self.fechar_balao()
        self.mudar("parado")

    # ---------- balões ----------

    def novo_balao(self, tipo):
        self.fechar_balao()
        b = tk.Toplevel(self.root)
        b.overrideredirect(True)
        b.attributes("-topmost", True)
        b.configure(bg=LINE2)
        moldura = tk.Frame(b, bg=SURFACE, padx=self.px(14), pady=self.px(12))
        moldura.pack(padx=1, pady=1, fill="both", expand=True)
        b.bind("<Escape>", lambda e: self.fechar_balao())
        self.balao, self.balao_tipo = b, tipo
        return b, moldura

    def posicionar_balao(self, b):
        b.update_idletasks()
        L, T, R, B = area_de_trabalho()
        bw, bh = b.winfo_reqwidth(), b.winfo_reqheight()
        meio = self.x + self.px(self.CX)
        x = int(min(max(meio - bw / 2, L + 8), R - bw - 8))
        y = int(self.y + self.px(20) - bh)
        if y < T + 8:   # sem espaço em cima: abre embaixo do robô
            y = int(min(self.y + self.px(self.H), B - bh - 8))
        b.geometry(f"+{x}+{y}")
        esconder_da_barra(b)

    def fechar_balao(self):
        if self.balao_tipo == "alerta" and self.alerta:   # fechou sem responder: lembra de novo em 5 min
            l, self.alerta = self.alerta, None
            l["quando"] = time.time() + 300
            self.gravar_lembretes()
            if self.estado == "doido":
                self.mudar("parado")
        if self.balao is not None:
            try:
                self.balao.destroy()
            except Exception:
                pass
        self.balao, self.balao_tipo = None, None

    def cabecalho(self, pai, titulo, chip=None, chip_cor=None):
        linha = tk.Frame(pai, bg=SURFACE)
        linha.pack(fill="x", pady=(0, self.px(8)))
        tk.Label(linha, text=titulo, bg=SURFACE, fg=TX, font=(self.fonte, 11, "bold")).pack(side="left")
        if chip:
            tk.Label(linha, text=chip, bg=ATIVO, fg=chip_cor or ACCENT, font=(self.fonte, 8, "bold"),
                     padx=self.px(7), pady=self.px(2)).pack(side="left", padx=(self.px(8), 0))
        x = tk.Label(linha, text="×", bg=SURFACE, fg=TX3, font=(self.fonte, 14), cursor="hand2")
        x.pack(side="right")
        x.bind("<Button-1>", lambda e: self.fechar_balao())
        x.bind("<Enter>", lambda e: x.configure(fg=TX))
        x.bind("<Leave>", lambda e: x.configure(fg=TX3))
        return linha

    def botao(self, pai, texto, comando, principal=False):
        cor, cor_h, fg = (ACCENT, "#5da2e8", "#ffffff") if principal else (SURFACE2, HOVER, TX)
        bt = tk.Label(pai, text=texto, bg=cor, fg=fg, font=(self.fonte, 9, "bold" if principal else "normal"),
                      padx=self.px(11), pady=self.px(5), cursor="hand2", highlightthickness=0)
        bt.bind("<Button-1>", lambda e: comando())
        bt.bind("<Enter>", lambda e: bt.configure(bg=cor_h))
        bt.bind("<Leave>", lambda e: bt.configure(bg=cor))
        return bt

    def abrir_pergunta(self, continuar=None):
        self.mexeu()
        b, m = self.novo_balao("pergunta")
        tem_conversa = bool(self.historico or self.sessao and self.sessao_iniciada)
        so_gratis = not any(n == "claude" for n, _, _ in fn.ordem_motores())
        self.cabecalho(m, "Pergunte ao robô" if so_gratis else "Pergunte ao Claude",
                       "IA GRÁTIS" if so_gratis else "SÓ LEITURA")
        caixa = tk.Text(m, width=44, height=4, wrap="word", bg=CONSOLE, fg=TX, insertbackground=TX,
                        relief="flat", font=(self.fonte, 10), padx=self.px(9), pady=self.px(7),
                        highlightthickness=1, highlightbackground=LINE2, highlightcolor=ACCENT)
        caixa.pack(fill="x")
        rodape = tk.Frame(m, bg=SURFACE)
        rodape.pack(fill="x", pady=(self.px(8), 0))
        if continuar is not None:
            self.var_continuar.set(continuar)
        elif not tem_conversa:
            self.var_continuar.set(False)
        ck = tk.Checkbutton(rodape, text="Continuar a conversa", variable=self.var_continuar,
                            bg=SURFACE, fg=TX2, selectcolor=CONSOLE, activebackground=SURFACE,
                            activeforeground=TX, font=(self.fonte, 9), bd=0, highlightthickness=0,
                            state="normal" if tem_conversa else "disabled", disabledforeground=TX3)
        ck.pack(side="left")
        enviar = lambda: self.enviar(caixa.get("1.0", "end"), self.var_continuar.get())
        self.botao(rodape, "Enviar", enviar, principal=True).pack(side="right")
        tk.Label(m, text="Enter envia · Shift+Enter pula linha · Esc fecha\n"
                         "Comece com !fazer para deixar o Claude alterar arquivos",
                 bg=SURFACE, fg=TX3, font=(self.fonte, 8), justify="left").pack(anchor="w", pady=(self.px(8), 0))

        def tecla_enter(e):
            if e.state & 0x1:  # Shift
                return None
            enviar()
            return "break"
        caixa.bind("<Return>", tecla_enter)
        caixa.bind("<Escape>", lambda e: self.fechar_balao())
        self.posicionar_balao(b)
        trazer_para_frente(b)
        caixa.focus_set()

    def mostrar_pensando(self):
        b, m = self.novo_balao("pensando")
        self.cabecalho(m, "Pensando", "!FAZER" if self.ultimo_fazer else "SÓ LEITURA",
                       WARN if self.ultimo_fazer else None)
        pergunta = self.ultima_pergunta if len(self.ultima_pergunta) <= 90 else self.ultima_pergunta[:87] + "..."
        tk.Label(m, text=pergunta, bg=SURFACE, fg=TX2, font=(self.fonte, 9), wraplength=self.px(300),
                 justify="left").pack(anchor="w")
        rel = tk.Label(m, text="", bg=SURFACE, fg=TX3, font=(self.fonte, 8))
        rel.pack(anchor="w", pady=(self.px(6), self.px(8)))
        self.botao(m, "Cancelar", self.cancelar_pedido).pack(anchor="e")

        def tique():
            if self.balao is not b or not self.pedido:
                return
            seg = int(time.time() - self.inicio_pedido)
            rel.configure(text=f"{seg} s de espera · limite de 3 minutos")
            b.after(1000, tique)
        tique()
        self.posicionar_balao(b)

    def inserir_markdown(self, caixa, texto):
        """Mostra o Markdown da IA formatado: títulos, negrito, itálico, código e listas com •."""
        import re
        caixa.tag_configure("b", font=(self.fonte, 10, "bold"))
        caixa.tag_configure("i", font=(self.fonte, 10, "italic"))
        caixa.tag_configure("h", font=(self.fonte, 11, "bold"), foreground=TX, spacing1=self.px(6), spacing3=self.px(2))
        caixa.tag_configure("code", font=("Consolas", 9), background=SURFACE2)
        caixa.tag_configure("lista", lmargin1=self.px(4), lmargin2=self.px(16))
        caixa.tag_configure("marca", foreground=ACCENT)
        caixa.tag_configure("sep", foreground=LINE2)
        inline = re.compile(r"\*\*(.+?)\*\*|__(.+?)__|`([^`]+)`|(?<![*\w])\*(?!\s)(.+?)(?<!\s)\*(?!\*)")
        for n, linha in enumerate(texto.splitlines()):
            if n:
                caixa.insert("end", "\n")
            s = linha.strip()
            base = ()
            if re.fullmatch(r"[-*_]{3,}", s):
                caixa.insert("end", "―" * 24, ("sep",))
                continue
            m = re.match(r"^(#{1,6})\s+(.*)", s)
            if m:
                s, base = m.group(2), ("h",)
            else:
                m = re.match(r"^([-*+]|\d+[.)])\s+(.*)", s)
                if m:
                    marca = "•" if m.group(1) in "-*+" else m.group(1)
                    recuo = "    " * min(2, (len(linha) - len(linha.lstrip())) // 2)
                    caixa.insert("end", f"{recuo}{marca} ", ("lista", "marca"))
                    s, base = m.group(2), ("lista",)
            pos = 0
            for achado in inline.finditer(s):
                caixa.insert("end", s[pos:achado.start()], base)
                b, b2, code, it = achado.groups()
                if code:
                    caixa.insert("end", code, base + ("code",))
                elif it:
                    caixa.insert("end", it, base + ("i",))
                else:
                    caixa.insert("end", b or b2, base + ("b",))
                pos = achado.end()
            caixa.insert("end", s[pos:], base)

    def mostrar_resposta(self, texto, erro=False, motor="claude", titulo=None):
        b, m = self.novo_balao("resposta")
        hora = time.strftime("%H:%M")
        nome_motor = {"claude": "Claude", "gemini": "Gemini", "groq": "Groq", "openrouter": "OpenRouter"}
        if erro:
            self.cabecalho(m, "Não deu certo", "VERIFICAR", BAD)
        elif titulo:
            self.cabecalho(m, f"{titulo} · {hora}")
        else:
            self.cabecalho(m, f"Resposta do {nome_motor.get(motor, motor)} · {hora}",
                           "!FAZER" if self.ultimo_fazer else ("SÓ LEITURA" if motor == "claude" else "IA GRÁTIS"),
                           WARN if self.ultimo_fazer else None)
        if self.ultima_pergunta and not erro and not titulo:
            p = self.ultima_pergunta if len(self.ultima_pergunta) <= 90 else self.ultima_pergunta[:87] + "..."
            tk.Label(m, text=p, bg=SURFACE, fg=TX3, font=(self.fonte, 9, "italic"), wraplength=self.px(400),
                     justify="left").pack(anchor="w", pady=(0, self.px(6)))
        linhas = texto.count("\n") + 1 + len(texto) // 60
        area = tk.Frame(m, bg=CONSOLE, highlightthickness=1, highlightbackground=LINE2)
        area.pack(fill="both", expand=True)
        caixa = tk.Text(area, width=56, height=max(3, min(16, linhas)), wrap="word", bg=CONSOLE, fg=TX,
                        relief="flat", font=(self.fonte, 10), padx=self.px(10), pady=self.px(8),
                        highlightthickness=0, spacing2=2)
        barra = tk.Scrollbar(area, command=caixa.yview, width=self.px(10))
        caixa.configure(yscrollcommand=barra.set)
        if linhas > 16:
            barra.pack(side="right", fill="y")
        caixa.pack(side="left", fill="both", expand=True)
        self.inserir_markdown(caixa, texto)
        caixa.configure(state="disabled")
        caixa.bind("<MouseWheel>", lambda e: caixa.yview_scroll(int(-e.delta / 120) * 2, "units"))

        rodape = tk.Frame(m, bg=SURFACE)
        rodape.pack(fill="x", pady=(self.px(10), 0))
        copiar = None

        def fazer_copia():
            self.root.clipboard_clear()
            self.root.clipboard_append(fn.limpar_markdown(texto))
            self.root.update()
            copiar.configure(text="Copiado")
            b.after(1500, lambda: copiar.winfo_exists() and copiar.configure(text="Copiar"))
        copiar = self.botao(rodape, "Copiar", fazer_copia)
        copiar.pack(side="left")
        self.botao(rodape, "Abrir no Claude", self.abrir_claude_desktop).pack(side="left", padx=(self.px(6), 0))
        self.botao(rodape, "Fechar", self.fechar_balao).pack(side="right")
        if not erro and not titulo:
            self.botao(rodape, "Responder", lambda: self.abrir_pergunta(continuar=True), principal=True
                       ).pack(side="right", padx=(0, self.px(6)))
        b.bind("<Control-c>", lambda e: fazer_copia())
        self.posicionar_balao(b)
        trazer_para_frente(b)

    def aviso(self, titulo, texto, erro=False):
        b, m = self.novo_balao("aviso")
        self.cabecalho(m, titulo, "VERIFICAR" if erro else None, BAD if erro else None)
        tk.Label(m, text=texto, bg=SURFACE, fg=TX2, font=(self.fonte, 10), wraplength=self.px(330),
                 justify="left").pack(anchor="w")
        self.botao(m, "OK", self.fechar_balao, principal=True).pack(anchor="e", pady=(self.px(10), 0))
        self.posicionar_balao(b)
        b.after(9000, lambda: self.balao is b and self.fechar_balao())

    def aviso_sem_claude(self):
        self.aviso("Claude Code não encontrado",
                   "Não achei o Claude Code neste computador.\n\n"
                   "Peça para instalar (comando: npm install -g @anthropic-ai/claude-code) "
                   "e depois faça o login pelo meu menu > \"Entrar no Claude Code\".", erro=True)

    def confirmar(self, titulo, texto, rotulo_sim):
        """Janelinha de confirmação no padrão DrillGeo. Devolve True/False."""
        resposta = {"ok": False}
        d = tk.Toplevel(self.root)
        d.overrideredirect(True)
        d.attributes("-topmost", True)
        d.configure(bg=LINE2)
        m = tk.Frame(d, bg=SURFACE, padx=self.px(18), pady=self.px(16))
        m.pack(padx=1, pady=1)
        tk.Label(m, text=titulo, bg=SURFACE, fg=TX, font=(self.fonte, 12, "bold")).pack(anchor="w")
        tk.Label(m, text=texto, bg=SURFACE, fg=TX2, font=(self.fonte, 10), wraplength=self.px(360),
                 justify="left").pack(anchor="w", pady=(self.px(8), self.px(14)))
        linha = tk.Frame(m, bg=SURFACE)
        linha.pack(fill="x")

        def fim(v):
            resposta["ok"] = v
            d.destroy()
        self.botao(linha, "Cancelar", lambda: fim(False)).pack(side="right")
        self.botao(linha, rotulo_sim, lambda: fim(True), principal=True).pack(side="right", padx=(0, self.px(8)))
        d.bind("<Escape>", lambda e: fim(False))
        d.update_idletasks()
        L, T, R, B = area_de_trabalho()
        d.geometry(f"+{(L + R - d.winfo_reqwidth()) // 2}+{(T + B - d.winfo_reqheight()) // 2}")
        esconder_da_barra(d)
        trazer_para_frente(d)
        d.grab_set()
        self.root.wait_window(d)
        return resposta["ok"]

    def abrir_claude_desktop(self):
        """Só abre o Claude Desktop; não cola nada."""
        for alvo in ("claude://", r"shell:AppsFolder\Claude_pzs8sxrjxfjjc!Claude"):
            try:
                if alvo.startswith("shell:"):
                    subprocess.Popen(["explorer.exe", alvo])
                else:
                    os.startfile(alvo)
                return
            except Exception:
                continue
        self.aviso("Não consegui", "Não achei o Claude Desktop neste computador.", erro=True)

    # ---------- painel: vida + ferramentas ----------

    def linha_botoes(self, pai, itens, titulo=None):
        if titulo:
            tk.Label(pai, text=titulo.upper(), bg=SURFACE, fg=TX3, font=(self.fonte, 8, "bold")
                     ).pack(anchor="w", pady=(self.px(10), self.px(4)))
        linha = tk.Frame(pai, bg=SURFACE)
        linha.pack(fill="x")
        for texto, comando, *principal in itens:
            self.botao(linha, texto, comando, bool(principal and principal[0])).pack(side="left", padx=(0, self.px(5)))

    def painel_sonda(self, m):
        """Peças da sonda (estado de cada uma) + revisões, limpeza e compra de peça quebrada."""
        v = self.vida
        tk.Label(m, text="SONDA" + ("  ·  SUJA DE PETRÓLEO: TUDO 50% MAIS CARO" if v["suja"] else ""),
                 bg=SURFACE, fg=WARN if v["suja"] else TX3, font=(self.fonte, 8, "bold")
                 ).pack(anchor="w", pady=(self.px(10), self.px(4)))
        grade = tk.Frame(m, bg=SURFACE)
        grade.pack(fill="x")
        for i, (k, (nome, tipo, _)) in enumerate(PECAS.items()):
            x = v["pecas"][k]
            cor = BAD if x <= 0 else OK if x >= 50 else WARN
            tk.Label(grade, text=f"{nome}  " + ("QUEBRADA" if x <= 0 else f"{x:.0f}%"), bg=SURFACE, fg=cor,
                     font=(self.fonte, 8), anchor="w").grid(row=i // 3, column=i % 3, sticky="w",
                                                            padx=(0, self.px(14)), pady=self.px(1))
        itens = [(f"{REVISAO[t][0]} · R$ {self.custo_revisao(t)}", lambda t=t: self.revisar(t))
                 for t in ("mecanica", "eletrica") if self.custo_revisao(t)]
        if v["suja"]:
            itens.append(("Limpar petróleo · R$ 25", lambda: self.cuidar("limpar")))
        if itens:
            tk.Frame(m, bg=SURFACE, height=self.px(6)).pack()
            self.linha_botoes(m, itens[:2])
            if itens[2:]:
                tk.Frame(m, bg=SURFACE, height=self.px(5)).pack()
                self.linha_botoes(m, itens[2:])
        quebradas = self.pecas_quebradas()
        for i in range(0, len(quebradas), 3):
            self.linha_botoes(m, [(f"Comprar {PECAS[k][0]} · R$ {self.preco_peca(k)}",
                                   lambda k=k: self.comprar_peca(k), True) for k in quebradas[i:i + 3]],
                              "Peças quebradas" if i == 0 else None)

    def abrir_painel(self):
        self.mexeu()
        b, m = self.novo_balao("painel")
        v = self.vida
        emo = {"feliz": ("FELIZ", OK), "normal": ("TRANQUILO", ACCENT), "cansado": ("CANSADO", WARN),
               "triste": ("TRISTE", WARN), "preocupado": ("SONDA QUEBRADA", BAD)}[self.emocao()]
        self.cabecalho(m, "Robozinho", *emo)

        # resumo do jogo numa linha só
        tk.Label(m, text=f"R$ {v['dinheiro']}   ·   {v['metros']:,.0f} m perfurados   ·   "
                         f"{v['testemunhos']} testemunhos   ·   {len(v['premios'])} prêmios".replace(",", "."),
                 bg=SURFACE, fg=TX2, font=(self.fonte, 9)).pack(anchor="w", pady=(0, self.px(8)))
        problemas = [p for p, ativo in (("chovendo em cima de mim", self.chuva_ate),
                                        ("sonda suja de petróleo", v["suja"])) if ativo]
        if problemas:
            tk.Label(m, text="Agora: " + " · ".join(problemas), bg=SURFACE, fg=WARN,
                     font=(self.fonte, 9)).pack(anchor="w", pady=(0, self.px(8)))

        # barras finas, sem contorno
        larg = 320
        barras = tk.Canvas(m, width=self.px(larg), height=self.px(4 * 22), bg=SURFACE, highlightthickness=0)
        barras.pack(anchor="w")
        for i, (nome, chave) in enumerate((("Energia", "energia"), ("Óleo", "oleo"), ("Humor", "humor"),
                                           ("Sonda", "sonda"))):
            y = self.px(i * 22 + 8)
            val = v[chave]
            cor = OK if val >= 50 else WARN if val >= 25 else BAD
            barras.create_text(0, y, text=nome, anchor="w", fill=TX3, font=(self.fonte, 8))
            barras.create_line(self.px(62), y, self.px(larg - 40), y, fill=LINE, width=self.px(5), capstyle="round")
            if val > 1:
                barras.create_line(self.px(62), y, self.px(62 + (larg - 102) * val / 100), y, fill=cor,
                                   width=self.px(5), capstyle="round")
            barras.create_text(self.px(larg), y, text=f"{val:.0f}%", anchor="e", fill=TX3, font=(self.fonte, 8))

        # cuidar: ações pequenas; doação como texto discreto
        cuidar = [("Recarregar", lambda: self.cuidar("recarregar")), ("Óleo · R$ 5", lambda: self.cuidar("oleo")),
                  ("Carinho", lambda: self.cuidar("carinho"))]
        self.linha_botoes(m, cuidar, "Cuidar")
        doar = tk.Frame(m, bg=SURFACE)
        doar.pack(anchor="w", pady=(self.px(6), 0))
        tk.Label(doar, text="Doar", bg=SURFACE, fg=TX3, font=(self.fonte, 8)).pack(side="left", padx=(0, self.px(6)))
        for x in (10, 50, 100):
            lk = tk.Label(doar, text=f"R$ {x}", bg=SURFACE, fg=ACCENT, font=(self.fonte, 9), cursor="hand2")
            lk.pack(side="left", padx=(0, self.px(10)))
            lk.bind("<Button-1>", lambda e, x=x: self.doar(x))
            lk.bind("<Enter>", lambda e, w_=lk: w_.configure(fg=TX))
            lk.bind("<Leave>", lambda e, w_=lk: w_.configure(fg=ACCENT))
        self.painel_sonda(m)

        # ferramentas em grade alinhada; só "Perguntar" em destaque
        tk.Frame(m, bg=LINE, height=1).pack(fill="x", pady=(self.px(12), self.px(10)))
        self.botao(m, "Perguntar", self.abrir_pergunta, principal=True).pack(fill="x")
        grade = tk.Frame(m, bg=SURFACE)
        grade.pack(fill="x", pady=(self.px(6), 0))
        ferramentas = [("Procurar no cofre", self.abrir_busca), ("PDF", self.abrir_pdf),
                       ("Imagens", self.abrir_imagens), ("Analisar documento", self.analisar_documento),
                       ("Corretor", self.abrir_corretor), ("Auditoria", self.auditoria),
                       ("Lembretes", self.abrir_lembrete), ("Jogar moto", lambda: self.jogar("moto")),
                       ("Jogar nave", lambda: self.jogar("nave")),
                       ("Passeio de moto", lambda: self.jogar("moto", True)),
                       ("Passeio de nave", lambda: self.jogar("nave", True))]
        for i, (texto, cmd) in enumerate(ferramentas):
            bt = self.botao(grade, texto, cmd)
            bt.configure(anchor="w")
            bt.grid(row=i // 2, column=i % 2, sticky="ew", padx=(0, self.px(4) if i % 2 == 0 else 0),
                    pady=(0, self.px(4)))
        grade.columnconfigure(0, weight=1, uniform="f")
        grade.columnconfigure(1, weight=1, uniform="f")
        tk.Label(m, text="Dica: arraste uma imagem ou PDF para cima de mim.", bg=SURFACE, fg=TX3,
                 font=(self.fonte, 8)).pack(anchor="w", pady=(self.px(4), 0))
        self.posicionar_balao(b)
        trazer_para_frente(b)

    def abrir_busca(self):
        self.mexeu()
        b, m = self.novo_balao("busca")
        self.cabecalho(m, "Procurar no cofre")
        caixa = tk.Entry(m, width=44, bg=CONSOLE, fg=TX, insertbackground=TX, relief="flat", font=(self.fonte, 10),
                         highlightthickness=1, highlightbackground=LINE2, highlightcolor=ACCENT)
        caixa.pack(fill="x", ipady=self.px(5))
        lista = tk.Frame(m, bg=SURFACE)
        lista.pack(fill="x", pady=(self.px(8), 0))

        def abrir(p):
            try:
                os.startfile(fn.link_obsidian(COFRE, p))
            except Exception:
                os.startfile(str(p))

        def procurar(e=None):
            for w_ in lista.winfo_children():
                w_.destroy()
            achados = fn.buscar_cofre(COFRE, caixa.get())
            if not achados:
                tk.Label(lista, text="Nada encontrado.", bg=SURFACE, fg=TX3, font=(self.fonte, 9)).pack(anchor="w")
            for p, trecho in achados:
                item = tk.Frame(lista, bg=SURFACE2, highlightthickness=1, highlightbackground=LINE2, cursor="hand2")
                item.pack(fill="x", pady=(0, self.px(4)))
                rotulos = [tk.Label(item, text=p.stem, bg=SURFACE2, fg=ACCENT, font=(self.fonte, 9, "bold"),
                                    anchor="w", padx=self.px(8)),
                           tk.Label(item, text=f"{p.parent.relative_to(COFRE)}  ·  {trecho[:90]}", bg=SURFACE2, fg=TX3,
                                    font=(self.fonte, 8), anchor="w", padx=self.px(8), wraplength=self.px(380),
                                    justify="left")]
                for w_ in [item] + rotulos:
                    w_.bind("<Button-1>", lambda e, p=p: abrir(p))
                for r_ in rotulos:
                    r_.pack(fill="x")
            self.posicionar_balao(b)
        caixa.bind("<Return>", procurar)
        caixa.bind("<Escape>", lambda e: self.fechar_balao())
        self.botao(m, "Procurar", procurar, principal=True).pack(anchor="e", pady=(self.px(6), 0))
        tk.Label(m, text="Clique no resultado para abrir no Obsidian.", bg=SURFACE, fg=TX3,
                 font=(self.fonte, 8)).pack(anchor="w")
        self.posicionar_balao(b)
        trazer_para_frente(b)
        caixa.focus_set()

    def escolher(self, varios=False, titulo="Escolha o arquivo", tipos=(("PDF", "*.pdf"),)):
        self.fechar_balao()
        tipos = tuple(tipos) + (("Todos", "*.*"),)
        if varios:
            return list(filedialog.askopenfilenames(parent=self.root, title=titulo, filetypes=tipos))
        c = filedialog.askopenfilename(parent=self.root, title=titulo, filetypes=tipos)
        return [c] if c else []

    def rodar_pdf(self, acao, soltos=None):
        self.fechar_balao()
        try:
            if acao == "juntar":
                arqs = soltos or self.escolher(True, "Escolha os PDFs na ordem (Ctrl+clique)")
                if len(arqs) < 2:
                    return
                saidas = fn.pdf_juntar(arqs)
            else:
                arqs = soltos or self.escolher()
                if not arqs:
                    return
                faixa = ""
                if acao == "extrair":
                    faixa = self.perguntar_texto("Quais páginas?", "Ex.: 1-3, 5, 8-")
                    if not faixa:
                        return
                saidas = []
                for a in arqs:   # arrastou vários: faz em todos
                    if acao == "separar":
                        saidas += fn.pdf_separar(a)
                    elif acao == "girar":
                        saidas += fn.pdf_girar(a)
                    elif acao == "texto":
                        saidas += fn.pdf_para_texto(a)
                    else:
                        saidas += fn.pdf_extrair(a, faixa)
        except Exception as e:
            registrar_erro(traceback.format_exc())
            self.mudar("confuso", 3)
            self.aviso("Não deu certo", str(e), erro=True)
            return
        premio = self.recompensar("pdf", len(arqs))
        pasta = Path(saidas[0]).parent
        b, m = self.novo_balao("aviso")
        self.cabecalho(m, "PDF pronto", "OK", OK)
        nomes = "\n".join(Path(s).name for s in saidas[:5]) + (f"\n… e mais {len(saidas) - 5}" if len(saidas) > 5 else "")
        tk.Label(m, text=f"{len(saidas)} arquivo(s) novo(s), o original não mudou:\n{nomes}", bg=SURFACE, fg=TX2,
                 font=(self.fonte, 9), justify="left", wraplength=self.px(360)).pack(anchor="w")
        self.linha_premio(m, premio)
        self.linha_botoes(m, [("Abrir pasta", lambda: os.startfile(str(pasta)), True), ("Fechar", self.fechar_balao)])
        self.posicionar_balao(b)
        trazer_para_frente(b)

    def perguntar_texto(self, titulo, dica):
        """Caixinha de uma linha; devolve o texto ou ''."""
        resposta = {"t": ""}
        d = tk.Toplevel(self.root)
        d.overrideredirect(True)
        d.attributes("-topmost", True)
        d.configure(bg=LINE2)
        m = tk.Frame(d, bg=SURFACE, padx=self.px(16), pady=self.px(14))
        m.pack(padx=1, pady=1)
        tk.Label(m, text=titulo, bg=SURFACE, fg=TX, font=(self.fonte, 11, "bold")).pack(anchor="w")
        tk.Label(m, text=dica, bg=SURFACE, fg=TX3, font=(self.fonte, 8)).pack(anchor="w")
        e = tk.Entry(m, width=30, bg=CONSOLE, fg=TX, insertbackground=TX, relief="flat", font=(self.fonte, 10))
        e.pack(fill="x", pady=(self.px(6), self.px(10)), ipady=self.px(4))

        def fim(ok):
            resposta["t"] = e.get().strip() if ok else ""
            d.destroy()
        self.linha_botoes(m, [("OK", lambda: fim(True), True), ("Cancelar", lambda: fim(False))])
        e.bind("<Return>", lambda ev: fim(True))
        e.bind("<Escape>", lambda ev: fim(False))
        d.update_idletasks()
        L, T, R, B = area_de_trabalho()
        d.geometry(f"+{(L + R - d.winfo_reqwidth()) // 2}+{(T + B - d.winfo_reqheight()) // 2}")
        trazer_para_frente(d)
        e.focus_set()
        d.grab_set()
        self.root.wait_window(d)
        return resposta["t"]

    def abrir_pdf(self):
        self.mexeu()
        b, m = self.novo_balao("pdf")
        self.cabecalho(m, "Ferramentas de PDF")
        tk.Label(m, text="O original nunca é alterado: o resultado sai ao lado, com nome novo.",
                 bg=SURFACE, fg=TX3, font=(self.fonte, 8)).pack(anchor="w")
        self.linha_botoes(m, [("Juntar", lambda: self.rodar_pdf("juntar"), True),
                              ("Separar páginas", lambda: self.rodar_pdf("separar")),
                              ("Extrair páginas", lambda: self.rodar_pdf("extrair"))])
        self.linha_botoes(m, [("Girar 90°", lambda: self.rodar_pdf("girar")),
                              ("Virar texto (.txt)", lambda: self.rodar_pdf("texto"))])
        self.posicionar_balao(b)
        trazer_para_frente(b)

    # ---------- recompensa por usar as ferramentas ----------

    # ferramenta: (plural para o prêmio, R$ por arquivo)
    FERRAMENTAS = {"pdf": ("PDFs", 3), "imagem": ("imagens convertidas", 2), "fundo": ("fundos removidos", 5)}
    MARCAS_USO = [(1, 10), (10, 30), (50, 80), (100, 150), (500, 500)]   # (usos, bônus R$)

    def recompensar(self, ferramenta, qtd):
        """Dinheiro por arquivo, bônus no primeiro uso do dia e prêmio nas marcas. Devolve o texto do balão."""
        nome, por_arquivo = self.FERRAMENTAS[ferramenta]
        usos = self.vida.setdefault("usos", {})
        dias = self.vida.setdefault("uso_dia", {})
        antes = usos.get(ferramenta, 0)
        usos[ferramenta] = antes + qtd
        ganho = por_arquivo * min(qtd, 20)                 # teto: juntar 300 arquivos não vira fortuna
        partes = [f"+ R$ {ganho}"]
        hoje = time.strftime("%Y-%m-%d")
        if dias.get(ferramenta) != hoje:
            dias[ferramenta] = hoje
            ganho += 10
            partes.append("bônus do dia R$ 10")
        for marca, bonus in self.MARCAS_USO:
            if antes < marca <= usos[ferramenta]:
                premio = f"Estreia: {nome}" if marca == 1 else f"{marca} {nome}"
                if premio not in self.vida["premios"]:
                    self.vida["premios"].append(premio)
                ganho += bonus
                partes.append(f"prêmio \"{premio}\" + R$ {bonus}")
        self.vida["dinheiro"] += ganho
        self.ajustar(energia=-1, humor=2 + min(qtd, 5))
        self.mudar("comemorando", 2.5)
        self.salvar_config()
        return "  ·  ".join(partes)

    def linha_premio(self, pai, texto):
        tk.Label(pai, text=texto, bg=SURFACE, fg=OK, font=(self.fonte, 9, "bold"), wraplength=self.px(360),
                 justify="left").pack(anchor="w", pady=(self.px(8), self.px(8)))

    def receber_arquivos(self, arqs):
        """Arquivo arrastado para cima do robô: oferece o que dá para fazer com ele."""
        self.mexeu()
        ext = lambda a: Path(a).suffix.lower()
        imgs = [a for a in arqs if ext(a) in (".png", ".jpg", ".jpeg", ".jfif", ".webp", ".bmp", ".gif", ".tif",
                                              ".tiff", ".ico", ".heic", ".heif", ".avif")]
        pdfs = [a for a in arqs if ext(a) == ".pdf"]
        docs = [a for a in arqs if ext(a) in (".docx", ".xlsx", ".xlsm", ".csv", ".txt", ".md")]
        self.mudar("amor", 1.5)
        b, m = self.novo_balao("soltos")
        self.cabecalho(m, f"Recebi {len(arqs)} arquivo(s)")
        nomes = ", ".join(Path(a).name for a in arqs[:3]) + (f" e mais {len(arqs) - 3}" if len(arqs) > 3 else "")
        tk.Label(m, text=nomes, bg=SURFACE, fg=TX3, font=(self.fonte, 8), wraplength=self.px(400),
                 justify="left").pack(anchor="w")
        if imgs:
            self.linha_botoes(m, [("Remover fundo", lambda: self.tirar_fundo(imgs), True)], f"{len(imgs)} imagem(ns)")
            fmts = list(fn.FORMATOS_IMAGEM)
            self.linha_botoes(m, [(f, lambda f=f: self.converter(f, imgs)) for f in fmts[:4]])
            self.linha_botoes(m, [(f, lambda f=f: self.converter(f, imgs)) for f in fmts[4:]])
        if pdfs:
            itens = [("Juntar", lambda: self.rodar_pdf("juntar", pdfs), True)] if len(pdfs) > 1 else []
            itens += [("Separar", lambda: self.rodar_pdf("separar", pdfs)),
                      ("Extrair págs", lambda: self.rodar_pdf("extrair", pdfs)),
                      ("Girar 90°", lambda: self.rodar_pdf("girar", pdfs))]
            self.linha_botoes(m, itens, f"{len(pdfs)} PDF(s)")
            self.linha_botoes(m, [("Virar texto", lambda: self.rodar_pdf("texto", pdfs)),
                                  ("Virar PNG", lambda: self.converter("PNG", pdfs)),
                                  ("Virar JPG", lambda: self.converter("JPG", pdfs)),
                                  ("Analisar", lambda: self.analisar_documento(pdfs[:1]))])
        if docs:
            self.linha_botoes(m, [("Analisar", lambda: self.analisar_documento(docs[:1]), True)], "Documento")
        if not (imgs or pdfs or docs):
            tk.Label(m, text="Não sei mexer nesse tipo de arquivo ainda.", bg=SURFACE, fg=TX2,
                     font=(self.fonte, 9)).pack(anchor="w", pady=(self.px(6), 0))
        self.posicionar_balao(b)
        trazer_para_frente(b)

    JEITOS = [("calmo", "Calmo"), ("animado", "Animado"), ("carinhoso", "Carinhoso"), ("urgente", "Urgente")]
    REPETIR = [("nao", "Uma vez"), ("diario", "Todo dia"), ("uteis", "Dias úteis"), ("semanal", "Toda semana"),
               ("mensal", "Todo mês")]

    def escolha(self, pai, opcoes, var):
        """Fileira de opções (uma marcada) no padrão do painel."""
        linha = tk.Frame(pai, bg=SURFACE)
        linha.pack(anchor="w", pady=(0, self.px(4)))
        rotulos = {}

        def pintar():
            for k, w_ in rotulos.items():
                w_.configure(bg=ACCENT if var.get() == k else SURFACE2, fg="#ffffff" if var.get() == k else TX2)
        for k, nome in opcoes:
            w_ = tk.Label(linha, text=nome, font=(self.fonte, 9), padx=self.px(9), pady=self.px(4), cursor="hand2")
            w_.pack(side="left", padx=(0, self.px(4)))
            w_.bind("<Button-1>", lambda e, k=k: (var.set(k), pintar()))
            rotulos[k] = w_
        pintar()

    def abrir_lembrete(self):
        import datetime as dt
        self.mexeu()
        b, m = self.novo_balao("lembrete")
        self.cabecalho(m, "Lembretes")
        entrada = lambda larg: tk.Entry(m if larg > 20 else linha_dt, width=larg, bg=CONSOLE, fg=TX, insertbackground=TX,
                                        relief="flat", font=(self.fonte, 10), highlightthickness=1,
                                        highlightbackground=LINE2, highlightcolor=ACCENT)
        tk.Label(m, text="O que lembrar", bg=SURFACE, fg=TX3, font=(self.fonte, 8)).pack(anchor="w")
        texto = entrada(44)
        texto.pack(fill="x", ipady=self.px(4))
        tk.Label(m, text="Quando (dd/mm/aaaa ou hoje/amanhã · hora)", bg=SURFACE, fg=TX3,
                 font=(self.fonte, 8)).pack(anchor="w", pady=(self.px(8), 0))
        linha_dt = tk.Frame(m, bg=SURFACE)
        linha_dt.pack(anchor="w", fill="x")
        data, hora = entrada(12), entrada(6)
        data.pack(side="left", ipady=self.px(4))
        hora.pack(side="left", padx=(self.px(6), self.px(10)), ipady=self.px(4))
        daqui = dt.datetime.now() + dt.timedelta(minutes=15)
        data.insert(0, daqui.strftime("%d/%m/%Y"))
        hora.insert(0, daqui.strftime("%H:%M"))

        def atalho(minutos=None, dia=None, hh="09:00"):
            alvo = dt.datetime.now() + dt.timedelta(minutes=minutos) if minutos else None
            data.delete(0, "end")
            hora.delete(0, "end")
            if alvo:
                data.insert(0, alvo.strftime("%d/%m/%Y"))
                hora.insert(0, alvo.strftime("%H:%M"))
            else:
                data.insert(0, dia.strftime("%d/%m/%Y"))
                hora.insert(0, hh)
        hoje = dt.date.today()
        segunda = hoje + dt.timedelta(days=(7 - hoje.weekday()) or 7)
        for rot, cmd in (("15 min", lambda: atalho(15)), ("1 h", lambda: atalho(60)),
                         ("Amanhã 9h", lambda: atalho(dia=hoje + dt.timedelta(days=1))),
                         ("Segunda 9h", lambda: atalho(dia=segunda))):
            self.botao(linha_dt, rot, cmd).pack(side="left", padx=(0, self.px(4)))
        tk.Label(m, text="Repetir", bg=SURFACE, fg=TX3, font=(self.fonte, 8)).pack(anchor="w", pady=(self.px(8), 0))
        v_rep = tk.StringVar(value="nao")
        self.escolha(m, self.REPETIR, v_rep)
        tk.Label(m, text="Jeito do robô na hora (Urgente: pula, corre e não para até você responder)",
                 bg=SURFACE, fg=TX3, font=(self.fonte, 8)).pack(anchor="w", pady=(self.px(4), 0))
        v_jeito = tk.StringVar(value="animado")
        self.escolha(m, self.JEITOS, v_jeito)
        aviso = tk.Label(m, text="", bg=SURFACE, fg=BAD, font=(self.fonte, 8))
        aviso.pack(anchor="w")

        def salvar():
            msg = texto.get().strip()
            if not msg:
                aviso.configure(text="Escreva o que é para lembrar.")
                return
            try:
                quando = fn.ler_data_hora(data.get(), hora.get())
            except Exception:
                aviso.configure(text="Data ou hora não entendida. Ex.: 25/12/2026 e 09:30.")
                return
            if quando < time.time() - 60 and v_rep.get() == "nao":
                aviso.configure(text="Essa data já passou.")
                return
            self.lembretes.append({"id": uuid.uuid4().hex[:8], "texto": msg, "quando": quando,
                                   "repetir": v_rep.get(), "jeito": v_jeito.get()})
            self.gravar_lembretes()
            self.mudar("comemorando", 1.5)
            self.abrir_lembrete()
        self.botao(m, "Salvar lembrete", salvar, principal=True).pack(fill="x", pady=(self.px(4), self.px(8)))

        proximos = sorted(self.lembretes, key=lambda l: l["quando"])[:6]
        if proximos:
            tk.Frame(m, bg=LINE, height=1).pack(fill="x", pady=(0, self.px(6)))
        nomes_rep = dict(self.REPETIR)
        for l in proximos:
            item = tk.Frame(m, bg=SURFACE)
            item.pack(fill="x", pady=(0, self.px(2)))
            quando = time.strftime("%d/%m %H:%M", time.localtime(l["quando"]))
            extra = "" if l["repetir"] == "nao" else f" · {nomes_rep.get(l['repetir'], '')}"
            cor = BAD if l["jeito"] == "urgente" else TX2
            tk.Label(item, text=f"{quando}{extra}", bg=SURFACE, fg=TX3, font=(self.fonte, 8), width=20,
                     anchor="w").pack(side="left")
            tk.Label(item, text=l["texto"][:40], bg=SURFACE, fg=cor, font=(self.fonte, 9), anchor="w").pack(side="left")
            x = tk.Label(item, text="×", bg=SURFACE, fg=TX3, font=(self.fonte, 12), cursor="hand2")
            x.pack(side="right")
            x.bind("<Button-1>", lambda e, i=l["id"]: (self.apagar_lembrete(i), self.abrir_lembrete()))
        self.posicionar_balao(b)
        trazer_para_frente(b)
        texto.focus_set()

    def gravar_lembretes(self):
        try:
            fn.salvar_lembretes(self.lembretes)
        except Exception:
            registrar_erro(traceback.format_exc())

    def apagar_lembrete(self, ident):
        self.lembretes = [l for l in self.lembretes if l["id"] != ident]
        self.gravar_lembretes()

    def conferir_lembretes(self):
        if self.alerta or time.time() < self.prox_conferir:
            return
        self.prox_conferir = time.time() + 2
        vencidos = [l for l in self.lembretes if l["quando"] <= time.time()]
        if vencidos:
            self.disparar(min(vencidos, key=lambda l: l["quando"]))

    def disparar(self, l):
        self.alerta = l
        self.ultima_interacao = time.time()
        jeito = l["jeito"]
        if jeito == "urgente":
            self.estado, self.doido_x = "doido", self.x
        else:
            self.mudar({"animado": "comemorando", "carinhoso": "amor"}.get(jeito, "parado"), 4)
        if jeito != "calmo":
            self.root.bell()
        b, m = self.novo_balao("alerta")
        titulo = {"urgente": "URGENTE!", "carinhoso": "Lembrete com carinho", "animado": "Ei! Lembrete!"}.get(jeito, "Lembrete")
        self.cabecalho(m, titulo, "AGORA" if jeito == "urgente" else time.strftime("%H:%M"),
                       BAD if jeito == "urgente" else None)
        tk.Label(m, text=l["texto"], bg=SURFACE, fg=TX, font=(self.fonte, 12 if jeito == "urgente" else 11, "bold"),
                 wraplength=self.px(340), justify="left").pack(anchor="w", pady=(0, self.px(10)))
        self.linha_botoes(m, [("Feito", lambda: self.responder_alerta(None), True),
                              ("Mais 10 min", lambda: self.responder_alerta(10)),
                              ("Mais 1 h", lambda: self.responder_alerta(60)),
                              ("Amanhã", lambda: self.responder_alerta(24 * 60))])
        b.protocol("WM_DELETE_WINDOW", lambda: None)
        self.posicionar_balao(b)
        trazer_para_frente(b)
        if jeito == "urgente":
            self.insistir(b)

    def insistir(self, b):
        """Urgente: apita e volta o balão para a frente até a pessoa responder."""
        if self.alerta is None or self.balao is not b:
            return
        self.root.bell()
        trazer_para_frente(b)
        self.root.after(8000, lambda: self.insistir(b))

    def responder_alerta(self, adiar_min):
        l, self.alerta = self.alerta, None
        if l is None:
            return
        if adiar_min:
            l["quando"] = time.time() + adiar_min * 60
        else:
            prox = fn.proxima_vez(l["quando"], l["repetir"])
            if prox:
                l["quando"] = prox
            else:
                self.lembretes = [x for x in self.lembretes if x["id"] != l["id"]]
        self.gravar_lembretes()
        self.fechar_balao()
        self.ajustar(humor=3)
        self.mudar("comemorando", 1.5)

    # ---------- jogos ----------

    def jogar(self, tipo, auto=False):
        self.fechar_balao()
        if self.jogo_ativo:
            self.jogo_ativo.fim()
        cores = dict(area=area_de_trabalho, TRANSP=TRANSP, SURFACE=SURFACE, LINE2=LINE2, TX=TX, TX2=TX2, TX3=TX3,
                     BG=BG, CLARO=CLARO, ACCENT=ACCENT, ACCENT_ESC=ACCENT_ESC, OK=OK, WARN=WARN, BAD=BAD)
        try:
            classe = {("moto", False): jogos.Moto, ("nave", False): jogos.Nave,
                      ("moto", True): jogos.PasseioMoto, ("nave", True): jogos.PasseioNave}[(tipo, auto)]
            self.jogo_ativo = classe(self, cores, auto)
        except Exception:
            registrar_erro(traceback.format_exc())
            self.root.deiconify()
            self.aviso("Não deu certo", "O jogo não abriu. Detalhes no erro.log.", erro=True)

    def fim_de_jogo(self, nome, pontos, premio, auto=False):
        self.jogo_ativo = None
        self.vida["dinheiro"] += premio
        self.mexeu()
        if auto:
            self.mudar("comemorando", 3)
            self.salvar_config()
            self.aviso(f"Voltei do passeio · {nome}", f"Descansei! Energia {self.vida['energia']:.0f}%, "
                       f"humor {self.vida['humor']:.0f}%. Bora trabalhar!")
            return
        self.ajustar(humor=min(25, 5 + pontos), energia=-5)
        self.mudar("comemorando" if pontos else "triste", 3)
        self.salvar_config()
        self.aviso(f"Fim do jogo · {nome}", f"Fiz {pontos} ponto(s) e ganhei R$ {premio}. Bora de novo?")

    def abrir_imagens(self):
        self.mexeu()
        b, m = self.novo_balao("imagens")
        self.cabecalho(m, "Converter imagens")
        tk.Label(m, text="Escolha o formato de saída e depois as imagens (várias de uma vez).\n"
                         "Entra: PNG, JPG, WEBP, BMP, GIF, TIFF, ICO, HEIC, AVIF e PDF (uma imagem por página).\n"
                         "O original nunca é alterado.",
                 bg=SURFACE, fg=TX3, font=(self.fonte, 8), justify="left").pack(anchor="w")
        self.linha_botoes(m, [("Remover fundo (sem perder qualidade)", self.tirar_fundo, True)])
        formatos = list(fn.FORMATOS_IMAGEM)
        self.linha_botoes(m, [(f, lambda f=f: self.converter(f), f == "PNG") for f in formatos[:4]], "Converter para")
        self.linha_botoes(m, [(f, lambda f=f: self.converter(f)) for f in formatos[4:]])
        self.posicionar_balao(b)
        trazer_para_frente(b)

    def converter(self, formato, soltos=None):
        self.fechar_balao()
        arqs = soltos or self.escolher(True, f"Imagens para converter em {formato}",
                             (("Imagens", fn.ENTRADA_IMAGEM),))
        if not arqs:
            return
        saidas, falhas = fn.converter_imagens(arqs, formato)
        if not saidas:
            self.mudar("confuso", 3)
            self.aviso("Não deu certo", "\n".join(falhas) or "Nenhuma imagem convertida.", erro=True)
            return
        premio = self.recompensar("pdf" if all(Path(a).suffix.lower() == ".pdf" for a in arqs) else "imagem",
                                  len(saidas))
        b, m = self.novo_balao("aviso")
        self.cabecalho(m, f"Convertido para {formato}", "VERIFICAR" if falhas else "OK", BAD if falhas else OK)
        texto = f"{len(saidas)} arquivo(s) novo(s) ao lado do original."
        if falhas:
            texto += "\n\nNão converti:\n" + "\n".join(falhas[:5])
        tk.Label(m, text=texto, bg=SURFACE, fg=TX2, font=(self.fonte, 9), justify="left",
                 wraplength=self.px(360)).pack(anchor="w")
        self.linha_premio(m, premio)
        pasta = Path(saidas[0]).parent
        self.linha_botoes(m, [("Abrir pasta", lambda: os.startfile(str(pasta)), True), ("Fechar", self.fechar_balao)])
        self.posicionar_balao(b)
        trazer_para_frente(b)

    def tirar_fundo(self, soltos=None):
        self.fechar_balao()
        arqs = soltos or self.escolher(True, "Imagens para tirar o fundo", (("Imagens", "*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff"),))
        if not arqs:
            return
        self.mudar("pensando")
        self.root.update()
        saidas, falhas, metodo = [], [], ""
        for a in arqs:
            try:
                alvo, metodo = fn.remover_fundo(a)
                saidas.append(alvo)
            except Exception as e:
                registrar_erro(traceback.format_exc())
                falhas.append(f"{Path(a).name}: {str(e)[:80]}")
        if not saidas:
            self.mudar("confuso", 3)
            self.aviso("Não deu certo", "\n".join(falhas), erro=True)
            return
        premio = self.recompensar("fundo", len(saidas))
        texto = (f"{len(saidas)} PNG(s) sem fundo, mesmo tamanho e mesmos pixels do original.\nMétodo: {metodo}.")
        if metodo != "IA (rembg)":
            texto += "\n\nPara fotos (pessoas, objetos) peça para instalar o rembg: pip install \"rembg[cpu]\"."
        if falhas:
            texto += "\n\nNão consegui:\n" + "\n".join(falhas[:5])
        b, m = self.novo_balao("aviso")
        self.cabecalho(m, "Fundo removido", "VERIFICAR" if falhas else "OK", BAD if falhas else OK)
        tk.Label(m, text=texto, bg=SURFACE, fg=TX2, font=(self.fonte, 9), justify="left",
                 wraplength=self.px(360)).pack(anchor="w")
        self.linha_premio(m, premio)
        pasta = Path(saidas[0]).parent
        self.linha_botoes(m, [("Abrir pasta", lambda: os.startfile(str(pasta)), True), ("Fechar", self.fechar_balao)])
        self.posicionar_balao(b)
        trazer_para_frente(b)

    def abrir_corretor(self):
        self.mexeu()
        b, m = self.novo_balao("corretor")
        self.cabecalho(m, "Corretor ortográfico", "PT-BR")
        caixa = tk.Text(m, width=52, height=7, wrap="word", bg=CONSOLE, fg=TX, insertbackground=TX, relief="flat",
                        font=(self.fonte, 10), padx=self.px(9), pady=self.px(7),
                        highlightthickness=1, highlightbackground=LINE2, highlightcolor=ACCENT)
        caixa.pack(fill="x")
        info = tk.Label(m, text="Cole o texto e clique em Corrigir. Texto com CPF não sai do computador."
                                "", bg=SURFACE, fg=TX3, font=(self.fonte, 8),
                        wraplength=self.px(420), justify="left")
        info.pack(anchor="w", pady=(self.px(6), 0))

        def corrigir():
            texto = caixa.get("1.0", "end").strip()
            if not texto:
                return
            if fn.tem_dado_pessoal(texto):
                self.enviar("Corrija a ortografia e a gramática deste texto (português do Brasil) sem mudar o "
                            "sentido. Devolva só o texto corrigido e, embaixo, a lista do que mudou.\n\n" + texto, False)
                return
            try:
                corrigido, trocas = fn.corrigir_ortografia(texto)
            except Exception:
                self.enviar("Corrija a ortografia e a gramática deste texto (português do Brasil) sem mudar o "
                            "sentido. Devolva só o texto corrigido e, embaixo, a lista do que mudou.\n\n" + texto, False)
                return
            self.ajustar(humor=2)
            self.mudar("comemorando", 2)
            self.ultima_pergunta = ""
            lista = "\n".join("· " + t for t in trocas) if trocas else "Nenhum erro encontrado."
            self.mostrar_resposta(f"{corrigido}\n\n— {len(trocas)} correção(ões) —\n{lista}", titulo="Texto corrigido")
        self.linha_botoes(m, [("Corrigir", corrigir, True), ("Limpar", lambda: caixa.delete("1.0", "end"))])
        self.posicionar_balao(b)
        trazer_para_frente(b)
        caixa.focus_set()

    def analisar_documento(self, soltos=None):
        self.mexeu()
        self.fechar_balao()
        arqs = soltos or self.escolher(titulo="Escolha o documento para analisar",
                             tipos=(("Documentos", "*.pdf *.docx *.xlsx *.xlsm *.csv *.txt *.md"),))
        if not arqs:
            return
        caminho = Path(arqs[0])
        try:
            texto = fn.ler_documento(caminho)
        except Exception as e:
            registrar_erro(traceback.format_exc())
            self.mudar("confuso", 3)
            self.aviso("Não consegui ler", str(e), erro=True)
            return
        resumo, tem_cpf = fn.analisar_texto(texto)
        self.ajustar(energia=-1, humor=2)
        self.mudar("comemorando" if "VERIFICAR" not in resumo else "confuso", 2.5)
        b, m = self.novo_balao("analise")
        self.cabecalho(m, f"Análise · {caminho.name[:40]}", "VERIFICAR" if "VERIFICAR" in resumo else "OK",
                       BAD if "VERIFICAR" in resumo else OK)
        tk.Label(m, text=resumo, bg=CONSOLE, fg=TX, font=(self.fonte, 9), justify="left", anchor="w",
                 padx=self.px(10), pady=self.px(8), wraplength=self.px(400)).pack(fill="x")
        if tem_cpf:
            tk.Label(m, text="Tem CPF: a análise acima é feita só no computador; o resumo com IA grátis fica bloqueado.",
                     bg=SURFACE, fg=WARN, font=(self.fonte, 8), wraplength=self.px(400), justify="left"
                     ).pack(anchor="w", pady=(self.px(6), 0))

        def resumir():
            pedido = ("Analise este documento para o RH/DP: diga o que é, resuma os pontos principais e "
                      "aponte erros, inconsistências ou o que precisa ser conferido.\n\n"
                      f"Arquivo: {caminho.name}\n\n{texto[:12000]}")
            self.enviar(pedido, False)
        self.linha_botoes(m, [("Resumir com IA", resumir, True), ("Fechar", self.fechar_balao)])
        self.posicionar_balao(b)
        trazer_para_frente(b)

    def auditoria(self):
        self.mexeu()
        self.fechar_balao()
        partes = []
        if not (self.claude_exe or achar_claude()):
            partes.append("VERIFICAR  Claude Code não encontrado neste computador.")
        motores = [n for n, _, _ in fn.ordem_motores() if n != "claude"]
        partes.append(f"IAs grátis com chave: {', '.join(motores) or 'nenhuma (só Claude Code)'}")
        if LOG.is_file():
            fim = LOG.read_text(encoding="utf-8", errors="replace").strip().splitlines()[-6:]
            partes.append("VERIFICAR  Últimas linhas do erro.log do robô:\n    " + "\n    ".join(fim))
        else:
            partes.append("OK  Robô sem erros registrados")
        try:
            partes.append(fn.auditar_cofre(COFRE))
        except Exception as e:
            partes.append(f"Não consegui auditar o cofre: {e}")
        texto = "\n\n".join(partes)
        self.ajustar(energia=-2)
        self.mudar("confuso" if "VERIFICAR" in texto else "comemorando", 2.5)
        self.ultima_pergunta = ""
        self.mostrar_resposta(texto, titulo="Auditoria de erros")

    def abrir_chaves(self):
        try:
            os.startfile(str(fn.criar_arquivo_chaves()))
        except Exception as e:
            self.aviso("Não consegui", str(e), erro=True)
            return
        self.aviso("Chaves das IAs grátis", "Abri o chaves.json (fica no seu perfil do Windows, fora do Dropbox).\n\n"
                   "Cole a chave grátis entre as aspas, salve e pergunte de novo. Sem chave, uso o Claude Code.")

    def rodar(self):
        self.root.mainloop()


# ----------------------------------------------------------------------------
# Modo de teste: passa por todas as animações e salva prints (precisa do Pillow)
# ----------------------------------------------------------------------------

class Demo:
    ROTEIRO = [("andando", 3.0), ("operando", 7.0), ("parado", 1.6), ("sentado", 1.6), ("dormindo", 2.4),
               ("pensando", 2.4), ("comemorando", 2.4), ("confuso", 2.4), ("arrastando", 1.6),
               ("testemunho", 2.4), ("consertando", 2.4), ("amor", 2.0), ("triste", 2.0), ("bocejando", 2.0),
               ("recarregando", 2.0), ("lubrificando", 2.0), ("escalando", 2.0), ("quebrada", 2.4),
               ("chuva", 2.4), ("petroleo", 2.4), ("agua", 2.4)]

    def __init__(self, robo, pasta):
        from PIL import ImageGrab
        self.grab = ImageGrab.grab
        self.robo, self.pasta = robo, pasta
        self.pasta.mkdir(parents=True, exist_ok=True)
        self.i, self.inicio, self.quadros = -1, 0, []
        robo.modo = "parado"
        robo.x = float(area_de_trabalho()[2] - robo.px(robo.W) - 300)

    def passo(self):
        r, agora = self.robo, time.time()
        if self.i < 0 or agora - self.inicio > self.ROTEIRO[self.i][1]:
            self.i += 1
            if self.i >= len(self.ROTEIRO):
                if self.quadros:
                    self.quadros[0].save(self.pasta / "robozinho_animacoes.gif", save_all=True,
                                         append_images=self.quadros[1:], duration=100, loop=0)
                return True
            self.inicio = agora
        nome = self.ROTEIRO[self.i][0]
        r.vida["quebrada"] = nome == "quebrada"
        r.vida["suja"] = nome == "petroleo"
        r.chuva_ate = agora + 60 if nome == "chuva" else 0.0
        r.jorro_ate = agora + 60 if nome in ("petroleo", "agua") else 0.0
        r.jorro_cor = CONSOLE if nome == "petroleo" else ACCENT
        r.ultimo_testemunho = ("Diamante", ACCENT, 100, [])
        r.estado = "operando" if nome in ("quebrada", "chuva", "petroleo", "agua") else nome
        r.ate = agora + 10
        r.ultima_interacao = agora
        r.com_sonda = nome in ("operando", "dormindo", "pensando", "testemunho", "consertando", "quebrada",
                                 "chuva", "petroleo", "agua")
        if nome == "andando":
            r.dir = -1
            r.lado = -1
            r.x -= 2 * r.S
        elif nome == "operando":
            r.lado = 1
        elif nome == "arrastando":
            r.lado = 0
            r.y = r.chao() - r.px(60)
        else:
            r.lado = 0
        if r.t % 2 == 0:
            r.root.update_idletasks()
            x, y = int(r.x), int(r.y)
            img = self.grab(bbox=(x - 10, y - 10, x + r.px(r.W) + 10, y + r.px(r.H) + 10))
            self.quadros.append(img.convert("P", palette=1, colors=128))
            meio = agora - self.inicio > self.ROTEIRO[self.i][1] / 2
            arq = self.pasta / f"{self.i + 1:02d}_{nome}.png"
            if meio and not arq.exists():
                img.save(arq)


def principal():
    args = sys.argv[1:]
    if "--criar-atalho" in args:
        desenhar_icone()
        area = Path(os.environ["USERPROFILE"]) / "Desktop"
        try:
            buf = ctypes.create_unicode_buffer(260)
            ctypes.windll.shell32.SHGetFolderPathW(None, 0x0010, None, 0, buf)  # CSIDL_DESKTOPDIRECTORY
            if buf.value:
                area = Path(buf.value)
        except Exception:
            pass
        ok = criar_lnk(area / f"{NOME}.lnk")
        print(("Atalho criado em " if ok else "Falhou ao criar o atalho em ") + str(area))
        return
    ligar_dpi()
    if ja_aberto() and "--demo" not in args:
        user32.MessageBoxW(0, "O Robozinho já está aberto na sua tela.", NOME, 0x40)
        return
    demo = args[args.index("--demo") + 1] if "--demo" in args else None
    Robozinho(demo).rodar()


if __name__ == "__main__":
    try:
        principal()
    except Exception:
        registrar_erro(traceback.format_exc())
        user32.MessageBoxW(0, "O Robozinho encontrou um erro e precisou fechar.\n\nDetalhes em erro.log, na pasta do robô.",
                           NOME, 0x10)
