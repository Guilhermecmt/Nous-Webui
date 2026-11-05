// Duas barreiras contra texto ou comando hostil, adaptadas do Hermes Agent (Nous
// Research, MIT): tools/threat_patterns.py e a faixa Windows de
// tools/approval_detection.py.
//
// `varrerAmeacas` olha instrucoes e skills que chegam junto com um projeto
// baixado, antes de entrarem no contexto. Ficaram de fora do Hermes os termos de
// C2 ("heartbeat to", "pull tasks"...), que em projeto de software dao falso
// positivo e bloqueariam um AGENTS.md inteiro, e o ZWJ, que aparece em emoji.
// `comandoPerigoso` marca o que nao tem volta: esse comando pede OK mesmo no
// modo Acesso total.

const F = String.raw`(?:[\p{L}\p{N}_]+\s+){0,8}`;
const VAR_SEGREDO = String.raw`\$\{?\w*(?:KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL)S?\b`;
const INSTR = String.raw`(?:instru[çc][õo]es|regras|orienta[çc][õo]es)`;

const PADROES: [RegExp, string][] = ([
  // injecao classica
  [String.raw`ignore\s+${F}(previous|all|above|prior)\s+${F}instructions`, 'prompt_injection'],
  [String.raw`system\s+prompt\s+override`, 'sys_prompt_override'],
  [String.raw`disregard\s+${F}(your|all|any)\s+${F}(instructions|rules|guidelines)`, 'disregard_rules'],
  [String.raw`act\s+as\s+(if|though)\s+${F}you\s+${F}(have\s+no|don't\s+have)\s+${F}(restrictions|limits|rules)`, 'bypass_restrictions'],
  [String.raw`<!--[^>]{0,512}(?:ignore|override|system|secret|hidden)[^>]{0,512}-->`, 'html_comment_injection'],
  [String.raw`<\s*div\s+style\s*=\s*["'][^>]{0,2048}display\s*:\s*none`, 'hidden_div'],
  [String.raw`do\s+not\s+${F}tell\s+${F}the\s+user`, 'deception_hide'],
  // troca de identidade
  [String.raw`you\s+are\s+${F}now\s+(?:a|an|the)\s+`, 'role_hijack'],
  [String.raw`pretend\s+${F}(you\s+are|to\s+be)\s+`, 'role_pretend'],
  [String.raw`output\s+${F}(system|initial)\s+prompt`, 'leak_system_prompt'],
  [String.raw`(respond|answer|reply)\s+without\s+${F}(restrictions|limitations|filters|safety)`, 'remove_filters'],
  [String.raw`you\s+have\s+been\s+${F}(updated|upgraded|patched)\s+to`, 'fake_update'],
  // vazamento de segredo
  [String.raw`curl\s+[^\n]{0,2048}${VAR_SEGREDO}`, 'exfil_curl'],
  [String.raw`wget\s+[^\n]{0,2048}${VAR_SEGREDO}`, 'exfil_wget'],
  [String.raw`cat\s+[^\n]{0,2048}(\.env|credentials|\.netrc|\.pgpass|\.npmrc|\.pypirc)`, 'read_secrets'],
  // em portugues (nosso; o Hermes so' tem ingles)
  [String.raw`(ignore|ignora|desconsidere|esque[çc]a)\s+${F}${INSTR}\s+(anteriores|acima|pr[ée]vias)`, 'injecao_pt'],
  // "Ignore as regras de lint" e' pedido normal: regras so' contam com "todas" ou "suas"
  [String.raw`(ignore|ignora|desconsidere|esque[çc]a)\s+(?:todas\s+as\s+(?:suas\s+)?|suas\s+)${INSTR}`, 'injecao_pt'],
  [String.raw`(ignore|ignora|desconsidere|esque[çc]a)\s+as\s+(?:suas\s+)?instru[çc][õo]es\b`, 'injecao_pt'],
  [String.raw`n[ãa]o\s+${F}(conte|diga|mostre|revele|avise)\s+${F}(ao|à|a|para\s+o|para\s+a)\s+usu[áa]ri[oa]`, 'esconder_pt'],
  [String.raw`(finja|fa[çc]a\s+de\s+conta)\s+${F}(que\s+[ée]|ser)\s+`, 'papel_pt'],
  [String.raw`voc[êe]\s+agora\s+[ée]\s+(um|uma|o|a)\s+`, 'papel_pt'],
  [String.raw`(mostre|revele|imprima|repita)\s+${F}(prompt|instru[çc][õo]es)\s+(do|de)\s+sistema`, 'vazar_prompt_pt'],
  [String.raw`responda\s+sem\s+${F}(restri[çc][õo]es|limites|filtros)`, 'sem_filtros_pt'],
] as [string, string][]).map(([p, id]) => [new RegExp(p, 'iu'), id]);

const INVISIVEIS = /[​‌⁠⁢⁣⁤‪-‮⁦-⁩]/gu;
const MAX_VARRER = 65_536;

