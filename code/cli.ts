// nous: o Nous Code no terminal. Uso: nous [pedido] | nous -p "pedido" | nous --ajuda
// (os modulos ficam em code/cli/)
import { principal } from './cli/principal.ts';

principal(process.argv.slice(2)).then(
  (codigo) => { process.stdout.write('', () => process.exit(codigo)); },
  (e) => { process.stderr.write('nous: ' + (e instanceof Error ? e.message : String(e)) + '\n'); process.exit(1); },
);
