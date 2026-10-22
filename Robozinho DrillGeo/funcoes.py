# -*- coding: utf-8 -*-
"""Funções de trabalho do Robozinho DrillGeo (sem tela).

- IA grátis com reserva: Gemini -> Groq -> OpenRouter -> Claude Code (ordem em chaves.json)
- Ferramentas de PDF (pypdf): juntar, separar, extrair páginas, girar, tirar texto
- Ler e analisar documentos (PDF, TXT/MD/CSV, DOCX, XLSX) com conferência de CPF
- Auditoria do cofre (links quebrados, cabeçalho YAML, arquivos soltos na raiz)
- Busca no cofre com link para abrir no Obsidian

Nada aqui apaga ou sobrescreve arquivo: toda saída ganha nome novo ao lado do original.
"""

import json
import os
import re
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

try:   # certificados do Windows: antivírus/rede que inspeciona HTTPS não quebra as chamadas
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass

# Chaves ficam no perfil do Windows (fora do Dropbox): cada pessoa usa as suas.
PASTA_CHAVES = Path(os.environ.get("APPDATA", str(Path.home()))) / "Robozinho DrillGeo"
CHAVES = PASTA_CHAVES / "chaves.json"


def _resgatar_chaves_do_pacote():
    """Programa aberto pelo Claude Desktop (app em pacote MSIX) grava o AppData numa pasta privada
    (Packages\\<app>\\LocalCache\\Roaming); o robô, aberto pelo atalho, não enxerga. Copia para cá."""
    if CHAVES.is_file():
        return
    pacotes = Path(os.environ.get("LOCALAPPDATA", "")) / "Packages"
    try:
        achados = sorted(pacotes.glob("*/LocalCache/Roaming/Robozinho DrillGeo/chaves.json"),
                         key=lambda p: p.stat().st_mtime, reverse=True)
        if achados:
            PASTA_CHAVES.mkdir(parents=True, exist_ok=True)
            CHAVES.write_bytes(achados[0].read_bytes())
    except OSError:
        pass


_resgatar_chaves_do_pacote()

MOTORES = {
    # nome: (endereço compatível com OpenAI, modelo padrão, variável de ambiente)
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
               "gemini-3.5-flash-lite,gemini-3.8-flash,gemini-flash-latest", "GEMINI_API_KEY"),
    "groq": ("https://api.groq.com/openai/v1/chat/completions",
             "openai/gpt-oss-120b,qwen/qwen3.8-27b,openai/gpt-oss-20b", "GROQ_API_KEY"),
    "openrouter": ("https://openrouter.ai/api/v1/chat/completions",
                   "openrouter/free", "OPENROUTER_API_KEY"),
}

MODELO_CHAVES = {
    "_leia": "Chaves grátis: Gemini em aistudio.google.com/apikey · Groq em console.groq.com/keys · "
             "OpenRouter em openrouter.ai/keys. Cole a chave entre as aspas e salve. "
             "Sem chave, o motor é pulado. 'claude' = Claude Code deste computador (conta da empresa). "
             "Texto com CPF vai sempre só para o Claude.",
    "ordem": ["groq", "gemini", "openrouter", "claude"],
    "gemini": {"chave": "", "modelo": MOTORES["gemini"][1]},
    "groq": {"chave": "", "modelo": MOTORES["groq"][1]},
    "openrouter": {"chave": "", "modelo": MOTORES["openrouter"][1]},
}


ULTIMO_ERRO_CHAVES = ""


LEMBRETES = PASTA_CHAVES / "lembretes.json"   # texto pode ser pessoal: fica fora do Dropbox


def ler_lembretes():
    try:
        return json.loads(LEMBRETES.read_text(encoding="utf-8-sig"))
    except Exception:
        return []


def salvar_lembretes(lista):
    PASTA_CHAVES.mkdir(parents=True, exist_ok=True)
    LEMBRETES.write_text(json.dumps(lista, ensure_ascii=False, indent=2), encoding="utf-8")


