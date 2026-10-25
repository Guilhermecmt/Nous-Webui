# Distribuição do Nous: releases, atualização e instalador assinado

Este documento é para quem mantém o Nous. Quem só usa não precisa dele.

## Como o Nous se atualiza

O ícone do Nous na bandeja (perto do relógio) e o painel avisam quando há versão nova
**do Nous** ou **de um modelo instalado**, e atualizam com um clique.

- **Quando procura:** no máximo 1 vez por dia, em segundo plano, a partir do ícone da bandeja
  (ele sobe junto com o Nous). É uma ida à internet: `api.github.com` (última release) e
  `registry.ollama.ai` (digest dos modelos). Nada seu é enviado além do pedido.
- **Como desligar:** menu do ícone, "Procurar atualizações sozinho" (ou `"verificar": false` em
  `%USERPROFILE%\NousData\atualizacao-config.json`). "Procurar atualizações agora" continua
  funcionando a pedido. No primeiro uso o ícone avisa disso numa notificação.
- **Nada é baixado sem o clique** em "Atualizar".
- **Onde fica o estado:** `NousData\atualizacao-estado.json`; o registro do que aconteceu fica
  em `NousData\atualizacao\atualizacao.log`; a cópia de segurança da versão anterior fica em
  `NousData\atualizacao\backup\` (só a última).

### Atualizar o Nous (app)

`atualizacao\nous-atualizar.ps1 -Acao Aplicar` (chamado pelo ícone ou pelo painel):

1. Consulta de novo a última release (não confia no arquivo de estado) e só aceita endereços de
   download do GitHub.
2. Confere espaço em disco, baixa `Nous-X.Y.Z.zip` e confere o **SHA256** com o
   `Nous-X.Y.Z.zip.sha256` publicado junto. Se não bater, apaga e para; nada foi alterado.
3. Extrai numa pasta de trabalho e confere que o pacote está completo e que o `VERSION` dele é o da tag.
4. Guarda uma cópia do app atual, para o Nous, troca os arquivos (espelha o pacote sobre
   `%LOCALAPPDATA%\Programs\Nous`; ficam intocados `bkp\`, `node_modules\`, `*.sqlite`, `*.log`,
   `.webui_secret_key`), atualiza o Open WebUI se o `$OPENWEBUI_PIN` do pacote mudou e as peças do
   Nous Code se o `package-lock.json` mudou.
5. Reinicia o Nous (se estava rodando) e espera ele responder. **Se não responder ou algo falhar
   no meio, volta sozinho para a versão anterior** e avisa.

Os dados em `NousData`, as notas em Documentos e o Ollama nunca são tocados.

Limite honesto: o hash publicado junto com o zip protege contra download corrompido, não contra
alguém que consiga trocar os dois arquivos na release. A proteção contra isso vem de assinar
o instalador/pacote (abaixo) e de proteger a conta do GitHub.

### Atualizar modelos

O mesmo ciclo diário compara o `digest` de cada modelo instalado (`/api/tags` do Ollama) com o do
registro (cabeçalho `Ollama-Content-Digest` do manifesto). Se mudou, o ícone e o painel avisam e
"Atualizar" refaz o `pull` (só as camadas que mudaram são baixadas) pela Loja de Modelos, com
progresso. Ficam de fora modelos do Hugging Face (`hf.co/...`), de nuvem e criados à mão.

## Publicar uma release

1. Acerte `VERSION`, `installer\nous-setup.iss` (`#define MyAppVersion`) e o `CHANGELOG.md`; commit na `main`.
2. Gere os arquivos (no computador ou pelo workflow):
   ```powershell
   .\tools\compilar-instalador.ps1     # dist\Nous-Setup.exe (+ .sha256), sem assinatura
   .\tools\empacotar-release.ps1       # dist\Nous-X.Y.Z.zip (+ .sha256)
   ```
   O workflow `.github/workflows/release.yml` faz o mesmo ao empurrar a tag `vX.Y.Z` e cria um
   **rascunho** de release; ele nunca publica sozinho. (Se o GitHub Actions estiver sem minutos, use os dois scripts.)
3. Publicar a mão, depois de conferir:
   ```powershell
   gh release create vX.Y.Z dist\Nous-X.Y.Z.zip dist\Nous-X.Y.Z.zip.sha256 dist\Nous-Setup.exe dist\Nous-Setup.exe.sha256 --title "Nous X.Y.Z"
   ```

