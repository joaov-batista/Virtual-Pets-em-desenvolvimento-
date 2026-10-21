---
titulo: Robozinho DrillGeo — LEIA-ME
tipo: referencia
atualizado: 2026-10-21
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

Quando fica parado, ele opera uma sonda de perfuração ao lado. Parado por 3 minutos, dorme.

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
| `robozinho.py` | O programa (Python + tkinter, nada para instalar) |
| `Abrir Robozinho.vbs` | Abre sem janela preta e avisa se faltar Python |
| `robozinho.ico` | Ícone do atalho |
| `config.json` | Preferências (modo, atalho). Criado sozinho; sem dado pessoal |
| `erro.log` | Só aparece se der erro no programa |

Recriar o atalho da área de trabalho: `python robozinho.py --criar-atalho`.
Teste das animações (salva prints e GIF): `python robozinho.py --demo <pasta>`.
