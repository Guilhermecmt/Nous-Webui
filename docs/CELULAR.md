# Usar no celular

O Nous abre no celular, em casa, pelo mesmo Wi-Fi do computador. Vem **desligado**: você liga no painel **Seu Nous > Celular**, lê um QR com a câmera e pronto. Fecha sozinho quando o Nous fecha.

## Como usar

1. No computador: painel **Seu Nous > Celular > Ligar "Usar no celular"**. O Windows pede permissão (uma vez) para liberar a porta na rede privada.
2. Leia o QR com a câmera do celular e toque no link (ou digite o código na página que abrir).
3. O celular guarda um cookie de aparelho por 180 dias. Nas próximas vezes, basta ligar "Usar no celular" no computador e abrir o endereço (`http://192.168.x.x:8999`); não precisa de QR.
4. Para tirar um celular: **Celular > Remover**. Vale na hora. O ícone da bandeja mostra se está ligado e desliga.

## Segurança (o que ele faz e o que não faz)

O Nous não tem login: quem entra pelo celular usa o Nous inteiro (conversas, documentos, agenda, e-mail). Por isso:

- **Desligado por padrão** e desliga quando o Nous fecha (o Parar Nous também derruba o portão).
- **Portão próprio** (`celular/nous_celular.py`, porta 8999). O Open WebUI e os serviços continuam só em 127.0.0.1; o portão repassa para eles (HTTP, streaming e WebSocket).
- **Só rede de casa**: o IP de origem tem que ser IPv4 privado (10/8, 172.16/12, 192.168/16), link-local, ou IPv6 ULA/link-local. Qualquer outro recebe 403 antes de qualquer outra coisa. O cabeçalho `Host` tem que ser o IP do PC (ou o nome dele), o que barra DNS rebinding.
- **Pareamento**: código de 8 caracteres (~40 bits), uso único, vence em 5 minutos, guardado só como hash. O portão troca por um cookie de aparelho (`HttpOnly`, `SameSite=Strict`, 256 bits, guardado só como hash em `NousData\celular\aparelhos\`).
- **Força bruta**: 5 erros por IP = 5 minutos de espera (dobra a cada bloqueio, até 1 h); 10 erros no total queimam o código.
- **CSRF**: todo pedido que muda coisa e todo WebSocket precisa de `Origin` igual ao endereço do portão (ou `Sec-Fetch-Site` same-origin); o cookie é `SameSite=Strict`. Para o Open WebUI e os serviços o portão reescreve o `Origin` (que lá só aceitam o próprio Nous).
- **Não passa pelo portão**: o Nous Code (8998, roda comandos no PC) e o controle do próprio celular (`/celular/*` do monitor, que só atende o computador).
- **Firewall**: uma regra de entrada `Nous - Usar no celular`, TCP na porta 8999, perfil **Privado**, só da sub-rede local, ligada ao `python.exe` do Nous. Criada ao ligar (com o pedido do Windows) e removida ao desligar e na desinstalação. Se fechar o Nous com o celular ligado, a regra fica (sem ninguém escutando); desligar no painel ou desinstalar a remove. Em rede **Pública** o Nous não liga e explica como mudar para Privada.

## HTTP e não HTTPS

O endereço é `http://` (sem cadeado). Um certificado próprio faria o celular mostrar "conexão não segura / site perigoso", que assusta quem não é técnico, e no iPhone só some instalando um perfil. Uma autoridade pública não emite certificado para `192.168.x.x`. Num Wi-Fi doméstico com senha WPA2/WPA3 o tráfego já vai cifrado até o roteador, e o portão só atende a rede de casa; o risco que sobra é de quem já está dentro do seu Wi-Fi. Se você usa Wi-Fi aberto ou compartilhado com desconhecidos, não ligue.

**O que não funciona por causa disso** (o navegador só libera com HTTPS ou localhost): microfone e modo de voz, instalar o Nous como aplicativo (PWA), copiar com um toque pela API de área de transferência e notificações do navegador. Digitar, enviar fotos, documentos, agenda, e-mail, loja de modelos, editor de fotos e galeria funcionam.

## Teste sem mexer no Windows

`NOUS_CELULAR_SIMULAR=1` no monitor: nada é mudado no firewall; `NousData\celular\simulado.log` mostra o comando que seria executado. `NOUS_CELULAR_PORT` troca a porta; `NOUS_CELULAR_PERFIL_SIMULADO=Public` finge rede pública. Os testes (`celular/testes`, rodados pelo `tools/lint.ps1`) sobem um Open WebUI e um serviço de mentira; o IP de origem é injetado pelo cabeçalho `X-Teste-Ip`, que só existe com `--modo-teste` (o monitor nunca passa isso).
