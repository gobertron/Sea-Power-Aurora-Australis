const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const crypto = require('node:crypto');

async function main() {
    const html = path.resolve(process.argv[2] || path.join(__dirname, '../../HMAS-Rimehaven-3D.html'));
    const executable = process.env.CHROMIUM_PATH ||
        (fs.existsSync('/usr/bin/chromium') ? '/usr/bin/chromium' : undefined);
    const browser = await chromium.launch({
        executablePath: executable, headless: true,
        args: ['--no-sandbox', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'],
    });
    try {
        const page = await browser.newPage({viewport: {width: 1400, height: 900}});
        const errors = [];
        page.on('pageerror', e => errors.push(e.message));
        await page.goto(pathToFileURL(html).href);
        await page.waitForFunction(() => window.viewerReady === true, null, {timeout: 60000});
        assert.equal(await page.title(), 'HMAS Rimehaven • 3D model');
        const result = {file: path.basename(html), fits: {}, browser: await browser.version()};
        const canvas = page.locator('#view');
        async function digest() {
            return crypto.createHash('sha256').update(await canvas.screenshot()).digest('hex');
        }
        const silhouettes = new Set();
        for (const fit of ['2000','2010','2020']) {
            await page.selectOption('#era', fit);
            await page.waitForFunction(year => window.viewerEra === year, fit);
            result.fits[fit] = await page.locator('#geometry').innerText();
            silhouettes.add(await digest());
        }
        assert.equal(silhouettes.size, 3);
        for (const view of ['bow','stern','side','top','quarter']) {
            await page.locator(`[data-view="${view}"]`).click();
            assert.equal(await page.locator(`[data-view="${view}"]`).getAttribute('aria-pressed'), 'true');
        }
        await page.locator('[data-view="side"]').click();
        const full = await digest();
        await page.uncheck('#underwater');
        assert.notEqual(await digest(), full);
        await page.locator('[data-view="bow"]').click();
        assert.ok(await page.locator('#underwater').isChecked());
        const plain = await digest();
        await page.selectOption('#highlight', '6');
        assert.notEqual(await digest(), plain);
        await page.setViewportSize({width: 390, height: 844});
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
        assert.deepEqual(errors, []);
        console.log(JSON.stringify({...result, fullHullToggle: true, hullHighlight: true, mobileLayout: true}, null, 2));
    } finally {
        await browser.close();
    }
}
main().catch(e => { console.error(e); process.exitCode = 1; });
