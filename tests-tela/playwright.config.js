/* Testes de tela do Nous. Um Open WebUI so' para o teste sobe no globalSetup e
 * morre no fim: um worker, porque todos os testes usam a mesma instancia. */
const { defineConfig } = require('@playwright/test');

module.exports = defineConfig({
  testDir: '.',
  testMatch: '*.spec.js',
  outputDir: 'saida/resultados',
  globalSetup: './servidor.js',
  workers: 1,
  fullyParallel: false,
  timeout: 60000,
  reporter: [['list']],
  use: {
    baseURL: 'http://127.0.0.1:8082',
    viewport: { width: 1400, height: 860 },
    locale: 'pt-BR',
    screenshot: 'only-on-failure',
  },
});
