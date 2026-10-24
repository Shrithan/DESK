const { chromium } = require('playwright');
const out = process.argv[2];
(async () => {
  const b = await chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  const p = await b.newPage({ viewport: { width: 1600, height: 1000 } });
  p.on('pageerror', e => console.log('err:', e.message));
  await p.goto('http://127.0.0.1:8765/rig_scene.html'); await p.waitForFunction('window.ready === true', null, { timeout: 60000 });
  const shots = {
    rig_overview: [[1.55, -1.75, 1.15], [0, 0.02, 0.2], 38],
    mount_closeup_back_left: [[-0.18, 0.02, 0.62], [-0.4, 0.27, 0.48], 32],
    mount_closeup_overhead: [[0.16, -0.2, 0.42], [0.0, 0.03, 0.49], 34],
    calibration_board_view: [[0.0, -1.3, 1.2], [0, 0.05, 0.15], 34, true],
  };
  for (const [name, [pos, look, fov, board]] of Object.entries(shots)) {
    await p.evaluate(([a, b, c, d]) => window.shoot(a, b, c, d), [pos, look, fov, !!board]);
    await p.screenshot({ path: `${out}/${name}.png` });
  }
  await b.close();
})();
