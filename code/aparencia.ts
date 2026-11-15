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

export function paletaEscolhida(dataDir: string): string {
  try {
    const v = JSON.parse(fs.readFileSync(path.join(dataDir, 'aparencia.json'), 'utf8'));
    const p = v && typeof v === 'object' && !Array.isArray(v) ? v.paleta : null;
    return typeof p === 'string' && ids().includes(p) ? p : PADRAO;
  } catch { return PADRAO; }
}
