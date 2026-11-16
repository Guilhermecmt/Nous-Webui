# Nous.exe: janela própria do Nous

Desenho aprovado pelo dono em 15/11/2026 (abordagem A e os padrões abaixo).

## Por quê

O Nous abria como uma aba do navegador padrão (e a tela de carregamento como uma
página solta). O dono quer que ele seja um programa: janela própria, separada do
Chrome, com nome e ícone próprios.

## Objetivos

- `Nous.exe`: janela do Windows com o motor do Edge embutido (WebView2, que já vem no
  Windows 11), nome "Nous" e o ícone em selo na barra de tarefas e no Alt+Tab.
- Uma janela só: abrir de novo traz a janela aberta para a frente.
- A tela de carregamento aparece dentro da janela; depois o Nous abre ali mesmo.
- Fechar a janela não desliga o Nous (como fechar a aba hoje); "Parar Nous" desliga
  tudo e fecha a janela.
- Atalho, Menu Iniciar, bandeja ("Abrir o Nous") e o `start-nous.ps1` abrem a janela.
- O Nous Code abre como janela do `Nous.exe` (várias, uma por projeto), no lugar do Edge.
- Links de sites abrem no navegador padrão; o microfone e a área de transferência são
  liberados só para o próprio Nous; tamanho e posição são lembrados; perfil (cookies,
  armazenamento) em `NousData\janela`, separado do Chrome e do Edge.
- Vai no instalador para todo mundo. Sem WebView2, ou se a compilação falhar, tudo
  continua abrindo no navegador, como antes.

## Fora

- Juntar a bandeja dentro do `Nous.exe` (a bandeja segue no `bandeja.ps1`).
- Celular (continua pelo navegador do celular).
- Assinatura digital do `.exe`.

## O que não pode acontecer

- Lógica de inicialização congelada dentro do `.exe` (o `Nous.exe` antigo, do ps2exe,
  foi removido por isso): quem liga o Nous continua sendo o `start-nous.ps1`.
- Atalho sumir se algo falhar na compilação.
- Atualização travar porque a janela está aberta (o `.exe` em uso).

## Abordagens consideradas

1. **C# compilado na instalação (escolhida).** Fonte `janela/Nous.cs` no repositório,
   compilada com o `csc.exe` do .NET Framework 4.8 (já vem no Windows). DLLs do SDK do
   WebView2 1.0.3856.49 (assinadas pela Microsoft, licença BSD) em `janela/lib`.
2. pywebview (Python): pacotes a baixar, abre mais devagar, ícone e nome na barra de
   tarefas exigem ajustes.
3. `.exe` pronto no repositório: binário no git e aviso de "editor desconhecido" para
   quem baixa.

## Desenho

- `janela/Nous.cs`:
  - Sem argumentos: janela principal. Uma instância só (mutex `Local\Nous.Janela.Principal`;
    a segunda instância sinaliza `Local\Nous.Janela.Mostrar` e sai).
  - Servidor no ar (`/health` em 8080): abre `http://localhost:8080`. Fora do ar: abre
    `launchers/loading.html` e, sem `--sem-iniciar`, roda `launchers/nous-hidden.vbs` com
    `NOUS_SEM_NAVEGADOR=1`. Confere o servidor a cada 2 s e abre o Nous quando subir.
  - `--code <url>`: janela do Nous Code (só `http://127.0.0.1:8998/...`).
  - `--destino <url>`: só classifica (código de saída: 0 Nous, 1 Nous Code, 2 outra página
    local, 3 site de fora, 4 bloqueado). Usado pelos testes.
  - `--carregando`: mostra a tela de carregamento sem conferir o servidor (teste visual).
  - Navegação: site de fora vai para o navegador padrão; Nous Code abre janela do Nous Code;
    outra página local abre numa janela filha (mesmo perfil).
  - Perfil em `NousData\janela\perfil`; posição em `NousData\janela\principal.txt` e
    `code.txt`.
- `launchers/janela-nous.ps1`: `Test-WebView2`, `Get-JanelaHash`, `Test-JanelaAtual`,
  `Build-NousJanela` (compila numa pasta temporária e troca; se o `.exe` estiver em uso,
  renomeia o antigo, o que o Windows permite), `Get-NousJanela` e `Open-NousJanela`.
- `start-nous.ps1`, `bandeja.ps1`, `code/ide.ts`: abrem o `Nous.exe` quando existe.
- Instalador: compila no passo 6 e o atalho "Nous" aponta para o `Nous.exe`.
  Atualizador: recompila se o código da janela mudou. `stop-nous.ps1` fecha a janela
  (o atualizador passa `-ManterJanela`).

## Plano

1. `Nous.cs`, DLLs + licença, `janela-nous.ps1`, teste `janela/testes/testar-janela.ps1`
   (compila numa pasta temporária e confere os destinos) e o passo no `lint.ps1`.
2. Ligações: `start-nous.ps1`, `bandeja.ps1`, `stop-nous.ps1`, `code/ide.ts`, instalador,
   atualizador.
3. Teste na tela contra o Nous instalado (servidor no ar): janela abre, uma instância só,
   link de fora vai ao navegador, Nous Code abre na janela própria, tela de carregamento.
4. CHANGELOG, instalar no app, conferir.
