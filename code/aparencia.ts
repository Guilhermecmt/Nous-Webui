// Paleta de cores escolhida no Nous (Aparencia). A escolha e' da instalacao e fica em
// NousData/aparencia.json, gravada pelo monitor (monitor/aparencia.py); aqui so' se le'.
// Qualquer problema (sem arquivo, estragado, paleta que nao existe mais) = ouro.
import fs from 'node:fs';
import path from 'node:path';

const AQUI = import.meta.dirname;
const BRANDING = path.join(AQUI, '..', 'branding');
export const FOLHA_PALETAS = path.join(BRANDING, 'nous-paletas.css');
const PADRAO = 'ouro';

function ids(): string[] {
  try {
    const j = JSON.parse(fs.readFileSync(path.join(BRANDING, 'paletas.json'), 'utf8'));
    return (j.paletas || []).map((p: { id: string }) => p.id);
  } catch { return [PADRAO]; }
}

/* As cores do Nous para o terminal (versao escura da paleta escolhida): a de texto e a
 * de destaque. Usadas na coruja da abertura, no prompt e nos olhos do "pensando". */
export function coresMarca(dataDir: string): { clara: string; escura: string } | undefined {
  try {
    const j = JSON.parse(fs.readFileSync(path.join(BRANDING, 'paletas.json'), 'utf8'));
    const id = paletaEscolhida(dataDir);
    const p = (j.paletas || []).find((x: { id: string }) => x.id === id);
    if (p && p.escuro && p.escuro.acc_txt && p.escuro.acc) return { clara: p.escuro.acc_txt, escura: p.escuro.acc };
  } catch { /* sem paletas: o terminal usa as cores dele */ }
  return undefined;
}

export function paletaEscolhida(dataDir: string): string {
  try {
    const v = JSON.parse(fs.readFileSync(path.join(dataDir, 'aparencia.json'), 'utf8'));
    const p = v && typeof v === 'object' && !Array.isArray(v) ? v.paleta : null;
    return typeof p === 'string' && ids().includes(p) ? p : PADRAO;
  } catch { return PADRAO; }
}
