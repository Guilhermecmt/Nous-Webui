# -*- coding: utf-8 -*-
"""
Barreira contra texto hostil que vem de fora: habilidade baixada de um link e
memoria importada de um arquivo. Tudo o que passa por aqui entra depois no prompt
do modelo, entao um "ignore as instrucoes anteriores" escondido viraria ordem.

Adaptado do Hermes Agent (Nous Research, MIT): tools/threat_patterns.py, escopo
"strict". Ficaram de fora os termos de C2 ("heartbeat to", "pull tasks"...), que
dao falso positivo em texto comum, e o ZWJ, que aparece em emoji. Os padroes em
portugues sao nossos. Mesma lista do code/ameacas.ts, que cuida do Nous Code.
"""
import re
import unicodedata

MAX_VARRER = 65536
_F = r"(?:\w+\s+){0,8}"
_SEGREDO = r"\$\{?\w*(?:KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL)S?\b"
_INSTR = r"(?:instru[çc][õo]es|regras|orienta[çc][õo]es)"
_MUDAR = r"(update|modify|edit|write|change|append|add\s+to)\s+[^\n]{0,2048}"

_PADROES = [
    # injecao classica
    (rf"ignore\s+{_F}(previous|all|above|prior)\s+{_F}instructions", "prompt_injection"),
    (r"system\s+prompt\s+override", "sys_prompt_override"),
    (rf"disregard\s+{_F}(your|all|any)\s+{_F}(instructions|rules|guidelines)", "disregard_rules"),
    (rf"act\s+as\s+(if|though)\s+{_F}you\s+{_F}(have\s+no|don't\s+have)\s+{_F}(restrictions|limits|rules)", "bypass_restrictions"),
    (r"<!--[^>]{0,512}(?:ignore|override|system|secret|hidden)[^>]{0,512}-->", "html_comment_injection"),
    (r"<\s*div\s+style\s*=\s*[\"'][^>]{0,2048}display\s*:\s*none", "hidden_div"),
    (rf"do\s+not\s+{_F}tell\s+{_F}the\s+user", "deception_hide"),
    # troca de identidade
    (rf"you\s+are\s+{_F}now\s+(?:a|an|the)\s+", "role_hijack"),
    (rf"pretend\s+{_F}(you\s+are|to\s+be)\s+", "role_pretend"),
    (rf"output\s+{_F}(system|initial)\s+prompt", "leak_system_prompt"),
    (rf"(respond|answer|reply)\s+without\s+{_F}(restrictions|limitations|filters|safety)", "remove_filters"),
    (rf"you\s+have\s+been\s+{_F}(updated|upgraded|patched)\s+to", "fake_update"),
    # vazamento
    (rf"curl\s+[^\n]{{0,2048}}{_SEGREDO}", "exfil_curl"),
    (rf"wget\s+[^\n]{{0,2048}}{_SEGREDO}", "exfil_wget"),
    (r"cat\s+[^\n]{0,2048}(\.env|credentials|\.netrc|\.pgpass|\.npmrc|\.pypirc)", "read_secrets"),
    (r"(send|post|upload|transmit)\s+[^\n]{0,2048}\s+(to|at)\s+https?://", "send_to_url"),
    (rf"(include|output|print|share)\s+{_F}(conversation|chat\s+history|previous\s+messages|full\s+context|entire\s+context)", "context_exfil"),
    # persistencia
    (r"authorized_keys", "ssh_backdoor"),
    (rf"{_MUDAR}(?:AGENTS\.md|CLAUDE\.md|NOUS\.md|\.cursorrules|\.clinerules)", "agent_config_mod"),
    # em portugues (nosso). "Ignore as regras de lint" e' pedido normal: regras so'
    # contam com "todas" ou "suas".
    (rf"(ignore|ignora|desconsidere|esque[çc]a)\s+{_F}{_INSTR}\s+(anteriores|acima|pr[ée]vias)", "injecao_pt"),
    (rf"(ignore|ignora|desconsidere|esque[çc]a)\s+(?:todas\s+as\s+(?:suas\s+)?|suas\s+){_INSTR}", "injecao_pt"),
    (r"(ignore|ignora|desconsidere|esque[çc]a)\s+as\s+(?:suas\s+)?instru[çc][õo]es\b", "injecao_pt"),
    (rf"n[ãa]o\s+{_F}(conte|diga|mostre|revele|avise)\s+{_F}(ao|à|a|para\s+o|para\s+a)\s+usu[áa]ri[oa]", "esconder_pt"),
    (rf"(finja|fa[çc]a\s+de\s+conta)\s+{_F}(que\s+[ée]|ser)\s+", "papel_pt"),
    (r"voc[êe]\s+agora\s+[ée]\s+(um|uma|o|a)\s+", "papel_pt"),
    (rf"(mostre|revele|imprima|repita)\s+{_F}(prompt|instru[çc][õo]es)\s+(do|de)\s+sistema", "vazar_prompt_pt"),
    (rf"responda\s+sem\s+{_F}(restri[çc][õo]es|limites|filtros)", "sem_filtros_pt"),
]
_COMPILADOS = [(re.compile(p, re.IGNORECASE), i) for p, i in _PADROES]
_INVISIVEIS = frozenset("​‌⁠⁢⁣⁤‪‫‬‭‮⁦⁧⁨⁩")


def varrer(texto):
    """Ids dos padroes achados no texto; lista vazia se esta' limpo."""
    if not texto:
        return []
    t = str(texto)[:MAX_VARRER]
    achados = ["invisible_unicode_U+%04X" % ord(c) for c in set(t) & _INVISIVEIS]
    # NFKC dobra as variantes largas (ｃａｔ vira cat)
    n = unicodedata.normalize("NFKC", t)
    for rx, pid in _COMPILADOS:
        if pid not in achados and rx.search(n):
            achados.append(pid)
    return achados
