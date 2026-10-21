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

PASTA = Path(__file__).resolve().parent          # ...\Claude outputs\Robozinho DrillGeo
COFRE = PASTA.parents[1]                         # ...\Segundo cerebro
CONFIG = PASTA / "config.json"
LOG = PASTA / "erro.log"
NOME = "Robozinho DrillGeo"

LIMITE_SEG = 180          # tempo máximo de espera pelo Claude
SONO_SEG = 180            # parado sem ninguém mexer -> dorme
SONO_ANDANDO_SEG = 600    # andando sem ninguém mexer -> cansa e dorme
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

    def __init__(self, fila, exe, texto, fazer, sessao, continuar):
        super().__init__(daemon=True)
        self.fila, self.exe, self.texto = fila, exe, texto
        self.fazer, self.sessao, self.continuar = fazer, sessao, continuar
        self.proc = None
        self.cancelado = False

    def run(self):
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
        self.cfg.update(modo=self.modo, atalho=self.var_atalho.get())
        try:
            CONFIG.write_text(json.dumps(self.cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            registrar_erro(traceback.format_exc())

    def mexeu(self):
        self.ultima_interacao = time.time()
        if self.estado in ("dormindo", "sentado"):
            self.estado = "parado"
            self.prox_decisao = time.time() + 2

    def mudar(self, estado, segundos=0.0):
        self.estado = estado
        self.ate = time.time() + segundos

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
            if self.estado == "operando":
                self.com_sonda = True
            elif self.estado in ("andando", "arrastando", "caindo"):
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
        if self.estado in ("comemorando", "confuso"):
            if agora < self.ate:
                return
            self.mudar("parado")
            self.prox_decisao = agora + 3
        if self.estado == "pensando":
            self.mudar("parado")

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
                elif sorteio < 0.92:
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
                self.x += self.dir * 2.0 * self.S
                limite_dir = R - self.px(self.CX + 45)   # andando, só o robô precisa caber na tela
                if self.x <= L + 4 and self.dir < 0 or self.x >= limite_dir and self.dir > 0:
                    self.x = max(L + 4, min(self.x, limite_dir))
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
            self.desenhar_sonda(base, st == "operando", w)

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
        sentado = st in ("sentado", "dormindo")
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
            if st == "andando":
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
        c.create_oval(cx - 3 + f * 4, top_corpo + 27, cx + 3 + f * 4, top_corpo + 33, fill=luz, outline="")

        # braços
        ombro_y = top_corpo + 9
        for lado_b in (-1, 1):
            ox = cx + lado_b * 23
            if st == "comemorando":
                mao = (cx + lado_b * 38, ombro_y - 30 + math.sin(t * 0.6 + lado_b) * 5)
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

        c.scale("all", 0, 0, S, S)

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

    def rosto(self, cx, ey, st, w):
        c = self.cv
        olhos = (cx - 11, cx + 11)
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
            self.abrir_pergunta()

    # ---------- menu ----------

    def montar_menu(self):
        m = tk.Menu(self.root, tearoff=0, bg=SURFACE, fg=TX, activebackground=ATIVO, activeforeground=TX,
                    font=(self.fonte, 10), bd=0, relief="flat")
        m.add_command(label="Perguntar ao Claude", command=self.abrir_pergunta)
        m.add_command(label="Nova conversa", command=self.nova_conversa)
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

    def dormir(self):
        self.alvo_x = None
        self.lado = 0
        self.estado = "dormindo"
        self.ultima_interacao = time.time() - SONO_ANDANDO_SEG - 60  # continua dormindo até alguém mexer

    def nova_conversa(self):
        self.mexeu()
        self.sessao = None
        self.sessao_iniciada = False
        self.var_continuar.set(False)
        self.aviso("Conversa nova", "Pronto. A próxima pergunta começa do zero: o Claude não lembra do que foi falado antes.")

    def fechar(self):
        if self.pedido:
            self.pedido.cancelar()
        if self.atalho:
            self.atalho.parar()
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
            if tipo == "atalho":
                self.mexeu()
                if self.pedido:
                    self.mostrar_pensando()
                else:
                    self.abrir_pergunta()
            elif tipo == "atalho_status":
                self.atalho_ok = dado
                if not dado:
                    self.var_atalho.set(False)
            elif origem is self.pedido:
                self.pedido = None
                self.mexeu()
                if tipo == "resposta":
                    self.sessao_iniciada = True
                    self.mudar("comemorando", 2.8)
                    self.mostrar_resposta(dado)
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
        if not self.claude_exe:
            self.mudar("confuso", 4.5)
            self.aviso_sem_claude()
            return
        fazer = texto.lower().startswith("!fazer")
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
        if not (continuar and self.sessao and self.sessao_iniciada):
            self.sessao = str(uuid.uuid4())
            self.sessao_iniciada = False
            continuar = False
        self.ultima_pergunta = texto
        self.ultimo_fazer = fazer
        self.inicio_pedido = time.time()
        self.pedido = Pedido(self.fila, self.claude_exe, texto, fazer, self.sessao, continuar)
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
                      padx=self.px(11), pady=self.px(5), cursor="hand2",
                      highlightthickness=0 if principal else 1, highlightbackground=LINE2)
        bt.bind("<Button-1>", lambda e: comando())
        bt.bind("<Enter>", lambda e: bt.configure(bg=cor_h))
        bt.bind("<Leave>", lambda e: bt.configure(bg=cor))
        return bt

    def abrir_pergunta(self, continuar=None):
        self.mexeu()
        b, m = self.novo_balao("pergunta")
        tem_conversa = bool(self.sessao and self.sessao_iniciada)
        self.cabecalho(m, "Pergunte ao Claude", "SÓ LEITURA")
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

    def mostrar_resposta(self, texto, erro=False):
        b, m = self.novo_balao("resposta")
        hora = time.strftime("%H:%M")
        if erro:
            self.cabecalho(m, "Não deu certo", "VERIFICAR", BAD)
        else:
            self.cabecalho(m, f"Resposta do Claude · {hora}",
                           "!FAZER" if self.ultimo_fazer else "SÓ LEITURA", WARN if self.ultimo_fazer else None)
        if self.ultima_pergunta and not erro:
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
        caixa.insert("1.0", texto)
        caixa.configure(state="disabled")
        caixa.bind("<MouseWheel>", lambda e: caixa.yview_scroll(int(-e.delta / 120) * 2, "units"))

        rodape = tk.Frame(m, bg=SURFACE)
        rodape.pack(fill="x", pady=(self.px(10), 0))
        copiar = None

        def fazer_copia():
            self.root.clipboard_clear()
            self.root.clipboard_append(texto)
            self.root.update()
            copiar.configure(text="Copiado")
            b.after(1500, lambda: copiar.winfo_exists() and copiar.configure(text="Copiar"))
        copiar = self.botao(rodape, "Copiar", fazer_copia)
        copiar.pack(side="left")
        self.botao(rodape, "Abrir no Claude", self.abrir_claude_desktop).pack(side="left", padx=(self.px(6), 0))
        self.botao(rodape, "Fechar", self.fechar_balao).pack(side="right")
        if not erro:
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

    def rodar(self):
        self.root.mainloop()


# ----------------------------------------------------------------------------
# Modo de teste: passa por todas as animações e salva prints (precisa do Pillow)
# ----------------------------------------------------------------------------

class Demo:
    ROTEIRO = [("andando", 3.0), ("operando", 7.0), ("parado", 1.6), ("sentado", 1.6), ("dormindo", 2.4),
               ("pensando", 2.4), ("comemorando", 2.4), ("confuso", 2.4), ("arrastando", 1.6)]

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
        r.estado = nome
        r.ate = agora + 10
        r.ultima_interacao = agora
        r.com_sonda = nome in ("operando", "dormindo", "pensando")
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
