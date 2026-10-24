/** Builds a deterministic SVG placeholder "camera frame" so the selection UI has something real to click on, without needing actual camera hardware. */
export const PLACEHOLDER_NATIVE_WIDTH = 1280;
export const PLACEHOLDER_NATIVE_HEIGHT = 720;

export function placeholderFrameDataUrl(cameraId: string, seed: number): string {
  const w = PLACEHOLDER_NATIVE_WIDTH;
  const h = PLACEHOLDER_NATIVE_HEIGHT;
  const cx = w / 2 + Math.sin(seed) * 180;
  const cy = h / 2 + Math.cos(seed * 0.7) * 100;

  const svg = `
    <svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}">
      <rect width="${w}" height="${h}" fill="#1a1a1a" />
      ${Array.from({ length: 12 })
        .map((_, i) => `<line x1="${(i + 1) * (w / 13)}" y1="0" x2="${(i + 1) * (w / 13)}" y2="${h}" stroke="#262626" stroke-width="1" />`)
        .join("")}
      <circle cx="${cx}" cy="${cy}" r="70" fill="#374151" stroke="#6b7280" stroke-width="3" />
      <text x="24" y="40" fill="#e5e7eb" font-family="monospace" font-size="24">${cameraId} (mock)</text>
      <text x="24" y="${h - 24}" fill="#6b7280" font-family="monospace" font-size="16">${w}x${h}</text>
    </svg>`.trim();

  return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`;
}