def proxima_vez(quando, repetir):
    """Próxima data de um lembrete que se repete (diario, uteis, semanal, mensal). None = não repete."""
    import datetime as dt
    d = dt.datetime.fromtimestamp(quando)
    agora = dt.datetime.now()
    if repetir not in ("diario", "uteis", "semanal", "mensal"):
        return None
    while d <= agora:
        if repetir == "diario":
            d += dt.timedelta(days=1)
        elif repetir == "semanal":
            d += dt.timedelta(days=7)
        elif repetir == "uteis":
            d += dt.timedelta(days=1)
            while d.weekday() >= 5:
                d += dt.timedelta(days=1)
        else:
            mes, ano = (d.month % 12) + 1, d.year + (d.month == 12)
            import calendar
            d = d.replace(year=ano, month=mes, day=min(d.day, calendar.monthrange(ano, mes)[1]))
    return d.timestamp()


def ler_data_hora(data, hora):
    """'25/12/2026' + '09:30' -> timestamp. Aceita 'hoje', 'amanhã' e data sem ano."""
    import datetime as dt
    data, hora = (data or "hoje").strip().lower(), (hora or "09:00").strip().replace("h", ":")
    hoje = dt.date.today()
    if data in ("hoje", ""):
        dia = hoje
    elif data in ("amanha", "amanhã"):
        dia = hoje + dt.timedelta(days=1)
    else:
        partes = [int(x) for x in re.split(r"[/.-]", data)]
        ano = partes[2] if len(partes) > 2 else hoje.year
        dia = dt.date(ano + 2000 if ano < 100 else ano, partes[1], partes[0])
    hh, mm = (hora.split(":") + ["0"])[:2]
    return dt.datetime.combine(dia, dt.time(int(hh), int(mm or 0))).timestamp()


def ler_chaves():
    """Lê o chaves.json aceitando UTF-8 com ou sem BOM e ANSI (Bloco de Notas antigo)."""
    global ULTIMO_ERRO_CHAVES
    ULTIMO_ERRO_CHAVES = ""
    for cod in ("utf-8-sig", "cp1252"):
        try:
            return json.loads(CHAVES.read_text(encoding=cod))
        except UnicodeDecodeError:
            continue
        except Exception as e:
            ULTIMO_ERRO_CHAVES = f"{CHAVES}: {e}"
            break
    else:
        ULTIMO_ERRO_CHAVES = f"{CHAVES}: codificação desconhecida"
    return dict(MODELO_CHAVES)


def diagnostico_chaves():
    """Uma linha para a tela: qual arquivo foi lido e quais IAs têm chave."""
    com_chave = [n for n, _, _ in ordem_motores() if n != "claude"]
    if ULTIMO_ERRO_CHAVES:
        return "Não consegui ler as chaves: " + ULTIMO_ERRO_CHAVES
    return f"Arquivo: {CHAVES} (existe: {'sim' if CHAVES.is_file() else 'não'}) · IAs com chave: {', '.join(com_chave) or 'nenhuma'}"


def criar_arquivo_chaves():
    """Cria o chaves.json de modelo (se ainda não existir) e devolve o caminho."""
    if not CHAVES.is_file():
        PASTA_CHAVES.mkdir(parents=True, exist_ok=True)
        CHAVES.write_text(json.dumps(MODELO_CHAVES, ensure_ascii=False, indent=2), encoding="utf-8")
    return CHAVES


def ordem_motores():
    """Lista [(nome, chave, modelo)] na ordem configurada; 'claude' entra com chave vazia."""
    cfg = ler_chaves()
    saida = []
    for nome in cfg.get("ordem", MODELO_CHAVES["ordem"]):
        if nome == "claude":
            saida.append(("claude", "", ""))
        elif nome in MOTORES:
            item = cfg.get(nome, {})
            chave = (item.get("chave") or os.environ.get(MOTORES[nome][2], "")).strip()
            if chave:
                saida.append((nome, chave, item.get("modelo") or MOTORES[nome][1]))
    return saida


