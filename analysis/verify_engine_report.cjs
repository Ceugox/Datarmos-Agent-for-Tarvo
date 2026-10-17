const { chromium } = require('C:/Users/marce/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const { pathToFileURL } = require('node:url');
const path = require('node:path');
const fs = require('node:fs');
const assert = require('node:assert/strict');

(async () => {
  const browser = await chromium.launch({ headless: true, executablePath: 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe' });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    const errors = [];
    const external = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('request', request => { if (/^https?:/.test(request.url())) external.push(request.url()); });
    await page.goto(pathToFileURL(path.resolve('saida/index.html')).href);
    assert.deepEqual(errors, []);
    assert.deepEqual(external, []);
    assert.match(await page.locator('#count').innerText(), /32 registros/);
    const payload = await page.locator('#records').textContent();
    const records = JSON.parse(payload);
    assert.equal(records.comissoes_por_lojista.length, 32);
    assert.equal(records.divergencias_taxa.length, 88);
    assert.equal(records.notas_a_emitir.length, 19);
    assert.equal(records.lancamentos_classificados.length, 184);
    assert.equal(records.cobertura.length, 2360);
    await page.screenshot({ path: 'analysis/engine-desktop.png' });
    await page.selectOption('#dataset', 'divergencias_taxa');
    await page.fill('#search', '22224579000109');
    assert.match(await page.locator('#count').innerText(), /5 registros/);
    await page.selectOption('#dataset', 'rastro');
    await page.fill('#search', records.comissoes_por_lojista[0].id_saida);
    const relevant = records.rastro.filter(row => row.id_saida === records.comissoes_por_lojista[0].id_saida);
    assert.match(await page.locator('#count').innerText(), new RegExp(`${relevant.length} registros`));
    await page.selectOption('#dataset', 'lancamentos_classificados');
    await page.fill('#search', 'L92');
    assert.equal(await page.locator('#table tbody tr').count(), 1);
    await page.selectOption('#dataset', 'comissoes_por_lojista');
    await page.click('#next');
    assert.match(await page.locator('#page').innerText(), /Página 2/);
    await page.fill('#search', 'nonexistent-record');
    assert.equal(await page.locator('#table tbody tr').count(), 0);
    await page.selectOption('#dataset', 'comissoes_por_lojista');
    await page.fill('#search', '');
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    for (const href of await page.locator('a').evaluateAll(links => links.map(a => a.getAttribute('href')))) {
      assert.equal(fs.existsSync(path.resolve('saida', decodeURIComponent(href))), true, href);
    }
    await page.screenshot({ path: 'analysis/engine-table.png' });
    await page.setViewportSize({ width: 390, height: 844 });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    await page.evaluate(() => { document.activeElement.blur(); window.scrollTo(0, 0); });
    await page.screenshot({ path: 'analysis/engine-mobile.png' });
    await page.emulateMedia({ media: 'print' });
    await page.pdf({ path: 'analysis/engine-print-preview.pdf', format: 'A4', printBackground: true });
    const evidence = { status: 'PASS', browser: 'Microsoft Edge', checks: ['embedded output counts','filters','pagination','trace selection','empty search','desktop/mobile overflow','all local downloads and source links','print render'], consoleErrors: errors, externalRequests: external };
    fs.writeFileSync('analysis/engine-browser-checks.json', JSON.stringify(evidence, null, 2));
    console.log(JSON.stringify(evidence));
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
