# Avisos de terceiros: Telegram e WhatsApp

## Hermes Agent

`whatsapp-ponte/` é uma cópia de `scripts/whatsapp-bridge/` do [Hermes Agent](https://github.com/NousResearch/hermes-agent), da Nous Research (MIT), checkout de 05/11/2026, commit `d0001c5b`. Arquivos: `bridge.js`, `bridge_helpers.js`, `allowlist.js`, `outbound_ids.js`, `owner_message_gate.js`. O cabeçalho de `bridge.js` lista o que mudou (modo fixo, segredo nas chamadas HTTP, nome do aparelho, sem QR no terminal).

`telegram.py` adapta de `plugins/platforms/telegram/` o limite de tempo do long polling e a espera crescente no 409. `ponte.py` adapta de `gateway/pairing.py` as regras do código de uso único e de `tools/send_message_tool.py` a regra de o modelo nunca enviar mensagem por conta própria.

```
MIT License

Copyright (c) 2025 Nous Research

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## Dependências que o `npm ci` baixa para a ponte

Não ficam no repositório; cada uma vem com a própria licença.

| Pacote | Licença | Para quê |
|---|---|---|
| [@whiskeysockets/baileys](https://github.com/WhiskeySockets/Baileys) | MIT | o protocolo do WhatsApp Web (não oficial) |
| [express](https://github.com/expressjs/express) | MIT | o HTTP local da ponte |
| [pino](https://github.com/pinojs/pino) | MIT | o log da Baileys |
| [@hapi/boom](https://github.com/hapijs/boom) | BSD-3-Clause | ler o motivo da desconexão |
