const { chromium } = require('playwright');
const out = process.argv[2];
(async () => {
  const b = await chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  const p = await b.newPage({ viewport: { width: 1600, height: 1000 } });
  p.on('pageerror', e => console.log('err:', e.message));
  await p.goto('http://127.0.0.1:8765/rig_scene.html'); await p.waitForFunction('window.ready === true', null, { timeout: 60000 });
  const shots = {
    rig_overview: [[1.7, -1.9, 1.35], [0, 0.0, 0.28], 38],
    mount_closeup_side: [[-0.33, -0.32, 0.56], [-0.53, -0.06, 0.67], 34],
    mount_closeup_overhead: [[0.16, -0.2, 0.6], [0.0, 0.03, 0.69], 34],
    calibration_board_view: [[0.0, -1.4, 1.35], [0, 0.05, 0.2], 34, true],
  };
  for (const [name, [pos, look, fov, board]] of Object.entries(shots)) {
    await p.evaluate(([a, b, c, d]) => window.shoot(a, b, c, d), [pos, look, fov, !!board]);
    await p.screenshot({ path: `${out}/${name}.png` });
  }
  await b.close();
})();
