const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  const p = await b.newPage({ viewport: { width: 1600, height: 1000 } });
  p.on('console', m => console.log('console:', m.text())); p.on('pageerror', e => console.log('err:', e.message));
  await p.goto('http://127.0.0.1:8765/index.html'); await p.waitForFunction('window.ready === true', null, { timeout: 60000 });
  const shots = { rig_overview: [[2.1, -2.0, 1.55], [0, 0.05, 0.25], 38], rig_overhead_mount: [[0.32, -0.26, 0.82], [0.0, 0.02, 0.99], 28] };
  for (const [name, [pos, look, fov]] of Object.entries(shots)) {
    await p.evaluate(([a, b, c]) => window.shoot(a, b, c), [pos, look, fov]);
    await p.screenshot({ path: `../${name}.png` });
  }
  await b.close();
})();