def perguntar_externo(nome, chave, modelo, mensagens, limite=20):
    """'modelo' pode ser uma lista separada por vírgula: se um estiver lotado ou fora do ar, tenta o próximo."""
    url = MOTORES[nome][0]
    erro = None
    for m in [x.strip() for x in modelo.split(",") if x.strip()]:
        corpo = json.dumps({"model": m, "messages": mensagens, "temperature": 0.4}).encode("utf-8")
        req = urllib.request.Request(url, data=corpo, method="POST", headers={
            "Content-Type": "application/json", "Authorization": f"Bearer {chave}",
            "User-Agent": "RobozinhoDrillGeo/2.0",   # sem isso o Groq (Cloudflare) recusa: erro 1010
            "HTTP-Referer": "https://drillgeo.com.br", "X-Title": "Robozinho DrillGeo"})
        try:
            with urllib.request.urlopen(req, timeout=limite) as r:
                dado = json.loads(r.read().decode("utf-8"))
            texto = (dado.get("choices") or [{}])[0].get("message", {}).get("content", "")
            if texto.strip():
                return texto.strip()
            erro = RuntimeError(f"{m}: resposta vazia")
        except Exception as e:
            erro = e
    raise erro or RuntimeError("nenhum modelo configurado")


# ----------------------------------------------------------------------------
# CPF
# ----------------------------------------------------------------------------

RE_CPF = re.compile(r"(?<!\d)(\d{3}\.?\d{3}\.?\d{3}-?\d{2})(?!\d)")


def cpf_valido(cpf):
    d = re.sub(r"\D", "", cpf)
    if len(d) != 11 or d == d[0] * 11:
        return False
    for n in (9, 10):
        soma = sum(int(d[i]) * (n + 1 - i) for i in range(n))
        if (soma * 10 % 11) % 10 != int(d[n]):
            return False
    return True


def tem_dado_pessoal(texto):
    return bool(RE_CPF.search(texto or ""))


SINAIS_SENSIVEIS = [
    (r"\bsal[aá]rio\b", "salário"), (r"\bholerite|contracheque|recibo de pagamento", "holerite"),
    (r"\bl[ií]quido\b", "valor líquido"), (r"\bag[eê]ncia\b|\bag\.\s?\d|\bc/?c\b|conta corrente", "dados bancários"),
    (r"\bpis\b|\bnis\b|\bpasep\b", "PIS"), (r"\brg\b|identidade", "RG"), (r"\bctps\b", "CTPS"),
    (r"\bcid\b|atestado|laudo", "saúde"), (r"\bfgts\b|\binss\b", "FGTS/INSS"),
    (r"\badmiss[aã]o\b|\bdemiss[aã]o\b|rescis[aã]o", "contrato de trabalho"),
]


def sinais_sensiveis(texto):
    """O que no texto parece dado de colaborador (LGPD). Lista vazia = nada encontrado."""
    baixo = (texto or "").lower()
    return [nome for padrao, nome in SINAIS_SENSIVEIS if re.search(padrao, baixo)]


def limpar_markdown(texto):
    """Texto puro (para copiar): tira **, __, `, # e troca marcador de lista por •."""
    linhas = []
    for linha in texto.splitlines():
        s = linha.lstrip()
        recuo = linha[:len(linha) - len(s)]
        s = re.sub(r"^#{1,6}\s+", "", s)
        s = re.sub(r"^[-*+]\s+", "• ", s)
        s = re.sub(r"\*\*(.+?)\*\*|__(.+?)__", lambda m: m.group(1) or m.group(2), s)
        s = re.sub(r"(?<![*\w])\*(?!\s)(.+?)(?<!\s)\*(?!\*)", r"\1", s)
        s = re.sub(r"`([^`]+)`", r"\1", s)
        linhas.append(recuo + s)
    return "\n".join(linhas)


def mascarar(cpf):
    d = re.sub(r"\D", "", cpf)
    return f"***.***.{d[6:9]}-{d[9:]}" if len(d) == 11 else "***"


# ----------------------------------------------------------------------------
# Arquivos e PDF
# ----------------------------------------------------------------------------

def novo_nome(base, sufixo, ext=None):
    """Arquivo ao lado do original com sufixo; nunca reaproveita um nome existente."""
    base = Path(base)
    ext = ext or base.suffix
    alvo = base.with_name(f"{base.stem} - {sufixo}{ext}")
    i = 2
    while alvo.exists():
        alvo = base.with_name(f"{base.stem} - {sufixo} ({i}){ext}")
        i += 1
    return alvo