Formato que o atualizador exige: tag `vX.Y.Z` (sem sufixo de pré-lançamento), asset `Nous-X.Y.Z.zip` e
asset `Nous-X.Y.Z.zip.sha256` com uma linha `hash  Nous-X.Y.Z.zip`. O zip tem os arquivos na raiz
(como o repositório, sem `.github`, `mockups` e `docs/screenshots`). Releases de rascunho e
pré-lançamento não contam como "última".

## O instalador (Nous-Setup.exe)

`installer\nous-setup.iss` (Inno Setup 6) copia o app para `%LOCALAPPDATA%\Programs\Nous` e roda o
`install-nous.ps1` para baixar e configurar o resto (Ollama, Python, Open WebUI). Atalhos: Nous, Parar Nous e
Nous Bandeja no Menu Iniciar; Nous na Área de Trabalho (opcional). Há também a opção, desligada, de abrir o
ícone da bandeja ao ligar o Windows (a mesma que o menu do ícone liga e desliga). Desinstalar: pelo
Windows, que roda o `uninstall-nous.ps1` (para o ícone e o Nous, remove o ambiente; preserva `NousData`).

Instalar o Inno Setup só para o seu usuário: `winget install --id JRSoftware.InnoSetup -e --scope user`.
O `.exe` fica em `dist\` e **não vai para o git** (`dist/` e `*.exe` estão no `.gitignore`).

## Assinar o instalador (quando houver certificado)

**Hoje não há certificado** (decisão: seguir sem). O instalador sai sem assinatura e o SmartScreen mostra
"O Windows protegeu seu PC" / "editor desconhecido"; a pessoa clica em "Mais informações > Executar assim mesmo".
`tools\assinar-instalador.ps1` fica parado, com aviso e código de saída 2, até receber um método e um certificado.

Opções quando for a hora:

| Opção | O que é | Observações |
| --- | --- | --- |
| **Azure Trusted Signing** | Serviço da Microsoft: não há arquivo de chave para guardar. | Exige conta Azure e validação de identidade da pessoa/empresa (disponível só em alguns países/regiões; confira antes). Mensalidade baixa. Reputação no SmartScreen vem mais rápido. |
| **Certificado OV em .pfx** | Comprado de uma autoridade (DigiCert, Sectigo, SSL.com...). | Desde 2023 as autoridades entregam a chave em token/HSM ou serviço na nuvem, não mais em arquivo livre; veja o que o fornecedor oferece. O SmartScreen ainda desconfia até juntar reputação. |
| **Certificado EV** | Validação estendida, em token USB/nuvem. | Mais caro; reputação imediata no SmartScreen. |

Passo a passo:

1. Instale o `signtool.exe` (Windows SDK, componente "Signing Tools for Desktop Apps"):
   `winget install Microsoft.WindowsSDK.10.0.26100`.
2. Compile: `.\tools\compilar-instalador.ps1`.
3. Assine:
   - **.pfx:** `$env:NOUS_PFX_SENHA = "..."` e depois
     `.\tools\assinar-instalador.ps1 -Metodo pfx -Pfx C:\caminho\nous.pfx` (a senha nunca vai na linha de comando).
   - **Azure Trusted Signing:** instale o pacote NuGet `Microsoft.Trusted.Signing.Client`, crie o `metadata.json`
     (`Endpoint`, `CodeSigningAccountName`, `CertificateProfileName`), entre com `az login` e rode
     `.\tools\assinar-instalador.ps1 -Metodo azure -AzureDlib C:\...\Azure.CodeSigning.Dlib.dll -AzureMetadata C:\...\metadata.json`.
   O script carimba a data (a assinatura continua válida depois do certificado vencer), verifica
   (`signtool verify /pa`) e regrava o `.sha256`, que muda com a assinatura.
4. Publique o `.exe` assinado e o novo `.sha256` na release.

Detalhes que valem a pena na hora: o desinstalador que o Inno embute é outro executável, assinável pela
diretiva `SignTool=` do `.iss` (opcional); o `.zip` de atualização não é "assinado" no sentido do Windows, ele é
protegido pelo SHA256 e pela conta do GitHub; reputação do SmartScreen se constrói com o tempo e downloads, mesmo com
certificado válido.
