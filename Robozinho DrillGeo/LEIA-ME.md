---
titulo: Robozinho DrillGeo — LEIA-ME
tipo: referencia
atualizado: 2026-10-22
tags: [robozinho, claude-code, assistente]
---

# Robozinho DrillGeo

Robô de mesa que anda pela base da tela e manda perguntas rápidas para o Claude.
Projeto: [[Robozinho DrillGeo]].

## Como abrir

- Duas vezes no atalho **Robozinho DrillGeo** da área de trabalho
  (ou em `Abrir Robozinho.vbs`, nesta pasta).
- Precisa do Python 3 e do Claude Code instalados. Se faltar um deles, o robô avisa.
- **Primeira vez:** botão direito no robô > **Entrar no Claude Code (login)** e faça o login
  no navegador. Só uma vez por computador.

## Comandos

| Ação | Como |
|---|---|
| Perguntar | Clique no robô ou **Ctrl+Alt+Espaço** → escreva → **Enter** (Shift+Enter pula linha, Esc fecha) |
| Continuar a conversa | Botão **Responder** na resposta, ou marque "Continuar a conversa" |
| Começar do zero | Botão direito > **Nova conversa** |
| Copiar a resposta | Botão **Copiar** (ou Ctrl+C no balão) |
| Abrir o Claude Desktop | Botão **Abrir no Claude** (só abre, não cola nada) |
| Mudar de lugar | Arraste com o mouse |
| Menu | Botão direito: Andar, Parar, Dormir, Ficar no canto, Nova conversa, Fechar |

Quando fica parado, ele opera uma sonda de perfuração ao lado. Dorme só depois de 15 min sem ninguém mexer, e o cochilo dura pouco.

**Problemas do dia a dia** (a cada 2 a 4 min): chuva em cima dele, petróleo que suja a sonda (limpe no painel por R$ 25 ou espere chover), água no furo que estraga a sonda, rocha dura, tropeço e, de vez em quando, um elogio do supervisor. Todos mexem no humor.

**Sonda com peças:** Broca, Haste, Bomba de lama e Motor (mecânicas) e Painel elétrico, Fiação e Bateria (elétricas). Cada uma gasta e pode quebrar sozinha, e uma peça quebrada para a sonda. No painel: **Revisão mecânica** e **Revisão elétrica** recuperam as peças que ainda funcionam; peça quebrada só com **Comprar peça**. Com petróleo, as peças gastam em dobro e tudo fica 50% mais caro.

## Tamagotchi e ferramentas (v2)

- **Clique nele** → painel: Energia, Óleo, Humor, Sonda, dinheiro, testemunhos e prêmios, e os botões.
- **Cuide dele:** Recarregar, Óleo (R$ 5), Carinho, Consertar a sonda, Doar R$ 10/50/100.
  Ele ganha dinheiro tirando testemunhos da sonda e ajudando você.
- **Arraste** uma imagem, PDF ou documento para cima dele: aparecem as ações daquele arquivo.
- Ferramentas: PDF, converter imagens, remover fundo (sem perder qualidade), corretor ortográfico,
  analisar documento, auditoria de erros, procurar no cofre (abre no Obsidian), lembrete.
- **Lembretes** com data, hora, repetição e jeito (Urgente: ele fica doido até você responder).
- **Jogos**: Jogar moto (dinossauro: Espaço pula, ↓ abaixa) / Jogar nave (Flappy: Espaço dá impulso). Esc sai.
- **Passeio**: ele anda de moto ou voa sozinho, sem obstáculos, para descansar. Clique nele para voltar.
- Nada é sobrescrito: o resultado sai ao lado do original, com nome novo.

### IAs grátis
Menu > **Chaves das IAs grátis** abre o `chaves.json` (no seu perfil do Windows, fora do Dropbox).
Cole a chave do Gemini (aistudio.google.com/apikey), do Groq (console.groq.com/keys) ou do
OpenRouter (openrouter.ai/keys). Ordem: Groq → Gemini → OpenRouter (sem Claude Code). Sem chave, usa o
Claude Code. Texto com CPF e `!fazer` vão sempre só para o Claude Code.

**Se aparecer "Não consegui ler as chaves… No such file":** o `chaves.json` foi salvo por um programa aberto pelo Claude Desktop e ficou na pasta privada dele. Feche e abra o robô pelo atalho: ele copia as chaves sozinho para a pasta certa.

## Modo só leitura (padrão)

O robô usa `claude -p` na pasta do cofre (segue o `CLAUDE.md`) com só as ferramentas de
leitura (Read, Glob, Grep): **não cria, não altera e não apaga arquivos, não roda comandos**
e não usa conectores. Para deixar o Claude alterar arquivos, comece a mensagem com
**`!fazer`** e confirme na janelinha "Tem certeza?". Mesmo assim, comandos de terminal ficam bloqueados.

Limite de espera: 3 minutos. Tarefas longas: use o Claude Desktop.

## Como desligar

- Fechar: botão direito > **Fechar**.
- Abrir junto com o Windows: botão direito > **Abrir junto com o Windows** (vem desligado;
  pede confirmação antes de ligar; clique de novo para desligar).
- Atalho de teclado: botão direito > **Atalho Ctrl+Alt+Espaço** liga/desliga.

## Arquivos

| Arquivo | Para quê |
|---|---|
| `robozinho.py` | O programa (Python + tkinter) |
| `jogos.py` | Jogos na tela (moto estilo dinossauro, nave estilo Flappy Bird) e passeios livres para descansar |
| `funcoes.py` | Ferramentas: IAs, PDF, imagens, análise, auditoria, busca (usa pypdf, Pillow, PyMuPDF) |
| `Abrir Robozinho.vbs` | Abre sem janela preta e avisa se faltar Python |
| `robozinho.ico` | Ícone do atalho |
| `config.json` | Preferências (modo, atalho). Criado sozinho; sem dado pessoal |
| `erro.log` | Só aparece se der erro no programa |

Recriar o atalho da área de trabalho: `python robozinho.py --criar-atalho`.
Teste das animações (salva prints e GIF): `python robozinho.py --demo <pasta>`.