def _pypdf():
    try:
        import pypdf
        return pypdf
    except ImportError:
        raise RuntimeError("Falta a biblioteca pypdf. Peça para instalar: pip install pypdf")


def pdf_juntar(caminhos):
    pypdf = _pypdf()
    w = pypdf.PdfWriter()
    for c in caminhos:
        for p in pypdf.PdfReader(c).pages:
            w.add_page(p)
    alvo = novo_nome(caminhos[0], "juntado", ".pdf")
    with open(alvo, "wb") as f:
        w.write(f)
    return [alvo]


def pdf_separar(caminho):
    pypdf = _pypdf()
    r = pypdf.PdfReader(caminho)
    pasta = novo_nome(caminho, "páginas", "")
    pasta.mkdir()
    saidas = []
    for i, p in enumerate(r.pages, 1):
        w = pypdf.PdfWriter()
        w.add_page(p)
        alvo = pasta / f"{Path(caminho).stem} - pág {i:03d}.pdf"
        with open(alvo, "wb") as f:
            w.write(f)
        saidas.append(alvo)
    return saidas


def faixa_paginas(texto, total):
    """'1-3, 5' -> [0, 1, 2, 4] (base zero), dentro do total."""
    paginas = []
    for parte in re.split(r"[,;\s]+", texto.strip()):
        if not parte:
            continue
        if "-" in parte:
            a, b = parte.split("-", 1)
            a, b = int(a or 1), int(b or total)
            paginas += list(range(a, b + 1))
        else:
            paginas.append(int(parte))
    return [p - 1 for p in paginas if 1 <= p <= total]


def pdf_extrair(caminho, faixa):
    pypdf = _pypdf()
    r = pypdf.PdfReader(caminho)
    idx = faixa_paginas(faixa, len(r.pages))
    if not idx:
        raise RuntimeError(f"Nenhuma página válida em '{faixa}' (o PDF tem {len(r.pages)}).")
    w = pypdf.PdfWriter()
    for i in idx:
        w.add_page(r.pages[i])
    alvo = novo_nome(caminho, f"págs {faixa.replace(' ', '')}", ".pdf")
    with open(alvo, "wb") as f:
        w.write(f)
    return [alvo]


def pdf_girar(caminho, graus=90):
    pypdf = _pypdf()
    r = pypdf.PdfReader(caminho)
    w = pypdf.PdfWriter()
    for p in r.pages:
        w.add_page(p.rotate(graus))
    alvo = novo_nome(caminho, "girado", ".pdf")
    with open(alvo, "wb") as f:
        w.write(f)
    return [alvo]


def pdf_para_texto(caminho):
    alvo = novo_nome(caminho, "texto", ".txt")
    alvo.write_text(ler_documento(caminho), encoding="utf-8")
    return [alvo]


FORMATOS_IMAGEM = {"PNG": ".png", "JPG": ".jpg", "WEBP": ".webp", "BMP": ".bmp", "GIF": ".gif",
                   "TIFF": ".tif", "ICO": ".ico", "PDF": ".pdf"}
ENTRADA_IMAGEM = "*.png *.jpg *.jpeg *.jfif *.webp *.bmp *.gif *.tif *.tiff *.ico *.heic *.heif *.avif *.pdf"


def converter_imagens(caminhos, formato):
    """Converte cada imagem para o formato escolhido (ao lado do original).
    PDF de entrada vira uma imagem por página (precisa do PyMuPDF); HEIC precisa do pillow-heif."""
    try:
        from PIL import Image
    except ImportError:
        raise RuntimeError("Falta a biblioteca Pillow. Peça para instalar: pip install pillow")
    try:
        import pillow_heif
        pillow_heif.register_heif_opener()
    except ImportError:
        pass
    ext = FORMATOS_IMAGEM[formato]
    saidas, falhas = [], []
    for c in caminhos:
        c = Path(c)
        try:
            if c.suffix.lower() == ".pdf":
                import pymupdf
                for i, pag in enumerate(pymupdf.open(str(c)), 1):
                    pix = pag.get_pixmap(dpi=150)
                    im = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                    saidas.append(_salvar_imagem(im, novo_nome(c, f"pág {i}", ext), formato))
                continue
            im = Image.open(c)
            im.load()
            saidas.append(_salvar_imagem(im, novo_nome(c, formato.lower(), ext), formato))
        except Exception as e:
            falhas.append(f"{c.name}: {str(e)[:80]}")
    return saidas, falhas


