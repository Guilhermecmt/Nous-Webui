# Telegram e WhatsApp

Fale com o Nous de qualquer lugar, pelo celular. A mensagem chega ao computador de casa, o modelo responde lá, e a resposta volta pelo mesmo app. Memória, agenda, habilidades e e-mail funcionam como na tela, porque a mensagem entra pelo mesmo caminho da conversa normal.

Vem **desligado**. É a primeira vez que algo seu sai da máquina: o texto e o áudio da conversa passam pelos servidores do Telegram ou do WhatsApp. O modelo, as memórias e os arquivos continuam no computador, e ele precisa estar ligado e com o Nous aberto.

Abra em **Seu Nous › Telegram e WhatsApp**.

## Telegram (recomendado)

É oficial, de graça, e não abre porta nenhuma no roteador: o computador pergunta ao Telegram se há mensagem nova.

1. No Telegram do celular, abra o **@BotFather** e mande `/newbot`. Dê um nome e um usuário terminado em `bot`.
2. Ele responde com um **token**. Cole na tela do Nous e clique em **Conectar o bot**.
3. Clique em **Conectar o meu celular**: aparece um QR e um link. Leia o QR (ou abra o link no celular) e toque em **Começar**. O código vale 5 minutos e uma vez só.
4. Pronto. Escreva ou mande áudio para o bot.

Quem escrever para o bot sem parear **não recebe resposta nenhuma**, nem "quem é você?". Um bot é público, e o seu computador não pode virar porta de entrada. Conversas em grupo são ignoradas.

Comandos no chat: `/novo` começa uma conversa nova; `/ajuda` mostra o que dá para fazer. O áudio é transcrito **no computador** (Whisper local), e o Nous repete o que entendeu antes de responder.

## WhatsApp (experimental)

O WhatsApp não tem um jeito oficial de fazer isto para uso pessoal. O Nous usa a ponte do [Hermes Agent](https://github.com/NousResearch/hermes-agent) (biblioteca Baileys, de código aberto e não oficial), que entra como um **aparelho conectado** da sua conta, como o WhatsApp Web.

- O WhatsApp pode **suspender o número** por isso. Use um chip que você pode perder. Não há como medir o risco; ele existe.
- A ponte só lê o que **você escreve para você mesmo** (a conversa "Você"). Mensagens de outras pessoas, e o que você manda para os outros, ela descarta antes de chegar ao Nous.
- Precisa do Node.js, que vem com o Nous Code. Na primeira vez, o Nous baixa a ponte (`npm ci`), o que leva um minuto.
- Ao ligar, a ponte consulta `raw.githubusercontent.com` para saber a versão atual do protocolo do WhatsApp. É a única chamada fora do WhatsApp.

Para ligar: leia o aviso, marque que entendeu, **Ligar o WhatsApp**, e leia o QR em **Configurações › Aparelhos conectados › Conectar aparelho**. Desligar apaga a sessão e tira o computador dos aparelhos conectados.

## Por dentro

- `mensageiros/ponte.py`: pareamento, conversa e a chamada ao Open WebUI (`/api/chat/completions`, com um token de sessão assinado pela chave do próprio Nous). Uma pergunta por vez: a placa de vídeo é uma só.
- `mensageiros/telegram.py`: Bot API sobre `aiohttp`, sem biblioteca do Telegram. Long polling com limite de tempo e tratamento do 409 (sessão anterior ainda viva), do Hermes.
- `mensageiros/whatsapp.py` + `mensageiros/whatsapp-ponte/`: a ponte do Hermes em Node, com o modo fixo em "conversa consigo mesmo", um segredo por execução em toda chamada HTTP e o nome do Nous no aparelho.
- `mensageiros/nous_mensageiros.py`: o processo (8988) que roda os canais. Sobe quando há um canal ligado e volta sozinho com o Nous.
- `mensageiros/mensageiros_controle.py`: as rotas `/mensageiros/*` do monitor (8990). Só o computador chega nelas; pelo celular o botão nem aparece.
- Dados em `NousData\mensageiros`: `config.json` (o token do bot fica aqui, nunca volta para a tela), `donos\`, `conversas\`, `whatsapp\sessao\`.

O modelo **nunca** manda mensagem sozinho: só responde a quem falou com ele. Tarefas agendadas e lembretes continuam avisando por ntfy e e-mail.

Testes: `python -m unittest discover -s mensageiros/testes` (Telegram, Open WebUI e ponte de mentira; nada sai da máquina).
