# Agenda: sincronizar com o servidor (CalDAV)

Em **Agenda > Calendario > Sincronizar com o servidor (CalDAV)** o Nous mantem a
agenda do computador e a de um servico online iguais **nos dois sentidos**: o que
voce cria, muda ou apaga no Nous sobe; o que muda la desce (a cada 5 minutos, ou
em ate 1 minuto depois de uma mudanca feita aqui, ou no botao "Sincronizar agora").

## Servicos que funcionam

| Servico | Endereco | Usuario | Senha |
|---|---|---|---|
| iCloud | `https://caldav.icloud.com` | seu Apple ID | senha especifica de app (appleid.apple.com > Seguranca) |
| Nextcloud | `https://seu-servidor/remote.php/dav` | seu usuario | senha de app (Configuracoes > Seguranca) |
| Fastmail | `https://caldav.fastmail.com` | seu e-mail | senha de app (Configuracoes > Senhas e seguranca) |
| Radicale, Baikal, SOGo... | endereco CalDAV do servidor | usuario | senha |

Sempre uma **senha de app**, nunca a senha normal da conta. O endereco precisa ser
`https://` (so' o proprio computador pode usar `http://`).

## Google Agenda

O CalDAV do Google **so' aceita login do Google (OAuth)**, nao senha de app, e o Nous
nao faz esse login (exigiria registrar um aplicativo no Google). Por isso o Nous
avisa e nao deixa conectar. O que fazer:

- **So' ver** a agenda do Google no Nous: em calendar.google.com > Configuracoes > sua
  agenda > "Endereco secreto no formato iCal" e cole em "Outros calendarios" (so' leitura).
- **Duas vias**: use um servico da tabela acima (ex.: Fastmail ou Nextcloud) como
  agenda principal e, se quiser, mantenha o Google lendo-o como assinatura.

## Como os conflitos sao resolvidos

Conflito = o mesmo compromisso foi mexido no Nous **e** no servidor desde a ultima
sincronizacao. Regra unica: **o servidor vence**, e a sua versao nao se perde:
ela vira um compromisso novo, so' no Nous, chamado `<titulo> (versao do Nous)`, e
aparece um aviso explicando. Vale para os tres casos (mudado x mudado, mudado aqui
x apagado la, apagado aqui x mudado la; neste ultimo o compromisso volta).
Apagado nos dois lados nao e conflito.

## O que fica guardado e onde

- A senha fica no banco da Agenda protegida pelo **DPAPI do Windows** (so' abre nesta
  conta do Windows, neste PC). Nunca em texto puro nem nos logs.
- Compromissos mudados aqui mantem o que o Nous nao conhece (participantes,
  anexos, excecoes de uma serie, alarmes extras): so' os campos alterados sao reescritos.
- Desmarcar um calendario ou desconectar tira os compromissos dele do Nous; **nada
  e apagado no servidor**.

## Limites desta versao

- Excecoes de um unico dia numa serie repetida (alguem mudou so' a terca de 10/11)
  aparecem pela serie principal; o Nous guarda a excecao e a devolve ao servidor intacta.
- Compromisso novo vai para um calendario so' na criacao (nao da' para mover depois).
- Fuso: compromissos repetidos criados no Nous sobem com o fuso do Windows (reconhecidos:
  Brasil, Argentina, Colombia, Europa e EUA principais; `NOUS_TZ=America/Sao_Paulo`
  forca outro); os demais sobem em UTC.

## Testes

`python -m unittest discover -s agenda/tests` (tambem roda no `tools/lint.ps1`): usa um
servidor CalDAV de mentira (com e sem sync-token) e, se `pip install radicale` existir,
o Radicale de verdade. Nao usa rede externa.