def _salvar_imagem(im, alvo, formato):
    if formato in ("JPG", "BMP", "PDF") and im.mode not in ("RGB", "L"):
        fundo = _fundo_branco(im)
        im = fundo
    if formato == "JPG":
        im.save(alvo, "JPEG", quality=92)
    elif formato == "ICO":
        im.save(alvo, "ICO", sizes=[(s, s) for s in (16, 32, 48, 64, 128, 256) if s <= max(im.size)])
    elif formato == "TIFF":
        im.save(alvo, "TIFF", compression="tiff_lzw")
    else:
        im.save(alvo, {"PNG": "PNG", "WEBP": "WEBP", "BMP": "BMP", "GIF": "GIF", "PDF": "PDF"}[formato])
    return alvo


def _fundo_branco(im):
    """Transparência vira fundo branco (JPG/BMP/PDF não têm transparência)."""
    from PIL import Image
    im = im.convert("RGBA")
    fundo = Image.new("RGB", im.size, (255, 255, 255))
    fundo.paste(im, mask=im.split()[3])
    return fundo


_SESSAO_IA = None


def _mascara_ia(rgba):
    """Máscara do rembg com o modelo isnet-general-use (~170 MB, baixado uma vez em ~/.u2net)."""
    global _SESSAO_IA
    from rembg import new_session, remove
    if _SESSAO_IA is None:
        try:
            import truststore   # usa os certificados do Windows (antivírus/rede que inspeciona HTTPS)
            truststore.inject_into_ssl()
        except ImportError:
            pass
        _SESSAO_IA = new_session("isnet-general-use")
    return remove(rgba, session=_SESSAO_IA, only_mask=True).convert("L").resize(rgba.size)


