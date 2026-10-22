# -*- coding: utf-8 -*-
"""Joguinhos do Robozinho na tela inteira, por cima de tudo, com fundo transparente.

- Moto: igual ao jogo do dinossauro do navegador. Corre no chão; Espaço pula (segure para ir mais alto),
  seta para baixo abaixa. Pedras, caixas de testemunho, sondinhas e drones.
- Nave: estilo Flappy Bird. Espaço dá impulso, a gravidade puxa; passe pelos vãos entre os mastros de sonda
  e desvie dos monstrinhos.
Esc sai. O que ganhar vira dinheiro do robô.

Passeios (PasseioMoto, PasseioNave): ele anda ou voa livre pela tela, sem obstáculos, para descansar do
trabalho, sem pegar o teclado. Dá para continuar trabalhando: o fundo é transparente e o clique passa para as janelas de trás.
Clicar nele (ou Ctrl+Alt+Espaço) encerra; sozinho, volta depois de alguns minutos.
"""

import math
import random
import time
import tkinter as tk


class Jogo:
    QUADRO = 16          # ~60 quadros por segundo
    PASSEIO_MIN = 5      # duração do passeio sozinho
    NOME = ROTULO = DICA = ""

    def __init__(self, robo, cores, auto=False):
        self.r, self.c, self.auto = robo, cores, auto
        self.S = robo.S
        L, T, R, B = cores["area"]()
        self.W, self.H = R - L, B - T
        self.top = tk.Toplevel(robo.root)
        self.top.overrideredirect(True)
        self.top.attributes("-topmost", True)
        self.top.attributes("-transparentcolor", cores["TRANSP"])
        self.top.geometry(f"{self.W}x{self.H}+{L}+{T}")
        self.cv = tk.Canvas(self.top, width=self.W, height=self.H, bg=cores["TRANSP"], highlightthickness=0)
        self.cv.pack()
        self.teclas = set()
        self.top.bind("<KeyPress>", lambda e: self.teclas.add(e.keysym.lower()))
        self.top.bind("<KeyRelease>", lambda e: self.teclas.discard(e.keysym.lower()))
        self.top.bind("<Escape>", lambda e: self.fim())
        # passeio: clicar nele encerra · jogo: clicar dá impulso (e devolve o teclado ao jogo)
        self.cv.bind("<Button-1>", self.ao_clicar)
        self.vidas, self.pontos, self.t, self.invul, self.vivo = 3, 0, 0, 0, True
        self.inicio = time.time()
        robo.root.withdraw()
        if not auto:
            self.top.after(50, self.top.focus_force)
        self.top.after(self.QUADRO, self.laco)

    def px(self, v):
        return v * self.S

    def tecla(self, *nomes):
        return any(n in self.teclas for n in nomes)

    def ao_clicar(self, e):
        if self.auto:
            self.fim()
        else:
            self.top.focus_force()
            self.clique = True

    def laco(self):
        if not self.vivo:
            return
        agora = time.time()
        # física em passos fixos de 1/60 s: o desenho da tela inteira é lento, mas o jogo anda no ritmo certo
        self.acum = min(0.1, getattr(self, "acum", 0.0) + agora - getattr(self, "ultimo", agora - 1 / 60))
        self.ultimo = agora
        if self.auto:
            h = (agora - getattr(self, "ultimo_desc", agora)) / 3600   # passear descansa: energia e humor
            self.ultimo_desc = agora
            self.r.ajustar(energia=120 * h, humor=90 * h)
            if agora - self.inicio > self.PASSEIO_MIN * 60:
                self.fim()
                return
        while self.acum >= 1 / 60 and self.vivo:
            self.acum -= 1 / 60
            self.t += 1
            self.invul = max(0, self.invul - 1)
            self.passo()
        self.cv.delete("all")
        self.desenhar()
        self.hud()
        if self.vidas <= 0:
            self.fim()
            return
        self.top.after(self.QUADRO, self.laco)

    def hud(self):
        c, S = self.c, self.S
        if self.auto:   # passeio: só um aviso discreto no começo, para não atrapalhar o trabalho
            if self.t < 300:
                texto = f"{self.NOME}: passeio para descansar · clique nele para voltar"
                self.caixa(texto, self.topo - self.px(22), c["TX2"])
            return
        coracoes = "♥ " * self.vidas
        self.caixa(f"{self.NOME}   ·   {self.ROTULO} {self.pontos}   ·   vidas {coracoes}  ·   Esc sai",
                   getattr(self, "hud_y", self.px(26)), c["TX"])
        if self.t < 240:
            self.cv.create_text(self.W / 2, getattr(self, "hud_y", self.px(26)) + self.px(32), text=self.DICA, fill=c["TX2"], font=(self.r.fonte, -int(12 * S)))

    def caixa(self, texto, y, cor):
        c, x = self.c, self.W / 2
        larg = self.px(7.8) * len(texto)
        self.cv.create_rectangle(x - larg / 2, y - self.px(14), x + larg / 2, y + self.px(14),
                                 fill=c["SURFACE"], outline=c["LINE2"])
        self.cv.create_text(x, y, text=texto, fill=cor, font=(self.r.fonte, -int(12 * self.S)))

    def fim(self):
        if not self.vivo:
            return
        self.vivo = False
        self.top.destroy()
        self.r.root.deiconify()
        self.r.fim_de_jogo(self.NOME, self.pontos, self.premio() // (2 if self.auto else 1), self.auto)

    def premio(self):
        return self.pontos * 3


class Flappy(Jogo):
    ROTULO = "vãos"
    DICA = "Espaço ou clique: impulso  ·  passe pelos vãos entre as sondas"
    MONSTROS = False

    def __init__(self, robo, cores, auto=False):
        super().__init__(robo, cores, auto)
        px = self.px
        self.topo = px(80)
        self.chao = self.H - px(6)
        self.x, self.y, self.vy = self.W * 0.25, (self.topo + self.chao) / 2, 0.0
        self.vel = px(3.6)
        self.canos, self.monstros = [], []
        self.prox_cano = self.W * 0.6
        self.clique = False
        self.segurando = False
        self.impulso_t = -99

    # ---------- regras ----------

    def impulso(self):
        self.vy = -self.px(7.6)
        self.impulso_t = self.t

    def novo_cano(self):
        px = self.px
        vao = px(190) - min(px(40), self.pontos * px(1.5))   # fica mais justo aos poucos
        margem = px(40) + vao / 2
        meio = random.uniform(self.topo + margem, self.chao - margem)
        cano = {"x": self.W + px(40), "meio": meio, "vao": vao, "contou": False}
        self.canos.append(cano)
        if self.MONSTROS and random.random() < 0.45:   # monstrinho flutuando dentro do vão
            self.monstros.append({"cano": cano, "fase": random.uniform(0, 6), "r": px(13),
                                  "cor": random.choice(("OK", "BAD"))})

    def pos_monstro(self, m):
        c = m["cano"]
        return c["x"], c["meio"] + math.sin(self.t * 0.05 + m["fase"]) * c["vao"] * 0.22

    def passo(self):
        px = self.px
        aperta = self.tecla("space", "up", "w") or self.clique
        if aperta and not self.segurando:
            self.impulso()
        self.segurando = self.tecla("space", "up", "w")
        self.clique = False
        self.vy = min(px(9), self.vy + px(0.42))
        self.y += self.vy
        self.vel = px(3.6) + min(px(2.4), self.pontos * px(0.06))
        for c in self.canos:
            c["x"] -= self.vel
            if not c["contou"] and c["x"] < self.x:
                c["contou"] = True
                self.pontos += 1
        self.canos = [c for c in self.canos if c["x"] > -px(60)]
        self.monstros = [m for m in self.monstros if m["cano"] in self.canos]
        self.prox_cano -= self.vel
        if self.prox_cano <= 0:
            self.novo_cano()
            self.prox_cano = px(330)
        r = px(13)
        bateu = self.y - r < self.topo or self.y + r > self.chao
        for c in self.canos:
            if abs(c["x"] - self.x) < px(30) + r and abs(self.y - c["meio"]) > c["vao"] / 2 - r:
                bateu = True
        for m in self.monstros:
            mx, my = self.pos_monstro(m)
            if math.hypot(mx - self.x, my - self.y) < m["r"] + r:
                bateu = True
        if bateu:
            self.y = min(max(self.y, self.topo + r), self.chao - r)
            if self.invul:
                return
            self.vidas -= 1
            self.invul = 90
            self.top.bell()
            alvo = next((c for c in self.canos if c["x"] > self.x - px(40)), None)
            self.y, self.vy = (alvo["meio"] if alvo else (self.topo + self.chao) / 2), 0.0   # volta no vão

    # ---------- desenho ----------

    def mastro(self, x, y1, y2, ponta_em_baixo):
        """Mastro de sonda (o 'cano' do Flappy): treliça âmbar com a boca virada para o vão."""
        c, cv, px = self.c, self.cv, self.px
        if y2 - y1 < 2:
            return
        cv.create_rectangle(x - px(24), y1, x + px(24), y2, fill=c["WARN"], outline=c["SURFACE"], width=2)
        passo = px(22)
        k = y1
        while k < y2 - 2:   # treliça em X
            fim_k = min(y2, k + passo)
            cv.create_line(x - px(24), k, x + px(24), fim_k, fill=c["SURFACE"], width=1)
            cv.create_line(x + px(24), k, x - px(24), fim_k, fill=c["SURFACE"], width=1)
            k += passo
        boca = y2 - px(16) if ponta_em_baixo else y1
        cv.create_rectangle(x - px(30), boca, x + px(30), boca + px(16), fill=c["WARN"], outline=c["SURFACE"], width=2)
        cv.create_line(x - px(30), boca + px(8), x + px(30), boca + px(8), fill=c["SURFACE"], width=1)

    def desenhar(self):
        c, cv, px = self.c, self.cv, self.px
        for cano in self.canos:
            x, meio, vao = cano["x"], cano["meio"], cano["vao"]
            self.mastro(x, self.topo, meio - vao / 2, True)
            self.mastro(x, meio + vao / 2, self.chao, False)
        for m in self.monstros:
            mx, my = self.pos_monstro(m)
            r = m["r"]
            cv.create_oval(mx - r, my - r, mx + r, my + r, fill=c[m["cor"]], outline=c["SURFACE"], width=2)
            for k in (-1, 1):
                ex = mx + k * r * 0.38
                cv.create_oval(ex - r * 0.22, my - r * 0.42, ex + r * 0.22, my, fill=c["CLARO"], outline="")
                cv.create_oval(ex - r * 0.28, my - r * 0.28, ex - r * 0.08, my - r * 0.08, fill=c["BG"], outline="")
        if self.invul and (self.t // 5) % 2:
            return
        ang = max(-0.5, min(0.9, self.vy / px(12)))   # inclina para cima no impulso e para baixo na queda
        ca, sa = math.cos(ang), math.sin(ang)

        def P(lx, ly):   # lx para a frente, ly para cima
            return self.x + ca * px(lx) + sa * px(ly), self.y + sa * px(lx) - ca * px(ly)
        self.veiculo(P, ang)


def desenhar_moto(j, P, abaixado=False, fumaca=False):
    """Robô na moto. P(lx, ly): lx para a frente, ly para cima; rodas no ly = -8."""
    c, cv, px = j.c, j.cv, j.px
    for rx in (-16, 16):   # rodas com raio girando
        cx, cy = P(rx, -8)
        cv.create_oval(cx - px(8), cy - px(8), cx + px(8), cy + px(8), fill=c["SURFACE"], outline=c["TX2"], width=2)
        a = j.t * 0.4
        cv.create_line(cx - math.cos(a) * px(6), cy - math.sin(a) * px(6),
                       cx + math.cos(a) * px(6), cy + math.sin(a) * px(6), fill=c["TX3"], width=2)
    cv.create_polygon(*P(-16, -8), *P(-6, 2), *P(10, 2), *P(16, -8), *P(4, -4), fill=c["ACCENT_ESC"],
                      outline=c["SURFACE"], width=2)
    cv.create_line(*P(10, 2), *P(14, 10), fill=c["TX2"], width=3)
    d, f = (-12, 8) if abaixado else (0, 0)   # abaixado: deita sobre o tanque
    cv.create_line(*P(-2, 4), *P(4 + f, 18 + d), fill=c["SURFACE"], width=int(px(6)))
    cv.create_line(*P(4 + f, 14 + d), *P(13, 10), fill=c["SURFACE"], width=int(px(4)))
    cv.create_polygon(*P(-6 + f, 18 + d), *P(14 + f, 18 + d), *P(14 + f, 36 + d), *P(-6 + f, 36 + d),
                      fill=c["CLARO"], outline=c["SURFACE"])
    cv.create_polygon(*P(-3 + f, 21 + d), *P(11 + f, 21 + d), *P(11 + f, 33 + d), *P(-3 + f, 33 + d),
                      fill=c["BG"], outline="")
    for ex in (2, 9):
        ox, oy = P(ex + f, 27 + d)
        cv.create_oval(ox - px(1.8), oy - px(1.8), ox + px(1.8), oy + px(1.8), fill=c["ACCENT"], outline="")
    cv.create_polygon(*P(-8 + f, 36 + d), *P(16 + f, 36 + d), *P(12 + f, 44 + d), *P(-4 + f, 44 + d),
                      fill=c["ACCENT_ESC"], outline=c["SURFACE"])
    if fumaca:
        for k in range(3):
            fx, fy = P(-24 - k * 7 - (j.t % 6), -10 + k * 2)
            cv.create_oval(fx - 3, fy - 3, fx + 3, fy + 3, fill=c["TX3"], outline="")


def desenhar_nave(j, x, y, ang, fogo):
    c, cv, px = j.c, j.cv, j.px
    ca, sa = math.cos(ang), math.sin(ang)

    def P(lx, ly):   # lx para a frente, ly para o lado
        return x + ca * px(lx) - sa * px(ly), y + sa * px(lx) + ca * px(ly)
    if fogo:
        chama = 10 + (j.t % 4) * 3
        cv.create_polygon(*P(-14, 6), *P(-14 - chama, 0), *P(-14, -6), fill=c["WARN"], outline="")
    cv.create_polygon(*P(22, 0), *P(-14, 16), *P(-8, 0), *P(-14, -16), fill=c["ACCENT_ESC"],
                      outline=c["SURFACE"], width=2)
    cx, cy = P(2, 0)
    cv.create_oval(cx - px(9), cy - px(9), cx + px(9), cy + px(9), fill=c["CLARO"], outline=c["SURFACE"], width=2)
    cv.create_oval(cx - px(6), cy - px(6), cx + px(6), cy + px(6), fill=c["BG"], outline="")
    for k in (-2.5, 2.5):
        ox, oy = cx + px(k), cy - px(1)
        cv.create_oval(ox - px(1.6), oy - px(1.6), ox + px(1.6), oy + px(1.6), fill=c["ACCENT"], outline="")


class Moto(Jogo):
    """Igual ao jogo do dinossauro do navegador: corre no chão, pula e abaixa."""
    NOME, ROTULO = "Moto", "obstáculos"
    DICA = "Espaço ou seta para cima: pula (segure para ir mais alto)  ·  seta para baixo: abaixa"
    # tipo: (largura, altura, altura do chão até a base)
    OBSTACULOS = {"pedra": (26, 20, 0), "caixa": (42, 22, 0), "sonda": (24, 54, 0),
                  "drone_baixo": (32, 16, 26), "drone_alto": (32, 16, 50)}

    def __init__(self, robo, cores, auto=False):
        super().__init__(robo, cores, auto)
        px = self.px
        self.chao = self.H - px(8)
        self.hud_y = self.chao - px(190)
        self.x, self.h, self.vh = self.W * 0.14, 0.0, 0.0
        self.obst, self.falta, self.andado = [], self.W * 0.5, 0.0
        self.segurando = self.clique = False

    def passo(self):
        px = self.px
        pula = self.tecla("space", "up", "w") or self.clique
        self.clique = False
        self.abaixado = self.tecla("down", "s") and self.h == 0
        if pula and self.h == 0 and not self.segurando:
            self.vh = px(10.5)
        self.segurando = self.tecla("space", "up", "w")
        g = px(0.5) if self.segurando and self.vh > 0 else px(0.95)   # segurar = pulo mais alto
        if self.tecla("down", "s") and self.h > 0:
            g = px(1.6)                                                 # baixo no ar = desce rápido
        self.vh -= g
        self.h = max(0.0, self.h + self.vh)
        if self.h == 0:
            self.vh = 0.0
        self.vel = px(6) + min(px(6), self.t * px(0.0022))
        self.andado += self.vel
        for o in self.obst:
            o["x"] -= self.vel
            if not o["contou"] and o["x"] + px(o["w"]) < self.x - px(20):
                o["contou"] = True
                self.pontos += 1
        self.obst = [o for o in self.obst if o["x"] > -px(80)]
        self.falta -= self.vel
        if self.falta <= 0:
            tipos = ["pedra", "caixa", "sonda"] + (["drone_baixo", "drone_alto"] if self.pontos >= 5 else [])
            tipo = random.choice(tipos)
            w, h, base = self.OBSTACULOS[tipo]
            self.obst.append({"tipo": tipo, "x": self.W + px(20), "w": w, "h": h, "base": base, "contou": False})
            self.falta = random.uniform(px(300), px(620)) * (self.vel / px(6))
        # caixa do robô na moto: 40 de largura, 56 de altura (34 abaixado)
        alto = px(34 if self.abaixado else 56)
        for o in self.obst:
            ox1, ox2 = o["x"] + px(4), o["x"] + px(o["w"]) - px(4)
            oy1, oy2 = px(o["base"]), px(o["base"] + o["h"])
            if ox1 < self.x + px(20) and ox2 > self.x - px(20) and oy1 < self.h + alto and oy2 > self.h + px(2):
                if not self.invul:
                    self.vidas -= 1
                    self.invul = 90
                    self.top.bell()

    def desenhar(self):
        c, cv, px = self.c, self.cv, self.px
        cv.create_line(0, self.chao, self.W, self.chao, fill=c["TX3"], width=2)
        for k in range(0, int(self.W), int(px(90))):   # pedrinhas do chão passando
            gx = (k - self.andado) % self.W
            cv.create_line(gx, self.chao + px(3), gx + px(6), self.chao + px(3), fill=c["LINE2"], width=2)
        for o in self.obst:
            x, w, h, b = o["x"], px(o["w"]), px(o["h"]), px(o["base"])
            y2 = self.chao - b
            if o["tipo"] == "pedra":
                cv.create_polygon(x, y2, x + w * 0.2, y2 - h * 0.7, x + w * 0.55, y2 - h, x + w * 0.9, y2 - h * 0.5,
                                  x + w, y2, fill=c["TX3"], outline=c["SURFACE"], width=2)
            elif o["tipo"] == "caixa":   # caixa de testemunho
                cv.create_rectangle(x, y2 - h, x + w, y2, fill=c["WARN"], outline=c["SURFACE"], width=2)
                for k in (1, 2):
                    cv.create_line(x + w * k / 3, y2 - h, x + w * k / 3, y2, fill=c["SURFACE"])
            elif o["tipo"] == "sonda":   # sondinha: mastro com treliça
                cv.create_rectangle(x, y2 - h, x + w, y2, fill=c["WARN"], outline=c["SURFACE"], width=2)
                cv.create_line(x, y2 - h, x + w, y2 - h / 2, x, y2, fill=c["SURFACE"])
                cv.create_line(x + w, y2 - h, x, y2 - h / 2, x + w, y2, fill=c["SURFACE"])
            else:   # drone com hélices
                cv.create_rectangle(x + w * 0.25, y2 - h, x + w * 0.75, y2, fill=c["BAD"], outline=c["SURFACE"], width=2)
                gira = math.sin(self.t * 0.8) * w * 0.25
                cv.create_line(x + w * 0.25 - gira, y2 - h - px(3), x + w * 0.25 + gira, y2 - h - px(3), fill=c["TX2"], width=2)
                cv.create_line(x + w * 0.75 - gira, y2 - h - px(3), x + w * 0.75 + gira, y2 - h - px(3), fill=c["TX2"], width=2)
        if self.invul and (self.t // 5) % 2:
            return
        base = self.chao - px(16) - self.h
        desenhar_moto(self, lambda lx, ly: (self.x + px(lx), base - px(ly)), getattr(self, "abaixado", False),
                      self.h == 0)

    def premio(self):
        return self.pontos * 2


class PasseioMoto(Jogo):
    """Descanso: anda de moto de um lado para o outro no pé da tela, sem obstáculos; às vezes empina ou pula."""
    NOME = "Moto"

    def __init__(self, robo, cores, auto=True):
        super().__init__(robo, cores, True)
        px = self.px
        self.chao = self.H - px(8)
        self.topo = self.chao - px(110)
        self.x, self.sentido, self.h, self.vh, self.empina = self.W * 0.2, 1, 0.0, 0.0, 0
        self.vel = px(3.5)

    def passo(self):
        px = self.px
        self.x += self.sentido * self.vel
        if self.x > self.W - px(40) or self.x < px(40):
            self.sentido = -self.sentido
            self.x = min(max(self.x, px(40)), self.W - px(40))
        if self.h == 0 and random.random() < 0.004:
            self.vh = px(random.uniform(6, 10))   # pulinho de alegria
        if self.h == 0 and not self.empina and random.random() < 0.003:
            self.empina = 90                       # empina por um tempinho
        self.empina = max(0, self.empina - 1)
        self.vh -= px(0.6)
        self.h = max(0.0, self.h + self.vh)
        if self.h == 0:
            self.vh = 0.0
        self.vel = px(3.5 + math.sin(self.t * 0.01) * 1.2)

    def desenhar(self):
        px = self.px
        ang = -0.35 if self.empina else 0.0
        ca, sa = math.cos(ang), math.sin(ang)
        ox, oy = self.x - self.sentido * px(16), self.chao - px(8) - self.h   # gira em torno da roda de trás

        def P(lx, ly):
            lx, ly = lx + 16, ly + 8
            rx, ry = lx * ca - ly * sa, lx * sa + ly * ca
            return ox + self.sentido * px(rx), oy - px(ry)
        desenhar_moto(self, P, False, self.h == 0)


class PasseioNave(Jogo):
    """Descanso: voa livre pela tela em curvas suaves, sem obstáculos."""
    NOME = "Nave"

    def __init__(self, robo, cores, auto=True):
        super().__init__(robo, cores, True)
        self.topo = self.px(60)
        self.x, self.y, self.vx, self.vy = self.W * 0.3, self.H * 0.5, 0.0, 0.0
        self.fase = random.uniform(0, 6)

    def passo(self):
        k = self.t * 0.004 + self.fase
        gx = self.W / 2 + math.sin(k) * self.W * 0.42 + math.sin(k * 3.1) * self.W * 0.05
        gy = self.H / 2 + math.sin(k * 1.7 + 1) * self.H * 0.38
        self.vx += (gx - self.x) * 0.0012
        self.vy += (gy - self.y) * 0.0012
        vel = math.hypot(self.vx, self.vy)
        limite = self.px(5)
        if vel > limite:
            self.vx, self.vy = self.vx / vel * limite, self.vy / vel * limite
        self.x += self.vx
        self.y += self.vy

    def desenhar(self):
        desenhar_nave(self, self.x, self.y, math.atan2(self.vy, self.vx), True)


class Nave(Flappy):
    NOME = "Nave"
    MONSTROS = True
    DICA = "Espaço ou clique: impulso  ·  passe pelos vãos e desvie dos monstrinhos"

    def veiculo(self, P, ang):
        desenhar_nave(self, self.x, self.y, ang, self.t - self.impulso_t < 12)
