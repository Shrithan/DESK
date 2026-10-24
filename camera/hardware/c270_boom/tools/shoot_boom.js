// node shoot_boom.js <out_dir>   (serve the folder holding boom_scene.html, boom_scene.json, boom_assembled.stl, node_modules/three on :8765)
const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  const p = await b.newPage({ viewport: { width: 1600, height: 1000 } });
  p.on('pageerror', e => console.log('err:', e.message));
  await p.goto('http://127.0.0.1:8765/boom_scene.html'); await p.waitForFunction('window.ready === true', null, { timeout: 60000 });
  const shots = { boom_overview: [[1.9, -2.0, 1.4], [0.3, 0, 0.45], 36], boom_head: [[0.62, -0.32, 0.78], [0.43, 0, 0.93], 32], boom_base: [[0.38, -0.42, 0.32], [0.02, 0, 0.06], 34] };
  for (const [n, [pos, look, fov]] of Object.entries(shots)) { await p.evaluate(([a, c, d]) => window.shoot(a, c, d), [pos, look, fov]); await p.screenshot({ path: `${process.argv[2]}/${n}.png` }); }
  await b.close();
})();
