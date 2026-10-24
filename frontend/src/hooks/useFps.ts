import { useEffect, useRef, useState } from "react";

/** Samples requestAnimationFrame rate, updating state at most twice a second. */
export function useFps(): number {
  const [fps, setFps] = useState(0);
  const frames = useRef(0);
  const lastSample = useRef(performance.now());

  useEffect(() => {
    let raf = 0;
    const loop = () => {
      frames.current += 1;
      const now = performance.now();
      const elapsed = now - lastSample.current;
      if (elapsed >= 500) {
        setFps(Math.round((frames.current * 1000) / elapsed));
        frames.current = 0;
        lastSample.current = now;
      }
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, []);

  return fps;
}