def remover_fundo(caminho, tolerancia=30):
    """Tira o fundo sem perder qualidade: os pixels da imagem não são mexidos, só ganham
    transparência (canal alfa), e sai em PNG (sem compressão com perda), no mesmo tamanho.
    Com o rembg instalado usa IA (fotos, pessoas, objetos); sem ele, tira o fundo liso
    que encosta nas bordas (logos, assinaturas, documentos, fundo branco)."""
    from PIL import Image, ImageDraw
    original = Image.open(caminho)
    original.load()
    rgba = original.convert("RGBA")
    try:
        mascara = _mascara_ia(rgba)
        metodo = "IA (rembg)"
    except Exception:   # sem rembg ou sem o modelo baixado: método do fundo liso
        import numpy as np
        px = np.asarray(rgba.convert("RGB")).astype(np.int16)
        borda = np.concatenate([px[0], px[-1], px[:, 0], px[:, -1]])
        fundo = np.median(borda, axis=0)
        dist = np.abs(px - fundo).max(axis=2)
        cand = Image.fromarray(np.where(dist <= tolerancia, 255, 0).astype(np.uint8)).copy()  # copy: fromarray é só leitura
        w, h = cand.size
        sementes = [(x, y) for x in range(0, w, 7) for y in (0, h - 1)] + \
                   [(x, y) for y in range(0, h, 7) for x in (0, w - 1)]
        for s in sementes:     # só o fundo ligado às bordas (o miolo da imagem fica)
            if cand.getpixel(s) == 255:
                ImageDraw.floodfill(cand, s, 128)
        fora = np.asarray(cand) == 128
        # borda suave: pixel quase igual ao fundo fica meio transparente (sem serrilhado)
        suave = np.clip((dist - tolerancia * 0.5) / (tolerancia * 0.5), 0, 1)
        alfa = np.where(fora, 0, 255).astype(np.float32)
        from PIL import ImageFilter
        vizinho = np.asarray(Image.fromarray((fora * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(5))) > 0
        perto = ~fora & vizinho & (dist <= tolerancia * 1.5)   # só o contorno, nunca o miolo
        alfa[perto] = np.maximum(suave[perto], 0.5) * 255
        mascara = Image.fromarray(alfa.astype(np.uint8))
        metodo = "fundo liso das bordas"
    alfa_orig = rgba.getchannel("A")
    from PIL import ImageChops
    rgba.putalpha(ImageChops.multiply(alfa_orig, mascara))
    alvo = novo_nome(caminho, "sem fundo", ".png")
    info = {k: v for k, v in original.info.items() if k in ("dpi", "icc_profile")}
    rgba.save(alvo, "PNG", optimize=False, **info)
    return alvo, metodo


def corrigir_ortografia(texto, limite=20):
    """Corretor do LanguageTool (grátis, pt-BR). Devolve (texto corrigido, lista de trocas)."""
    dados = urllib.parse.urlencode({"text": texto, "language": "pt-BR"}).encode("utf-8")
    req = urllib.request.Request("https://api.languagetool.org/v2/check", data=dados, method="POST")
    with urllib.request.urlopen(req, timeout=limite) as r:
        achados = json.loads(r.read().decode("utf-8")).get("matches", [])
    trocas, corrigido = [], texto
    for a in sorted(achados, key=lambda a: -a["offset"]):   # de trás para frente: posições não mudam
        if not a.get("replacements"):
            continue
        ini, fim = a["offset"], a["offset"] + a["length"]
        novo = a["replacements"][0]["value"]
        trocas.append(f"{texto[ini:fim]} → {novo}  ({a.get('message', '')[:60]})")
        corrigido = corrigido[:ini] + novo + corrigido[fim:]
    return corrigido, list(reversed(trocas))


def ler_documento(caminho):
    caminho = Path(caminho)
    ext = caminho.suffix.lower()
    if ext == ".pdf":
        r = _pypdf().PdfReader(str(caminho))
        return "\n\n".join(f"--- página {i} ---\n{p.extract_text() or ''}" for i, p in enumerate(r.pages, 1))
    if ext == ".docx":
        with zipfile.ZipFile(caminho) as z:
            xml = z.read("word/document.xml").decode("utf-8", errors="replace")
        xml = re.sub(r"</w:p>", "\n", xml)
        return re.sub(r"<[^>]+>", "", xml)
    if ext in (".xlsx", ".xlsm"):
        import openpyxl
        wb = openpyxl.load_workbook(caminho, read_only=True, data_only=True)
        linhas = []
        for ws in wb.worksheets:
            linhas.append(f"--- aba {ws.title} ---")
            for row in ws.iter_rows(values_only=True):
                if any(v is not None for v in row):
                    linhas.append(" | ".join("" if v is None else str(v) for v in row))
        return "\n".join(linhas)
    for cod in ("utf-8", "cp1252"):
        try:
            return caminho.read_text(encoding=cod)
        except UnicodeDecodeError:
            continue
    return caminho.read_text(encoding="utf-8", errors="replace")


def analisar_texto(texto):
    """Números rápidos + conferência de CPF (mostra só mascarado)."""
    cpfs = [m.group(1) for m in RE_CPF.finditer(texto)]
    norm = [re.sub(r"\D", "", c) for c in cpfs]
    invalidos = sorted({mascarar(c) for c in cpfs if not cpf_valido(c)})
    repetidos = sorted({mascarar(c) for c in norm if norm.count(c) > 1})
    datas = re.findall(r"\b\d{2}/\d{2}/\d{4}\b", texto)
    valores = re.findall(r"R\$\s?[\d.]+,\d{2}", texto)
    vazias = texto.count("|  |")
    linhas = [
        f"Caracteres: {len(texto):,}".replace(",", "."),
        f"Palavras: {len(texto.split()):,}".replace(",", "."),
        f"Datas encontradas: {len(datas)}" + (f" (de {min(datas, key=_ord)} a {max(datas, key=_ord)})" if datas else ""),
        f"Valores em R$: {len(valores)}",
        f"CPFs: {len(cpfs)} · inválidos: {len(invalidos)} · repetidos: {len(repetidos)}",
    ]
    if invalidos:
        linhas.append("  VERIFICAR inválidos: " + ", ".join(invalidos[:10]))
    if repetidos:
        linhas.append("  VERIFICAR repetidos: " + ", ".join(repetidos[:10]))
    if vazias:
        linhas.append(f"Células vazias entre preenchidas: {vazias}")
    if len(texto.strip()) < 30:
        linhas.append("VERIFICAR: quase sem texto — pode ser PDF escaneado (imagem).")
    return "\n".join(linhas), bool(cpfs)


def _ord(d):
    dd, mm, aa = d.split("/")
    return aa + mm + dd


# ----------------------------------------------------------------------------
# Cofre
# ----------------------------------------------------------------------------

RAIZ_PERMITIDA = {"00 - COMECE AQUI.md", "00 - Fluxo do cofre.md", "CLAUDE.md"}
PULAR = {".obsidian", ".trash", "08 - Arquivo"}


def notas(cofre):
    for p in Path(cofre).rglob("*.md"):
        if not any(parte in PULAR for parte in p.relative_to(cofre).parts):
            yield p


def auditar_cofre(cofre):
    cofre = Path(cofre)
    todas = list(notas(cofre))
    nomes = {p.stem.lower() for p in cofre.rglob("*") if p.is_file()}
    quebrados, sem_yaml, sem_data = [], [], []
    for p in todas:
        try:
            t = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        rel = str(p.relative_to(cofre))
        if rel == "CLAUDE.md":      # instrução do Claude: sem YAML e com [[Nota]] de exemplo
            continue
        if "Claude outputs" not in rel:
            if not t.startswith("---"):
                sem_yaml.append(rel)
            elif "atualizado:" not in t.split("---", 2)[1]:
                sem_data.append(rel)
        for alvo in re.findall(r"\[\[([^\]|#^]+)", t):
            nome = Path(alvo.strip()).stem.lower() if alvo.strip().lower().endswith(".md") else Path(alvo.strip()).name.lower()
            if nome and nome not in nomes:
                quebrados.append(f"{rel} → [[{alvo.strip()}]]")
    soltos = [p.name for p in cofre.iterdir() if p.is_file() and p.name not in RAIZ_PERMITIDA]

    def bloco(titulo, itens, n=12):
        if not itens:
            return f"OK  {titulo}: nenhum"
        extra = f"\n    … e mais {len(itens) - n}" if len(itens) > n else ""
        return f"VERIFICAR  {titulo}: {len(itens)}\n" + "\n".join(f"    · {i}" for i in itens[:n]) + extra

    return "\n\n".join([
        f"Notas conferidas: {len(todas)} (fora 08 - Arquivo)",
        bloco("Links [[...]] quebrados", quebrados),
        bloco("Notas sem cabeçalho YAML", sem_yaml),
        bloco("Notas sem campo atualizado:", sem_data),
        bloco("Arquivos soltos na raiz do cofre", soltos),
    ])


def buscar_cofre(cofre, termo, limite=8):
    """Procura no nome (vale mais) e no texto das notas. Devolve [(Path, trecho)]."""
    termo = termo.strip().lower()
    if not termo:
        return []
    palavras = termo.split()
    achados = []
    for p in notas(cofre):
        nome = p.stem.lower()
        pontos = sum(5 for w in palavras if w in nome)
        trecho = ""
        try:
            t = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            t = ""
        baixo = t.lower()
        for w in palavras:
            n = baixo.count(w)
            pontos += min(n, 5)
            if n and not trecho:
                i = baixo.find(w)
                trecho = " ".join(t[max(0, i - 50):i + 70].split())
        if pontos and all(w in nome or w in baixo for w in palavras):
            achados.append((pontos, p, trecho))
    achados.sort(key=lambda a: -a[0])
    return [(p, tr) for _, p, tr in achados[:limite]]


def link_obsidian(cofre, caminho):
    cofre = Path(cofre)
    rel = Path(caminho).relative_to(cofre).as_posix()
    return "obsidian://open?vault=" + urllib.parse.quote(cofre.name) + "&file=" + urllib.parse.quote(rel)
