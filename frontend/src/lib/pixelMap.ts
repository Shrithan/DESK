/**
 * Maps a CSS click position on an `object-fit: contain` image/video element to
 * native image pixel coordinates, accounting for letterboxing. Clicks that land
 * in the letterbox bars (outside the actual image) return null.
 */
export function cssClickToNativePixel(
  clickX: number,
  clickY: number,
  displayWidth: number,
  displayHeight: number,
  nativeWidth: number,
  nativeHeight: number,
): { x: number; y: number } | null {
  const displayAspect = displayWidth / displayHeight;
  const nativeAspect = nativeWidth / nativeHeight;

  let renderedWidth = displayWidth;
  let renderedHeight = displayHeight;
  let offsetX = 0;
  let offsetY = 0;

  if (nativeAspect > displayAspect) {
    // Image is wider than container: letterbox top/bottom.
    renderedHeight = displayWidth / nativeAspect;
    offsetY = (displayHeight - renderedHeight) / 2;
  } else {
    // Image is taller than container: letterbox left/right.
    renderedWidth = displayHeight * nativeAspect;
    offsetX = (displayWidth - renderedWidth) / 2;
  }

  const localX = clickX - offsetX;
  const localY = clickY - offsetY;

  if (localX < 0 || localY < 0 || localX > renderedWidth || localY > renderedHeight) {
    return null;
  }

  return {
    x: Math.round((localX / renderedWidth) * nativeWidth),
    y: Math.round((localY / renderedHeight) * nativeHeight),
  };
}