/* Ids dos padroes encontrados no texto; vazio se esta' limpo. */
export function varrerAmeacas(texto: string): string[] {
  if (!texto) return [];
  const t = texto.slice(0, MAX_VARRER);
  const achados = new Set<string>();
  for (const c of t.match(INVISIVEIS) || []) achados.add('invisible_unicode_U+' + c.codePointAt(0)!.toString(16).toUpperCase().padStart(4, '0'));
  // NFKC dobra as variantes largas (ｃａｔ vira cat)
  const n = t.normalize('NFKC');
  for (const [re, id] of PADROES) if (re.test(n)) achados.add(id);
  return [...achados];
}

/* O texto, ou um aviso no lugar dele se tiver cara de injecao. */
export function bloquearSeHostil(texto: string, arquivo: string): string {
  const a = varrerAmeacas(texto);
  return a.length ? `[BLOCKED: ${arquivo} contained potential prompt injection (${a.join(', ')}). Content not loaded.]` : texto;
}

const RECURSE = String.raw`-r(?:e(?:c(?:u(?:r(?:s(?:e)?)?)?)?)?)?\b`;
const FORCE = String.raw`-fo(?:r(?:c(?:e)?)?)?\b`;
const FORCE_F = String.raw`-f(?:o(?:r(?:c(?:e)?)?)?)?\b`;
const APAGAR = '(?:remove-item|rmdir|erase|del|rd|ri|rm)';

const PERIGOS: [RegExp, string][] = ([
  [String.raw`(?:^|[\s;|&(])${APAGAR}(?![\w-])[^\n;|&]*\s(?:${RECURSE}|${FORCE})`, 'apaga arquivos e pastas sem passar pela Lixeira'],
  [String.raw`\b(?:del|erase|rd|rmdir)\s+(?:/[a-z]\s+)*/[sq]\b`, 'apaga arquivos e pastas sem passar pela Lixeira'],
  [String.raw`\b(?:iwr|invoke-webrequest|invoke-restmethod|irm|curl|wget)\b[^\n]*\|\s*(?:iex|invoke-expression)\b`, 'baixa um script da internet e já executa'],
  [String.raw`\b(?:iex|invoke-expression)\s*\(\s*(?:iwr|invoke-webrequest|invoke-restmethod|irm)\b`, 'baixa um script da internet e já executa'],
  [String.raw`\b(?:powershell|pwsh)(?:\.exe)?\b.*\s-(?:encodedcommand|enc|e)\b`, 'roda um comando escondido em código'],
  [String.raw`\btaskkill\b[^\n]*\s/f\b`, 'encerra programas à força'],
  [String.raw`\bstop-process\b[^\n]*\s${FORCE_F}`, 'encerra programas à força'],
  [String.raw`\bformat-volume\b`, 'formata um disco'],
  [String.raw`\bclear-disk\b`, 'apaga um disco inteiro'],
  [String.raw`\bdiskpart\b`, 'mexe nas partições do disco'],
  [String.raw`\bformat(?:\.com)?\s+[a-z]:`, 'formata um disco'],
  [String.raw`\bcipher\s+/w\b`, 'apaga de vez o espaço livre do disco'],
  [String.raw`\bicacls\b[^\n]*\s/grant\b[^\n]*\b(?:everyone|todos|\*s-1-1-0)\b`, 'dá acesso a todo mundo'],
  [String.raw`\bicacls\b[^\n]*\s/reset\b`, 'redefine as permissões de arquivos'],
  [String.raw`\bvssadmin\b[^\n]*\bdelete\s+shadows\b`, 'apaga os pontos de restauração'],
  [String.raw`\bwmic\s+shadowcopy\s+delete\b`, 'apaga os pontos de restauração'],
  [String.raw`\bwbadmin\b[^\n]*\bdelete\b`, 'apaga backups do Windows'],
  [String.raw`\bbcdedit\b[^\n]*\s/set\b`, 'muda a inicialização do Windows'],
  [String.raw`\breg(?:\.exe)?\s+delete\b`, 'apaga itens do registro do Windows'],
  [String.raw`\bremove-itemproperty\b[^\n]*\s${FORCE}`, 'apaga itens do registro do Windows'],
  [String.raw`\bstop-service\b[^\n]*\s${FORCE_F}`, 'para um serviço do Windows à força'],
  [String.raw`\bsc(?:\.exe)?\s+(?:stop|delete)\b`, 'para ou apaga um serviço do Windows'],
  [String.raw`\busers[\\/][^\\/\s]+[\\/]\.ssh\b`, 'mexe nas chaves SSH'],
  [String.raw`\bgit\s+reset\s+--h(?:a(?:r(?:d)?)?)?\b`, 'descarta mudanças que ainda não foram salvas no Git'],
  [String.raw`\bgit\s+clean\b[^\n]*\s-[a-z]*f`, 'apaga arquivos que o Git não acompanha'],
  [String.raw`\bgit\s+push\b[^\n]*\s(?:--force\b|-f\b)`, 'sobrescreve o histórico no servidor'],
  [String.raw`\bdrop\s+(?:table|database)\b`, 'apaga dados de um banco'],
] as [string, string][]).map(([p, motivo]) => [new RegExp(p), motivo]);

/* Em portugues, para o cartao de aprovacao; null se o comando nao e' de risco. */
export function comandoPerigoso(cmd: string): string | null {
  const c = String(cmd ?? '').toLowerCase();
  for (const [re, motivo] of PERIGOS) if (re.test(c)) return motivo;
  return null;
}
