<#
  Nous WebUI - Ambiente do servidor (variaveis de ambiente do Open WebUI e do Ollama).
  Lido pelo start-nous.ps1 a cada inicio e pelo installer\atualizar-openwebui.ps1 no
  servidor de teste da atualizacao: desde a 0.10 o Open WebUI grava no banco os
  padroes que ve' no PRIMEIRO inicio, entao esse inicio tem que ter o ambiente do Nous.
  Devolve o modelo escolhido na instalacao (ou $null).
#>
function Set-NousEnv {
# --- Configuracao ---
$env:WEBUI_NAME          = "Nous"
$env:DATA_DIR            = if ($env:NOUS_DATA_DIR) { $env:NOUS_DATA_DIR } else { Join-Path $env:USERPROFILE "NousData" }
$env:OLLAMA_BASE_URL     = "http://127.0.0.1:11434"
# Modelo fica na VRAM por 5 min apos a ultima mensagem. Era 30s, mas recarregar
# um modelo de ~8 GB custa ~100s; com 30s, qualquer pausa para ler/digitar fazia
# o modelo sair e a proxima resposta demorar muito. 5 min cobre conversas
# normais sem recarregar e ainda libera a VRAM sozinho quando voce para.
$env:OLLAMA_KEEP_ALIVE   = "5m"
# Contexto padrao do Ollama. Sem isto o Ollama 0.30 carrega modelos pequenos com
# contexto maximo (qwen3:4b = 262k = ~44 GB, metade na RAM) sempre que alguma
# chamada nao manda num_ctx, e recarrega o modelo a cada troca: respostas de
# 3 min em vez de 15 s. Mesmo valor do register_model_ctx.py. Gravado tambem na
# conta do usuario para o Ollama aberto pela bandeja (vale no proximo inicio dele).
$env:OLLAMA_CONTEXT_LENGTH = "16384"
if (-not [Environment]::GetEnvironmentVariable("OLLAMA_CONTEXT_LENGTH", "User")) {
    [Environment]::SetEnvironmentVariable("OLLAMA_CONTEXT_LENGTH", "16384", "User")
}
$env:ENABLE_WEB_SEARCH   = "True"
$env:WEB_SEARCH_ENGINE   = "duckduckgo"
$env:WEB_SEARCH_RESULT_COUNT = "5"
# Injeta os resultados da busca direto no contexto (sem exigir modelo de
# embedding) - sem isto, o Gemma responde "nao tenho acesso em tempo real".
$env:BYPASS_WEB_SEARCH_EMBEDDING_AND_RETRIEVAL = "True"
$env:PORT                = "8080"
# Sem login o Open WebUI entrega a sessao a quem pedir; com CORS "*" (o padrao
# dele) qualquer site aberto no navegador poderia pedir. So' o proprio Nous.
$env:CORS_ALLOW_ORIGIN   = "http://localhost:8080;http://127.0.0.1:8080"
# Arena é gerenciado pelo register_arena.py (register via DB no boot).
# DEFAULT_MODELS só é definido se o instalador gravou um modelo escolhido.
$manifestPath = Join-Path $env:DATA_DIR "install-manifest.json"
$manifestModel = $null
if (Test-Path $manifestPath) {
    try { $manifestModel = (Get-Content $manifestPath -Raw | ConvertFrom-Json).model } catch {}
}
# O aviso "Uma nova versao do Open WebUI esta disponivel" leva ao GitHub e o
# usuario leigo nao tem como atualizar por la' - quem atualiza e' o Nous.
$env:ENABLE_VERSION_UPDATE_CHECK = "False"

# Modelos de NUVEM opcionais (GPT-4, Claude via OpenRouter, Gemini...). Deixamos a
# conexao OpenAI-compativel LIGADA para que o usuario POSSA adicionar uma chave em
# Admin > Settings > Connections se quiser. Sem chave, nada acontece e nada sai da
# maquina — o Nous continua 100% local por padrao. A memoria, os arquivos e o
# historico SEMPRE usam o Ollama local, mesmo que o chat use um modelo de nuvem.
$env:ENABLE_OPENAI_API = "True"

# Forca o idioma do Whisper para portugues (env-only na 0.9.6).
$env:WHISPER_LANGUAGE = "pt"

# Padroes do Nous sobre o Open WebUI (valem em instalacao nova; nas existentes
# o ajustes/register_ajustes.py grava uma vez na tabela config). Calendario e
# automacoes nativos ficam escondidos: o Nous tem a Agenda propria.
$env:DEFAULT_LOCALE          = "pt-BR"
$env:YOUTUBE_LOADER_LANGUAGE = "pt,pt-BR,en"
$env:ENABLE_CALENDAR         = "False"
$env:ENABLE_AUTOMATIONS      = "False"
# Desde a 0.10 o Open WebUI chama busca web e documentos como ferramentas do
# modelo ("nativo"); modelos pequenos de PC nao chamam e a busca voltava sem
# fontes. "legacy" e' o modo de sempre: o Open WebUI busca e poe no contexto.
$env:DEFAULT_MODEL_PARAMS    = '{"function_calling":"legacy"}'
# Embeddings multilingues (granite pelo Ollama, o mesmo do resto do Nous) so'
# com banco novo: trocar o modelo com documentos ja' indexados invalidaria a
# busca neles. Pelo Ollama porque o download do Hugging Face falha no Windows
# sem Modo de Desenvolvedor (links simbolicos).
if (-not (Test-Path (Join-Path $env:DATA_DIR "webui.db"))) {
    $env:RAG_EMBEDDING_ENGINE = "ollama"
    $env:RAG_EMBEDDING_MODEL  = "granite-embedding:278m"
}
# Desativa perguntas de acompanhamento automaticas (Autocomplete/Follow-up).
$env:ENABLE_AUTOCOMPLETE_GENERATION = "False"
$env:ENABLE_FOLLOW_UP_GENERATION    = "False"   # as sugestoes "Acompanhamento" sob a resposta

# Chave secreta ESTAVEL: sem ela, o open-webui gera uma nova a cada inicio e
# desloga voce. Guardamos uma chave local (em NousData, fora do git) e a reusamos.
$keyFile = Join-Path $env:DATA_DIR ".webui_secret_key"
if (-not (Test-Path $keyFile)) {
    New-Item -ItemType Directory -Force -Path $env:DATA_DIR | Out-Null
    $bytes = New-Object 'byte[]' 32
    [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    $key = ($bytes | ForEach-Object { $_.ToString('x2') }) -join ''
    [IO.File]::WriteAllText($keyFile, $key)
}
$env:WEBUI_SECRET_KEY = (Get-Content $keyFile -Raw).Trim()

# Sugestoes da tela inicial (substitui as genericas em ingles)
$env:DEFAULT_PROMPT_SUGGESTIONS = '[{"title":["Resumir um texto","cole o conteúdo e peça um resumo claro"],"content":"Resuma o texto a seguir de forma clara e objetiva:\n\n"},{"title":["Escrever um e-mail","profissional e direto"],"content":"Escreva um e-mail profissional sobre: "},{"title":["Explicar um conceito","de forma simples"],"content":"Explique de forma simples o conceito de: "},{"title":["Ideias criativas","para um projeto"],"content":"Me dê 5 ideias criativas para: "}]'
    return $manifestModel
}
